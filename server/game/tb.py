"""Traders & Barbarians state: the fish-token supply, private fish hands, and
the old boot.

Kept in its own module so the base game stays readable, exactly as
`cities_knights.py` and `ep.py` do for their expansions. A base-game reader
never has to page past rules that do not apply to them.

This is a state container, not a mode. The Game builds one whenever a rule that
needs somewhere to keep the fish supply, the per-player fish hands or the old
boot is on — see `rules.TB_STATE_RULES`. Whether a given mechanic actually
happens is decided by that mechanic's own rule, never by the presence of this
object.

The fish supply is the box's own bag (expansions.md 508): 11 tokens showing 1
fish, 10 showing 2, 8 showing 3 — 29 tokens — mixed face down with the single
old-boot token. A token is a plain int (the fish it shows); the boot is the
sentinel `BOOT`. Fish in a hand are secret like a dev card: a viewer sees their
own tokens in full and only a count of anybody else's.
"""

import random

# The face-down supply the box holds (expansions.md 508).
FISH_TOKEN_COUNTS = {1: 11, 2: 10, 3: 8}

# The old boot, mixed into the supply face down. Drawn like a fish token but
# revealed at once and never spent (expansions.md 517).
BOOT = "boot"


class TB:
    """All Traders & Barbarians (Fishermen) state for one game.

    The token counts are passed in rather than read from the constant above
    because a lobby could change them; the constant remains what the box holds.
    """

    def __init__(self, fish_token_counts: dict = None, rng: random.Random = None):
        self.rng = rng or random.Random()

        # The face-down bag, drawn from the end. Seeded by `seed_supply`.
        self.supply = []
        # Spent tokens, face up beside the bag. When the bag runs dry they are
        # turned back over and shuffled into a fresh supply (expansions.md 524).
        self.discard = []
        # player -> the fish tokens (ints) they hold face down, private.
        self.hands = {}
        # Who holds the old boot, or None while it is still in the supply.
        self.old_boot_holder = None

        # Seeded from the board at setup, read by production. A fishing ground is
        # {'number': n, 'vertices': [three coastal vertex keys]}; the lake is a
        # single hex key whose neighbours draw fish on 2/3/11/12.
        self.fishing_grounds = []
        self.lake_hex = None

        # The Caravans (expansions.md 573-601). Camels are neutral pieces sitting
        # on paths, each with a `front` — the vertex its head points toward, where
        # its caravan continues. `camels` maps an edge key to {'front': vertex}.
        # `caravans` is the up-to-three non-branching chains: each is
        # {'arrow': starting-edge, 'edges': [edge keys in order], 'frontier':
        # the vertex the last camel's head points at}. `camel_vote` is the open
        # voting round, or None — see game/caravans.py for its shape.
        self.camels = {}
        self.caravans = []
        self.camel_vote = None

        self._counts = dict(fish_token_counts) if fish_token_counts else dict(FISH_TOKEN_COUNTS)

    # --- Setup -------------------------------------------------------------

    def seed_supply(self):
        """Fill and shuffle the face-down bag, boot mixed in (expansions.md 507)."""
        bag = []
        for fish, count in sorted(self._counts.items()):
            bag.extend([fish] * count)
        bag.append(BOOT)
        self.rng.shuffle(bag)
        self.supply = bag

    def register(self, player_name: str):
        self.hands.setdefault(player_name, [])

    def start_turn(self):
        """Nothing per-turn on the container itself — the boot-pass allowance and
        the like are the game's per-turn state. Present for symmetry with the
        other expansion containers, and a hook if a per-turn field is added."""

    # --- The fish supply ---------------------------------------------------

    def supply_count(self) -> int:
        """How many tokens are face down and drawable right now."""
        return len(self.supply)

    def available(self) -> int:
        """How many tokens could still be drawn this turn — the face-down bag
        plus the face-up discard that is reshuffled in when the bag empties. What
        the "nobody gets fish if the supply is short" check measures against."""
        return len(self.supply) + len(self.discard)

    def _reshuffle_if_empty(self):
        """Turn the spent pile back over into a fresh face-down bag when the last
        face-down token has been drawn (expansions.md 524)."""
        if not self.supply and self.discard:
            self.supply = list(self.discard)
            self.discard = []
            self.rng.shuffle(self.supply)

    def draw_raw(self):
        """Take the next token off the bag, or None if none remain.

        The boot comes back as `BOOT` and is not put in a hand — the caller sets
        `old_boot_holder`. A fish token (an int) is returned for the caller to
        place; this method does not know whose hand it goes into.
        """
        self._reshuffle_if_empty()
        if not self.supply:
            return None
        return self.supply.pop()

    def draw_to_hand(self, player_name: str, cap: int) -> object:
        """Draw one token for a player, honouring the hand cap.

        Returns the token drawn (an int, or `BOOT`), or None if the supply was
        empty. A fish token that would take the player over `cap` is not kept —
        the draw is skipped and None-for-cap is signalled by returning the
        string 'capped', so the caller can log it. The boot never counts toward
        the cap and is always taken.
        """
        hand = self.hands.setdefault(player_name, [])
        # Peek only matters for the cap on a fish token; the boot is exempt, so
        # decide after the draw.
        token = self.draw_raw()
        if token is None:
            return None
        if token == BOOT:
            self.old_boot_holder = player_name
            return BOOT
        if len(hand) >= cap:
            # Over the cap: the token is not kept. Rather than lose it from the
            # game, it goes to the discard so the supply is conserved.
            self.discard.append(token)
            return "capped"
        hand.append(token)
        return token

    def hand(self, player_name: str) -> list:
        return self.hands.setdefault(player_name, [])

    def held_fish(self, player_name: str) -> int:
        """How many fish tokens (cards, not fish pips) a player holds."""
        return len(self.hands.get(player_name, []))

    def spend(self, player_name: str, tokens: list) -> bool:
        """Remove the named tokens from a hand into the discard, if all are held.

        `tokens` is a list of fish values (ints) — a multiset, so two 1-fish
        tokens are `[1, 1]`. Returns False without changing anything if the hand
        does not hold exactly those, so an over-spend or a spend of tokens a
        player never had is refused whole.
        """
        hand = self.hands.get(player_name, [])
        working = list(hand)
        for token in tokens:
            if token in working:
                working.remove(token)
            else:
                return False
        self.hands[player_name] = working
        self.discard.extend(tokens)
        return True

    # --- The old boot ------------------------------------------------------

    def give_boot(self, to_player: str):
        self.old_boot_holder = to_player

    # --- Serialization -----------------------------------------------------

    def to_dict(self, viewer: str = None) -> dict:
        """Serialize for the client.

        A fish hand is private — a viewer sees their own tokens in full and only
        a count of anyone else's, the way a dev-card hand is redacted. The supply
        count, the old-boot holder and the board's fishing grounds and lake are
        public.
        """
        hands = {}
        counts = {}
        for name, hand in self.hands.items():
            counts[name] = len(hand)
            if viewer is not None and name == viewer:
                hands[name] = list(hand)
        return {
            "supply_count": self.supply_count(),
            "discard_count": len(self.discard),
            "old_boot_holder": self.old_boot_holder,
            "fish_counts": counts,
            "fish_hand": hands.get(viewer) if viewer is not None else None,
            "fishing_grounds": [dict(g) for g in self.fishing_grounds],
            "lake_hex": self.lake_hex,
            # The Caravans are public: the camels on their paths, the chains, and
            # the open voting round with each player's bid count (the cards
            # themselves are already face up in front of their bidder).
            "camels": {edge: dict(camel) for edge, camel in self.camels.items()},
            "caravans": [dict(c) for c in self.caravans],
            "camel_vote": dict(self.camel_vote) if self.camel_vote else None,
        }

    _SNAPSHOT_FIELDS = (
        "supply", "discard", "hands", "old_boot_holder",
        "fishing_grounds", "lake_hex",
        "camels", "caravans", "camel_vote",
    )

    def snapshot(self) -> dict:
        """The full state for persistence — nothing redacted: a save has to
        remember the face-down supply and every hand, or a reload would re-deal
        a different bag and lose the private tokens."""
        return {field: getattr(self, field) for field in self._SNAPSHOT_FIELDS}

    def load(self, data: dict):
        for field in self._SNAPSHOT_FIELDS:
            if field in data:
                setattr(self, field, data[field])
