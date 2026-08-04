"""Optional house rules from expansions.md."""

import random

import pytest
from game import board as board_module
from game import rules as rules_module
from game.game import Game


def make_game(rules=None, players=('Alice', 'Bob'), rng=None):
    return Game(list(players), [], rng=rng or random.Random(4242), rules=rules)


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
            assert rule['type'] in (rules_module.BOOL, rules_module.INT, rules_module.CHOICE)
            if rule['type'] == rules_module.INT:
                assert rule['minimum'] <= rule['default'] <= rule['maximum']
            if rule['type'] == rules_module.CHOICE:
                options = rule['options']
                assert all(option['id'] and option['name'] and option['summary']
                           for option in options)
                assert rule['default'] in {option['id'] for option in options}

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

    def test_harbormaster_does_not_rewrite_an_explicit_target(self):
        """Reported: "10 vp needed setting got overridden".

        Harbormaster used to add 1 to whatever the lobby chose, so a table
        that agreed on 10 played to 11 with nothing on screen saying so. The
        variant's suggestion now lives in its preset, where it can be seen and
        changed.
        """
        game = make_game({'victory_target': 10, 'harbormaster': True})
        assert game.victory_points_to_win == 10

    def test_the_cities_and_knights_preset_does_not_rewrite_it_either(self):
        """The same bug from the other side: the expansion forced 13."""
        rules = rules_module.preset_rules('cities_and_knights')
        rules['victory_target'] = 10
        assert make_game(rules).victory_points_to_win == 10

    def test_a_preset_is_where_a_suggested_target_lives(self):
        """A rule may suggest a length; only a preset ever sets it."""
        assert make_game(
            rules_module.preset_rules('cities_and_knights')
        ).victory_points_to_win == 13
        assert make_game(
            rules_module.preset_rules('traders_and_barbarians')
        ).victory_points_to_win == 11


class TestHandLimit:
    """The default 7 is pinned in test_rules.py; these cover raising it."""

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


class TestHarbourRates:
    """The 3:1 and 2:1 defaults are pinned in test_harbours.py against a real
    board; these cover a table moving them."""

    def _settle_on_harbour(self, game, owner, port_type):
        """Put a settlement on one end of a harbour of this type."""
        for edge in game.edges.values():
            if edge.port and edge.port['type'] == port_type:
                game.get_player(owner).settlements = [edge.neighbors['vertices'][0]]
                return edge.port
        pytest.fail(f"no {port_type} harbour on this board")

    def test_a_table_can_take_the_advantage_out_of_harbours(self):
        game = make_game({'generic_harbour_rate': 4})
        self._settle_on_harbour(game, 'Alice', 'generic')
        assert game.best_trade_rate('Alice', {'wood': 4}) == 4

    def test_a_matching_harbour_rate_applies_to_its_own_resource_only(self):
        game = make_game({'special_harbour_rate': 1})
        port = self._settle_on_harbour(game, 'Alice', 'resource')
        other = 'wood' if port['resource'] != 'wood' else 'ore'
        assert game.best_trade_rate('Alice', {port['resource']: 1}) == 1
        assert game.best_trade_rate('Alice', {other: 4}) == 4

    def test_a_generous_bank_still_beats_a_harbour(self):
        game = make_game({'bank_trade_rate': 2})
        self._settle_on_harbour(game, 'Alice', 'generic')
        assert game.best_trade_rate('Alice', {'wood': 2}) == 2, "a harbour never makes it worse"


class TestCityProduction:
    def _lone_hex_corner(self, game):
        """An intersection touching exactly one producing hex, and that hex."""
        for vertex_key, vertex in game.vertices.items():
            producing = [
                game.hexes[key] for key in vertex.neighbors['hexes']
                if game.hexes[key].number is not None and key != game.robber_hex
            ]
            if len(producing) == 1:
                return vertex_key, producing[0]
        pytest.fail("no coastal corner touching a single producing hex")

    @pytest.mark.parametrize('amount', [2, 3])
    def test_a_city_collects_what_the_rule_says(self, amount):
        """2 is the rulebook; anything else has to actually be paid out."""
        game = make_game({'city_production': amount})
        vertex_key, hex_obj = self._lone_hex_corner(game)
        game.vertices[vertex_key].building = {'type': 'city', 'player': 'Alice'}
        game.get_player('Alice').cities.append(vertex_key)

        game.distribute_resources(hex_obj.number)

        assert game.get_player('Alice').resources[hex_obj.type] == amount

    def test_a_settlement_still_collects_one(self):
        game = make_game({'city_production': 4})
        vertex_key, hex_obj = self._lone_hex_corner(game)
        game.vertices[vertex_key].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(vertex_key)

        game.distribute_resources(hex_obj.number)

        assert game.get_player('Alice').resources[hex_obj.type] == 1


class TestRobberFreeOpening:
    """A 7 in the first rounds leaves the robber where it is; the discard does
    not care."""

    def _rolls_a_seven(self, rules):
        from tests.conftest import ScriptedRandom

        game = make_game(rules, rng=ScriptedRandom([3, 4]))
        game.game_phase = "playing"
        game.start_turn()
        game.get_player('Alice').resources = {'wood': 9}
        return game, game.roll_dice('Alice')

    def test_off_by_default_the_robber_moves_at_once(self):
        game, result = self._rolls_a_seven(None)
        assert result['total'] == 7
        assert game.must_move_robber is True

    def test_the_grace_keeps_the_robber_off_the_board(self):
        game, _ = self._rolls_a_seven({'robber_free_opening_rounds': 2})
        assert game.must_move_robber is False

    def test_the_discard_still_bites(self):
        game, _ = self._rolls_a_seven({'robber_free_opening_rounds': 2})
        assert game.players_needing_discard['Alice'] == 4

    def test_the_grace_runs_out(self):
        """Two rounds of a two-player game is four turns."""
        game = make_game({'robber_free_opening_rounds': 2})
        game.turn_count = 3
        assert game.in_robber_free_opening()
        game.turn_count = 4
        assert not game.in_robber_free_opening()


class TestDiceDeck:
    """Production numbers dealt from a deck of all 36 dice combinations."""

    def _roll_many(self, game, times):
        totals = []
        for _ in range(times):
            game.has_rolled_dice = False
            game.must_move_robber = False
            totals.append(game.roll_dice('Alice')['total'])
        return totals

    def _playing(self, rules):
        game = make_game(rules, players=('Alice', 'Bob'))
        game.game_phase = "playing"
        game.start_turn()
        return game

    def test_a_full_deck_is_the_exact_dice_distribution(self):
        game = self._playing({'dice_deck': True})
        totals = self._roll_many(game, 36)
        assert sorted(totals) == sorted(
            first + second for first in range(1, 7) for second in range(1, 7)
        )

    def test_the_deck_is_reshuffled_rather_than_exhausted(self):
        game = self._playing({'dice_deck': True})
        totals = self._roll_many(game, 72)
        assert len(totals) == 72
        assert totals.count(7) == 12, "two passes, six sevens each"

    def test_two_dice_are_not_a_deck(self):
        """Off, 36 rolls are chance and the deck stays empty."""
        game = self._playing(None)
        self._roll_many(game, 36)
        assert game.dice_deck == []


class TestEpidemic:
    """expansions.md 775: on a 6 or an 8 a city collects one card, not two."""

    def _city_on_a_number(self, game, number):
        """Put Alice's city on a corner touching one producing hex, and make
        that hex's number the one asked for."""
        vertex_key, hex_obj = TestCityProduction()._lone_hex_corner(game)
        hex_obj.number = number
        game.vertices[vertex_key].building = {'type': 'city', 'player': 'Alice'}
        game.get_player('Alice').cities.append(vertex_key)
        return hex_obj

    @pytest.mark.parametrize('number', [6, 8])
    def test_a_city_collects_one_on_the_red_numbers(self, number):
        game = make_game({'epidemic': True})
        hex_obj = self._city_on_a_number(game, number)

        game.distribute_resources(number)

        assert game.get_player('Alice').resources[hex_obj.type] == 1

    def test_every_other_number_still_pays_a_city_in_full(self):
        game = make_game({'epidemic': True})
        hex_obj = self._city_on_a_number(game, 5)

        game.distribute_resources(5)

        assert game.get_player('Alice').resources[hex_obj.type] == 2

    def test_it_caps_whatever_the_table_set_a_city_to(self):
        """The epidemic runs after the city's own share, so a table playing
        cities at 4 cards still collects 1 on a 6."""
        game = make_game({'epidemic': True, 'city_production': 4})
        hex_obj = self._city_on_a_number(game, 6)

        game.distribute_resources(6)

        assert game.get_player('Alice').resources[hex_obj.type] == 1

    def test_off_by_default_a_six_pays_a_city_twice(self):
        game = make_game()
        hex_obj = self._city_on_a_number(game, 6)

        game.distribute_resources(6)

        assert game.get_player('Alice').resources[hex_obj.type] == 2


class TestDiceSets:
    """expansions.md 739: "When you roll a '2' or a '12' as your production
    roll you re-roll the dice, because no hex carries those numbers"."""

    def _playing(self, rules):
        game = make_game(rules, rng=random.Random(11))
        game.game_phase = "playing"
        game.start_turn()
        return game

    def _roll_many(self, game, times):
        totals = []
        for _ in range(times):
            game.has_rolled_dice = False
            game.must_move_robber = False
            totals.append(game.roll_dice('Alice')['total'])
        return totals

    def test_the_chosen_set_never_throws_a_two_or_a_twelve(self):
        game = self._playing({'dice_set': 'no_two_or_twelve'})
        totals = self._roll_many(game, 200)
        assert set(totals) == set(range(3, 12))

    def test_the_standard_set_still_throws_them(self):
        game = self._playing(None)
        assert {2, 12} <= set(self._roll_many(game, 400))

    def test_a_dealt_deck_deals_the_chosen_set(self):
        """The dice deck and a dice set compose: the deck is the set, shuffled,
        so 34 rolls is every combination that set allows, once each."""
        game = self._playing({'dice_set': 'no_two_or_twelve', 'dice_deck': True})
        totals = self._roll_many(game, 34)
        assert sorted(totals) == sorted(
            first + second
            for first in range(1, 7) for second in range(1, 7)
            if first + second not in (2, 12)
        )

    def test_the_same_seed_deals_the_same_game(self):
        """A set is drawn from the game's own generator, like everything else."""
        first = self._roll_many(self._playing({'dice_set': 'no_two_or_twelve'}), 20)
        second = self._roll_many(self._playing({'dice_set': 'no_two_or_twelve'}), 20)
        assert first == second


class TestVictoryPointCardsInHand:
    def _one_card_short(self, game):
        """Settlements worth one point less than the game needs."""
        player = game.get_player('Alice')
        player.settlements = [f"v{i}" for i in range(game.victory_points_to_win - 1)]
        player.dev_cards['victory_point']['count'] = 1

    def test_a_held_card_does_nothing_by_default(self):
        game = make_game()
        self._one_card_short(game)
        assert game.claim_victory('Alice') is None

    def test_a_held_card_wins_the_game_when_the_rule_is_on(self):
        game = make_game({'victory_point_cards_count_in_hand': True})
        self._one_card_short(game)
        assert game.claim_victory('Alice') == 10

    def test_playing_the_card_does_not_score_it_twice(self):
        game = make_game({'victory_point_cards_count_in_hand': True})
        player = game.get_player('Alice')
        player.dev_cards['victory_point']['count'] = 1
        assert game.victory_points_for('Alice') == 1

        player.dev_cards['victory_point']['count'] = 0
        player.victory_points = 1
        assert game.victory_points_for('Alice') == 1


class TestRedNumberSeparation:
    def _adjacent_red_pairs(self, game):
        return [
            (key, neighbour)
            for key, hex_obj in game.hexes.items()
            if hex_obj.number in board_module.RED_NUMBERS
            for neighbour in hex_obj.neighbors
            if game.hexes[neighbour].number in board_module.RED_NUMBERS
        ]

    @pytest.mark.parametrize('seed', [1, 2, 3, 7, 4242])
    def test_no_two_red_numbers_touch(self, seed):
        game = make_game({'no_adjacent_red_numbers': True}, rng=random.Random(seed))
        assert self._adjacent_red_pairs(game) == []

    def test_the_box_still_holds_the_same_tokens(self):
        """Separation swaps tokens between hexes; it must not invent any."""
        game = make_game({'no_adjacent_red_numbers': True}, rng=random.Random(9))
        numbers = sorted(
            h.number for h in game.hexes.values()
            if h.number is not None
        )
        assert numbers == list(board_module.NUMBER_TOKENS)

    def test_the_desert_keeps_its_empty_face(self):
        game = make_game({'no_adjacent_red_numbers': True}, rng=random.Random(9))
        deserts = [h for h in game.hexes.values() if h.type == 'desert']
        assert deserts and all(h.number is None for h in deserts)

    def test_a_random_board_is_left_alone_unless_asked(self):
        """The rule is off by default, and the boards that were legal before
        must be identical."""
        loose = make_game(rng=random.Random(1))
        assert self._adjacent_red_pairs(loose), \
            "seed 1 deals adjacent red numbers, which is what the rule fixes"


class TestDependencies:
    """A rule that cannot act on its own is refused, never quietly propped up."""

    def test_a_coherent_set_has_no_problems(self):
        assert rules_module.dependency_problems(
            rules_module.preset_rules('cities_and_knights')
        ) == []

    def test_a_metropolis_needs_the_tracks_that_award_one(self):
        problems = rules_module.dependency_problems(
            rules_module.coerce({'metropolis': True})
        )
        assert problems == ['Metropolis needs City improvements']

    def test_progress_cards_name_both_halves_they_need(self):
        problems = rules_module.dependency_problems(
            rules_module.coerce({'progress_cards': True})
        )
        assert problems == ['Progress cards needs Barbarian attacks and City improvements']

    def test_nothing_is_switched_on_for_you(self):
        chosen = rules_module.coerce({'metropolis': True})
        assert chosen['city_improvements'] is False
        assert chosen['commodities'] is False

    def test_every_dependency_names_a_real_rule(self):
        for rule_id, required in rules_module.DEPENDENCIES.items():
            assert rule_id in rules_module.RULES_BY_ID
            for other in required:
                assert other in rules_module.RULES_BY_ID


class TestPresets:
    def test_a_preset_is_only_ever_individual_rules(self):
        for preset in rules_module.presets():
            for rule_id in preset['rules']:
                assert rule_id in rules_module.RULES_BY_ID, \
                    f"{preset['id']} sets {rule_id}, which is not a rule"

    def test_every_preset_is_a_set_a_table_could_actually_start(self):
        for preset in rules_module.presets():
            chosen = rules_module.preset_rules(preset['id'])
            assert rules_module.dependency_problems(chosen) == [], preset['id']

    def test_the_cities_and_knights_preset_ticks_the_expansion(self):
        chosen = rules_module.preset_rules('cities_and_knights')
        on = {rule_id for rule_id, value in chosen.items()
              if value is True and rules_module.RULES_BY_ID[rule_id]['group']
              == rules_module.EXPANSION}
        assert on == {'commodities', 'city_improvements', 'metropolis', 'knights',
                      'barbarians', 'city_walls', 'progress_cards', 'setup_second_city'}

    def test_the_military_preset_leaves_the_commodities_behind(self):
        chosen = rules_module.preset_rules('knights_only')
        assert chosen['knights'] is True
        assert chosen['barbarians'] is True
        assert chosen['commodities'] is False
        assert chosen['city_improvements'] is False

    def test_an_unknown_preset_is_none(self):
        assert rules_module.preset_rules('no_such_preset') is None


class TestLegacyModeFlag:
    """Saves and clients written before the expansion was decomposed."""

    def test_the_old_flag_becomes_the_rules_it_stood_for(self):
        chosen = rules_module.coerce({'cities_and_knights': True})
        assert chosen == rules_module.preset_rules('cities_and_knights')

    def test_a_game_in_progress_keeps_the_thirteen_it_was_being_played_to(self):
        assert make_game({'cities_and_knights': True}).victory_points_to_win == 13

    def test_the_flag_itself_is_not_kept(self):
        assert 'cities_and_knights' not in rules_module.coerce({'cities_and_knights': True})

    def test_the_flag_switched_off_leaves_a_base_game(self):
        chosen = rules_module.coerce({'cities_and_knights': False})
        assert chosen == rules_module.defaults()

    def test_an_old_game_still_has_its_knights(self):
        game = make_game({'cities_and_knights': True})
        assert game.ck is not None
        assert game.rules['knights'] is True
