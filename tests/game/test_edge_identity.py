"""One hex side, one Edge.

Hex centres sit 3 apart in this cube-coordinate system, so a shared side has no
lattice midpoint and each of the two hexes it separates used to name the side
from its own centre. The board then held two Edge objects for the same physical
path — 114 objects for 72 paths on the base map — and two roads could stand on
one strip of land, one on each name.
"""

import random

import pytest

from game.game import Game


def physical_paths(game) -> dict:
    """Edge keys grouped by the pair of intersections they run between."""
    paths = {}
    for key, edge in game.edges.items():
        paths.setdefault(tuple(sorted(edge.neighbors['vertices'])), []).append(key)
    return paths


def a_shared_path(game) -> tuple:
    """An inland path — one that both of its hexes can name — and its ends.

    Returns (edge_key, near_vertex, far_vertex). Inland rather than coastal
    because the inland ones are the paths that used to be duplicated. Read off
    the intersections rather than off `edge.neighbors['hexes']`, so that this
    finds the same path whether or not the board still holds twins.
    """
    for key, edge in sorted(game.edges.items()):
        near, far = edge.neighbors['vertices']
        shared = set(game.vertices[near].neighbors['hexes']).intersection(
            game.vertices[far].neighbors['hexes']
        )
        if len(shared) == 2:
            return key, near, far
    raise AssertionError("board has no inland path")


def give_settlement(game, player_name, vertex_key):
    game.vertices[vertex_key].building = {'type': 'settlement', 'player': player_name}
    game.get_player(player_name).settlements.append(vertex_key)


class TestOneEdgePerPath:
    def test_the_board_holds_one_edge_per_physical_path(self, fresh_game):
        assert len(fresh_game.edges) == len(physical_paths(fresh_game))

    def test_no_two_edges_run_between_the_same_pair_of_intersections(self, fresh_game):
        duplicated = {ends: keys for ends, keys in physical_paths(fresh_game).items()
                      if len(keys) > 1}
        assert not duplicated

    @pytest.mark.parametrize('layout', ['random', 'beginner', 'large'])
    def test_every_layout_holds_one_edge_per_path(self, layout):
        game = Game(['A', 'B'], [], rng=random.Random(7),
                    rules={'board_layout': layout})
        assert len(game.edges) == len(physical_paths(game))

    def test_the_base_board_has_seventy_two_paths(self, fresh_game):
        """19 hexes of 6 sides with the 42 inland ones shared: 114 - 42 = 72."""
        assert len(fresh_game.edges) == 72

    def test_an_intersection_meets_exactly_three_paths(self, fresh_game):
        for key, vertex in fresh_game.vertices.items():
            assert len(vertex.neighbors['edges']) == 3, key

    def test_a_path_runs_between_exactly_two_intersections(self, fresh_game):
        for key, edge in fresh_game.edges.items():
            assert len(edge.neighbors['vertices']) == 2, key

    def test_a_path_separates_one_or_two_land_hexes(self, fresh_game):
        """Two inland, one on the coast — which is what makes an edge able to
        say for itself whether it is coastal."""
        counts = sorted(len(e.neighbors['hexes']) for e in fresh_game.edges.values())
        assert counts[0] == 1 and counts[-1] == 2
        assert sum(1 for e in fresh_game.edges.values() if len(e.neighbors['hexes']) == 1) == 30


class TestOneRoadPerPath:
    def test_a_second_player_cannot_road_over_the_first_players_road(
        self, playing_game, give
    ):
        """The headline symptom: with two names for one strip of land, two
        players each built a road on it, one under each name."""
        edge_key, near, far = a_shared_path(playing_game)
        first, second = (player.name for player in playing_game.players[:2])
        give_settlement(playing_game, second, far)
        playing_game.edges[edge_key].road = {'player': first}
        playing_game.get_player(first).roads.append(edge_key)

        give(playing_game, second, wood=5, brick=5)
        playing_game.current_player_index = next(
            index for index, p in enumerate(playing_game.players) if p.name == second
        )
        playing_game.has_rolled_dice = True

        for key in list(playing_game.edges):
            if playing_game.edges[key].neighbors['vertices'] in ([near, far], [far, near]):
                result = playing_game.build_road(second, key)
                assert not result['success'], f"{key} is the same strip of land as {edge_key}"

    def test_a_player_cannot_road_the_same_path_twice(self, playing_game, give):
        edge_key, near, _far = a_shared_path(playing_game)
        name = playing_game.current_player_name()
        give_settlement(playing_game, name, near)
        give(playing_game, name, wood=5, brick=5)
        playing_game.has_rolled_dice = True

        assert playing_game.build_road(name, edge_key)['success']
        assert len(playing_game.get_player(name).roads) == 1
        for key in list(playing_game.edges):
            if key == edge_key:
                continue
            if set(playing_game.edges[key].neighbors['vertices']) == set(
                playing_game.edges[edge_key].neighbors['vertices']
            ):
                assert not playing_game.build_road(name, key)['success']


class TestLongestRoadCountsPhysicalPaths:
    def test_a_chain_of_inland_roads_is_as_long_as_it_looks(self, playing_game, give):
        """Roads laid end to end must count once each. While a path answered to
        two names a player could build on both, and the walk counted the same
        strip of land twice."""
        name = playing_game.current_player_name()
        give(playing_game, name, wood=20, brick=20)
        playing_game.has_rolled_dice = True

        start = next(
            key for key, vertex in sorted(playing_game.vertices.items())
            if len(vertex.neighbors['hexes']) == 3
        )
        give_settlement(playing_game, name, start)

        # Walk outwards, never revisiting an intersection, so the chain is a
        # simple path and its length is exactly the number of roads built.
        walked = {start}
        current = start
        built = 0
        while built < 4:
            edge_key = next(
                key for key in playing_game.vertices[current].neighbors['edges']
                if playing_game.edges[key].road is None
                and all(v not in walked
                        for v in playing_game.edges[key].neighbors['vertices']
                        if v != current)
            )
            assert playing_game.build_road(name, edge_key)['success']
            built += 1
            current = next(
                v for v in playing_game.edges[edge_key].neighbors['vertices'] if v != current
            )
            walked.add(current)

            # Every other name for a path already built on must be refused.
            for key, edge in playing_game.edges.items():
                if key == edge_key:
                    continue
                if set(edge.neighbors['vertices']) == set(
                    playing_game.edges[edge_key].neighbors['vertices']
                ):
                    assert not playing_game.build_road(name, key)['success']

        assert playing_game.calculate_longest_road(name) == 4
