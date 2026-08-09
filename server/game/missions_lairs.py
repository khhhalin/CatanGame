"""Mission: Pirate Lairs — discovery, the lair token, and the build lock.

Split out alongside the other rules mixins, like `missions.py` (the container it
advances) and the two sibling missions. Every method is gated on
`self.rules['mission_pirate_lairs']`, so a table not running the mission is
untouched.

This is the mission's entry point (expansions.md 980-984): every gold field hex
is occupied by a pirate lair, so discovering one drops a face-down lair token on
it, and while that lair sits unturned the gold field is locked — no road on its
edges, no settlement on its corners — until it is captured.

The capture itself (landing crews from a ship, the die-roll hero battle, the
rewards, and the liberated field's 2-gold-per-building payout) is the next
increment; it hangs on the lair this places and on the crews `cargo.py` builds.
"""

from game.results import refused

# The Pirate Lairs mission card's track length: a marker caps here. Approximate
# until it is pinned to the printed card — the lead-card VP (whoever is furthest,
# resolved by the missions container) is what actually scores, so the exact cap
# only bounds a runaway marker.
LAIRS_TRACK_LENGTH = 12


class MissionLairsRules:
    """The Pirate Lairs mission's discovery half: the lair and the build lock."""

    def setup_pirate_lairs(self):
        """Declare the mission's track once, when the rule is on. A no-op
        otherwise, and a no-op without an `ep` container to hold it."""
        if self.rules['mission_pirate_lairs']:
            self.register_mission_track('pirate_lairs', LAIRS_TRACK_LENGTH)

    def place_pirate_lair(self, hex_key: str):
        """Drop a face-down lair on a just-discovered gold field, from the supply.

        The 2-gold discovery reward is paid by exploration's own reward path (a
        gold field is not a plain resource, so it already pays 2 gold on reveal);
        this adds the lair token the mission hangs on. A no-op unless the mission
        is on, the hex is a gold field, and the lair supply still holds a token.
        """
        if not self.rules['mission_pirate_lairs'] or self.ep is None:
            return
        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None or hex_obj.type != 'gold':
            return
        if self.ep.token_supply.get('lair_token', 0) <= 0:
            return
        self.ep.token_supply['lair_token'] -= 1
        self.ep.lairs[hex_key] = {'captured': False, 'crews': {}}

    def uncaptured_lair_hexes(self) -> set:
        """The gold fields that still carry an unturned lair."""
        if self.ep is None:
            return set()
        return {key for key, lair in self.ep.lairs.items() if not lair['captured']}

    def pirate_lair_build_refusal(self, hex_keys):
        """Refuse a build touching an uncaptured pirate lair, or None to proceed.

        expansions.md 984: while a lair sits unturned on a gold field, no road may
        lie on that field's edges and no settlement may stand at its corners.
        Capturing the lair (a later increment) lifts the lock.
        """
        if not self.rules['mission_pirate_lairs']:
            return None
        locked = self.uncaptured_lair_hexes()
        for hex_key in hex_keys:
            if hex_key in locked:
                return refused(
                    'PIRATE_LAIR_BLOCKS',
                    'An uncaptured pirate lair blocks building on its gold field',
                )
        return None
