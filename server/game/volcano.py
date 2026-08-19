"""Seafarers, the "Krakatoa"/Volcano variant — the eruption of a volcano hex.

Source: the Seafarers Volcano variant and its "Krakatoa" sub-variant, in which
three volcanoes make an island on number tokens 4, 5 and 6
(ultraboardgames.com/catan/the-volcano.php; catan-expansions-research.md, "The
Volcano"). One mixin on `Game`, the pattern the other scenario modules use (see
`oil_springs.py`, `cloth_for_catan.py`). Every method is gated on the individual
`volcano_hex` rule — never on the scenario's name — so a table not running it is
untouched.

Two things happen when a volcano's number is rolled, in this order:

1. Production. The volcano pays each adjacent building resources of the owner's
   choice, exactly as a Seafarers gold field does. That half is not here: it is
   the shared gold-of-choice production modifier (`game/modifiers.py`), which
   `distribute_resources` resolves before this runs, so a building produces
   before it can be destroyed. A table that runs the volcano without the gold
   variant simply gets no production, which is the basic Volcano variant.

2. Eruption. A die is rolled for the direction the lava flows — one of the hex's
   six corners — and the building standing there is destroyed (a settlement is
   returned to its owner's supply) or downgraded (a city is reduced to a
   settlement). No player chooses the victim; the die decides. The robber cannot
   stop an eruption, only production.
"""


class VolcanoRules:
    """The volcano's eruption. Production is the shared gold-of-choice modifier;
    this adds the destruction that follows it."""

    # --- Board setup -------------------------------------------------------

    def setup_volcano_hexes(self):
        """Read the volcano hexes off the dealt board into game state.

        A volcano is simply a hex of the `volcano` terrain — no per-hex metadata
        needed, unlike the oil springs, because the terrain itself is the marker.
        A no-op for a board that prints none, and off the `volcano_hex` rule, so
        every other board is unaffected.
        """
        if not self.rules['volcano_hex']:
            return
        self.volcano_hexes = {
            hex_key for hex_key, hex_obj in self.hexes.items()
            if hex_obj.type == 'volcano'
        }

    # --- Eruption ----------------------------------------------------------

    def _volcano_corner(self, hex_key: str, direction: int) -> str:
        """The vertex key of one of a hex's six corners, by direction index.

        `direction` is 0-5, indexing `VERTEX_DIRECTIONS` in the board's fixed
        order — the same order a die 1-6 selects from. The corner may not exist
        as a buildable vertex (a hex side that faces open sea has none), in which
        case there is nothing to destroy: the lava flows into the water.
        """
        hx, hy, hz = self._parse_key(hex_key)
        vx, vy, vz = self.VERTEX_DIRECTIONS[direction]
        return self._hex_key(hx + vx, hy + vy, hz + vz)

    def erupt_volcanoes(self, dice_total: int) -> list:
        """Erupt every volcano whose number came up, after production is paid.

        For each volcano hex carrying the rolled number, a die (1-6) picks the
        corner the lava reaches. A settlement there is destroyed and returned to
        its owner's supply; a city is reduced to a settlement; an empty corner —
        or one facing open sea — loses nothing. Returns one record per erupting
        volcano: {'hex', 'die', 'vertex', 'player', 'was', 'now'}, with `player`
        and `was` None when the eruption destroyed nothing. Empty on a 7, off the
        rule, and on a board with no volcanoes. Volcanoes are visited in sorted
        key order so a seeded game erupts identically every run.
        """
        if not self.rules['volcano_hex'] or dice_total == 7:
            return []
        if not self.volcano_hexes:
            return []

        eruptions = []
        for hex_key in sorted(self.volcano_hexes):
            hex_obj = self.hexes.get(hex_key)
            if hex_obj is None or hex_obj.number != dice_total:
                continue
            die = self.rng.randint(1, 6)
            vertex_key = self._volcano_corner(hex_key, die - 1)
            record = {'hex': hex_key, 'die': die, 'vertex': vertex_key,
                      'player': None, 'was': None, 'now': None}
            self._destroy_at(vertex_key, record)
            eruptions.append(record)
        return eruptions

    def _destroy_at(self, vertex_key: str, record: dict):
        """Destroy or downgrade the building on `vertex_key`, filling `record`.

        Mirrors the Oil Springs flood: a city drops to a settlement (the city
        piece back, the settlement piece down), a settlement (harbor settlement
        included) is removed and its piece returned. Nothing standing there
        leaves the record's victim fields None.
        """
        vertex = self.vertices.get(vertex_key)
        if vertex is None or not vertex.building:
            return
        player_name = vertex.building.get('player')
        player = self.get_player(player_name)
        was = vertex.building.get('type')
        record['player'] = player_name
        record['was'] = was
        if was == 'city':
            if player and vertex_key in player.cities:
                player.cities.remove(vertex_key)
                player.settlements.append(vertex_key)
            vertex.building = {'type': 'settlement', 'player': player_name}
            record['now'] = 'settlement'
        elif was in ('settlement', 'harbor_settlement'):
            if player and vertex_key in player.settlements:
                player.settlements.remove(vertex_key)
            if player and vertex_key in getattr(player, 'harbor_settlements', []):
                player.harbor_settlements.remove(vertex_key)
            vertex.building = None
            record['now'] = None
