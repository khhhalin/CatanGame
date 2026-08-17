"""Catan: Oil Springs — oil production, the disaster track, and sequestering.

The scenario by Erik Assadourian & Ty Hansen for Klaus Teuber's Settlers of
Catan (coilspringsgb_2015_web.pdf, the 3-4 player rules on pp. 1-2). One mixin
on `Game`, the pattern the other scenario modules use (see `cloth_for_catan.py`,
`fishing.py`). Every method is gated on the individual rule that governs it —
never on the scenario's name — so a table not running Oil Springs is untouched:

- `oil_tokens` — buildings on an oil spring produce oil (1/settlement, 2/city,
  3/metropolis) on the hex's number, capped at 4 held per player.
- `disaster_track` — using oil advances a shared track; every fifth oil used
  triggers a disaster at the end of the turn (a 7 floods the coasts, otherwise a
  hex is polluted and loses its number), and the board dies at five lost tokens.
- `oil_sequester_vp` — sequestering oil scores 1 VP per 3, and the first to
  sequester 3 takes the 1-VP Champion of the Environment token.
- `oil_metropolis` — 2 oil plus 1 brick/grain/ore upgrades a city into a 3-VP,
  flood-proof metropolis.

Oil lives on `Player.oil`, the way gold lives on `Player.gold`: a public
currency, not a resource card. The general supply, the disaster track and the
removed-token count live on the game and are read straight off it.
"""

# 3-4 player component counts (coilspringsgb_2015_web.pdf p. 1: "use 15 for
# 3-4 players"; "you may only hold a maximum of 4 oil").
OIL_SUPPLY = 15
MAX_OIL_HELD = 4

# The oil a building on an oil spring produces (p. 1): a settlement one, a city
# two, a metropolis three.
OIL_PER_SETTLEMENT = 1
OIL_PER_CITY = 2
OIL_PER_METROPOLIS = 3


class OilSpringsRules:
    """Oil production and the general supply. The disaster track, sequestering
    and metropolises are folded in by the later chunks of this mixin."""

    # --- Board setup -------------------------------------------------------

    def setup_oil_springs(self):
        """Read the oil-spring hexes off the dealt board into game state.

        An oil spring is a hex whose metadata carries `oil_spring` — read the
        same way the Fishermen read their grounds off hex metadata. A no-op for
        a board that prints none, and off the `oil_tokens` rule, so every other
        board is unaffected.
        """
        if not self.rules['oil_tokens']:
            return
        springs = set()
        for hex_key, hex_obj in self.hexes.items():
            meta = getattr(hex_obj, 'meta', None)
            if meta is not None and getattr(meta, 'oil_spring', False):
                springs.add(hex_key)
        self.oil_spring_hexes = springs

    # --- Production --------------------------------------------------------

    def _oil_building_yield(self, vertex_key: str):
        """The oil a building on `vertex_key` produces, and its owner.

        Returns (player, count): a settlement one, a city two, and a metropolis
        three. (None, 0) for an empty vertex. A metropolis is a city the table
        has upgraded — recorded in `oil_metropolises` — so it is checked before
        the plain city.
        """
        vertex = self.vertices.get(vertex_key)
        if vertex is None or not vertex.building:
            return None, 0
        player = vertex.building.get('player')
        if not player:
            return None, 0
        btype = vertex.building.get('type')
        if vertex_key in self.oil_metropolises:
            return player, OIL_PER_METROPOLIS
        if btype == 'city':
            return player, OIL_PER_CITY
        if btype in ('settlement', 'harbor_settlement'):
            return player, OIL_PER_SETTLEMENT
        return None, 0

    def distribute_oil(self, dice_total: int, roller_name: str) -> dict:
        """Produce oil for every building on an oil spring whose number came up.

        Oil is handed out one token at a time, starting with the player who
        rolled and going clockwise, until everyone has what they produced or the
        supply is exhausted (p. 1). A player may never be pushed past the 4-oil
        hold cap, so any excess they produced is simply not taken. Returns
        {player: oil produced}; empty on a 7, off the rule, and on a board with
        no springs.
        """
        if not self.rules['oil_tokens'] or dice_total == 7:
            return {}
        if not self.oil_spring_hexes:
            return {}

        owed = {}
        for hex_key in self.oil_spring_hexes:
            hex_obj = self.hexes.get(hex_key)
            if hex_obj is None or hex_obj.number != dice_total:
                continue
            for vertex_key in self._oil_spring_vertices(hex_key):
                player, count = self._oil_building_yield(vertex_key)
                if player:
                    owed[player] = owed.get(player, 0) + count
        if not owed:
            return {}

        # Clockwise from the roller: rotate the seating so the roller is first.
        order = [player.name for player in self.players]
        if roller_name in order:
            start = order.index(roller_name)
            order = order[start:] + order[:start]

        produced = {}
        # One token at a time, round-robin, until nobody can take another —
        # either they are owed no more, are at the hold cap, or the supply is
        # spent.
        progress = True
        while progress and self.oil_supply > 0:
            progress = False
            for name in order:
                if self.oil_supply <= 0:
                    break
                if owed.get(name, 0) <= 0:
                    continue
                player = self.get_player(name)
                if player is None or player.oil >= MAX_OIL_HELD:
                    owed[name] = 0
                    continue
                player.oil += 1
                self.oil_supply -= 1
                owed[name] -= 1
                produced[name] = produced.get(name, 0) + 1
                progress = True
        return {name: produced[name] for name in sorted(produced)}

    def _oil_spring_vertices(self, hex_key: str) -> list:
        """The buildable intersections that touch this hex — its six corners that
        exist as vertices, the same walk the Fishermen use for a coastal hex."""
        hx, hy, hz = self._parse_key(hex_key)
        found = []
        for vx, vy, vz in self.VERTEX_DIRECTIONS:
            vertex_key = self._hex_key(hx + vx, hy + vy, hz + vz)
            if vertex_key in self.vertices:
                found.append(vertex_key)
        return found

    # --- Client state ------------------------------------------------------

    def oil_client_state(self) -> dict | None:
        """The oil/disaster panel's state, or None off the scenario.

        The springs so the board can badge them, each player's oil for the
        readout, and the shared supply. The disaster track and sequester totals
        are added by the later chunks.
        """
        if not self.rules['oil_tokens']:
            return None
        return {
            'springs': sorted(self.oil_spring_hexes),
            'supply': self.oil_supply,
            'oil': {player.name: player.oil for player in self.players},
        }
