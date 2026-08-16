"""The Seafarers scenario "The Four Islands", built as a board plus a preset.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 2 "The Four Islands"
(pp. 11-12). The scenario adds no new engine mechanic: the map has no main
land, so there is no home continent, and the existing island bonus already pays
"TWO special victory points" for a player's first settlement on each foreign
island. The rulebook's own cap falls straight out of that — "If you start the
scenario with 2 home islands, you will only be able to earn FOUR special
victory points. If you start with only 1 home island, you may earn up to SIX."
— because the board is exactly four islands and a player's foreign islands are
the ones left over.

So what is worth pinning is the board the scenario ships (four islands, no
desert, no gold, the printed terrain and token counts) and that the four-island
board makes the 4/6 cap real, both read off the board as generated rather than
off a literal copied from the file.
"""

import random
from collections import Counter

from game import map_store, maps
from game import rules as rules_module
from game.game import Game

SEAFARING = {
    'ships': True,
    'ship_movement': True,
    'pirate': True,
    'longest_trade_route': True,
    'island_victory_points': True,
}


def four_islands_game(players=('Alice', 'Bob', 'Cara'), seed=99):
    defn = maps.parse_map(map_store.read_map('four-islands'))
    return Game(list(players), [], rng=random.Random(seed),
                map_definition=defn, rules=dict(SEAFARING))


def land_hexes(game):
    return [key for key, hex_obj in game.hexes.items() if hex_obj.type != 'ocean']


class TestTheBoardAsDealt:
    """Every assertion reads the board the engine generated, so a literal that
    drifts from the file is caught where the file is consumed, not where it is
    declared."""

    def test_it_deals_exactly_four_islands_of_the_printed_sizes(self):
        game = four_islands_game()
        island_of = game.islands()
        sizes = sorted(Counter(island_of.values()).values())
        assert sizes == [4, 4, 6, 6]
        assert len(land_hexes(game)) == 20

    def test_no_desert_and_no_gold_field(self):
        """The rulebook's component list is "Desert 0, Gold field 0"."""
        game = four_islands_game()
        kinds = {game.hexes[key].type for key in land_hexes(game)}
        assert 'desert' not in kinds
        assert not any('gold' in kind for kind in kinds)

    def test_the_terrain_is_the_three_player_component_list(self):
        """4 each of fields, hills, mountains, pasture and forest (20 hexes)."""
        game = four_islands_game()
        counts = Counter(game.hexes[key].type for key in land_hexes(game))
        assert counts == {'wheat': 4, 'brick': 4, 'ore': 4, 'sheep': 4, 'wood': 4}

    def test_the_number_tokens_are_the_printed_twenty(self):
        game = four_islands_game()
        tokens = sorted(game.hexes[key].number for key in land_hexes(game))
        assert tokens == [2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
                          8, 8, 9, 9, 9, 10, 10, 11, 11, 12]

    def test_every_landmass_is_across_water(self):
        """No two islands touch, so a starting split really is a split: reaching
        another island always needs a ship."""
        game = four_islands_game()
        island_of = game.islands()
        for key in land_hexes(game):
            for neighbour in game.hexes[key].neighbors:
                if game.hexes[neighbour].type != 'ocean':
                    assert island_of[key] == island_of[neighbour]


class TestNoHomeContinent:
    def test_the_board_names_no_main_land(self):
        """There is no home continent to force a start onto: every region is an
        island, so `start_on_main_land` would have nothing to honour and the
        engine treats no hex as main land."""
        game = four_islands_game()
        assert game.map_definition.hexes_of_kind('main') == set()
        assert all(not game.is_main_land(key) for key in land_hexes(game))


class TestTheForeignIslandCapIsTheBoards:
    """The 4/6 cap is not a rule; it is what four islands leave once a player's
    home islands are taken out. Simulated on the generated board."""

    def _one_vertex_per_island(self, game):
        seen = {}
        for vertex_key, _ in sorted(game.vertices.items()):
            island = game.island_of_vertex(vertex_key)
            if island is not None and island not in seen:
                seen[island] = vertex_key
        return seen

    def test_two_home_islands_leave_four_special_points(self):
        game = four_islands_game()
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
        # Nothing further to reach: the two home islands never pay.
        for island in island_ids[:2]:
            assert game.record_island_settlement('Alice', homes[island], award=True) == 0
        assert game.island_points['Alice'] == 4

    def test_one_home_island_leaves_six_special_points(self):
        game = four_islands_game()
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


class TestThePreset:
    def test_it_plays_the_seafarers_rules_to_the_scenarios_thirteen(self):
        """A rulebook pin: The Four Islands ends at 13, not the 14 the base
        Seafarers preset suggests, and it keeps the island bonus and the
        pirate that make it the scenario it is."""
        chosen = rules_module.preset_rules('four_islands')
        assert chosen is not None
        assert chosen['victory_target'] == 13
        assert chosen['island_victory_points'] is True
        assert chosen['ships'] is True
        assert chosen['pirate'] is True
