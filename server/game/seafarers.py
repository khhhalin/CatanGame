"""Seafarers: ships, moving them, the pirate and the islands they reach.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. It stays a mixin because every method reads Game state — the board,
the hands, the turn counter and the per-turn flags.

The one thing worth knowing before reading: a ship is not a road on water. It
lives on the same Edge object a road would, under `edge.ship`, but the two
networks are deliberately kept apart. A road and a ship may never share a hex
side, they only chain into one trade route through an intersection where their
owner has a building, and each is built from its own network alone.
"""

import logging

from game import tiles
from game.results import refused

logger = logging.getLogger(__name__)


class SeafarersRules:
    """Ship placement and movement, the pirate, and the island bonus."""

    # --- Where a ship may lie ------------------------------------------

    def is_sea_edge(self, edge_key: str) -> bool:
        """Whether a ship could ever lie on this hex side.

        Two conditions from the rulebook, both geometric: at least one of the
        two hexes is sea, and there are two hexes at all — the outer sides of
        the frame have only the one, and "players may build ships on the inner
        edges of the frame pieces but never on the outer edges".
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return False
        return len(edge.neighbors['hexes']) == 2 and len(self.land_hexes_of_edge(edge_key)) <= 1

    def pirate_blocks_edge(self, edge_key: str) -> bool:
        """Whether the pirate is sitting on one of this side's two hexes."""
        if self.pirate_hex is None:
            return False
        edge = self.edges.get(edge_key)
        return edge is not None and self.pirate_hex in edge.neighbors['hexes']

    def ship_connects(self, player_name: str, edge_key: str, ignoring: str = None) -> bool:
        """Whether a ship here would touch that player's *shipping* network.

        Their own ships and their own coastal buildings, and nothing else: a
        road at the same intersection does not extend a shipping route, because
        "a player may only join a land network of roads to a sea network of
        ships by building a settlement at the intersection where the two
        networks meet" — and a settlement is exactly what this counts.

        `ignoring` is the side a ship is being moved off, which must not hold
        its own destination up.
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return False

        for vertex_key in edge.neighbors['vertices']:
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            if vertex.building and vertex.building.get('player') == player_name:
                return True
            for connected_key in vertex.neighbors['edges']:
                if connected_key in (edge_key, ignoring):
                    continue
                connected = self.edges.get(connected_key)
                if connected and connected.ship and connected.ship.get('player') == player_name:
                    return True
        return False

    def _ship_placement_refusal(
        self, player_name: str, edge_key: str, ignoring: str = None
    ) -> dict | None:
        """Why a ship may not go here, or None if it may.

        Shared by building and moving, because "the ship's new position must
        satisfy all of the normal rules for placing a new ship" — one function
        so the two can never drift apart.
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return refused('INVALID_TARGET', 'Invalid edge')
        if not self.is_sea_edge(edge_key):
            return refused('INVALID_PLACEMENT', 'A ship must lie on a hex side that touches sea')
        if edge.ship is not None:
            return refused('OCCUPIED', 'This location already has a ship')
        if edge.road is not None:
            return refused('OCCUPIED', 'This coastal side already carries a road')
        if self.pirate_blocks_edge(edge_key):
            return refused('PIRATE_BLOCKS', 'The pirate blocks every side of the hex it sits on')
        return None

    # --- Building ------------------------------------------------------

    def build_ship(self, player_name: str, edge_key: str) -> dict:
        """Build a ship, free during setup and paid for afterwards.

        Setup allows one because "a player who places a starting settlement on
        the coast may place a ship instead of a road next to that settlement",
        so this doubles as the setup placement and advances the setup turn the
        way `build_road` does.
        """
        if not self.rules['ships']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with ships')

        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        in_setup = self.game_phase == "setup"
        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can place pieces')

        if in_setup and self.setup_action != "road":
            return refused('WRONG_PHASE', 'You must place a settlement first')

        if not self.has_piece_available(player_name, 'ship'):
            return refused('NO_PIECES_LEFT', f'You have used all {self.MAX_SHIPS} ships')

        problem = self._ship_placement_refusal(player_name, edge_key)
        if problem is not None:
            return problem

        edge = self.edges[edge_key]
        used_free_road = False
        if in_setup:
            if not self.last_setup_settlement:
                return refused('WRONG_PHASE', 'You must place a settlement first')
            if self.last_setup_settlement not in edge.neighbors['vertices']:
                return refused('INVALID_PLACEMENT', 'Ship must be connected to your settlement')
        else:
            if not self.ship_connects(player_name, edge_key):
                return refused(
                    'INVALID_PLACEMENT',
                    'A ship must extend your own shipping route or leave one of your settlements',
                )
            # Road Building pays for a ship as readily as for a road: the card
            # builds "two roads, two ships, or one road and one ship".
            if self.free_roads_remaining > 0:
                self.free_roads_remaining -= 1
                used_free_road = True
            elif not self.can_afford(player_name, 'ship'):
                return refused('INSUFFICIENT_RESOURCES', self._cost_message('ship'))
            else:
                self.deduct_cost(player_name, 'ship')

        edge.ship = {'player': player_name, 'built_turn': self.turn_count}

        owner = self.get_player(player_name)
        if owner is not None and edge_key not in owner.ships:
            owner.ships.append(edge_key)

        if in_setup:
            self._advance_setup_turn()
        else:
            self.update_longest_road()

        # The Fog Islands: a ship reaching a fog hex reveals it for a resource
        # (Seafarers 2021, Scenario 3). A no-op without `fog_reveal` and away
        # from a face-down hex, so a plain Seafarers table is unaffected.
        revealed = self.discover_from_build(player_name, edge.neighbors['hexes'])

        # The Forgotten Tribe: a ship built onto a marked coast edge claims its
        # gift (Seafarers 2021, Scenario 5). A no-op without `coast_gifts` and
        # away from a marked edge, so a plain Seafarers table is unaffected.
        gift = self.claim_coast_gift(player_name, edge_key)

        return {'success': True, 'error': '', 'used_free_road': used_free_road,
                'revealed': revealed, 'gift': gift}

    # --- Moving --------------------------------------------------------

    def ship_is_open(self, player_name: str, edge_key: str) -> bool:
        """Whether this ship may be picked up.

        Three sentences of the rulebook, in the order they narrow each other:

        - "A player may only move a ship if at least one of that ship's two
          ends is not adjacent to any other piece belonging to that player."
        - "If a circular shipping route does not touch any of the owner's
          settlements or cities, every ship in that route counts as open."
        - "If a shipping route leaves one settlement and returns to that same
          settlement without touching any other settlement or city, one ship at
          each end of that route counts as open."

        Only the first used to be implemented, which made every loop closed. A
        closed route is one that "interconnects two of the owner's settlements
        and/or cities", so a circle touching one building or none was never
        closed by the definition; the other two sentences say which of its
        ships that leaves open.
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return False

        if self._ship_has_a_free_end(player_name, edge_key):
            return True

        route = self.ship_route(player_name, edge_key)
        if not self._route_is_circular(route):
            return False

        buildings = self._route_buildings(player_name, route)
        if not buildings:
            return True
        if len(buildings) == 1:
            # The loop leaves one building and comes back to it: the ship at
            # each end of it — the two touching that building — may move.
            return buildings[0] in edge.neighbors['vertices']
        return False

    def ship_route(self, player_name: str, edge_key: str) -> list:
        """Every ship of this player's chained to this one, this one included.

        "A chain of connected ships of the same colour forms a single shipping
        route", and a route is what the closed-and-open rules are written
        about — one ship on its own cannot tell whether it is in a circle.
        """
        route = {edge_key}
        unexplored = [edge_key]
        while unexplored:
            edge = self.edges.get(unexplored.pop())
            if edge is None:
                continue
            for vertex_key in edge.neighbors['vertices']:
                vertex = self.vertices.get(vertex_key)
                if vertex is None:
                    continue
                for connected_key in vertex.neighbors['edges']:
                    if connected_key in route:
                        continue
                    connected = self.edges.get(connected_key)
                    if connected and connected.ship \
                            and connected.ship.get('player') == player_name:
                        route.add(connected_key)
                        unexplored.append(connected_key)
        return sorted(route)

    def _route_is_circular(self, route: list) -> bool:
        """Whether the route closes on itself.

        A connected run of sides holds a loop exactly when it has at least as
        many sides as it has intersections; a route that branches without
        looping always has one intersection more.
        """
        intersections = {
            vertex_key
            for edge_key in route
            for vertex_key in self.edges[edge_key].neighbors['vertices']
        }
        return len(route) >= len(intersections)

    def _route_buildings(self, player_name: str, route: list) -> list:
        """Which of the owner's buildings this route touches.

        The owner's alone: the rules ask about "the owner's settlements and/or
        cities", and an opponent standing on the route neither closes it nor
        opens it.
        """
        touched = set()
        for edge_key in route:
            for vertex_key in self.edges[edge_key].neighbors['vertices']:
                vertex = self.vertices.get(vertex_key)
                if vertex and vertex.building \
                        and vertex.building.get('player') == player_name:
                    touched.add(vertex_key)
        return sorted(touched)

    def _ship_has_a_free_end(self, player_name: str, edge_key: str) -> bool:
        """Whether one end of this ship is clear of its owner's other pieces."""
        edge = self.edges[edge_key]
        for vertex_key in edge.neighbors['vertices']:
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            if vertex.building and vertex.building.get('player') == player_name:
                continue
            held = False
            for connected_key in vertex.neighbors['edges']:
                if connected_key == edge_key:
                    continue
                connected = self.edges.get(connected_key)
                if connected is None:
                    continue
                for piece in (connected.ship, connected.road):
                    if piece and piece.get('player') == player_name:
                        held = True
            if not held:
                return True
        return False

    def move_ship(self, player_name: str, from_edge_key: str, to_edge_key: str) -> dict:
        """Pick a ship up and lay it down somewhere it could have been built.

        One per turn, never one built this turn, never one whose both ends are
        held, and never off a side the pirate is beside. Costs nothing.
        """
        if not self.rules['ship_movement']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with ship movement')

        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot move ships during setup')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can move a ship')

        if self.ship_moved_this_turn:
            return refused('ALREADY_MOVED', 'You may only move one ship per turn')

        edge = self.edges.get(from_edge_key)
        if edge is None or edge.ship is None:
            return refused('INVALID_TARGET', 'There is no ship there')
        if edge.ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'You can only move your own ships')
        if edge.ship.get('built_turn') == self.turn_count:
            return refused('SHIP_JUST_BUILT', 'A ship cannot be moved on the turn it was built')
        if self.pirate_blocks_edge(from_edge_key):
            return refused(
                'PIRATE_BLOCKS', 'A ship beside the pirate may not be moved away'
            )
        if not self.ship_is_open(player_name, from_edge_key):
            return refused(
                'CLOSED_ROUTE',
                'Only a ship with a free end may be moved; this one is part of a closed route',
            )

        problem = self._ship_placement_refusal(player_name, to_edge_key, ignoring=from_edge_key)
        if problem is not None:
            return problem
        if not self.ship_connects(player_name, to_edge_key, ignoring=from_edge_key):
            return refused(
                'INVALID_PLACEMENT',
                'A ship must extend your own shipping route or leave one of your settlements',
            )

        ship = edge.ship
        edge.ship = None
        self.edges[to_edge_key].ship = {'player': player_name, 'built_turn': ship['built_turn']}

        owner = self.get_player(player_name)
        if owner is not None:
            if from_edge_key in owner.ships:
                owner.ships.remove(from_edge_key)
            if to_edge_key not in owner.ships:
                owner.ships.append(to_edge_key)

        self.ship_moved_this_turn = True
        self.update_longest_road()

        # The Forgotten Tribe: a ship *moved* onto a marked coast edge claims its
        # gift just as a built one does (Seafarers 2021, Scenario 5). A no-op
        # without `coast_gifts` and away from a marked edge.
        gift = self.claim_coast_gift(player_name, to_edge_key)

        return {'success': True, 'error': '', 'gift': gift}

    # --- The pirate ----------------------------------------------------

    def pirate_victims(self, player_name: str) -> list:
        """Whose ships lie beside the pirate, the mover's own excepted."""
        if self.pirate_hex is None:
            return []

        victims = []
        for edge in self.edges.values():
            if edge.ship is None or self.pirate_hex not in edge.neighbors['hexes']:
                continue
            owner = edge.ship.get('player')
            # One card from a player however many ships they have there.
            if owner and owner != player_name and owner not in victims:
                victims.append(owner)
        return victims

    def move_pirate(self, player_name: str, hex_key: str) -> dict:
        """Move the pirate onto a sea hex instead of moving the robber.

        Returns {'success', 'error', 'code', 'victims'}; a non-empty victim
        list means the mover still owes a choice, exactly as the robber does,
        and the same `steal_from_victim` resolves it.
        """
        if not self.rules['pirate']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with the pirate')

        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot move the pirate during setup')

        if not self.must_move_robber:
            return refused('WRONG_PHASE', 'You do not need to move the robber or the pirate')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can move the pirate')

        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None:
            return refused('INVALID_TARGET', 'Invalid hex')
        if not tiles.is_sea(hex_obj.type):
            return refused('INVALID_TARGET', 'The pirate sails; it may only sit on a sea hex')
        if hex_key == self.pirate_hex:
            return refused('INVALID_TARGET', 'The pirate is already there')

        self.pirate_hex = hex_key
        self.must_move_robber = False

        victims = self.pirate_victims(player_name)
        if victims:
            self.must_choose_victim = True
            self.robber_victims = victims

        return {'success': True, 'error': '', 'victims': victims}

    # --- Islands -------------------------------------------------------

    def island_of_vertex(self, vertex_key: str) -> str | None:
        """Which island this intersection stands on, or None out at sea.

        All the land hexes meeting at one intersection are neighbours of each
        other, so they are always the same island; the lowest key is taken only
        to make the answer independent of iteration order.
        """
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return None
        islands = self.islands()
        touching = sorted(key for key in vertex.neighbors['hexes'] if key in islands)
        return islands[touching[0]] if touching else None

    def record_island_settlement(self, player_name: str, vertex_key: str, award: bool) -> int:
        """Note that a player has reached an island, and score it if it is new.

        `award` is False for the starting settlements: the island a player
        began on is theirs already, and the special points are for "the first
        settlement on one of the small islands". Returns the points scored.
        """
        if not self.rules['island_victory_points']:
            return 0

        island_id = self.island_of_vertex(vertex_key)
        if island_id is None:
            return 0

        settled = self.player_islands.setdefault(player_name, [])
        if island_id in settled:
            return 0
        settled.append(island_id)

        if not award:
            return 0

        points = self.rules['island_points_per_island']
        self.island_points[player_name] = self.island_points.get(player_name, 0) + points
        logger.debug("%s reached island %s for %d special victory points",
                     player_name, island_id, points)
        return points
