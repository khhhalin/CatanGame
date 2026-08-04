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
    """Two connected clients in a started two-player game, past setup and
    past the roll."""
    alice = socketio.test_client(socket_app)
    bob = socketio.test_client(socket_app)

    alice.emit('join', {'name': 'Alice', 'role': 'player', 'color': '#3498db'})
    bob.emit('join', {'name': 'Bob', 'role': 'player', 'color': '#27ae60'})
    alice.emit('start_game')

    game = state.session().game
    game.game_phase = 'playing'
    game.start_turn()
    # Trading and building come after the dice, so the table starts where a
    # player would be doing either: their roll already made.
    game.set_dice_rolled()

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


class TestNothingHappensBeforeTheDice:
    """Reported: a player built their whole turn and rolled afterwards.

    expansions.md 1121 spells the sequence out: "roll the dice, then the trade
    and build phase, then the end of the active player's turn". Nothing asked
    `has_rolled_dice` before building, trading or buying.
    """

    def _settled(self, game, name):
        """A settlement of this player's, and a land side leaving it."""
        for vertex_key, vertex in game.vertices.items():
            edges = [e for e in vertex.neighbors.get('edges', []) if game.land_hexes_of_edge(e)]
            if vertex.building or not edges or not vertex.neighbors['hexes']:
                continue
            vertex.building = {'type': 'settlement', 'player': name}
            game.get_player(name).settlements.append(vertex_key)
            return vertex_key, edges[0]
        raise AssertionError('no usable intersection on this board')

    def test_a_road_is_refused_before_the_roll(self, clients):
        client, name = current_client(clients)
        game = state.session().game
        game.has_rolled_dice = False
        _vertex, edge_key = self._settled(game, name)
        game.get_player(name).resources = {'wood': 1, 'brick': 1}

        client.emit('place_road', {'name': name, 'edge': edge_key})

        assert last_error(client)['code'] == 'MUST_ROLL_FIRST'
        assert game.edges[edge_key].road is None

    def test_a_city_is_refused_before_the_roll(self, clients):
        client, name = current_client(clients)
        game = state.session().game
        game.has_rolled_dice = False
        vertex_key, _edge = self._settled(game, name)
        game.get_player(name).resources = {'ore': 3, 'wheat': 2}

        client.emit('upgrade_city', {'name': name, 'vertex': vertex_key})

        assert last_error(client)['code'] == 'MUST_ROLL_FIRST'
        assert game.get_player(name).cities == []

    def test_a_bank_trade_is_refused_before_the_roll(self, clients):
        client, name = current_client(clients)
        game = state.session().game
        game.has_rolled_dice = False
        game.get_player(name).resources = {'ore': 4}

        client.emit('propose_trade', {'name': name, 'offered': {'ore': 4}, 'wanted': {'wood': 1}})

        assert last_error(client)['code'] == 'MUST_ROLL_FIRST'
        assert game.get_player(name).resources == {'ore': 4}

    def test_a_dev_card_cannot_be_bought_before_the_roll(self, clients):
        client, name = current_client(clients)
        game = state.session().game
        game.has_rolled_dice = False
        game.get_player(name).resources = {'sheep': 1, 'wheat': 1, 'ore': 1}

        client.emit('buy_dev_card', {'name': name})

        assert last_error(client)['code'] == 'MUST_ROLL_FIRST'
        assert game.get_player(name).total_dev_cards() == 0

    def test_a_knight_is_still_playable_before_the_roll(self, clients):
        """The one thing the rulebook allows first, and it must stay allowed."""
        client, name = current_client(clients)
        game = state.session().game
        game.has_rolled_dice = False
        game.get_player(name).dev_cards['knight'] = {'count': 1, 'purchase_turn': None}

        client.emit('play_dev_card', {'name': name, 'card_type': 'knight'})

        assert last_error(client) is None
        assert game.must_move_robber is True

    def test_setup_placements_are_untouched(self, socket_app):
        """Setup has no dice at all, so the gate must not reach it."""
        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player', 'color': '#3498db'})
        bob.emit('join', {'name': 'Bob', 'role': 'player', 'color': '#27ae60'})
        alice.emit('start_game')
        alice.get_received()
        bob.get_received()

        game = state.session().game
        assert game.game_phase == 'setup' and not game.has_rolled_dice
        client = alice if game.current_player_name() == 'Alice' else bob

        client.emit('place_settlement',
                    {'name': game.current_player_name(), 'vertex': next(iter(game.vertices))})

        assert last_error(client) is None


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
