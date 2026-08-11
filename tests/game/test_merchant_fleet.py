"""Merchant Fleet: a 2:1 bank rate on one card type, for the rest of the turn.

`expansions.md` 450 — "The Merchant Fleet card lets the player trade one chosen
resource or commodity at a 2:1 rate with the bank for the rest of the turn."

The card was refused by name for as long as the trade engine had no bank rate
for commodities at all. It has one now (`test_commodity_trading.py`), and the
one asymmetry that came with it — line 331, a 2:1 *harbour* never takes a
commodity — is what these tests have to keep true while granting a 2:1 that
does.

Each test asserts something a player would notice: a dialog with eight options,
four paper buying two cards instead of one, and the rate being gone the moment
the turn ends.
"""

import json
import random

import pytest
from game import persistence
from game import rules as rules_module
from game.game import Game


@pytest.fixture
def game():
    game = Game(['Alice', 'Bob'], [], rng=random.Random(7),
                rules=rules_module.preset_rules('cities_and_knights'))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = next(
        index for index, player in enumerate(game.players) if player.name == 'Alice'
    )
    game.set_dice_rolled()
    return game


def play_fleet(game, player_name, card_type):
    """Play the card and answer the question it opens."""
    game.ck.progress_hands[player_name] = ['merchant_fleet']
    assert game.play_progress_card(player_name, 'merchant_fleet')['success']
    return game.resolve_choice(player_name, 'merchant_fleet', card_type)


class TestTheCardAsksWhichType:
    def test_all_eight_card_types_are_offered(self, game):
        """"one chosen resource or commodity" — the choice is the card.

        Eight on this standard board: the five resources and three commodities.
        `cotton` is in the type system (a custom map may deal it) but this board
        does not, so it must NOT be offered — the picker follows what the board
        can pay, not the whole vocabulary. That absence is what proves a standard
        table's fleet dialog is unchanged by cotton existing.
        """
        game.ck.progress_hands['Alice'] = ['merchant_fleet']

        result = game.play_progress_card('Alice', 'merchant_fleet')

        assert result['success'], result.get('error')
        offered = game.pending_choice_for('Alice')['options']
        assert offered == ['wood', 'brick', 'sheep', 'wheat', 'ore',
                           'cloth', 'coin', 'paper']
        assert 'cotton' not in offered

    def test_a_type_that_was_never_offered_is_refused(self, game):
        game.ck.progress_hands['Alice'] = ['merchant_fleet']
        game.play_progress_card('Alice', 'merchant_fleet')

        result = game.resolve_choice('Alice', 'merchant_fleet', 'gold')

        assert result['code'] == 'INVALID_CHOICE'
        assert game.best_trade_rate('Alice', {'wood': 2}) == 4


class TestTheRate:
    def test_the_chosen_resource_buys_a_card_for_two(self, game):
        play_fleet(game, 'Alice', 'ore')
        game.get_player('Alice').resources = {'ore': 2}

        result = game.propose_trade('Alice', {'ore': 2}, {'wheat': 1})

        assert result['kind'] == 'bank'
        assert result['rate_used'] == 2
        assert game.get_player('Alice').resources['wheat'] == 1

    def test_a_commodity_can_be_the_chosen_type(self, game):
        """The card says "resource or commodity", and line 331 only withdraws
        the *harbour's* 2:1 — the fleet is not a harbour."""
        play_fleet(game, 'Alice', 'paper')
        game.get_player('Alice').commodities = {'paper': 2}

        result = game.propose_trade('Alice', {'paper': 2}, {'wood': 1})

        assert result['kind'] == 'bank'
        assert result['rate_used'] == 2
        assert game.get_player('Alice').commodities['paper'] == 0

    def test_the_player_s_other_cards_are_unchanged(self, game):
        play_fleet(game, 'Alice', 'ore')

        assert game.best_trade_rate('Alice', {'wheat': 4}) == 4
        assert game.best_trade_rate('Alice', {'cloth': 4}) == 4

    def test_a_mixed_offer_pays_the_table_rate(self, game):
        """Two ore buy a card; one ore and one wheat do not, or a fleet would
        discount every card in the hand as long as one of them was ore."""
        play_fleet(game, 'Alice', 'ore')

        assert game.best_trade_rate('Alice', {'ore': 1, 'wheat': 1}) == 4

    def test_it_belongs_to_the_player_who_played_it(self, game):
        play_fleet(game, 'Alice', 'ore')

        assert game.best_trade_rate('Bob', {'ore': 2}) == 4


class TestItComposesWithTheHarbours:
    def _seat_on(self, game, player_name, port):
        for vertex_key in sorted(game.vertices):
            vertex = game.vertices[vertex_key]
            if not vertex.port or vertex.port['type'] != port['type']:
                continue
            if port['type'] == 'resource' and vertex.port['resource'] != port['resource']:
                continue
            game.get_player(player_name).settlements = [vertex_key]
            return vertex.port
        raise AssertionError(f'no {port} harbour on this board')

    def test_it_beats_a_generic_harbour(self, game):
        self._seat_on(game, 'Alice', {'type': 'generic'})
        play_fleet(game, 'Alice', 'ore')

        assert game.best_trade_rate('Alice', {'ore': 2}) == 2
        assert game.best_trade_rate('Alice', {'wheat': 3}) == 3

    def test_a_matching_two_to_one_harbour_makes_it_no_better(self, game):
        port = self._seat_on(game, 'Alice', {'type': 'resource', 'resource': 'wood'})
        play_fleet(game, 'Alice', port['resource'])

        assert game.best_trade_rate('Alice', {port['resource']: 2}) == 2

    def test_a_resource_harbour_still_never_takes_a_commodity(self, game):
        """Line 331 survives the fleet: the harbour's 2:1 is withdrawn for a
        commodity the fleet did not name."""
        self._seat_on(game, 'Alice', {'type': 'resource', 'resource': 'wood'})
        play_fleet(game, 'Alice', 'ore')

        assert game.best_trade_rate('Alice', {'cloth': 2}) == 4
        assert game.best_trade_rate('Alice', {'wood': 2, 'cloth': 2}) == 4


class TestItLastsOneTurn:
    def test_the_next_turn_pays_the_table_rate_again(self, game):
        play_fleet(game, 'Alice', 'ore')
        assert game.advance_turn('Alice')['success']

        assert game.best_trade_rate('Alice', {'ore': 2}) == 4

    def test_a_turn_the_watchdog_ends_clears_it_too(self, game):
        """A player who walks away mid-turn must not keep the rate: the
        watchdog force-advances, which is the path `pending_invention` and the
        free roads are already cleared on."""
        play_fleet(game, 'Alice', 'ore')
        game.force_advance_turn()

        assert game.best_trade_rate('Alice', {'ore': 2}) == 4


class TestItSurvivesARestart:
    def test_a_round_trip_mid_turn_keeps_the_rate(self, tmp_path):
        game = Game(['Alice', 'Bob'], [], {},
                    rules=rules_module.preset_rules('cities_and_knights'),
                    rng=random.Random(11))
        game.start()
        game.set_dice_rolled()
        holder = game.players[game.current_player_index].name
        play_fleet(game, holder, 'paper')

        path = str(tmp_path / 'game.json')
        persistence.save(game, path)
        restored = persistence.load(path)

        assert restored.best_trade_rate(holder, {'paper': 2}) == 2

    def test_a_save_written_without_the_key_still_loads(self, tmp_path):
        game = Game(['Alice', 'Bob'], [], {},
                    rules=rules_module.preset_rules('cities_and_knights'),
                    rng=random.Random(11))
        game.start()
        path = str(tmp_path / 'game.json')
        persistence.save(game, path)

        with open(path) as handle:
            data = json.load(handle)
        del data['merchant_fleet_types']
        with open(path, 'w') as handle:
            json.dump(data, handle)

        restored = persistence.load(path)
        assert restored.merchant_fleet_types == {}
