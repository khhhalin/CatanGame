"""Catan: Oil Springs — oil production off the oil-spring hexes.

Chunk 1: the sixth commodity. The board carries three Oil Spring tiles; a
building on one produces oil on the hex's number, capped at four held, drawn
from a supply of fifteen. Later chunks add the disaster track, sequestering and
metropolises.

Source: coilspringsgb_2015_web.pdf, 3-4 player rules p. 1.
"""

import random

from game import map_store, maps, persistence
from game import rules as rules_module
from game.game import Game


def oil_game(players=('Alice', 'Bob'), seed=12345, **overrides):
    """A playing game on the Oil Springs board with the oil rule on."""
    defn = maps.parse_map(map_store.read_map('oil-springs'))
    chosen = dict(rules_module.preset_rules('oil_springs'))
    chosen['turn_order'] = 'lobby'
    chosen.update(overrides)
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.start_turn()
    return game


class TestBoardDeal:
    def test_the_board_carries_exactly_three_oil_springs(self):
        """The scenario prints three Oil Spring tiles: the desert, a forest hex
        and a pasture hex (p. 1 set-up). Asserted against the generated board,
        not the map literal."""
        game = oil_game()
        springs = {key for key, hex_obj in game.hexes.items()
                   if getattr(hex_obj.meta, 'oil_spring', False)}
        assert springs == game.oil_spring_hexes
        assert len(springs) == 3
        kinds = sorted(game.hexes[key].type for key in springs)
        assert kinds == ['desert', 'sheep', 'wood']

    def test_the_forest_and_pasture_springs_carry_a_nine_and_a_ten(self):
        """The two producing springs sit on a 9 forest and a 10 pasture (p. 1)."""
        game = oil_game()
        by_type = {game.hexes[key].type: game.hexes[key].number
                   for key in game.oil_spring_hexes}
        assert by_type['wood'] == 9
        assert by_type['sheep'] == 10
        assert by_type['desert'] is None

    def test_the_producing_hexes_carry_the_eighteen_base_tokens(self):
        """A base-game board underneath: the 18 number tokens are unchanged."""
        game = oil_game()
        tokens = sorted(hex_obj.number for hex_obj in game.hexes.values()
                        if hex_obj.type not in ('ocean', 'desert'))
        assert tokens == [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]


class TestProduction:
    def _settle(self, game, spring_key, player_name, btype='settlement'):
        """Put a building of `player_name` on a corner of the given spring."""
        vertex_key = game._oil_spring_vertices(spring_key)[0]
        game.vertices[vertex_key].building = {'type': btype, 'player': player_name}
        return vertex_key

    def _wood_spring(self, game):
        return next(k for k in game.oil_spring_hexes if game.hexes[k].type == 'wood')

    def test_a_settlement_on_an_oil_spring_produces_one_oil_on_its_number(self):
        game = oil_game()
        spring = self._wood_spring(game)  # a 9
        self._settle(game, spring, 'Alice')
        produced = game.distribute_oil(9, 'Alice')
        assert produced == {'Alice': 1}
        assert game.get_player('Alice').oil == 1
        assert game.oil_supply == 15 - 1

    def test_a_city_on_an_oil_spring_produces_two_oil(self):
        game = oil_game()
        spring = self._wood_spring(game)
        self._settle(game, spring, 'Alice', btype='city')
        produced = game.distribute_oil(9, 'Alice')
        assert produced == {'Alice': 2}
        assert game.get_player('Alice').oil == 2

    def test_no_oil_is_produced_when_the_number_is_not_rolled(self):
        game = oil_game()
        spring = self._wood_spring(game)  # a 9
        self._settle(game, spring, 'Alice')
        assert game.distribute_oil(6, 'Alice') == {}
        assert game.get_player('Alice').oil == 0

    def test_no_oil_is_produced_on_a_seven(self):
        game = oil_game()
        spring = self._wood_spring(game)
        self._settle(game, spring, 'Alice')
        assert game.distribute_oil(7, 'Alice') == {}

    def test_a_player_never_holds_more_than_four_oil(self):
        """The hold cap is 4; oil produced beyond it is not taken (p. 1)."""
        game = oil_game()
        spring = self._wood_spring(game)
        self._settle(game, spring, 'Alice', btype='city')  # 2 per roll
        game.get_player('Alice').oil = 3
        produced = game.distribute_oil(9, 'Alice')
        assert produced == {'Alice': 1}
        assert game.get_player('Alice').oil == 4

    def test_the_rule_off_produces_no_oil(self):
        game = oil_game(oil_tokens=False)
        # With the rule off the springs are never read, so nothing produces.
        assert game.oil_spring_hexes == set()
        assert game.distribute_oil(9, 'Alice') == {}


class TestPersistence:
    def test_oil_and_the_supply_survive_a_save_and_reload(self):
        game = oil_game()
        game.get_player('Alice').oil = 3
        game.oil_supply = 9
        blob = persistence.serialize(game)
        restored = persistence.deserialize(blob)
        assert restored.get_player('Alice').oil == 3
        assert restored.oil_supply == 9
        # The springs are re-derived from the map, not the save.
        assert len(restored.oil_spring_hexes) == 3
