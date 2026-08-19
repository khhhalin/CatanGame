"""Catan for Two: the two non-producing neutral colours.

Source [OFFICIAL]: Traders & Barbarians 2020 rulebook, "Catan for Two", pp. 6-7
(catan-t_b_2020_rule_book_200820.pdf).

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. A neutral colour is not a seat: it is deliberately kept out of
`self.players`, which is what makes it invisible to production and turn order
without a single branch on its identity. `distribute_resources` already skips a
vertex whose owner `get_player` cannot find (game.py), and `force_advance_turn`
only ever indexes `self.players` — so a colour that is not in that list produces
nothing and never takes a turn, for free. Its pieces still sit on the board's
vertices and edges the same way a real player's do, so the distance rule and the
`OCCUPIED` checks block real building against them with no extra code.
"""

from game.player import Player

# The two "sets of game pieces not chosen by the players". Any two distinct
# colours will do; these read as neutral against the six seat colours and each
# other. Kept off `Game.PLAYER_COLORS` so a real seat never draws one.
NEUTRAL_NAMES = ["Neutral 1", "Neutral 2"]
NEUTRAL_COLORS = ["#95a5a6", "#34495e"]

# A neutral colour draws from the same physical supply a seat does.
NEUTRAL_MAX_SETTLEMENTS = 5
NEUTRAL_MAX_ROADS = 15


class NeutralPlayersRules:
    """The two imaginary neutral players and how they expand to block space."""

    def setup_neutral_players(self):
        """Seat the two neutral colours and place each one's opening settlement.

        Off unless `rules['neutral_players']`, in which case `self.neutral_players`
        stays the empty list `__init__` gave it and every method below is a no-op.
        """
        self.neutral_players = []
        if not self.rules["neutral_players"]:
            return
        for name, color in zip(NEUTRAL_NAMES, NEUTRAL_COLORS, strict=True):
            self.neutral_players.append(Player(name, color))
        self._place_neutral_opening_settlements()

    def is_neutral(self, name: str) -> bool:
        """Whether this colour is one of the neutral, non-producing players."""
        return any(neutral.name == name for neutral in self.neutral_players)

    def _place_neutral_opening_settlements(self):
        """One settlement per neutral, on a central intersection, no road.

        The rulebook marks the two opening intersections in an illustration the
        PDF cannot yield as coordinates. The defensible reading places each on an
        interior (three-land-hex) intersection — the central band the marks sit
        in — chosen deterministically off the sorted vertex keys and honouring
        the distance rule, so the pair occupies and blocks space exactly as the
        printed marks would. Reproducible under a seeded board.
        """
        interior = [
            key
            for key in sorted(self.vertices)
            if len(self.vertices[key].neighbors["hexes"]) == 3
        ]
        for neutral in self.neutral_players:
            spot = next(
                (
                    key
                    for key in interior
                    if self.vertices[key].building is None
                    and self._respects_distance_rule(key)
                ),
                None,
            )
            if spot is not None:
                self._seat_neutral_settlement(neutral, spot)

    def _seat_neutral_settlement(self, neutral: Player, vertex_key: str) -> dict:
        """Plant a neutral settlement on the board and record it on the colour."""
        self.vertices[vertex_key].building = {
            "type": "settlement",
            "player": neutral.name,
        }
        neutral.settlements.append(vertex_key)
        return {"neutral": neutral.name, "piece": "settlement", "key": vertex_key}

    def expand_neutral_players(self, builder_name: str):
        """Build one free neutral piece in answer to a real player's build.

        Rulebook "Building Progress of the Neutral Players": "When you build a
        road or a settlement, you must also build (for free) 1 road or 1
        settlement for either of the two neutral players. If there is no legal
        settlement location for the neutral players, you must build a road
        instead." A settlement is preferred where one can legally go, otherwise a
        road. Which neutral gets the piece is the builder's choice in the book;
        the defensible automatic reading gives it to the neutral with the fewest
        pieces (ties by name), so the two grow at an even, reproducible pace.
        Returns the placement, or None if neither neutral can legally add a piece.
        """
        if not self.rules["neutral_players"] or not self.neutral_players:
            return None
        order = sorted(
            self.neutral_players,
            key=lambda neutral: (len(neutral.settlements) + len(neutral.roads), neutral.name),
        )
        for neutral in order:
            placed = self._neutral_build_settlement(neutral)
            if placed is None:
                placed = self._neutral_build_road(neutral)
            if placed is not None:
                return placed
        return None

    def _neutral_reach_vertices(self, neutral: Player) -> set:
        """The intersections the neutral's own roads reach."""
        reach = set()
        for edge_key in neutral.roads:
            edge = self.edges.get(edge_key)
            if edge is not None:
                reach.update(edge.neighbors.get("vertices", []))
        return reach

    def _neutral_build_settlement(self, neutral: Player):
        """Plant a neutral settlement where one may legally go, else None.

        Legal here means connected to the neutral's own road network (the normal
        connectivity rule), standing on land, on an empty vertex, and honouring
        the distance rule. The first such vertex in key order, for a reproducible
        board.
        """
        if len(neutral.settlements) >= NEUTRAL_MAX_SETTLEMENTS:
            return None
        for vertex_key in sorted(self._neutral_reach_vertices(neutral)):
            vertex = self.vertices.get(vertex_key)
            if vertex is None or vertex.building is not None:
                continue
            if not vertex.neighbors.get("hexes"):
                continue
            if not self._respects_distance_rule(vertex_key):
                continue
            return self._seat_neutral_settlement(neutral, vertex_key)
        return None

    def _neutral_build_road(self, neutral: Player):
        """Extend the neutral's network by one road, else None.

        A neutral road runs from one of the neutral's settlements or the ends of
        its existing roads, onto an empty land side. The first such side in key
        order, for a reproducible board.
        """
        if len(neutral.roads) >= NEUTRAL_MAX_ROADS:
            return None
        frontier = set(neutral.settlements) | self._neutral_reach_vertices(neutral)
        candidates = []
        for vertex_key in frontier:
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            for edge_key in vertex.neighbors.get("edges", []):
                edge = self.edges.get(edge_key)
                if edge is None or edge.road is not None or edge.ship is not None:
                    continue
                if not self.land_hexes_of_edge(edge_key):
                    continue
                candidates.append(edge_key)
        if not candidates:
            return None
        edge_key = sorted(candidates)[0]
        self.edges[edge_key].road = {"player": neutral.name}
        neutral.roads.append(edge_key)
        return {"neutral": neutral.name, "piece": "road", "key": edge_key}

    def neutral_board_state(self) -> list:
        """The neutral colours and their pieces, for the client renderer.

        Empty off the rule. Carries the colour so the board can draw a neutral
        piece even though the colour is not a seat in the players list.
        """
        return [
            {
                "name": neutral.name,
                "color": neutral.color,
                "settlements": list(neutral.settlements),
                "roads": list(neutral.roads),
            }
            for neutral in self.neutral_players
        ]
