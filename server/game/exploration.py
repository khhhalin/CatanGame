"""Exploration: turning face-down tiles face up when a ship reaches them.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. Every method here is gated on `self.rules['ships_explore']`, never on an
expansion name, so a base-game or Seafarers table is untouched: no hex is ever
hidden without a v2 hidden pool, and the discovery hook, the reveal and the two
build guards all fall through to no-ops when the rule is off.

The board holds the truth about a hidden tile — its real terrain sits on the
`Hex` with `hidden=True`, redacted from `get_board_data` — so discovery is only
a matter of flipping the flag, drawing the tile's number token, and paying the
reward. The undiscovered pool and the reveal order live on `self.ep`, and so do
the per-area number-token stacks a discovery draws from (expansions.md 883-893).
"""

from game import maps

# A discovery that is not a plain resource terrain pays 2 gold instead of a
# resource card: a gold field, a fish-shoal, a spice hex, a desert or a stretch
# of sea (expansions.md 888). A resource terrain pays 1 card of its own type
# (887).
DISCOVERY_GOLD = 2


class ExplorationRules:
    """Discovering hidden tiles by ship, and the builds it forbids."""

    # --- Seeding the pool --------------------------------------------------

    def _seed_exploration_pool(self):
        """Fill the undiscovered pool and its number stacks from the map.

        Called once the board's hidden tiles exist. The tokens a hidden pool
        lists in the map file are not dealt onto the board — a hidden tile
        carries no number until it is discovered — so they are shuffled per
        region here and popped at reveal instead. A no-op without the rule, an
        `ep` container, or a map to read the pools from.
        """
        if self.ep is None or self.map_definition is None:
            return
        if not self.rules['ships_explore']:
            return

        hidden_keys = [key for key, hex_obj in self.hexes.items() if hex_obj.hidden]
        self.ep.seed_hidden_tiles(maps.sort_hex_keys(hidden_keys))

        stacks = {}
        for region in self.map_definition.regions:
            if region.pool.is_hidden:
                numbers = list(region.pool.numbers)
                self.rng.shuffle(numbers)
                stacks[region.id] = numbers
        self.ep.seed_number_stacks(stacks)

    # --- Discovery on ship movement ----------------------------------------

    def discover_from_ship(self, player_name: str, edge_key: str) -> list:
        """Reveal every undiscovered hex an end of the ship on this edge points at.

        Either end (bow or stern) of a ship is one of its edge's two
        intersections, and an end "points at" a hex when that intersection is a
        corner of it (884). Wired into `move_transport_ship` so the check runs
        the moment a ship arrives; guarded so a table not exploring is
        unaffected. Returns the hex keys revealed, in a stable order.
        """
        if not self.rules['ships_explore']:
            return []
        edge = self.edges.get(edge_key)
        if edge is None:
            return []

        revealed = []
        for vertex_key in edge.neighbors['vertices']:
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            for hex_key in vertex.neighbors['hexes']:
                hex_obj = self.hexes.get(hex_key)
                if hex_obj is not None and hex_obj.hidden and hex_key not in revealed:
                    self._reveal_hex(hex_key, player_name)
                    revealed.append(hex_key)
        return revealed

    def _reveal_hex(self, hex_key: str, player_name: str):
        """Turn one tile face up: draw its token, record it, pay the reward."""
        hex_obj = self.hexes[hex_key]
        hex_obj.hidden = False

        # A producing tile takes a number token from its area's stack; a desert
        # or sea takes none, exactly as the deal would have decided.
        if maps.takes_a_token(hex_obj.type) and self.ep is not None:
            region_id = self.map_definition.region_of().get(hex_key)
            hex_obj.number = self.ep.draw_number(region_id)

        if self.ep is not None:
            self.ep.reveal(hex_key, player_name)

        self._grant_discovery_reward(hex_obj.type, player_name)

        # Missions react to a freshly turned tile: the Pirate Lairs mission drops
        # a face-down lair on a gold field. A no-op for every other terrain and
        # for a table not running the mission.
        self.place_pirate_lair(hex_key)

    def _grant_discovery_reward(self, terrain: str, player_name: str):
        """Pay the discoverer: 1 resource of the terrain's type, or 2 gold (887).

        A plain resource terrain hands its own card; anything else — a gold
        field, a fish-shoal, a spice hex, a desert or sea — pays 2 gold instead.
        """
        if terrain in maps.RESOURCE_TERRAINS:
            self.give_resource(player_name, terrain)
        else:
            self.gain_gold(player_name, DISCOVERY_GOLD)

    # --- Build guards ------------------------------------------------------

    def undiscovered_build_refusal(self, hex_keys):
        """Refuse a build touching a face-down hex, or None if it may proceed.

        A road may not lie on a path beside an undiscovered hex, and a
        settlement may not stand at an intersection beside one (891). A hex is
        only ever hidden with a v2 pool, and the caller is gated on the rule, so
        this is a no-op on every base-game and Seafarers board.
        """
        from game.results import refused

        for hex_key in hex_keys:
            hex_obj = self.hexes.get(hex_key)
            if hex_obj is not None and hex_obj.hidden:
                return refused(
                    'UNDISCOVERED_ADJACENT',
                    'You cannot build next to an undiscovered hex',
                )
        return None
