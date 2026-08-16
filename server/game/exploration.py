"""Exploration: turning face-down tiles face up when a ship reaches them.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. Every method here is gated on a specific reveal rule, never on an
expansion name, so a base-game or plain-Seafarers table is untouched: no hex is
ever hidden without a v2 hidden pool, and the discovery hooks, the reveal and
the build guards all fall through to no-ops when their rule is off.

Two scenarios share the reveal machinery through one seam. Explorers & Pirates
(`ships_explore`) discovers a tile by *moving* a transport ship so an end points
at it, forbids building next to a face-down hex, and pays 2 gold for a hex that
is not a plain resource terrain. Seafarers' The Fog Islands (`fog_reveal`)
discovers by *building* a ship or road that reaches a fog hex, allows exactly
that, and pays only resources — a producing land hex hands its own card and a
sea hex pays nothing (Seafarers 2021, Scenario 3, p.14). `_reveal_hex` and the
pool seeding are common to both; only the trigger and the reward branch differ,
each keyed on its own rule.

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
        if not (self.rules['ships_explore'] or self.rules['fog_reveal']):
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

    def discover_from_build(self, player_name: str, hex_keys) -> list:
        """Reveal every face-down hex a freshly built ship or road now borders.

        The Fog Islands reveal (Seafarers 2021, Scenario 3, p.14): "When you
        connect a ship (or a road) to an unexplored area, you discover a new
        hex." Wired into `build_ship` and `build_road`, so a ship or road laid
        beside a fog hex flips it. Gated on `fog_reveal`, so a table not playing
        the fog board is unaffected, and it shares `_reveal_hex` with the
        Explorers & Pirates discovery — only the trigger and the reward differ.
        Returns the hex keys revealed, in a stable order.
        """
        if not self.rules['fog_reveal']:
            return []
        revealed = []
        for hex_key in maps.sort_hex_keys(hex_keys):
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

        # Missions react to a freshly turned tile: Pirate Lairs drops a face-down
        # lair on a gold field, Fish for Catan pins a placement number to a fish
        # shoal, and Spices for Catan stocks a spice hex's village. Each is a
        # no-op for every other terrain and for a table not running that mission.
        self.place_pirate_lair(hex_key)
        self.place_fish_shoal(hex_key)
        self.place_spice_village(hex_key)

    def _grant_discovery_reward(self, terrain: str, player_name: str):
        """Pay the discoverer, by the reward rule the table is exploring under.

        A plain resource terrain hands its own card either way. The difference
        is what a non-producing tile pays: Explorers & Pirates pays 2 gold for a
        gold field, fish-shoal, spice hex, desert or sea (887); The Fog Islands
        pays nothing for a revealed sea hex, the only non-resource its board can
        deal, and never touches the gold currency (Seafarers 2021, Scenario 3,
        p.14). This is the shared seam: the trigger and the pool are common, the
        reward forks here on the rule.
        """
        if terrain in maps.RESOURCE_TERRAINS:
            self.give_resource(player_name, terrain)
        elif self.rules['fog_reveal']:
            return
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
