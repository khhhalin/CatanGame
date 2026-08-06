"""Transport ships, the Explorers & Pirates cargo carriers.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. A transport ship is not a Seafarers ship. Both live on the same
`edge.ship` slot, but they are opposite readings of it: the Seafarers ship is a
route connector that extends a shipping network and feeds the Longest Trade
Route, while an E&P transport ship carries cargo in a hold, moves along the sea
with movement points, and forms no routes at all (expansions.md 864-882, 866).

The two never coexist — `transport_ships` is refused with `ships` at
`start_game` (the `sea_ship_model` exclusion in rules.py) — so this module never
has to reconcile them. It keeps its own build, movement and cargo code entirely
apart from `seafarers.py`; the Seafarers `ship_connects` / `build_ship` /
`move_ship` are not called here, and a transport-ship edge is fenced out of
`_touches_own_route` as defence in depth even though the exclusion already means
it can never be reached with `ships` on.

Every method is gated on `self.rules['transport_ships']`, never on an expansion
name. A transport ship is built only on a sea side beside one of the player's
harbor settlements, for 1 lumber and 1 wool; harbor settlements own the basins
cargo is loaded from and unloaded to, so — like harbor settlements themselves —
transport ships need no `self.ep` container.
"""

from game.results import refused

# A hold carries one large piece or two small ones (expansions.md 872). Counted
# in slots so the "1 large or 2 small" rule is one comparison: a large piece
# fills both slots, a small piece fills one.
HOLD_SLOTS = 2
LARGE_SLOTS = 2
SMALL_SLOTS = 1


def _is_transport_ship(ship: dict) -> bool:
    """Whether an `edge.ship` dict is an E&P transport, not a Seafarers ship.

    A Seafarers ship carries no `kind`; a transport is tagged `'transport'` when
    it is built, which is the one thing that tells the two apart on a slot they
    share.
    """
    return bool(ship) and ship.get('kind') == 'transport'


def _piece_slots(piece: dict) -> int:
    """How much of the hold a cargo piece takes: a large piece fills it."""
    return LARGE_SLOTS if piece.get('size') == 'large' else SMALL_SLOTS


class TransportShipRules:
    """Building, moving and loading Explorers & Pirates transport ships."""

    # --- Telling the two ship models apart ---------------------------------

    def is_transport_ship_edge(self, edge_key: str) -> bool:
        """Whether this edge carries an E&P transport ship (not a Seafarers one)."""
        edge = self.edges.get(edge_key)
        return edge is not None and _is_transport_ship(edge.ship)

    # --- Building ----------------------------------------------------------

    def _adjacent_harbor_settlement(self, player_name: str, edge_key: str):
        """A vertex of this edge holding the player's harbor settlement, or None.

        A transport ship is built and loaded at a harbor settlement, so both the
        build site and the load site are "a sea side one of whose ends is my
        harbor settlement" — the one geometric test they share.
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return None
        for vertex_key in edge.neighbors['vertices']:
            vertex = self.vertices.get(vertex_key)
            if (
                vertex is not None
                and vertex.building is not None
                and vertex.building.get('type') == 'harbor_settlement'
                and vertex.building.get('player') == player_name
            ):
                return vertex_key
        return None

    def build_transport_ship(self, player_name: str, edge_key: str) -> dict:
        """Build a transport ship on a sea side beside a harbor settlement.

        Mirrors the ownership and turn guards of the other builds, with a
        transport's own site rule: a harbor settlement, never a bare coastline,
        is the only place a ship is built (expansions.md 899). It forms no route
        and so runs no network update — the sharpest way it differs from a
        Seafarers ship.
        """
        if not self.rules['transport_ships']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with transport ships')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked
        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot build a transport ship during setup phase')

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can place pieces')

        if not self.has_piece_available(player_name, 'ship'):
            return refused('NO_PIECES_LEFT', f'You have used all {self.MAX_SHIPS} ships')

        edge = self.edges.get(edge_key)
        if edge is None:
            return refused('INVALID_TARGET', 'Invalid edge')
        if not self.is_sea_edge(edge_key):
            return refused('INVALID_PLACEMENT', 'A ship must lie on a hex side that touches sea')
        if edge.ship is not None:
            return refused('OCCUPIED', 'This location already has a ship')
        if edge.road is not None:
            return refused('OCCUPIED', 'This coastal side already carries a road')
        if self._adjacent_harbor_settlement(player_name, edge_key) is None:
            return refused(
                'NOT_AT_HARBOR',
                'A transport ship is built on a sea side beside one of your harbor settlements',
            )

        if not self.can_afford(player_name, 'transport_ship'):
            return refused('INSUFFICIENT_RESOURCES', self._cost_message('transport_ship'))
        self.deduct_cost(player_name, 'transport_ship')

        self.transport_ship_counter += 1
        edge.ship = {
            'player': player_name,
            'built_turn': self.turn_count,
            'kind': 'transport',
            'cargo': [],
            'id': self.transport_ship_counter,
        }

        owner = self.get_player(player_name)
        if owner is not None and edge_key not in owner.ships:
            owner.ships.append(edge_key)

        # No route update: a transport ship extends no network (866).
        return {'success': True, 'error': ''}

    # --- Movement ----------------------------------------------------------

    def ship_movement_points_for(self, player_name: str) -> int:
        """How far a transport ship may travel this turn.

        The table's `ship_movement_points` (default 4, expansions.md 874), plus
        1 if this player earned the Swift Voyage village advantage — read off
        the E&P state when there is one, since the advantage is state, not a
        catalogue rule.
        """
        points = self.rules['ship_movement_points']
        if self.ep is not None and self.ep.has_advantage(player_name, 'swift_voyage'):
            points += 1
        return points

    def _sea_edge_neighbors(self, edge_key: str) -> list:
        """The sea sides a ship on this edge could sail to in one step.

        Every hex side sharing an endpoint with this one that is itself a sea
        edge — the sea-route graph, walked one step. It is *not* the shipping
        network: it ignores who owns what, because a transport ship sails open
        water, it does not extend a route.
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return []
        neighbours = []
        for vertex_key in edge.neighbors['vertices']:
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            for other_key in vertex.neighbors.get('edges', []):
                if other_key == edge_key or other_key in neighbours:
                    continue
                if self.is_sea_edge(other_key):
                    neighbours.append(other_key)
        return neighbours

    def _reachable_sea_edges(self, from_edge_key: str, points: int) -> dict:
        """Empty sea sides reachable from here within `points` steps.

        A breadth-first walk of the sea-route graph. The path may not pass
        through a side another ship already occupies — ships do not stack — so
        an occupied edge is a wall, not a stepping stone. Returns {edge: steps}.
        """
        distances = {from_edge_key: 0}
        frontier = [from_edge_key]
        while frontier:
            current = frontier.pop(0)
            if distances[current] >= points:
                continue
            for neighbour in self._sea_edge_neighbors(current):
                if neighbour in distances:
                    continue
                if self.edges[neighbour].ship is not None:
                    continue
                distances[neighbour] = distances[current] + 1
                frontier.append(neighbour)
        del distances[from_edge_key]
        return distances

    def move_transport_ship(self, player_name: str, from_edge_key: str, to_edge_key: str) -> dict:
        """Sail a transport ship along the sea, up to its movement points.

        One move per ship per turn (the minimal movement-phase guard; the full
        production→build→movement ordering is a separate wave). The destination
        must be an empty sea side reachable within the ship's movement points,
        and the cargo rides along untouched.
        """
        if not self.rules['transport_ships']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with transport ships')
        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot move ships during setup')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can move a ship')

        edge = self.edges.get(from_edge_key)
        if edge is None or edge.ship is None:
            return refused('INVALID_TARGET', 'There is no ship there')
        if not _is_transport_ship(edge.ship):
            return refused('NOT_A_TRANSPORT', 'That ship is not a transport ship')
        if edge.ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'You can only move your own ships')
        if edge.ship['id'] in self.transport_ships_moved:
            return refused('ALREADY_MOVED', 'That ship has already moved this turn')

        destination = self.edges.get(to_edge_key)
        if destination is None:
            return refused('INVALID_TARGET', 'Invalid edge')
        if to_edge_key == from_edge_key:
            return refused('INVALID_PLACEMENT', 'A ship must move to a different sea side')
        if destination.ship is not None:
            return refused('OCCUPIED', 'This location already has a ship')
        if destination.road is not None:
            return refused('OCCUPIED', 'This coastal side already carries a road')

        points = self.ship_movement_points_for(player_name)
        if to_edge_key not in self._reachable_sea_edges(from_edge_key, points):
            return refused(
                'OUT_OF_RANGE',
                f'That side is more than {points} movement points away over the sea',
            )

        ship = edge.ship
        edge.ship = None
        destination.ship = ship

        owner = self.get_player(player_name)
        if owner is not None:
            if from_edge_key in owner.ships:
                owner.ships.remove(from_edge_key)
            if to_edge_key not in owner.ships:
                owner.ships.append(to_edge_key)

        self.transport_ships_moved.add(ship['id'])
        # A ship arriving beside an opponent's pirate pays 1 gold tribute
        # (expansions.md 949). The call is a no-op without the pirate rule, so a
        # table playing transport ships alone is unaffected.
        self.charge_pirate_tribute(player_name, to_edge_key)
        # No route update: a transport ship extends no network (866).
        return {'success': True, 'error': ''}

    # --- Cargo hold --------------------------------------------------------

    def _hold_used(self, cargo: list) -> int:
        return sum(_piece_slots(piece) for piece in cargo)

    def load_transport_ship(self, player_name: str, edge_key: str, basin_index: int) -> dict:
        """Move a piece from an adjacent harbor settlement's basin into the hold.

        The hold takes one large piece or two small ones (872); a load that
        would overflow it is refused. The ship must lie beside the player's
        harbor settlement, which is the only place cargo is loaded (899).
        """
        if not self.rules['transport_ships']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with transport ships')
        edge = self.edges.get(edge_key)
        if edge is None or not _is_transport_ship(edge.ship):
            return refused('INVALID_TARGET', 'There is no transport ship there')
        if edge.ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'You can only load your own ships')

        harbor_key = self._adjacent_harbor_settlement(player_name, edge_key)
        if harbor_key is None:
            return refused('NOT_AT_HARBOR', 'A ship loads only beside your harbor settlement')
        basin = self.vertices[harbor_key].building['basin']
        if basin_index < 0 or basin_index >= len(basin):
            return refused('INVALID_TARGET', 'No such piece in the basin')

        piece = basin[basin_index]
        cargo = edge.ship['cargo']
        if self._hold_used(cargo) + _piece_slots(piece) > HOLD_SLOTS:
            return refused('HOLD_FULL', 'The hold takes one large piece or two small ones')

        basin.pop(basin_index)
        cargo.append(piece)
        return {'success': True, 'error': ''}

    def unload_transport_ship(self, player_name: str, edge_key: str, cargo_index: int) -> dict:
        """Move a piece from the hold back into an adjacent harbor's basin."""
        if not self.rules['transport_ships']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with transport ships')
        edge = self.edges.get(edge_key)
        if edge is None or not _is_transport_ship(edge.ship):
            return refused('INVALID_TARGET', 'There is no transport ship there')
        if edge.ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'You can only unload your own ships')

        harbor_key = self._adjacent_harbor_settlement(player_name, edge_key)
        if harbor_key is None:
            return refused('NOT_AT_HARBOR', 'A ship unloads only beside your harbor settlement')
        cargo = edge.ship['cargo']
        if cargo_index < 0 or cargo_index >= len(cargo):
            return refused('INVALID_TARGET', 'No such piece in the hold')

        piece = cargo.pop(cargo_index)
        self.vertices[harbor_key].building['basin'].append(piece)
        return {'success': True, 'error': ''}
