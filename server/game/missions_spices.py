"""Mission: Spices for Catan — spice villages, the crew-for-sack trade, delivery.

Split out alongside `missions_lairs`/`missions_fish` and the container they
advance (`missions.py`), one mixin per mission. Every method is gated on
`self.rules['mission_spices']`, so a table not running the mission is untouched.

The mission, end to end (expansions.md 1021-1039):

- Discovering a spice hex pays its 2-gold discovery reward (exploration's own
  path already does, a spice hex not being a plain resource) and stocks its
  village with one spice sack per player from the supply, dealing the hex one of
  the three advantages (`place_spice_village`).
- A crew-laden ship with an end pointing at a corner of a spice hex befriends its
  village: one crew steps off the ship onto the village for good, one spice sack
  comes aboard in trade, and the hex's advantage is earned permanently
  (`befriend_spice_village`). A player may befriend each village only once.
- Until a player has befriended a spice hex, it locks building on its edges and
  corners for that player (`spice_build_refusal`).
- A spice-laden ship pointing at a Council-of-Catan dock unloads: each sack
  advances the marker one space and then leaves the game (`deliver_spices`).

The "use the advantage immediately, even on the ship that just befriended the
village, unless that ship also just discovered the hex" timing (1036) is the
movement layer's to enforce; these methods are the mechanic, as the fish
once-per-movement gate and the lair client-wait are left to their surface wave.
"""

from game.ep import VILLAGE_ADVANTAGES
from game.results import refused

# The Spices for Catan mission card's track length: a marker caps here. The box
# holds 24 spice sacks and each delivered sack is one step, so no run can exceed
# it; approximate until pinned to the printed card, the lead-card VP being what
# actually scores.
SPICES_TRACK_LENGTH = 24

# A spice sack rides as one small cargo piece — two fit a hold, beside a crew.
SPICE_SACK_PIECE = {'type': 'spice_sack', 'size': 'small'}


class MissionSpicesRules:
    """The Spices for Catan mission: villages, the crew-for-sack trade, delivery."""

    def setup_spices(self):
        """Declare the mission's track and seed the advantage bag, when the rule
        is on. A no-op otherwise, and only ever called with an `ep` container."""
        if not self.rules['mission_spices']:
            return
        self.register_mission_track('spices', SPICES_TRACK_LENGTH)
        self._seed_spice_advantages()

    def _seed_spice_advantages(self):
        """Fill the bag the villages draw their advantages from: two of each of
        the three, as the box holds (expansions.md 1032), shuffled."""
        bag = [advantage for advantage in VILLAGE_ADVANTAGES for _ in range(2)]
        self.rng.shuffle(bag)
        self.ep.spice_advantage_bag = bag

    def _draw_spice_advantage(self) -> str:
        """The next advantage for a discovered village, refilling if a scenario
        reveals more spice hexes than the two-of-each bag holds."""
        if not self.ep.spice_advantage_bag:
            self._seed_spice_advantages()
        return self.ep.spice_advantage_bag.pop()

    def place_spice_village(self, hex_key: str):
        """Stock a just-discovered spice hex's village and deal it an advantage.

        One sack per player is placed from the supply (expansions.md 1023); the
        2-gold discovery reward is paid by exploration's own path. A no-op unless
        the mission is on and the hex is a spice hex.
        """
        if not self.rules['mission_spices'] or self.ep is None:
            return
        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None or hex_obj.type != 'spice':
            return
        sacks = 0
        for _ in range(len(self.players)):
            if self.ep.token_supply.get('spice_sack', 0) <= 0:
                break
            self.ep.token_supply['spice_sack'] -= 1
            sacks += 1
        self.ep.spice_hexes[hex_key] = {
            'sacks': sacks,
            'advantage': self._draw_spice_advantage(),
            'crews': [],
        }

    def spice_build_refusal(self, player_name: str, hex_keys):
        """Refuse a build touching a spice hex the player has not befriended, or
        None to proceed (expansions.md 1027). The lock lifts for a player once
        they have placed a crew on that village."""
        if not self.rules['mission_spices'] or self.ep is None:
            return None
        for hex_key in hex_keys:
            spice = self.ep.spice_hexes.get(hex_key)
            if spice is not None and player_name not in spice['crews']:
                return refused(
                    'SPICE_VILLAGE_BLOCKS',
                    'Befriend this spice village before building on its hex',
                )
        return None

    def befriend_spice_village(self, player_name: str, ship_edge_key: str,
                               spice_hex_key: str) -> dict:
        """Trade a crew for a spice sack at a village (expansions.md 1024-1026).

        The ship must belong to the player, point an end at the spice hex, and
        carry a crew; the player must not already be friends with this village,
        which must still hold a sack. One crew steps off onto the village for
        good, one sack comes aboard, and the hex's advantage is earned.
        """
        if not self.rules['mission_spices'] or self.ep is None:
            return refused('RULE_NOT_IN_PLAY', 'This table is not trading spices')
        spice = self.ep.spice_hexes.get(spice_hex_key)
        if spice is None:
            return refused('INVALID_TARGET', 'There is no spice village there')
        if player_name in spice['crews']:
            return refused('ALREADY_FRIENDS', 'You have already befriended that village')
        if spice['sacks'] <= 0:
            return refused('NO_SACKS', 'That village has no spice sack left to trade')

        edge = self.edges.get(ship_edge_key)
        ship = edge.ship if edge is not None else None
        if ship is None or ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'That is not one of your ships')
        if not self._ship_points_at(edge, spice_hex_key):
            return refused('INVALID_PLACEMENT', 'The ship does not point at that village')
        crew = next((piece for piece in ship['cargo'] if piece['type'] == 'crew'), None)
        if crew is None:
            return refused('NO_CREWS', 'That ship carries no crew to place on the village')

        # The crew leaves the ship for the village permanently; in its place a
        # sack comes aboard. Both are small, so the hold stays within its cap.
        ship['cargo'].remove(crew)
        ship['cargo'].append(dict(SPICE_SACK_PIECE))
        spice['crews'].append(player_name)
        spice['sacks'] -= 1
        self.ep.grant_advantage(player_name, spice['advantage'])
        return {'success': True, 'error': '', 'advantage': spice['advantage']}

    def deliver_spices(self, player_name: str, ship_edge_key: str,
                       council_hex_key: str) -> dict:
        """Unload a spice-laden ship at a Council-of-Catan dock (expansions.md 1028).

        The target hex must carry a dock, the ship must belong to the player and
        point an end at it. Every spice sack aboard advances the marker one space
        and is then removed from the game — delivered sacks do not return to the
        supply.
        """
        if not self.rules['mission_spices'] or self.ep is None:
            return refused('RULE_NOT_IN_PLAY', 'This table is not trading spices')
        council = self.hexes.get(council_hex_key)
        if council is None or council.meta is None or not council.meta.docks:
            return refused('INVALID_TARGET', 'That hex has no Council-of-Catan dock')

        edge = self.edges.get(ship_edge_key)
        ship = edge.ship if edge is not None else None
        if ship is None or ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'That is not one of your ships')
        if not self._ship_points_at(edge, council_hex_key):
            return refused('INVALID_PLACEMENT', 'The ship does not point at that dock')

        sacks = [piece for piece in ship['cargo'] if piece['type'] == 'spice_sack']
        if not sacks:
            return refused('NO_CARGO', 'That ship is carrying no spice sacks to unload')

        for sack in sacks:
            ship['cargo'].remove(sack)   # delivered sacks leave the game (1029)
        marker = self.advance_mission(player_name, 'spices', len(sacks))
        return {'success': True, 'error': '', 'delivered': len(sacks), 'marker': marker}
