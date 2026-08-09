"""Mission: Pirate Lairs — discovery, the lair token, and the build lock.

Split out alongside the other rules mixins, like `missions.py` (the container it
advances) and the two sibling missions. Every method is gated on
`self.rules['mission_pirate_lairs']`, so a table not running the mission is
untouched.

The mission, end to end (expansions.md 980-991):

- Every gold field is occupied by a pirate lair, so discovering one drops a
  face-down lair token on it, and while that lair sits unturned the gold field is
  locked — no road on its edges, no settlement on its corners.
- A ship with crews aboard, one end pointing at a corner of the lair, lands them
  onto it; the 3rd crew captures it, rewarding every participant and fighting for
  a hero (`land_crews_on_lair` / `_resolve_lair_capture`). Capturing flips the
  lair and unlocks its field.
- A player picks their surviving crews back up with a ship (`pickup_crews_from_lair`).

The liberated field's "2 gold per adjacent building on its number" is not coded
here: a captured gold field is an ordinary gold hex, and the production loop
already pays 2 gold per building on it (see `test_gold`) once the build-lock is
lifted, so it needs nothing mission-specific.
"""

from game.results import refused
from game.transport import HOLD_SLOTS

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
        Capturing the lair lifts the lock.
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

    # --- The capture -------------------------------------------------------
    #
    # A ship with crews aboard, one end pointing at a corner of a lair hex, may
    # land those crews onto the lair (982). Up to 3 crews may stand on a lair,
    # from any mix of players; the 3rd crew captures it. The rulebook resolves the
    # capture after the mover finishes their movement phase — this resolves it the
    # moment the 3rd crew lands, which is where the client wave will add the wait.

    def _crews_on_lair(self, lair: dict) -> int:
        return sum(lair['crews'].values())

    def land_crews_on_lair(self, player_name: str, ship_edge_key: str,
                           lair_hex_key: str) -> dict:
        """Move a ship's crews onto an adjacent uncaptured lair (expansions.md 982).

        The ship must belong to the player, one of its ends must be a corner of
        the lair hex, and it must carry at least one crew. Lands as many of its
        crews as fit under the 3-crew cap; the 3rd crew triggers the capture.
        """
        if not self.rules['mission_pirate_lairs'] or self.ep is None:
            return refused('RULE_NOT_IN_PLAY', 'This table is not chasing pirate lairs')
        lair = self.ep.lairs.get(lair_hex_key)
        if lair is None or lair['captured']:
            return refused('INVALID_TARGET', 'There is no uncaptured lair there')

        edge = self.edges.get(ship_edge_key)
        ship = edge.ship if edge is not None else None
        if ship is None or ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'That is not one of your ships')
        # An end of the ship points at the lair when a vertex of its edge is a
        # corner of the lair hex.
        if not any(lair_hex_key in self.vertices[v].neighbors['hexes']
                   for v in edge.neighbors['vertices']):
            return refused('INVALID_PLACEMENT', 'The ship does not point at that lair')

        crews_aboard = [piece for piece in ship['cargo'] if piece['type'] == 'crew']
        landing = min(len(crews_aboard), 3 - self._crews_on_lair(lair))
        if landing <= 0:
            return refused('NO_CREWS', 'That ship has no crews to land, or the lair is full')

        for _ in range(landing):
            ship['cargo'].remove(next(p for p in ship['cargo'] if p['type'] == 'crew'))
        lair['crews'][player_name] = lair['crews'].get(player_name, 0) + landing

        captured = self._crews_on_lair(lair) >= 3
        result = {'success': True, 'error': '', 'landed': landing, 'captured': captured}
        if captured:
            result['hero'] = self._resolve_lair_capture(lair_hex_key)
        return result

    def _resolve_lair_capture(self, lair_hex_key: str) -> str:
        """Resolve a full lair: reward every participant, fight for the hero, and
        flip the lair face up (expansions.md 985-991).

        Each player with a crew on the lair takes 2 gold and moves 1 space,
        starting with the player whose turn it is and going clockwise. Then each
        rolls a die and adds their crew count; the highest is the hero and moves 1
        extra space and loses a crew. A tie on the total goes to more crews, and a
        remaining tie re-rolls among the tied. A solo capturer is the hero
        automatically. Returns the hero's name.
        """
        lair = self.ep.lairs[lair_hex_key]
        order = (self.players[self.current_player_index:]
                 + self.players[:self.current_player_index])
        participants = [p.name for p in order if lair['crews'].get(p.name, 0) > 0]

        for name in participants:
            self.gain_gold(name, 2)
            self.advance_mission(name, 'pirate_lairs', 1)

        hero = self._battle_for_hero(participants, lair['crews'])
        self.advance_mission(hero, 'pirate_lairs', 1)
        # The hero returns one of their crews to their supply.
        lair['crews'][hero] -= 1
        if lair['crews'][hero] == 0:
            del lair['crews'][hero]
        self.get_player(hero).crews -= 1

        lair['captured'] = True
        return hero

    def _battle_for_hero(self, participants: list, crews: dict) -> str:
        """The hero of the battle: highest die + crew count, ties to more crews,
        then a re-roll among any still tied. A lone capturer wins outright."""
        if len(participants) == 1:
            return participants[0]
        totals = {name: self.rng.randint(1, 6) + crews[name] for name in participants}
        best = max(totals.values())
        leaders = [name for name in participants if totals[name] == best]
        if len(leaders) == 1:
            return leaders[0]
        most_crews = max(crews[name] for name in leaders)
        by_crews = [name for name in leaders if crews[name] == most_crews]
        if len(by_crews) == 1:
            return by_crews[0]
        return self._battle_for_hero(by_crews, crews)

    def pickup_crews_from_lair(self, player_name: str, ship_edge_key: str,
                              lair_hex_key: str) -> dict:
        """Load a player's surviving crews from beside a captured lair back into a
        ship's hold (expansions.md 989). The ship must point at the lair and have
        room; a crew is a small piece, so a hold takes up to two.
        """
        if not self.rules['mission_pirate_lairs'] or self.ep is None:
            return refused('RULE_NOT_IN_PLAY', 'This table is not chasing pirate lairs')
        lair = self.ep.lairs.get(lair_hex_key)
        if lair is None or not lair['captured']:
            return refused('INVALID_TARGET', 'No captured lair to pick crews up from there')

        edge = self.edges.get(ship_edge_key)
        ship = edge.ship if edge is not None else None
        if ship is None or ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'That is not one of your ships')
        if not any(lair_hex_key in self.vertices[v].neighbors['hexes']
                   for v in edge.neighbors['vertices']):
            return refused('INVALID_PLACEMENT', 'The ship does not point at that lair')

        mine = lair['crews'].get(player_name, 0)
        if mine <= 0:
            return refused('NO_CREWS', 'You have no crews beside that lair')
        # A crew fills one hold slot; the hold holds two.
        room = HOLD_SLOTS - self._hold_used(ship['cargo'])
        take = min(mine, room)
        if take <= 0:
            return refused('HOLD_FULL', 'That ship has no room for a crew')

        lair['crews'][player_name] -= take
        if lair['crews'][player_name] == 0:
            del lair['crews'][player_name]
        for _ in range(take):
            ship['cargo'].append({'type': 'crew', 'size': 'small'})
        return {'success': True, 'error': '', 'picked_up': take}
