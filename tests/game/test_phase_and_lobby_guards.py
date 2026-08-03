"""Bugs D, H and I, proved at the socket boundary a browser actually talks to.

D: building while the robber or a discard is outstanding.
H: two players holding the same colour.
I: trading a resource for itself.
"""

import pytest
import state
from extensions import socketio


@pytest.fixture
def clients(socket_app):
    """Two connected clients in a started two-player game, past setup."""
    alice = socketio.test_client(socket_app)
    bob = socketio.test_client(socket_app)

    alice.emit('join', {'name': 'Alice', 'role': 'player', 'color': '#3498db'})
    bob.emit('join', {'name': 'Bob', 'role': 'player', 'color': '#27ae60'})
    alice.emit('start_game')

    game = state.session().game
    game.game_phase = 'playing'
    game.start_turn()

    alice.get_received()
    bob.get_received()
    return alice, bob


def events(client, name):
    return [msg['args'][0] for msg in client.get_received() if msg['name'] == name]


def last_error(client):
    errors = events(client, 'error')
    return errors[-1] if errors else None


def current_client(clients):
    """The client whose turn it is, and their name."""
    game = state.session().game
    name = game.players[game.current_player_index].name
    alice, bob = clients
    return (alice if name == 'Alice' else bob), name


class TestBuildingIsBlockedWhileTheRobberIsPending:
    def test_roads_are_refused(self, clients):
        client, name = current_client(clients)
        state.session().game.must_move_robber = True

        client.emit('place_road', {'name': name, 'edge': next(iter(state.session().game.edges))})
        assert last_error(client)['code'] == 'MUST_MOVE_ROBBER'

    def test_settlements_are_refused(self, clients):
        client, name = current_client(clients)
        state.session().game.must_move_robber = True

        vertex = next(iter(state.session().game.vertices))
        client.emit('place_settlement', {'name': name, 'vertex': vertex})
        assert last_error(client)['code'] == 'MUST_MOVE_ROBBER'

    def test_dev_cards_cannot_be_bought(self, clients):
        client, name = current_client(clients)
        game = state.session().game
        game.must_move_robber = True
        game.get_player(name).resources = {'sheep': 1, 'wheat': 1, 'ore': 1}

        client.emit('buy_dev_card', {'name': name})
        assert last_error(client)['code'] == 'MUST_MOVE_ROBBER'
        assert game.get_player(name).total_dev_cards() == 0

    def test_an_unchosen_victim_also_blocks(self, clients):
        client, name = current_client(clients)
        state.session().game.must_choose_victim = True

        client.emit('place_road', {'name': name, 'edge': next(iter(state.session().game.edges))})
        assert last_error(client)['code'] == 'MUST_CHOOSE_VICTIM'

    def test_an_owed_discard_blocks_the_player_who_owes_it(self, clients):
        client, name = current_client(clients)
        state.session().game.players_needing_discard = {name: 4}

        client.emit('place_road', {'name': name, 'edge': next(iter(state.session().game.edges))})
        assert last_error(client)['code'] == 'MUST_DISCARD'


class TestSelfTrade:
    def test_a_resource_cannot_be_traded_for_itself(self, clients):
        client, name = current_client(clients)
        state.session().game.get_player(name).resources = {'ore': 3}

        client.emit('propose_trade', {'name': name, 'offered': {'ore': 1}, 'wanted': {'ore': 1}})

        assert last_error(client)['code'] == 'INVALID_TRADE'
        assert state.session().game.get_player(name).resources == {'ore': 3}

    def test_an_overlapping_side_is_refused_too(self, clients):
        client, name = current_client(clients)
        state.session().game.get_player(name).resources = {'ore': 3, 'wood': 3}

        client.emit(
            'propose_trade',
            {'name': name, 'offered': {'ore': 1, 'wood': 1}, 'wanted': {'ore': 2}},
        )
        assert last_error(client)['code'] == 'INVALID_TRADE'

    def test_an_ordinary_offer_still_goes_through(self, clients):
        client, name = current_client(clients)
        state.session().game.get_player(name).resources = {'ore': 3}

        client.emit('propose_trade', {'name': name, 'offered': {'ore': 1}, 'wanted': {'wood': 1}})
        assert last_error(client) is None


class TestLobbyColors:
    def test_a_colour_already_in_use_is_reassigned(self, socket_app):
        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)

        alice.emit('join', {'name': 'Alice', 'role': 'player', 'color': '#3498db'})
        bob.emit('join', {'name': 'Bob', 'role': 'player', 'color': '#3498db'})

        users = {u['name']: u['color'] for u in state.lobby_users()}
        assert users['Alice'] == '#3498db'
        assert users['Bob'] != '#3498db'

    def test_rejoining_under_your_own_name_keeps_your_colour(self, socket_app):
        alice = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player', 'color': '#3498db'})
        alice.emit('join', {'name': 'Alice', 'role': 'player', 'color': '#3498db',
                            'takeover': True})

        users = {u['name']: u['color'] for u in state.lobby_users()}
        assert users['Alice'] == '#3498db'

    def test_taking_an_opponents_colour_mid_game_is_refused(self, clients):
        alice, _ = clients
        alice.emit('set_color', {'name': 'Alice', 'color': '#27ae60'})

        assert last_error(alice)['code'] == 'COLOR_TAKEN'
        assert state.session().game.get_player('Alice').color == '#3498db'
