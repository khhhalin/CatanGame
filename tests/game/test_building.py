"""Placement rules, straight against the engine.

These used to live in `server/handlers/building.py`, where the only way to
reach them was to open a socket. Everything here is the base game's building
law: the distance rule, road connectivity, setup ordering and piece supply.
"""

import pytest


def acting(game):
    return game.current_player_name()


def other_player(game, name):
    return next(p.name for p in game.players if p.name != name)


def a_vertex(game):
    """Any vertex with both neighbouring vertices and edges recorded."""
    for key, vertex in game.vertices.items():
        if vertex.neighbors.get('vertices') and vertex.neighbors.get('edges'):
            return key
    raise AssertionError("board has no connected vertices")


def neighbour_of(game, vertex_key):
    return game.vertices[vertex_key].neighbors['vertices'][0]


def give_road(game, player_name, edge_key):
    """Put a road on the board without going through the placement rules.

    Building a network legally takes a whole setup phase; these tests are about
    the *next* placement, so the starting position is set up directly.
    """
    game.edges[edge_key].road = {'player': player_name}
    player = game.get_player(player_name)
    if edge_key not in player.roads:
        player.roads.append(edge_key)


def give_building(game, player_name, vertex_key, building_type='settlement'):
    game.vertices[vertex_key].building = {'type': building_type, 'player': player_name}
    player = game.get_player(player_name)
    if building_type == 'city':
        player.cities.append(vertex_key)
    else:
        player.settlements.append(vertex_key)


BUILD_COSTS = {'wood': 1, 'brick': 1, 'sheep': 1, 'wheat': 1, 'ore': 3}


@pytest.fixture
def rich():
    """Enough of everything for any single building."""
    def _rich(game, player_name):
        game.get_player(player_name).resources = dict(BUILD_COSTS)
    return _rich


class TestSetupOrdering:
    def test_a_settlement_is_followed_by_a_road(self, fresh_game):
        name = acting(fresh_game)
        result = fresh_game.place_settlement(name, a_vertex(fresh_game))

        assert result['success']
        assert fresh_game.setup_action == 'road'

    def test_a_second_settlement_in_the_same_turn_is_refused(self, fresh_game):
        name = acting(fresh_game)
        first = a_vertex(fresh_game)
        fresh_game.place_settlement(name, first)

        far = next(
            key for key in fresh_game.vertices
            if key != first and key not in fresh_game.vertices[first].neighbors['vertices']
        )
        result = fresh_game.place_settlement(name, far)

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'You must place a road next'

    def test_a_road_before_any_settlement_is_refused(self, fresh_game):
        name = acting(fresh_game)
        result = fresh_game.build_road(name, next(iter(fresh_game.edges)))

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'You must place a settlement first'

    def test_the_setup_road_must_touch_the_new_settlement(self, fresh_game):
        name = acting(fresh_game)
        vertex_key = a_vertex(fresh_game)
        fresh_game.place_settlement(name, vertex_key)

        touching = set(fresh_game.vertices[vertex_key].neighbors['edges'])
        elsewhere = next(key for key in fresh_game.edges if key not in touching)
        result = fresh_game.build_road(name, elsewhere)

        assert result['code'] == 'INVALID_PLACEMENT'
        assert result['error'] == 'Road must be connected to your settlement'

    def test_a_settlement_and_road_pass_the_turn_on(self, fresh_game):
        first = acting(fresh_game)
        vertex_key = a_vertex(fresh_game)
        fresh_game.place_settlement(first, vertex_key)
        fresh_game.build_road(first, fresh_game.vertices[vertex_key].neighbors['edges'][0])

        assert fresh_game.setup_turn == 1
        assert acting(fresh_game) != first
        assert fresh_game.setup_action == 'settlement'

    def test_only_the_player_whose_turn_it_is_may_place(self, fresh_game):
        name = acting(fresh_game)
        intruder = other_player(fresh_game, name)

        result = fresh_game.place_settlement(intruder, a_vertex(fresh_game))

        assert result['code'] == 'NOT_YOUR_TURN'
        assert result['error'] == f'Only {name} can place buildings'

    def test_setup_placement_costs_nothing(self, fresh_game):
        name = acting(fresh_game)
        fresh_game.place_settlement(name, a_vertex(fresh_game))

        assert fresh_game.get_player(name).resources == {}

    def test_the_second_round_reverses_the_order(self, fresh_game):
        """Setup runs 0,1,...,n-1,n-1,...,0, so the last player places twice."""
        seen = []
        for _ in range(2 * len(fresh_game.players)):
            name = acting(fresh_game)
            seen.append(name)
            vertex_key = next(
                key for key in fresh_game.vertices
                if fresh_game._respects_distance_rule(key)
                and fresh_game.vertices[key].building is None
                and fresh_game.vertices[key].neighbors.get('edges')
            )
            assert fresh_game.place_settlement(name, vertex_key)['success']
            edge_key = next(
                key for key in fresh_game.vertices[vertex_key].neighbors['edges']
                if fresh_game.edges[key].road is None
            )
            assert fresh_game.build_road(name, edge_key)['success']

        assert seen == seen[: len(fresh_game.players)] + seen[: len(fresh_game.players)][::-1]
        assert fresh_game.game_phase == 'playing'


class TestDistanceRule:
    def test_a_neighbouring_intersection_is_too_close(self, fresh_game):
        name = acting(fresh_game)
        occupied = a_vertex(fresh_game)
        give_building(fresh_game, other_player(fresh_game, name), occupied)

        result = fresh_game.place_settlement(name, neighbour_of(fresh_game, occupied))

        assert result['code'] == 'INVALID_PLACEMENT'
        assert result['error'] == 'Cannot place settlement next to another settlement'

    def test_your_own_settlement_blocks_you_too(self, fresh_game):
        name = acting(fresh_game)
        occupied = a_vertex(fresh_game)
        give_building(fresh_game, name, occupied)

        result = fresh_game.place_settlement(name, neighbour_of(fresh_game, occupied))

        assert result['code'] == 'INVALID_PLACEMENT'

    def test_two_intersections_away_is_far_enough(self, fresh_game):
        name = acting(fresh_game)
        occupied = a_vertex(fresh_game)
        give_building(fresh_game, name, occupied)

        blocked = set(fresh_game.vertices[occupied].neighbors['vertices']) | {occupied}
        clear = next(key for key in fresh_game.vertices if key not in blocked)

        assert fresh_game.place_settlement(name, clear)['success']

    def test_an_occupied_intersection_is_refused_before_the_distance_rule(self, fresh_game):
        name = acting(fresh_game)
        occupied = a_vertex(fresh_game)
        give_building(fresh_game, name, occupied)

        result = fresh_game.place_settlement(name, occupied)

        assert result['code'] == 'OCCUPIED'
        assert result['error'] == 'This location already has a building'

    def test_an_unknown_vertex_is_refused(self, fresh_game):
        result = fresh_game.place_settlement(acting(fresh_game), 'nowhere')

        assert result['code'] == 'INVALID_TARGET'
        assert result['error'] == 'Invalid vertex'


class TestBuildingInPlay:
    def test_a_settlement_needs_one_of_your_own_roads(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)

        result = playing_game.place_settlement(name, a_vertex(playing_game))

        assert result['code'] == 'INVALID_PLACEMENT'
        assert result['error'] == 'Settlement must be connected to your own road'

    def test_someone_elses_road_does_not_count(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        vertex_key = a_vertex(playing_game)
        give_road(playing_game, other_player(playing_game, name),
                  playing_game.vertices[vertex_key].neighbors['edges'][0])

        result = playing_game.place_settlement(name, vertex_key)

        assert result['code'] == 'INVALID_PLACEMENT'

    def test_a_connected_settlement_is_paid_for(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        vertex_key = a_vertex(playing_game)
        give_road(playing_game, name, playing_game.vertices[vertex_key].neighbors['edges'][0])

        assert playing_game.place_settlement(name, vertex_key)['success']

        player = playing_game.get_player(name)
        assert vertex_key in player.settlements
        # A settlement is wood, brick, sheep and wheat; the ore is untouched.
        assert player.resources == {'wood': 0, 'brick': 0, 'sheep': 0, 'wheat': 0, 'ore': 3}

    def test_an_empty_hand_cannot_build(self, playing_game):
        name = acting(playing_game)
        vertex_key = a_vertex(playing_game)
        give_road(playing_game, name, playing_game.vertices[vertex_key].neighbors['edges'][0])

        result = playing_game.place_settlement(name, vertex_key)

        assert result['code'] == 'INSUFFICIENT_RESOURCES'
        assert result['error'].startswith('Not enough resources. Need:')

    def test_the_robber_must_be_moved_first(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        playing_game.must_move_robber = True

        result = playing_game.place_settlement(name, a_vertex(playing_game))

        assert result['code'] == 'MUST_MOVE_ROBBER'


class TestRoadConnectivity:
    def test_a_road_must_touch_your_own_network(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)

        result = playing_game.build_road(name, next(iter(playing_game.edges)))

        assert result['code'] == 'INVALID_PLACEMENT'
        assert result['error'] == 'Road must be connected to your own road'

    def test_a_road_next_to_your_own_is_allowed(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        vertex_key = a_vertex(playing_game)
        first, second = playing_game.vertices[vertex_key].neighbors['edges'][:2]
        give_road(playing_game, name, first)

        assert playing_game.build_road(name, second)['success']
        assert second in playing_game.get_player(name).roads

    def test_an_opponents_road_does_not_extend_your_network(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        vertex_key = a_vertex(playing_game)
        first, second = playing_game.vertices[vertex_key].neighbors['edges'][:2]
        give_road(playing_game, other_player(playing_game, name), first)

        assert playing_game.build_road(name, second)['code'] == 'INVALID_PLACEMENT'

    def test_an_occupied_edge_is_refused(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        edge_key = next(iter(playing_game.edges))
        give_road(playing_game, name, edge_key)

        result = playing_game.build_road(name, edge_key)

        assert result['code'] == 'OCCUPIED'
        assert result['error'] == 'This location already has a road'

    def test_a_two_roads_card_pays_for_the_placement(self, playing_game):
        name = acting(playing_game)
        vertex_key = a_vertex(playing_game)
        first, second = playing_game.vertices[vertex_key].neighbors['edges'][:2]
        give_road(playing_game, name, first)
        playing_game.free_roads_remaining = 2

        result = playing_game.build_road(name, second)

        assert result['success'] and result['used_free_road']
        assert playing_game.free_roads_remaining == 1
        assert playing_game.get_player(name).resources == {}


class TestPieceSupply:
    def test_settlements_run_out(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        player = playing_game.get_player(name)
        player.settlements = [f"placed-{i}" for i in range(playing_game.MAX_SETTLEMENTS)]

        result = playing_game.place_settlement(name, a_vertex(playing_game))

        assert result['code'] == 'NO_PIECES_LEFT'
        assert result['error'] == f'You have used all {playing_game.MAX_SETTLEMENTS} settlements'

    def test_roads_run_out(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        playing_game.get_player(name).roads = [f"placed-{i}" for i in range(playing_game.MAX_ROADS)]

        result = playing_game.build_road(name, next(iter(playing_game.edges)))

        assert result['code'] == 'NO_PIECES_LEFT'
        assert result['error'] == f'You have used all {playing_game.MAX_ROADS} roads'

    def test_cities_run_out(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        vertex_key = a_vertex(playing_game)
        give_building(playing_game, name, vertex_key)
        playing_game.get_player(name).cities = [
            f"placed-{i}" for i in range(playing_game.MAX_CITIES)
        ]

        result = playing_game.upgrade_city(name, vertex_key)

        assert result['code'] == 'NO_PIECES_LEFT'
        assert result['error'] == f'You have used all {playing_game.MAX_CITIES} cities'

    def test_the_supply_is_read_from_the_house_rules(self, rng):
        from game.game import Game

        game = Game(["Alice", "Bob"], [], rng=rng, rules={'max_settlements': 1})
        game.game_phase = 'playing'
        name = game.current_player_name()
        game.get_player(name).settlements = ['placed-0']

        assert game.place_settlement(name, a_vertex(game))['code'] == 'NO_PIECES_LEFT'


class TestUpgradingToACity:
    def test_a_settlement_becomes_a_city(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        playing_game.get_player(name).resources['ore'] = 3
        playing_game.get_player(name).resources['wheat'] = 2
        vertex_key = a_vertex(playing_game)
        give_building(playing_game, name, vertex_key)

        assert playing_game.upgrade_city(name, vertex_key)['success']

        player = playing_game.get_player(name)
        assert vertex_key in player.cities and vertex_key not in player.settlements
        assert playing_game.vertices[vertex_key].building['type'] == 'city'

    def test_you_cannot_upgrade_someone_elses_settlement(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        vertex_key = a_vertex(playing_game)
        give_building(playing_game, other_player(playing_game, name), vertex_key)

        result = playing_game.upgrade_city(name, vertex_key)

        assert result['code'] == 'NOT_YOUR_PIECE'
        assert result['error'] == 'Can only upgrade your own settlements'

    def test_a_city_cannot_be_upgraded_again(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)
        vertex_key = a_vertex(playing_game)
        give_building(playing_game, name, vertex_key, 'city')

        result = playing_game.upgrade_city(name, vertex_key)

        assert result['code'] == 'INVALID_TARGET'
        assert result['error'] == 'Can only upgrade settlements to cities'

    def test_an_empty_intersection_has_nothing_to_upgrade(self, playing_game, rich):
        name = acting(playing_game)
        rich(playing_game, name)

        result = playing_game.upgrade_city(name, a_vertex(playing_game))

        assert result['code'] == 'INVALID_TARGET'
        assert result['error'] == 'No building at this location'

    def test_upgrading_during_setup_is_refused(self, fresh_game):
        name = acting(fresh_game)
        vertex_key = a_vertex(fresh_game)
        give_building(fresh_game, name, vertex_key)

        result = fresh_game.upgrade_city(name, vertex_key)

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'Cannot upgrade to city during setup phase'


class TestWinning:
    def test_claim_victory_is_silent_below_the_target(self, playing_game):
        assert playing_game.claim_victory(acting(playing_game)) is None
        assert playing_game.game_state == 'started'

    def test_reaching_the_target_finishes_the_game(self, playing_game):
        name = acting(playing_game)
        playing_game.get_player(name).victory_points = playing_game.victory_points_to_win

        assert playing_game.claim_victory(name) == playing_game.victory_points_to_win
        assert playing_game.game_state == 'finished'
