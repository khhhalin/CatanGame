"""Ships: what they cost, where they may go, and how they move.

Every rule here is one sentence of `expansions.md`'s Seafarers section, cited
in the test that pins it. What a player would notice if one broke: ships
sailing across the island, a shipping route that grows from a road it is not
joined to, or a ship picked up out of a closed route it should be stuck in.
"""

import pytest
from seafarers_board import (
    build_ships_along,
    coastal_vertex,
    give_building,
    inland_edges_at,
    other_end,
    sea_edges_at,
    sea_ring,
    seafarers_game,
    ship_path,
)


@pytest.fixture
def sea_game():
    return seafarers_game()


@pytest.fixture
def alice_on_the_coast(sea_game):
    """Alice with a settlement on the coast and a sea side leaving it."""
    vertex_key = coastal_vertex(sea_game)
    give_building(sea_game, 'Alice', vertex_key)
    return sea_game, vertex_key, sea_edges_at(sea_game, vertex_key)[0]


def afford_a_ship(game, player_name='Alice'):
    game.get_player(player_name).resources = {'wood': 1, 'sheep': 1}


class TestCost:
    def test_a_ship_costs_one_wool_and_one_lumber(self, alice_on_the_coast):
        """expansions.md 34: "A ship costs one wool and one lumber to build.\""""
        game, _vertex, edge_key = alice_on_the_coast
        game.get_player('Alice').resources = {'wood': 1, 'sheep': 1, 'brick': 3}

        assert game.build_ship('Alice', edge_key)['success']
        assert game.get_player('Alice').resources == {'wood': 0, 'sheep': 0, 'brick': 3}

    def test_an_empty_hand_cannot_pay_for_one(self, alice_on_the_coast):
        game, _vertex, edge_key = alice_on_the_coast
        game.get_player('Alice').resources = {'wood': 1}

        result = game.build_ship('Alice', edge_key)
        assert result['code'] == 'INSUFFICIENT_RESOURCES'
        assert game.edges[edge_key].ship is None

    def test_a_road_building_card_pays_for_a_ship(self, alice_on_the_coast):
        """expansions.md 127: the card builds "two roads, two ships, or one
        road and one ship"."""
        game, _vertex, edge_key = alice_on_the_coast
        game.free_roads_remaining = 2
        game.get_player('Alice').resources = {}

        assert game.build_ship('Alice', edge_key)['success']
        assert game.free_roads_remaining == 1


class TestWhereAShipMayLie:
    def test_a_ship_may_never_lie_between_two_land_hexes(self, sea_game):
        """expansions.md 38."""
        vertex_key = coastal_vertex(sea_game, with_inland_edge=True)
        give_building(sea_game, 'Alice', vertex_key)
        afford_a_ship(sea_game)

        # An inland side reachable from Alice's own settlement, so the only
        # thing that can refuse it is the water rule.
        edge_key = inland_edges_at(sea_game, vertex_key)[0]
        result = sea_game.build_ship('Alice', edge_key)
        assert result['code'] == 'INVALID_PLACEMENT'
        assert sea_game.edges[edge_key].ship is None

    def test_a_ship_may_not_share_a_side_with_a_road(self, alice_on_the_coast):
        """expansions.md 41: not along a coastal side that already has a road."""
        game, _vertex, edge_key = alice_on_the_coast
        game.edges[edge_key].road = {'player': 'Alice'}
        afford_a_ship(game)

        assert game.build_ship('Alice', edge_key)['code'] == 'OCCUPIED'

    def test_a_road_may_not_share_a_side_with_a_ship(self, alice_on_the_coast):
        game, _vertex, edge_key = alice_on_the_coast
        game.edges[edge_key].ship = {'player': 'Alice', 'built_turn': 0}
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1}

        assert game.build_road('Alice', edge_key)['code'] == 'OCCUPIED'

    def test_a_road_cannot_be_built_out_at_sea(self, sea_game):
        """The sea sides exist for ships. A road on open water would be a way
        to walk to another island on foot."""
        vertex_key = coastal_vertex(sea_game)
        give_building(sea_game, 'Alice', vertex_key)
        sea_game.get_player('Alice').resources = {'wood': 1, 'brick': 1}

        open_water = [
            key for key in sea_game.vertices[vertex_key].neighbors['edges']
            if not sea_game.land_hexes_of_edge(key)
        ]
        for edge_key in open_water:
            assert sea_game.build_road('Alice', edge_key)['code'] == 'INVALID_PLACEMENT'

    def test_a_settlement_cannot_be_built_out_at_sea(self, sea_game):
        """The graph reaches over the water now; the buildings must not."""
        sea_vertex = next(
            key for key, vertex in sorted(sea_game.vertices.items())
            if not vertex.neighbors['hexes']
        )
        sea_game.get_player('Alice').resources = {
            'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1,
        }
        result = sea_game.place_settlement('Alice', sea_vertex)
        assert result['code'] == 'INVALID_PLACEMENT'
        assert sea_game.vertices[sea_vertex].building is None


class TestTheShippingNetwork:
    def test_a_ship_may_leave_a_settlement_of_your_own(self, alice_on_the_coast):
        """expansions.md 39."""
        game, _vertex, edge_key = alice_on_the_coast
        afford_a_ship(game)

        assert game.build_ship('Alice', edge_key)['success']
        assert game.edges[edge_key].ship['player'] == 'Alice'
        assert game.get_player('Alice').ships == [edge_key]

    def test_a_ship_may_extend_a_ship_of_your_own(self, alice_on_the_coast):
        """expansions.md 40."""
        game, vertex_key, edge_key = alice_on_the_coast
        build_ships_along(game, 'Alice', [edge_key])
        afford_a_ship(game)

        onward = next(
            key for key in sea_edges_at(game, other_end(game, edge_key, vertex_key))
            if key != edge_key
        )
        assert game.build_ship('Alice', onward)['success']

    def test_a_ship_may_not_start_from_nowhere(self, sea_game):
        afford_a_ship(sea_game)
        edge_key = next(key for key in sorted(sea_game.edges) if sea_game.is_sea_edge(key))

        result = sea_game.build_ship('Alice', edge_key)
        assert result['code'] == 'INVALID_PLACEMENT'

    def test_a_ship_may_not_extend_an_opponents_route(self, alice_on_the_coast):
        game, vertex_key, edge_key = alice_on_the_coast
        build_ships_along(game, 'Bob', [edge_key])
        # Alice's settlement is at one end, so ask from the far end, where only
        # Bob's ship touches.
        far_end = other_end(game, edge_key, vertex_key)
        onward = next(key for key in sea_edges_at(game, far_end) if key != edge_key)
        afford_a_ship(game)

        assert game.build_ship('Alice', onward)['code'] == 'INVALID_PLACEMENT'

    def test_a_road_alone_does_not_carry_a_shipping_route_onward(self, sea_game):
        """expansions.md 58-59: the two networks only join at a settlement, so
        a road reaching the coast does not let a ship set out from it."""
        vertex_key = coastal_vertex(sea_game, with_inland_edge=True)
        land_side = inland_edges_at(sea_game, vertex_key)[0]
        sea_game.edges[land_side].road = {'player': 'Alice'}
        sea_game.get_player('Alice').roads.append(land_side)
        afford_a_ship(sea_game)

        edge_key = sea_edges_at(sea_game, vertex_key)[0]
        assert sea_game.build_ship('Alice', edge_key)['code'] == 'INVALID_PLACEMENT'

    def test_a_settlement_joins_the_two_networks(self, sea_game):
        vertex_key = coastal_vertex(sea_game, with_inland_edge=True)
        land_side = inland_edges_at(sea_game, vertex_key)[0]
        sea_game.edges[land_side].road = {'player': 'Alice'}
        give_building(sea_game, 'Alice', vertex_key)
        afford_a_ship(sea_game)

        assert sea_game.build_ship('Alice', sea_edges_at(sea_game, vertex_key)[0])['success']


class TestSupplyAndRules:
    def test_a_player_runs_out_of_ships(self, alice_on_the_coast):
        """expansions.md 51-52: fifteen pieces, and no more until one frees up."""
        game, _vertex, edge_key = alice_on_the_coast
        game.get_player('Alice').ships = [f'{n},0,0' for n in range(game.MAX_SHIPS)]
        afford_a_ship(game)

        assert game.build_ship('Alice', edge_key)['code'] == 'NO_PIECES_LEFT'

    def test_a_table_without_ships_has_nowhere_to_put_one(self):
        """The rule is off, so the board has no sea sides and the action is
        refused by name rather than by geometry."""
        game = seafarers_game(ships=False, ship_movement=False, pirate=False,
                              longest_trade_route=False, island_victory_points=False)
        assert game.build_ship('Alice', next(iter(game.edges)))['code'] == 'RULE_NOT_IN_PLAY'

    def test_only_the_player_whose_turn_it_is_may_build(self, alice_on_the_coast):
        game, _vertex, edge_key = alice_on_the_coast
        game.get_player('Bob').resources = {'wood': 1, 'sheep': 1}

        assert game.build_ship('Bob', edge_key)['code'] == 'NOT_YOUR_TURN'


class TestMovingShips:
    def _route(self, game, length=2):
        start = coastal_vertex(game)
        give_building(game, 'Alice', start)
        edges, vertices = ship_path(game, start, length)
        build_ships_along(game, 'Alice', edges)
        return start, edges, vertices

    def test_the_free_end_of_a_route_may_be_moved(self, sea_game):
        """expansions.md 63, 66: one ship a turn, and only one with a free end."""
        start, edges, vertices = self._route(sea_game, length=2)
        # Somewhere still touching what is left of the route once this ship is
        # picked up: a second side leaving the settlement it sails from.
        target = next(
            key for key in sea_edges_at(sea_game, start)
            if key not in edges and sea_game.edges[key].ship is None
        )

        assert sea_game.move_ship('Alice', edges[-1], target)['success']
        assert sea_game.edges[edges[-1]].ship is None
        assert sea_game.edges[target].ship['player'] == 'Alice'
        assert sorted(sea_game.get_player('Alice').ships) == sorted([edges[0], target])

    def test_only_one_ship_may_move_per_turn(self, sea_game):
        """expansions.md 62."""
        start, edges, vertices = self._route(sea_game, length=2)
        # Somewhere still touching what is left of the route once this ship is
        # picked up: a second side leaving the settlement it sails from.
        target = next(
            key for key in sea_edges_at(sea_game, start)
            if key not in edges and sea_game.edges[key].ship is None
        )
        assert sea_game.move_ship('Alice', edges[-1], target)['success']

        assert sea_game.move_ship('Alice', target, edges[-1])['code'] == 'ALREADY_MOVED'

    def test_the_allowance_comes_back_next_turn(self, sea_game):
        sea_game.ship_moved_this_turn = True
        sea_game.force_advance_turn()
        assert sea_game.ship_moved_this_turn is False

    def test_a_ship_built_this_turn_stays_where_it_was_put(self, alice_on_the_coast):
        """expansions.md 64."""
        game, vertex_key, edge_key = alice_on_the_coast
        afford_a_ship(game)
        assert game.build_ship('Alice', edge_key)['success']

        elsewhere = next(
            key for key in sea_edges_at(game, vertex_key) if key != edge_key
        )
        assert game.move_ship('Alice', edge_key, elsewhere)['code'] == 'SHIP_JUST_BUILT'

    def test_a_ship_between_two_of_your_settlements_is_stuck(self, sea_game):
        """expansions.md 68: a closed route may never be moved. Both ends of
        every ship in it are held — by a building or by the next ship."""
        start, edges, vertices = self._route(sea_game, length=2)
        give_building(sea_game, 'Alice', vertices[-1])

        for edge_key in edges:
            assert not sea_game.ship_is_open('Alice', edge_key)
            target = next(
                key for key in sorted(sea_game.edges)
                if sea_game.is_sea_edge(key) and sea_game.edges[key].ship is None
            )
            assert sea_game.move_ship('Alice', edge_key, target)['code'] == 'CLOSED_ROUTE'

    def test_a_moved_ship_must_land_somewhere_it_could_have_been_built(self, sea_game):
        """expansions.md 65-67."""
        start, edges, vertices = self._route(sea_game, length=1)
        stranded = next(
            key for key in sorted(sea_game.edges)
            if sea_game.is_sea_edge(key)
            and sea_game.edges[key].ship is None
            and not sea_game.ship_connects('Alice', key, ignoring=edges[0])
        )
        assert sea_game.move_ship('Alice', edges[0], stranded)['code'] == 'INVALID_PLACEMENT'
        assert sea_game.edges[edges[0]].ship is not None

    def test_moving_a_ship_costs_nothing(self, sea_game):
        """expansions.md 70."""
        start, edges, vertices = self._route(sea_game, length=1)
        sea_game.get_player('Alice').resources = {'wood': 2, 'sheep': 2}
        target = next(
            key for key in sea_edges_at(sea_game, start)
            if key != edges[0] and sea_game.edges[key].ship is None
        )

        assert sea_game.move_ship('Alice', edges[0], target)['success']
        assert sea_game.get_player('Alice').resources == {'wood': 2, 'sheep': 2}

    def test_nobody_moves_another_players_ship(self, sea_game):
        start, edges, vertices = self._route(sea_game, length=1)
        target = next(
            key for key in sea_edges_at(sea_game, start)
            if key != edges[0] and sea_game.edges[key].ship is None
        )
        sea_game.current_player_index = sea_game.get_player_names().index('Bob')

        assert sea_game.move_ship('Bob', edges[0], target)['code'] == 'NOT_YOUR_PIECE'

    def test_a_table_that_did_not_take_the_rule_cannot_move_ships(self):
        game = seafarers_game(ship_movement=False)
        start = coastal_vertex(game)
        give_building(game, 'Alice', start)
        edges, _vertices = ship_path(game, start, 1)
        build_ships_along(game, 'Alice', edges)

        target = next(
            key for key in sea_edges_at(game, start)
            if key != edges[0] and game.edges[key].ship is None
        )
        assert game.move_ship('Alice', edges[0], target)['code'] == 'RULE_NOT_IN_PLAY'


class TestCircularRoutes:
    """A loop is not a closed route.

    Reported as a rule the engine got wrong: `ship_is_open` asked only whether
    both ends of one ship were held, so every ship in a circle was stuck for
    ever — the one thing expansions.md 67-68 say cannot happen. A closed route
    is one that "interconnects *two* of the owner's settlements and/or cities"
    (expansions.md 72), and a loop touching one building or none is not that.
    """

    def _ring(self, game):
        edges, vertices = sea_ring(game)
        build_ships_along(game, 'Alice', edges)
        return edges, vertices

    def test_a_circle_touching_no_building_is_open_all_the_way_round(self, sea_game):
        """expansions.md 67: "If a circular shipping route does not touch any
        of the owner's settlements or cities, every ship in that route counts
        as open and may be moved.\""""
        edges, _vertices = self._ring(sea_game)

        assert [key for key in edges if not sea_game.ship_is_open('Alice', key)] == []

    def test_a_loop_back_to_one_settlement_opens_a_ship_at_each_end(self, sea_game):
        """expansions.md 68: "If a shipping route leaves one settlement and
        returns to that same settlement without touching any other settlement
        or city, one ship at each end of that route counts as open.\""""
        edges, vertices = self._ring(sea_game)
        home = vertices[0]
        give_building(sea_game, 'Alice', home)

        ends = sorted(
            key for key in edges if home in sea_game.edges[key].neighbors['vertices']
        )
        assert len(ends) == 2, 'a loop leaves its settlement by two sides'
        assert [key for key in edges if sea_game.ship_is_open('Alice', key)] == ends

    def test_a_loop_between_two_settlements_is_still_closed(self, sea_game):
        """expansions.md 72: a route interconnecting two of the owner's
        buildings is closed, and a circle that does so is no exception."""
        edges, vertices = self._ring(sea_game)
        give_building(sea_game, 'Alice', vertices[0])
        give_building(sea_game, 'Alice', vertices[len(vertices) // 2])

        assert [key for key in edges if sea_game.ship_is_open('Alice', key)] == []

    def test_an_opponents_building_does_not_open_your_loop(self, sea_game):
        """The rule names "the owner's" buildings, so Bob standing on the ring
        neither closes Alice's route nor opens it."""
        edges, vertices = self._ring(sea_game)
        give_building(sea_game, 'Alice', vertices[0])
        give_building(sea_game, 'Bob', vertices[len(vertices) // 2])

        ends = sorted(
            key for key in edges
            if vertices[0] in sea_game.edges[key].neighbors['vertices']
        )
        assert [key for key in edges if sea_game.ship_is_open('Alice', key)] == ends


class TestSetup:
    def test_a_starting_settlement_on_the_coast_may_be_given_a_ship(self):
        """expansions.md 132-133: a ship instead of the starting road."""
        game = seafarers_game()
        game.game_phase = 'setup'
        game.setup_turn = 0
        game.setup_action = 'settlement'

        vertex_key = coastal_vertex(game)
        # Clear whatever the fixture's own setup left standing there.
        game.vertices[vertex_key].building = None
        assert game.place_settlement('Alice', vertex_key)['success']

        edge_key = sea_edges_at(game, vertex_key)[0]
        assert game.build_ship('Alice', edge_key)['success']
        assert game.edges[edge_key].ship['player'] == 'Alice'
        assert game.get_player('Alice').resources == {}, "a setup ship is free"
