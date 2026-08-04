"""Flood protection for inbound socket events.

coding-rules.md Part II asks for a rate limit on *every* inbound event, not
just the expensive ones: a client can emit thousands of trivially cheap events
per second and starve the event loop that serves every other game in the
process. It also asks that a client which keeps tripping the limit be
disconnected rather than merely throttled, and that trips be logged with
identity - which is why `allow` refusing is not the end of the story and
`AbuseTracker` exists next to it.

Token buckets rather than fixed windows: a fixed window lets a client spend its
whole allowance at the end of one window and again at the start of the next,
delivering double the limit in a moment straddling the boundary. Buckets refill
continuously in fractional tokens, so the sustained rate is the rate you wrote
down.

Transport-free by design (see coding-rules.md Part V): nothing here imports
Flask or Socket.IO and the clock is injected, so every limit is exercisable in
a test without waiting for real seconds to pass.
"""

import time
from collections.abc import Callable
from typing import NamedTuple

# Monotonic, never wall clock: `time.time()` can step backwards over an NTP
# correction or a manual clock change, and a bucket that reads a backwards jump
# as elapsed time hands out free requests exactly when an operator is fixing
# the clock. The buckets clamp negative deltas as well, so a caller that
# injects a misbehaving clock still cannot be farmed for tokens.
DEFAULT_CLOCK = time.monotonic


class Limit(NamedTuple):
    """One bucket's settings.

    `capacity` is the largest burst allowed after an idle period;
    `refill_per_second` is the sustained rate once that burst is spent.
    """

    capacity: float
    refill_per_second: float


# Generous but finite, and deliberately what ordinary game actions
# (`place_settlement`, `roll_dice`, `place_road`, ...) run under: a human
# playing Catan produces a handful of actions per turn, so 30 in a burst and 5
# per second sustained is far beyond real play while still bounding a script.
# Anything unlisted below lands here, so a new event added to `app.py` is rate
# limited from the moment it exists rather than from the moment someone
# remembers to add it to the table.
DEFAULT_LIMIT = Limit(capacity=30, refill_per_second=5.0)

# Tighter budgets where the event is cheaper for the client than for us.
# Connection and room-join churn is the cheapest way to exhaust server
# resources, so `join` and the game-lifecycle events get a few per minute;
# resync events rebuild and serialize the whole board per call, so they get
# about one per second; chat is set for conversation, not for filling the log.
EVENT_LIMITS: dict[str, Limit] = {
    # Lobby and lifecycle: a real player joins once and starts a game once.
    "join": Limit(capacity=5, refill_per_second=0.05),  # ~3/min sustained
    "start_game": Limit(capacity=3, refill_per_second=0.033),  # ~2/min
    "end_game": Limit(capacity=3, refill_per_second=0.033),  # ~2/min
    "set_rules": Limit(capacity=10, refill_per_second=0.5),
    "set_color": Limit(capacity=10, refill_per_second=0.5),
    # Cheap to ask for, expensive to answer: each one serializes board state.
    "refresh_board": Limit(capacity=10, refill_per_second=1.0),
    "request_state": Limit(capacity=10, refill_per_second=1.0),
    "request_log": Limit(capacity=10, refill_per_second=1.0),
    "request_users": Limit(capacity=10, refill_per_second=1.0),
    "request_rules": Limit(capacity=10, refill_per_second=1.0),
    # Maps: listing reads and validates every file in the maps directory, and
    # a preview deals a whole board through the real engine. Both are far more
    # work per message than anything else a lobby client sends.
    "request_maps": Limit(capacity=10, refill_per_second=1.0),
    "preview_map": Limit(capacity=10, refill_per_second=1.0),
    "save_map": Limit(capacity=10, refill_per_second=0.5),
    "delete_map": Limit(capacity=10, refill_per_second=0.5),
    # Enough for a fast typist trading banter, not enough to fill the panel.
    "chat_message": Limit(capacity=8, refill_per_second=0.5),  # 30/min
    # The command bar is drawn from this, once per client.
    "request_commands": Limit(capacity=10, refill_per_second=1.0),
    # `run_command` is deliberately absent: it spends the `chat_message` bucket
    # instead (see `state.rate_limited`), because the command bar *is* the chat
    # box and a budget of its own would be a way to talk at twice the rate.
}

# A socket that has been silent for this long is either gone or has a fully
# refilled bucket, so its entry carries no information and can be dropped.
IDLE_TTL_SECONDS = 300.0

# Buckets are swept opportunistically rather than on a timer: this module owns
# no thread, and a sweep every N accesses keeps the table proportional to
# recent traffic without paying a scan on every event.
SWEEP_EVERY = 256

# Refusals allowed before the caller should stop talking to this client. Ten
# leaves room for an honest client with an over-eager retry loop or a laggy
# double-click, while a script hammering an event reaches it in well under a
# second.
DISCONNECT_THRESHOLD = 10

# Violations decay: a player who tripped the chat limit once an hour ago is not
# an attacker, and without decay every long-lived socket eventually accumulates
# enough stray trips to be disconnected.
VIOLATION_TTL_SECONDS = 60.0

# Nothing an honest client sends comes close: the largest real payload is a
# trade offer with two resource maps. Oversized messages are rejected on size
# alone, before parsing or validating, because deserializing attacker-sized
# input is itself the denial of service.
MAX_PAYLOAD_BYTES = 8192


def limit_for(event: str) -> Limit:
    """The bucket settings for one event name, or `DEFAULT_LIMIT` if unlisted."""
    return EVENT_LIMITS.get(event, DEFAULT_LIMIT)


class _Bucket:
    """Mutable token-bucket state for one key. Internal to this module."""

    __slots__ = ("tokens", "updated_at")

    def __init__(self, tokens: float, updated_at: float) -> None:
        self.tokens = tokens
        self.updated_at = updated_at


class RateLimiter:
    """Token buckets keyed by an arbitrary string.

    The key is whatever the caller wants to limit: a socket id, a player name,
    a client IP, or any of those combined with an event name. The limiter
    ascribes no meaning to it, so the same instance can enforce a per-socket
    and a per-player budget side by side (Part II asks for both, because one
    attacker opening many sockets defeats a per-socket limit alone).

    The constructor's `limit` is the default for every key; `allow` and
    `retry_after` accept a per-call `limit` so one instance can serve every
    event when the caller keys by `f"{sid}:{event}"`.
    """

    def __init__(
        self,
        limit: Limit = DEFAULT_LIMIT,
        clock: Callable[[], float] = DEFAULT_CLOCK,
        idle_ttl: float = IDLE_TTL_SECONDS,
        sweep_every: int = SWEEP_EVERY,
    ) -> None:
        self._limit = limit
        self._clock = clock
        self._idle_ttl = idle_ttl
        self._sweep_every = sweep_every
        self._buckets: dict[str, _Bucket] = {}
        self._since_sweep = 0

    def allow(self, key: str, cost: float = 1.0, limit: Limit | None = None) -> bool:
        """Consume `cost` tokens for `key` and report whether it was affordable.

        A refusal consumes nothing, so a client that keeps asking during its
        cooldown does not push its own recovery further away.
        """
        effective = limit or self._limit
        bucket = self._refill(key, effective)
        self._maybe_sweep()
        if bucket.tokens < cost:
            return False
        bucket.tokens -= cost
        return True

    def retry_after(self, key: str, cost: float = 1.0, limit: Limit | None = None) -> float:
        """Seconds until `cost` tokens are available; 0.0 when they already are.

        The caller reports this to the client so a legitimately fast player is
        told when to try again instead of being silently ignored.
        """
        effective = limit or self._limit
        bucket = self._refill(key, effective)
        missing = cost - bucket.tokens
        if missing <= 0:
            return 0.0
        if effective.refill_per_second <= 0:
            return float("inf")
        return missing / effective.refill_per_second

    def tokens_left(self, key: str, limit: Limit | None = None) -> float:
        """Tokens currently in `key`'s bucket, for logging and tests."""
        return self._refill(key, limit or self._limit).tokens

    def forget(self, key: str) -> None:
        """Drop a key's bucket, e.g. when its socket disconnects.

        Without this the table grows one entry per socket for the life of the
        process. Forgetting also resets the budget, which is why the caller
        should key by socket id rather than by player name for anything a
        reconnect must not clear.
        """
        self._buckets.pop(key, None)

    def prune(self, now: float | None = None) -> int:
        """Drop buckets untouched for `idle_ttl`; return how many went.

        Called automatically every `sweep_every` accesses, and exposed so a
        caller with a maintenance tick can force it. An idle bucket has
        refilled to capacity by definition, so dropping it changes no decision.
        """
        cutoff = (self._clock() if now is None else now) - self._idle_ttl
        stale = [key for key, bucket in self._buckets.items() if bucket.updated_at <= cutoff]
        for key in stale:
            del self._buckets[key]
        return len(stale)

    def _refill(self, key: str, limit: Limit) -> _Bucket:
        """Bring `key`'s bucket up to date and return it, creating it if new."""
        now = self._clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=limit.capacity, updated_at=now)
            self._buckets[key] = bucket
            return bucket

        # max(0.0, ...) is the defence against a clock that steps backwards:
        # a negative delta must never be spent as refill.
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(limit.capacity, bucket.tokens + elapsed * limit.refill_per_second)
        bucket.updated_at = now
        return bucket

    def _maybe_sweep(self) -> None:
        self._since_sweep += 1
        if self._since_sweep >= self._sweep_every:
            self._since_sweep = 0
            self.prune()


class AbuseTracker:
    """Counts refusals per key so the caller can escalate to a disconnect.

    Kept separate from `RateLimiter` because the two answer different
    questions: a bucket is per event budget, while the decision to hang up is
    about one client's overall behaviour and must also be able to count things
    that are not rate-limit trips at all - Part II asks for the same treatment
    of a client that "repeatedly sends invalid events", which the caller can
    feed in through the same `record_violation`.
    """

    def __init__(
        self,
        threshold: int = DISCONNECT_THRESHOLD,
        violation_ttl: float = VIOLATION_TTL_SECONDS,
        clock: Callable[[], float] = DEFAULT_CLOCK,
    ) -> None:
        self._threshold = threshold
        self._violation_ttl = violation_ttl
        self._clock = clock
        # key -> timestamps of recent violations, oldest first.
        self._violations: dict[str, list[float]] = {}

    @property
    def threshold(self) -> int:
        """Refusals within the window that warrant a disconnect."""
        return self._threshold

    def record_violation(self, key: str) -> int:
        """Record one refusal and return the count still inside the window."""
        now = self._clock()
        recent = self._recent(key, now)
        recent.append(now)
        self._violations[key] = recent
        return len(recent)

    def violations(self, key: str) -> int:
        """How many refusals `key` has inside the window, recording none."""
        return len(self._recent(key, self._clock()))

    def should_disconnect(self, key: str) -> bool:
        """Whether `key` has earned a disconnect rather than another refusal."""
        return self.violations(key) >= self._threshold

    def forget(self, key: str) -> None:
        """Drop a key's history, e.g. once its socket has been disconnected."""
        self._violations.pop(key, None)

    def prune(self) -> int:
        """Drop keys whose violations have all expired; return how many went."""
        now = self._clock()
        stale = [key for key in self._violations if not self._recent(key, now)]
        for key in stale:
            del self._violations[key]
        return len(stale)

    def _recent(self, key: str, now: float) -> list[float]:
        cutoff = now - self._violation_ttl
        return [at for at in self._violations.get(key, ()) if at > cutoff]


def payload_too_large(payload: object, max_bytes: int = MAX_PAYLOAD_BYTES) -> bool:
    """Whether `payload` is too big to be worth parsing.

    Checked before validation, not after: the point is to refuse attacker-sized
    input before spending work on it. Sizing is a cheap structural walk rather
    than a re-serialization, since `json.dumps` on a hostile payload is the
    very cost being avoided; the result is an approximation of wire size that
    is monotonic in the payload's real size, which is all a cap needs.
    """
    return _approximate_size(payload, max_bytes) > max_bytes


def _approximate_size(value: object, budget: int, depth: int = 0) -> int:
    """Sum an approximate byte size, giving up as soon as `budget` is passed.

    Bails out early so a deeply nested or enormous structure costs a walk
    proportional to the cap, not to the payload. Depth is capped for the same
    reason: nesting beyond a handful of levels is not something this protocol's
    payloads do, and recursing to find out is the attack.
    """
    if depth > 8:
        return budget + 1

    if isinstance(value, str):
        return len(value.encode("utf-8", "replace")) + 2
    if isinstance(value, bytes | bytearray):
        return len(value)
    if isinstance(value, bool) or value is None:
        return 5
    if isinstance(value, int | float):
        return len(repr(value))

    total = 2
    if isinstance(value, dict):
        for key, item in value.items():
            total += _approximate_size(key, budget, depth + 1)
            total += _approximate_size(item, budget, depth + 1) + 2
            if total > budget:
                return total
        return total
    if isinstance(value, list | tuple | set | frozenset):
        for item in value:
            total += _approximate_size(item, budget, depth + 1) + 1
            if total > budget:
                return total
        return total

    # Anything else is not JSON the client could have sent; treat it as opaque
    # and small rather than pretending to measure it.
    return 8
