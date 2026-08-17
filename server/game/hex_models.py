"""
Hex models for Catan board representation.

This module defines the three core classes for representing a Catan board:
- Hex: A single tile on the board (resource, desert, or ocean)
- Vertex: A corner where 3 hexes meet (can have settlement/city)
- Edge: An edge between two hexes (can have road)

Uses a cube coordinate system as described in hex.md for unique keys
and algebraic neighbor relationships.
"""


class Hex:
    """
    Represents a single hex tile on the Catan board.

    Attributes:
        key (str): Unique identifier in "x,y,z" format from cube coordinates.
                   Example: "3,-3,0" for the center hex in a radius-1 board.
        type (str): Resource type - "ore", "wheat", "sheep", "brick", "wood",
                    "desert", or "ocean"; a v2 map may also deal the E&P terrains
                    "gold", "fish" and "spice".
        number (int or None): Dice number token (2-12) for resource hexes,
                              None for desert and ocean tiles.
        neighbors (list): List of adjacent hex keys.
        hidden (bool): An exploration tile dealt face-down by a v2 hidden pool.
                       Its type and number are real on the server but secret to
                       clients until discovery reveals it (a later wave), so
                       `get_board_data` redacts them per viewer.
        meta: The tile's `maps.HexMeta` (docks, village, lair) when a v2 map
              prints per-hex metadata, else None.
    """

    def __init__(self, key: str, hex_type: str, number: int | None):
        """
        Initialize a Hex object.

        Args:
            key: Unique coordinate key in "x,y,z" format
            hex_type: Resource type or special tile type
            number: Dice number (2-12) or None for desert/ocean
        """
        self.key = key
        self.type = hex_type
        self.number = number
        self.neighbors = []
        self.hidden = False
        self.meta = None


class Vertex:
    """
    Represents a corner where 3 hexes meet.

    Vertices are the positions where settlements and cities can be built.
    Each vertex touches exactly 3 hexes and has 3 adjacent edges.

    Attributes:
        key (str): Unique identifier in "x,y,z" cube coordinate format.
                   Note: Vertices have no coordinate divisible by 3.
        building (dict or None): Contains {"type": "settlement"/"city",
                                    "player": player_name} if occupied.
        port (dict or None): Contains port info if this vertex is a port:
            - "type": "generic" (3:1) or resource type (2:1)
            - "resource": for resource-specific ports: "wood", "brick", "sheep", "wheat", "ore"
        neighbors (dict): Dictionary with keys:
            - "hexes": List of 3 adjacent hex keys
            - "edges": List of 3 adjacent edge keys
            - "vertices": List of adjacent vertex keys
        kind (str): "standard" for a corner the %3 lattice predicts, or a tag
                    ("plaza", ...) for a non-standard intersection a map injects
                    with explicit neighbours — one the lattice cannot express,
                    such as a central-plaza vertex at a hex centre. Standard
                    vertices are produced only by the algebraic pass; a tagged
                    vertex carries a non-lattice key and is never fed to the %3
                    classifiers.
    """

    def __init__(self, key: str, kind: str = "standard"):
        """
        Initialize a Vertex object.

        Args:
            key: Unique coordinate key in "x,y,z" format
            kind: "standard" (lattice) or a tag for an injected piece
        """
        self.key = key
        self.kind = kind
        self.building = None  # {"type": "settlement"/"city", "player": name}
        self.port = None  # {"type": "generic"/resource, "resource": resource_type}
        self.neighbors = {
            "hexes": [],      # 3 adjacent hex keys
            "edges": [],      # 3 adjacent edge keys
            "vertices": []    # Adjacent vertex keys
        }


class Edge:
    """
    Represents an edge between two hexes.

    Edges are the positions where roads can be built.
    Each edge is shared by exactly 2 hexes and connects 2 vertices.

    Attributes:
        key (str): Unique identifier in "x,y,z" cube coordinate format.
                   Note: Edges have exactly one coordinate divisible by 3.
        road (dict or None): Contains {"player": player_name} if occupied.
        ship (dict or None): Seafarers. Contains {"player": player_name,
                             "built_turn": turn} if a ship lies on this side.
                             The turn is what stops a ship being moved on the
                             turn it was built. A side never holds both a road
                             and a ship.
        port (dict or None): The harbour on this coastal edge, if any. A
                             harbour belongs to a hex side and serves both of
                             the intersections at its ends, which carry a copy
                             of this in their own `port`.
        neighbors (dict): Dictionary with keys:
            - "hexes": List of 2 adjacent hex keys
            - "edges": List of adjacent edge keys
            - "vertices": List of 2 adjacent vertex keys
        kind (str): "standard" for a hex side the %3 lattice predicts, or a tag
                    ("spoke", ...) for a non-standard side a map injects with
                    explicit neighbours — one the lattice cannot express, such
                    as an interior spoke bordering a single hex from inside.
                    Standard edges are produced only by the algebraic pass; a
                    tagged edge carries a non-lattice key, has no lattice twin,
                    and is never fed to the %3 classifiers.
    """

    def __init__(self, key: str, kind: str = "standard"):
        """
        Initialize an Edge object.

        Args:
            key: Unique coordinate key in "x,y,z" format
            kind: "standard" (lattice) or a tag for an injected piece
        """
        self.key = key
        self.kind = kind
        self.road = None  # {"player": name}
        self.ship = None  # {"player": name, "built_turn": turn}
        self.port = None  # {"type": "generic"/"resource", "resource": type}
        self.neighbors = {
            "hexes": [],      # 2 adjacent hex keys
            "edges": [],      # Adjacent edge keys
            "vertices": []    # 2 adjacent vertex keys
        }
