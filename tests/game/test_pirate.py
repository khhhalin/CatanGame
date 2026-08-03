"""The pirate: a robber for the sea.

It is moved instead of the robber when a 7 comes up, steals from a player with
a ship beside it, and freezes every hex side around the hex it sits on. A
player would notice any of these breaking: a pirate parked on the desert, a
steal from someone with no ships there, or a ship built straight past it.
"""

import pytest
from seafarers_board import (
    build_ships_along,
    coastal_vertex,
    give_building,
    sea_edges_at,
    seafarers_game,
    ship_path,
)


@pytest.fixture
def sea_game():
    game = seafarers_game()
    game.must_move_robber = True
    return game


def sea_hex_beside(game, edge_key):
    """The water hex this side borders."""
    return next(
        key for key in game.edges[edge_key].neighbors['hexes']
        if game.hexes[key].type == 'ocean'
    )


class TestWhereThePirateGoes:
    def test_the_pirate_starts_beside_the_board(self):
        """expansions.md 88: placed beside the board before the game begins."""
        assert seafarers_game().pirate_hex is None

    def test_the_pirate_only_sits_on_a_sea_hex(self, sea_game):
        """expansions.md 91."""
        land_hex = next(
            key for key, hex_obj in sorted(sea_game.hexes.items())
            if hex_obj.type != 'ocean'
        )
        assert sea_game.move_pirate('Alice', land_hex)['code'] == 'INVALID_TARGET'
        assert sea_game.pirate_hex is None

    def test_moving_the_pirate_answers_the_seven_the_robber_would_have(self, sea_game):
        """expansions.md 89: a 7 may move the pirate *instead of* the robber."""
        robber_was = sea_game.robber_hex
        sea_hex = next(
            key for key, hex_obj in sorted(sea_game.hexes.items())
            if hex_obj.type == 'ocean'
        )

        assert sea_game.move_pirate('Alice', sea_hex)['success']
        assert sea_game.pirate_hex == sea_hex
        assert sea_game.must_move_robber is False
        assert sea_game.robber_hex == robber_was, "the robber stayed where it was"

    def test_the_pirate_may_not_be_moved_out_of_turn(self, sea_game):
        sea_hex = next(
            key for key, hex_obj in sorted(sea_game.hexes.items())
            if hex_obj.type == 'ocean'
        )
        assert sea_game.move_pirate('Bob', sea_hex)['code'] == 'NOT_YOUR_TURN'

    def test_a_table_without_the_pirate_cannot_move_one(self):
        game = seafarers_game(pirate=False)
        game.must_move_robber = True
        sea_hex = next(
            key for key, hex_obj in sorted(game.hexes.items()) if hex_obj.type == 'ocean'
        )
        assert game.move_pirate('Alice', sea_hex)['code'] == 'RULE_NOT_IN_PLAY'


class TestStealing:
    def _bob_has_a_ship(self, game):
        vertex_key = coastal_vertex(game)
        give_building(game, 'Bob', vertex_key)
        edge_key = sea_edges_at(game, vertex_key)[0]
        build_ships_along(game, 'Bob', [edge_key])
        return edge_key

    def test_a_player_with_a_ship_beside_the_pirate_can_be_robbed(self, sea_game):
        """expansions.md 92."""
        edge_key = self._bob_has_a_ship(sea_game)
        sea_game.get_player('Bob').resources = {'ore': 1}

        result = sea_game.move_pirate('Alice', sea_hex_beside(sea_game, edge_key))
        assert result['victims'] == ['Bob']
        assert sea_game.must_choose_victim is True

        assert sea_game.steal_from_victim('Alice', 'Bob')['stolen'] == 'ore'
        assert sea_game.get_player('Alice').resources['ore'] == 1

    def test_a_player_with_two_ships_there_still_loses_only_one_card(self, sea_game):
        """expansions.md 93."""
        vertex_key = coastal_vertex(sea_game)
        give_building(sea_game, 'Bob', vertex_key)
        edges, _vertices = ship_path(sea_game, vertex_key, 2)
        build_ships_along(sea_game, 'Bob', edges)

        shared = next(
            key for key in sea_game.edges[edges[0]].neighbors['hexes']
            if key in sea_game.edges[edges[1]].neighbors['hexes']
            and sea_game.hexes[key].type == 'ocean'
        )
        assert sea_game.move_pirate('Alice', shared)['victims'] == ['Bob']

    def test_the_mover_is_never_their_own_victim(self, sea_game):
        vertex_key = coastal_vertex(sea_game)
        give_building(sea_game, 'Alice', vertex_key)
        edge_key = sea_edges_at(sea_game, vertex_key)[0]
        build_ships_along(sea_game, 'Alice', [edge_key])

        result = sea_game.move_pirate('Alice', sea_hex_beside(sea_game, edge_key))
        assert result['victims'] == []
        assert sea_game.must_choose_victim is False

    def test_a_hex_with_no_ships_beside_it_robs_nobody(self, sea_game):
        self._bob_has_a_ship(sea_game)
        empty_sea = next(
            key for key, hex_obj in sorted(sea_game.hexes.items())
            if hex_obj.type == 'ocean'
            and not any(
                edge.ship for edge in sea_game.edges.values()
                if key in edge.neighbors['hexes']
            )
        )
        assert sea_game.move_pirate('Alice', empty_sea)['victims'] == []


class TestBlocking:
    def _pirate_beside(self, game, edge_key):
        game.pirate_hex = sea_hex_beside(game, edge_key)

    def test_no_ship_may_be_built_beside_the_pirate(self, sea_game):
        """expansions.md 94."""
        vertex_key = coastal_vertex(sea_game)
        give_building(sea_game, 'Alice', vertex_key)
        edge_key = sea_edges_at(sea_game, vertex_key)[0]
        self._pirate_beside(sea_game, edge_key)
        sea_game.must_move_robber = False
        sea_game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}

        assert sea_game.build_ship('Alice', edge_key)['code'] == 'PIRATE_BLOCKS'
        assert sea_game.edges[edge_key].ship is None

    def test_no_ship_beside_the_pirate_may_sail_away(self, sea_game):
        """expansions.md 95."""
        vertex_key = coastal_vertex(sea_game)
        give_building(sea_game, 'Alice', vertex_key)
        edges, _vertices = ship_path(sea_game, vertex_key, 1)
        build_ships_along(sea_game, 'Alice', edges)
        self._pirate_beside(sea_game, edges[0])
        sea_game.must_move_robber = False

        target = next(
            key for key in sea_edges_at(sea_game, vertex_key)
            if key != edges[0] and sea_game.edges[key].ship is None
            and not sea_game.pirate_blocks_edge(key)
        )
        assert sea_game.move_ship('Alice', edges[0], target)['code'] == 'PIRATE_BLOCKS'
        assert sea_game.edges[edges[0]].ship is not None

    def test_the_pirate_does_not_stop_production(self, sea_game):
        """expansions.md 96: it blocks ships, not hexes."""
        producing = next(
            key for key, hex_obj in sorted(sea_game.hexes.items())
            if hex_obj.number is not None and key != sea_game.robber_hex
        )
        vertex_key = next(
            key for key, vertex in sorted(sea_game.vertices.items())
            if producing in vertex.neighbors['hexes']
        )
        give_building(sea_game, 'Alice', vertex_key)
        sea_game.pirate_hex = next(
            key for key, hex_obj in sorted(sea_game.hexes.items())
            if hex_obj.type == 'ocean' and key in sea_game.hexes[producing].neighbors
        )
        sea_game.get_player('Alice').resources = {}

        sea_game.distribute_resources(sea_game.hexes[producing].number)
        assert sea_game.get_player('Alice').resources.get(
            sea_game.hexes[producing].type
        ) == 1
