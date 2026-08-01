"""Rules-engine invariants: costs, discards, piece limits, victory."""

import pytest


class TestCosts:
    def test_settlement_cost_matches_the_rulebook(self, playing_game):
        assert playing_game.get_cost('settlement') == {
            'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1
        }

    def test_city_cost_matches_the_rulebook(self, playing_game):
        assert playing_game.get_cost('city') == {'wheat': 2, 'ore': 3}

    def test_road_cost_matches_the_rulebook(self, playing_game):
        assert playing_game.get_cost('road') == {'wood': 1, 'brick': 1}

    def test_exactly_enough_can_afford(self, playing_game, give):
        give(playing_game, 'Alice', wood=1, brick=1, wheat=1, sheep=1)
        assert playing_game.can_afford('Alice', 'settlement')

    def test_one_short_cannot_afford(self, playing_game, give):
        """Off-by-one resource checks pass the happy path and fail in play."""
        give(playing_game, 'Alice', wood=1, brick=1, wheat=1, sheep=0)
        assert not playing_game.can_afford('Alice', 'settlement')

    def test_deduct_removes_exactly_the_cost(self, playing_game, give):
        give(playing_game, 'Alice', wood=3, brick=3, wheat=3, sheep=3)
        playing_game.deduct_cost('Alice', 'settlement')
        assert playing_game.get_player('Alice').resources == {
            'wood': 2, 'brick': 2, 'wheat': 2, 'sheep': 2
        }

    def test_failed_purchase_leaves_the_hand_untouched(self, playing_game, give):
        """An illegal action must change nothing, not merely return an error."""
        give(playing_game, 'Alice', wood=1)
        before = dict(playing_game.get_player('Alice').resources)
        assert not playing_game.can_afford('Alice', 'city')
        assert playing_game.get_player('Alice').resources == before


class TestDiscard:
    def test_discard_required_only_above_seven_cards(self, playing_game, give):
        give(playing_game, 'Alice', wood=7)
        give(playing_game, 'Bob', wood=8)
        playing_game.check_discard_required()
        assert 'Alice' not in playing_game.players_needing_discard
        assert playing_game.players_needing_discard['Bob'] == 4

    def test_discard_amount_rounds_down(self, playing_game, give):
        give(playing_game, 'Alice', wood=9)
        playing_game.check_discard_required()
        assert playing_game.players_needing_discard['Alice'] == 4

    def test_valid_discard_succeeds(self, playing_game, give):
        give(playing_game, 'Alice', wood=8)
        playing_game.check_discard_required()
        assert playing_game.discard_resources('Alice', {'wood': 4})
        assert playing_game.get_player('Alice').resources['wood'] == 4

    def test_wrong_total_is_rejected(self, playing_game, give):
        give(playing_game, 'Alice', wood=8)
        playing_game.check_discard_required()
        assert not playing_game.discard_resources('Alice', {'wood': 3})
        assert playing_game.get_player('Alice').resources['wood'] == 8

    def test_cannot_discard_cards_you_do_not_hold(self, playing_game, give):
        give(playing_game, 'Alice', wood=8)
        playing_game.check_discard_required()
        assert not playing_game.discard_resources('Alice', {'ore': 4})
        assert playing_game.get_player('Alice').resources['wood'] == 8

    def test_negative_counts_cannot_mint_resources(self, playing_game, give):
        """The exploit: a negative count passed `held < count` and then *added*
        cards when subtracted, while draining the bank below zero."""
        give(playing_game, 'Alice', wood=8)
        playing_game.check_discard_required()
        bank_before = dict(playing_game.bank.resources)

        assert not playing_game.discard_resources('Alice', {'wood': 54, 'ore': -50})

        assert playing_game.get_player('Alice').resources == {'wood': 8}
        assert playing_game.bank.resources == bank_before

    def test_unknown_resource_keys_are_rejected(self, playing_game, give):
        give(playing_game, 'Alice', wood=8)
        playing_game.check_discard_required()
        assert not playing_game.discard_resources('Alice', {'gold': 4})
        assert 'gold' not in playing_game.get_player('Alice').resources


class TestPieceLimits:
    def test_settlement_supply_is_five(self, playing_game):
        player = playing_game.get_player('Alice')
        for index in range(playing_game.MAX_SETTLEMENTS):
            assert playing_game.has_piece_available('Alice', 'settlement')
            player.settlements.append(f"v{index}")
        assert not playing_game.has_piece_available('Alice', 'settlement')

    def test_city_supply_is_four(self, playing_game):
        player = playing_game.get_player('Alice')
        for index in range(playing_game.MAX_CITIES):
            assert playing_game.has_piece_available('Alice', 'city')
            player.cities.append(f"v{index}")
        assert not playing_game.has_piece_available('Alice', 'city')

    def test_road_supply_is_fifteen(self, playing_game):
        player = playing_game.get_player('Alice')
        for index in range(playing_game.MAX_ROADS):
            assert playing_game.has_piece_available('Alice', 'road')
            player.roads.append(f"e{index}")
        assert not playing_game.has_piece_available('Alice', 'road')


class TestVictoryPoints:
    def test_settlement_is_one_point_city_is_two(self, playing_game):
        player = playing_game.get_player('Alice')
        player.settlements = ['a', 'b']
        player.cities = ['c']
        assert player.get_victory_points() == 4

    def test_longest_road_and_largest_army_add_two_each(self, playing_game):
        player = playing_game.get_player('Alice')
        player.settlements = ['a']
        assert player.get_victory_points('Alice', 'Alice') == 5

    def test_unplayed_victory_point_cards_are_not_public(self, playing_game):
        """An unplayed VP card sits in the hand and must not raise the public
        total, or opponents can read it off the scoreboard."""
        player = playing_game.get_player('Alice')
        player.settlements = ['a']
        player.dev_cards['victory_point']['count'] = 3
        assert player.get_victory_points() == 1


class TestInvariants:
    def test_healthy_game_has_no_violations(self, playing_game):
        assert playing_game.check_invariants() == []

    def test_negative_hand_is_detected(self, playing_game, give):
        give(playing_game, 'Alice', wood=-1)
        assert any('wood' in problem for problem in playing_game.check_invariants())

    def test_too_many_settlements_is_detected(self, playing_game):
        playing_game.get_player('Alice').settlements = [f"v{i}" for i in range(6)]
        assert any('settlements' in problem for problem in playing_game.check_invariants())

    def test_bank_over_limit_is_detected(self, playing_game):
        playing_game.bank.resources['wood'] = 99
        assert any('bank' in problem for problem in playing_game.check_invariants())


class TestBank:
    def test_take_removes_the_requested_amount(self, playing_game):
        before = playing_game.bank.resources['wood']
        assert playing_game.bank.take('wood', 3)
        assert playing_game.bank.resources['wood'] == before - 3

    def test_take_refuses_when_short(self, playing_game):
        playing_game.bank.resources['wood'] = 2
        assert not playing_game.bank.take('wood', 3)
        assert playing_game.bank.resources['wood'] == 2

    def test_return_is_capped_at_the_supply_limit(self, playing_game):
        playing_game.bank.return_resources('wood', 100)
        assert playing_game.bank.resources['wood'] == playing_game.bank.resource_limit

    def test_dev_card_draw_is_weighted_by_remaining_counts(self, playing_game):
        """Drawing uniformly over distinct *types* made a monopoly (2 in deck)
        as likely as a knight (14). Over many draws the knight must dominate."""
        import random

        from game.bank import Bank

        drawn = {}
        for seed in range(200):
            bank = Bank(rng=random.Random(seed))
            card = bank.draw_dev_card()
            drawn[card] = drawn.get(card, 0) + 1

        assert drawn['knight'] > drawn.get('monopoly', 0) * 2, (
            f"knight should dominate a single draw, got {drawn}"
        )

    def test_deck_empties_and_then_returns_none(self, playing_game):
        bank = playing_game.bank
        total = bank.total_dev_cards_remaining()
        for _ in range(total):
            assert bank.draw_dev_card() is not None
        assert bank.draw_dev_card() is None
        assert bank.total_dev_cards_remaining() == 0


class TestHiddenInformation:
    def test_a_player_sees_their_own_hand(self, playing_game, give):
        give(playing_game, 'Alice', wood=3)
        data = playing_game.get_board_data(viewer='Alice')
        alice = next(p for p in data['players'] if p['name'] == 'Alice')
        assert alice['is_you'] is True
        assert alice['resources'] == {'wood': 3}

    def test_a_player_never_sees_an_opponents_hand(self, playing_game, give):
        give(playing_game, 'Bob', wood=3, ore=2)
        data = playing_game.get_board_data(viewer='Alice')
        bob = next(p for p in data['players'] if p['name'] == 'Bob')
        assert bob['is_you'] is False
        assert bob['resources'] is None
        assert bob['dev_cards'] is None
        assert bob['resource_count'] == 5

    def test_no_opponent_hand_appears_anywhere_in_the_payload(self, playing_game, give):
        """The one protocol bug with no visible symptom: serialize once and
        assert the private data simply is not in the bytes."""
        import json
        give(playing_game, 'Bob', wood=3)
        playing_game.get_player('Bob').dev_cards['knight']['count'] = 2

        payload = json.dumps(playing_game.get_board_data(viewer='Alice'))
        bob = next(p for p in json.loads(payload)['players'] if p['name'] == 'Bob')
        assert bob['resources'] is None
        assert bob['dev_cards'] is None

    def test_dev_card_deck_composition_is_never_sent(self, playing_game):
        data = playing_game.get_board_data(viewer='Alice')
        assert 'dev_card_deck' not in data, "per-type deck counts reveal the draw"
        assert isinstance(data['dev_cards_remaining'], int)

    def test_observer_sees_no_hands_at_all(self, playing_game, give):
        give(playing_game, 'Alice', wood=3)
        data = playing_game.get_board_data(viewer=None)
        assert all(p['resources'] is None for p in data['players'])


class TestStateVersion:
    def test_board_data_carries_a_version(self, playing_game):
        assert playing_game.get_board_data()['state_version'] == 0

    def test_version_is_reported_after_being_bumped(self, playing_game):
        playing_game.state_version += 1
        assert playing_game.get_board_data()['state_version'] == 1


@pytest.mark.parametrize("building", ["settlement", "city", "road"])
def test_every_cost_is_positive_and_uses_known_resources(playing_game, building):
    from game.validation import RESOURCE_TYPES
    cost = playing_game.get_cost(building)
    assert cost, f"{building} has no cost"
    for resource, amount in cost.items():
        assert resource in RESOURCE_TYPES
        assert amount > 0
