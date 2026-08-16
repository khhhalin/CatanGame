"""The Seafarers scenario "Through the Desert", built as a board plus a rule.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 4 "Through the Desert"
(p. 17). A belt of three deserts splits the discovered island into the main
land and a small land strip beyond the desert, and three smaller islands lie
out at sea. The strip and the three islands are the four "foreign" areas, and
"the first time you build a new settlement in each of the 'foreign' areas ...
you receive TWO special victory points ... Potentially, each player can earn up
to 8 Special Victory Points." The game is won at 14.

The one new mechanic is `desert_regions`: it generalises the island bonus so a
desert belt separates scoring regions exactly as open sea already does. So what
is worth pinning is the board the scenario ships (the belt really splitting the
island into the printed region count, three deserts, no gold field), that the
generalisation pays the strip its two points and respects the board's own cap
of eight, and — the regression that guards the other Seafarers boards — that
with the rule off nothing about sea-only island scoring changes.
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

STRIP_HEXES = {'9,-3,-6', '12,-9,-3', '12,-6,-6'}


def desert_game(players=('Alice', 'Bob', 'Cara'), seed=7, desert_regions=True):
    defn = maps.parse_map(map_store.read_map('through-the-desert'))
    chosen = dict(SEAFARING)
    if desert_regions:
        chosen['desert_regions'] = True
    return Game(list(players), [], rng=random.Random(seed),
                map_definition=defn, rules=chosen)


def land_hexes(game):
    return [key for key, hex_obj in game.hexes.items() if hex_obj.type != 'ocean']


def one_vertex_per_region(game):
    seen = {}
    for vertex_key, _ in sorted(game.vertices.items()):
        region = game.island_of_vertex(vertex_key)
        if region is not None and region not in seen:
            seen[region] = vertex_key
    return seen


class TestTheBoardAsDealt:
    """Every assertion reads the board the engine generated, so a literal that
    drifts from the file is caught where the file is consumed."""

    def test_the_desert_belt_splits_the_island_into_five_regions(self):
        """With the rule on, the belt cuts the island into the main land, the
        strip beyond it and the three outer islands — five regions of the
        printed sizes, the deserts themselves belonging to none."""
        game = desert_game()
        sizes = sorted(Counter(game.islands().values()).values())
        assert sizes == [1, 2, 2, 3, 14]

    def test_the_three_deserts_form_the_belt_and_two_gold_fields(self):
        """The component list is "Desert 3, Gold field 2": the belt is three
        deserts and the two printed gold fields sit on the small sea-islands,
        dealt as real gold-of-choice hexes (gold_field_choice)."""
        game = desert_game()
        counts = Counter(game.hexes[key].type for key in land_hexes(game))
        assert counts['desert'] == 3
        assert counts['gold'] == 2

    def test_the_terrain_is_the_three_player_component_list(self):
        """Main land + strip + islands, the two gold fields restored on the two
        southern/eastern islands: 4 ore, 4 wheat, 5 wood, 4 sheep, 3 hills, 2
        gold and the 3 deserts (25 hexes)."""
        game = desert_game()
        counts = Counter(game.hexes[key].type for key in land_hexes(game))
        assert counts == {'ore': 4, 'wheat': 4, 'wood': 5, 'sheep': 4,
                          'brick': 3, 'gold': 2, 'desert': 3}

    def test_the_number_tokens_are_the_printed_twenty_two(self):
        game = desert_game()
        tokens = sorted(
            game.hexes[key].number for key in land_hexes(game)
            if game.hexes[key].number is not None
        )
        assert tokens == [2, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6,
                          8, 8, 8, 9, 9, 9, 10, 10, 11, 11]


class TestReachingTheDesertRegions:
    """The special points, simulated on the generated board."""

    def test_each_foreign_area_pays_two_up_to_the_boards_eight(self):
        """Home is the main land; the strip and the three islands are the four
        foreign areas. A first settlement in each pays two, capped at the eight
        the board can offer, and nothing pays twice."""
        game = desert_game()
        regions = one_vertex_per_region(game)
        sizes = Counter(game.islands().values())
        home = next(region for region in regions if sizes[region] == 14)
        foreign = [region for region in regions if region != home]
        assert len(foreign) == 4

        game.game_phase = 'setup'
        game.record_island_settlement('Alice', regions[home], award=False)
        game.game_phase = 'playing'

        earned = sum(
            game.record_island_settlement('Alice', regions[region], award=True)
            for region in foreign
        )
        assert earned == 8
        assert game.island_points['Alice'] == 8

        # The home land and any already-reached area never pay again: eight is
        # the board's cap.
        assert game.record_island_settlement('Alice', regions[home], award=True) == 0
        for region in foreign:
            assert game.record_island_settlement('Alice', regions[region], award=True) == 0
        assert game.island_points['Alice'] == 8

    def test_the_strip_beyond_the_desert_is_a_region_of_its_own(self):
        """The whole point of the scenario: a vertex on the land strip is not
        the main land, so settling there after starting on the main land scores
        the new-area bonus."""
        game = desert_game()
        strip_vertex = next(
            vertex_key for vertex_key, _ in sorted(game.vertices.items())
            if set(game.vertices[vertex_key].neighbors['hexes']) & STRIP_HEXES
            and game.island_of_vertex(vertex_key) is not None
        )
        main_vertex = next(
            vertex_key for vertex_key, _ in sorted(game.vertices.items())
            if Counter(game.islands().values())[game.island_of_vertex(vertex_key)] == 14
        )
        assert game.island_of_vertex(strip_vertex) != game.island_of_vertex(main_vertex)

        game.game_phase = 'setup'
        game.record_island_settlement('Bob', main_vertex, award=False)
        game.game_phase = 'playing'
        assert game.record_island_settlement('Bob', strip_vertex, award=True) == 2


class TestSeaOnlyScoringIsUnchangedWhenOff:
    """The regression that guards every other Seafarers board: with the rule
    off, the desert belt is ordinary land again and only the sea separates
    regions, so the strip is home ground and the three sea-islands score
    exactly as they did before the generalisation existed."""

    def test_without_the_rule_the_belt_does_not_split_the_island(self):
        game = desert_game(desert_regions=False)
        # Desert is land again: main land, belt and strip are one landmass, and
        # only the three sea-islands stand apart — four regions, not five.
        sizes = sorted(Counter(game.islands().values()).values())
        assert sizes == [1, 2, 2, 20]

    def test_without_the_rule_the_strip_is_the_home_landmass(self):
        game = desert_game(desert_regions=False)
        strip_vertex = next(
            vertex_key for vertex_key, _ in sorted(game.vertices.items())
            if set(game.vertices[vertex_key].neighbors['hexes']) & STRIP_HEXES
            and game.island_of_vertex(vertex_key) is not None
        )
        main_vertex = next(
            vertex_key for vertex_key, _ in sorted(game.vertices.items())
            if Counter(game.islands().values())[game.island_of_vertex(vertex_key)] == 20
        )
        assert game.island_of_vertex(strip_vertex) == game.island_of_vertex(main_vertex)

        game.game_phase = 'setup'
        game.record_island_settlement('Cara', main_vertex, award=False)
        game.game_phase = 'playing'
        # The strip is home ground with the rule off, so it pays nothing.
        assert game.record_island_settlement('Cara', strip_vertex, award=True) == 0

    def test_the_three_sea_islands_still_pay_two_each(self):
        """Sea-only island scoring is untouched: starting on the home landmass
        leaves the three islands to reach, six points in all — the six a
        pre-generalisation Seafarers board would have paid."""
        game = desert_game(desert_regions=False)
        regions = one_vertex_per_region(game)
        sizes = Counter(game.islands().values())
        home = next(region for region in regions if sizes[region] == 20)
        islands = [region for region in regions if region != home]
        assert len(islands) == 3

        game.game_phase = 'setup'
        game.record_island_settlement('Cara', regions[home], award=False)
        game.game_phase = 'playing'
        earned = sum(
            game.record_island_settlement('Cara', regions[region], award=True)
            for region in islands
        )
        assert earned == 6


class TestThePreset:
    def test_it_plays_the_seafarers_rules_to_fourteen_with_desert_regions(self):
        """A rulebook pin: Through the Desert ends at 14 and ticks the desert
        belt on top of the island bonus, ships and the pirate."""
        chosen = rules_module.preset_rules('through_the_desert')
        assert chosen is not None
        assert chosen['victory_target'] == 14
        assert chosen['desert_regions'] is True
        assert chosen['island_victory_points'] is True
        assert chosen['gold_field_choice'] is True
        assert chosen['ships'] is True
        assert chosen['pirate'] is True
