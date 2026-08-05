"""Which deck of cards a table plays with: the `card_system` rule.

Progress cards replace development cards outright (expansions.md 303, 427),
and that stays the default. The rule exists so a table can say otherwise —
development cards at a table that switched the progress decks on, or the house
rule that runs both at once.

What a player would notice if this broke: buying a development card in a game
that is supposed to have none, a city gate dealing progress cards to a table
that chose the base game deck, or a table that asked for both being refused
one of them.
"""

import random

from game import persistence
from game import rules as rules_module
from game.game import Game


def ck_game(extra=None, players=('Alice', 'Bob')):
    rules = rules_module.preset_rules('cities_and_knights')
    rules.update(extra or {})
    game = Game(list(players), [], rng=random.Random(7), rules=rules)
    game.game_phase = 'playing'
    game.start_turn()
    return game


def buying_hand(game, player_name):
    """Exactly the price of one development card."""
    game.get_player(player_name).resources = dict(game.get_cost('knight'))


def stack(game, deck_name, *card_ids):
    """Load a deck so a draw is deterministic. The top of the deck is the end."""
    game.ck.progress_decks[deck_name] = list(card_ids)


def deal_to(game, player_name, deck_name):
    """Make one player top of the track and deal them one card."""
    game.ck.improvements[player_name][deck_name] = 5
    return game._deal_progress_cards(deck_name, 1)


class TestTheRulebookIsStillTheDefault:
    def test_a_progress_card_table_cannot_buy_development_cards(self):
        game = ck_game()
        name = game.current_player_name()
        buying_hand(game, name)

        result = game.buy_dev_card(name)
        assert result['success'] is False
        assert result['code'] == 'DEV_CARDS_NOT_IN_PLAY'

    def test_it_cannot_play_one_either(self):
        game = ck_game()
        name = game.current_player_name()
        game.get_player(name).dev_cards['knight']['count'] = 1

        assert game.play_dev_card(name, 'knight')['code'] == 'DEV_CARDS_NOT_IN_PLAY'

    def test_the_city_gates_still_deal(self):
        game = ck_game()
        stack(game, 'trade', 'merchant')
        assert deal_to(game, 'Alice', 'trade') == {'Alice': 'merchant'}

    def test_a_base_game_table_buys_development_cards_as_it_always_did(self):
        """The rule says nothing where there is only one deck to draw from."""
        game = Game(['Alice', 'Bob'], [], rng=random.Random(7))
        game.game_phase = 'playing'
        game.start_turn()
        name = game.current_player_name()
        buying_hand(game, name)

        assert game.rules['card_system'] == 'progress'
        assert game.buy_dev_card(name)['success'] is True


class TestDevelopmentCardsInstead:
    def test_the_deck_is_buyable(self):
        game = ck_game({'card_system': 'development'})
        name = game.current_player_name()
        buying_hand(game, name)

        assert game.buy_dev_card(name)['success'] is True

    def test_the_city_gates_deal_nothing(self):
        game = ck_game({'card_system': 'development'})
        stack(game, 'science', 'mining')

        assert deal_to(game, 'Alice', 'science') == {}
        assert game.ck.hand_of('Alice') == []


class TestBothAtOnce:
    """The house rule. Two systems drawing, holding and scoring together."""

    def test_both_decks_deal_to_the_same_player(self):
        game = ck_game({'card_system': 'both'})
        name = game.current_player_name()
        buying_hand(game, name)
        stack(game, 'trade', 'merchant')

        assert game.buy_dev_card(name)['success'] is True
        assert deal_to(game, name, 'trade') == {name: 'merchant'}

        held = game.get_player(name).dev_cards
        assert sum(card['count'] for card in held.values()) == 1
        assert game.ck.hand_of(name) == ['merchant']

    def test_a_development_card_can_still_be_played(self):
        game = ck_game({'card_system': 'both'})
        name = game.current_player_name()
        game.get_player(name).dev_cards['knight']['count'] = 1
        game.get_player(name).dev_cards['knight']['purchase_turn'] = -1

        assert game.play_dev_card(name, 'knight')['success'] is True

    def test_points_from_both_decks_add_up(self):
        """A victory point card of each kind, and the total counts both."""
        game = ck_game({'card_system': 'both', 'victory_point_cards_count_in_hand': True})
        name = game.current_player_name()
        before = game.victory_points_for(name)

        game.get_player(name).dev_cards['victory_point']['count'] = 1
        stack(game, 'science', 'printer')
        deal_to(game, name, 'science')

        assert game.victory_points_for(name) == before + 2


class TestTheLobbyAndOldSaves:
    def test_the_options_are_the_three_the_lobby_offers(self):
        rule = rules_module.RULES_BY_ID['card_system']
        assert [option['id'] for option in rule['options']] == [
            'progress', 'development', 'both',
        ]
        assert rule['type'] == rules_module.CHOICE

    def test_a_save_written_before_the_rule_existed_plays_the_rulebook(self):
        """A missing rule falls back to the default, and the default is the
        game those tables were already playing."""
        chosen = rules_module.coerce({'progress_cards': True})
        assert chosen['card_system'] == 'progress'
        assert rules_module.dev_deck_in_play(chosen) is False
        assert rules_module.progress_deck_in_play(chosen) is True

    def test_a_value_nobody_recognises_falls_back_too(self):
        assert rules_module.coerce({'card_system': 'tarot'})['card_system'] == 'progress'
        assert rules_module.card_system({'card_system': None}) == 'progress'

    def test_the_choice_survives_a_save_and_a_reload(self, tmp_path):
        game = ck_game({'card_system': 'both'})
        path = str(tmp_path / 'game.json')
        persistence.save(game, path)

        reloaded = persistence.load(path)
        assert reloaded.rules['card_system'] == 'both'
        assert reloaded.dev_deck_in_play() is True


class TestTheCommandBarSaysWhichSystem:
    """`/deck` is where a player checks what there is left to draw."""

    def _deck_lines(self, game):
        from game import commands
        return commands.run('/deck', game.current_player_name(), game, game.rules)['lines']

    def test_both_decks_are_reported_when_both_are_in_play(self):
        game = ck_game({'card_system': 'both'})
        lines = self._deck_lines(game)
        assert any(line.startswith('Development cards: 25') for line in lines)
        assert any('Progress cards: ' in line and 'left.' in line for line in lines)

    def test_the_development_deck_is_reported_as_replaced_by_default(self):
        lines = self._deck_lines(ck_game())
        assert any('progress cards replace them' in line for line in lines)
