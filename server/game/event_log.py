"""The running record of everything that happened in one game.

Chat and game events share a single log so the client can render them
interleaved in one scrollable panel: a player reading "Bob built a city" next
to "Bob: sorry!" needs them in the order they actually occurred, which two
parallel lists cannot guarantee.

Transport-free by design (see coding-rules.md Part V): nothing here imports
Flask or Socket.IO, so the whole log is exercisable without a server.
"""

import time
from collections import deque
from collections.abc import Callable

# Every kind a log entry may carry. Anything outside this list is a bug in the
# caller, not a client payload, so `log` raises rather than coercing - a typo'd
# kind would otherwise render as an untagged grey line nobody notices.
KINDS = (
    "chat",
    "dice",
    "build",
    "trade",
    "robber",
    "dev_card",
    "turn",
    "game",
    "rules",
    # A slash command that changed the game. Its own kind because the table has
    # to be able to pick these out: a card that appeared because somebody typed
    # /add_resource reads exactly like one that was produced, and the whole
    # bargain of allowing commands is that they are visible.
    "command",
)

# A game left open for hours must not grow without limit: an unbounded list
# would keep every dice roll of a six-hour session in memory and ship the lot
# to anyone who reconnects. 500 entries is far more history than a player
# scrolls back through, and the oldest are dropped silently.
MAX_ENTRIES = 500

# Long enough for a sentence, short enough that one player cannot flood the
# panel or push the rest of the history out of the deque with a single message.
MAX_CHAT_LENGTH = 300


class EventLog:
    """A bounded, append-only log of game events and chat.

    Entries are plain dicts ready for the wire:

        {"id": int, "at": float, "kind": str, "text": str,
         "player": str | None, "details": dict}

    Callers must treat returned entries as read-only; the log hands out the
    same dict objects it stores rather than copying on every read.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        # The clock is injected the same way the engine takes a `random.Random`:
        # a test can hand in a scripted sequence instead of waiting for real
        # seconds to pass.
        self._clock = clock
        # maxlen does the eviction: appending to a full deque drops the oldest
        # entry, so the log can never outgrow its bound.
        self._entries: deque[dict] = deque(maxlen=max_entries)
        self._next_id = 1

    @property
    def last_id(self) -> int:
        """The id of the newest entry, or 0 when nothing has been logged.

        This is what the board payload carries as `log_last_id` so a client
        can tell it missed something and ask for the gap.
        """
        return self._next_id - 1

    def log(self, kind: str, text: str, player: str | None = None, **details) -> dict:
        """Append one entry and return it.

        The timestamp is generated here, never accepted from a caller: a client
        that owns the clock can forge the order of history.
        """
        if kind not in KINDS:
            raise ValueError(f"unknown log kind: {kind!r}")

        entry = {
            "id": self._next_id,
            "at": float(self._clock()),
            "kind": kind,
            "text": text,
            "player": player,
            "details": details,
        }
        self._next_id += 1
        self._entries.append(entry)
        return entry

    def recent(self, limit: int = 100) -> list[dict]:
        """The newest `limit` entries, oldest first."""
        if limit <= 0:
            return []
        return list(self._entries)[-limit:]

    def since(self, after_id: int) -> list[dict]:
        """Every entry newer than `after_id`, oldest first.

        A client that reconnects sends the highest id it already has and gets
        only what it missed, so a dropped connection costs one small message
        instead of the whole history.
        """
        return [entry for entry in self._entries if entry["id"] > after_id]


def sanitize_chat(text: object) -> str:
    """Clean one chat message, or raise `ValueError` if it is unusable.

    Trims, collapses every run of whitespace (including newlines, which would
    otherwise let one message take over the whole panel), and refuses anything
    empty or longer than `MAX_CHAT_LENGTH` - too long is rejected rather than
    truncated so the sender is told, instead of quietly losing half a sentence.

    Deliberately does *not* HTML-escape: escaping belongs to whatever renders
    the text, and escaping in both places produces visible `&amp;lt;` in the
    log. The client renders chat with `textContent`, which is inert by
    construction.
    """
    if not isinstance(text, str):
        raise ValueError("chat message must be a string")

    cleaned = " ".join(text.split())
    if not cleaned:
        raise ValueError("chat message must not be empty")
    if len(cleaned) > MAX_CHAT_LENGTH:
        raise ValueError(f"chat message must be at most {MAX_CHAT_LENGTH} characters")

    return cleaned
