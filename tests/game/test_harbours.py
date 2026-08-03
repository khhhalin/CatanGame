"""Harbour geometry — a harbour is a coastal edge, not a point.

The rulebook draws each of the 9 harbour pieces on the sea frame with two
lines reaching the two intersections at the ends of one coastal hex side, and
the almanac gives control of it to a settlement "on a coastal intersection
which borders the harbour". Harbours used to hang off a single vertex picked
by its angle around the centre, which served one intersection instead of two
and did not follow the coast at all.
"""

import random

import pytest
from game.game import Game


def harbour_edges(game):
    """Every edge carrying a harbour."""
    return {key: edge.port for key, edge in game.edges.items() if edge.port}


def hexes_shared_by(game, vertex_keys):
    """The land hexes every one of these intersections touches."""
    shared = None
    for vertex_key in vertex_keys:
        touching = set(game.vertices[vertex_key].neighbors['hexes'])
        shared = touching if shared is None else shared & touching
    return shared


def test_the_split_is_four_generic_and_one_per_resource(fresh_game):
    ports = list(harbour_edges(fresh_game).values())
    generic = [p for p in ports if p['type'] == 'generic']
    specific = sorted(p['resource'] for p in ports if p['type'] == 'resource')
    assert len(generic) == 4
    assert specific == ['brick', 'ore', 'sheep', 'wheat', 'wood']


def test_a_harbour_serves_the_two_intersections_at_the_ends_of_its_edge(fresh_game):
    for edge_key, port in harbour_edges(fresh_game).items():
        ends = fresh_game.edges[edge_key].neighbors['vertices']
        assert len(ends) == 2
        for vertex_key in ends:
            assert fresh_game.vertices[vertex_key].port == port

    served = [v for v in fresh_game.vertices.values() if v.port]
    assert len(served) == 18, "9 harbours, each serving 2 intersections and no others"


def test_the_geometry_holds_for_many_seeds():
    for seed in range(25):
        game = Game(['A', 'B'], [], rng=random.Random(seed))
        harbours = harbour_edges(game)
        assert len(harbours) == 9, f"seed {seed} placed {len(harbours)} harbours"

        claimed = set()
        for edge_key, port in harbours.items():
            ends = game.edges[edge_key].neighbors['vertices']
            assert len(hexes_shared_by(game, ends)) == 1, f"seed {seed}: {edge_key} is inland"
            assert not set(ends) & claimed, f"seed {seed}: harbours share an intersection"
            claimed |= set(ends)
            for vertex_key in ends:
                assert game.vertices[vertex_key].port == port


@pytest.mark.parametrize('end', [0, 1])
def test_a_settlement_on_either_end_gets_the_harbour_rate(fresh_game, end):
    """Both intersections of the edge control the harbour, not just one."""
    for edge_key, port in harbour_edges(fresh_game).items():
        vertex_key = fresh_game.edges[edge_key].neighbors['vertices'][end]
        # Straight onto the player rather than through the setup phase: this is
        # about which intersections the harbour reaches, not about placement.
        player = fresh_game.get_player('Alice')
        player.settlements = [vertex_key]

        if port['type'] == 'generic':
            assert fresh_game.best_trade_rate('Alice', {'wood': 3}) == 3
        else:
            resource = port['resource']
            assert fresh_game.best_trade_rate('Alice', {resource: 2}) == 2


def test_a_city_on_the_far_end_also_controls_the_harbour(fresh_game):
    edge_key, port = next(iter(harbour_edges(fresh_game).items()))
    far_end = fresh_game.edges[edge_key].neighbors['vertices'][1]
    player = fresh_game.get_player('Bob')
    player.cities = [far_end]

    expected = 3 if port['type'] == 'generic' else 2
    offered = {'wood': 4} if port['type'] == 'generic' else {port['resource']: 4}
    assert fresh_game.best_trade_rate('Bob', offered) == expected


def test_the_board_payload_carries_the_harbour_on_its_edge(fresh_game):
    """The renderer still draws ports from vertices; the edge is there for it
    to move onto."""
    data = fresh_game.get_board_data('Alice')
    edges_with_ports = {k: v['port'] for k, v in data['edges'].items() if 'port' in v}
    assert edges_with_ports == harbour_edges(fresh_game)

    for edge_key, port in edges_with_ports.items():
        for vertex_key in fresh_game.edges[edge_key].neighbors['vertices']:
            assert data['vertices'][vertex_key]['port'] == port
