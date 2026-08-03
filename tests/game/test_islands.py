"""Islands, and the special victory points for reaching a new one.

An island is derived, not authored: a stretch of land the sea cuts off from the
rest of the board. The scoring rule is "each time a player builds their first
settlement on one of the small islands, that player receives two special
victory points" (expansions.md 121), so the island a player started on pays
nothing and the second settlement on the same island pays nothing either.
"""

import pytest
from seafarers_board import seafarers_game


@pytest.fixture
def sea_game():
    return seafarers_game()


def split_the_board(game):
    """Sink the middle ring, leaving the centre hex alone in the sea.

    Turns the default one-island board into a two-island one without a map
    editor, which does not exist yet. The graph is untouched — only the terrain
    changes, and an island is read off the terrain.
    """
    centre = '0,0,0'
    assert game.hexes[centre].type != 'ocean'
    for hex_key in game.hexes[centre].neighbors:
        game.hexes[hex_key].type = 'ocean'
        game.hexes[hex_key].number = None
    return centre


def vertex_on(game, hex_key):
    return next(
        key for key, vertex in sorted(game.vertices.items())
        if hex_key in vertex.neighbors['hexes']
    )


class TestWhatCountsAsAnIsland:
    def test_the_default_board_is_one_island(self, sea_game):
        """19 hexes of land, all of a piece — checked against the board that
        was generated, not against a number written down here."""
        islands = sea_game.islands()
        land = [key for key, hex_obj in sea_game.hexes.items() if hex_obj.type != 'ocean']
        assert sorted(islands) == sorted(land)
        assert len(set(islands.values())) == 1

    def test_land_the_sea_cuts_off_is_a_second_island(self, sea_game):
        centre = split_the_board(sea_game)
        islands = sea_game.islands()

        assert len({islands[key] for key in islands}) == 2
        outer = [key for key in islands if key != centre]
        assert islands[centre] != islands[outer[0]]
        assert len({islands[key] for key in outer}) == 1

    def test_an_intersection_out_at_sea_is_on_no_island(self, sea_game):
        sea_vertex = next(
            key for key, vertex in sorted(sea_game.vertices.items())
            if not vertex.neighbors['hexes']
        )
        assert sea_game.island_of_vertex(sea_vertex) is None


class TestReachingANewIsland:
    def test_a_shipping_route_can_found_a_settlement_where_it_lands(self, sea_game):
        """expansions.md 48: "When a player's shipping route reaches a
        coastline, that player may build a settlement on that coast even if it
        lies on a new island."

        The rule the whole expansion exists for. Without it a second island can
        be sailed to and never landed on, and an island map stays unplayable.
        """
        centre = split_the_board(sea_game)
        landing = vertex_on(sea_game, centre)
        sea_edge = next(
            key for key in sorted(sea_game.vertices[landing].neighbors['edges'])
            if sea_game.is_sea_edge(key)
        )
        sea_game.edges[sea_edge].ship = {'player': 'Alice', 'built_turn': 0}
        sea_game.get_player('Alice').ships.append(sea_edge)
        sea_game.get_player('Alice').resources = {
            'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1,
        }

        result = sea_game.place_settlement('Alice', landing)
        assert result['success'], result['error']
        assert sea_game.vertices[landing].building['player'] == 'Alice'

    def test_an_opponents_ship_founds_nobody_elses_settlement(self, sea_game):
        centre = split_the_board(sea_game)
        landing = vertex_on(sea_game, centre)
        sea_edge = next(
            key for key in sorted(sea_game.vertices[landing].neighbors['edges'])
            if sea_game.is_sea_edge(key)
        )
        sea_game.edges[sea_edge].ship = {'player': 'Bob', 'built_turn': 0}
        sea_game.get_player('Alice').resources = {
            'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1,
        }

        assert sea_game.place_settlement('Alice', landing)['code'] == 'INVALID_PLACEMENT'


class TestScoring:
    def _alice_started_on_the_outer_island(self, game, centre):
        outer_hex = next(
            key for key, hex_obj in sorted(game.hexes.items())
            if hex_obj.type != 'ocean' and key != centre
        )
        home = vertex_on(game, outer_hex)
        game.game_phase = 'setup'
        game.record_island_settlement('Alice', home, award=False)
        game.game_phase = 'playing'
        return home

    def test_the_island_you_started_on_pays_nothing(self, sea_game):
        centre = split_the_board(sea_game)
        home = self._alice_started_on_the_outer_island(sea_game, centre)

        assert sea_game.island_points == {}
        assert sea_game.island_of_vertex(home) in sea_game.player_islands['Alice']

    def test_the_first_settlement_on_a_new_island_scores_two(self, sea_game):
        centre = split_the_board(sea_game)
        self._alice_started_on_the_outer_island(sea_game, centre)
        landing = vertex_on(sea_game, centre)

        scored = sea_game.record_island_settlement('Alice', landing, award=True)
        assert scored == 2
        assert sea_game.island_points['Alice'] == 2
        assert sea_game.victory_points_for('Alice') == 2

    def test_a_second_settlement_on_the_same_island_scores_nothing_more(self, sea_game):
        centre = split_the_board(sea_game)
        self._alice_started_on_the_outer_island(sea_game, centre)
        first = vertex_on(sea_game, centre)
        second = next(
            key for key, vertex in sorted(sea_game.vertices.items())
            if centre in vertex.neighbors['hexes'] and key != first
        )

        sea_game.record_island_settlement('Alice', first, award=True)
        assert sea_game.record_island_settlement('Alice', second, award=True) == 0
        assert sea_game.island_points['Alice'] == 2

    def test_another_player_may_score_the_same_island(self, sea_game):
        """expansions.md 122: the points are per player, "regardless of whether
        other players have already settled that island"."""
        centre = split_the_board(sea_game)
        landing = vertex_on(sea_game, centre)

        assert sea_game.record_island_settlement('Alice', landing, award=True) == 2
        assert sea_game.record_island_settlement('Bob', landing, award=True) == 2

    def test_placing_a_settlement_scores_the_island_it_stands_on(self, sea_game):
        """Through the engine, not the bookkeeping call: a build that reaches a
        new island has to score it without the caller asking."""
        centre = split_the_board(sea_game)
        self._alice_started_on_the_outer_island(sea_game, centre)

        landing = vertex_on(sea_game, centre)
        # A ship reaching the coast is what makes this legal in a real game;
        # here the connection is a road so the test is about the scoring.
        road_key = next(
            key for key in sea_game.vertices[landing].neighbors['edges']
            if sea_game.land_hexes_of_edge(key)
        )
        sea_game.edges[road_key].road = {'player': 'Alice'}
        sea_game.get_player('Alice').resources = {
            'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1,
        }

        result = sea_game.place_settlement('Alice', landing)
        assert result['success']
        assert result['island_points'] == 2
        assert sea_game.island_points['Alice'] == 2

    def test_the_special_points_show_in_the_player_list(self, sea_game):
        """The scoreboard a browser draws comes from `players`, not from the
        engine's own total, so points that never reach it are points the owner
        cannot see they have won."""
        centre = split_the_board(sea_game)
        self._alice_started_on_the_outer_island(sea_game, centre)
        sea_game.record_island_settlement('Alice', vertex_on(sea_game, centre), award=True)

        shown = next(
            player for player in sea_game.get_board_data(viewer='Alice')['players']
            if player['name'] == 'Alice'
        )
        assert shown['victory_points'] == 2

    def test_a_table_without_the_rule_scores_no_island_points(self):
        game = seafarers_game(island_victory_points=False)
        centre = split_the_board(game)

        assert game.record_island_settlement('Alice', vertex_on(game, centre), award=True) == 0
        assert game.island_points == {}
