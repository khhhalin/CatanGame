"""Bugs F and B: progress cards were dead code, and the Defender card is a point.

`progress_cards.py` held all 54 cards and nothing imported it, so a Cities &
Knights game dealt base-game development cards and the three city-gate faces of
the event die did nothing at all (expansions.md 303, 314, 427).

The Defender of Catan half is a check rather than a fix: `victory_points_for`
already added `ck.defender_cards`, so these pin it rather than repair it.
"""

import random

import pytest
import state
from extensions import socketio
from game import cities_knights as ck_module
from game import rules as rules_module
from game.game import Game


def ck_game(players=('Alice', 'Bob')):
    game = Game(list(players), [], rng=random.Random(7),
                rules=rules_module.preset_rules('cities_and_knights'))
    game.game_phase = 'playing'
    game.start_turn()
    return game


@pytest.fixture
def game():
    return ck_game()


def stack(game, deck_name, *card_ids):
    """Load a deck so a draw is deterministic. The top of the deck is the end."""
    game.ck.progress_decks[deck_name] = list(card_ids)


class TestDealingOnACityGate:
    def test_a_gate_deals_to_everyone_who_qualifies(self, game):
        game.ck.improvements['Alice']['trade'] = 2
        game.ck.improvements['Bob']['trade'] = 1
        stack(game, 'trade', 'merchant', 'merchant')

        # Red die 3 clears level 2 (draws on 1-3) but not level 1 (1-2).
        draws = game._deal_progress_cards('trade', 3)

        assert list(draws) == ['Alice']
        assert game.ck.hand_of('Bob') == []

    def test_level_zero_never_draws(self, game):
        stack(game, 'science', 'mining')
        assert game._deal_progress_cards('science', 1) == {}

    def test_level_five_always_draws(self, game):
        game.ck.improvements['Alice']['politics'] = 5
        stack(game, 'politics', 'warlord')

        assert game._deal_progress_cards('politics', 6) == {'Alice': 'warlord'}

    def test_the_event_die_is_what_triggers_it(self, game):
        game.ck.improvements['Alice']['trade'] = 5
        stack(game, 'trade', 'merchant')
        game.roll_event_die = lambda: 'trade'

        outcome = game._resolve_event_die(4)

        assert outcome['draws'] == {'Alice': 'merchant'}
        assert game.ck.hand_of('Alice') == ['merchant']


class TestHandLimit:
    def test_a_fifth_card_is_not_dealt(self, game):
        game.ck.improvements['Alice']['trade'] = 5
        game.ck.progress_hands['Alice'] = ['merchant'] * ck_module.PROGRESS_HAND_LIMIT
        stack(game, 'trade', 'commercial_harbor')

        assert game._deal_progress_cards('trade', 1) == {}

    def test_the_undealt_card_goes_back_under_the_deck(self, game):
        game.ck.improvements['Alice']['trade'] = 5
        game.ck.progress_hands['Alice'] = ['merchant'] * ck_module.PROGRESS_HAND_LIMIT
        stack(game, 'trade', 'merchant_fleet', 'commercial_harbor')

        game._deal_progress_cards('trade', 1)

        assert game.ck.progress_decks['trade'] == ['commercial_harbor', 'merchant_fleet']


class TestVictoryPointCards:
    def test_the_printer_scores_the_moment_it_is_drawn(self, game):
        game.ck.improvements['Alice']['science'] = 5
        stack(game, 'science', 'printer')

        before = game.victory_points_for('Alice')
        game._deal_progress_cards('science', 1)

        assert game.victory_points_for('Alice') == before + 1

    def test_it_never_takes_a_place_in_hand(self, game):
        game.ck.improvements['Alice']['politics'] = 5
        stack(game, 'politics', 'constitution')

        game._deal_progress_cards('politics', 1)
        assert game.ck.hand_of('Alice') == []


class TestPlayingCards:
    def test_road_building_grants_two_free_roads(self, game):
        game.ck.progress_hands['Alice'] = ['road_building']
        game.set_dice_rolled()

        assert game.play_progress_card('Alice', 'road_building')['success']
        assert game.free_roads_remaining == 2

    def test_a_played_card_leaves_the_hand(self, game):
        game.ck.progress_hands['Alice'] = ['road_building']
        game.set_dice_rolled()

        game.play_progress_card('Alice', 'road_building')
        assert game.ck.hand_of('Alice') == []

    def test_a_card_you_do_not_hold_cannot_be_played(self, game):
        game.set_dice_rolled()
        result = game.play_progress_card('Alice', 'road_building')

        assert not result['success']
        assert game.free_roads_remaining == 0

    def test_a_turn_card_cannot_be_played_before_the_roll(self, game):
        game.ck.progress_hands['Alice'] = ['road_building']

        assert not game.play_progress_card('Alice', 'road_building')['success']

    def test_resource_monopoly_takes_two_from_each_opponent(self, game):
        game.ck.progress_hands['Alice'] = ['resource_monopoly']
        game.get_player('Bob').resources = {'ore': 5}
        game.set_dice_rolled()

        assert game.play_progress_card('Alice', 'resource_monopoly', 'ore')['success']
        assert game.get_player('Alice').resources['ore'] == 2
        assert game.get_player('Bob').resources['ore'] == 3

    def test_trade_monopoly_takes_one_commodity(self, game):
        game.ck.progress_hands['Alice'] = ['trade_monopoly']
        game.get_player('Bob').commodities = {'cloth': 2}
        game.set_dice_rolled()

        assert game.play_progress_card('Alice', 'trade_monopoly', 'cloth')['success']
        assert game.get_player('Alice').commodities['cloth'] == 1
        assert game.get_player('Bob').commodities['cloth'] == 1

    def test_warlord_activates_every_idle_knight(self, game):
        game.ck.knights['Alice'] = [ck_module.Knight('v1'), ck_module.Knight('v2')]
        game.ck.progress_hands['Alice'] = ['warlord']
        game.set_dice_rolled()

        assert game.play_progress_card('Alice', 'warlord')['success']
        assert all(k.active for k in game.ck.knights_of('Alice'))

    def test_warlord_with_nothing_to_activate_is_refused(self, game):
        game.ck.progress_hands['Alice'] = ['warlord']
        game.set_dice_rolled()

        assert not game.play_progress_card('Alice', 'warlord')['success']
        # A refused card stays in hand rather than being burned.
        assert game.ck.hand_of('Alice') == ['warlord']

    def test_irrigation_pays_per_building_not_per_hex(self, game):
        terrain = 'wheat'
        vertex_key = next(
            key for key, vertex in game.vertices.items()
            if sum(
                1 for hex_key in vertex.neighbors.get('hexes', [])
                if game.hexes.get(hex_key) is not None
                and game.hexes[hex_key].type == terrain
            ) >= 2
        )
        game.get_player('Alice').settlements.append(vertex_key)
        game.ck.progress_hands['Alice'] = ['irrigation']
        game.set_dice_rolled()

        assert game.play_progress_card('Alice', 'irrigation')['success']
        assert game.get_player('Alice').resources['wheat'] == 2

    def test_a_card_with_no_effect_on_your_own_board_is_refused(self, game):
        game.ck.progress_hands['Alice'] = ['mining']
        game.set_dice_rolled()

        assert not game.play_progress_card('Alice', 'mining')['success']

    def test_the_crane_takes_one_commodity_off_an_improvement(self, game):
        alice = game.get_player('Alice')
        alice.cities.append('some-city')
        alice.commodities = {'cloth': 0}
        game.ck.improvements['Alice']['trade'] = 0
        game.ck.progress_hands['Alice'] = ['crane']
        game.set_dice_rolled()

        # Level 1 normally costs 1 cloth; with the Crane it is free.
        assert game.play_progress_card('Alice', 'crane', 'trade')['success']
        assert game.ck.level('Alice', 'trade') == 1


class TestDefenderOfCatan:
    def _defended(self, game, alice_strength, bob_strength):
        for name, strength in (('Alice', alice_strength), ('Bob', bob_strength)):
            if not strength:
                continue
            knight = ck_module.Knight(f'{name}-v', strength)
            knight.active = True
            game.ck.knights[name] = [knight]
        return game.resolve_barbarian_attack()

    def test_the_sole_top_defender_takes_a_card_worth_a_point(self, game):
        before = game.victory_points_for('Alice')
        result = self._defended(game, 3, 1)

        assert result['won'] and result['defenders'] == ['Alice']
        assert game.ck.defender_cards['Alice'] == 1
        assert game.victory_points_for('Alice') == before + 1

    def test_each_card_scores_separately(self, game):
        game.ck.defender_cards['Alice'] = 2
        assert game.victory_points_for('Alice') == 2

    def test_tied_defenders_each_draw_a_progress_card_instead(self, game):
        result = self._defended(game, 2, 2)

        assert sorted(result['defenders']) == ['Alice', 'Bob']
        assert game.ck.defender_cards['Alice'] == 0
        assert sorted(result['draws']) == ['Alice', 'Bob']


class TestOverTheWire:
    @pytest.fixture
    def ck_clients(self, socket_app):
        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player'})
        bob.emit('join', {'name': 'Bob', 'role': 'player'})
        alice.emit('set_rules', {'preset': 'cities_and_knights'})
        alice.emit('start_game')

        game = state.session().game
        game.game_phase = 'playing'
        game.start_turn()
        game.set_dice_rolled()
        alice.get_received()
        bob.get_received()
        return alice, bob

    def _current(self, ck_clients):
        game = state.session().game
        name = game.players[game.current_player_index].name
        alice, bob = ck_clients
        return (alice if name == 'Alice' else bob), name

    def test_development_cards_are_refused_in_a_ck_game(self, ck_clients):
        client, name = self._current(ck_clients)
        state.session().game.get_player(name).resources = {'sheep': 1, 'wheat': 1, 'ore': 1}

        client.emit('buy_dev_card', {'name': name})

        errors = [m['args'][0] for m in client.get_received() if m['name'] == 'error']
        assert errors[-1]['code'] == 'WRONG_MODE'

    def test_a_card_can_be_played_through_the_handler(self, ck_clients):
        client, name = self._current(ck_clients)
        game = state.session().game
        game.ck.progress_hands[name] = ['road_building']

        client.emit('play_progress_card', {'name': name, 'card': 'road_building'})

        assert game.free_roads_remaining == 2
        assert game.ck.hand_of(name) == []

    def test_an_opponents_progress_hand_is_never_serialized(self, ck_clients):
        alice, _ = ck_clients
        state.session().game.ck.progress_hands['Bob'] = ['spy', 'warlord']

        alice.emit('request_state')
        payloads = [m['args'][0] for m in alice.get_received() if m['name'] == 'game_state']
        knights = payloads[-1]['board']['cities_knights']

        assert knights['progress_hand'] == []
        assert knights['progress_hand_counts']['Bob'] == 2
