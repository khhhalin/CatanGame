"""Board geometry and generation.

Split out of `game.py` so the rules engine is readable on its own: this is the
cube-coordinate maths from hex.md plus the one-time layout of hexes, vertices,
edges and ports. It is a mixin rather than free functions because every method
here reads the board configuration off the Game (the chosen layout, `rng`, and
the dicts it fills in), and threading all of that through parameters would
obscure the geometry, which is the hard part.

A layout in `LAYOUTS` is one selectable map: which tiles the island is made of,
what is in the box for a board that size, and whether any of it is printed
rather than shuffled.
"""

import logging

from game import maps
from game.hex_models import Edge, Hex, Vertex

logger = logging.getLogger(__name__)

# The number tokens in the base-game box: 18 of them, 2 and 12 once each and
# every other number twice. A 7 is the robber's roll and never sits on a hex.
NUMBER_TOKENS = (2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12)

# The tokens printed in red — the two likeliest rolls. The rulebook's variable
# setup forbids them on neighbouring hexes; the "Keep 6s and 8s apart" rule is
# what enforces it here.
RED_NUMBERS = (6, 8)

# A cap on the swap loop below. Every pass fixes one hex and each fix is a swap
# with a hex that has no red neighbour, so a legal board is reached in far fewer
# passes than there are tokens; the cap only stops a pathological layout (one a
# hand-written island could produce) from spinning forever.
MAX_RED_SEPARATION_PASSES = 200

# The 9 harbour pieces in the base-game box: 4 generic 3:1 harbours and one 2:1
# harbour per resource, since the almanac allows "only 1 special harbor for each
# type of resource".
PORT_TYPES = ('generic', 'generic', 'generic', 'generic',
              'wood', 'brick', 'sheep', 'wheat', 'ore')

# The 19 base-game terrain hexes.
RESOURCE_TYPES = (
    ('wood',) * 4 + ('wheat',) * 4 + ('sheep',) * 4
    + ('brick',) * 3 + ('ore',) * 3 + ('desert',)
)

# The 5–6 player game plays on both boxes at once: the base game's 19 terrain
# hexes plus the extension's 11 (1 desert, 2 fields, 2 forest, 2 pasture,
# 2 mountains, 2 hills), for 30 land hexes and 2 deserts.
LARGE_RESOURCE_TYPES = (
    ('wood',) * 6 + ('wheat',) * 6 + ('sheep',) * 6
    + ('brick',) * 5 + ('ore',) * 5 + ('desert',) * 2
)

# The extension's own 28 tokens replace the base game's 18: 2 and 12 twice
# each, every other number three times. 28 tokens for 30 hexes less 2 deserts.
LARGE_NUMBER_TOKENS = (
    (2,) * 2 + (12,) * 2
    + tuple(number for number in (3, 4, 5, 6, 8, 9, 10, 11) for _ in range(3))
)

# 11 harbours: the base game's 9 plus the extension's two frame pieces, which
# are one more generic 3:1 and a second 2:1 wool harbour.
LARGE_PORT_TYPES = PORT_TYPES + ('generic', 'sheep')


def _hexagon(radius: int) -> tuple:
    """The land tiles of a regular hexagonal island, in cube coordinates.

    Rows first, left to right within a row, which is the order a printed map
    is read in.
    """
    coords = []
    for row in range(-radius, radius + 1):
        first = max(-radius, -radius - row)
        last = min(radius, radius - row)
        for column in range(first, last + 1):
            coords.append((3 * column, -3 * (column + row), 3 * row))
    return tuple(coords)


def _island_rows(rows: tuple) -> tuple:
    """Land tiles listed row by row as (row, leftmost column, width)."""
    coords = []
    for row, first_column, width in rows:
        for column in range(first_column, first_column + width):
            coords.append((3 * column, -3 * (column + row), 3 * row))
    return tuple(coords)


# The 5–6 player island is not a regular hexagon — its rows run 3-4-5-6-5-4-3 —
# so it is spelled out row by row. A row of 6 forces the whole island half a
# tile off centre horizontally; there is no arrangement of these rows that is
# both this shape and centred.
LARGE_ISLAND = _island_rows((
    (-3, 0, 3), (-2, -1, 4), (-1, -2, 5), (0, -3, 6), (1, -3, 5), (2, -3, 4), (3, -3, 3),
))

# The starting map for beginners, read off Illustration A on page 3 of the
# rulebook: five rows of 3, 4, 5, 4 and 3 terrain hexes, top row first.
BEGINNER_ISLAND = (
    ('ore', 10), ('sheep', 2), ('wood', 9),
    ('wheat', 12), ('brick', 6), ('sheep', 4), ('brick', 10),
    ('wheat', 9), ('wood', 11), ('desert', None), ('wood', 3), ('ore', 8),
    ('wood', 8), ('ore', 3), ('wheat', 4), ('sheep', 5),
    ('brick', 5), ('wheat', 6), ('sheep', 11),
)

# One entry per selectable map. `island` is the printed tile-by-tile map for a
# fixed layout and None when the tiles are shuffled; `fixed` also freezes where
# the harbours sit, so the same map comes back every game.
LAYOUTS = {
    'random': {
        'hexes': _hexagon(2),
        'resources': RESOURCE_TYPES,
        'numbers': NUMBER_TOKENS,
        'ports': PORT_TYPES,
        'island': None,
        'fixed': False,
    },
    'beginner': {
        'hexes': _hexagon(2),
        'resources': RESOURCE_TYPES,
        'numbers': NUMBER_TOKENS,
        'ports': PORT_TYPES,
        'island': BEGINNER_ISLAND,
        'fixed': True,
    },
    'large': {
        'hexes': LARGE_ISLAND,
        'resources': LARGE_RESOURCE_TYPES,
        'numbers': LARGE_NUMBER_TOKENS,
        'ports': LARGE_PORT_TYPES,
        'island': None,
        'fixed': False,
    },
}

DEFAULT_LAYOUT = 'random'


class BoardBuilder:
    """Everything that turns a layout into a populated board."""

    HEX_DIRECTIONS = [
        (3, -3, 0),  # Right
        (3, 0, -3),  # Upper right
        (0, 3, -3),  # Upper left
        (-3, 3, 0),  # Left
        (-3, 0, 3),  # Lower left
        (0, -3, 3),  # Lower right
    ]

    VERTEX_DIRECTIONS = [
        (1, -2, 1),  # Top-right
        (2, -1, -1),  # Right
        (1, 1, -2),  # Bottom-right
        (-1, 2, -1),  # Bottom-left
        (-2, 1, 1),  # Left
        (-1, -1, 2),  # Top-left
    ]

    EDGE_DIRECTIONS = [
        (1, -1, 0),  # Right
        (1, 0, -1),  # Upper right
        (0, 1, -1),  # Upper left
        (-1, 1, 0),  # Left
        (-1, 0, 1),  # Lower left
        (0, -1, 1),  # Lower right
    ]

    def _hex_key(self, x: int, y: int, z: int) -> str:
        """
        Create a hex key string from cube coordinates.

        Args:
            x, y, z: Cube coordinates (must satisfy x + y + z = 0)

        Returns:
            String in format "x,y,z"
        """
        return f"{x},{y},{z}"

    def _parse_key(self, key: str) -> tuple:
        """
        Parse a coordinate key string into (x, y, z) tuple.

        Args:
            key: String in format "x,y,z"

        Returns:
            Tuple of (x, y, z) integers
        """
        parts = key.split(',')
        return int(parts[0]), int(parts[1]), int(parts[2])

    def _edge_twin(self, x: int, y: int, z: int) -> tuple:
        """The other cube coordinate naming this same hex side.

        Hex centres sit 3 apart, so a shared side has no lattice midpoint: each
        of the two hexes it separates names the side from its own centre, one
        step out. The two names therefore differ by exactly one edge direction
        — the one that, subtracted, lands on a hex centre — and no other
        direction can qualify because the six are all distinct modulo 3.

        Args:
            x, y, z: An edge coordinate (exactly one divisible by 3)

        Returns:
            Tuple of (x, y, z) for the twin coordinate
        """
        for dx, dy, dz in self.EDGE_DIRECTIONS:
            if (x - dx) % 3 == 0 and (y - dy) % 3 == 0 and (z - dz) % 3 == 0:
                return x + dx, y + dy, z + dz
        raise ValueError(f"{x},{y},{z} is not an edge coordinate")

    def _edge_key(self, x: int, y: int, z: int) -> str:
        """The one key for a hex side, whichever of its two hexes named it.

        Both names identify the same strip of land, so the board keeps the
        lower of the pair and nothing else. Without this the board held two
        Edge objects per inland side and two players could each build a road on
        it, one under each name.

        Args:
            x, y, z: Either of the side's two edge coordinates

        Returns:
            String in format "x,y,z"
        """
        return self._hex_key(*min((x, y, z), self._edge_twin(x, y, z)))

    def canonical_edge_key(self, key: str) -> str | None:
        """This board's key for a hex side, given any name for it.

        Public because a save written before a side had a single key names half
        of its roads and harbours by the twin coordinate the board no longer
        holds, and loading such a game has to translate. Returns None when the
        key names nothing on this board.
        """
        try:
            canonical = self._edge_key(*self._parse_key(key))
        except (IndexError, ValueError):
            return None
        return canonical if canonical in self.edges else None

    def _generate_board(self):
        """
        Generate the complete Catan board.

        This method:
        1. Creates the island of the chosen layout, and the sea around it
        2. Generates all vertices and edges for each land hex
        3. Builds neighbor relationships algebraically
        4. Lays out terrain, number tokens and harbours
        """
        if self.map_definition is not None:
            # A custom map authors its own sea, because deriving it from
            # adjacency is wrong the moment there are two islands: two
            # landmasses three hexes apart would have no water between them,
            # only a hole where hexes do not exist.
            land_hex_keys, ocean_hex_keys = self._apply_map_instance(
                maps.instantiate(self.map_definition, self.rng)
            )
        else:
            self.board_layout = LAYOUTS.get(
                self.rules.get('board_layout'), LAYOUTS[DEFAULT_LAYOUT]
            )
            island = self.board_layout['hexes']

            land_hex_keys = {self._hex_key(*coords) for coords in island}

            # The sea is whatever touches the island. Derived from adjacency
            # rather than from a radius, because a layout can be any shape: the
            # 5–6 player island is not a hexagon, so no radius describes it.
            ocean_hex_keys = set()
            for x, y, z in island:
                for dx, dy, dz in self.HEX_DIRECTIONS:
                    neighbor_key = self._hex_key(x + dx, y + dy, z + dz)
                    if neighbor_key not in land_hex_keys:
                        ocean_hex_keys.add(neighbor_key)

            # Step 2: Create hex objects with resource types and numbers
            self._create_hexes(land_hex_keys, ocean_hex_keys)

        # Step 2b: land is what was dealt, not what the layout set aside for it.
        # The two are the same set for every built-in layout, which is why this
        # never mattered before; a pool that can deal sea into a land slot is
        # what makes them differ, and every other rule on the board already
        # reads the terrain rather than this list.
        land_hex_keys = {key for key in land_hex_keys if self.hexes[key].type != 'ocean'}
        ocean_hex_keys = set(self.hexes) - land_hex_keys

        # Step 3: Generate the graph. Without ships the ocean ring is scenery
        # and only the land carries intersections and hex sides. Ships need
        # somewhere to be built — Seafarers ships or E&P transport ships alike,
        # so either rule grows the sea — so with the rule on the sea is generated too —
        # which is a bigger graph, not a different one: `is_coastal_edge` picks
        # the coastline out by counting *land* neighbours rather than by
        # counting neighbours, so the harbours land in the same places either
        # way, and `vertices` still list land hexes only, which is what keeps a
        # settlement off the open water.
        needs_sea = self.rules['ships'] or self.rules['transport_ships']
        graph_hex_keys = land_hex_keys | ocean_hex_keys if needs_sea else land_hex_keys
        self._generate_vertices_and_edges(graph_hex_keys)

        # Step 4: Build all neighbor relationships
        self._build_neighbor_relationships(land_hex_keys, graph_hex_keys)

        # Step 4b: separate the red numbers, if the table asked for it. It runs
        # here rather than in _create_hexes because it needs to know which hexes
        # touch which, and that is what the previous step just worked out.
        if self.rules['no_adjacent_red_numbers']:
            self._separate_red_numbers()

        # Step 5: Hang the harbours off the coast
        self._assign_ports()

        logger.debug("\n=== Board Generated ===")
        logger.debug(f"Total hexes: {len(self.hexes)}")
        logger.debug(f"Total vertices: {len(self.vertices)}")
        logger.debug(f"Total edges: {len(self.edges)}")

        # Count hex types for debugging
        hex_types = {}
        for hex_obj in self.hexes.values():
            hex_types[hex_obj.type] = hex_types.get(hex_obj.type, 0) + 1
        logger.debug(f"Hex distribution: {hex_types}")
        logger.debug("=======================\n")

    def _apply_map_instance(self, instance) -> tuple:
        """Lay a dealt map onto the board, and say which of it is land.

        The map file's `sea` becomes the engine's `ocean` here and nowhere
        else. `board_layout` is filled in with the harbour bag the map carries
        so `_assign_ports` needs no branch of its own — it asks a layout for its
        harbours, and a map is a layout that came from a file.
        """
        self.board_layout = {
            'hexes': (), 'resources': (), 'numbers': (),
            'ports': instance.harbours, 'island': None, 'fixed': False,
        }

        meta = instance.meta or {}
        for hex_key in maps.sort_hex_keys(instance.placed):
            terrain, number = instance.placed[hex_key]
            hex_obj = Hex(hex_key, 'ocean' if terrain == 'sea' else terrain, number)
            # A hidden tile keeps its real terrain here — the board holds the
            # truth and `get_board_data` is what redacts it — but is flagged so
            # the renderer draws its back and discovery can reveal it later.
            hex_obj.hidden = hex_key in instance.hidden
            if hex_key in meta:
                hex_obj.meta = meta[hex_key]
            self.hexes[hex_key] = hex_obj

        self.robber_hex = instance.robber_hex
        # The one thing a region's `kind` decides: where a starting settlement
        # may go, when the table asked for that rule.
        self.main_hex_keys = self.map_definition.hexes_of_kind('main')

        land_hex_keys = {
            hex_key for hex_key, (terrain, _) in instance.placed.items() if terrain != 'sea'
        }
        return land_hex_keys, set(instance.placed) - land_hex_keys

    def is_main_land(self, hex_key: str) -> bool:
        """Whether this hex belongs to a region the map calls the main land.

        Every hex of a built-in layout is main land: there is one island and
        nothing to distinguish. That is what makes the "start on the main land"
        rule a no-op on the built-in boards rather than a rule that refuses
        every placement on them.
        """
        return self.main_hex_keys is None or hex_key in self.main_hex_keys

    def _create_hexes(self, land_hex_keys: set, ocean_hex_keys: set):
        """
        Create Hex objects, with the terrain and number tokens of the layout.

        A fixed layout is a printed map and is laid out tile by tile in the
        order the rulebook shows; otherwise the box is shuffled.

        Args:
            land_hex_keys: The island's hexes
            ocean_hex_keys: The sea around it, which carries no terrain
        """
        layout = self.board_layout

        if layout['island']:
            placed = list(layout['island'])
        else:
            resource_types = list(layout['resources'])
            number_tokens = list(layout['numbers'])
            self.rng.shuffle(resource_types)
            self.rng.shuffle(number_tokens)
            # Only a resource hex takes a token. Exempting the desert alone let
            # a sea tile in a land pool pop a token out of the box and carry a
            # number on open water, where the renderer would draw it and
            # production would pay nobody.
            placed = [
                (hex_type, number_tokens.pop() if maps.takes_a_token(hex_type) else None)
                for hex_type in resource_types
            ]

        # The counts are what the box holds, and a mismatch is a silent, varying
        # board rather than a crash: a resource list one entry too long used to
        # drop a different tile's terrain on every run.
        assert len(placed) == len(land_hex_keys), (
            f"{len(placed)} tiles for {len(land_hex_keys)} land hexes"
        )
        assert sorted(hex_type for hex_type, _ in placed) == sorted(layout['resources']), (
            "terrain must match the layout's distribution"
        )
        assert sorted(n for _, n in placed if n is not None) == sorted(layout['numbers']), (
            "one token per numbered land hex; the desert takes none"
        )

        terrain = dict(
            zip(
                (self._hex_key(*coords) for coords in layout['hexes']),
                placed,
                strict=True,
            )
        )

        # Sorted, not raw set order: iterating a set of strings gives an order
        # that varies between processes, so the robber would start on a
        # different desert from run to run.
        for key in sorted(land_hex_keys | ocean_hex_keys):
            hex_type, number = terrain.get(key, ("ocean", None))
            self.hexes[key] = Hex(key, hex_type, number)

            # Place robber on the first desert tile
            if hex_type == "desert" and self.robber_hex is None:
                self.robber_hex = key

    def _separate_red_numbers(self):
        """Swap number tokens until no two red numbers touch.

        The rulebook's own remedy for a fully random token layout: a 6 or an 8
        that landed next to another one is exchanged with a hex holding a
        milder number, keeping the pool of tokens exactly as the box has it.
        The hex it moves to is picked with the game's own generator, so a seed
        still replays the same board.
        """
        numbered = sorted(key for key, hex_obj in self.hexes.items() if hex_obj.number is not None)

        def is_red(key: str) -> bool:
            return self.hexes[key].number in RED_NUMBERS

        for _ in range(MAX_RED_SEPARATION_PASSES):
            crowded = [
                key for key in numbered
                if is_red(key) and any(is_red(n) for n in self.hexes[key].neighbors)
            ]
            if not crowded:
                return

            moving = crowded[0]
            candidates = [key for key in numbered if not is_red(key)]
            self.rng.shuffle(candidates)
            for candidate in candidates:
                # `moving` is about to become mild, so it does not count against
                # the hex the red number is heading for.
                if any(n != moving and is_red(n) for n in self.hexes[candidate].neighbors):
                    continue
                self.hexes[moving].number, self.hexes[candidate].number = (
                    self.hexes[candidate].number, self.hexes[moving].number
                )
                break
            else:
                # Nowhere left to put it: the island is too small or too tightly
                # packed for the constraint. Say so rather than loop, and leave
                # the board playable.
                logger.warning(
                    "no free hex to move the red number off %s; leaving it adjacent", moving
                )
                return

        logger.warning("gave up separating red numbers after %d passes",
                       MAX_RED_SEPARATION_PASSES)

    def _generate_vertices_and_edges(self, hex_keys: set):
        """
        Generate all vertices and edges from hex coordinates.

        For each hex, we calculate its 6 vertices and 6 edges using
        the direction vectors from hex.md.

        Args:
            hex_keys: The hexes the graph is drawn from — the island alone in
                the base game, the island and the sea around it once ships are
                in play. A sea intersection is generated so a shipping route
                out in open water has corners to turn on; nothing may be built
                on one, because a vertex only ever lists *land* hexes as its
                neighbours and every building rule reads that list.
        """
        vertex_keys = set()
        edge_keys = set()

        # Sorted for the same reason _create_hexes sorts: iterating a set of
        # strings gives an order that varies between processes, so the same
        # seed would otherwise produce different vertex ordering and different
        # port placement on every run.
        for hex_key in sorted(hex_keys):
            hx, hy, hz = self._parse_key(hex_key)

            # Generate 6 vertices for this hex
            for vx, vy, vz in self.VERTEX_DIRECTIONS:
                vertex_key = self._hex_key(hx + vx, hy + vy, hz + vz)
                vertex_keys.add(vertex_key)

            # Generate 6 edges for this hex. Canonicalised, so the side this
            # hex shares with its neighbour is the same Edge for both of them.
            for ex, ey, ez in self.EDGE_DIRECTIONS:
                edge_key = self._edge_key(hx + ex, hy + ey, hz + ez)
                edge_keys.add(edge_key)

        # Create Vertex objects
        for key in sorted(vertex_keys):
            self.vertices[key] = Vertex(key)

        # Create Edge objects
        for key in sorted(edge_keys):
            self.edges[key] = Edge(key)

    def _build_neighbor_relationships(self, land_hex_keys: set, graph_hex_keys: set):
        """
        Build all neighbor relationships between hexes, vertices, and edges.

        Uses algebraic rules from hex.md to derive neighbors without lookup tables.

        Args:
            land_hex_keys: The land hexes. A vertex lists these and nothing
                else, because a building belongs to the land: production, the
                distance rule, the robber's victims and settlement legality all
                read `vertex.neighbors['hexes']`.
            graph_hex_keys: The hexes the sides were generated from. An edge
                lists whichever of these it separates, sea included, because a
                ship needs to know it is on water and the pirate needs to know
                which sides border its hex.
        """
        # Build hex -> hex neighbors
        for hex_key, hex_obj in self.hexes.items():
            hx, hy, hz = self._parse_key(hex_key)

            for dx, dy, dz in self.HEX_DIRECTIONS:
                neighbor_key = self._hex_key(hx + dx, hy + dy, hz + dz)
                if neighbor_key in self.hexes:
                    hex_obj.neighbors.append(neighbor_key)

        # Build hex -> vertices: the land only, so an intersection out in the
        # sea touches nothing and no building rule will have it.
        for hex_key in sorted(land_hex_keys):
            hx, hy, hz = self._parse_key(hex_key)

            for vx, vy, vz in self.VERTEX_DIRECTIONS:
                vertex_key = self._hex_key(hx + vx, hy + vy, hz + vz)
                if vertex_key in self.vertices:
                    self.vertices[vertex_key].neighbors["hexes"].append(hex_key)

        # Build hex -> edges over everything the graph was drawn from. A side
        # collects each of the two hexes it separates that the graph holds, so
        # a coastal side knows both its land and its water.
        for hex_key in sorted(graph_hex_keys):
            hx, hy, hz = self._parse_key(hex_key)

            for ex, ey, ez in self.EDGE_DIRECTIONS:
                edge_key = self._edge_key(hx + ex, hy + ey, hz + ez)
                if edge_key in self.edges:
                    self.edges[edge_key].neighbors["hexes"].append(hex_key)

        # Build edge -> vertices neighbors using brute force
        # For each edge, find the 2 vertices by checking which vertices are at either end
        # An edge at (ex,ey,ez) has vertices at (ex±1, ey∓1, ez) etc.
        for edge_key, edge_obj in self.edges.items():
            ex, ey, ez = self._parse_key(edge_key)

            # The 6 edge directions tell us how to move from edge to vertex
            # Try each direction: edge +/- direction gives a vertex coordinate
            candidates = []
            for dx, dy, dz in self.EDGE_DIRECTIONS:
                # Positive direction
                v1 = (ex + dx, ey + dy, ez + dz)
                v2 = (ex - dx, ey - dy, ez - dz)
                candidates.extend([v1, v2])

            for cx, cy, cz in candidates:
                if cx + cy + cz != 0:
                    continue
                # Check if this is a valid vertex (none divisible by 3)
                if cx % 3 == 0 or cy % 3 == 0 or cz % 3 == 0:
                    continue
                vertex_key = self._hex_key(cx, cy, cz)
                if vertex_key in self.vertices:
                    if vertex_key not in edge_obj.neighbors["vertices"]:
                        edge_obj.neighbors["vertices"].append(vertex_key)

        # Build vertex -> edges neighbors (vertices connect to 3 edges each)
        for vertex_key, vertex_obj in self.vertices.items():
            vx, vy, vz = self._parse_key(vertex_key)

            # A vertex connects to edges that have the vertex at one end
            # Try each edge direction from the vertex
            candidates = []
            for dx, dy, dz in self.EDGE_DIRECTIONS:
                # Edge = vertex +/- direction
                e1 = (vx + dx, vy + dy, vz + dz)
                e2 = (vx - dx, vy - dy, vz - dz)
                candidates.extend([e1, e2])

            for cx, cy, cz in candidates:
                if cx + cy + cz != 0:
                    continue
                # Check if this is a valid edge (exactly one divisible by 3)
                div_count = sum(1 for c in (cx, cy, cz) if c % 3 == 0)
                if div_count != 1:
                    continue
                # Both names of a side turn up among the candidates, and both
                # canonicalise to the one key the board holds.
                edge_key = self._edge_key(cx, cy, cz)
                if edge_key in self.edges:
                    if edge_key not in vertex_obj.neighbors["edges"]:
                        vertex_obj.neighbors["edges"].append(edge_key)

        # Build edge -> edges neighbors (edges sharing a vertex)
        for edge_key, edge_obj in self.edges.items():
            for vertex_key in edge_obj.neighbors["vertices"]:
                vertex_obj = self.vertices[vertex_key]
                for neighbor_edge_key in vertex_obj.neighbors["edges"]:
                    if (
                        neighbor_edge_key != edge_key
                        and neighbor_edge_key not in edge_obj.neighbors["edges"]
                    ):
                        edge_obj.neighbors["edges"].append(neighbor_edge_key)

        # Build vertex -> vertices neighbors (vertices connected by an edge)
        for vertex_key, vertex_obj in self.vertices.items():
            for edge_key in vertex_obj.neighbors["edges"]:
                edge_obj = self.edges[edge_key]
                for connected_vertex_key in edge_obj.neighbors["vertices"]:
                    if (
                        connected_vertex_key != vertex_key
                        and connected_vertex_key not in vertex_obj.neighbors["vertices"]
                    ):
                        vertex_obj.neighbors["vertices"].append(connected_vertex_key)

    def islands(self) -> dict:
        """Land hex key -> the id of the island it belongs to.

        An island is derived, never authored: a stretch of land the sea cuts
        off from the rest of the board, found by flood fill over neighbouring
        land hexes. A map file can group hexes into regions for its own
        purposes, but which of them a player has landed on has to come from the
        board as it was actually dealt — a region whose pool dealt it some sea
        may end up as two islands, or none.

        The id is the lowest hex key in the component, so it is stable for a
        board however the hexes were iterated.
        """
        land = sorted(key for key, hex_obj in self.hexes.items() if hex_obj.type != 'ocean')
        island_of = {}
        for start in land:
            if start in island_of:
                continue
            component = []
            frontier = [start]
            seen = {start}
            while frontier:
                key = frontier.pop()
                component.append(key)
                for neighbor_key in sorted(self.hexes[key].neighbors):
                    if neighbor_key in seen or self.hexes[neighbor_key].type == 'ocean':
                        continue
                    seen.add(neighbor_key)
                    frontier.append(neighbor_key)
            island_id = min(component)
            for key in component:
                island_of[key] = island_id
        return island_of

    def land_hexes_of_edge(self, edge_key: str) -> list:
        """The land hexes this side separates — none, one or two of them."""
        edge = self.edges.get(edge_key)
        if edge is None:
            return []
        return [
            hex_key
            for hex_key in edge.neighbors["hexes"]
            if self.hexes[hex_key].type != 'ocean'
        ]

    def is_coastal_edge(self, edge_key: str) -> bool:
        """Whether this side has land on one hand and open sea on the other.

        Counting *land* neighbours rather than neighbours is what lets the same
        signature hold whether or not the sea was generated: with ships off a
        coastal side is the only kind with a single hex at all, and with ships
        on it has two hexes of which exactly one is land. An inland side has
        two land hexes, and a side out at sea has none.
        """
        return len(self.land_hexes_of_edge(edge_key)) == 1

    def _coastline_rings(self) -> list:
        """Every coastline on this board, walked in order, longest first.

        A board can have more than one. The walk used to follow a single ring
        from the lowest coastal edge and hand it back even when it had reached
        a fraction of the coast — 18 edges of 54 on a board with an island in a
        lagoon, none of them the island's — so every harbour crowded onto
        whichever coast the walk happened to find. Repeating the walk from the
        lowest edge nobody has claimed yet is all it takes.

        The first ring is walked exactly as it always was, which is what keeps
        the harbours of a one-coast board where they have always been.
        """
        coastal = [
            edge_key for edge_key in sorted(self.edges) if self.is_coastal_edge(edge_key)
        ]

        if not coastal:
            return []

        edges_at_vertex = {}
        for edge_key in coastal:
            for vertex_key in self.edges[edge_key].neighbors["vertices"]:
                edges_at_vertex.setdefault(vertex_key, []).append(edge_key)

        # Walk from one coastal edge to the next through the intersection they
        # share. Sorted starting point and sorted candidates, for the same
        # reason the rest of generation sorts: set order varies between
        # processes, and the harbours would land somewhere else every run.
        rings = []
        visited = set()
        for start in coastal:
            if start in visited:
                continue
            ring = [start]
            visited.add(start)
            behind = min(self.edges[start].neighbors["vertices"])
            while True:
                ahead = next(
                    vertex_key
                    for vertex_key in self.edges[ring[-1]].neighbors["vertices"]
                    if vertex_key != behind
                )
                unvisited = sorted(
                    edge_key for edge_key in edges_at_vertex[ahead] if edge_key not in visited
                )
                if not unvisited:
                    break
                ring.append(unvisited[0])
                visited.add(unvisited[0])
                behind = ahead
            rings.append(ring)

        # Longest first, so the coast with room for the most harbours is served
        # first and the leftovers land on the biggest island. Tie broken by the
        # lowest edge key, never by walk order.
        rings.sort(key=lambda ring: (-len(ring), ring[0]))
        return rings

    def _harbours_per_ring(self, rings: list, count: int) -> list:
        """How many harbours each coastline gets, in proportion to its length.

        Capped at half a coast's length, because harbours never share an
        intersection and the spacing below needs an edge between each pair. A
        board with more harbours in the box than its coasts can hold keeps the
        existing behaviour: say so and place as many as fit.
        """
        capacity = [len(ring) // 2 for ring in rings]
        coast = sum(len(ring) for ring in rings)
        count = min(count, sum(capacity))

        share = [
            min(cap, count * len(ring) // coast)
            for cap, ring in zip(capacity, rings, strict=True)
        ]
        # Whatever rounding left over goes to the longest coast that still has
        # room; `rings` is already longest first.
        for index, cap in enumerate(capacity):
            while sum(share) < count and share[index] < cap:
                share[index] += 1
        return share

    def _assign_ports(self):
        """Hang the harbours off coastal edges, spaced around the island.

        A harbour belongs to a hex *side*, not a point: the rulebook draws each
        one on the sea frame with two lines reaching the two intersections at
        the ends of one coastal side, and a settlement on either of them
        controls it. This used to pick nine single vertices by angle around the
        centre, so a harbour served one intersection instead of two and did not
        sit on a coastal side at all.

        `edge.port` is the geometry; `vertex.port` is kept populated on both
        ends because the trade rules, the save file and the renderer all read
        it there.

        For a fixed layout the harbours are fixed too, but note the caveat:
        the harbour *types* in Illustration A are unreadable at the resolution
        of the published rulebook scan, so which harbour sits where on the
        beginner map is ours. Their number and 4/5 split are the rulebook's.
        """
        # A map may declare no harbours at all — E&P has none — and then there
        # is nothing to place and no coastline worth walking for it.
        if not self.board_layout['ports']:
            return
        rings = self._coastline_rings()
        coast = sum(len(ring) for ring in rings)
        port_types = list(self.board_layout['ports'])
        share = self._harbours_per_ring(rings, len(port_types)) if rings else []
        if sum(share) < len(port_types):
            logger.warning(
                f"coastline of {coast} edges is too short for "
                f"{len(port_types)} harbours that do not touch"
            )
            port_types = port_types[: sum(share)]
        if not port_types:
            return

        # A printed map has its harbours printed too, so a fixed layout keeps
        # the order below and starts at the same place on the coast every game.
        if not self.board_layout['fixed']:
            self.rng.shuffle(port_types)

        placed = 0
        for ring, count in zip(rings, share, strict=True):
            if not count:
                continue
            # Where the run of harbours starts is the only thing chance decides
            # about their placement; the spacing below is fixed. One draw per
            # coastline, so a board with a single coast — every built-in layout
            # — makes exactly the calls it always made.
            rotation = 0 if self.board_layout['fixed'] else self.rng.randrange(len(ring))

            for index, port_type in enumerate(port_types[placed:placed + count]):
                # Evenly spaced around the ring, because real harbours never
                # share an intersection: at this spacing consecutive harbours
                # always leave at least one coastal edge between them.
                position = (rotation + round(index * len(ring) / count)) % len(ring)
                edge_obj = self.edges[ring[position]]

                if port_type == "generic":
                    port = {"type": "generic"}
                else:
                    port = {"type": "resource", "resource": port_type}

                edge_obj.port = port
                for vertex_key in edge_obj.neighbors["vertices"]:
                    # A copy per vertex: one shared dict would let a mutation of
                    # a single intersection silently change the whole harbour.
                    self.vertices[vertex_key].port = dict(port)
            placed += count

        logger.debug(
            f"Harbours assigned: {sum(1 for t in port_types if t == 'generic')} generic (3:1), "
            f"{sum(1 for t in port_types if t != 'generic')} resource (2:1) "
            f"on {coast} coastal edges over {len(rings)} coastlines"
        )
