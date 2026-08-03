"""The robber, the turn cycle, development cards and trading, as engine rules.

Like the placement rules, these were only reachable through a socket handler
before; the checks in here are the ones a player actually runs into.
"""

import pytest


def acting(game):
    return game.current_player_name()


def other_player(game, name):
    return next(p.name for p in game.players if p.name != name)


def a_land_hex(game):
    return next(key for key, hex_obj in game.hexes.items() if hex_obj.type not in ('ocean',))


def an_ocean_hex(game):
    return next(key for key, hex_obj in game.hexes.items() if hex_obj.type == 'ocean')


def vertex_on(game, hex_key):
    return next(
        key for key, vertex in game.vertices.items()
        if hex_key in vertex.neighbors.get('hexes', [])
    )


def settle(game, player_name, vertex_key):
    game.vertices[vertex_key].building = {'type': 'settlement', 'player': player_name}
    game.get_player(player_name).settlements.append(vertex_key)


class TestMovingTheRobber:
    def test_the_robber_does_not_move_during_setup(self, fresh_game):
        fresh_game.must_move_robber = True
        result = fresh_game.move_robber(acting(fresh_game), a_land_hex(fresh_game))

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'Cannot move robber during setup'

    def test_the_robber_only_moves_when_it_is_owed(self, playing_game):
        result = playing_game.move_robber(acting(playing_game), a_land_hex(playing_game))

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'You do not need to move the robber'

    def test_only_the_current_player_moves_it(self, playing_game):
        playing_game.must_move_robber = True
        name = acting(playing_game)

        result = playing_game.move_robber(
            other_player(playing_game, name), a_land_hex(playing_game)
        )

        assert result['code'] == 'NOT_YOUR_TURN'
        assert result['error'] == f'Only {name} can move the robber'

    def test_the_ocean_is_not_a_hiding_place(self, playing_game):
        playing_game.must_move_robber = True

        result = playing_game.move_robber(acting(playing_game), an_ocean_hex(playing_game))

        assert result['code'] == 'INVALID_TARGET'
        assert result['error'] == 'Cannot place robber on ocean'

    def test_an_unknown_hex_is_refused(self, playing_game):
        playing_game.must_move_robber = True

        result = playing_game.move_robber(acting(playing_game), 'nowhere')

        assert result['code'] == 'INVALID_TARGET'
        assert result['error'] == 'Invalid hex'

    def test_a_legal_move_clears_the_obligation(self, playing_game):
        playing_game.must_move_robber = True
        hex_key = a_land_hex(playing_game)

        result = playing_game.move_robber(acting(playing_game), hex_key)

        assert result['success']
        assert playing_game.robber_hex == hex_key
        assert playing_game.must_move_robber is False

    def test_a_neighbouring_opponent_becomes_a_victim(self, playing_game):
        playing_game.must_move_robber = True
        name = acting(playing_game)
        victim = other_player(playing_game, name)
        hex_key = a_land_hex(playing_game)
        settle(playing_game, victim, vertex_on(playing_game, hex_key))

        result = playing_game.move_robber(name, hex_key)

        assert result['victims'] == [victim]
        assert playing_game.must_choose_victim is True

    def test_you_are_never_your_own_victim(self, playing_game):
        playing_game.must_move_robber = True
        name = acting(playing_game)
        hex_key = a_land_hex(playing_game)
        settle(playing_game, name, vertex_on(playing_game, hex_key))

        result = playing_game.move_robber(name, hex_key)

        assert result['victims'] == []
        assert playing_game.must_choose_victim is False

    def test_friendly_robber_keeps_the_hex_off_limits(self, rng):
        """The optional rule is enforced by the same method, not by the caller."""
        from game.game import Game

        game = Game(["Alice", "Bob"], [], rng=rng, rules={'friendly_robber': True})
        game.game_phase = 'playing'
        game.must_move_robber = True
        name = game.current_player_name()
        hex_key = a_land_hex(game)
        settle(game, other_player(game, name), vertex_on(game, hex_key))

        result = game.move_robber(name, hex_key)

        assert result['code'] == 'FRIENDLY_ROBBER'


class TestStealing:
    @pytest.fixture
    def robbed(self, playing_game):
        """The robber has landed and a victim is owed a card."""
        playing_game.must_move_robber = True
        name = acting(playing_game)
        victim = other_player(playing_game, name)
        hex_key = a_land_hex(playing_game)
        settle(playing_game, victim, vertex_on(playing_game, hex_key))
        playing_game.move_robber(name, hex_key)
        return playing_game, name, victim

    def test_a_card_moves_across(self, robbed):
        game, thief, victim = robbed
        game.get_player(victim).resources = {'ore': 1}

        result = game.steal_from_victim(thief, victim)

        assert result['success'] and result['stolen'] == 'ore'
        assert game.get_player(victim).resources['ore'] == 0
        assert game.get_player(thief).resources['ore'] == 1
        assert game.must_choose_victim is False

    def test_an_empty_hand_is_a_legal_outcome(self, robbed):
        game, thief, victim = robbed

        result = game.steal_from_victim(thief, victim)

        assert result['success'] and result['stolen'] is None

    def test_a_player_not_on_the_hex_cannot_be_robbed(self, robbed):
        game, thief, _ = robbed

        result = game.steal_from_victim(thief, 'Nobody')

        assert result['code'] == 'INVALID_TARGET'
        assert result['error'] == 'Invalid victim selection'

    def test_stealing_without_a_pending_choice_is_refused(self, playing_game):
        name = acting(playing_game)

        result = playing_game.steal_from_victim(name, other_player(playing_game, name))

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'No victim selection required'


class TestDiscarding:
    def test_a_player_under_the_limit_has_nothing_to_discard(self, playing_game):
        result = playing_game.discard(acting(playing_game), {'wood': 1})

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'You do not need to discard'

    def test_the_wrong_number_of_cards_is_refused(self, playing_game):
        name = acting(playing_game)
        playing_game.get_player(name).resources = {'wood': 8}
        playing_game.check_discard_required()

        result = playing_game.discard(name, {'wood': 3})

        assert result['code'] == 'INVALID_PAYLOAD'
        assert playing_game.get_player(name).resources == {'wood': 8}

    def test_the_right_half_is_accepted(self, playing_game):
        name = acting(playing_game)
        playing_game.get_player(name).resources = {'wood': 8}
        playing_game.check_discard_required()

        assert playing_game.discard(name, {'wood': 4})['success']
        assert playing_game.get_player(name).resources['wood'] == 4
        assert name not in playing_game.players_needing_discard


class TestAdvancingTheTurn:
    def test_the_current_player_may_end_their_turn(self, playing_game):
        name = acting(playing_game)

        result = playing_game.advance_turn(name)

        assert result['success']
        assert result['current_player'] != name
        assert playing_game.turn_count == 1

    def test_someone_else_may_not(self, playing_game):
        name = acting(playing_game)

        result = playing_game.advance_turn(other_player(playing_game, name))

        assert result['code'] == 'NOT_YOUR_TURN'
        assert result['error'] == f'Only {name} can advance the turn'

    def test_an_expired_round_lets_anyone_move_it_on(self, playing_game):
        name = acting(playing_game)
        playing_game.set_dice_rolled()
        playing_game.round_time_limit = 0

        assert playing_game.advance_turn(other_player(playing_game, name))['success']

    def test_an_owed_robber_blocks_the_turn(self, playing_game):
        playing_game.must_move_robber = True

        assert playing_game.advance_turn(acting(playing_game))['code'] == 'MUST_MOVE_ROBBER'

    def test_an_owed_victim_blocks_the_turn(self, playing_game):
        playing_game.must_choose_victim = True

        assert playing_game.advance_turn(acting(playing_game))['code'] == 'MUST_CHOOSE_VICTIM'

    def test_an_owed_discard_blocks_the_turn(self, playing_game):
        name = acting(playing_game)
        playing_game.get_player(name).resources = {'wood': 8}
        playing_game.check_discard_required()

        assert playing_game.advance_turn(name)['code'] == 'MUST_DISCARD'

    def test_setup_turns_are_not_skippable(self, fresh_game):
        result = fresh_game.advance_turn(acting(fresh_game))

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'Cannot skip turn during setup phase'

    def test_a_new_turn_drops_unspent_follow_ups(self, playing_game):
        name = acting(playing_game)
        playing_game.pending_invention = name
        playing_game.pending_monopoly = name
        playing_game.free_roads_remaining = 2

        playing_game.force_advance_turn()

        assert playing_game.pending_invention is None
        assert playing_game.pending_monopoly is None
        assert playing_game.free_roads_remaining == 0

    def test_the_watchdog_can_advance_a_turn_nobody_asked_to_end(self, playing_game):
        name = acting(playing_game)

        assert playing_game.force_advance_turn() != name


class TestRollingTheDice:
    def test_setup_has_no_dice(self, fresh_game):
        result = fresh_game.roll_dice(acting(fresh_game))

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'Cannot roll dice during setup phase'

    def test_only_the_current_player_rolls(self, playing_game):
        name = acting(playing_game)

        result = playing_game.roll_dice(other_player(playing_game, name))

        assert result['code'] == 'NOT_YOUR_TURN'
        assert result['error'] == f'Only {name} can roll dice'

    def test_one_roll_per_turn(self, playing_game):
        name = acting(playing_game)
        assert playing_game.roll_dice(name)['success']

        result = playing_game.roll_dice(name)

        assert result['code'] == 'ALREADY_ROLLED'
        assert result['error'] == 'You have already rolled this turn'

    def test_a_seven_owes_the_robber_and_the_discards(self, started_game):
        from tests.conftest import ScriptedRandom

        started_game.rng = ScriptedRandom([3, 4])
        started_game.game_phase = 'playing'
        started_game.start_turn()
        name = started_game.current_player_name()
        started_game.get_player(name).resources = {'wood': 8}

        result = started_game.roll_dice(name)

        assert result['total'] == 7
        assert started_game.must_move_robber is True
        assert result['discards'] == {name: 4}

    def test_the_base_game_rolls_no_event_die(self, playing_game):
        assert playing_game.roll_dice(acting(playing_game))['event'] is None


class TestDevelopmentCards:
    def test_a_card_cannot_be_bought_during_setup(self, fresh_game):
        result = fresh_game.buy_dev_card(acting(fresh_game))

        assert result['code'] == 'WRONG_PHASE'
        assert result['error'] == 'Cannot buy development cards during setup'

    def test_the_robber_comes_first(self, playing_game):
        playing_game.must_move_robber = True

        assert playing_game.buy_dev_card(acting(playing_game))['code'] == 'MUST_MOVE_ROBBER'

    def test_only_the_current_player_buys(self, playing_game):
        name = acting(playing_game)

        result = playing_game.buy_dev_card(other_player(playing_game, name))

        assert result['code'] == 'NOT_YOUR_TURN'

    def test_an_unaffordable_card_says_so(self, playing_game):
        result = playing_game.buy_dev_card(acting(playing_game))

        assert result['code'] == 'ACTION_FAILED'
        assert result['error'] == 'Cannot afford development card'

    def test_a_knight_owes_the_robber(self, playing_game):
        name = acting(playing_game)
        player = playing_game.get_player(name)
        player.dev_cards['knight'] = {'count': 1, 'purchase_turn': None}

        result = playing_game.play_dev_card(name, 'knight')

        assert result['success'] and result['must_move_robber']
        assert playing_game.must_move_robber is True
        assert player.knights_played == 1

    def test_two_roads_grants_two_free_roads(self, playing_game):
        name = acting(playing_game)
        playing_game.has_rolled_dice = True
        playing_game.get_player(name).dev_cards['two_roads'] = {
            'count': 1, 'purchase_turn': None
        }

        assert playing_game.play_dev_card(name, 'two_roads')['success']
        assert playing_game.free_roads_remaining == 2

    def test_invention_leaves_the_player_owed_a_choice(self, playing_game):
        name = acting(playing_game)
        playing_game.has_rolled_dice = True
        playing_game.get_player(name).dev_cards['invention'] = {
            'count': 1, 'purchase_turn': None
        }

        result = playing_game.play_dev_card(name, 'invention')

        assert result['needs_resources'] is True
        assert playing_game.pending_invention == name

    def test_a_card_you_do_not_hold_cannot_be_played(self, playing_game):
        result = playing_game.play_dev_card(acting(playing_game), 'monopoly')

        assert result['code'] == 'ACTION_REJECTED'
        assert result['error'] == 'You do not have this card'

    def test_a_victory_point_card_can_end_the_game(self, playing_game):
        name = acting(playing_game)
        player = playing_game.get_player(name)
        playing_game.has_rolled_dice = True
        player.victory_points = playing_game.victory_points_to_win - 1
        player.dev_cards['victory_point'] = {'count': 1, 'purchase_turn': None}

        result = playing_game.play_dev_card(name, 'victory_point')

        assert result['won'] is True
        assert result['victory_points'] == playing_game.victory_points_to_win
        assert playing_game.game_state == 'finished'


class TestInventionAndMonopoly:
    def test_invention_without_the_card_is_refused(self, playing_game):
        result = playing_game.use_invention(acting(playing_game), {'wood': 2})

        assert result['code'] == 'NO_PENDING_INVENTION'

    def test_invention_grants_exactly_two(self, playing_game):
        name = acting(playing_game)
        playing_game.pending_invention = name

        result = playing_game.use_invention(name, {'wood': 1, 'ore': 1})

        assert result['taken'] == {'wood': 1, 'ore': 1}
        assert playing_game.pending_invention is None, "the grant is consumed"

    def test_invention_refuses_a_different_number(self, playing_game):
        name = acting(playing_game)
        playing_game.pending_invention = name

        result = playing_game.use_invention(name, {'wood': 3})

        assert result['code'] == 'INVALID_PAYLOAD'
        assert result['error'] == 'Invention gives exactly 2 resources'

    def test_monopoly_without_the_card_is_refused(self, playing_game):
        result = playing_game.use_monopoly(acting(playing_game), 'wood')

        assert result['code'] == 'NO_PENDING_MONOPOLY'

    def test_monopoly_empties_every_other_hand(self, playing_game):
        name = acting(playing_game)
        victim = other_player(playing_game, name)
        playing_game.get_player(victim).resources = {'wood': 3, 'ore': 1}
        playing_game.pending_monopoly = name

        result = playing_game.use_monopoly(name, 'wood')

        assert result['stolen_count'] == 3
        assert playing_game.get_player(victim).resources == {'wood': 0, 'ore': 1}
        assert playing_game.get_player(name).resources['wood'] == 3
        assert playing_game.pending_monopoly is None


class TestTrading:
    def test_a_trade_needs_both_sides(self, playing_game):
        result = playing_game.propose_trade(acting(playing_game), {'wood': 1}, {})

        assert result['code'] == 'INVALID_PAYLOAD'
        assert result['error'] == 'A trade needs resources on both sides'

    def test_you_cannot_offer_what_you_do_not_hold(self, playing_game):
        name = acting(playing_game)

        result = playing_game.propose_trade(name, {'wood': 1}, {'ore': 1})

        assert result['code'] == 'INSUFFICIENT_RESOURCES'
        assert result['error'] == 'Not enough wood: have 0, offering 1'

    def test_only_the_current_player_proposes(self, playing_game):
        name = acting(playing_game)
        opponent = other_player(playing_game, name)
        playing_game.get_player(opponent).resources = {'wood': 4}

        result = playing_game.propose_trade(opponent, {'wood': 4}, {'ore': 1})

        assert result['code'] == 'NOT_YOUR_TURN'

    def test_a_player_offer_waits_for_a_response(self, playing_game):
        name = acting(playing_game)
        playing_game.get_player(name).resources = {'wood': 1}

        result = playing_game.propose_trade(name, {'wood': 1}, {'ore': 1})

        assert result['kind'] == 'offer'
        assert result['offer']['proposer'] == name

    def test_four_for_one_settles_against_the_bank(self, playing_game):
        name = acting(playing_game)
        playing_game.get_player(name).resources = {'wood': 4}

        result = playing_game.propose_trade(name, {'wood': 4}, {'ore': 1})

        assert result['kind'] == 'bank' and result['rate_used'] == 4
        assert playing_game.get_player(name).resources == {'wood': 0, 'ore': 1}

    def test_a_harbour_lowers_the_rate(self, playing_game):
        name = acting(playing_game)
        player = playing_game.get_player(name)
        player.resources = {'wood': 3}
        harbour = next(
            key for key, vertex in playing_game.vertices.items()
            if vertex.port and vertex.port.get('type') == 'generic'
        )
        settle(playing_game, name, harbour)

        assert playing_game.best_trade_rate(name, {'wood': 3}) == 3
        assert playing_game.propose_trade(name, {'wood': 3}, {'ore': 1})['kind'] == 'bank'

    def test_the_bank_cannot_pay_what_it_does_not_have(self, playing_game):
        name = acting(playing_game)
        playing_game.get_player(name).resources = {'wood': 4}
        playing_game.bank.resources['ore'] = 0

        result = playing_game.propose_trade(name, {'wood': 4}, {'ore': 1})

        assert result['code'] == 'BANK_EMPTY'
        assert result['error'] == 'Bank does not have 1 ore'
        assert playing_game.get_player(name).resources == {'wood': 4}, "nothing was touched"

    def test_accepting_an_offer_you_cannot_pay_for_is_refused(self, playing_game):
        name = acting(playing_game)
        opponent = other_player(playing_game, name)
        playing_game.get_player(name).resources = {'wood': 1}
        offer = playing_game.propose_trade(name, {'wood': 1}, {'ore': 1})['offer']

        result = playing_game.accept_trade(offer['id'], opponent)

        assert result['code'] == 'INSUFFICIENT_RESOURCES'
        assert result['error'] == 'Not enough ore to accept this trade'

    def test_an_unknown_offer_is_refused(self, playing_game):
        result = playing_game.accept_trade(999, acting(playing_game))

        assert result['code'] == 'TRADE_NOT_FOUND'

    def test_a_player_trade_moves_both_sides(self, playing_game):
        name = acting(playing_game)
        opponent = other_player(playing_game, name)
        playing_game.get_player(name).resources = {'wood': 1}
        playing_game.get_player(opponent).resources = {'ore': 1}
        offer = playing_game.propose_trade(name, {'wood': 1}, {'ore': 1})['offer']

        assert playing_game.accept_trade(offer['id'], opponent)['success']
        result = playing_game.complete_trade(offer['id'], name, opponent)

        assert result['success'] and result['type'] == 'player'
        assert playing_game.get_player(name).resources == {'wood': 0, 'ore': 1}
        assert playing_game.get_player(opponent).resources == {'ore': 0, 'wood': 1}

    def test_completing_an_unaccepted_offer_is_refused(self, playing_game):
        name = acting(playing_game)
        playing_game.get_player(name).resources = {'wood': 1}
        offer = playing_game.propose_trade(name, {'wood': 1}, {'ore': 1})['offer']

        result = playing_game.complete_trade(offer['id'], name)

        assert result['code'] == 'TRADE_FAILED'
        assert result['error'] == 'Could not complete trade'
