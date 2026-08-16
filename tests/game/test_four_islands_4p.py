"""The 4-player printed board for "The Four Islands".

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 2 "The Four Islands",
"The Four Islands 4-Player Set-up" (p. 13). The 4-player game plays the same
scenario rules as the 3-player one — no home continent, two special victory
points for the first settlement on each foreign island — but on a larger
printed board: four islands of 7, 4, 8 and 4 land hexes (23 in all, against the
3-player board's 20). The token and terrain component counts read straight off
the printed set-up.

Because it is still exactly four islands, the rulebook's own cap is unchanged
from the 3-player game — "you will only be able to earn FOUR special victory
points" with two home islands, "up to SIX" with one — and it falls out of the
board rather than any numeric rule. So this file pins the board the 4-player
scenario ships (four islands of the printed sizes, no desert, no gold, the
printed terrain and token counts) and that the four-island board makes the 4/6
cap real, everything read off the board as generated rather than off a literal
copied from the file. The assertions differ from the 3-player test in every
number that the bigger board changes; nothing here restates it.
"""

import random
from collections import Counter

from game import map_store, maps
from game.game import Game

SEAFARING = {
    'ships': True,
    'ship_movement': True,
    'pirate': True,
    'longest_trade_route': True,
    'island_victory_points': True,
}


def four_islands_4p_game(players=('Alice', 'Bob', 'Cara', 'Dan'), seed=99):
    defn = maps.parse_map(map_store.read_map('four-islands-4p'))
    return Game(list(players), [], rng=random.Random(seed),
                map_definition=defn, rules=dict(SEAFARING))


def land_hexes(game):
    return [key for key, hex_obj in game.hexes.items() if hex_obj.type != 'ocean']


class TestTheBoardAsDealt:
    """Every assertion reads the board the engine generated, so a literal that
    drifts from the file is caught where the file is consumed, not where it is
    declared."""

    def test_it_deals_exactly_four_islands_of_the_printed_sizes(self):
        game = four_islands_4p_game()
        island_of = game.islands()
        sizes = sorted(Counter(island_of.values()).values())
        assert sizes == [4, 4, 7, 8]
        assert len(land_hexes(game)) == 23

    def test_no_desert_and_no_gold_field(self):
        """The rulebook's component list is "Desert 0, Gold field 0"."""
        game = four_islands_4p_game()
        kinds = {game.hexes[key].type for key in land_hexes(game)}
        assert 'desert' not in kinds
        assert not any('gold' in kind for kind in kinds)

    def test_the_terrain_is_the_four_player_component_list(self):
        """The 4-player printed board: 5 fields, 4 hills, 4 mountains, 5 pasture
        and 5 forest (23 hexes)."""
        game = four_islands_4p_game()
        counts = Counter(game.hexes[key].type for key in land_hexes(game))
        assert counts == {'wheat': 5, 'brick': 4, 'ore': 4, 'sheep': 5, 'wood': 5}

    def test_the_number_tokens_are_the_printed_twenty_three(self):
        game = four_islands_4p_game()
        tokens = sorted(game.hexes[key].number for key in land_hexes(game))
        assert tokens == [2, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 8, 8,
                          9, 9, 9, 10, 10, 10, 11, 11, 11, 12]

    def test_every_landmass_is_across_water(self):
        """No two islands touch, so a starting split really is a split: reaching
        another island always needs a ship."""
        game = four_islands_4p_game()
        island_of = game.islands()
        for key in land_hexes(game):
            for neighbour in game.hexes[key].neighbors:
                if game.hexes[neighbour].type != 'ocean':
                    assert island_of[key] == island_of[neighbour]


class TestNoHomeContinent:
    def test_the_board_names_no_main_land(self):
        """As on the 3-player board there is no home continent to force a start
        onto: every region is an island, so no hex is main land."""
        game = four_islands_4p_game()
        assert game.map_definition.hexes_of_kind('main') == set()
        assert all(not game.is_main_land(key) for key in land_hexes(game))


class TestTheForeignIslandCapIsTheBoards:
    """Four islands, so the cap is 4 with two home islands and 6 with one —
    unchanged from the 3-player board because the number of islands is what sets
    it, not the number of players. Simulated on the generated board."""

    def _one_vertex_per_island(self, game):
        seen = {}
        for vertex_key, _ in sorted(game.vertices.items()):
            island = game.island_of_vertex(vertex_key)
            if island is not None and island not in seen:
                seen[island] = vertex_key
        return seen

    def test_two_home_islands_leave_four_special_points(self):
        game = four_islands_4p_game()
        homes = self._one_vertex_per_island(game)
        island_ids = list(homes)
        assert len(island_ids) == 4

        game.game_phase = 'setup'
        for island in island_ids[:2]:
            game.record_island_settlement('Alice', homes[island], award=False)
        game.game_phase = 'playing'

        earned = sum(
            game.record_island_settlement('Alice', homes[island], award=True)
            for island in island_ids[2:]
        )
        assert earned == 4
        assert game.island_points['Alice'] == 4

    def test_one_home_island_leaves_six_special_points(self):
        game = four_islands_4p_game()
        homes = self._one_vertex_per_island(game)
        island_ids = list(homes)

        game.game_phase = 'setup'
        game.record_island_settlement('Bob', homes[island_ids[0]], award=False)
        game.game_phase = 'playing'

        earned = sum(
            game.record_island_settlement('Bob', homes[island], award=True)
            for island in island_ids[1:]
        )
        assert earned == 6
        assert game.island_points['Bob'] == 6
