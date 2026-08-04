"""Shared setup for the Seafarers tests.

Nothing here asserts anything; it builds a game with the sea in play and finds
positions on it. The positions are searched for rather than written down,
because a hardcoded coastal vertex is a copy of the board that would go on
passing after the board changed underneath it.
"""

import random

from game.game import Game

# Seats in the order given, so a test knows whose turn it is.
BASE_RULES = {
    'ships': True,
    'ship_movement': True,
    'pirate': True,
    'longest_trade_route': True,
    'island_victory_points': True,
    'turn_order': 'lobby',
}


def seafarers_game(players=('Alice', 'Bob'), seed=12345, **rules):
    """A game past setup, with the sea generated and the rules under test on."""
    chosen = dict(BASE_RULES)
    chosen.update(rules)
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen)
    game.start()
    game.game_phase = 'playing'
    game.start_turn()
    return game


def give_building(game, player_name, vertex_key, building_type='settlement'):
    """Stand a building at an intersection without playing a turn for it.

    The ship rules are what these tests are about, and driving the engine
    through a settlement mid-game would need roads, resources and turns that
    say nothing about ships.
    """
    game.vertices[vertex_key].building = {'type': building_type, 'player': player_name}
    player = game.get_player(player_name)
    if building_type == 'city':
        player.cities.append(vertex_key)
    else:
        player.settlements.append(vertex_key)
    return vertex_key


def sea_edges_at(game, vertex_key):
    """The sides a ship could lie on that meet this intersection."""
    return [
        edge_key
        for edge_key in sorted(game.vertices[vertex_key].neighbors['edges'])
        if game.is_sea_edge(edge_key)
    ]


def inland_edges_at(game, vertex_key):
    """The sides with land on both hands that meet this intersection."""
    return [
        edge_key
        for edge_key in sorted(game.vertices[vertex_key].neighbors['edges'])
        if len(game.land_hexes_of_edge(edge_key)) == 2
    ]


def coastal_vertex(game, with_inland_edge=False):
    """An intersection on land with a sea side leaving it.

    `with_inland_edge` asks for one that also has a side running inland, which
    is what a test about roads meeting ships needs — a corner sticking out into
    the sea has no such side.
    """
    for vertex_key in sorted(game.vertices):
        vertex = game.vertices[vertex_key]
        if not vertex.neighbors['hexes'] or not sea_edges_at(game, vertex_key):
            continue
        if with_inland_edge and not inland_edges_at(game, vertex_key):
            continue
        return vertex_key
    raise AssertionError('no coastal intersection on this board')


def inland_edge(game):
    """A side with land on both hands — where a ship may never go."""
    for edge_key in sorted(game.edges):
        if len(game.land_hexes_of_edge(edge_key)) == 2:
            return edge_key
    raise AssertionError('no inland side on this board')


def other_end(game, edge_key, vertex_key):
    ends = game.edges[edge_key].neighbors['vertices']
    return ends[1] if ends[0] == vertex_key else ends[0]


def ship_path(game, start_vertex, length):
    """A run of `length` sea sides leaving this intersection, end to end.

    Returned as (edges, vertices) with one more vertex than edge, so a test can
    say where the route reaches as well as what it lies on.
    """
    def walk(vertex_key, edges, vertices):
        if len(edges) == length:
            return edges, vertices
        for edge_key in sea_edges_at(game, vertex_key):
            if edge_key in edges:
                continue
            ahead = other_end(game, edge_key, vertex_key)
            if ahead in vertices:
                continue
            found = walk(ahead, edges + [edge_key], vertices + [ahead])
            if found:
                return found
        return None

    found = walk(start_vertex, [], [start_vertex])
    assert found, f'no run of {length} sea sides from {start_vertex}'
    return found


def sea_ring(game):
    """The board's circular run of sea sides, as (edges, vertices).

    Found by stripping dead ends off the sea-side graph until only the loop is
    left, rather than written down: which sides form it depends on where the
    land ended up, and a hardcoded ring would be a copy of one board.
    """
    sides = {
        edge_key: set(game.edges[edge_key].neighbors['vertices'])
        for edge_key in sorted(game.edges)
        if game.is_sea_edge(edge_key)
    }

    pruned = True
    while pruned:
        pruned = False
        ends = {}
        for edge_key, vertices in sides.items():
            for vertex_key in vertices:
                ends.setdefault(vertex_key, []).append(edge_key)
        for edge_keys in ends.values():
            if len(edge_keys) == 1 and edge_keys[0] in sides:
                del sides[edge_keys[0]]
                pruned = True

    assert sides, 'no circular run of sea sides on this board'
    vertices = sorted({key for ends in sides.values() for key in ends})
    return sorted(sides), vertices


def build_ships_along(game, player_name, edges):
    """Put this player's ships on these sides, bypassing cost and turn order."""
    player = game.get_player(player_name)
    for edge_key in edges:
        game.edges[edge_key].ship = {'player': player_name, 'built_turn': -1}
        player.ships.append(edge_key)
    return edges
