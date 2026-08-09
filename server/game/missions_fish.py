"""Mission: Fish for Catan — shoals, hauls, catching, and the Council docks.

Split out alongside `missions_lairs` and the container it advances (`missions.py`),
one mixin per mission. Every method is gated on `self.rules['mission_fish']`, so a
table not running the mission is untouched.

The mission, end to end (expansions.md 1000-1019):

- Discovering a fish shoal pays its 2-gold discovery reward (exploration's own
  reward path already does, a shoal not being a plain resource) and pins a number
  1-6 to it — the roll a fish-placement must match (`place_fish_shoal`).
- Once during a movement phase a player rolls a die; if it matches a discovered
  shoal that carries neither a haul nor a pirate, a fish haul comes off the supply
  onto that shoal (`roll_fish_haul`). The once-per-movement gate is the turn-flow
  layer's to enforce, exactly as the lair capture leaves its client wait to the
  surface wave; this method is the mechanic.
- An *empty* ship with an end pointing at a shoal-with-haul scoops it up — a haul
  fills the whole hold, so the ship must arrive empty (`catch_fish`).
- A fish-laden ship pointing at a Council-of-Catan dock unloads: the haul returns
  to the supply and the mission marker advances (`deliver_fish`).
- A pirate landing on a shoal-with-haul scatters it back to the supply
  (`strip_fish_haul`). A fish shoal is not a sea hex today, so the pirate cannot
  yet sit on one and the hook is dormant; it is wired so it simply works once
  shoals become sea-navigable in the movement wave.
"""

from game.results import refused

# The Fish for Catan mission card's track length: a marker caps here. Six is the
# haul supply, so every haul delivered once fills the track; approximate until it
# is pinned to the printed card, the lead-card VP being what actually scores.
FISH_TRACK_LENGTH = 6

# A landed haul rides as one large cargo piece, which fills the hold — so a ship
# must arrive empty to catch and carries nothing else until it has delivered.
FISH_HAUL_PIECE = {'type': 'fish_haul', 'size': 'large'}


class MissionFishRules:
    """The Fish for Catan mission: shoals, hauls, the catch and the delivery."""

    def setup_fish(self):
        """Declare the mission's track once, when the rule is on. A no-op
        otherwise, and a no-op without an `ep` container to hold it."""
        if self.rules['mission_fish']:
            self.register_mission_track('fish', FISH_TRACK_LENGTH)

    def place_fish_shoal(self, hex_key: str):
        """Pin a placement number 1-6 to a just-discovered fish shoal.

        The 2-gold discovery reward is paid by exploration's own reward path (a
        shoal is not a plain resource), so this only records the number a later
        fish-placement roll must match. A no-op unless the mission is on and the
        hex is a fish shoal.
        """
        if not self.rules['mission_fish'] or self.ep is None:
            return
        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None or hex_obj.type != 'fish':
            return
        self.ep.fish_shoals[hex_key] = {'number': self.rng.randint(1, 6), 'haul': False}

    def roll_fish_haul(self, player_name: str) -> dict:
        """Roll one die to drop a fish haul onto a matching shoal (expansions.md 1007).

        The roll lands a haul from the supply onto a discovered shoal whose number
        it matches, as long as that shoal carries neither a haul already nor a
        pirate. Reports the roll and which shoal, if any, took the haul.
        """
        if not self.rules['mission_fish'] or self.ep is None:
            return refused('RULE_NOT_IN_PLAY', 'This table is not fishing')

        roll = self.rng.randint(1, 6)
        target = next(
            (key for key, shoal in self.ep.fish_shoals.items()
             if shoal['number'] == roll and not shoal['haul']
             and not self.ep.pirate_at(key)),
            None,
        )
        if target is None or self.ep.token_supply.get('fish_haul', 0) <= 0:
            return {'success': True, 'error': '', 'roll': roll, 'placed': None}

        self.ep.token_supply['fish_haul'] -= 1
        self.ep.fish_shoals[target]['haul'] = True
        return {'success': True, 'error': '', 'roll': roll, 'placed': target}

    def _hex_corner_vertices(self, hex_key: str) -> set:
        """The intersection keys around a hex, read from the edges bordering it.

        A sea hex is deliberately absent from a vertex's own hex list (a
        settlement belongs to the land), but every edge lists whichever hexes it
        separates, sea included — so a Council-of-Catan sea hex and a fish shoal
        alike find their corners this way.
        """
        corners = set()
        for edge in self.edges.values():
            if hex_key in edge.neighbors['hexes']:
                corners.update(edge.neighbors['vertices'])
        return corners

    def _ship_points_at(self, edge, hex_key: str) -> bool:
        """Whether an end of the ship on this edge is a corner of the hex."""
        return bool(set(edge.neighbors['vertices']) & self._hex_corner_vertices(hex_key))

    def catch_fish(self, player_name: str, ship_edge_key: str, shoal_hex_key: str) -> dict:
        """Scoop a shoal's haul into an empty ship (expansions.md 1011).

        The ship must belong to the player, point an end at the shoal, and be
        empty — a haul fills the whole hold. Moves the haul off the shoal and into
        the ship's cargo.
        """
        if not self.rules['mission_fish'] or self.ep is None:
            return refused('RULE_NOT_IN_PLAY', 'This table is not fishing')
        shoal = self.ep.fish_shoals.get(shoal_hex_key)
        if shoal is None or not shoal['haul']:
            return refused('INVALID_TARGET', 'There is no fish haul there to catch')

        edge = self.edges.get(ship_edge_key)
        ship = edge.ship if edge is not None else None
        if ship is None or ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'That is not one of your ships')
        if not self._ship_points_at(edge, shoal_hex_key):
            return refused('INVALID_PLACEMENT', 'The ship does not point at that shoal')
        if ship['cargo']:
            return refused('HOLD_FULL', 'A fish haul fills the hold; that ship must be empty')

        shoal['haul'] = False
        ship['cargo'].append(dict(FISH_HAUL_PIECE))
        return {'success': True, 'error': '', 'caught': shoal_hex_key}

    def deliver_fish(self, player_name: str, ship_edge_key: str, council_hex_key: str) -> dict:
        """Unload a fish-laden ship at a Council-of-Catan dock (expansions.md 1015).

        The target hex must carry a dock (a Council-of-Catan sea hex), the ship
        must belong to the player, point an end at it, and be carrying a haul. The
        haul returns to the supply and the mission marker advances one step.

        The exact dock-side an end points at is not matched here — an end touching
        the Council hex is enough; pinning delivery to a specific dock side is a
        refinement for when the surface wave draws the docks.
        """
        if not self.rules['mission_fish'] or self.ep is None:
            return refused('RULE_NOT_IN_PLAY', 'This table is not fishing')
        council = self.hexes.get(council_hex_key)
        if council is None or council.meta is None or not council.meta.docks:
            return refused('INVALID_TARGET', 'That hex has no Council-of-Catan dock')

        edge = self.edges.get(ship_edge_key)
        ship = edge.ship if edge is not None else None
        if ship is None or ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'That is not one of your ships')
        if not self._ship_points_at(edge, council_hex_key):
            return refused('INVALID_PLACEMENT', 'The ship does not point at that dock')

        haul = next((p for p in ship['cargo'] if p['type'] == 'fish_haul'), None)
        if haul is None:
            return refused('NO_CARGO', 'That ship is carrying no fish haul to unload')

        ship['cargo'].remove(haul)
        self.ep.token_supply['fish_haul'] = self.ep.token_supply.get('fish_haul', 0) + 1
        marker = self.advance_mission(player_name, 'fish', 1)
        return {'success': True, 'error': '', 'delivered': council_hex_key, 'marker': marker}

    def strip_fish_haul(self, hex_key: str):
        """Scatter a shoal's haul back to the supply when a pirate lands on it
        (expansions.md 1019). A no-op unless a shoal there actually carries one."""
        if self.ep is None:
            return
        shoal = self.ep.fish_shoals.get(hex_key)
        if shoal is not None and shoal['haul']:
            shoal['haul'] = False
            self.ep.token_supply['fish_haul'] = self.ep.token_supply.get('fish_haul', 0) + 1
