"""Maps on disk: the slug guard, the atomic write, and a directory a human edits.

The store is the only place client input becomes a filesystem path, so most of
what is here is about refusing to build one.
"""

import json
import os

import pytest
from game import map_store, maps

from .test_maps import make_map


@pytest.fixture(autouse=True)
def clean_maps_dir():
    """Start and finish with no custom maps, leaving the built-ins alone."""
    def wipe():
        if os.path.isdir(map_store.MAPS_DIR):
            for name in os.listdir(map_store.MAPS_DIR):
                os.remove(os.path.join(map_store.MAPS_DIR, name))
    wipe()
    yield
    wipe()


class TestTheIdIsThePathGuard:
    @pytest.mark.parametrize('map_id', [
        '../../../etc/passwd',
        '..',
        'maps/../../secrets',
        'Uppercase',
        'has space',
        'x' * 49,
        '',
        None,
        7,
    ])
    def test_nothing_but_a_slug_ever_becomes_a_path(self, map_id):
        with pytest.raises(map_store.UnknownMap):
            map_store.read_map(map_id)
        with pytest.raises(map_store.UnknownMap):
            map_store.write_map(map_id, make_map())
        with pytest.raises(map_store.UnknownMap):
            map_store.delete_map(map_id)

    def test_a_traversing_id_writes_nothing_anywhere(self, tmp_path):
        target = tmp_path / 'stolen.json'
        escape = os.path.relpath(str(target), map_store.MAPS_DIR)[: -len('.json')]
        with pytest.raises(map_store.UnknownMap):
            map_store.write_map(escape, make_map())
        assert not target.exists()


class TestSavingAndReading:
    def test_a_saved_map_comes_back_the_same(self):
        document = maps.parse_map(make_map()).to_json()
        map_store.write_map('test-map', document)
        assert map_store.read_map('test-map') == document

    def test_a_map_nobody_saved_is_not_found(self):
        with pytest.raises(map_store.UnknownMap):
            map_store.read_map('never-existed')

    def test_the_write_leaves_no_temp_file_behind(self):
        """Atomic, the way `persistence.save` is: an interrupted in-place write
        leaves a file that fails to parse, which is how a map gets lost."""
        map_store.write_map('test-map', make_map())
        assert os.listdir(map_store.MAPS_DIR) == ['test-map.json']

    def test_a_builtin_refuses_to_be_overwritten_or_deleted(self):
        with pytest.raises(map_store.ReadOnlyMap):
            map_store.write_map('standard', make_map())
        with pytest.raises(map_store.ReadOnlyMap):
            map_store.delete_map('standard')

    def test_deleting_removes_the_file(self):
        map_store.write_map('test-map', make_map())
        map_store.delete_map('test-map')
        with pytest.raises(map_store.UnknownMap):
            map_store.read_map('test-map')


class TestListing:
    def test_the_builtins_are_listed_and_marked(self):
        rows = {row['id']: row for row in map_store.list_maps()}
        assert rows['standard']['builtin'] is True
        assert rows['standard']['hexes'] == 37
        assert rows['little-shores']['islands'] == 2
        assert rows['standard']['problems'] == []

    def test_a_saved_map_appears_with_its_own_row(self):
        map_store.write_map('test-map', make_map())
        row = next(row for row in map_store.list_maps() if row['id'] == 'test-map')
        assert row == {'id': 'test-map', 'name': 'Test Map', 'author': '',
                       'hexes': 37, 'regions': 2, 'islands': 1,
                       'builtin': False, 'problems': []}

    def test_a_file_a_human_broke_becomes_a_row_not_an_exception(self):
        """A directory people can drop files into has a bad file in it sooner
        or later, and one bad map must not cost the editor the whole list."""
        os.makedirs(map_store.MAPS_DIR, exist_ok=True)
        with open(os.path.join(map_store.MAPS_DIR, 'broken.json'), 'w') as handle:
            handle.write('{not json')
        document = make_map(id='wrong-size')
        document['regions'][0]['pool']['terrain']['wood'] = 9
        with open(os.path.join(map_store.MAPS_DIR, 'wrong-size.json'), 'w') as handle:
            json.dump(document, handle)

        rows = {row['id']: row for row in map_store.list_maps()}
        assert rows['broken']['problems'][0]['code'] == 'UNREADABLE'
        assert rows['wrong-size']['problems'][0]['code'] == 'POOL_SIZE'
        assert rows['standard']['problems'] == []

    def test_a_file_whose_name_is_not_a_map_id_is_ignored(self):
        os.makedirs(map_store.MAPS_DIR, exist_ok=True)
        with open(os.path.join(map_store.MAPS_DIR, 'Not A Map.json'), 'w') as handle:
            json.dump(make_map(), handle)
        assert not [row for row in map_store.list_maps() if ' ' in row['id']]


class TestLoadingForAGame:
    def test_a_map_that_does_not_validate_is_refused_at_load(self):
        document = make_map(id='wrong-size')
        document['regions'][0]['pool']['terrain']['wood'] = 9
        map_store.write_map('wrong-size', document)
        with pytest.raises(maps.InvalidPayload):
            map_store.load_definition('wrong-size')

    def test_the_file_is_re_read_every_time_rather_than_cached(self):
        """The map that was listed is not necessarily the map on disk now."""
        map_store.write_map('test-map', make_map(name='First'))
        assert map_store.load_definition('test-map').name == 'First'
        map_store.write_map('test-map', make_map(name='Second'))
        assert map_store.load_definition('test-map').name == 'Second'
