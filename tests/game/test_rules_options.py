"""Optional house rules from expansions.md."""

import random

import pytest
from game import rules as rules_module
from game.game import Game


def make_game(rules=None, players=('Alice', 'Bob')):
    return Game(list(players), [], rng=random.Random(4242), rules=rules)


class TestRegistry:
    def test_defaults_match_the_base_game(self):
        chosen = rules_module.defaults()
        assert chosen['friendly_robber'] is False
        assert chosen['harbormaster'] is False
        assert chosen['victory_target'] == 10
        assert chosen['max_hand_before_discard'] == 7

    def test_every_rule_declares_what_the_lobby_needs(self):
        for rule in rules_module.catalogue():
            assert rule['id'] and rule['name'] and rule['summary']
            assert rule['source'], f"{rule['id']} must cite a rulebook"
            assert rule['type'] in (rules_module.BOOL, rules_module.INT)
            if rule['type'] == rules_module.INT:
                assert rule['minimum'] <= rule['default'] <= rule['maximum']

    def test_unknown_rule_ids_are_ignored(self):
        chosen = rules_module.coerce({'not_a_rule': True, 'friendly_robber': True})
        assert 'not_a_rule' not in chosen
        assert chosen['friendly_robber'] is True

    def test_numbers_are_clamped_not_rejected(self):
        assert rules_module.coerce({'victory_target': 999})['victory_target'] == 20
        assert rules_module.coerce({'victory_target': -5})['victory_target'] == 5

    def test_non_integers_fall_back_to_the_default(self):
        assert rules_module.coerce({'victory_target': 'ten'})['victory_target'] == 10
        # bool is an int subclass, so True must not sneak through as 1
        assert rules_module.coerce({'victory_target': True})['victory_target'] == 10

    def test_a_garbage_payload_yields_defaults(self):
        assert rules_module.coerce("nonsense") == rules_module.defaults()


class TestVictoryTarget:
    def test_default_target_is_ten(self):
        assert make_game().victory_points_to_win == 10

    def test_target_is_configurable(self):
        assert make_game({'victory_target': 14}).victory_points_to_win == 14

    def test_harbormaster_raises_the_target_by_one(self):
        """The official variant compensates for the extra 2-point card."""
        game = make_game({'victory_target': 10, 'harbormaster': True})
        assert game.victory_points_to_win == 11


class TestHandLimit:
    def test_default_limit_is_seven(self, ):
        game = make_game()
        game.get_player('Alice').resources = {'wood': 8}
        game.check_discard_required()
        assert game.players_needing_discard['Alice'] == 4

    def test_eight_cards_are_safe_when_the_limit_is_raised(self):
        game = make_game({'max_hand_before_discard': 9})
        game.get_player('Alice').resources = {'wood': 8}
        game.check_discard_required()
        assert 'Alice' not in game.players_needing_discard

    def test_raised_limit_still_triggers_above_it(self):
        game = make_game({'max_hand_before_discard': 9})
        game.get_player('Alice').resources = {'wood': 10}
        game.check_discard_required()
        assert game.players_needing_discard['Alice'] == 5


class TestFriendlyRobber:
    def _hex_with_a_settlement(self, game, owner):
        """Put a settlement on a land hex and return that hex's key."""
        for vertex_key, vertex in game.vertices.items():
            if vertex.building:
                continue
            for hex_key in vertex.neighbors.get('hexes', []):
                hex_obj = game.hexes.get(hex_key)
                if hex_obj and hex_obj.type not in ('ocean', 'desert'):
                    vertex.building = {'type': 'settlement', 'player': owner}
                    game.get_player(owner).settlements.append(vertex_key)
                    return hex_key
        pytest.fail("no usable land hex")

    def test_off_by_default(self):
        game = make_game()
        hex_key = self._hex_with_a_settlement(game, 'Bob')
        assert game.robber_is_allowed(hex_key), "base game allows any land hex"

    def test_protects_a_player_on_two_points(self):
        game = make_game({'friendly_robber': True})
        hex_key = self._hex_with_a_settlement(game, 'Bob')
        # Bob now has 2 settlements = 2 victory points.
        game.get_player('Bob').settlements.append('extra')
        assert game.get_player('Bob').get_victory_points() == 2
        assert not game.robber_is_allowed(hex_key)

    def test_allows_a_hex_once_that_player_is_ahead(self):
        game = make_game({'friendly_robber': True})
        hex_key = self._hex_with_a_settlement(game, 'Bob')
        game.get_player('Bob').settlements.extend(['b', 'c'])
        assert game.get_player('Bob').get_victory_points() == 3
        assert game.robber_is_allowed(hex_key)

    def test_an_empty_hex_is_always_allowed(self):
        game = make_game({'friendly_robber': True})
        empty = next(k for k, h in game.hexes.items() if h.type != 'ocean')
        assert game.robber_is_allowed(empty), "no buildings means nobody to protect"

    def test_there_is_a_desert_to_fall_back_to(self):
        game = make_game({'friendly_robber': True})
        assert game.friendly_robber_fallback() is not None


class TestHarbormaster:
    def _give_harbor_settlements(self, game, owner, count):
        """Place `count` settlements on harbour vertices."""
        placed = 0
        for vertex_key, vertex in game.vertices.items():
            if placed >= count:
                break
            if vertex.port and vertex.building is None:
                vertex.building = {'type': 'settlement', 'player': owner}
                game.get_player(owner).settlements.append(vertex_key)
                placed += 1
        assert placed == count, f"board had only {placed} free harbour vertices"

    def test_does_nothing_when_disabled(self):
        game = make_game()
        self._give_harbor_settlements(game, 'Alice', 3)
        game.update_harbormaster()
        assert game.harbormaster_holder is None

    def test_two_harbor_points_is_not_enough(self):
        game = make_game({'harbormaster': True})
        self._give_harbor_settlements(game, 'Alice', 2)
        game.update_harbormaster()
        assert game.harbor_points['Alice'] == 2
        assert game.harbormaster_holder is None

    def test_three_harbor_points_takes_the_card(self):
        game = make_game({'harbormaster': True})
        self._give_harbor_settlements(game, 'Alice', 3)
        game.update_harbormaster()
        assert game.harbormaster_holder == 'Alice'

    def test_a_city_on_a_harbor_counts_two(self):
        game = make_game({'harbormaster': True})
        self._give_harbor_settlements(game, 'Alice', 2)
        # Upgrade one of them.
        moved = game.get_player('Alice').settlements.pop()
        game.get_player('Alice').cities.append(moved)
        game.update_harbormaster()
        assert game.harbor_points['Alice'] == 3
        assert game.harbormaster_holder == 'Alice'

    def test_the_card_is_worth_two_victory_points(self):
        game = make_game({'harbormaster': True})
        self._give_harbor_settlements(game, 'Alice', 3)
        game.update_harbormaster()
        # 3 settlements = 3 points, plus 2 for the card.
        assert game.victory_points_for('Alice') == 5

    def test_a_tie_leaves_the_card_where_it_is(self):
        game = make_game({'harbormaster': True})
        self._give_harbor_settlements(game, 'Alice', 3)
        game.update_harbormaster()
        assert game.harbormaster_holder == 'Alice'

        self._give_harbor_settlements(game, 'Bob', 3)
        game.update_harbormaster()
        assert game.harbormaster_holder == 'Alice', "equal points does not steal it"

    def test_it_moves_to_whoever_has_strictly_more(self):
        game = make_game({'harbormaster': True})
        self._give_harbor_settlements(game, 'Alice', 3)
        game.update_harbormaster()
        self._give_harbor_settlements(game, 'Bob', 4)
        game.update_harbormaster()
        assert game.harbormaster_holder == 'Bob'


class TestRulesReachTheClient:
    def test_board_data_carries_the_selection(self):
        game = make_game({'friendly_robber': True, 'victory_target': 12})
        board = game.get_board_data(viewer='Alice')
        assert board['rules']['friendly_robber'] is True
        assert board['rules']['victory_target'] == 12

    def test_board_data_carries_harbormaster_state(self):
        game = make_game({'harbormaster': True})
        board = game.get_board_data(viewer='Alice')
        assert 'harbormaster_holder' in board
        assert 'harbor_points' in board


class TestCoreKnobs:
    """Base-game numbers that are normally fixed in the box."""

    def test_piece_supplies_are_configurable(self):
        game = make_game({'max_settlements': 8, 'max_cities': 6, 'max_roads': 20})
        assert game.MAX_SETTLEMENTS == 8
        assert game.MAX_CITIES == 6
        assert game.MAX_ROADS == 20

    def test_a_raised_settlement_supply_actually_lets_you_build_more(self):
        game = make_game({'max_settlements': 7})
        player = game.get_player('Alice')
        player.settlements = [f"v{i}" for i in range(5)]
        assert game.has_piece_available('Alice', 'settlement'), "5 is no longer the cap"
        player.settlements.extend(['v5', 'v6'])
        assert not game.has_piece_available('Alice', 'settlement')

    def test_the_default_supplies_match_the_box(self):
        game = make_game()
        assert (game.MAX_SETTLEMENTS, game.MAX_CITIES, game.MAX_ROADS) == (5, 4, 15)

    def test_bank_size_is_configurable(self):
        game = make_game({'bank_resource_limit': 30})
        assert game.bank.resource_limit == 30
        assert game.bank.resources['wood'] == 30

    def test_the_bank_still_runs_out_at_the_chosen_size(self):
        game = make_game({'bank_resource_limit': 5})
        assert game.bank.take('wood', 5)
        assert not game.bank.take('wood', 1)

    def test_longest_road_minimum_is_configurable(self):
        assert make_game({'longest_road_minimum': 3}).rules['longest_road_minimum'] == 3

    def test_largest_army_minimum_is_configurable(self):
        game = make_game({'largest_army_minimum': 1})
        game.get_player('Alice').knights_played = 1
        game.update_largest_army()
        assert game.largest_army_holder == 'Alice', "one knight is enough now"

    def test_the_default_army_minimum_still_needs_three(self):
        game = make_game()
        game.get_player('Alice').knights_played = 2
        game.update_largest_army()
        assert game.largest_army_holder is None

    def test_the_dev_card_deck_is_configurable(self):
        game = make_game({'dev_knights': 3, 'dev_victory_points': 1,
                          'dev_road_building': 0, 'dev_invention': 0,
                          'dev_monopoly': 0})
        assert game.bank.dev_cards_deck == {
            'knight': 3, 'victory_point': 1,
            'two_roads': 0, 'invention': 0, 'monopoly': 0,
        }
        assert game.bank.total_dev_cards_remaining() == 4

    def test_a_card_type_can_be_removed_entirely(self):
        game = make_game({'dev_knights': 0, 'dev_victory_points': 0,
                          'dev_road_building': 0, 'dev_invention': 0,
                          'dev_monopoly': 5})
        drawn = {game.bank.draw_dev_card() for _ in range(5)}
        assert drawn == {'monopoly'}

    def test_the_default_deck_is_the_standard_twenty_five(self):
        game = make_game()
        assert game.bank.total_dev_cards_remaining() == 25

    def test_every_rule_declares_a_group(self):
        for rule in rules_module.catalogue():
            assert rule['group'] in (rules_module.CORE, rules_module.EXPANSION,
                                     rules_module.VARIANT), rule['id']
