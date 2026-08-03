"""Board generation invariants — these must hold for every seed."""

import random

from game.game import Game


def test_board_has_nineteen_land_hexes(fresh_game):
    land = [h for h in fresh_game.hexes.values() if h.type != 'ocean']
    assert len(land) == 19


def test_exactly_one_desert_and_it_has_no_number(fresh_game):
    deserts = [h for h in fresh_game.hexes.values() if h.type == 'desert']
    assert len(deserts) == 1
    assert deserts[0].number is None


def test_every_land_hex_except_desert_has_a_legal_number(fresh_game):
    for hex_obj in fresh_game.hexes.values():
        if hex_obj.type in ('ocean', 'desert'):
            continue
        assert hex_obj.number is not None
        assert 2 <= hex_obj.number <= 12
        assert hex_obj.number != 7, "7 is the robber roll and never sits on a hex"


def test_resource_hex_distribution_matches_standard_catan(fresh_game):
    counts = {}
    for hex_obj in fresh_game.hexes.values():
        if hex_obj.type != 'ocean':
            counts[hex_obj.type] = counts.get(hex_obj.type, 0) + 1
    assert counts == {
        'wood': 4, 'wheat': 4, 'sheep': 4,
        'brick': 3, 'ore': 3, 'desert': 1,
    }


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


def test_board_generation_holds_for_many_seeds():
    """The distribution is fixed, so a bad seed would show up as a wrong count."""
    for seed in range(25):
        game = Game(["A", "B"], [], rng=random.Random(seed))
        land = [h for h in game.hexes.values() if h.type != 'ocean']
        assert len(land) == 19, f"seed {seed} produced {len(land)} land hexes"
        numbers = [h.number for h in land if h.type != 'desert']
        assert 7 not in numbers, f"seed {seed} placed a 7"
        assert all(n is not None for n in numbers), f"seed {seed} left a hex unnumbered"


def test_same_seed_produces_the_same_board():
    """Determinism is what makes every other test reproducible."""
    first = Game(["A", "B"], [], rng=random.Random(999))
    second = Game(["A", "B"], [], rng=random.Random(999))
    assert {k: (h.type, h.number) for k, h in first.hexes.items()} == \
           {k: (h.type, h.number) for k, h in second.hexes.items()}


def test_vertices_and_edges_are_generated(fresh_game):
    assert len(fresh_game.vertices) > 0
    assert len(fresh_game.edges) > 0
    # Every edge should connect exactly two vertices that exist.
    for edge in fresh_game.edges.values():
        for vertex_key in edge.neighbors.get('vertices', []):
            assert vertex_key in fresh_game.vertices


def test_the_whole_board_is_reproducible_across_processes():
    """Hexes, vertices, edges and ports must all come back identical.

    Board generation iterates sets of string keys; set order varies between
    processes, so without sorting, the same seed produced different vertex
    ordering and different port placement on every run — which showed up as a
    test that passed four times in five.
    """
    import json
    import os
    import subprocess
    import sys

    script = (
        "import sys, json, random;"
        "sys.path.insert(0, 'server');"
        "from game.game import Game;"
        "g = Game(['A','B'], [], rng=random.Random(99));"
        "print(json.dumps({"
        "'hexes': sorted((k, h.type, h.number) for k, h in g.hexes.items()),"
        "'vertices': sorted(g.vertices),"
        "'edges': sorted(g.edges),"
        "'ports': sorted((k, str(v.port)) for k, v in g.vertices.items() if v.port),"
        "}))"
    )
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    runs = []
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                             text=True, cwd=root, env=env, check=True)
        # Board generation still prints progress, so take the last line.
        runs.append(json.loads(out.stdout.strip().splitlines()[-1]))

    assert runs[0] == runs[1], "the same seed must build the same board in any process"


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
    assert sum(1 for v in fresh_game.vertices.values() if v.port) == 9
