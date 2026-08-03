"""Socket-layer tests, including the exploits the audit found.

These drive real clients through the real handlers, so they prove the fix at
the boundary a browser actually talks to.
"""

import pytest
import state
from extensions import socketio


@pytest.fixture
def clients(socket_app):
    """Two connected clients in a started two-player game."""

    alice = socketio.test_client(socket_app)
    bob = socketio.test_client(socket_app)

    alice.emit('join', {'name': 'Alice', 'role': 'player'})
    bob.emit('join', {'name': 'Bob', 'role': 'player'})
    alice.emit('start_game')

    alice.get_received()
    bob.get_received()
    return alice, bob


def events(client, name):
    """All payloads of a given event name from one drain of the queue."""
    return [msg['args'][0] for msg in client.get_received() if msg['name'] == name]


def last_error(client):
    errors = events(client, 'error')
    return errors[-1] if errors else None


class TestConnectionAndState:
    # A join with no game running is answered with in_game False: see
    # TestStartingAGame, which records why that flag matters to the client.

    def test_request_state_replies_to_the_asker_only(self, clients):
        alice, bob = clients
        alice.emit('request_state')
        assert events(alice, 'game_state'), "asker gets the snapshot"
        assert not events(bob, 'game_state'), "nobody else does"

    def test_empty_name_is_rejected_not_silently_dropped(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': '   '})
        assert last_error(client)['code'] == 'INVALID_PAYLOAD'

    def test_disconnect_drops_the_view_binding(self, clients):
        alice, _ = clients
        before = len(state.session().viewers)
        alice.disconnect()
        assert len(state.session().viewers) == before - 1


class TestHiddenInformationOverTheWire:
    def test_a_client_never_receives_an_opponents_hand(self, clients):
        alice, bob = clients
        state.session().game.get_player('Bob').resources = {'wood': 5}

        alice.emit('request_state')
        board = events(alice, 'game_state')[-1]['board']
        bob_entry = next(p for p in board['players'] if p['name'] == 'Bob')

        assert bob_entry['resources'] is None
        assert bob_entry['resource_count'] == 5

    def test_each_client_gets_its_own_view_of_the_same_broadcast(self, clients):
        alice, bob = clients
        game = state.session().game
        game.get_player('Alice').resources = {'wood': 2}
        game.get_player('Bob').resources = {'ore': 3}

        alice.emit('refresh_board')
        bob.emit('refresh_board')

        alice_board = events(alice, 'board_updated')[-1]['board']
        bob_board = events(bob, 'board_updated')[-1]['board']

        alice_self = next(p for p in alice_board['players'] if p['name'] == 'Alice')
        bob_self = next(p for p in bob_board['players'] if p['name'] == 'Bob')
        assert alice_self['resources'] == {'wood': 2}
        assert bob_self['resources'] == {'ore': 3}

        alice_sees_bob = next(p for p in alice_board['players'] if p['name'] == 'Bob')
        assert alice_sees_bob['resources'] is None


class TestDevCardFollowUpsRequireTheCard:
    def test_invention_without_the_card_is_refused(self, clients):
        """The exploit: use_invention had no turn check and no card check, so
        any client could drain the bank at any time."""
        alice, _ = clients
        game = state.session().game
        bank_before = dict(game.bank.resources)

        alice.emit('use_invention', {'name': 'Alice', 'resources': {'wood': 2}})

        assert last_error(alice)['code'] == 'NO_PENDING_INVENTION'
        assert game.bank.resources == bank_before
        assert game.get_player('Alice').resources == {}

    def test_invention_with_a_pending_card_grants_exactly_two(self, clients):
        alice, _ = clients
        game = state.session().game
        game.pending_invention = 'Alice'

        alice.emit('use_invention', {'name': 'Alice', 'resources': {'wood': 2}})

        assert game.get_player('Alice').resources['wood'] == 2
        assert game.pending_invention is None, "the grant is consumed"

    def test_invention_cannot_be_redeemed_twice(self, clients):
        alice, _ = clients
        game = state.session().game
        game.pending_invention = 'Alice'

        alice.emit('use_invention', {'name': 'Alice', 'resources': {'wood': 2}})
        alice.get_received()
        alice.emit('use_invention', {'name': 'Alice', 'resources': {'wood': 2}})

        assert last_error(alice)['code'] == 'NO_PENDING_INVENTION'
        assert game.get_player('Alice').resources['wood'] == 2

    def test_invention_asking_for_more_than_two_is_refused(self, clients):
        alice, _ = clients
        game = state.session().game
        game.pending_invention = 'Alice'

        alice.emit('use_invention', {'name': 'Alice', 'resources': {'wood': 19}})

        assert last_error(alice)['code'] == 'INVALID_PAYLOAD'
        assert game.get_player('Alice').resources == {}

    def test_monopoly_without_the_card_is_refused(self, clients):
        alice, _ = clients
        game = state.session().game
        game.get_player('Bob').resources = {'wood': 4}

        alice.emit('use_monopoly', {'name': 'Alice', 'resource_type': 'wood'})

        assert last_error(alice)['code'] == 'NO_PENDING_MONOPOLY'
        assert game.get_player('Bob').resources == {'wood': 4}

    def test_monopoly_with_an_unknown_resource_is_refused(self, clients):
        alice, _ = clients
        state.session().game.pending_monopoly = 'Alice'
        alice.emit('use_monopoly', {'name': 'Alice', 'resource_type': 'gold'})
        assert last_error(alice)['code'] == 'INVALID_PAYLOAD'


class TestDiscardOverTheWire:
    def test_negative_counts_are_refused_at_the_boundary(self, clients):
        alice, _ = clients
        game = state.session().game
        game.get_player('Alice').resources = {'wood': 8}
        game.check_discard_required()
        bank_before = dict(game.bank.resources)

        alice.emit('discard_resources',
                   {'name': 'Alice', 'resources': {'wood': 54, 'ore': -50}})

        assert last_error(alice)['code'] == 'INVALID_PAYLOAD'
        assert game.get_player('Alice').resources == {'wood': 8}
        assert game.bank.resources == bank_before

    def test_a_valid_discard_is_accepted(self, clients):
        alice, _ = clients
        game = state.session().game
        game.get_player('Alice').resources = {'wood': 8}
        game.check_discard_required()

        alice.emit('discard_resources', {'name': 'Alice', 'resources': {'wood': 4}})

        assert game.get_player('Alice').resources['wood'] == 4


class TestErrorsAreTargetedAndCoded:
    def test_a_rejection_reaches_only_the_offending_client(self, clients):
        alice, bob = clients
        alice.emit('use_monopoly', {'name': 'Alice', 'resource_type': 'wood'})
        assert last_error(alice) is not None
        assert last_error(bob) is None, "one player's illegal move is not the table's business"

    def test_every_error_carries_a_machine_readable_code(self, clients):
        alice, _ = clients
        alice.emit('use_invention', {'name': 'Alice', 'resources': {'wood': 2}})
        error = last_error(alice)
        assert error['code'] and error['code'].isupper()
        assert error['message']

    def test_malformed_payloads_do_not_crash_the_handler(self, clients):
        alice, _ = clients
        for bad in [{}, {'name': 123}, {'name': 'Alice', 'resources': 'nope'},
                    {'name': 'Alice', 'resources': {'wood': 'x'}},
                    {'name': 'Alice', 'resources': {'wood': True}}]:
            alice.emit('use_invention', bad)
            assert last_error(alice) is not None, f"no reply for {bad}"
        assert alice.is_connected()


class TestPieceLimitsOverTheWire:
    def test_settlements_run_out(self, clients):
        alice, _ = clients
        game = state.session().game
        game.game_phase = "playing"

        # Turn order is shuffled, so ask who is actually up rather than
        # assuming — otherwise this fails on NOT_YOUR_TURN half the time.
        acting = game.players[game.current_player_index].name
        player = game.get_player(acting)
        player.settlements = [f"v{i}" for i in range(game.MAX_SETTLEMENTS)]
        player.resources = {'wood': 9, 'brick': 9, 'wheat': 9, 'sheep': 9}
        vertex_key = next(iter(game.vertices))

        alice.emit('place_settlement', {'name': acting, 'vertex': vertex_key})

        assert last_error(alice)['code'] == 'NO_PIECES_LEFT'


class TestActingAsAnotherPlayerStillWorks:
    """This group is deliberate: the table trusts each other and wants to be
    able to finish a turn for someone who stepped away."""

    def test_one_client_can_act_for_another_player(self, clients):
        alice, _ = clients
        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        acting = game.players[game.current_player_index].name

        alice.emit('roll_dice', {'name': acting})

        assert game.has_rolled_dice, "acting on behalf of the current player is allowed"

    def test_taking_over_a_seat_switches_the_private_view(self, clients):
        alice, _ = clients
        game = state.session().game
        game.get_player('Bob').resources = {'ore': 4}

        # Alice's socket rejoins as Bob to cover for him. Bob is still
        # connected, so this is an explicit takeover.
        alice.emit('join', {'name': 'Bob', 'role': 'player', 'takeover': True})
        alice.get_received()
        alice.emit('request_state')

        board = events(alice, 'game_state')[-1]['board']
        bob_entry = next(p for p in board['players'] if p['name'] == 'Bob')
        assert bob_entry['is_you'] is True
        assert bob_entry['resources'] == {'ore': 4}


class TestConcurrentJoins:
    def test_simultaneous_joins_do_not_lose_a_player(self, socket_app):
        """Read-modify-write on users.json: both joins used to read the old
        list, append themselves, and the second write dropped the first."""
        import threading

        names = [f"P{i}" for i in range(4)]
        clients = [socketio.test_client(socket_app) for _ in names]

        def join(client, name):
            client.emit('join', {'name': name, 'role': 'player'})

        threads = [threading.Thread(target=join, args=(c, n))
                   for c, n in zip(clients, names, strict=True)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        saved = {u['name'] for u in state.load_users()}
        assert saved == set(names), f"lost players: {set(names) - saved}"


class TestLobbyPresence:
    """A stale users.json must never block a new player.

    The reported bug: four players from a finished session sat in users.json
    forever, so joining an empty lobby was refused with "Max 4 players" while
    the UI correctly showed 0/4.
    """

    def _seed_remembered_users(self, names):
        state.save_users(
            [{'name': n, 'role': 'player', 'color': '#fff'} for n in names]
        )

    def test_joining_an_empty_lobby_is_allowed_despite_remembered_players(self, socket_app):
        self._seed_remembered_users(['A', 'B', 'C', 'D'])

        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'Ruba', 'role': 'player'})

        # get_received() drains, so take one snapshot and read both from it.
        received = client.get_received()
        errors = [m['args'][0] for m in received if m['name'] == 'error']
        lists = [m['args'][0] for m in received if m['name'] == 'user_list']

        assert not errors, f"an empty lobby must accept a player, got {errors}"
        assert [p['name'] for p in lists[-1]['players']] == ['Ruba']

    def test_the_lobby_lists_only_connected_users(self, socket_app):
        self._seed_remembered_users(['Ghost1', 'Ghost2'])

        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'Ruba', 'role': 'player'})

        lists = events(client, 'user_list')
        names = [p['name'] for p in lists[-1]['players']]
        assert 'Ghost1' not in names and 'Ghost2' not in names

    def test_leaving_frees_the_seat(self, socket_app):

        joined = []
        for i in range(4):
            c = socketio.test_client(socket_app)
            c.emit('join', {'name': f'P{i}', 'role': 'player'})
            joined.append(c)

        extra = socketio.test_client(socket_app)
        extra.emit('join', {'name': 'Late', 'role': 'player'})
        assert last_error(extra)['code'] == 'GAME_FULL', "a genuinely full lobby still refuses"

        joined[0].disconnect()

        second = socketio.test_client(socket_app)
        second.emit('join', {'name': 'Late', 'role': 'player'})
        assert last_error(second) is None, "the freed seat must be reusable"

    def test_rejoining_under_the_same_name_does_not_consume_two_seats(self, socket_app):

        clients = []
        for i in range(4):
            c = socketio.test_client(socket_app)
            c.emit('join', {'name': f'P{i}', 'role': 'player'})
            clients.append(c)

        # P0 reconnects on a new socket without the old one having dropped.
        # The real client sends takeover on reconnect for exactly this case.
        again = socketio.test_client(socket_app)
        again.emit('join', {'name': 'P0', 'role': 'player', 'takeover': True})
        assert last_error(again) is None, "reclaiming your own seat is not a new seat"

    def test_a_started_game_seats_only_present_players(self, socket_app):
        self._seed_remembered_users(['Ghost1', 'Ghost2', 'Ghost3'])

        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player'})
        bob.emit('join', {'name': 'Bob', 'role': 'player'})
        alice.emit('start_game')

        assert state.session().game is not None
        seated = {p.name for p in state.session().game.players}
        assert seated == {'Alice', 'Bob'}, f"ghosts were dealt in: {seated}"


class TestNameCollision:
    """Browsers pre-fill the name field, so a second window would silently join
    as the first player and both would view that player's hand. Taking over a
    seat stays supported, but has to be asked for."""

    def test_joining_under_a_connected_name_is_refused(self, socket_app):
        first = socketio.test_client(socket_app)
        first.emit('join', {'name': 'A', 'role': 'player'})

        second = socketio.test_client(socket_app)
        second.emit('join', {'name': 'A', 'role': 'player'})

        assert last_error(second)['code'] == 'NAME_TAKEN'
        assert state.session().viewers.get(second.eio_sid) is None or \
            list(state.session().viewers.values()).count('A') == 1

    def test_explicit_takeover_is_allowed(self, socket_app):
        first = socketio.test_client(socket_app)
        first.emit('join', {'name': 'A', 'role': 'player'})

        second = socketio.test_client(socket_app)
        second.emit('join', {'name': 'A', 'role': 'player', 'takeover': True})

        assert last_error(second) is None, "taking over must still work"

    def test_rejoining_on_the_same_socket_is_not_a_collision(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()

        client.emit('join', {'name': 'A', 'role': 'player'})
        assert last_error(client) is None, "re-joining as yourself is not a takeover"

    def test_four_browsers_keep_four_identities(self, socket_app):
        """The reported bug, end to end."""
        clients = []
        for name in ['A', 'B', 'C', 'D']:
            c = socketio.test_client(socket_app)
            c.emit('join', {'name': name, 'role': 'player'})
            clients.append((name, c))

        assert sorted(state.session().viewers.values()) == ['A', 'B', 'C', 'D']

        clients[0][1].emit('start_game')
        for name, client in clients:
            client.emit('request_state')
            snap = events(client, 'game_state')[-1]
            mine = [p['name'] for p in snap['board']['players'] if p['is_you']]
            assert mine == [name], f"client {name} sees itself as {mine}"


class TestLobbyRules:
    """The table picks house rules before starting; they freeze at start."""

    def test_the_catalogue_is_sent_with_the_selection(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()

        client.emit('request_rules')
        payload = events(client, 'rules_changed')[-1]
        assert payload['catalogue']

    def test_joining_pushes_the_rules_without_asking(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})

        payload = events(client, 'rules_changed')[-1]

        assert payload['catalogue'], "the lobby renders from the server registry"
        assert 'friendly_robber' in payload['selected']
        assert payload['locked'] is False

    def test_changing_a_rule_reaches_every_client(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.get_received()
        b.get_received()

        a.emit('set_rules', {'rules': {'friendly_robber': True, 'victory_target': 12}})

        for client in (a, b):
            payload = events(client, 'rules_changed')[-1]
            assert payload['selected']['friendly_robber'] is True
            assert payload['selected']['victory_target'] == 12

    def test_a_non_member_cannot_change_the_rules(self, socket_app):
        lurker = socketio.test_client(socket_app)
        lurker.emit('set_rules', {'rules': {'friendly_robber': True}})
        assert last_error(lurker)['code'] == 'NOT_IN_LOBBY'

    def test_rules_are_frozen_once_the_game_starts(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {'victory_target': 12}})
        a.emit('start_game')
        a.get_received()

        a.emit('set_rules', {'rules': {'victory_target': 20}})

        assert last_error(a)['code'] == 'GAME_IN_PROGRESS'
        assert state.session().game.victory_points_to_win == 12

    def test_the_chosen_rules_are_applied_to_the_game(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {'friendly_robber': True, 'harbormaster': True}})
        a.emit('start_game')

        game = state.session().game
        assert game.rules['friendly_robber'] is True
        assert game.rules['harbormaster'] is True
        # Harbormaster raises the target by one.
        assert game.victory_points_to_win == 11

    def test_the_board_payload_carries_the_rules(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {'friendly_robber': True}})
        a.emit('start_game')
        a.get_received()

        a.emit('request_state')
        board = events(a, 'game_state')[-1]['board']
        assert board['rules']['friendly_robber'] is True

    def test_friendly_robber_is_enforced_on_the_wire(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {'friendly_robber': True}})
        a.emit('start_game')

        game = state.session().game
        game.game_phase = "playing"
        game.must_move_robber = True
        acting = game.players[game.current_player_index].name

        # Give the other player a settlement and exactly 2 victory points.
        victim = next(p for p in game.players if p.name != acting)
        protected_hex = None
        for vertex_key, vertex in game.vertices.items():
            if vertex.building:
                continue
            land = [h for h in vertex.neighbors.get('hexes', [])
                    if game.hexes.get(h) and game.hexes[h].type not in ('ocean', 'desert')]
            if land:
                vertex.building = {'type': 'settlement', 'player': victim.name}
                victim.settlements.append(vertex_key)
                protected_hex = land[0]
                break
        victim.settlements.append('second')      # 2 victory points exactly
        a.get_received()

        a.emit('move_robber', {'name': acting, 'hex': protected_hex})

        assert last_error(a)['code'] == 'FRIENDLY_ROBBER'
        assert game.robber_hex != protected_hex


class TestEndGame:
    """A game must be escapable. Without this, an abandoned game wedges the
    lobby permanently and only a server restart clears it."""

    def _started(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('start_game')
        a.get_received()
        b.get_received()
        return a, b

    def test_ending_returns_everyone_to_the_lobby(self, socket_app):
        a, b = self._started(socket_app)
        a.emit('end_game')

        assert state.session().game is None
        assert events(a, 'game_ended'), "the ender is told"
        assert events(b, 'game_ended'), "so is everyone else"

    def test_a_new_game_can_be_started_afterwards(self, socket_app):
        a, b = self._started(socket_app)
        a.emit('end_game')
        a.get_received()

        a.emit('start_game')

        assert last_error(a) is None, "the lobby must be usable again"
        assert state.session().game is not None

    def test_ending_with_no_game_is_refused(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()

        client.emit('end_game')
        assert last_error(client)['code'] == 'NO_GAME'

    def test_a_non_member_cannot_end_the_game(self, socket_app):
        a, _ = self._started(socket_app)
        lurker = socketio.test_client(socket_app)
        lurker.emit('end_game')

        assert last_error(lurker)['code'] == 'NOT_IN_LOBBY'
        assert state.session().game is not None

    def test_rules_unlock_after_the_game_ends(self, socket_app):
        a, _ = self._started(socket_app)
        a.emit('end_game')
        a.get_received()

        a.emit('set_rules', {'rules': {'victory_target': 12}})
        assert last_error(a) is None, "rules are editable again in the lobby"


class TestStartingAGame:
    """The lobby must be startable, and say why when it is not."""

    def test_the_lobby_snapshot_says_no_game_is_running(self, socket_app):
        """The client keys the whole lobby/game screen split off this flag;
        without it, joining an empty lobby wedged the Start Game button."""
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})

        snapshot = events(client, 'game_state')[-1]
        assert snapshot['in_game'] is False

    def test_the_lobby_is_told_how_many_players_are_needed(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})

        listing = events(client, 'user_list')[-1]
        assert listing['min_players'] == 2
        assert listing['max_players'] == 4

    def test_one_player_cannot_start_by_default(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()

        client.emit('start_game')
        error = last_error(client)
        assert error['code'] == 'NOT_ENOUGH_PLAYERS'
        assert '1 in the lobby' in error['message'], "say what is actually missing"

    def test_lowering_the_minimum_allows_a_solo_game(self, socket_app):
        """Set min_players to 1 to try the board alone."""
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.emit('set_rules', {'rules': {'min_players': 1}})
        client.get_received()

        client.emit('start_game')

        assert last_error(client) is None
        assert state.session().game is not None
        assert state.session().game.get_player_names() == ['A']

    def test_the_minimum_is_reported_after_it_changes(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()

        client.emit('set_rules', {'rules': {'min_players': 1}})
        listing = events(client, 'user_list')
        # user_list is re-sent on rules change only via join/disconnect, so ask.
        client.emit('request_users')
        listing = events(client, 'user_list')[-1]
        assert listing['min_players'] == 1

    def test_observers_do_not_count_toward_the_minimum(self, socket_app):
        player = socketio.test_client(socket_app)
        watcher = socketio.test_client(socket_app)
        player.emit('join', {'name': 'A', 'role': 'player'})
        watcher.emit('join', {'name': 'W', 'role': 'observer'})
        player.get_received()

        player.emit('start_game')
        assert last_error(player)['code'] == 'NOT_ENOUGH_PLAYERS'


class TestChatAndEventLog:
    def test_chatting_reaches_everyone(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.get_received()
        b.get_received()

        a.emit('chat_message', {'text': 'hello table'})

        for client in (a, b):
            entries = [e['entry'] for e in events(client, 'event_logged')]
            chat = [e for e in entries if e['kind'] == 'chat']
            assert chat[-1]['text'] == 'hello table'
            assert chat[-1]['player'] == 'A'

    def test_a_non_member_cannot_chat(self, socket_app):
        lurker = socketio.test_client(socket_app)
        lurker.emit('chat_message', {'text': 'hi'})
        assert last_error(lurker)['code'] == 'NOT_IN_LOBBY'

    def test_an_empty_message_is_refused(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()

        client.emit('chat_message', {'text': '   '})
        assert last_error(client)['code'] == 'INVALID_PAYLOAD'

    def test_the_timestamp_comes_from_the_server(self, socket_app):
        """A client that owns the clock could otherwise forge history."""
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()

        client.emit('chat_message', {'text': 'hi', 'at': 0, 'id': 999})
        entry = [e['entry'] for e in events(client, 'event_logged')][-1]
        assert entry['at'] > 1_000_000, "server clock, not the client's zero"
        assert entry['id'] != 999

    def test_game_actions_are_logged(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.get_received()
        b.get_received()

        a.emit('start_game')
        kinds = {e['entry']['kind'] for e in events(a, 'event_logged')}
        assert 'game' in kinds, "starting a game is recorded"

    def test_a_reconnecting_client_can_catch_up(self, socket_app):
        a = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        a.emit('chat_message', {'text': 'first'})
        a.emit('chat_message', {'text': 'second'})
        a.get_received()

        a.emit('request_log', {'after_id': 0})
        history = events(a, 'log_history')[-1]['entries']
        texts = [e['text'] for e in history]
        assert 'first' in texts and 'second' in texts

    def test_catch_up_returns_only_newer_entries(self, socket_app):
        a = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        a.emit('chat_message', {'text': 'old'})
        a.get_received()
        marker = state.session().event_log.last_id

        a.emit('chat_message', {'text': 'new'})
        a.get_received()
        a.emit('request_log', {'after_id': marker})

        texts = [e['text'] for e in events(a, 'log_history')[-1]['entries']]
        assert texts == ['new']

    def test_a_bogus_after_id_is_tolerated(self, socket_app):
        a = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        a.get_received()

        a.emit('request_log', {'after_id': 'nonsense'})
        assert events(a, 'log_history'), "falls back to everything rather than erroring"


class TestHandlersToleratePayloads:
    """Socket.IO passes whatever the client emitted straight to the handler.

    A handler declared `def handle_x():` raises TypeError the moment a client
    emits `x` with any payload, and the player sees only a generic server
    error. The tests emitted these events bare, so the gap survived until a
    real browser sent `start_game` with an argument.
    """

    NO_PAYLOAD_EVENTS = [
        'request_users', 'request_rules', 'request_state',
        'end_game', 'start_game', 'refresh_board', 'request_log',
    ]

    def _joined_client(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()
        return client

    @pytest.mark.parametrize("event", NO_PAYLOAD_EVENTS)
    def test_the_event_survives_an_unexpected_payload(self, socket_app, event):
        client = self._joined_client(socket_app)
        client.emit(event, {'anything': True})

        error = last_error(client)
        if error is not None:
            assert error['code'] != 'SERVER_ERROR', (
                f"{event} crashed on a payload: {error['message']}"
            )
        assert client.is_connected()

    @pytest.mark.parametrize("event", NO_PAYLOAD_EVENTS)
    def test_the_event_still_works_with_no_payload(self, socket_app, event):
        client = self._joined_client(socket_app)
        client.emit(event)

        error = last_error(client)
        if error is not None:
            assert error['code'] != 'SERVER_ERROR'
        assert client.is_connected()


class TestServerErrorReporting:
    def test_an_unexpected_error_carries_a_reference(self, socket_app, monkeypatch):
        """A player should be able to quote a code that finds the traceback."""

        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.get_received()

        def boom(*args, **kwargs):
            raise RuntimeError("deliberate")

        # Patch the handler module's reference, not state's: handlers import
        # helpers by value, so replacing state.emit_user_list would not affect
        # the already-bound name inside the handler.
        from handlers import lobby
        monkeypatch.setattr(lobby, 'emit_user_list', boom)
        client.emit('request_users')

        error = last_error(client)
        assert error['code'] == 'SERVER_ERROR'
        assert 'request_users' in error['message'], "name the event that failed"
        assert 'RuntimeError' in error['message'], "name the failure type"
        assert len(error['details']['reference']) == 8


class TestCitiesKnightsOverTheWire:
    def _ck_game(self, socket_app):

        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {'cities_and_knights': True}})
        a.emit('start_game')
        a.get_received()
        b.get_received()
        return a, b

    def test_the_expansion_reaches_the_client(self, socket_app):
        a, _ = self._ck_game(socket_app)
        a.emit('request_state')
        board = events(a, 'game_state')[-1]['board']
        assert board['rules']['cities_and_knights'] is True
        assert board['cities_knights'] is not None
        assert board['cities_knights']['barbarian_track_length'] == 7

    def test_the_base_game_sends_no_expansion_state(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('start_game')
        a.get_received()

        a.emit('request_state')
        board = events(a, 'game_state')[-1]['board']
        assert board['cities_knights'] is None

    def test_the_second_setup_placement_builds_a_city(self, socket_app):
        """The reported gap: the second starting building stayed a settlement."""
        a, _ = self._ck_game(socket_app)
        game = state.session().game

        placed = []
        for _round in range(len(game.players) * 2):
            who = game.players[game._get_setup_player_index()].name
            expected = game.setup_building_type()

            vertex = next(
                key for key, v in game.vertices.items()
                if not v.building
                and not any(game.vertices[n].building
                            for n in v.neighbors.get('vertices', [])
                            if n in game.vertices)
            )
            a.emit('place_settlement', {'name': who, 'vertex': vertex})
            assert game.vertices[vertex].building['type'] == expected, (
                f"round {_round}: expected {expected}"
            )
            placed.append(expected)

            edge = next(
                key for key, e in game.edges.items()
                if not e.road and vertex in e.neighbors.get('vertices', [])
            )
            a.emit('place_road', {'name': who, 'edge': edge})

        assert placed[:2] == ['settlement', 'settlement']
        assert placed[-2:] == ['city', 'city'], "round two builds cities"

        for player in game.players:
            assert len(player.settlements) == 1
            assert len(player.cities) == 1

    def test_buying_an_improvement_works(self, socket_app):
        a, _ = self._ck_game(socket_app)
        game = state.session().game
        game.game_phase = "playing"
        acting = game.players[game.current_player_index].name
        player = game.get_player(acting)
        player.cities.append('a-city')
        player.commodities = {'cloth': 5}
        a.get_received()

        a.emit('buy_improvement', {'name': acting, 'track': 'trade'})

        assert last_error(a) is None
        assert game.ck.level(acting, 'trade') == 1

    def test_an_unaffordable_improvement_says_why(self, socket_app):
        a, _ = self._ck_game(socket_app)
        game = state.session().game
        game.game_phase = "playing"
        acting = game.players[game.current_player_index].name
        game.get_player(acting).cities.append('a-city')
        a.get_received()

        a.emit('buy_improvement', {'name': acting, 'track': 'trade'})

        error = last_error(a)
        assert error['code'] == 'ACTION_REJECTED'
        assert 'cloth' in error['message'], "name what is missing"

    def test_only_the_current_player_may_act(self, socket_app):
        a, _ = self._ck_game(socket_app)
        game = state.session().game
        game.game_phase = "playing"
        other = next(p.name for p in game.players
                     if p.name != game.players[game.current_player_index].name)
        a.get_received()

        a.emit('buy_improvement', {'name': other, 'track': 'trade'})
        assert last_error(a)['code'] == 'NOT_YOUR_TURN'

    def test_the_actions_are_refused_in_the_base_game(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('start_game')
        a.get_received()

        a.emit('buy_improvement', {'name': 'A', 'track': 'trade'})
        assert last_error(a)['code'] == 'WRONG_MODE'

    def test_a_malformed_ck_payload_does_not_crash(self, socket_app):
        a, _ = self._ck_game(socket_app)
        a.get_received()
        for bad in [{}, {'name': 1}, {'name': 'A'}, {'name': 'A', 'track': 5}]:
            a.emit('buy_improvement', bad)
            error = last_error(a)
            assert error is None or error['code'] != 'SERVER_ERROR', bad
        assert a.is_connected()


class TestBarbarianClock:
    """The event die must actually drive the barbarian ship.

    The engine had roll_event_die / advance_barbarians / resolve_barbarian_attack
    fully tested, but nothing called them: the ship never moved, so knights had
    nothing to defend against and the expansion had no clock.
    """

    def _playing_ck_game(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {'cities_and_knights': True}})
        a.emit('start_game')
        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        a.get_received()
        b.get_received()
        return a, game

    def test_rolling_records_the_event_die(self, socket_app):
        a, game = self._playing_ck_game(socket_app)
        acting = game.players[game.current_player_index].name
        a.emit('roll_dice', {'name': acting})
        assert game.ck.last_event is not None, "the third die was rolled"
        assert game.ck.last_red_die is not None

    def test_the_ship_advances_over_many_rolls(self, socket_app):
        a, game = self._playing_ck_game(socket_app)
        start = game.ck.barbarian_position
        moved = False
        for _ in range(30):
            acting = game.players[game.current_player_index].name
            game.has_rolled_dice = False
            a.emit('roll_dice', {'name': acting})
            if game.ck.barbarian_position != start or game.ck.barbarians_have_attacked:
                moved = True
                break
        assert moved, "3 of 6 event faces advance the ship; 30 rolls must move it"

    def test_an_attack_eventually_happens_and_resets(self, socket_app):
        a, game = self._playing_ck_game(socket_app)
        for _ in range(200):
            acting = game.players[game.current_player_index].name
            game.has_rolled_dice = False
            a.emit('roll_dice', {'name': acting})
            if game.ck.barbarians_have_attacked:
                break
        assert game.ck.barbarians_have_attacked, "the ship must reach the island"
        assert game.ck.barbarian_position == 0, "and the track resets"

    def test_a_seven_does_not_move_the_robber_before_the_first_attack(self, socket_app):
        """C&K holds the robber back until the barbarians have landed once."""
        a, game = self._playing_ck_game(socket_app)
        game.ck.barbarians_have_attacked = False
        acting = game.players[game.current_player_index].name

        # Force a 7 without touching the engine's own generator contract.
        rolls = iter([3, 4])
        game.rng.randint = lambda lo, hi: next(rolls, 3)
        a.emit('roll_dice', {'name': acting})

        assert not game.must_move_robber

    def test_a_seven_moves_the_robber_after_the_first_attack(self, socket_app):
        a, game = self._playing_ck_game(socket_app)
        game.ck.barbarians_have_attacked = True
        acting = game.players[game.current_player_index].name

        rolls = iter([3, 4])
        game.rng.randint = lambda lo, hi: next(rolls, 3)
        game.rng.choice = lambda seq: seq[-1]      # a city gate, not a barbarian
        a.emit('roll_dice', {'name': acting})

        assert game.must_move_robber

    def test_knights_can_act_again_next_turn(self, socket_app):
        """ck.start_turn() was never called, so a knight that acted once was
        spent for the rest of the game."""
        from game import cities_knights as ck
        a, game = self._playing_ck_game(socket_app)
        knight = ck.Knight('v1')
        knight.active = True
        knight.acted_this_turn = True
        game.ck.knights[game.players[0].name] = [knight]

        acting = game.players[game.current_player_index].name
        a.emit('next_turn', {'name': acting})

        assert knight.acted_this_turn is False
        assert knight.activated_this_turn is False
