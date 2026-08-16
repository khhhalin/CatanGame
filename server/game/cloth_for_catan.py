"""Cloth for Catan: villages that pay cloth to the shipping routes reaching them.

One mixin on `Game`, the pattern the other scenario modules use. Every method is
gated on the individual rule that governs it — `cloth_villages` for the whole
cloth economy — so a table not running the scenario is untouched and the base
game is unchanged.

The mechanic (Seafarers 2021, Scenario 6, p. 22): the small islands carry eight
villages, each a number token sitting on an intersection with a supply of cloth
bolts. As soon as a player joins one of their own settlements or cities to a
village by a shipping route they take 1 bolt at once, and 1 more from that
village every time its number is rolled — drawing from the general supply if the
village is short of paying every connected player, but never once the village
itself is empty. Two bolts of cloth score 1 victory point; an unpaired bolt
scores nothing.

The scoring and the supply reuse the plumbing already here: a bolt is banked in
`cloth_tokens` and read in `victory_points_for` the way the Forgotten Tribe's
gift points are, and a village sits on the barren small islands the no-build and
robber rules already know, derived from the village intersections the way the
gift edges' barren islands are.
"""

# Bolts of cloth each village starts with, and the bolts set beside the board as
# a general supply (Seafarers 2021, p. 22: 5 per village on 8 villages, 10 more
# as a general supply, 50 Catan chits in all).
CLOTH_PER_VILLAGE = 5
CLOTH_GENERAL_SUPPLY = 10


class ClothForCatanRules:
    """The village supplies, the cloth a route earns, and the cloth score."""

    # --- Board setup -------------------------------------------------------

    def setup_cloth_villages(self):
        """Read the map's villages and the barren islands they sit on.

        A village is an intersection the map names with a number token; each
        starts with a full supply of cloth. The barren small islands are the
        land hexes those intersections border that are not the main land, which
        is all the no-build and robber bans need — derived from the villages the
        way the Forgotten Tribe derives them from its gift edges. A no-op for a
        map that prints no villages, so every other board is unaffected.
        """
        definition = self.map_definition
        if definition is None or not getattr(definition, 'cloth_villages', ()):
            return
        for vertex_key, number in definition.cloth_villages:
            if vertex_key not in self.vertices:
                continue
            self.village_number[vertex_key] = number
            self.village_cloth[vertex_key] = CLOTH_PER_VILLAGE
            self.village_traders[vertex_key] = set()
            for hex_key in self.vertices[vertex_key].neighbors.get('hexes', []):
                if not self.is_main_land(hex_key):
                    self.barren_island_hexes.add(hex_key)

    # --- Which routes reach a village --------------------------------------

    def village_route_players(self, vertex_key: str) -> list:
        """Players joined to this village by one of their own shipping routes.

        A player is connected when one of their ships lies on a side of the
        village intersection and the route that ship belongs to touches one of
        their own settlements or cities — "a shipping route between one of your
        own settlements/cities and a village". Read live off the ships, so it is
        the truth about the board rather than a cached guess, and sorted so a
        payout order never depends on set iteration order.
        """
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return []
        found = set()
        for edge_key in vertex.neighbors.get('edges', []):
            edge = self.edges.get(edge_key)
            if edge is None or edge.ship is None:
                continue
            player_name = edge.ship.get('player')
            if not player_name or player_name in found:
                continue
            route = self.ship_route(player_name, edge_key)
            if self._route_buildings(player_name, route):
                found.add(player_name)
        return sorted(found)

    def _draw_cloth_from(self, vertex_key: str) -> bool:
        """Take one bolt for a village payout, the village first then the supply.

        The village pays from its own stack; only once that runs short of the
        players it owes does it draw the shortfall from the general supply
        (p. 22). Returns whether a bolt was actually paid — false when both are
        empty, which the caller reads as nobody drew.
        """
        if self.village_cloth.get(vertex_key, 0) > 0:
            self.village_cloth[vertex_key] -= 1
            return True
        if self.cloth_general_supply > 0:
            self.cloth_general_supply -= 1
            return True
        return False

    # --- Earning cloth -----------------------------------------------------

    def claim_cloth_connections(self, player_name: str) -> dict:
        """Pay the one bolt a newly-joined village owes, once per village.

        Called after a ship is built or moved, the way `build_ship` calls
        `claim_coast_gift`. A no-op without `cloth_villages`. For each village
        this player has just reached for the first time it banks the connection
        and takes 1 bolt from that village's own supply — never the general one,
        which only extends a roll payout — and takes nothing if the village is
        already empty. Returns {village vertex: 1} for each bolt paid.
        """
        if not self.rules['cloth_villages']:
            return {}
        gained = {}
        for vertex_key in sorted(self.village_number):
            traders = self.village_traders.setdefault(vertex_key, set())
            if player_name in traders:
                continue
            if player_name not in self.village_route_players(vertex_key):
                continue
            traders.add(player_name)
            if self.village_cloth.get(vertex_key, 0) > 0:
                self.village_cloth[vertex_key] -= 1
                self.cloth_tokens[player_name] = self.cloth_tokens.get(player_name, 0) + 1
                gained[vertex_key] = 1
        return gained

    def distribute_cloth(self, dice_total: int) -> dict:
        """Pay a bolt to every route joined to a village whose number came up.

        Returns {player: bolts drawn}. Empty when no village matched, and — for a
        village that is already empty when its number is rolled — nobody draws
        and the general supply is left alone (p. 22). A no-op without the rule
        and on a 7, which pays nothing.
        """
        if not self.rules['cloth_villages'] or dice_total == 7:
            return {}
        gained = {}
        for vertex_key in sorted(self.village_number):
            if self.village_number[vertex_key] != dice_total:
                continue
            # Zero bolts at the village when its number is rolled: no one draws,
            # and the general supply is not touched.
            if self.village_cloth.get(vertex_key, 0) <= 0:
                continue
            for player_name in self.village_route_players(vertex_key):
                if self._draw_cloth_from(vertex_key):
                    self.cloth_tokens[player_name] = self.cloth_tokens.get(player_name, 0) + 1
                    gained[player_name] = gained.get(player_name, 0) + 1
        return {name: gained[name] for name in sorted(gained)}

    # --- Scoring and the supply -------------------------------------------

    def cloth_victory_points(self, player_name: str) -> int:
        """A player's victory points from cloth: two bolts to a point.

        Integer division, so an unpaired bolt scores nothing (p. 22). Read live
        off the bolt count, so a point appears the moment a second bolt lands.
        """
        return self.cloth_tokens.get(player_name, 0) // 2

    def villages_with_cloth_remaining(self) -> int:
        """How many villages still hold at least one bolt.

        The rulebook's second end condition is reached when three or fewer
        villages still hold cloth; this is the count that alternate end reads.
        """
        return sum(1 for vertex_key in self.village_number
                   if self.village_cloth.get(vertex_key, 0) > 0)

    def cloth_alternate_end(self) -> dict | None:
        """The scenario's second end condition, checked after a roll pays cloth.

        The game ends the moment three or fewer villages still hold a bolt, and
        the winner is the player with the most victory points, a tie broken in
        favour of more bolts of cloth (expansions.md 191-192). Marks the game
        finished and returns {'winner', 'victory_points', 'reason'}, or None if
        the board still has more than three villages in cloth. Gated on
        `cloth_villages` — every village-less board reports zero remaining, which
        is `<= 3`, so this gate is the only thing keeping a base game from ending
        on its first roll.
        """
        if not self.rules['cloth_villages']:
            return None
        if self.villages_with_cloth_remaining() > 3:
            return None
        self.game_state = "finished"
        winner = self._cloth_endgame_winner()
        return {
            'winner': winner,
            'victory_points': self.victory_points_for(winner),
            'reason': 'villages_depleted',
        }

    def _cloth_endgame_winner(self) -> str:
        """Who takes the villages-out win: most victory points, a tie broken by
        more bolts of cloth (expansions.md 192).

        The rulebook names no third tiebreak, so a pair still level on both is
        settled by seat order — `max` returns the first player reaching the top
        key — which is deterministic rather than an undecided winner that would
        stall the announcement.
        """
        return max(
            self.players,
            key=lambda player: (self.victory_points_for(player.name),
                                self.cloth_tokens.get(player.name, 0)),
        ).name
