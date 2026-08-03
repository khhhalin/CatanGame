"""The Longest Trade Route: roads and ships counted as one line.

The card is the base game's Longest Road under new terms — same two points,
same minimum of five, same breaking — so what is tested here is only what
changed: ships count, and a road and a shipping route are one route only where
their owner has a building at the intersection they meet on.
"""

import pytest
from seafarers_board import (
    build_ships_along,
    coastal_vertex,
    give_building,
    inland_edges_at,
    other_end,
    seafarers_game,
    ship_path,
)


@pytest.fixture
def sea_game():
    return seafarers_game()


def road_path(game, start_vertex, length):
    """A run of inland sides leaving this intersection, end to end."""
    def walk(vertex_key, edges, vertices):
        if len(edges) == length:
            return edges, vertices
        for edge_key in inland_edges_at(game, vertex_key):
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
    assert found, f'no run of {length} inland sides from {start_vertex}'
    return found


def build_roads_along(game, player_name, edges):
    player = game.get_player(player_name)
    for edge_key in edges:
        game.edges[edge_key].road = {'player': player_name}
        player.roads.append(edge_key)


class TestShipsCount:
    def test_a_line_of_ships_is_a_trade_route(self, sea_game):
        """expansions.md 79: both roads and ships count toward the length."""
        start = coastal_vertex(sea_game)
        edges, _vertices = ship_path(sea_game, start, 4)
        build_ships_along(sea_game, 'Alice', edges)

        assert sea_game.calculate_longest_road('Alice') == 4

    def test_ships_do_not_count_when_the_table_plays_the_roads_only_card(self):
        """The base-game card is about roads, and a table that did not take
        the Seafarers rule keeps it that way."""
        game = seafarers_game(longest_trade_route=False)
        start = coastal_vertex(game)
        edges, _vertices = ship_path(game, start, 4)
        build_ships_along(game, 'Alice', edges)

        assert game.calculate_longest_road('Alice') == 0

    def test_five_ships_claim_the_card(self, sea_game):
        """expansions.md 84: the minimum of five segments still applies."""
        start = coastal_vertex(sea_game)
        edges, _vertices = ship_path(sea_game, start, 5)
        build_ships_along(sea_game, 'Alice', edges)
        sea_game.update_longest_road()

        assert sea_game.longest_road_holder == 'Alice'
        assert sea_game.victory_points_for('Alice') == 2

    def test_four_ships_are_one_short(self, sea_game):
        start = coastal_vertex(sea_game)
        edges, _vertices = ship_path(sea_game, start, 4)
        build_ships_along(sea_game, 'Alice', edges)
        sea_game.update_longest_road()

        assert sea_game.longest_road_holder is None


class TestWhereRoadsAndShipsJoin:
    def _road_and_ships_meeting_at(self, game, roads=2, ships=2):
        """A run of roads and a run of ships that meet at one intersection."""
        junction = coastal_vertex(game, with_inland_edge=True)
        road_edges, _road_vertices = road_path(game, junction, roads)
        ship_edges, _ship_vertices = ship_path(game, junction, ships)
        build_roads_along(game, 'Alice', road_edges)
        build_ships_along(game, 'Alice', ship_edges)
        return junction, road_edges, ship_edges

    def test_they_are_two_routes_without_a_settlement_between_them(self, sea_game):
        """expansions.md 81: they count as one route only where the player has
        a settlement or city at the intersection where the two meet."""
        self._road_and_ships_meeting_at(sea_game, roads=2, ships=2)

        assert sea_game.calculate_longest_road('Alice') == 2

    def test_a_settlement_at_the_junction_joins_them(self, sea_game):
        junction, _roads, _ships = self._road_and_ships_meeting_at(
            sea_game, roads=2, ships=2
        )
        give_building(sea_game, 'Alice', junction)

        assert sea_game.calculate_longest_road('Alice') == 4

    def test_an_opponents_settlement_at_the_junction_does_not(self, sea_game):
        junction, _roads, _ships = self._road_and_ships_meeting_at(
            sea_game, roads=2, ships=2
        )
        give_building(sea_game, 'Bob', junction)

        assert sea_game.calculate_longest_road('Alice') == 2


class TestTheCardItself:
    def test_the_longest_trade_route_is_awarded_without_the_base_game_card(self):
        """Seafarers replaces the Longest Road rather than joining it, so a
        table that unticked the old card still gets the new one."""
        game = seafarers_game(longest_road_card=False)
        start = coastal_vertex(game)
        edges, _vertices = ship_path(game, start, 5)
        build_ships_along(game, 'Alice', edges)
        game.update_longest_road()

        assert game.longest_road_holder == 'Alice'

    def test_drawing_level_does_not_take_the_card_off_its_holder(self, sea_game):
        """expansions.md 84: "all other Longest Road rules from basic Catan
        apply", and those leave the card with whoever holds it when an opponent
        only matches them.

        Bob earns it at sea; Alice then matches him by land. She sits ahead of
        him in the turn order, which is what used to hand her the two points.
        """
        junction = coastal_vertex(sea_game, with_inland_edge=True)
        ship_edges, _ship_vertices = ship_path(sea_game, junction, 5)
        build_ships_along(sea_game, 'Bob', ship_edges)
        sea_game.update_longest_road()
        assert sea_game.longest_road_holder == 'Bob'

        road_edges, _road_vertices = road_path(sea_game, junction, 5)
        build_roads_along(sea_game, 'Alice', road_edges)
        sea_game.update_longest_road()

        assert sea_game.longest_road_length == {'Alice': 5, 'Bob': 5}
        assert sea_game.longest_road_holder == 'Bob'

    def test_moving_a_ship_keeps_a_route_that_is_still_as_long(self, sea_game):
        """expansions.md 83. The move here swaps the last ship for another side
        leaving the same intersection, so the route never shortens."""
        start = coastal_vertex(sea_game)
        give_building(sea_game, 'Alice', start)
        edges, vertices = ship_path(sea_game, start, 5)
        build_ships_along(sea_game, 'Alice', edges)
        sea_game.update_longest_road()
        assert sea_game.longest_road_holder == 'Alice'

        end = vertices[-2]
        target = next(
            key for key in sea_game.vertices[end].neighbors['edges']
            if sea_game.is_sea_edge(key) and sea_game.edges[key].ship is None
        )
        assert sea_game.move_ship('Alice', edges[-1], target)['success']
        assert sea_game.longest_road_holder == 'Alice'
        assert sea_game.longest_road_length['Alice'] == 5
