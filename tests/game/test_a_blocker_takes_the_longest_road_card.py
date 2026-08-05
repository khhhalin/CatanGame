"""Reported twice: "knight doesn't break enemy roads in two".

`calculate_longest_road` already refuses to walk through an opponent's knight,
and the first fix stopped there — nothing recomputed the award when a knight
appeared, moved, was displaced or deserted. So the route stayed broken in the
walk and whole on the scoreboard until somebody happened to build a road, and
the card sat with a player whose road no longer existed.

The audit that followed found the base game's own version of the same defect:
an opponent's settlement breaks a route exactly as a knight does, and placing
one recomputed nothing either.
"""

import random

import pytest
from game import cities_knights as ck
from game import rules as rules_module
from game.game import Game

RUN_LENGTH = 5


def knights_game():
    """Two players, knights and the Longest Road card, nothing placed yet."""
    rules = rules_module.preset_rules('cities_and_knights')
    return Game(['Alice', 'Bob'], [], rng=random.Random(7), rules=rules)


def _walk(game, vertex, edges, vertices):
    """A simple path of RUN_LENGTH edges out of `vertex`, or None."""
    if len(edges) == RUN_LENGTH:
        return edges, vertices
    for edge_key in sorted(game.vertices[vertex].neighbors.get('edges', [])):
        edge = game.edges.get(edge_key)
        if edge is None or edge_key in edges:
            continue
        next_vertex = next((v for v in edge.neighbors['vertices'] if v != vertex), None)
        if next_vertex is None or next_vertex in vertices or next_vertex not in game.vertices:
            continue
        found = _walk(game, next_vertex, edges + [edge_key], vertices + [next_vertex])
        if found:
            return found
    return None


def _spur(game, vertices, path_edges):
    """The middle vertex of the run, an edge off it, and where that edge leads.

    The spur is what lets Bob act at all: a knight is built and moved along its
    owner's own roads, so Bob needs one touching the intersection he wants.
    Intersections nearest the middle come first, so the knight cuts the run
    into two real halves rather than shaving an end off it.
    """
    inner = sorted(vertices[1:-1], key=lambda v: abs(vertices.index(v) - len(vertices) // 2))
    for middle in inner:
        for edge_key in sorted(game.vertices[middle].neighbors.get('edges', [])):
            if edge_key in path_edges:
                continue
            edge = game.edges.get(edge_key)
            if edge is None:
                continue
            far = next((v for v in edge.neighbors['vertices'] if v != middle), None)
            if far and far not in vertices and far in game.vertices:
                return middle, edge_key, far
    return None, None, None


@pytest.fixture
def route():
    """Alice holds the Longest Road with a straight run; Bob has a spur off it.

    Returns (game, middle, spur_end): the intersection Bob can stand a knight
    on to cut the run in two, and where that knight can step away to.
    """
    game = knights_game()
    start = next(iter(sorted(game.vertices)))
    walked = _walk(game, start, [], [start])
    if walked is None:
        pytest.skip('no straight run of five edges on this board')
    path_edges, vertices = walked
    vertices = [start] + vertices[1:] if vertices[0] != start else vertices

    alice = game.get_player('Alice')
    for edge_key in path_edges:
        game.edges[edge_key].road = {'player': 'Alice'}
        alice.roads.append(edge_key)

    middle, spur_edge, spur_end = _spur(game, vertices, path_edges)
    if middle is None:
        pytest.skip('no spur off the middle of this run')
    bob = game.get_player('Bob')
    game.edges[spur_edge].road = {'player': 'Bob'}
    bob.roads.append(spur_edge)

    game.update_longest_road()
    assert game.longest_road_holder == 'Alice'
    assert game.longest_road_length['Alice'] == RUN_LENGTH
    return game, middle, spur_end


def _pay_for_a_knight(game, player_name):
    game.get_player(player_name).resources.update({'sheep': 1, 'ore': 1})


class TestAKnightTakesTheLongestRoadCard:
    def test_building_a_knight_mid_route_takes_the_card_away(self, route):
        game, middle, _ = route
        _pay_for_a_knight(game, 'Bob')

        assert game.build_knight('Bob', middle)['success']

        assert game.calculate_longest_road('Alice') == 3
        assert game.longest_road_length['Alice'] == 3
        assert game.longest_road_holder is None

    def test_the_knight_stepping_off_gives_the_card_back(self, route):
        game, middle, spur_end = route
        _pay_for_a_knight(game, 'Bob')
        game.build_knight('Bob', middle)
        assert game.longest_road_holder is None
        _, knight = game.ck.knight_at(middle)
        knight.active = True
        game.ck.start_turn()

        assert game.move_knight('Bob', middle, spur_end)['success']

        assert game.longest_road_length['Alice'] == RUN_LENGTH
        assert game.longest_road_holder == 'Alice'

    def test_displacing_the_blocking_knight_gives_the_card_back(self, route):
        game, middle, spur_end = route
        _pay_for_a_knight(game, 'Bob')
        game.build_knight('Bob', middle)
        assert game.longest_road_holder is None

        # Alice rides a stronger knight in from the far end of her own run.
        home = next(
            v for v in sorted(game.vertices)
            if game._touches_own_road('Alice', v) and game.ck.knight_at(v)[1] is None
        )
        alice_knight = ck.Knight(home, ck.STRONG)
        alice_knight.active = True
        game.ck.knights_of('Alice').append(alice_knight)

        result = game.move_knight('Alice', home, middle)
        assert result['success'] and result['displaced'] == 'Bob'

        # Bob's knight retreated to the spur, and Alice's own knight never
        # blocked her, so the run is whole again.
        assert game.ck.knight_at(spur_end)[0] == 'Bob'
        assert game.longest_road_holder == 'Alice'

    def test_intrigue_clearing_the_knight_gives_the_card_back(self, route):
        game, middle, spur_end = route
        _pay_for_a_knight(game, 'Bob')
        game.build_knight('Bob', middle)
        assert game.longest_road_holder is None

        assert game._progress_intrigue('Alice', middle)['success']

        assert game.ck.knight_at(spur_end)[0] == 'Bob'
        assert game.longest_road_holder == 'Alice'

    def test_a_deserting_knight_gives_the_card_back(self, route):
        game, middle, _ = route
        _pay_for_a_knight(game, 'Bob')
        game.build_knight('Bob', middle)
        assert game.longest_road_holder is None

        choice = {'player': 'Bob', 'context': {'to': 'Alice'}}
        assert game._choice_deserter(choice, middle)['deserted'] == middle

        assert game.longest_road_holder == 'Alice'

    def test_the_deserters_replacement_takes_the_card_away(self, route):
        game, middle, _ = route

        choice = {'player': 'Bob', 'context': {'rank': ck.BASIC}}
        assert game._choice_deserter_placement(choice, middle)['placed'] == middle

        assert game.longest_road_length['Alice'] == 3
        assert game.longest_road_holder is None


class TestASettlementTakesTheLongestRoadCard:
    """The base game's half of the same bug, found auditing the knight paths."""

    def test_settling_mid_route_takes_the_card_away(self, route):
        game, middle, _ = route
        game.game_phase = 'playing'
        game.current_player_index = [p.name for p in game.players].index('Bob')
        game.get_player('Bob').resources.update(
            {'wood': 1, 'brick': 1, 'sheep': 1, 'wheat': 1}
        )

        assert game.place_settlement('Bob', middle)['success']

        assert game.longest_road_length['Alice'] == 3
        assert game.longest_road_holder is None
