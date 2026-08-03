"""The sea half of the board graph, and the harbours it must not disturb.

Ships need hex sides out on the water, which is why the graph is generated
from the sea as well as the land once the rule is on. That change had to leave
two things alone: a settlement still belongs on land, and the harbours still
follow the coastline. Both are checked here against a board with the sea in
it, because the base-game tests only ever see a board without one.
"""

import random

from game.game import Game

SEAFARING = {'ships': True, 'turn_order': 'lobby'}


def game_with(rules, seed=12345, layout='random'):
    chosen = dict(rules)
    chosen['board_layout'] = layout
    return Game(['Alice', 'Bob'], [], rng=random.Random(seed), rules=chosen)


def harbours(game):
    return {key: edge.port for key, edge in game.edges.items() if edge.port}


class TestHarboursSurviveTheSea:
    """The coastline is found by counting land, not by counting hexes."""

    def test_the_same_seed_puts_the_same_harbours_on_the_same_sides(self):
        """Proof the sea did not move a single harbour.

        A coastal side used to be recognisable as the only kind with one hex;
        with the sea generated it has two, one of them water. Had the signature
        not been rewritten to count land hexes, the harbours would have spread
        out over the open water and this would differ.
        """
        for seed in range(10):
            landlocked = game_with({'turn_order': 'lobby'}, seed=seed)
            seafaring = game_with(SEAFARING, seed=seed)
            assert harbours(seafaring) == harbours(landlocked), f"seed {seed}"

    def test_nine_harbours_on_the_default_board_and_eleven_on_the_large_one(self):
        assert len(harbours(game_with(SEAFARING))) == 9
        assert len(harbours(game_with(SEAFARING, layout='large'))) == 11

    def test_no_two_harbours_share_an_intersection(self):
        game = game_with(SEAFARING)
        claimed = set()
        for edge_key in harbours(game):
            ends = set(game.edges[edge_key].neighbors['vertices'])
            assert not ends & claimed, f"{edge_key} shares an intersection"
            claimed |= ends

    def test_every_harbour_still_sits_where_land_meets_sea(self):
        game = game_with(SEAFARING)
        for edge_key in harbours(game):
            assert game.is_coastal_edge(edge_key)
            assert len(game.land_hexes_of_edge(edge_key)) == 1


class TestWhatTheSeaAdds:
    def test_the_sea_only_appears_when_ships_are_in_play(self):
        landlocked = game_with({})
        seafaring = game_with(SEAFARING)
        assert not any(landlocked.is_sea_edge(key) for key in landlocked.edges)
        assert len(seafaring.edges) > len(landlocked.edges)
        assert set(landlocked.edges) <= set(seafaring.edges), (
            "the land sides keep their keys; the sea is added, not renumbered"
        )

    def test_a_sea_side_separates_two_hexes_and_at_most_one_of_them_is_land(self):
        game = game_with(SEAFARING)
        sea_edges = [key for key in game.edges if game.is_sea_edge(key)]
        assert sea_edges
        for key in sea_edges:
            assert len(game.edges[key].neighbors['hexes']) == 2
            assert len(game.land_hexes_of_edge(key)) <= 1

    def test_the_outer_frame_carries_no_ships(self):
        """"Never on the outer edges of the frame" — those sides have one hex."""
        game = game_with(SEAFARING)
        outer = [key for key, edge in game.edges.items()
                 if len(edge.neighbors['hexes']) == 1]
        assert outer, "the sea ring has an outside"
        for key in outer:
            assert not game.is_sea_edge(key)

    def test_an_intersection_out_at_sea_touches_no_land_hex(self):
        game = game_with(SEAFARING)
        open_water = [key for key, vertex in game.vertices.items()
                      if not vertex.neighbors['hexes']]
        assert open_water, "open water has intersections for a route to turn on"

    def test_the_board_payload_carries_the_ships_and_the_pirate(self):
        game = game_with(SEAFARING)
        data = game.get_board_data('Alice')
        assert data['pirate_hex'] is None, "the pirate starts beside the board"
        assert all('ship' in edge for edge in data['edges'].values())


class TestDeterminism:
    def test_two_boards_from_one_seed_are_identical(self):
        """Board generation walks a bigger graph now; it must still replay."""
        first = game_with(SEAFARING, seed=99)
        second = game_with(SEAFARING, seed=99)
        assert sorted(first.edges) == sorted(second.edges)
        assert harbours(first) == harbours(second)
        assert (
            {key: hex_obj.type for key, hex_obj in first.hexes.items()}
            == {key: hex_obj.type for key, hex_obj in second.hexes.items()}
        )
