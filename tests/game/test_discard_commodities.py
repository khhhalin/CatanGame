"""Bug A: commodities count toward the 7-discard, so they must be discardable.

`expansions.md` lines 316 and 327 are explicit — a roll of 7 counts resources
and commodities together — and the engine's own hand limit already did. Only the
discard half disagreed, which left a player holding nothing but commodities
permanently unable to comply.
"""

import random

import pytest
from game import rules as rules_module
from game.game import Game
from game.validation import InvalidPayload, clean_card_counts


def ck_game(players=('Alice', 'Bob')):
    return Game(list(players), [], rng=random.Random(7),
                rules=rules_module.preset_rules('cities_and_knights'))


@pytest.fixture
def owing_alice():
    """A C&K game where Alice is over the limit and owes a discard."""
    game = ck_game()
    game.game_phase = 'playing'
    alice = game.get_player('Alice')
    alice.resources = {'wood': 4}
    alice.commodities = {'cloth': 3, 'coin': 3}
    game.check_discard_required()
    return game


class TestDiscardCounting:
    def test_commodities_push_a_player_over_the_limit(self, owing_alice):
        assert owing_alice.players_needing_discard == {'Alice': 5}

    def test_commodities_alone_can_pay_the_discard(self, owing_alice):
        assert owing_alice.discard('Alice', {'cloth': 3, 'coin': 2})['success']

        alice = owing_alice.get_player('Alice')
        assert alice.commodities == {'cloth': 0, 'coin': 1}
        assert alice.resources == {'wood': 4}
        assert 'Alice' not in owing_alice.players_needing_discard

    def test_resources_and_commodities_can_be_mixed(self, owing_alice):
        assert owing_alice.discard('Alice', {'wood': 2, 'paper': 0, 'coin': 3})['success']
        assert owing_alice.get_player('Alice').total_cards() == 5

    def test_discarding_commodities_the_player_does_not_hold_is_refused(self, owing_alice):
        result = owing_alice.discard('Alice', {'paper': 5})
        assert not result['success']
        assert owing_alice.get_player('Alice').commodities['cloth'] == 3

    def test_commodities_do_not_go_back_to_the_resource_bank(self, owing_alice):
        before = owing_alice.bank.get_all()
        owing_alice.discard('Alice', {'cloth': 3, 'coin': 2})
        assert owing_alice.bank.get_all() == before


class TestPayloadValidation:
    def test_commodities_survive_cleaning(self):
        assert clean_card_counts({'cloth': 2, 'wood': 1}) == {'cloth': 2, 'wood': 1}

    def test_unknown_card_types_are_still_refused(self):
        with pytest.raises(InvalidPayload):
            clean_card_counts({'gold': 1})

    def test_negative_counts_are_still_refused(self):
        with pytest.raises(InvalidPayload):
            clean_card_counts({'coin': -1})
