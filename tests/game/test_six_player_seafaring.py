"""Six players, on a board with room for them.

The cap was `MAX_PLAYERS = 4` in `config.py` and nowhere else — the one seating
number the table could not agree on, while `min_players` had always been a
rule. A fifth player was refused at the door, and had the door been opened,
would have been seated in white: `PLAYER_COLORS` held four colours and fell
back to `#ffffff` for everyone after them, so a fifth and a sixth player would
have been the same colour on the board.

`six-shores` is the board they play on. What a player would notice if any of
this broke: being told a six-player lobby is full, or sitting down at a
one-island board where every ship has nowhere to sail.
"""

import json
import os
import random

import pytest
import state
from extensions import socketio
from game import map_store, maps
from game import rules as rules_module
from game.game import Game

SIX = ['Ana', 'Ben', 'Cleo', 'Dev', 'Esi', 'Finn']

# Ships, because three of the four landmasses are across water and
# `maps.start_problems` refuses the map without them.
SIX_PLAYER_RULES = {
    'board_layout': 'custom',
    'board_map': 'six-shores',
    'ships': True,
    'max_players': 6,
}


def six_shores() -> maps.MapDefinition:
    return maps.parse_map(map_store.read_map('six-shores'))


def six_player_game(seed=5) -> Game:
    rules = rules_module.coerce(SIX_PLAYER_RULES)
    return Game(list(SIX), [], rng=random.Random(seed), rules=rules,
                map_definition=six_shores())


def _free_vertex(game, player_name):
    """The first intersection this player may put a starting settlement on."""
    for vertex_key in sorted(game.vertices):
        if game.place_settlement(player_name, vertex_key)['success']:
            return vertex_key
    pytest.fail(f'nowhere left for {player_name} to settle')


def _free_road(game, player_name, vertex_key):
    for edge_key in game.vertices[vertex_key].neighbors['edges']:
        if game.build_road(player_name, edge_key)['success']:
            return edge_key
    pytest.fail(f'nowhere for {player_name} to build from {vertex_key}')


def play_setup(game) -> list:
    """Drive the whole setup phase, returning the seats in placement order."""
    seats = []
    while game.game_phase == 'setup':
        actor = game.current_player_name()
        seats.append(actor)
        vertex_key = _free_vertex(game, actor)
        _free_road(game, actor, vertex_key)
    return seats


class TestTheBoardHasRoomForSix:
    def test_the_map_deals_both_boxes_across_four_landmasses(self):
        """30 terrain hexes and 28 tokens — the 5-6 player extension's two
        boxes — with three of the landmasses out at sea."""
        game = six_player_game()
        land = [h for h in game.hexes.values() if h.type != 'ocean']
        assert len(land) == 30
        assert sorted(h.number for h in land if h.number is not None) == sorted(
            (2,) * 2 + (12,) * 2
            + tuple(n for n in (3, 4, 5, 6, 8, 9, 10, 11) for _ in range(3))
        )
        assert len(set(game.islands().values())) == 4

    def test_every_harbour_in_the_bag_reaches_the_board(self):
        """11 harbours, as the extension's frame holds. A bag bigger than the
        coastline silently drops the ones that do not fit."""
        game = six_player_game()
        placed = sorted(
            edge.port.get('resource', 'generic')
            for edge in game.edges.values() if edge.port
        )
        assert placed == sorted(
            ['generic'] * 5 + ['wood', 'brick', 'sheep', 'sheep', 'wheat', 'ore']
        )

    def test_it_is_a_map_file_and_not_a_layout(self):
        """The format was built for exactly this, and a built-in map has to
        round-trip through it or the editor cannot open the board it ships."""
        defn = six_shores()
        assert maps.parse_map(defn.to_json()) == defn
        assert maps.validate_map(defn)[0] == []

    def test_it_says_whose_scenario_it_is(self):
        """No rulebook prints this board. The `both` card system says so in its
        own summary and so does this."""
        assert "Ours, not a rulebook's" in six_shores().notes

    def test_it_refuses_to_start_without_ships(self):
        without_ships = dict(SIX_PLAYER_RULES, ships=False)
        problems = maps.start_problems(six_shores(), rules_module.coerce(without_ships))
        assert any('Ships' in problem for problem in problems)


class TestSixPlayersCanActuallyPlay:
    def test_every_seat_gets_a_colour_of_its_own(self):
        """A fifth player used to be white, and so did the sixth."""
        colours = [player.color for player in six_player_game().players]
        assert len(set(colours)) == 6
        assert '#ffffff' not in colours

    def test_setup_runs_twice_round_all_six_seats(self):
        """Twelve placements, out and back — the seating order is shuffled at
        the start, so it is the pattern that is pinned, not the names."""
        game = six_player_game()
        game.start()
        seats = play_setup(game)

        order = [player.name for player in game.players]
        assert sorted(order) == sorted(SIX)
        assert seats == order + order[::-1]
        assert game.game_phase == 'playing'
        assert all(len(game.player_settlements[name]) == 2 for name in SIX)

    def test_the_sixth_player_can_take_a_turn(self):
        """Seating six is worth nothing if the turn cycle stops at four."""
        game = six_player_game()
        game.start()
        play_setup(game)

        sixth_seat = game.players[5].name
        for _ in range(5):
            game.set_dice_rolled()
            assert game.advance_turn(game.current_player_name())['success'] is True
        assert game.current_player_name() == sixth_seat

        rolled = game.roll_dice(sixth_seat)
        assert rolled['success'] is True
        assert 2 <= rolled['total'] <= 12


class TestTheCapIsARuleAndNotAConstant:
    def test_a_table_that_says_nothing_keeps_the_servers_own_number(self):
        """0 means "whatever this server is configured with", as the clocks do,
        which is also how a save written before the rule existed loads."""
        assert rules_module.defaults()['max_players'] == 0
        assert rules_module.coerce({})['max_players'] == 0

    def test_the_lobby_refuses_a_fifth_player_by_default(self, socket_app):
        clients = [_joined(socket_app, name) for name in SIX[:4]]
        assert all(client is not None for client in clients)

        fifth = socketio.test_client(socket_app)
        fifth.emit('join', {'name': SIX[4], 'role': 'player'})
        assert _last_error(fifth)['code'] == 'GAME_FULL'

    def test_a_table_that_raises_it_seats_six(self, socket_app):
        host = _joined(socket_app, SIX[0])
        host.emit('set_rules', {'rules': {'max_players': 6}})
        host.get_received()

        for name in SIX[1:]:
            client = _joined(socket_app, name)
            assert _last_error(client) is None, name

        assert len(state.lobby_users()) == 6

    def test_the_seat_count_is_broadcast_to_the_lobby(self, socket_app):
        """The heading used to read "/4" out of the markup."""
        host = _joined(socket_app, SIX[0])
        host.emit('set_rules', {'rules': {'max_players': 6}})
        host.emit('request_users')
        assert _events(host, 'user_list')[-1]['max_players'] == 6


def _joined(socket_app, name):
    client = socketio.test_client(socket_app)
    client.emit('join', {'name': name, 'role': 'player'})
    return client


def _events(client, name):
    return [msg['args'][0] for msg in client.get_received() if msg['name'] == name]


def _last_error(client):
    errors = _events(client, 'error')
    return errors[-1] if errors else None


class TestTheMapShipsAsAFile:
    def test_it_is_in_the_box_and_read_only(self):
        assert 'six-shores' in map_store.builtin_ids()
        path = os.path.join(map_store.BUILTIN_DIR, 'six-shores.json')
        with open(path) as handle:
            assert json.load(handle)['id'] == 'six-shores'
