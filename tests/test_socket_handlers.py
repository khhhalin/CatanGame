"""Socket-layer tests, including the exploits the audit found.

These drive real clients through the real handlers, so they prove the fix at
the boundary a browser actually talks to.
"""

import os
import random

import pytest
import state
from extensions import socketio
from game import buildings, map_store, maps, rate_limit, resources
from game import rules as rules_module
from game.game import Game
from seafarers_board import build_ships_along, give_building, ship_path


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


def seated(name, **clients):
    """The client holding `name`'s seat.

    Turn order is shuffled, so a test that acts for the current player has to
    ask which socket is sitting in that seat — since the fix, no other socket
    can act for them without an explicit takeover.
    """
    return clients[name]


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


def _install_oil_game():
    """Replace the session's game with an Oil Springs game, Alice to move."""
    defn = maps.parse_map(map_store.read_map('oil-springs'))
    rules = dict(rules_module.preset_rules('oil_springs'))
    rules['turn_order'] = 'lobby'
    game = Game(['Alice', 'Bob'], [], rng=random.Random(7), rules=rules,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.game_state = 'started'
    game.current_player_index = 0
    game.set_dice_rolled()
    state.session().game = game
    return game


class TestOilActionsAnnounceAWinImmediately:
    """An oil action that reaches the target must end the game on that action,
    not silently wait for the next roll or build to notice."""

    def test_a_sequester_that_reaches_the_target_wins_now(self, clients):
        alice, bob = clients
        game = _install_oil_game()
        alice_player = game.get_player('Alice')
        alice_player.victory_points = 10   # 10 to the target of 12
        game.oil_sequestered = {'Alice': 2}
        alice_player.oil = 1
        alice.get_received()
        bob.get_received()

        # The third sequestered oil scores 1 (the triple) + 1 (Champion) = 2,
        # crossing 12.
        alice.emit('sequester_oil', {'name': 'Alice'})

        won = events(alice, 'game_won')
        assert won and won[-1]['player'] == 'Alice', won
        assert game.game_state == 'finished'

    def test_a_metropolis_that_reaches_the_target_wins_now(self, clients):
        alice, bob = clients
        game = _install_oil_game()
        vertex_key = next(key for key, vertex in sorted(game.vertices.items())
                          if not vertex.building and vertex.neighbors['hexes'])
        game.vertices[vertex_key].building = {'type': 'city', 'player': 'Alice'}
        alice_player = game.get_player('Alice')
        alice_player.cities.append(vertex_key)   # a city scores 2
        alice_player.victory_points = 9          # 9 + 2 = 11, one short
        alice_player.resources = {'brick': 1, 'wheat': 1, 'ore': 1}
        alice_player.oil = 2
        alice.get_received()
        bob.get_received()

        # The metropolis lifts the city from 2 to 3 points: 11 -> 12.
        alice.emit('build_oil_metropolis', {'name': 'Alice', 'vertex': vertex_key})

        won = events(alice, 'game_won')
        assert won and won[-1]['player'] == 'Alice', won
        assert game.game_state == 'finished'


class TestOilInDevCards:
    """Year of Plenty and Monopoly may name oil on an Oil Springs table."""

    def test_year_of_plenty_can_take_oil_from_the_supply(self, clients):
        alice, _ = clients
        game = _install_oil_game()
        game.pending_invention = 'Alice'
        game.get_player('Alice').oil = 0
        supply_before = game.oil_supply
        alice.get_received()

        alice.emit('use_invention', {'name': 'Alice', 'resources': {'oil': 2}})

        assert last_error(alice) is None
        assert game.get_player('Alice').oil == 2
        assert game.oil_supply == supply_before - 2

    def test_monopoly_can_sweep_oil(self, clients):
        alice, _ = clients
        game = _install_oil_game()
        game.pending_monopoly = 'Alice'
        game.get_player('Alice').oil = 0
        game.get_player('Bob').oil = 3
        alice.get_received()

        alice.emit('use_monopoly', {'name': 'Alice', 'resource_type': 'oil'})

        assert last_error(alice) is None
        assert game.get_player('Alice').oil == 3
        assert game.get_player('Bob').oil == 0

    def test_monopoly_on_oil_respects_the_four_oil_hold_cap(self, clients):
        alice, _ = clients
        game = _install_oil_game()
        game.pending_monopoly = 'Alice'
        game.get_player('Alice').oil = 2
        game.get_player('Bob').oil = 3
        alice.get_received()

        alice.emit('use_monopoly', {'name': 'Alice', 'resource_type': 'oil'})

        # Alice tops up to the cap of 4; Bob keeps the one that would not fit.
        assert game.get_player('Alice').oil == 4
        assert game.get_player('Bob').oil == 1

    def test_oil_is_not_a_monopoly_target_without_the_rule(self, clients):
        """Off an Oil Springs table oil is not a resource, so the base game is
        unchanged — naming it is refused, exactly as naming gold is."""
        alice, _ = clients
        state.session().game.pending_monopoly = 'Alice'
        alice.emit('use_monopoly', {'name': 'Alice', 'resource_type': 'oil'})
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
        alice, bob = clients
        game = state.session().game
        game.game_phase = "playing"

        # Turn order is shuffled, so ask who is actually up rather than
        # assuming — otherwise this fails on NOT_YOUR_TURN half the time.
        game.set_dice_rolled()
        acting = game.players[game.current_player_index].name
        player = game.get_player(acting)
        player.settlements = [f"v{i}" for i in range(game.MAX_SETTLEMENTS)]
        player.resources = {'wood': 9, 'brick': 9, 'wheat': 9, 'sheep': 9}
        vertex_key = next(iter(game.vertices))

        actor = seated(acting, Alice=alice, Bob=bob)
        actor.emit('place_settlement', {'name': acting, 'vertex': vertex_key})

        assert last_error(actor)['code'] == 'NO_PIECES_LEFT'


class TestIdentityComesFromTheConnection:
    """Who is acting is decided by the socket's seat, never by the payload.

    Every handler used to take `data['name']` at face value, so any connected
    client could send another player's name and roll their dice, spend their
    resources or answer their pending choices. Covering for someone who stepped
    away is still supported — but it now means taking their seat on purpose,
    which the table can see in the log.
    """

    def _playing(self, clients):
        alice, bob = clients
        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        acting = game.players[game.current_player_index].name
        return game, acting, seated(acting, Alice=alice, Bob=bob)

    def test_another_players_socket_cannot_roll_for_them(self, clients):
        """The hole: a second socket sent {'name': 'Alice'} and rolled Alice's
        dice."""
        alice, bob = clients
        game, acting, actor = self._playing(clients)
        impostor = bob if actor is alice else alice
        impostor.get_received()

        impostor.emit('roll_dice', {'name': acting})

        assert not game.has_rolled_dice, "the roll was attributed to the sender's seat"
        assert last_error(impostor)['code'] == 'NOT_YOUR_TURN'

    def test_a_socket_with_no_seat_cannot_act(self, socket_app, clients):
        game, acting, _actor = self._playing(clients)
        lurker = socketio.test_client(socket_app)

        lurker.emit('roll_dice', {'name': acting})

        assert not game.has_rolled_dice
        assert last_error(lurker)['code'] == 'NOT_SEATED'

    def test_an_observer_cannot_act_as_a_player(self, socket_app, clients):
        game, acting, _actor = self._playing(clients)
        watcher = socketio.test_client(socket_app)
        watcher.emit('join', {'name': 'Wanda', 'role': 'observer'})
        watcher.get_received()

        watcher.emit('roll_dice', {'name': acting})

        assert not game.has_rolled_dice
        assert last_error(watcher)['code'] == 'NOT_A_PLAYER'

    def test_covering_for_a_player_means_taking_their_seat(self, clients):
        """The feature the table wants, now as a deliberate act: one socket
        joins as the absent player and can then play their turn."""
        alice, bob = clients
        game, acting, actor = self._playing(clients)
        cover = bob if actor is alice else alice

        cover.emit('join', {'name': acting, 'role': 'player', 'takeover': True})
        cover.get_received()
        cover.emit('roll_dice', {'name': acting})

        assert game.has_rolled_dice, "the seat was taken, so the action is theirs"
        assert last_error(cover) is None

    def test_a_takeover_is_announced_to_the_table(self, clients):
        alice, bob = clients

        bob.emit('join', {'name': 'Alice', 'role': 'player', 'takeover': True})

        texts = [e['entry']['text'] for e in events(bob, 'event_logged')]
        assert any('took over' in text and 'Alice' in text for text in texts), texts

    def test_the_socket_that_lost_its_seat_can_no_longer_act(self, clients):
        """Two sockets holding one seat is how the impersonation looked from
        the inside. After a takeover the seat has exactly one holder."""
        alice, bob = clients
        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()

        bob.emit('join', {'name': 'Alice', 'role': 'player', 'takeover': True})
        alice.get_received()
        alice.emit('roll_dice', {'name': 'Alice'})

        assert list(state.session().viewers.values()).count('Alice') == 1
        assert last_error(alice)['code'] == 'NOT_SEATED'

    def test_a_reconnecting_player_recovers_their_seat(self, socket_app, clients):
        """A refresh gives the player a new sid. If the seat did not come back
        with them the game would be unplayable on any dropped connection."""
        alice, bob = clients
        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        acting = game.players[game.current_player_index].name
        seated(acting, Alice=alice, Bob=bob).disconnect()

        again = socketio.test_client(socket_app)
        again.emit('join', {'name': acting, 'role': 'player', 'takeover': True})
        again.get_received()
        again.emit('roll_dice', {'name': acting})

        assert game.has_rolled_dice, "the reconnected socket holds the seat again"
        assert last_error(again) is None

    def test_the_payload_name_is_ignored_in_favour_of_the_seat(self, clients):
        """The client still sends `name` on every event; it must not decide
        anything."""
        alice, bob = clients
        game, acting, actor = self._playing(clients)
        other = next(p.name for p in game.players if p.name != acting)
        actor.get_received()

        actor.emit('roll_dice', {'name': other})

        assert game.has_rolled_dice, "the seat acted, whatever the payload claimed"
        assert last_error(actor) is None

    def test_a_progress_hand_can_only_be_asked_for_by_its_owner(self, socket_app):
        """`request_progress_hand` answered with whatever hand the payload
        named, so any client could read an opponent's cards."""
        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player'})
        bob.emit('join', {'name': 'Bob', 'role': 'player'})
        alice.emit('set_rules', {'preset': 'cities_and_knights'})
        alice.emit('start_game')
        state.session().game.ck.progress_hands['Bob'] = ['spy', 'warlord']
        alice.get_received()

        alice.emit('request_progress_hand', {'name': 'Bob'})

        hand = events(alice, 'progress_hand')[-1]
        assert hand['player'] == 'Alice'
        assert hand['cards'] == [], "Bob's cards stay Bob's"

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
        a.emit('set_rules', {'rules': {'friendly_robber': True, 'harbormaster': True,
                                       'victory_target': 10}})
        a.emit('start_game')

        game = state.session().game
        assert game.rules['friendly_robber'] is True
        assert game.rules['harbormaster'] is True
        assert game.victory_points_to_win == 10, "the lobby's number, not a rule's opinion"

    def test_a_preset_ticks_individual_rules(self, socket_app):
        """A preset is a shortcut. What arrives is the rules, not a mode."""
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.get_received()

        a.emit('set_rules', {'preset': 'cities_and_knights'})

        selected = events(a, 'rules_changed')[-1]['selected']
        assert selected == rules_module.preset_rules('cities_and_knights')
        assert selected['knights'] is True
        assert selected['commodities'] is True
        assert 'cities_and_knights' not in selected

    @pytest.mark.parametrize('preset_id, marker', [
        ('tb_fishermen', 'lake'),
        ('tb_rivers', 'river'),
        ('tb_caravans', 'oasis'),
        ('tb_barbarian_attack', 'castle'),
        ('tb_main', 'castle'),
        ('explorers_and_pirates', None),
    ])
    def test_a_scenario_preset_deals_its_own_board(self, socket_app, preset_id, marker):
        """A scenario preset must deal its scenario map, not a random island.

        The presets set `board_map` but the lobby loads a custom map only when
        `board_layout` is 'custom' — so a table that picked "The Fishermen of
        Catan" got a random board with no fishing grounds, no lake, no oasis, no
        castle, and the scenario was inert. Reproduced against the *generated*
        board: without the fix `map_definition` is None and the marker terrain
        the scenario map guarantees is absent.
        """
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'Alice', 'role': 'player'})
        b.emit('join', {'name': 'Bob', 'role': 'player'})
        a.emit('set_rules', {'preset': preset_id})
        a.emit('start_game')

        game = state.session().game
        assert game is not None, f"{preset_id} did not start a game"
        assert game.map_definition is not None, \
            f"{preset_id} dealt a random board, not its scenario map"
        if marker is not None:
            terrains = {hex_obj.type for hex_obj in game.hexes.values()}
            assert marker in terrains, \
                f"{preset_id} board has no {marker!r} hex — scenario map not dealt"

    def test_the_presets_are_offered_alongside_the_catalogue(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})

        payload = events(client, 'rules_changed')[-1]

        assert [preset['id'] for preset in payload['presets']] == \
            [preset['id'] for preset in rules_module.PRESETS]

    def test_the_exclusion_groups_ride_the_same_broadcast(self, socket_app):
        """The picker decorates and auto-unchecks excluding rows, so it needs
        the groups; they travel on rules_changed with no new event."""
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})

        payload = events(client, 'rules_changed')[-1]

        groups = {group['id']: group for group in payload['exclusions']}
        assert 'longest_line_award' in groups
        assert set(groups['longest_line_award']['rules']) == \
            {'longest_road_card', 'longest_trade_route'}
        assert groups['longest_line_award']['reason']

    def test_an_unknown_preset_is_refused(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})
        client.emit('set_rules', {'preset': 'no_such_preset'})
        assert last_error(client)['code'] == 'UNKNOWN_PRESET'

    def test_a_rule_without_what_it_needs_refuses_the_start(self, socket_app):
        """Metropolis with no improvement tracks can never award anything."""
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {'metropolis': True}})
        a.get_received()

        a.emit('start_game')

        error = last_error(a)
        assert error['code'] == 'INCOHERENT_RULES'
        assert 'City improvements' in error['message'], "name what is missing"
        assert state.session().game is None, "nothing was started"

    def test_a_crafted_both_on_exclusion_refuses_the_start(self, socket_app):
        """The client auto-unchecks a rival live, but a payload that arrives
        with both Longest Road awards on — an old save, a crafted set_rules —
        must be refused, not quietly resolved to trade-route-wins."""
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {
            'ships': True,
            'longest_trade_route': True,
            'longest_road_card': True,
        }})
        a.get_received()

        a.emit('start_game')

        error = last_error(a)
        assert error['code'] == 'INCOHERENT_RULES'
        assert 'Longest Road card' in error['message']
        assert 'Longest Trade Route' in error['message']
        assert state.session().game is None, "nothing was started"

    def test_an_old_client_still_gets_the_game_it_asked_for(self, socket_app):
        """A browser cached from before the decomposition sends one boolean."""
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {'cities_and_knights': True}})
        a.emit('start_game')

        game = state.session().game
        assert game is not None, "the translated set is coherent enough to start"
        assert game.rules['knights'] is True
        assert game.rules['commodities'] is True
        assert 'cities_and_knights' not in game.rules

    def test_a_bought_victory_point_card_can_win_on_the_spot(self, socket_app):
        """With the card counting in hand, nothing else happens afterwards to
        notice the win — the purchase itself has to announce it."""
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('set_rules', {'rules': {
            'victory_point_cards_count_in_hand': True,
            'victory_target': 5,
            # A deck of nothing else, so the draw is the card under test.
            'dev_knights': 0, 'dev_road_building': 0,
            'dev_invention': 0, 'dev_monopoly': 0,
        }})
        a.emit('start_game')

        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        game.set_dice_rolled()
        name = game.players[game.current_player_index].name
        buyer = a if name == 'A' else b
        game.get_player(name).settlements = ['v1', 'v2', 'v3', 'v4']
        game.get_player(name).resources = {'sheep': 1, 'wheat': 1, 'ore': 1}
        a.get_received()
        b.get_received()

        buyer.emit('buy_dev_card', {'name': name})

        won = events(a, 'game_won')
        assert won and won[-1]['player'] == name
        assert won[-1]['victory_points'] == 5

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

        actor = seated(acting, A=a, B=b)
        actor.get_received()
        actor.emit('move_robber', {'name': acting, 'hex': protected_hex})

        assert last_error(actor)['code'] == 'FRIENDLY_ROBBER'
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


class TestSlashCommands:
    """Commands over the wire: who may run one, and what the table is told.

    The engine's own refusals live in tests/game/test_commands.py. These are
    about the boundary — identity comes from the socket, the shared log names
    the runner, and a command cannot buy a client more talking than chat allows.
    """

    def _table(self, socket_app, rules=None):
        """Two players in a started game, with the rules the test asks for."""
        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player'})
        bob.emit('join', {'name': 'Bob', 'role': 'player'})
        if rules:
            alice.emit('set_rules', {'rules': dict(rules)})
        alice.emit('start_game')
        state.session().game.game_phase = 'playing'
        alice.get_received()
        bob.get_received()
        return alice, bob

    def test_the_catalogue_reaches_a_client_that_only_joined(self, socket_app):
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'A', 'role': 'player'})

        listed = events(client, 'commands_changed')[-1]['commands']
        assert [entry['name'] for entry in listed][:1] == ['/help']
        assert all(entry['summary'] for entry in listed)

    def test_the_catalogue_says_which_commands_this_table_allows(self, socket_app):
        alice, bob = self._table(socket_app)
        alice.emit('request_commands')
        listed = {entry['id']: entry
                  for entry in events(alice, 'commands_changed')[-1]['commands']}
        assert listed['add_resource']['available'] is False
        assert 'Chat commands' in listed['add_resource']['unavailable']

        bob.emit('end_game')
        alice.get_received()
        alice.emit('set_rules', {'rules': {'chat_commands': True}})
        alice.emit('start_game')

        listed = {entry['id']: entry
                  for entry in events(alice, 'commands_changed')[-1]['commands']}
        assert listed['add_resource']['available'] is True

    def test_a_socket_with_no_seat_cannot_run_a_command(self, socket_app):
        lurker = socketio.test_client(socket_app)
        lurker.emit('run_command', {'text': '/help'})
        assert last_error(lurker)['code'] == 'NOT_IN_LOBBY'

    def test_the_acting_seat_is_the_socket_s_not_the_payload_s(self, socket_app):
        """The payload's name is a claim; the seat is what the server knows."""
        alice, _bob = self._table(socket_app, {'chat_commands': True})

        alice.emit('run_command', {'text': '/add_resource wood 1', 'name': 'Bob'})

        game = state.session().game
        assert game.get_player('Alice').resources['wood'] == 1
        assert game.get_player('Bob').resources.get('wood', 0) == 0

    def test_a_command_that_changes_the_game_is_logged_for_everyone(self, socket_app):
        alice, bob = self._table(socket_app, {'chat_commands': True})

        alice.emit('run_command', {'text': '/add_resource wood 2'})

        for client in (alice, bob):
            entries = [e['entry'] for e in events(client, 'event_logged')]
            ran = [e for e in entries if e['kind'] == 'command']
            assert ran[-1]['player'] == 'Alice'
            assert 'added 2 wood' in ran[-1]['text']

    def test_the_reply_reaches_only_the_player_who_typed_it(self, socket_app):
        alice, bob = self._table(socket_app)

        alice.emit('run_command', {'text': '/whoami'})

        assert 'Alice' in ' '.join(events(alice, 'command_result')[-1]['lines'])
        assert not events(bob, 'command_result')

    def test_a_refused_command_reaches_only_its_caller(self, socket_app):
        alice, bob = self._table(socket_app)

        alice.emit('run_command', {'text': '/add_resource wood 1'})

        assert last_error(alice)['code'] == 'RULE_IS_OFF'
        assert not events(bob, 'error')
        assert state.session().game.get_player('Alice').resources == {}

    def test_an_observer_may_ask_but_not_act(self, socket_app):
        alice, _bob = self._table(socket_app, {'chat_commands': True})
        watcher = socketio.test_client(socket_app)
        watcher.emit('join', {'name': 'W', 'role': 'observer'})
        watcher.get_received()

        watcher.emit('run_command', {'text': '/help'})
        assert events(watcher, 'command_result'), "watching does not stop you reading"

        watcher.emit('run_command', {'text': '/add_resource wood 1 Alice'})
        assert last_error(watcher)['code'] == 'NOT_A_PLAYER'

    def test_the_board_goes_back_out_after_a_command(self, socket_app):
        """Without the broadcast the cards exist and nobody's screen shows them."""
        alice, bob = self._table(socket_app, {'chat_commands': True})

        alice.emit('run_command', {'text': '/add_resource wheat 1 Bob'})

        board = events(bob, 'board_updated')[-1]['board']
        seat = next(p for p in board['players'] if p['name'] == 'Bob')
        assert seat['resources'] == {'wheat': 1}

    def test_a_command_spends_the_chat_budget(self, socket_app):
        """Otherwise the command bar is a second mouth on the same socket."""
        alice, _bob = self._table(socket_app)
        limit = rate_limit.limit_for('chat_message')
        for _ in range(int(limit.capacity)):
            alice.emit('chat_message', {'text': 'hi'})
        alice.get_received()

        alice.emit('run_command', {'text': '/help'})

        assert last_error(alice)['code'] == 'RATE_LIMITED'
        assert not events(alice, 'command_result')

    def test_a_message_containing_a_slash_is_still_chat(self, socket_app):
        alice, _bob = self._table(socket_app)

        alice.emit('chat_message', {'text': 'back in 5 w/ coffee'})

        entries = [e['entry'] for e in events(alice, 'event_logged')]
        assert entries[-1]['kind'] == 'chat'
        assert entries[-1]['text'] == 'back in 5 w/ coffee'

    def test_a_command_is_not_posted_to_chat(self, socket_app):
        alice, _bob = self._table(socket_app)

        alice.emit('run_command', {'text': '/whoami'})

        entries = [e['entry'] for e in events(alice, 'event_logged')]
        assert not [e for e in entries if e['kind'] == 'chat']

    @pytest.mark.parametrize('payload', [None, {}, {'text': 42}, {'text': '   '},
                                         {'text': 'not a command'}])
    def test_a_malformed_command_payload_is_refused_not_crashed(self, socket_app, payload):
        alice, _bob = self._table(socket_app)

        alice.emit('run_command', payload)

        assert last_error(alice)['code'] in ('INVALID_PAYLOAD', 'NOT_A_COMMAND')
        assert alice.is_connected()

    def test_skipping_a_turn_tells_the_table_whose_turn_it_now_is(self, socket_app):
        alice, bob = self._table(socket_app, {'chat_commands': True})
        game = state.session().game
        was = game.current_player_name()

        seated(was, Alice=alice, Bob=bob).emit('run_command', {'text': '/skip'})

        announced = events(bob, 'turn_changed')[-1]['current_player']
        assert announced == game.current_player_name() != was


class TestHandlersToleratePayloads:
    """Socket.IO passes whatever the client emitted straight to the handler.

    A handler declared `def handle_x():` raises TypeError the moment a client
    emits `x` with any payload, and the player sees only a generic server
    error. The tests emitted these events bare, so the gap survived until a
    real browser sent `start_game` with an argument.
    """

    NO_PAYLOAD_EVENTS = [
        'request_users', 'request_rules', 'request_state', 'request_commands',
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
        a.emit('set_rules', {'preset': 'cities_and_knights'})
        a.emit('start_game')
        a.get_received()
        b.get_received()
        return a, b

    def test_the_expansion_reaches_the_client(self, socket_app):
        a, _ = self._ck_game(socket_app)
        a.emit('request_state')
        board = events(a, 'game_state')[-1]['board']
        assert board['rules']['knights'] is True
        assert board['rules']['commodities'] is True
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
        a, b = self._ck_game(socket_app)
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
            seated(who, A=a, B=b).emit('place_settlement', {'name': who, 'vertex': vertex})
            assert game.vertices[vertex].building['type'] == expected, (
                f"round {_round}: expected {expected}"
            )
            placed.append(expected)

            edge = next(
                key for key, e in game.edges.items()
                if not e.road and vertex in e.neighbors.get('vertices', [])
            )
            seated(who, A=a, B=b).emit('place_road', {'name': who, 'edge': edge})

        assert placed[:2] == ['settlement', 'settlement']
        assert placed[-2:] == ['city', 'city'], "round two builds cities"

        for player in game.players:
            assert len(player.settlements) == 1
            assert len(player.cities) == 1

    def test_buying_an_improvement_works(self, socket_app):
        a, b = self._ck_game(socket_app)
        game = state.session().game
        game.game_phase = "playing"
        game.set_dice_rolled()
        acting = game.players[game.current_player_index].name
        player = game.get_player(acting)
        player.cities.append('a-city')
        player.commodities = {'cloth': 5}
        actor = seated(acting, A=a, B=b)
        actor.get_received()

        actor.emit('buy_improvement', {'name': acting, 'track': 'trade'})

        assert last_error(actor) is None
        assert game.ck.level(acting, 'trade') == 1

    def test_an_unaffordable_improvement_says_why(self, socket_app):
        a, b = self._ck_game(socket_app)
        game = state.session().game
        game.game_phase = "playing"
        game.set_dice_rolled()
        acting = game.players[game.current_player_index].name
        game.get_player(acting).cities.append('a-city')
        actor = seated(acting, A=a, B=b)
        actor.get_received()

        actor.emit('buy_improvement', {'name': acting, 'track': 'trade'})

        error = last_error(actor)
        assert error['code'] == 'ACTION_REJECTED'
        assert 'cloth' in error['message'], "name what is missing"

    def test_only_the_current_player_may_act(self, socket_app):
        a, b = self._ck_game(socket_app)
        game = state.session().game
        game.game_phase = "playing"
        acting = game.players[game.current_player_index].name
        other = next(p.name for p in game.players if p.name != acting)
        waiting = seated(other, A=a, B=b)
        waiting.get_received()

        # Naming the player whose turn it is changes nothing: the action is
        # attributed to the seat this socket holds.
        waiting.emit('buy_improvement', {'name': acting, 'track': 'trade'})
        assert last_error(waiting)['code'] == 'NOT_YOUR_TURN'

    def test_the_actions_are_refused_in_the_base_game(self, socket_app):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        a.emit('start_game')
        a.get_received()

        a.emit('buy_improvement', {'name': 'A', 'track': 'trade'})
        error = last_error(a)
        assert error['code'] == 'RULE_NOT_IN_PLAY'
        assert 'City improvements' in error['message'], "name the rule that is missing"

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
        a.emit('set_rules', {'preset': 'cities_and_knights'})
        a.emit('start_game')
        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        a.get_received()
        b.get_received()
        return a, b, game

    def test_rolling_records_the_event_die(self, socket_app):
        a, b, game = self._playing_ck_game(socket_app)
        acting = game.players[game.current_player_index].name
        seated(acting, A=a, B=b).emit('roll_dice', {'name': acting})
        assert game.ck.last_event is not None, "the third die was rolled"
        assert game.ck.last_red_die is not None

    def test_the_ship_advances_over_many_rolls(self, socket_app):
        a, b, game = self._playing_ck_game(socket_app)
        start = game.ck.barbarian_position
        moved = False
        for _ in range(30):
            acting = game.players[game.current_player_index].name
            game.has_rolled_dice = False
            seated(acting, A=a, B=b).emit('roll_dice', {'name': acting})
            if game.ck.barbarian_position != start or game.ck.barbarians_have_attacked:
                moved = True
                break
        assert moved, "3 of 6 event faces advance the ship; 30 rolls must move it"

    def test_an_attack_eventually_happens_and_resets(self, socket_app):
        a, b, game = self._playing_ck_game(socket_app)
        for _ in range(200):
            acting = game.players[game.current_player_index].name
            game.has_rolled_dice = False
            seated(acting, A=a, B=b).emit('roll_dice', {'name': acting})
            if game.ck.barbarians_have_attacked:
                break
        assert game.ck.barbarians_have_attacked, "the ship must reach the island"
        assert game.ck.barbarian_position == 0, "and the track resets"

    def test_a_seven_does_not_move_the_robber_before_the_first_attack(self, socket_app):
        """C&K holds the robber back until the barbarians have landed once."""
        a, b, game = self._playing_ck_game(socket_app)
        game.ck.barbarians_have_attacked = False
        acting = game.players[game.current_player_index].name

        # Force a 7 without touching the engine's own generator contract.
        rolls = iter([3, 4])
        game.rng.randint = lambda lo, hi: next(rolls, 3)
        seated(acting, A=a, B=b).emit('roll_dice', {'name': acting})

        assert not game.must_move_robber

    def test_a_seven_moves_the_robber_after_the_first_attack(self, socket_app):
        a, b, game = self._playing_ck_game(socket_app)
        game.ck.barbarians_have_attacked = True
        acting = game.players[game.current_player_index].name

        rolls = iter([3, 4])
        game.rng.randint = lambda lo, hi: next(rolls, 3)
        game.rng.choice = lambda seq: seq[-1]      # a city gate, not a barbarian
        seated(acting, A=a, B=b).emit('roll_dice', {'name': acting})

        assert game.must_move_robber

    def test_knights_can_act_again_next_turn(self, socket_app):
        """ck.start_turn() was never called, so a knight that acted once was
        spent for the rest of the game."""
        from game import cities_knights as ck
        a, b, game = self._playing_ck_game(socket_app)
        knight = ck.Knight('v1')
        knight.active = True
        knight.acted_this_turn = True
        game.ck.knights[game.players[0].name] = [knight]

        acting = game.players[game.current_player_index].name
        seated(acting, A=a, B=b).emit('next_turn', {'name': acting})

        assert knight.acted_this_turn is False
        assert knight.activated_this_turn is False


class TestSeafarersOverTheWire:
    """The ship and pirate events at the boundary a browser talks to.

    The engine tests cover the rules; what is checked here is that a client
    can reach them at all, that a table which never took the rule is told so,
    and that a made-up payload cannot get past the handler.
    """

    def _sea_game(self, socket_app, preset='seafarers'):
        a = socketio.test_client(socket_app)
        b = socketio.test_client(socket_app)
        a.emit('join', {'name': 'A', 'role': 'player'})
        b.emit('join', {'name': 'B', 'role': 'player'})
        if preset:
            a.emit('set_rules', {'preset': preset})
        a.emit('start_game')

        game = state.session().game
        game.game_phase = 'playing'
        game.start_turn()
        # Building comes after the dice, so these start where a player would
        # actually be building: their roll already made.
        game.set_dice_rolled()
        a.get_received()
        b.get_received()
        return a, b, game

    def _coastal_settlement(self, game, player_name):
        """Stand a building where a ship can put out to sea from."""
        for vertex_key in sorted(game.vertices):
            vertex = game.vertices[vertex_key]
            sea = [key for key in vertex.neighbors['edges'] if game.is_sea_edge(key)]
            if vertex.neighbors['hexes'] and sea and not vertex.building:
                vertex.building = {'type': 'settlement', 'player': player_name}
                game.get_player(player_name).settlements.append(vertex_key)
                return vertex_key, sorted(sea)[0]
        raise AssertionError('no coastal intersection on this board')

    def test_the_sea_reaches_the_client(self, socket_app):
        a, _b, _game = self._sea_game(socket_app)
        a.emit('request_state')
        board = events(a, 'game_state')[-1]['board']

        assert board['rules']['ships'] is True
        assert board['pirate_hex'] is None
        assert any(edge['ship'] is None for edge in board['edges'].values())

    def test_a_client_can_build_a_ship(self, socket_app):
        a, b, game = self._sea_game(socket_app)
        acting = game.players[game.current_player_index].name
        _vertex, edge_key = self._coastal_settlement(game, acting)
        game.get_player(acting).resources = {'wood': 1, 'sheep': 1}

        seated(acting, A=a, B=b).emit('build_ship', {'name': acting, 'edge': edge_key})

        assert game.edges[edge_key].ship == {'player': acting, 'built_turn': game.turn_count}

    def test_a_table_without_ships_is_told_which_rule_is_missing(self, socket_app):
        a, b, game = self._sea_game(socket_app, preset=None)
        acting = game.players[game.current_player_index].name
        actor = seated(acting, A=a, B=b)

        actor.emit('build_ship', {'name': acting, 'edge': next(iter(game.edges))})

        assert last_error(actor)['code'] == 'RULE_NOT_IN_PLAY'

    def test_a_ship_cannot_be_built_by_naming_someone_elses_turn(self, socket_app):
        """Naming the player who is up buys nothing: the seat acts, and this
        socket's seat is the one waiting."""
        a, b, game = self._sea_game(socket_app)
        acting = game.players[game.current_player_index].name
        waiting = game.players[(game.current_player_index + 1) % len(game.players)].name
        _vertex, edge_key = self._coastal_settlement(game, acting)
        game.get_player(waiting).resources = {'wood': 1, 'sheep': 1}
        impostor = seated(waiting, A=a, B=b)

        impostor.emit('build_ship', {'name': acting, 'edge': edge_key})

        assert game.edges[edge_key].ship is None
        assert last_error(impostor)['code'] == 'NOT_YOUR_TURN'

    def test_a_junk_payload_is_dropped_rather_than_crashing_the_handler(self, socket_app):
        a, b, game = self._sea_game(socket_app)
        acting = game.players[game.current_player_index].name
        actor = seated(acting, A=a, B=b)

        actor.emit('build_ship', {'name': acting, 'edge': None})
        actor.emit('move_ship', {'name': acting, 'from_edge': 'nowhere'})
        actor.emit('move_pirate', {'name': acting, 'hex': ['not', 'a', 'key']})

        assert not any(edge.ship for edge in game.edges.values())
        assert game.pirate_hex is None

    def test_the_pirate_moves_and_offers_the_same_choice_the_robber_does(self, socket_app):
        a, b, game = self._sea_game(socket_app)
        acting = game.players[game.current_player_index].name
        victim = game.players[(game.current_player_index + 1) % len(game.players)].name
        _vertex, edge_key = self._coastal_settlement(game, victim)
        game.edges[edge_key].ship = {'player': victim, 'built_turn': 0}
        game.get_player(victim).ships.append(edge_key)
        game.get_player(victim).resources = {'ore': 1}
        game.must_move_robber = True

        sea_hex = next(
            key for key in game.edges[edge_key].neighbors['hexes']
            if game.hexes[key].type == 'ocean'
        )
        actor = seated(acting, A=a, B=b)
        actor.emit('move_pirate', {'name': acting, 'hex': sea_hex})

        assert game.pirate_hex == sea_hex
        assert events(actor, 'choose_victim')[-1]['victims'] == [victim]

    def test_a_client_can_move_a_ship(self, socket_app):
        """The one action with no equivalent in the base game, so nothing else
        proves the event is wired up at all."""
        a, b, game = self._sea_game(socket_app)
        acting = game.players[game.current_player_index].name
        vertex, from_edge = self._coastal_settlement(game, acting)
        game.edges[from_edge].ship = {'player': acting, 'built_turn': game.turn_count - 1}
        game.get_player(acting).ships.append(from_edge)
        to_edge = next(
            key for key in sorted(game.vertices[vertex].neighbors['edges'])
            if key != from_edge and game.is_sea_edge(key)
        )

        seated(acting, A=a, B=b).emit(
            'move_ship', {'name': acting, 'from_edge': from_edge, 'to_edge': to_edge})

        assert game.edges[from_edge].ship is None
        assert game.edges[to_edge].ship['player'] == acting

    def test_a_ship_that_claims_the_trade_route_ends_the_game(self, socket_app):
        """The Longest Trade Route is worth two points, so the fifth ship of a
        route can be the winning move. Nothing else tells the table it is over:
        the win is announced from the handler, not drawn from the board."""
        a, b, game = self._sea_game(socket_app)
        acting = game.players[game.current_player_index].name
        vertex, _first = self._coastal_settlement(game, acting)

        route, _vertices = ship_path(game, vertex, 5)
        build_ships_along(game, acting, route[:-1])
        player = game.get_player(acting)
        player.resources = {'wood': 1, 'sheep': 1}
        # Two short of the target, so only the card can carry them over it.
        player.victory_points = game.rules['victory_target'] - 2

        actor = seated(acting, A=a, B=b)
        actor.emit('build_ship', {'name': acting, 'edge': route[-1]})

        assert game.longest_road_holder == acting
        assert events(actor, 'game_won')[-1]['player'] == acting


class TestAnsweringAPendingChoice:
    """`make_choice` is the one way out of the choice phase, so it is also the
    one place an untrusted answer could rewrite somebody else's board."""

    def _ck_game(self, socket_app):
        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player'})
        bob.emit('join', {'name': 'Bob', 'role': 'player'})
        alice.emit('set_rules', {'preset': 'cities_and_knights'})
        alice.emit('start_game')
        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        game.set_dice_rolled()
        alice.get_received()
        bob.get_received()
        return alice, bob, game

    def _barbarians_take_a_city(self, game, owner='Alice'):
        """A lost attack against a player holding two cities, so they choose."""
        first, second = sorted(game.vertices)[:2]
        player = game.get_player(owner)
        for vertex_key in (first, second):
            game.vertices[vertex_key].building = {'type': 'city', 'player': owner}
            player.cities.append(vertex_key)
        game.resolve_barbarian_attack()
        return first, second

    def test_the_player_who_was_asked_can_answer(self, socket_app):
        alice, _bob, game = self._ck_game(socket_app)
        first, second = self._barbarians_take_a_city(game)

        alice.emit('make_choice', {'name': 'Alice', 'kind': 'barbarian_city',
                                   'option': second})

        assert game.get_player('Alice').cities == [first]
        assert game.pending_choices == []
        assert events(alice, 'choice_resolved')[-1]['player'] == 'Alice'

    def test_another_player_cannot_answer_for_them(self, socket_app):
        _alice, bob, game = self._ck_game(socket_app)
        first, second = self._barbarians_take_a_city(game)

        bob.emit('make_choice', {'name': 'Bob', 'kind': 'barbarian_city', 'option': second})

        assert last_error(bob)['code'] == 'NO_CHOICE_PENDING'
        assert game.get_player('Alice').cities == [first, second]

    def test_an_option_that_was_never_offered_is_refused(self, socket_app):
        alice, _bob, game = self._ck_game(socket_app)
        first, second = self._barbarians_take_a_city(game)
        stranger = next(k for k in sorted(game.vertices) if k not in (first, second))

        alice.emit('make_choice', {'name': 'Alice', 'kind': 'barbarian_city',
                                   'option': stranger})

        assert last_error(alice)['code'] == 'INVALID_CHOICE'
        assert game.get_player('Alice').cities == [first, second]

    def test_an_unknown_kind_is_refused_before_the_engine_sees_it(self, socket_app):
        alice, _bob, game = self._ck_game(socket_app)
        self._barbarians_take_a_city(game)

        alice.emit('make_choice', {'name': 'Alice', 'kind': 'nonsense', 'option': 'x'})

        assert last_error(alice)['code'] == 'INVALID_PAYLOAD'

    def test_a_junk_payload_is_dropped_rather_than_crashing_the_handler(self, socket_app):
        alice, _bob, game = self._ck_game(socket_app)
        self._barbarians_take_a_city(game)

        for bad in ({}, {'name': 5}, {'name': 'Alice'},
                    {'name': 'Alice', 'kind': 'barbarian_city', 'option': []}):
            alice.emit('make_choice', bad)
            error = last_error(alice)
            assert error is None or error['code'] != 'SERVER_ERROR', bad
        assert alice.is_connected()

    def test_the_table_is_told_who_it_is_waiting_for(self, socket_app):
        alice, bob, game = self._ck_game(socket_app)
        self._barbarians_take_a_city(game)

        bob.emit('request_state')
        waiting = events(bob, 'game_state')[-1]['board']['pending_choices']

        assert [entry['player'] for entry in waiting] == ['Alice']
        assert 'options' not in waiting[0] or waiting[0]['options'] is None

    def test_nobody_can_build_while_the_game_is_waiting(self, socket_app):
        """Even the player whose turn it is: the game has stopped on a
        question, and building around it would spend cards the answer moves."""
        alice, bob, game = self._ck_game(socket_app)
        self._barbarians_take_a_city(game)
        acting = game.players[game.current_player_index].name
        actor = seated(acting, Alice=alice, Bob=bob)
        actor.get_received()

        actor.emit('buy_improvement', {'name': acting, 'track': 'trade'})

        assert last_error(actor)['code'] in ('MUST_CHOOSE', 'AWAITING_CHOICE')


class TestCommoditiesReachTheTradeHandler:
    """The bug: `propose_trade` validated with `clean_resource_counts`, which
    knows only the five resources, so a player holding three paper could not
    put any of it on the table — the payload bounced as INVALID_PAYLOAD before
    the engine ever saw it."""

    def _on_turn(self, clients):
        alice, bob = clients
        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        acting = game.players[game.current_player_index].name
        # Trading is only legal after the roll, and this is about the payload,
        # not about the dice.
        game.set_dice_rolled()
        actor = seated(acting, Alice=alice, Bob=bob)
        actor.get_received()
        return game, acting, actor

    def test_a_commodity_offer_is_accepted_from_a_browser(self, clients):
        game, acting, actor = self._on_turn(clients)
        game.get_player(acting).commodities = {'paper': 3}

        actor.emit('propose_trade', {'name': acting, 'offered': {'paper': 1},
                                     'wanted': {'wood': 1}})

        # One drain: `events` empties the queue, so both facts come from it.
        received = [msg['name'] for msg in actor.get_received()]
        assert 'error' not in received
        assert 'trade_proposed' in received, "the offer reached the table"

    def test_four_paper_settles_against_the_bank(self, clients):
        game, acting, actor = self._on_turn(clients)
        game.get_player(acting).commodities = {'paper': 4}

        actor.emit('propose_trade', {'name': acting, 'offered': {'paper': 4},
                                     'wanted': {'wood': 1}})

        completed = events(actor, 'bank_trade_completed')
        assert completed and completed[-1]['rate_used'] == 4
        assert game.get_player(acting).resources['wood'] == 1

    def test_a_card_type_nobody_ever_holds_is_still_refused(self, clients):
        """The allowlist is eight names wide now, not open."""
        _game, acting, actor = self._on_turn(clients)

        actor.emit('propose_trade', {'name': acting, 'offered': {'gold': 1},
                                     'wanted': {'wood': 1}})

        assert last_error(actor)['code'] == 'INVALID_PAYLOAD'

    def test_a_commodity_the_player_does_not_hold_is_refused(self, clients):
        """Untrusted input: the payload names the card, the server owns the
        hand."""
        _game, acting, actor = self._on_turn(clients)

        actor.emit('propose_trade', {'name': acting, 'offered': {'cloth': 2},
                                     'wanted': {'wood': 1}})

        assert last_error(actor)['code'] == 'INSUFFICIENT_RESOURCES'


class TestGoldIsTradeableBetweenPlayers:
    """The gap: both gold economies (E&P `gold`, T&B `gold_coins`) make gold
    tradeable player-to-player, but gold is a scalar on `Player.gold`, not a card
    in the hand, and the trade payload only moved resources. So a player could
    not put gold on either side of an offer — it had no way to be expressed, and
    nothing crossed."""

    def _gold_turn(self, clients, rule='gold'):
        alice, bob = clients
        game = state.session().game
        game.rules['gold'] = False
        game.rules['gold_coins'] = False
        game.rules[rule] = True
        game.game_phase = "playing"
        game.start_turn()
        acting = game.players[game.current_player_index].name
        other_name = 'Bob' if acting == 'Alice' else 'Alice'
        game.set_dice_rolled()
        actor = seated(acting, Alice=alice, Bob=bob)
        other = seated(other_name, Alice=alice, Bob=bob)
        actor.get_received()
        other.get_received()
        return game, acting, other_name, actor, other

    def _offer_id(self, actor):
        proposed = events(actor, 'trade_proposed')
        assert proposed, "the offer never reached the table"
        return proposed[-1]['offer']['id']

    def test_offered_gold_crosses_to_the_accepter(self, clients):
        game, acting, other, actor, taker = self._gold_turn(clients)
        game.get_player(acting).gold = 5
        game.get_player(acting).resources = {}
        game.get_player(other).gold = 1
        game.get_player(other).resources = {'wood': 2}

        actor.emit('propose_trade', {'name': acting, 'offered': {},
                                     'offered_gold': 3, 'wanted': {'wood': 1}})
        offer_id = self._offer_id(actor)
        taker.emit('accept_trade', {'name': other, 'offer_id': offer_id})
        actor.emit('complete_trade', {'name': acting, 'offer_id': offer_id,
                                      'selected_responder': other})

        # Against the live players, never a copied literal: exactly 3 gold left
        # the proposer and reached the taker, and the wood came back the other way.
        assert game.get_player(acting).gold == 2
        assert game.get_player(other).gold == 4
        assert game.get_player(acting).resources.get('wood', 0) == 1
        assert game.get_player(other).resources.get('wood', 0) == 1

    def test_wanted_gold_crosses_from_the_accepter(self, clients):
        game, acting, other, actor, taker = self._gold_turn(clients, rule='gold_coins')
        game.get_player(acting).gold = 0
        game.get_player(acting).resources = {'ore': 2}
        game.get_player(other).gold = 4
        game.get_player(other).resources = {}

        actor.emit('propose_trade', {'name': acting, 'offered': {'ore': 1},
                                     'wanted': {}, 'wanted_gold': 2})
        offer_id = self._offer_id(actor)
        taker.emit('accept_trade', {'name': other, 'offer_id': offer_id})
        actor.emit('complete_trade', {'name': acting, 'offer_id': offer_id,
                                      'selected_responder': other})

        assert game.get_player(acting).gold == 2
        assert game.get_player(other).gold == 2
        assert game.get_player(acting).resources.get('ore', 0) == 1
        assert game.get_player(other).resources.get('ore', 0) == 1

    def test_offering_more_gold_than_held_is_refused(self, clients):
        game, acting, other, actor, _taker = self._gold_turn(clients)
        game.get_player(acting).gold = 1
        game.get_player(acting).resources = {}

        actor.emit('propose_trade', {'name': acting, 'offered': {},
                                     'offered_gold': 3, 'wanted': {'wood': 1}})

        assert last_error(actor)['code'] == 'INSUFFICIENT_GOLD'
        assert game.get_player(acting).gold == 1

    def test_a_base_game_refuses_gold_in_the_payload(self, clients):
        alice, bob = clients
        game = state.session().game
        game.rules['gold'] = False
        game.rules['gold_coins'] = False
        game.game_phase = "playing"
        game.start_turn()
        acting = game.players[game.current_player_index].name
        game.set_dice_rolled()
        actor = seated(acting, Alice=alice, Bob=bob)
        game.get_player(acting).gold = 5
        game.get_player(acting).resources = {'wood': 1}
        actor.get_received()

        actor.emit('propose_trade', {'name': acting, 'offered': {'wood': 1},
                                     'offered_gold': 2, 'wanted': {'ore': 1}})

        # No gold rule in play, so gold in the payload is refused rather than
        # moved: nothing left the proposer's purse.
        assert last_error(actor)['code'] == 'GOLD_RULE_OFF'
        assert game.get_player(acting).gold == 5


class TestTheLogSaysWhoTheRollPaid:
    """The bug: a roll logged "Alice rolled 3 + 3 = 6" and nothing else, so no
    player could tell what it had paid them — which is also how a production
    bug hides."""

    def _rolling(self, clients, faces):
        from tests.conftest import ScriptedRandom

        alice, bob = clients
        game = state.session().game
        game.rng = ScriptedRandom(faces)
        game.game_phase = "playing"
        game.start_turn()
        acting = game.players[game.current_player_index].name
        actor = seated(acting, Alice=alice, Bob=bob)
        actor.get_received()
        return game, acting, actor

    def _settle_on_six(self, game, name):
        """One settlement paying on a 6 and on nothing else.

        The other hexes the intersection touches are moved off every number
        this test rolls: an intersection borders three hexes, and leaving their
        numbers alone made "the roll paid nobody" depend on which numbers the
        shuffle happened to deal.
        """
        for vertex_key in sorted(game.vertices):
            vertex = game.vertices[vertex_key]
            producing = [
                key for key in vertex.neighbors.get('hexes', [])
                if key in game.hexes and game.hexes[key].number
                and game.hexes[key].type not in ('desert', 'ocean')
            ]
            if not producing:
                continue
            for key in producing[1:]:
                game.hexes[key].number = 12
            paying = game.hexes[producing[0]]
            paying.number = 6
            vertex.building = {'type': 'settlement', 'player': name}
            if game.robber_hex in producing:
                game.robber_hex = None
            return paying.type
        raise AssertionError("no producing hex on this board")

    def test_the_log_names_the_player_and_the_card(self, clients):
        game, acting, actor = self._rolling(clients, [3, 3])
        resource = self._settle_on_six(game, acting)

        actor.emit('roll_dice', {'name': acting})

        entries = [e['entry'] for e in events(actor, 'event_logged')]
        production = [e for e in entries if 'gained' in e['details']]
        assert len(production) == 1, "one entry for the whole table, not one per player"
        assert production[0]['details']['gained'] == {acting: {resource: 1}}
        assert f"+1 {resource}" in production[0]['text']
        assert acting in production[0]['text']

    def test_a_roll_that_paid_nobody_says_so(self, clients):
        game, acting, actor = self._rolling(clients, [2, 3])
        self._settle_on_six(game, acting)

        actor.emit('roll_dice', {'name': acting})

        entries = [e['entry'] for e in events(actor, 'event_logged')]
        production = [e for e in entries if 'gained' in e['details']]
        assert production[0]['details']['gained'] == {}
        assert 'nobody' in production[0]['text']

    def test_everyone_sees_the_same_entry(self, clients):
        """Shared history: the log is one record, not a private receipt."""
        alice, bob = clients
        game, acting, actor = self._rolling(clients, [3, 3])
        self._settle_on_six(game, acting)
        bob.get_received()
        alice.get_received()

        actor.emit('roll_dice', {'name': acting})

        seen = []
        for client in (alice, bob):
            entries = [e['entry'] for e in events(client, 'event_logged')]
            seen.append([e['text'] for e in entries if 'gained' in e['details']])
        assert seen[0] == seen[1] and seen[0], seen


class TestMovementPhaseOverTheWire:
    """Once a ship has moved, the build handlers refuse over the wire (851-862).

    The refusal lives on the engine build methods; this proves it survives the
    trip through the real building handler to the offending client, coded so the
    UI can act on it. The engine sets `turn_phase` to 'movement' when a transport
    ship sails; the handler for that move lands in a later wave, so the state a
    moved ship leaves is set on the live game directly.
    """

    def test_a_build_after_movement_is_refused_to_the_client(self, clients):
        alice, bob = clients
        game = state.session().game
        game.game_phase = "playing"
        game.rules['movement_phase'] = True
        game.set_dice_rolled()
        acting = game.players[game.current_player_index].name
        game.get_player(acting).resources = {'wood': 9, 'brick': 9, 'wheat': 9, 'sheep': 9}
        # A transport ship has already sailed this turn.
        game.turn_phase = 'movement'

        actor = seated(acting, Alice=alice, Bob=bob)
        actor.emit('place_road', {'name': acting, 'edge': next(iter(game.edges))})

        assert last_error(actor)['code'] == 'MOVEMENT_STARTED'

    def test_the_wire_build_is_unaffected_with_the_rule_off(self, clients):
        """The same moved-ship state without `movement_phase` does not lock the
        handler: the base game turn is untouched over the wire."""
        alice, bob = clients
        game = state.session().game
        game.game_phase = "playing"
        game.set_dice_rolled()
        acting = game.players[game.current_player_index].name
        game.turn_phase = 'movement'  # set, but the rule that reads it is off

        actor = seated(acting, Alice=alice, Bob=bob)
        actor.emit('place_road', {'name': acting, 'edge': next(iter(game.edges))})

        # It bounces on a real placement rule, never on the movement lock.
        assert last_error(actor)['code'] != 'MOVEMENT_STARTED'


class TestRegistryImport:
    """Uploading an edited registry over the wire (`import_registry`).

    The write-back half of the Download routes: a valid file must reach the live
    registry every Game reads from — a retint and a reprice both — and a
    malformed one must be refused without touching disk or the defaults. Each
    import writes a *process-global* override file, so a leak would reprice every
    later test's board; the cleanup fixture deletes both files and reloads the
    built-ins after every test here.
    """

    @pytest.fixture(autouse=True)
    def restore_registries(self):
        yield
        for module in (resources, buildings):
            if os.path.exists(module._PATH):
                os.remove(module._PATH)
            module.reload()

    @pytest.fixture
    def author(self, socket_app):
        """A joined lobby client — the import needs a seated viewer, no game."""
        client = socketio.test_client(socket_app)
        client.emit('join', {'name': 'Author', 'role': 'player'})
        client.get_received()
        return client

    def test_a_resources_import_retints_wood_and_adds_a_key(self, author):
        payload = {
            'wood': {'color': '#123456'},
            'obsidian': {'name': 'Obsidian', 'color': '#0b0b14',
                         'symbol': '', 'pattern': 'stipple'},
        }
        author.emit('import_registry', {'kind': 'resources', 'data': payload})

        received = author.get_received()
        assert not [msg for msg in received if msg['name'] == 'error']
        acks = [msg['args'][0] for msg in received if msg['name'] == 'registry_imported']
        assert acks[-1] == {'kind': 'resources', 'count': 2}
        registry = resources.registry()
        # The override merges over the default rather than replacing it: the new
        # colour lands, the untouched name survives, and the brand-new key exists.
        assert registry['wood']['color'] == '#123456'
        assert registry['wood']['name'] == 'Wood'
        assert registry['obsidian']['name'] == 'Obsidian'
        assert os.path.exists(resources._PATH)

    def test_a_buildings_import_reprices_and_reaches_get_cost(self, author):
        payload = {'road': {'name': 'Track', 'cost': {'wood': 3}}}
        author.emit('import_registry', {'kind': 'buildings', 'data': payload})

        assert last_error(author) is None
        assert buildings.registry()['road']['name'] == 'Track'
        # The import reaches the *price path*, not just the display registry: a
        # board dealt after it charges the new cost through the engine's own
        # get_cost, which is what a player actually pays.
        game = Game(['A', 'B'], [], rng=random.Random(1))
        assert game.get_cost('road') == {'wood': 3}

    def test_a_malformed_payload_is_refused_and_writes_nothing(self, author):
        default_wood = resources.DEFAULT_RESOURCES['wood']['color']
        for bad in (
            {'kind': 'resources', 'data': ['not', 'a', 'dict']},
            {'kind': 'resources', 'data': {'wood': 'not a dict'}},
            {'kind': 'nonsense', 'data': {}},
        ):
            author.emit('import_registry', bad)
            assert last_error(author) is not None

        assert not os.path.exists(resources._PATH)
        assert resources.registry()['wood']['color'] == default_wood

    def test_too_many_keys_is_refused_before_it_reaches_disk(self, author):
        payload = {str(n): {'name': str(n)} for n in range(600)}
        author.emit('import_registry', {'kind': 'buildings', 'data': payload})

        assert last_error(author)['code'] == 'INVALID_REGISTRY'
        assert not os.path.exists(buildings._PATH)


def _wonders_socket_game():
    """A started Wonders game with Alice on the turn, dice rolled, ready to build.

    Alice already holds two cities, so the Theater's requirement is met; the
    hand is set per test. Turn order is the lobby's, so Alice sits in seat 0 and
    the sockets seated as Alice and Bob keep acting for themselves.
    """
    defn = maps.parse_map(map_store.read_map('wonders-of-catan'))
    chosen = dict(rules_module.preset_rules('wonders_of_catan'))
    chosen['turn_order'] = 'lobby'
    chosen['board_layout'] = 'custom'
    chosen['board_map'] = 'wonders-of-catan'
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0  # Alice
    game.start_turn()
    game.set_dice_rolled()
    cities = [key for key in sorted(game.vertices)
              if game.vertices[key].neighbors['hexes']
              and not game.is_wonder_marker(key)][:2]
    for vertex_key in cities:
        give_building(game, 'Alice', vertex_key, 'city')
    return game


class TestBuildingAWonderOverTheWire:
    """`build_wonder_level` reached through the real handler: the boundary a
    browser talks to. The engine's own correctness is tests/game/test_wonders.py."""

    @pytest.fixture
    def wonders_clients(self, clients):
        alice, bob = clients
        state.session().game = _wonders_socket_game()
        alice.get_received()
        bob.get_received()
        return alice, bob

    def test_starting_a_wonder_pays_the_hand_and_broadcasts(self, wonders_clients):
        alice, _ = wonders_clients
        state.session().game.get_player('Alice').resources = {
            'sheep': 3, 'brick': 1, 'wood': 1}

        alice.emit('build_wonder_level', {'name': 'Alice', 'wonder': 'theater'})
        received = alice.get_received()

        assert not [m for m in received if m['name'] == 'error'], 'the build errored'
        assert [m for m in received if m['name'] == 'board_updated'], \
            'a successful build did not broadcast the board'
        game = state.session().game
        assert game.wonder_choice['Alice'] == 'theater'
        assert game.wonder_level_of('Alice') == 1
        assert game.get_player('Alice').resources.get('sheep', 0) == 0

    def test_an_unaffordable_wonder_is_refused_by_the_engine(self, wonders_clients):
        alice, _ = wonders_clients
        state.session().game.get_player('Alice').resources = {}

        alice.emit('build_wonder_level', {'name': 'Alice', 'wonder': 'theater'})

        error = last_error(alice)
        assert error is not None and error['code'] == 'INSUFFICIENT_RESOURCES', error
        assert 'Alice' not in state.session().game.wonder_choice

    def test_a_player_cannot_build_on_another_players_turn(self, wonders_clients):
        _, bob = wonders_clients
        # Bob's socket cannot act for Alice's seat: it is refused as not his turn,
        # so a Wonder is never started off-turn from another connection.
        bob.emit('build_wonder_level', {'name': 'Bob', 'wonder': 'cathedral'})

        error = last_error(bob)
        assert error is not None and error['code'] == 'NOT_YOUR_TURN', error
        assert state.session().game.wonder_choice == {}

    def test_the_base_game_refuses_the_wonder_build(self, clients):
        alice, _ = clients
        alice.emit('build_wonder_level', {'name': 'Alice', 'wonder': 'theater'})
        error = last_error(alice)
        assert error is not None, 'a base game accepted a Wonder build'


class TestTradeResponsesReachEveryone:
    """The v3.7.0 tester's report: "deny nie jest responsywne", "all players
    should see which players already agreed to a trade or denied it", and "if
    every not-proposing player denies a trade offer it should disappear".

    The decline handler recorded the refusal on the offer but never broadcast
    the board, so no screen updated: a Deny was invisible to the denier and to
    everyone else, and an offer every responder had refused stayed on the table
    forever. This drives three real sockets through the handlers and reads the
    board each one is actually sent.
    """

    def _three_player_turn(self, socket_app):
        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)
        carol = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player'})
        bob.emit('join', {'name': 'Bob', 'role': 'player'})
        carol.emit('join', {'name': 'Carol', 'role': 'player'})
        alice.emit('start_game')

        game = state.session().game
        game.game_phase = "playing"
        game.start_turn()
        game.set_dice_rolled()

        clients = {'Alice': alice, 'Bob': bob, 'Carol': carol}
        proposer = game.players[game.current_player_index].name
        responders = [n for n in ('Alice', 'Bob', 'Carol') if n != proposer]

        # A one-for-one no bank rate would settle, so it stands as a live offer
        # waiting on the table's answer rather than paying out at once.
        game.get_player(proposer).resources = {'wood': 1}
        for responder in responders:
            game.get_player(responder).resources = {'brick': 1}

        for client in clients.values():
            client.get_received()
        return game, clients, proposer, responders

    def _offer_active_for(self, client):
        updates = events(client, 'board_updated')
        assert updates, "no board update reached this client"
        return updates[-1]['board']['trades']['active']

    def test_a_deny_rides_the_broadcast_and_a_full_deny_clears_the_offer(
        self, socket_app
    ):
        game, clients, proposer, responders = self._three_player_turn(socket_app)
        first, second = responders

        clients[proposer].emit('propose_trade', {
            'name': proposer, 'offered': {'wood': 1}, 'wanted': {'brick': 1},
        })
        offer_id = events(clients[proposer], 'trade_proposed')[-1]['offer']['id']
        for client in clients.values():
            client.get_received()

        # One responder denies. Every client — the denier, the proposer and the
        # still-pending responder — is sent a board carrying that refusal, and
        # the offer stays live because someone might still take it.
        clients[first].emit('decline_trade', {'name': first, 'offer_id': offer_id})
        for name, client in clients.items():
            active = self._offer_active_for(client)
            assert len(active) == 1, f"{name} lost the still-live offer"
            assert active[0]['accepted_by'].get(first) is False, (
                f"{name} was not told {first} denied"
            )
            assert second not in active[0]['accepted_by'], (
                f"{name} saw {second} as having answered when they had not"
            )
        for client in clients.values():
            client.get_received()

        # The last responder denies too: now no non-proposer could take it, so it
        # comes off the table for everyone, the proposer included.
        clients[second].emit('decline_trade', {'name': second, 'offer_id': offer_id})
        for name, client in clients.items():
            assert self._offer_active_for(client) == [], (
                f"{name} still sees an offer every responder denied"
            )
