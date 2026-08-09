"""The map editor's v2 wire shape, pinned against the server that reads it.

The editor (`map-editor.js`) is the only writer of these documents, and it runs
in a browser the unit suite cannot. What it emits, though, is a plain JSON shape,
and the contract that matters is that the server accepts it and round-trips it.
So these tests hand-build the exact documents `mapDocToWire` produces for the v2
features — a hidden pool, the Explorers & Pirates terrains, a fixed pool, and
per-hex docks/village metadata — and assert `parse_map`/`validate_map` take them,
deal them, and return them unchanged. A drift between the editor's output and the
parser shows up here as a rejected shape.
"""

import random

from game import board as board_module
from game import maps
from game.game import Game

MAINLAND = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))
OCEAN = [k for k in maps.frame_hex_keys(3) if k not in set(MAINLAND)]


def _ocean_remaining():
    return {
        'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
        'pool': {'mode': 'shuffled',
                 'terrain': {'sea': len(maps.frame_hex_keys(3)) - len(MAINLAND)},
                 'numbers': []},
    }


def _played(document, **rules):
    chosen = {'board_layout': 'custom', 'board_map': document['id']}
    chosen.update(rules)
    return Game(['A', 'B'], [], rng=random.Random(1), rules=chosen,
                map_definition=maps.parse_map(document))


def _errors(document):
    errs, _ = maps.validate_map(maps.parse_map(document))
    return [e.code for e in errs]


class TestHiddenPoolWithEpTerrains:
    """A discovery map: a hidden mainland whose pool mixes gold and fish in."""

    def _doc(self):
        return {
            'map_version': 2, 'id': 'ep-hidden', 'name': 'EP Hidden',
            'frame': {'radius': 3},
            'regions': [
                {
                    'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND,
                    'pool': {'mode': 'hidden',
                             'terrain': {'gold': 1, 'fish': 1, 'wood': 2, 'wheat': 2,
                                         'sheep': 1},
                             'numbers': [3, 4, 5, 6, 9, 10]},
                    'meta': {MAINLAND[0]: {'village': True}},
                },
                _ocean_remaining(),
            ],
            'harbours': {'mode': 'bag', 'types': {}},
        }

    def test_it_parses_validates_and_deals(self):
        document = self._doc()
        assert _errors(document) == []
        # Deals a board through the real Game, the way a preview would.
        _played(document, transport_ships=True, harbor_settlements=True,
                ships_explore=True, gold=True)

    def test_the_v2_fields_survive_a_round_trip(self):
        defn = maps.parse_map(self._doc())
        assert maps.parse_map(defn.to_json()) == defn
        mainland = defn.to_json()['regions'][0]
        assert mainland['pool']['mode'] == 'hidden'
        assert mainland['pool']['terrain']['gold'] == 1
        assert mainland['pool']['terrain']['fish'] == 1
        assert mainland['meta'][MAINLAND[0]]['village'] is True


class TestCouncilDockMetadata:
    """Docks on a sea hex — the Council of Catan a fish haul is delivered to."""

    def _doc(self):
        return {
            'map_version': 2, 'id': 'ep-council', 'name': 'EP Council',
            'frame': {'radius': 3},
            'regions': [
                {
                    'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND,
                    'pool': {'mode': 'shuffled',
                             'terrain': {'wood': 2, 'wheat': 2, 'sheep': 1, 'brick': 1,
                                         'desert': 1},
                             'numbers': [3, 4, 5, 6, 9, 10]},
                },
                {**_ocean_remaining(), 'meta': {OCEAN[0]: {'docks': [0, 2, 4]}}},
            ],
            'harbours': {'mode': 'bag', 'types': {}},
        }

    def test_docks_on_a_sea_hex_validate_and_round_trip(self):
        document = self._doc()
        assert _errors(document) == []
        defn = maps.parse_map(document)
        ocean = defn.to_json()['regions'][1]
        assert ocean['meta'][OCEAN[0]]['docks'] == [0, 2, 4]


class TestFixedPool:
    """A printed board: every mainland hex names its own tile and token."""

    def _doc(self):
        placements = {
            MAINLAND[0]: {'terrain': 'wood', 'number': 5},
            MAINLAND[1]: {'terrain': 'brick', 'number': 6},
            MAINLAND[2]: {'terrain': 'sheep', 'number': 8},
            MAINLAND[3]: {'terrain': 'wheat', 'number': 9},
            MAINLAND[4]: {'terrain': 'ore', 'number': 10},
            MAINLAND[5]: {'terrain': 'gold', 'number': 11},
            MAINLAND[6]: {'terrain': 'desert'},
        }
        return {
            'map_version': 2, 'id': 'ep-fixed', 'name': 'EP Fixed',
            'frame': {'radius': 3},
            'regions': [
                {
                    'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND,
                    'pool': {'mode': 'fixed', 'placements': placements},
                },
                _ocean_remaining(),
            ],
            'harbours': {'mode': 'bag', 'types': {}},
        }

    def test_a_fixed_pool_places_every_hex_and_round_trips(self):
        document = self._doc()
        assert _errors(document) == []
        defn = maps.parse_map(document)
        assert maps.parse_map(defn.to_json()) == defn
        game = _played(document, gold=True)
        # The printed tiles land exactly where they were placed.
        assert game.hexes[MAINLAND[5]].type == 'gold'
        assert game.hexes[MAINLAND[0]].number == 5
