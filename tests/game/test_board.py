"""Board generation invariants — these must hold for every seed."""

import random

from game.game import Game


def test_exactly_one_desert_and_it_has_no_number(fresh_game):
    deserts = [h for h in fresh_game.hexes.values() if h.type == 'desert']
    assert len(deserts) == 1
    assert deserts[0].number is None


def test_the_token_set_is_the_same_for_every_seed():
    """The token set is fixed: 2 and 12 once, everything else twice.

    Only placement is random; a weighted pool would vary the set per run. The
    pool used to be weighted by dice probability (five 6s, five 8s) and held 30
    tokens for 18 slots, so the dealt board ran hot and often had no 2 or 12 at
    all.
    """
    for seed in range(10):
        game = Game(["A", "B"], [], rng=random.Random(seed))
        numbers = sorted(
            h.number for h in game.hexes.values() if h.type not in ('ocean', 'desert')
        )
        assert numbers == [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12], (
            f"seed {seed} dealt {numbers}"
        )


def test_distribution_is_identical_across_seeds(fresh_game):
    """The mix is fixed; only placement is random. A 20-entry resource list
    silently dropped one tile's type, which varied per run."""
    for seed in range(10):
        game = Game(["A", "B"], [], rng=random.Random(seed))
        counts = {}
        for hex_obj in game.hexes.values():
            if hex_obj.type != 'ocean':
                counts[hex_obj.type] = counts.get(hex_obj.type, 0) + 1
        assert counts == {
            'wood': 4, 'wheat': 4, 'sheep': 4,
            'brick': 3, 'ore': 3, 'desert': 1,
        }, f"seed {seed} produced {counts}"


def test_vertices_and_edges_are_generated(fresh_game):
    assert len(fresh_game.vertices) > 0
    assert len(fresh_game.edges) > 0
    # Every edge should connect exactly two vertices that exist.
    for edge in fresh_game.edges.values():
        for vertex_key in edge.neighbors.get('vertices', []):
            assert vertex_key in fresh_game.vertices


def test_the_board_has_a_ring_of_ocean_around_the_land(fresh_game):
    """Ocean tiles must actually exist.

    `_is_ocean` classified them with the *edge* rule (exactly one coordinate
    divisible by 3) while generation only ever visits hex coordinates (all
    three divisible by 3), so no tile ever matched and the board was 19 land
    hexes floating in nothing.
    """
    ocean = [h for h in fresh_game.hexes.values() if h.type == 'ocean']
    # edge_radius 3 around a radius-2 land board: the ring at distance 3.
    assert len(ocean) == 18
    assert all(h.number is None for h in ocean)


def test_ocean_tiles_carry_no_buildable_intersections(fresh_game):
    """The ocean is scenery: every vertex still belongs to land only.

    Vertices and edges are generated from the land hexes alone, so the ocean
    ring cannot be settled on and the coastline vertices — the ones that carry
    harbours — keep their fewer-than-three-hexes signature.
    """
    ocean_keys = {k for k, h in fresh_game.hexes.items() if h.type == 'ocean'}
    for vertex in fresh_game.vertices.values():
        assert not ocean_keys.intersection(vertex.neighbors.get('hexes', []))
    # Two intersections per harbour: 9 harbours, 18 vertices carrying one.
    assert sum(1 for v in fresh_game.vertices.values() if v.port) == 18
