"""Board geometry and generation.

Split out of `game.py` so the rules engine is readable on its own: this is the
cube-coordinate maths from hex.md plus the one-time layout of hexes, vertices,
edges and ports. It is a mixin rather than free functions because every method
here reads the board configuration off the Game (`hex_radius`, `rng`, and the
dicts it fills in), and threading all of that through parameters would obscure
the geometry, which is the hard part.
"""

import logging

from game.hex_models import Edge, Hex, Vertex

logger = logging.getLogger(__name__)


class BoardBuilder:
    """Everything that turns a radius into a populated board."""

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

    def _is_valid_hex(self, x: int, y: int, z: int) -> bool:
        """
        Check if coordinates represent a valid hex within the board.

        A hex is valid if:
        1. x + y + z = 0 (cube coordinate invariant)
        2. All coordinates are divisible by 3 (hex classification rule)
        3. The hex is within the land radius

        Args:
            x, y, z: Cube coordinates

        Returns:
            True if valid land hex, False otherwise
        """
        # Check cube coordinate invariant
        if x + y + z != 0:
            return False

        # Check hex classification (all divisible by 3)
        if x % 3 != 0 or y % 3 != 0 or z % 3 != 0:
            return False

        # Check if within land radius (using max coordinate as distance metric)
        max_coord = max(abs(x // 3), abs(y // 3), abs(z // 3))
        return max_coord <= self.hex_radius

    def _is_ocean(self, x: int, y: int, z: int) -> bool:
        """
        Check if coordinates represent an ocean (edge) tile.

        Ocean tiles are within edge_radius but outside hex_radius.

        Args:
            x, y, z: Cube coordinates

        Returns:
            True if ocean tile, False otherwise
        """
        if x + y + z != 0:
            return False

        # Must have exactly one coordinate divisible by 3 (edge classification)
        coords_divisible = sum(1 for c in (x, y, z) if c % 3 == 0)
        if coords_divisible != 1:
            return False

        # Check if within edge radius but outside land
        max_coord = max(abs(x), abs(y), abs(z))
        return max_coord <= self.edge_radius * 3 and not self._is_valid_hex(x, y, z)

    def _generate_board(self):
        """
        Generate the complete Catan board.

        This method:
        1. Creates all hexes within hex_radius (land) and edge_radius (ocean)
        2. Generates all vertices and edges for each hex
        3. Builds neighbor relationships algebraically
        4. Assigns resource types and numbers randomly
        """
        # Step 1: Generate all hex keys
        all_hex_keys = set()

        # Generate all possible coordinates within edge_radius
        # We iterate through a cube and filter based on our rules
        r = self.edge_radius * 3
        for x in range(-r, r + 1, 3):
            for y in range(-r, r + 1, 3):
                z = -x - y
                if -r <= z <= r:
                    if self._is_valid_hex(x, y, z):
                        all_hex_keys.add(self._hex_key(x, y, z))
                    elif self._is_ocean(x, y, z):
                        all_hex_keys.add(self._hex_key(x, y, z))

        # Step 2: Create hex objects with resource types and numbers
        self._create_hexes(all_hex_keys)

        # Step 3: Generate vertices and edges from hexes
        self._generate_vertices_and_edges(all_hex_keys)

        # Step 4: Build all neighbor relationships
        self._build_neighbor_relationships()

        # Step 5: Assign ports to edge vertices
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

    def _create_hexes(self, hex_keys: set):
        """
        Create Hex objects with random resource types and numbers.

        Standard Catan distribution (19 hexes):
        - 4 Wood, 4 Wheat, 4 Sheep, 3 Brick, 3 Ore, 1 Desert

        Args:
            hex_keys: Set of all hex coordinate keys
        """
        # Define resource types and their counts (standard Catan).
        # These must total exactly 19 — the number of land hexes. A list of 20
        # meant one tile's resource was silently dropped, and which one varied
        # per run, so no two boards had the same resource mix.
        resource_types = (
            ["wood"] * 4
            + ["wheat"] * 4
            + ["sheep"] * 4
            + ["brick"] * 3
            + ["ore"] * 3
            + ["desert"] * 1
        )
        assert len(resource_types) == 19, "resource distribution must match the 19 land hexes"

        # Shuffle for random placement
        self.rng.shuffle(resource_types)

        # Number tokens (2-12, excluding 7)
        # Each number appears with frequency based on real dice probability:
        # 2,12: 1 each, 3,11: 2 each, 4,10: 3 each, 5,9: 4 each, 6,8: 5 each
        number_tokens = [2, 12] * 1 + [3, 11] * 2 + [4, 10] * 3 + [5, 9] * 4 + [6, 8] * 5
        self.rng.shuffle(number_tokens)
        number_tokens_stack = list(number_tokens)  # Copy for popping

        # Sorted, not raw set order: iterating a set of strings gives an order
        # that varies between processes, so the same seed would otherwise still
        # produce a different board each run.
        for key in sorted(hex_keys):
            x, y, z = self._parse_key(key)

            # Determine if ocean or land
            if self._is_ocean(x, y, z):
                hex_type = "ocean"
                number = None
            else:
                # Assign resource type
                hex_type = resource_types.pop() if resource_types else "wheat"

                # Desert gets no number
                if hex_type == "desert":
                    number = None
                else:
                    number = number_tokens_stack.pop() if number_tokens_stack else None

            hex_obj = Hex(key, hex_type, number)
            self.hexes[key] = hex_obj

            # Place robber on desert tile
            if hex_type == "desert" and self.robber_hex is None:
                self.robber_hex = key

    def _generate_vertices_and_edges(self, hex_keys: set):
        """
        Generate all vertices and edges from hex coordinates.

        For each hex, we calculate its 6 vertices and 6 edges using
        the direction vectors from hex.md.

        Args:
            hex_keys: Set of all hex coordinate keys
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

            # Generate 6 edges for this hex
            for ex, ey, ez in self.EDGE_DIRECTIONS:
                edge_key = self._hex_key(hx + ex, hy + ey, hz + ez)
                edge_keys.add(edge_key)

        # Create Vertex objects
        for key in sorted(vertex_keys):
            self.vertices[key] = Vertex(key)

        # Create Edge objects
        for key in sorted(edge_keys):
            self.edges[key] = Edge(key)

    def _build_neighbor_relationships(self):
        """
        Build all neighbor relationships between hexes, vertices, and edges.

        Uses algebraic rules from hex.md to derive neighbors without lookup tables.
        """
        # Build hex -> hex neighbors
        for hex_key, hex_obj in self.hexes.items():
            hx, hy, hz = self._parse_key(hex_key)

            for dx, dy, dz in self.HEX_DIRECTIONS:
                neighbor_key = self._hex_key(hx + dx, hy + dy, hz + dz)
                if neighbor_key in self.hexes:
                    hex_obj.neighbors.append(neighbor_key)

        # Build hex -> vertices and hex -> edges neighbors
        for hex_key in self.hexes:
            hx, hy, hz = self._parse_key(hex_key)

            # Vertices
            for vx, vy, vz in self.VERTEX_DIRECTIONS:
                vertex_key = self._hex_key(hx + vx, hy + vy, hz + vz)
                if vertex_key in self.vertices:
                    self.vertices[vertex_key].neighbors["hexes"].append(hex_key)

            # Edges
            for ex, ey, ez in self.EDGE_DIRECTIONS:
                edge_key = self._hex_key(hx + ex, hy + ey, hz + ez)
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
                edge_key = self._hex_key(cx, cy, cz)
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

    def _assign_ports(self):
        """Assign ports to 9 vertices on the edge of the map (evenly distributed)."""

        # Find all edge vertices - vertices that don't have 3 adjacent hexes
        edge_vertices = []
        for vertex_key, vertex_obj in self.vertices.items():
            hex_neighbors = vertex_obj.neighbors.get("hexes", [])
            if len(hex_neighbors) < 3:
                edge_vertices.append(vertex_key)

        edge_vertices = list(set(edge_vertices))

        if len(edge_vertices) < 9:
            logger.debug(f"Warning: Only {len(edge_vertices)} edge vertices found")
            port_vertices = edge_vertices[:9] if edge_vertices else []
        else:
            # Sort edge vertices by angle to distribute evenly around the board
            def get_vertex_angle(vertex_key):
                """Get approximate angle for sorting vertices."""
                coords = self._parse_key(vertex_key)
                x, y, z = coords
                # Use atan2 to get angle from center
                # Project 3D coord to 2D
                px = x + 0.5 * z
                py = 0.866 * z  # sqrt(3)/2
                import math

                return math.atan2(py, px)

            # Sort by angle
            edge_vertices.sort(key=get_vertex_angle)

            # Select 9 evenly spaced vertices
            step = len(edge_vertices) / 9
            port_vertices = [edge_vertices[int(i * step)] for i in range(9)]

        self.rng.shuffle(port_vertices)

        # Port types: 4 generic (3:1), 5 resource-specific (2:1)
        port_types = ["generic"] * 4 + ["wood", "brick", "sheep", "wheat", "ore"]
        self.rng.shuffle(port_types)

        # Assign ports to vertices
        for i, vertex_key in enumerate(port_vertices):
            if vertex_key in self.vertices:
                vertex_obj = self.vertices[vertex_key]
                resource_type = port_types[i]

                if resource_type == "generic":
                    vertex_obj.port = {"type": "generic"}
                else:
                    vertex_obj.port = {"type": "resource", "resource": resource_type}

        # Count ports for debug
        generic_count = sum(
            1 for v in self.vertices.values() if v.port and v.port.get("type") == "generic"
        )
        resource_count = sum(
            1 for v in self.vertices.values() if v.port and v.port.get("type") == "resource"
        )
        logger.debug(
            f"Ports assigned: {generic_count} generic (3:1), {resource_count} resource (2:1)"
        )
