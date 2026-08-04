"""Selectable maps: the random board, the printed beginner map, and the
5–6 player extension island.

Sources: the base game rulebook (19 terrain hexes, 18 number tokens, 9
harbours; Illustration A on page 3 for the beginner map) and the Catan 5–6
Player Extension rulebook (11 extra terrain hexes for 30 in all, 28 number
tokens, 11 harbours).
"""

import random
from collections import Counter

import pytest
from game import board as board_module
from game import rules as rules_module
from game.game import Game

from .test_harbours import harbour_edges, hexes_shared_by


def make_game(layout, seed=4242):
    return Game(['A', 'B'], [], rng=random.Random(seed), rules={'board_layout': layout})


def terrain_counts(game):
    return Counter(h.type for h in game.hexes.values() if h.type != 'ocean')


def tokens(game):
    return sorted(h.number for h in game.hexes.values() if h.number is not None)


class TestRegistry:
    def test_random_is_the_default(self):
        assert rules_module.defaults()['board_layout'] == 'random'
        assert Game(['A', 'B'], [], rng=random.Random(1)).board_layout is (
            board_module.LAYOUTS['random']
        )

    def test_an_unknown_map_falls_back_to_the_default(self):
        assert rules_module.coerce({'board_layout': 'atlantis'})['board_layout'] == 'random'

    def test_every_listed_map_can_be_built(self):
        """The lobby dropdown is checked against what actually builds.

        The per-layout classes below name their three maps, so they cannot
        catch a fourth added to the options list that never builds — a player
        would pick it and get no board at all. This iterates the advertised
        list, so the literal is asserted against the thing it has to match.
        """
        listed = rules_module.RULES_BY_ID['board_layout']['options']
        for option in listed:
            game = make_game(option['id'])
            assert game.hexes and game.vertices and game.edges


class TestRandomMap:
    def test_it_is_the_nineteen_hex_board(self):
        game = make_game('random')
        assert terrain_counts(game) == {
            'wood': 4, 'wheat': 4, 'sheep': 4, 'brick': 3, 'ore': 3, 'desert': 1,
        }
        assert len(harbour_edges(game)) == 9

    def test_two_seeds_give_two_different_boards(self):
        first = {k: h.type for k, h in make_game('random', seed=1).hexes.items()}
        second = {k: h.type for k, h in make_game('random', seed=2).hexes.items()}
        assert first != second


class TestBeginnerMap:
    """Illustration A, page 3: the same island every game."""

    ROWS = (
        (('ore', 10), ('sheep', 2), ('wood', 9)),
        (('wheat', 12), ('brick', 6), ('sheep', 4), ('brick', 10)),
        (('wheat', 9), ('wood', 11), ('desert', None), ('wood', 3), ('ore', 8)),
        (('wood', 8), ('ore', 3), ('wheat', 4), ('sheep', 5)),
        (('brick', 5), ('wheat', 6), ('sheep', 11)),
    )

    def test_the_island_is_the_one_in_the_rulebook(self):
        game = make_game('beginner')
        rows = {}
        for coords in board_module.LAYOUTS['beginner']['hexes']:
            hex_obj = game.hexes['{},{},{}'.format(*coords)]
            rows.setdefault(coords[2], []).append((hex_obj.type, hex_obj.number))
        assert tuple(tuple(row) for _, row in sorted(rows.items())) == self.ROWS

    def test_the_seed_makes_no_difference(self):
        first, second = make_game('beginner', seed=1), make_game('beginner', seed=99)
        assert {k: (h.type, h.number) for k, h in first.hexes.items()} == \
               {k: (h.type, h.number) for k, h in second.hexes.items()}
        assert harbour_edges(first) == harbour_edges(second)

    def test_the_robber_starts_on_the_desert_in_the_middle(self):
        game = make_game('beginner')
        assert game.robber_hex == '0,0,0'
        assert game.hexes[game.robber_hex].type == 'desert'

    def test_it_still_has_the_base_game_harbours(self):
        assert len(harbour_edges(make_game('beginner'))) == 9


class TestLargeMap:
    """The 5–6 player extension: 30 land hexes, 28 tokens, 11 harbours."""

    def test_thirty_land_hexes_from_both_boxes(self):
        assert terrain_counts(make_game('large')) == {
            'wood': 6, 'wheat': 6, 'sheep': 6, 'brick': 5, 'ore': 5, 'desert': 2,
        }

    def test_the_extension_number_tokens(self):
        """2 and 12 twice each, every other number three times — 28 in all."""
        three_of_each = [n for n in (3, 4, 5, 6, 8, 9, 10, 11) for _ in range(3)]
        expected = sorted([2, 2, 12, 12] + three_of_each)
        assert tokens(make_game('large')) == expected
        assert len(expected) == 28

    def test_eleven_harbours_with_a_second_wool_one(self):
        ports = list(harbour_edges(make_game('large')).values())
        assert len(ports) == 11
        assert sum(1 for p in ports if p['type'] == 'generic') == 5
        assert Counter(p['resource'] for p in ports if p['type'] == 'resource') == {
            'sheep': 2, 'wood': 1, 'brick': 1, 'wheat': 1, 'ore': 1,
        }

    def test_the_island_rows_run_three_to_six_and_back(self):
        rows = Counter(coords[2] for coords in board_module.LAYOUTS['large']['hexes'])
        assert [rows[row] for row in sorted(rows)] == [3, 4, 5, 6, 5, 4, 3]

    def test_the_robber_starts_on_a_desert(self):
        game = make_game('large')
        assert game.hexes[game.robber_hex].type == 'desert'

    def test_harbour_geometry_holds_on_the_bigger_coast(self):
        for seed in range(10):
            game = make_game('large', seed=seed)
            claimed = set()
            for edge_key, port in harbour_edges(game).items():
                ends = game.edges[edge_key].neighbors['vertices']
                assert len(hexes_shared_by(game, ends)) == 1, f"seed {seed}: {edge_key} is inland"
                assert not set(ends) & claimed, f"seed {seed}: harbours share an intersection"
                claimed |= set(ends)
                for vertex_key in ends:
                    assert game.vertices[vertex_key].port == port


@pytest.mark.parametrize('layout', ['random', 'beginner', 'large'])
def test_the_same_seed_builds_the_same_board(layout):
    first, second = make_game(layout, seed=555), make_game(layout, seed=555)
    assert {k: (h.type, h.number) for k, h in first.hexes.items()} == \
           {k: (h.type, h.number) for k, h in second.hexes.items()}
    assert harbour_edges(first) == harbour_edges(second)


def test_every_map_is_reproducible_across_processes():
    """Set iteration order varies between processes; the board must not.

    Same guarantee as for the standard board, checked for every layout at once
    so a new map cannot quietly depend on hash order. The seafaring board is in
    the list because it is the one that grew: the sea doubles the graph and
    islands are found by flood fill, both of which walk sets of string keys.

    The custom maps are in the same loop rather than in a test of their own,
    because they are the ones with the most to get wrong: a map file is full of
    dicts and sets — regions, pools, hex keys — and every one of them has to be
    walked in an order that does not depend on the hash seed.
    """
    import json
    import os
    import subprocess
    import sys

    script = (
        "import sys, json, random;"
        "sys.path.insert(0, 'server');"
        "from game.game import Game;"
        "from game import map_store, maps;"
        "boards = {};"
        "\n"
        "for layout in ('random', 'beginner', 'large'):\n"
        "  for ships in (False, True):\n"
        "    rules = {'board_layout': layout, 'ships': ships}\n"
        "    g = Game(['A','B'], [], rng=random.Random(99), rules=rules)\n"
        "    boards[layout + str(ships)] = {"
        "'hexes': sorted((k, h.type, h.number) for k, h in g.hexes.items()),"
        "'vertices': sorted(g.vertices),"
        "'edges': sorted(g.edges),"
        "'islands': sorted(g.islands().items()),"
        "'ports': sorted((k, str(e.port)) for k, e in g.edges.items() if e.port),"
        "'robber': g.robber_hex}\n"
        "for map_id in ('standard', 'large-island', 'little-shores'):\n"
        "  defn = maps.parse_map(map_store.read_map(map_id))\n"
        "  for ships in (False, True):\n"
        "    rules = {'board_layout': 'custom', 'board_map': map_id, 'ships': ships}\n"
        "    g = Game(['A','B'], [], rng=random.Random(99), rules=rules,"
        " map_definition=defn)\n"
        "    boards[map_id + str(ships)] = {"
        "'hexes': sorted((k, h.type, h.number) for k, h in g.hexes.items()),"
        "'vertices': sorted(g.vertices),"
        "'edges': sorted(g.edges),"
        "'islands': sorted(g.islands().items()),"
        "'ports': sorted((k, str(e.port)) for k, e in g.edges.items() if e.port),"
        "'robber': g.robber_hex}\n"
        "print(json.dumps(boards))"
    )
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    runs = []
    for hash_seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                             text=True, cwd=root, env=env, check=True)
        runs.append(json.loads(out.stdout.strip().splitlines()[-1]))

    assert runs[0] == runs[1], "the same seed must build the same board in any process"
