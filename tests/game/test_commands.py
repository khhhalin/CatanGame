"""Slash commands: what each one does, and what each one refuses.

The refusals matter as much as the effects here. A command that quietly does
nothing — `/barbarians` at a table not playing them, `/deck` skipping over the
progress decks — teaches a player that the feature is broken, so every one of
these asserts that the refusal *says which rule is missing*.
"""

import random

import pytest
from game import commands as commands_module
from game import rules as rules_module
from game.game import Game

COMMAND_RULES = {'chat_commands': True}
KNIGHT_RULES = {'chat_commands': True, 'knights': True, 'barbarians': True}


def playing(rules=None, players=('Alice', 'Bob')):
    """A game past setup, driven through the real engine."""
    game = Game(list(players), [], rng=random.Random(4242), rules=rules or {})
    game.start()
    game.game_phase = 'playing'
    game.start_turn()
    return game


def run(game, text, actor='Alice'):
    return commands_module.run(text, actor, game, game.rules)


class TestTheHouseRule:
    def test_commands_are_off_by_default(self):
        assert rules_module.defaults()['chat_commands'] is False

    @pytest.mark.parametrize('line', [
        '/add_resource wheat 2',
        '/give Bob wheat 1',
        '/set_dice 3 4',
        '/skip',
        '/barbarians 3',
    ])
    def test_a_command_that_changes_the_game_is_refused_outright(self, line):
        """Off is off: none of these may touch a table that did not agree."""
        game = playing()
        before = dict(game.get_player('Alice').resources)
        result = run(game, line)

        assert result['success'] is False
        assert 'Chat commands' in result['error']
        assert game.get_player('Alice').resources == before

    @pytest.mark.parametrize('line', ['/help', '/whoami', '/rules', '/deck'])
    def test_the_reporting_commands_work_anyway(self, line):
        assert run(playing(), line)['success'] is True


class TestAddResource:
    def test_cards_come_out_of_the_bank(self):
        game = playing(COMMAND_RULES)
        wood_before = game.bank.resources['wood']

        result = run(game, '/add_resource wood 3')

        assert result['success'] is True
        assert game.get_player('Alice').resources['wood'] == 3
        assert game.bank.resources['wood'] == wood_before - 3

    def test_the_table_is_told_who_ran_it(self):
        result = run(playing(COMMAND_RULES), '/add_resource wood 1')
        assert result['log'] == "Alice added 1 wood to their own hand"

    def test_a_named_player_is_the_one_who_gets_them(self):
        game = playing(COMMAND_RULES)
        run(game, '/add_resource ore 2 Bob')
        assert game.get_player('Bob').resources['ore'] == 2
        assert game.get_player('Alice').resources.get('ore', 0) == 0

    def test_a_name_with_a_space_in_it_still_resolves(self):
        """Names are typed by people. Splitting on whitespace alone loses them."""
        game = playing(COMMAND_RULES, players=('Alice', 'Anna Maria'))
        assert run(game, '/add_resource ore 2 Anna Maria')['success'] is True
        assert game.get_player('Anna Maria').resources['ore'] == 2

    def test_an_empty_bank_refuses_and_says_how_many_are_left(self):
        game = playing(COMMAND_RULES)
        game.bank.resources['brick'] = 1

        result = run(game, '/add_resource brick 5')

        assert result['success'] is False
        assert '1 brick' in result['error']
        assert game.get_player('Alice').resources.get('brick', 0) == 0

    def test_a_commodity_needs_the_rule_that_makes_commodities_exist(self):
        result = run(playing(COMMAND_RULES), '/add_resource cloth 1')
        assert result['success'] is False
        assert 'Commodities' in result['error']

    def test_a_commodity_is_dealt_where_the_rule_is_on(self):
        game = playing({**COMMAND_RULES, 'commodities': True})
        assert run(game, '/add_resource cloth 2')['success'] is True
        assert game.get_player('Alice').commodities['cloth'] == 2

    def test_an_unknown_card_lists_the_ones_that_exist(self):
        result = run(playing(COMMAND_RULES), '/add_resource gold 1')
        assert result['success'] is False
        assert 'wood' in result['error'] and 'paper' in result['error']

    def test_a_count_outside_the_bounds_is_refused(self):
        game = playing(COMMAND_RULES)
        assert run(game, '/add_resource wood 0')['success'] is False
        assert run(game, '/add_resource wood 900')['success'] is False
        assert game.get_player('Alice').resources == {}


class TestGive:
    def test_cards_move_between_two_hands(self):
        game = playing(COMMAND_RULES)
        game.get_player('Alice').resources = {'sheep': 4}

        result = run(game, '/give Bob sheep 3')

        assert result['success'] is True
        assert game.get_player('Alice').resources['sheep'] == 1
        assert game.get_player('Bob').resources['sheep'] == 3

    def test_you_cannot_give_what_you_do_not_hold(self):
        game = playing(COMMAND_RULES)
        game.get_player('Alice').resources = {'sheep': 1}

        result = run(game, '/give Bob sheep 3')

        assert result['success'] is False
        assert '1 sheep' in result['error']
        assert game.get_player('Bob').resources.get('sheep', 0) == 0

    def test_an_unknown_player_names_who_is_at_the_table(self):
        result = run(playing(COMMAND_RULES), '/give Carol sheep 1')
        assert result['success'] is False
        assert 'Alice' in result['error'] and 'Bob' in result['error']


class TestSetDice:
    def test_the_next_roll_is_the_one_that_was_asked_for(self):
        game = playing(COMMAND_RULES)
        run(game, '/set_dice 3 4')

        rolled = game.roll_dice(game.current_player_name())

        assert (rolled['dice1'], rolled['dice2']) == (3, 4)
        assert rolled['total'] == 7

    def test_the_fix_is_spent_on_one_roll_only(self):
        game = playing(COMMAND_RULES)
        run(game, '/set_dice 6 6')
        game.roll_dice(game.current_player_name())
        assert game.pending_dice is None

    @pytest.mark.parametrize('line', ['/set_dice 0 4', '/set_dice 3 7', '/set_dice 3'])
    def test_something_no_die_can_show_is_refused(self, line):
        game = playing(COMMAND_RULES)
        assert run(game, line)['success'] is False
        assert game.pending_dice is None


class TestSkip:
    def test_the_turn_moves_on(self):
        game = playing(COMMAND_RULES)
        was = game.current_player_name()

        result = run(game, '/skip')

        assert result['success'] is True
        assert game.current_player_name() != was
        assert result['current_player'] == game.current_player_name()

    def test_a_pending_robber_is_named_rather_than_skipped_past(self):
        """Forcing past the robber carried the flag into the next player's turn."""
        game = playing(COMMAND_RULES)
        game.must_move_robber = True

        result = run(game, '/skip')

        assert result['success'] is False
        assert 'robber' in result['error']
        assert game.must_move_robber is True

    def test_setup_is_refused_because_it_has_no_turn_to_skip(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(4242), rules=COMMAND_RULES)
        game.start()

        result = run(game, '/skip')

        assert result['success'] is False
        assert 'setup' in result['error']


class TestBarbarians:
    def test_a_table_not_playing_them_is_told_which_rule_is_missing(self):
        result = run(playing(COMMAND_RULES), '/barbarians 3')
        assert result['success'] is False
        assert 'Barbarian attacks' in result['error']

    def test_the_ship_moves_to_the_space_asked_for(self):
        game = playing(KNIGHT_RULES)
        assert run(game, '/barbarians 3')['success'] is True
        assert game.ck.barbarian_position == 3

    def test_a_space_past_the_end_is_clamped_to_the_track(self):
        game = playing(KNIGHT_RULES)
        run(game, '/barbarians 99')
        assert game.ck.barbarian_position == game.ck.barbarian_track_length

    def test_an_attack_resolves_now_whatever_the_position(self):
        game = playing(KNIGHT_RULES)
        game.ck.barbarian_position = 1

        result = run(game, '/barbarians attack')

        assert result['success'] is True
        assert result['attack']['won'] is True, "no cities to sack, so nothing is lost"
        assert game.ck.barbarians_have_attacked is True
        assert game.ck.barbarian_position == 0

    def test_an_attack_sacks_a_city_when_nobody_defends(self):
        game = playing(KNIGHT_RULES)
        vertex = next(iter(game.vertices))
        game.get_player('Bob').cities = [vertex]
        game.vertices[vertex].building = {'type': 'city', 'player': 'Bob'}

        result = run(game, '/barbarians attack')

        assert result['attack']['won'] is False
        assert game.get_player('Bob').cities == []


class TestTheReportingCommands:
    def test_whoami_names_the_seat_and_whose_turn_it_is(self):
        game = playing()
        lines = ' '.join(run(game, '/whoami')['lines'])
        assert 'Alice' in lines
        assert game.current_player_name() in lines

    def test_rules_reports_only_what_differs_from_the_defaults(self):
        lines = ' '.join(run(playing({'victory_target': 12}), '/rules')['lines'])
        assert 'Victory points to win 12' in lines
        assert 'Longest Road' not in lines, "an untouched rule is not a difference"

    def test_rules_says_so_when_nothing_was_changed(self):
        assert 'default' in ' '.join(run(playing(), '/rules')['lines'])

    def test_deck_reports_the_development_cards_left(self):
        game = playing()
        game.bank.dev_cards_deck['knight'] = 0
        lines = ' '.join(run(game, '/deck')['lines'])
        assert f'{game.bank.total_dev_cards_remaining()} left' in lines

    def test_deck_says_a_table_does_not_play_progress_cards(self):
        """Skipping the line silently reads as "the command is broken"."""
        lines = ' '.join(run(playing(), '/deck')['lines'])
        assert 'Progress cards: this table does not play them' in lines

    def test_deck_counts_the_progress_decks_when_they_are_in_play(self):
        game = playing({
            'commodities': True, 'city_improvements': True,
            'knights': True, 'barbarians': True, 'progress_cards': True,
        })
        lines = ' '.join(run(game, '/deck')['lines'])
        assert 'science 18' in lines
        assert 'Development cards: none' in lines, "progress cards replace them"

    def test_deck_says_there_is_no_dice_deck_unless_one_is_in_play(self):
        assert 'no deck' in ' '.join(run(playing(), '/deck')['lines'])
        dealt = playing({'dice_deck': True})
        assert '36 of 36' in ' '.join(run(dealt, '/deck')['lines'])

    def test_help_lists_every_command_and_why_a_gated_one_cannot_run(self):
        lines = run(playing(), '/help')['lines']
        listed = ' '.join(lines)
        assert len(lines) == len(commands_module.COMMANDS)
        assert '/add_resource <card> <count> [player]' in listed
        assert 'Chat commands' in listed, "a gated command says what is missing"


class TestParsing:
    def test_a_chat_message_that_merely_contains_a_slash_is_not_a_command(self):
        assert commands_module.looks_like_command('back in 5 w/ coffee') is False
        assert commands_module.looks_like_command('/help') is True

    def test_an_unknown_command_names_the_ones_that_exist(self):
        result = run(playing(), '/summon')
        assert result['success'] is False
        assert '/help' in result['error']

    def test_the_command_name_is_not_case_sensitive(self):
        assert run(playing(), '/HELP')['success'] is True


class TestTheCatalogue:
    def test_every_command_declares_what_the_bar_needs_to_render_it(self):
        for command in commands_module.catalogue(rules_module.defaults()):
            assert command['id'] and command['name'].startswith('/')
            assert command['summary']
            assert isinstance(command['args'], str)
            assert isinstance(command['available'], bool)

    def test_availability_follows_the_table_s_rules(self):
        off = {entry['id']: entry for entry in
               commands_module.catalogue(rules_module.defaults(), has_game=True)}
        assert off['add_resource']['available'] is False
        assert 'Chat commands' in off['add_resource']['unavailable']

        on = {entry['id']: entry for entry in commands_module.catalogue(
            rules_module.coerce(COMMAND_RULES), has_game=True)}
        assert on['add_resource']['available'] is True

    def test_a_command_needing_a_game_says_so_in_the_lobby(self):
        listed = {entry['id']: entry for entry in commands_module.catalogue(
            rules_module.coerce(COMMAND_RULES), has_game=False)}
        assert listed['deck']['available'] is False
        assert 'no game' in listed['deck']['unavailable']
        assert listed['help']['available'] is True

    def test_the_catalogue_carries_nothing_that_cannot_go_on_a_wire(self):
        import json
        json.dumps(commands_module.catalogue(rules_module.defaults()))
