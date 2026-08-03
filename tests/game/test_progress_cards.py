"""The three Cities & Knights progress card decks from expansions.md."""

import random
from collections import Counter

import pytest
from game import progress_cards


class TestDeckComposition:
    def test_each_deck_holds_eighteen_cards(self):
        assert progress_cards.deck_counts() == {
            progress_cards.SCIENCE: 18,
            progress_cards.TRADE: 18,
            progress_cards.POLITICS: 18,
        }

    def test_every_card_declares_what_the_engine_needs(self):
        for card in progress_cards.PROGRESS_CARDS:
            assert card['id'] and card['name']
            assert card['summary'].strip(), f"{card['id']} must describe its effect"
            assert card['deck'] in progress_cards.DECKS
            assert card['timing'] in ('turn', 'before_roll', 'immediate')
            assert card['count'] >= 1
            assert card['victory_points'] in (0, 1)

    def test_needs_target_uses_the_closed_vocabulary(self):
        allowed = {
            None, 'resource', 'commodity', 'resource_or_commodity', 'player',
            'two_number_tokens', 'knight', 'road', 'vertex', 'hex', 'dice',
            'improvement',
        }
        for card in progress_cards.PROGRESS_CARDS:
            assert card['needs_target'] in allowed, card['id']

    def test_lookup_covers_every_card(self):
        """Also the uniqueness check: a duplicate id would collapse the lookup."""
        assert len(progress_cards.CARDS_BY_ID) == len(progress_cards.PROGRESS_CARDS)
        assert progress_cards.CARDS_BY_ID['alchemist']['deck'] == progress_cards.SCIENCE


class TestBuildDeck:
    def test_deck_composition_matches_the_declared_counts(self):
        deck = progress_cards.build_deck(progress_cards.POLITICS, random.Random(7))
        expected = Counter({
            card['id']: card['count']
            for card in progress_cards.PROGRESS_CARDS
            if card['deck'] == progress_cards.POLITICS
        })
        assert Counter(deck) == expected

    def test_same_seed_gives_the_same_shuffle(self):
        """A game must be replayable from its seed, so draws cannot use global random."""
        first = progress_cards.build_deck(progress_cards.SCIENCE, random.Random(99))
        second = progress_cards.build_deck(progress_cards.SCIENCE, random.Random(99))
        assert first == second

    def test_different_seeds_give_different_shuffles(self):
        first = progress_cards.build_deck(progress_cards.TRADE, random.Random(1))
        second = progress_cards.build_deck(progress_cards.TRADE, random.Random(2))
        assert first != second

    def test_unknown_deck_name_is_rejected(self):
        with pytest.raises(ValueError):
            progress_cards.build_deck('purple', random.Random(1))


class TestDrawThreshold:
    @pytest.mark.parametrize("level,threshold", [
        (0, 0),   # never draws
        (1, 2),   # draws on 1-2
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 6),   # always draws
    ])
    def test_each_improvement_level_draws_on_the_rulebook_range(self, level, threshold):
        assert progress_cards.draw_threshold(level) == threshold

    def test_levels_outside_zero_to_five_are_rejected(self):
        with pytest.raises(ValueError):
            progress_cards.draw_threshold(6)
        with pytest.raises(ValueError):
            progress_cards.draw_threshold(-1)


class TestSpecialCards:
    def test_printer_and_constitution_are_the_only_victory_point_cards(self):
        scoring = {
            card['id'] for card in progress_cards.PROGRESS_CARDS
            if card['victory_points'] == 1
        }
        assert scoring == {'printer', 'constitution'}

    def test_victory_point_cards_are_revealed_as_soon_as_they_are_drawn(self):
        for card_id in ('printer', 'constitution'):
            assert progress_cards.CARDS_BY_ID[card_id]['timing'] == 'immediate'

    def test_alchemist_is_the_only_card_played_before_the_roll(self):
        before_roll = {
            card['id'] for card in progress_cards.PROGRESS_CARDS
            if card['timing'] == 'before_roll'
        }
        assert before_roll == {'alchemist'}
