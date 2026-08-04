"""The map editor's events, driven through the real handlers.

A map arriving over a socket is untrusted input with exactly the status of a
`place_settlement` payload, and unlike one it becomes a filename. These tests
are at the boundary a browser talks to for that reason.
"""

import os

import pytest
import state
from extensions import socketio
from game import map_store

from .test_maps import make_map, region_named


@pytest.fixture(autouse=True)
def clean_maps_dir():
    def wipe():
        if os.path.isdir(map_store.MAPS_DIR):
            for name in os.listdir(map_store.MAPS_DIR):
                os.remove(os.path.join(map_store.MAPS_DIR, name))
    wipe()
    yield
    wipe()


def events(client, name):
    return [msg['args'][0] for msg in client.get_received() if msg['name'] == name]


def last_error(client):
    errors = events(client, 'error')
    return errors[-1] if errors else None


def joined(socket_app, name='A'):
    client = socketio.test_client(socket_app)
    client.emit('join', {'name': name, 'role': 'player'})
    client.get_received()
    return client


class TestListingMaps:
    def test_the_builtins_are_offered_without_anybody_saving_one(self, socket_app):
        client = joined(socket_app)
        client.emit('request_maps')
        listed = events(client, 'map_list')[-1]['maps']
        assert 'standard' in {row['id'] for row in listed}

    def test_a_saved_map_reaches_the_rules_picker(self, socket_app):
        """The picker's options come off disk, which is the whole reason
        `board_map` is a rule: a map saved a second ago is selectable with no
        front-end change at all."""
        client = joined(socket_app)
        client.emit('save_map', {'map': make_map()})

        selectable = {
            option['id']
            for rule in events(client, 'rules_changed')[-1]['catalogue']
            if rule['id'] == 'board_map'
            for option in rule['options']
        }
        assert 'test-map' in selectable


class TestSaving:
    def test_a_lurker_cannot_save(self, socket_app):
        lurker = socketio.test_client(socket_app)
        lurker.emit('save_map', {'map': make_map()})
        assert last_error(lurker)['code'] == 'NOT_IN_LOBBY'

    def test_a_map_cannot_be_saved_once_a_game_is_running(self, socket_app):
        a, b = joined(socket_app, 'A'), joined(socket_app, 'B')
        a.emit('start_game')
        a.get_received()
        b.get_received()

        a.emit('save_map', {'map': make_map()})
        assert last_error(a)['code'] == 'GAME_IN_PROGRESS'

    def test_a_map_whose_pool_does_not_fit_is_refused_with_its_problems(self, socket_app):
        client = joined(socket_app)
        document = make_map()
        region_named(document, 'mainland')['pool']['terrain']['wood'] = 4

        client.emit('save_map', {'map': document})

        error = last_error(client)
        assert error['code'] == 'INVALID_MAP'
        assert error['details']['problems'][0]['region_id'] == 'mainland'
        assert not os.listdir(map_store.MAPS_DIR) if os.path.isdir(map_store.MAPS_DIR) else True

    def test_an_id_that_climbs_out_of_the_maps_directory_is_refused(self, socket_app):
        client = joined(socket_app)
        client.emit('save_map', {'map': make_map(id='../../pwned')})
        assert last_error(client)['code'] == 'INVALID_MAP'

    def test_a_saved_map_is_on_disk_and_announced(self, socket_app):
        client = joined(socket_app)
        client.emit('save_map', {'map': make_map()})

        assert events(client, 'map_saved')[-1] == {'id': 'test-map'}
        assert map_store.read_map('test-map')['name'] == 'Test Map'


class TestDeleting:
    def test_deleting_needs_the_confirmation_flag(self, socket_app):
        client = joined(socket_app)
        client.emit('save_map', {'map': make_map()})
        client.get_received()

        client.emit('delete_map', {'id': 'test-map'})

        assert last_error(client)['code'] == 'CONFIRM_REQUIRED'
        assert map_store.read_map('test-map')

    def test_a_builtin_cannot_be_deleted(self, socket_app):
        client = joined(socket_app)
        client.emit('delete_map', {'id': 'standard', 'confirm': True})
        assert last_error(client)['code'] == 'MAP_READ_ONLY'

    def test_the_map_the_table_has_chosen_cannot_be_deleted(self, socket_app):
        client = joined(socket_app)
        client.emit('save_map', {'map': make_map()})
        client.emit('set_rules', {'rules': {'board_layout': 'custom',
                                            'board_map': 'test-map'}})
        client.get_received()

        client.emit('delete_map', {'id': 'test-map', 'confirm': True})

        assert last_error(client)['code'] == 'MAP_IN_USE'

    def test_a_confirmed_delete_removes_it(self, socket_app):
        client = joined(socket_app)
        client.emit('save_map', {'map': make_map()})
        client.get_received()

        client.emit('delete_map', {'id': 'test-map', 'confirm': True})

        assert events(client, 'map_deleted')[-1] == {'id': 'test-map'}
        with pytest.raises(map_store.UnknownMap):
            map_store.read_map('test-map')


class TestPreview:
    def test_the_preview_is_a_board_the_renderer_can_draw(self, socket_app):
        client = joined(socket_app)
        client.emit('preview_map', {'map': make_map(), 'seed': 5})

        preview = events(client, 'map_preview')[-1]
        assert len(preview['board']['hexes']) == 37
        assert preview['islands'] == [7]
        assert preview['warnings'] == []

    def test_the_same_seed_previews_the_same_board(self, socket_app):
        """Preview runs the game's own code path, so it inherits its
        determinism rather than reimplementing the draw in the browser."""
        client = joined(socket_app)
        client.emit('preview_map', {'map': make_map(), 'seed': 5})
        first = events(client, 'map_preview')[-1]['board']['hexes']
        client.emit('preview_map', {'map': make_map(), 'seed': 5})
        second = events(client, 'map_preview')[-1]['board']['hexes']
        assert first == second

    def test_a_two_island_map_previews_its_islands_and_its_warnings(self, socket_app):
        client = joined(socket_app)
        client.emit('preview_map', {'map': map_store.read_map('little-shores'), 'seed': 3})

        preview = events(client, 'map_preview')[-1]
        assert sum(preview['islands']) == 10 - 1, 'ten land slots, one dealt to the sea'
        assert len(preview['islands']) == 2
        assert 'MANY_ISLANDS' in {warning['code'] for warning in preview['warnings']}

    def test_a_broken_map_previews_nothing(self, socket_app):
        client = joined(socket_app)
        document = make_map()
        region_named(document, 'mainland')['pool']['numbers'] = []

        client.emit('preview_map', {'map': document})

        assert last_error(client)['code'] == 'INVALID_MAP'
        assert not events(client, 'map_preview')


class TestStartingOnACustomMap:
    def _table(self, socket_app, **rules):
        a, b = joined(socket_app, 'A'), joined(socket_app, 'B')
        a.emit('save_map', {'map': make_map()})
        a.emit('set_rules', {'rules': rules})
        a.get_received()
        b.get_received()
        return a, b

    def test_a_game_is_played_on_the_chosen_map(self, socket_app):
        a, _ = self._table(socket_app, board_layout='custom', board_map='test-map')
        a.emit('start_game')

        assert last_error(a) is None
        game = state.session().game
        assert game.map_definition.id == 'test-map'
        assert len(game.hexes) == 37

    def test_a_map_deleted_after_it_was_chosen_refuses_to_start(self, socket_app):
        """`coerce` falls back to the default on an id it does not know, so
        without this the table quietly gets a board nobody picked."""
        a, _ = self._table(socket_app, board_layout='custom', board_map='test-map')
        map_store.delete_map('test-map')

        a.emit('start_game')

        assert last_error(a)['code'] == 'UNKNOWN_MAP'
        assert state.session().game is None

    def test_two_islands_without_ships_are_refused_by_name(self, socket_app):
        a, _ = self._table(socket_app, board_layout='custom', board_map='little-shores')
        a.emit('start_game')

        error = last_error(a)
        assert error['code'] == 'INCOHERENT_RULES'
        assert 'needs Ships' in error['message']
        assert state.session().game is None

    def test_the_same_map_starts_once_ships_are_on(self, socket_app):
        a, _ = self._table(socket_app, board_layout='custom', board_map='little-shores',
                           ships=True)
        a.emit('start_game')

        assert last_error(a) is None
        assert state.session().game.map_definition.id == 'little-shores'
