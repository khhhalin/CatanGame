"""An opponent's settlement blocks your road, exactly as their knight does.

A knight was taught to hold the intersection it stands on, but the base-game
rule it was modelled on had never been implemented: a road may not run through
an intersection an opponent has built on. That left the engine inconsistent —
a knight blocked a road and the settlement the rule is named after did not.
"""

import pytest


def _connected_run(game, start_vertex):
    """A vertex, an edge out of it, and the far end of that edge."""
    first = next(
        key for key in sorted(game.edges)
        if start_vertex in game.edges[key].neighbors['vertices']
    )
    middle = next(
        v for v in game.edges[first].neighbors['vertices'] if v != start_vertex
    )
    second = next(
        key for key in sorted(game.edges)
        if key != first and middle in game.edges[key].neighbors['vertices']
    )
    return first, middle, second


class TestAnOpponentsBuildingBlocksARoad:
    @pytest.fixture
    def board(self, playing_game):
        game = playing_game
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(home)
        return game, home

    def test_a_road_may_not_run_through_an_opponents_settlement(self, board):
        game, home = board
        first, middle, second = _connected_run(game, home)

        # Alice lays the near edge, then Bob settles the intersection between.
        game.edges[first].road = {'player': 'Alice'}
        game.get_player('Alice').roads.append(first)
        game.vertices[middle].building = {'type': 'settlement', 'player': 'Bob'}
        game.get_player('Bob').settlements.append(middle)

        assert not game._road_connects('Alice', second), (
            f"Alice's network ran through Bob's settlement at {middle}"
        )

    def test_your_own_settlement_does_not_block_you(self, board):
        """The block is the opponent's, not the intersection's."""
        game, home = board
        first, middle, second = _connected_run(game, home)

        game.edges[first].road = {'player': 'Alice'}
        game.get_player('Alice').roads.append(first)
        game.vertices[middle].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(middle)

        assert game._road_connects('Alice', second)

    def test_an_opponents_city_blocks_too(self, board):
        game, home = board
        first, middle, second = _connected_run(game, home)

        game.edges[first].road = {'player': 'Alice'}
        game.get_player('Alice').roads.append(first)
        game.vertices[middle].building = {'type': 'city', 'player': 'Bob'}
        game.get_player('Bob').cities.append(middle)

        assert not game._road_connects('Alice', second)
