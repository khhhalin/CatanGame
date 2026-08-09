"""The map format: what it accepts, what it refuses, and what it deals.

The best test of a format is whether it can express the boards that already
exist, so the first class here builds the base game and the 5-6 player
extension out of map files and checks them hex for hex and token for token
against what `LAYOUTS` deals. The beginner map is the one board it cannot
express: its tiles are printed, and fixed pools are not in v1.
"""

import json
import random
from collections import Counter

import pytest
from game import board as board_module
from game import map_store, maps
from game.game import Game
from game.rate_limit import payload_too_large
from game.validation import InvalidPayload


def builtin(map_id):
    return maps.parse_map(map_store.read_map(map_id))


def make_map(**overrides) -> dict:
    """A small, valid map file: a 7-hex mainland in a radius-3 frame."""
    mainland = maps.sort_hex_keys('{},{},{}'.format(*coords) for coords in board_module._hexagon(1))
    document = {
        'map_version': 1,
        'id': 'test-map',
        'name': 'Test Map',
        'frame': {'radius': 3},
        'regions': [
            {
                'id': 'mainland', 'kind': 'main', 'hexes': mainland,
                'pool': {'mode': 'shuffled',
                         'terrain': {'wood': 2, 'wheat': 2, 'sheep': 1, 'brick': 1,
                                     'desert': 1},
                         'numbers': [3, 4, 5, 6, 9, 10]},
            },
            {
                'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
                'pool': {'mode': 'shuffled',
                         'terrain': {'sea': len(maps.frame_hex_keys(3)) - len(mainland)},
                         'numbers': []},
            },
        ],
        'harbours': {'mode': 'bag', 'types': {'generic': 2, 'ore': 1}},
    }
    document.update(overrides)
    return document


def region_named(document, region_id) -> dict:
    return next(region for region in document['regions'] if region['id'] == region_id)


def problems(document) -> tuple:
    errors, warnings = maps.validate_map(maps.parse_map(document))
    return [problem.code for problem in errors], [problem.code for problem in warnings]


def played(document, seed=1, **rules) -> Game:
    chosen = {'board_layout': 'custom', 'board_map': document['id']}
    chosen.update(rules)
    return Game(['A', 'B'], [], rng=random.Random(seed), rules=chosen,
                map_definition=maps.parse_map(document))


class TestTheFormatExpressesTheBuiltInBoards:
    """If the format cannot say what the engine already plays, it is wrong.

    Checked against the board `LAYOUTS` actually generates, never against a
    second copy of the same literal — the two board bugs in this project's
    history were both a literal that had drifted from the thing it filled.
    """

    @pytest.mark.parametrize('map_id, layout', [
        ('standard', 'random'),
        ('large-island', 'large'),
    ])
    def test_it_is_the_same_board_the_layout_builds(self, map_id, layout):
        from_map = played(map_store.read_map(map_id))
        from_layout = Game(['A', 'B'], [], rng=random.Random(1),
                           rules={'board_layout': layout})

        assert sorted(from_map.hexes) == sorted(from_layout.hexes)
        assert (
            Counter(h.type for h in from_map.hexes.values())
            == Counter(h.type for h in from_layout.hexes.values())
        )
        assert (
            sorted(h.number for h in from_map.hexes.values() if h.number is not None)
            == sorted(h.number for h in from_layout.hexes.values() if h.number is not None)
        )
        assert (
            len([e for e in from_map.edges.values() if e.port])
            == len([e for e in from_layout.edges.values() if e.port])
        )

    def test_the_standard_map_deals_the_base_game_box(self):
        game = played(map_store.read_map('standard'))
        assert Counter(
            h.type for h in game.hexes.values() if h.type != 'ocean'
        ) == {'wood': 4, 'wheat': 4, 'sheep': 4, 'brick': 3, 'ore': 3, 'desert': 1}
        assert sorted(
            h.number for h in game.hexes.values() if h.number is not None
        ) == sorted(board_module.NUMBER_TOKENS)

    def test_the_beginner_map_is_the_one_board_the_format_cannot_say(self):
        """Its tiles are printed, and a v1 pool is always shuffled.

        Written down rather than left implicit: somebody will look for a
        beginner map file and needs to find out why there is none from a test
        rather than from a missing file.
        """
        assert 'beginner' not in map_store.builtin_ids()
        assert maps.POOL_MODES == ('shuffled',)

    @pytest.mark.parametrize('map_id', ['standard', 'large-island', 'little-shores'])
    def test_a_builtin_survives_a_round_trip_and_has_no_errors(self, map_id):
        defn = builtin(map_id)
        assert maps.parse_map(defn.to_json()) == defn
        errors, _ = maps.validate_map(defn)
        assert errors == []


class TestTheLatticeMatchesTheEngine:
    """`maps.py` repeats two pieces of geometry so `board.py` can import it.

    Repeated code is allowed to drift; this is what stops it.
    """

    def test_the_neighbour_steps_are_the_boards_own(self):
        assert list(maps.HEX_NEIGHBOURS) == [
            tuple(step) for step in Game.HEX_DIRECTIONS
        ]

    @pytest.mark.parametrize('radius', [1, 2, 3, 6])
    def test_the_frame_is_the_boards_own_hexagon(self, radius):
        assert maps.frame_hex_keys(radius) == [
            '{},{},{}'.format(*coords) for coords in board_module._hexagon(radius)
        ]

    def test_hex_keys_sort_by_coordinate_not_by_string(self):
        keys = ['3,-3,0', '-3,0,3', '0,0,0']
        assert maps.sort_hex_keys(keys) == ['-3,0,3', '0,0,0', '3,-3,0']


class TestParsingRefusesRubbish:
    """A map is the most nested payload this protocol has, and it becomes a
    filename. Everything is bounded and allowlisted before anything else runs."""

    @pytest.mark.parametrize('description, document', [
        ('not an object', 'a map'),
        ('no version', make_map(map_version=None)),
        ('a version from the future', make_map(map_version=3)),
        ('an id that is a path', make_map(id='../../etc/passwd')),
        ('an id with a slash', make_map(id='maps/mine')),
        ('an empty id', make_map(id='')),
        ('a name that is too long', make_map(name='x' * 65)),
        ('no frame', make_map(frame=None)),
        ('a frame of nothing', make_map(frame={'radius': 0})),
        ('a frame bigger than the cap', make_map(frame={'radius': 9})),
        ('no regions', make_map(regions=[])),
        ('a robber that is not a hex', make_map(robber_start='over there')),
    ])
    def test_the_shape_is_refused(self, description, document):
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_a_hex_key_off_the_lattice_is_refused(self):
        document = make_map()
        region_named(document, 'mainland')['hexes'] = ['1,-1,0']
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_a_seven_is_not_a_number_token(self):
        document = make_map()
        region_named(document, 'mainland')['pool']['numbers'] = [3, 4, 5, 6, 7, 10]
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_a_terrain_nobody_has_implemented_is_refused(self):
        document = make_map()
        region_named(document, 'mainland')['pool']['terrain'] = {'gold': 7}
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_a_count_that_is_a_boolean_is_refused(self):
        """True is an int in Python and would sail through as 1."""
        document = make_map()
        region_named(document, 'mainland')['pool']['terrain'] = {'wood': True}
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_two_regions_cannot_both_claim_what_is_left(self):
        document = make_map()
        region_named(document, 'mainland')['hexes'] = 'remaining'
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_two_regions_cannot_share_an_id(self):
        document = make_map()
        region_named(document, 'ocean')['id'] = 'mainland'
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_remaining_is_expanded_at_parse_and_never_seen_again(self):
        defn = maps.parse_map(make_map())
        ocean = next(region for region in defn.regions if region.id == 'ocean')
        assert len(ocean.hexes) == len(maps.frame_hex_keys(3)) - 7
        assert 'remaining' not in defn.to_json()['regions'][1]['hexes']


class TestValidationRefusesMapsThatMeanNothing:
    def test_a_pool_that_does_not_fill_its_region(self):
        document = make_map()
        region_named(document, 'mainland')['pool']['terrain']['wood'] = 1
        assert 'POOL_SIZE' in problems(document)[0]

    def test_tokens_that_do_not_match_the_tiles_that_take_one(self):
        document = make_map()
        region_named(document, 'mainland')['pool']['numbers'] = [3, 4]
        assert 'TOKEN_COUNT' in problems(document)[0]

    def test_a_pool_of_sea_takes_no_tokens_at_all(self):
        """The rulebook: "no number tokens are placed on sea hexes"."""
        document = make_map()
        region_named(document, 'ocean')['pool']['numbers'] = [6]
        assert 'TOKEN_COUNT' in problems(document)[0]

    def test_a_hex_in_two_regions(self):
        document = make_map()
        region_named(document, 'ocean')['hexes'] = ['0,0,0']
        region_named(document, 'ocean')['pool']['terrain'] = {'sea': 1}
        assert 'HEX_CLAIMED_TWICE' in problems(document)[0]

    def test_a_hex_outside_the_frame(self):
        document = make_map(frame={'radius': 1})
        region_named(document, 'ocean')['hexes'] = ['12,-12,0']
        region_named(document, 'ocean')['pool']['terrain'] = {'sea': 1}
        assert 'OUTSIDE_FRAME' in problems(document)[0]

    def test_a_map_with_no_land_at_all(self):
        document = make_map()
        region_named(document, 'mainland')['pool']['terrain'] = {'sea': 7}
        region_named(document, 'mainland')['pool']['numbers'] = []
        assert problems(document)[0] == ['NO_LAND']

    def test_land_on_the_rim_of_the_frame(self):
        """A side with one hex is not a sea edge, so no ship can ever arrive."""
        document = make_map(frame={'radius': 1})
        region_named(document, 'ocean')['hexes'] = []
        region_named(document, 'ocean')['pool']['terrain'] = {'sea': 0}
        assert 'LAND_ON_THE_RIM' in problems(document)[0]

    def test_an_island_no_ship_could_reach(self):
        """Two islands, each with its own water, and nothing at all between them.

        Painting stops where the author stopped painting: a hex no region
        claims is not water, it is a hole where no hex exists. A shipping route
        cannot cross one, so the far island can be seen and never landed on.
        """
        far, home = '15,-15,0', '0,0,0'
        document = make_map(frame={'radius': 6})
        region_named(document, 'mainland')['hexes'] = [home]
        region_named(document, 'mainland')['pool']['terrain'] = {'desert': 1}
        region_named(document, 'mainland')['pool']['numbers'] = []
        water = maps.sort_hex_keys(maps.neighbour_keys(home) + maps.neighbour_keys(far))
        region_named(document, 'ocean')['hexes'] = water
        region_named(document, 'ocean')['pool']['terrain'] = {'sea': len(water)}
        document['regions'].append({
            'id': 'far-shore', 'kind': 'island', 'hexes': [far],
            'pool': {'mode': 'shuffled', 'terrain': {'ore': 1}, 'numbers': [8]},
        })
        assert problems(document)[0] == ['UNREACHABLE_LAND']

    def test_a_robber_starting_in_the_sea(self):
        document = make_map(robber_start='6,-6,0')
        assert 'ROBBER_START' in problems(document)[0]


class TestWarningsDoNotBlock:
    def test_two_islands_are_a_warning_at_save_and_a_refusal_at_start(self):
        defn = builtin('little-shores')
        errors, warnings = maps.validate_map(defn)
        assert errors == []
        assert 'MANY_ISLANDS' in [warning.code for warning in warnings]

        assert maps.start_problems(defn, {'ships': False}) == [
            'Little Shores has 2 islands and needs Ships'
        ]
        assert maps.start_problems(defn, {'ships': True}) == []

    def test_fog_parses_and_previews_but_never_starts(self):
        document = make_map()
        region_named(document, 'mainland')['kind'] = 'fog'
        errors, warnings = maps.validate_map(maps.parse_map(document))
        assert errors == []
        assert 'FOG_REGION' in [warning.code for warning in warnings]
        assert maps.start_problems(maps.parse_map(document), {'ships': True})

    def test_starting_on_the_main_land_needs_a_map_that_has_some(self):
        """The rule and the map have to agree, and the table is told which of
        the two to change rather than being handed a game nobody can open."""
        document = make_map()
        region_named(document, 'mainland')['kind'] = 'island'
        defn = maps.parse_map(document)

        assert maps.validate_map(defn)[0] == []
        assert maps.start_problems(defn, {'start_on_main_land': True}) == [
            'Test Map has no main land to start on'
        ]
        assert maps.start_problems(defn, {'start_on_main_land': False}) == []

    def test_more_harbours_than_the_coast_can_hold(self):
        document = make_map()
        document['harbours'] = {'mode': 'bag', 'types': {'generic': 12}}
        assert 'HARBOUR_CROWDING' in problems(document)[1]

    def test_a_suggested_target_far_from_the_rulebook_heuristic(self):
        assert 'VICTORY_TARGET' in problems(make_map(suggested_victory_target=20))[1]

    def test_a_map_with_no_desert_leaves_the_robber_beside_the_board(self):
        document = make_map()
        region_named(document, 'mainland')['pool']['terrain'] = {
            'wood': 3, 'wheat': 2, 'sheep': 1, 'brick': 1,
        }
        region_named(document, 'mainland')['pool']['numbers'] = [3, 4, 5, 6, 9, 10, 11]
        assert 'NO_ROBBER_START' in problems(document)[1]
        assert played(document).robber_hex is None


class TestTheDraw:
    def test_the_pool_is_exactly_what_lands_on_the_board(self):
        """Over a sweep of seeds, because a pool that loses a tile on one
        shuffle in twenty is the bug this project has already had twice."""
        for seed in range(20):
            game = played(builtin('little-shores').to_json(), seed=seed, ships=True)
            assert Counter(h.type for h in game.hexes.values()) == Counter({
                'ocean': 51 + 1, 'wood': 2, 'wheat': 2, 'sheep': 2, 'brick': 1,
                'ore': 1, 'desert': 1,
            }), f'seed {seed}'
            assert sorted(
                h.number for h in game.hexes.values() if h.number is not None
            ) == [3, 4, 5, 6, 8, 9, 10, 11], f'seed {seed}'

    def test_no_token_ever_sits_on_sea_or_desert(self):
        for seed in range(20):
            game = played(builtin('little-shores').to_json(), seed=seed, ships=True)
            for hex_obj in game.hexes.values():
                assert (hex_obj.number is None) == (hex_obj.type in ('ocean', 'desert')), (
                    f'seed {seed}: {hex_obj.key} is {hex_obj.type} with {hex_obj.number}'
                )

    def test_the_robber_starts_on_the_first_desert(self):
        game = played(make_map())
        assert game.hexes[game.robber_hex].type == 'desert'

    def test_an_authored_robber_hex_is_used_when_it_was_dealt_land(self):
        document = make_map(robber_start='0,0,0')
        for seed in range(5):
            assert played(document, seed=seed).robber_hex == '0,0,0'

    def test_the_same_seed_deals_the_same_board(self):
        first, second = played(make_map(), seed=77), played(make_map(), seed=77)
        assert {k: (h.type, h.number) for k, h in first.hexes.items()} == \
               {k: (h.type, h.number) for k, h in second.hexes.items()}

    def test_two_seeds_deal_two_boards(self):
        first, second = played(make_map(), seed=1), played(make_map(), seed=2)
        assert {k: h.type for k, h in first.hexes.items()} != \
               {k: h.type for k, h in second.hexes.items()}

    def test_a_pool_that_does_not_fit_is_refused_rather_than_dealt(self):
        document = make_map()
        region_named(document, 'mainland')['pool']['terrain']['wood'] = 3
        with pytest.raises(maps.MapUnplayable):
            played(document)


class TestTheMapFitsInAPayload:
    def test_the_largest_map_the_validator_accepts_fits_in_one_message(self):
        """Otherwise the editor refuses to save exactly the maps people work
        hardest on. save_map gets 64 KB via EVENT_PAYLOAD_LIMITS; this test
        checks both the per-event cap and the absolute byte count so the
        format cannot drift into a state where the cap alone saves it."""
        from game.rate_limit import max_bytes_for
        all_keys = maps.frame_hex_keys(8)
        inner = [key for key in all_keys if maps.ring_of(key) < 8]
        rim = [key for key in all_keys if maps.ring_of(key) == 8]
        document = {
            'map_version': 1, 'id': 'the-biggest-map-that-fits',
            'name': 'x' * 64, 'author': 'y' * 64, 'notes': 'z' * 512,
            'frame': {'radius': 8},
            'regions': [
                {'id': 'mainland', 'kind': 'main', 'color': '#8bb26a', 'hexes': inner,
                 'pool': {'mode': 'shuffled', 'terrain': {'wood': len(inner)},
                          'numbers': [8] * len(inner)}},
                {'id': 'ocean', 'kind': 'sea', 'color': '#3b6ea5', 'hexes': rim,
                 'pool': {'mode': 'shuffled', 'terrain': {'sea': len(rim)}, 'numbers': []}},
            ],
            'harbours': {'mode': 'bag', 'types': {'generic': 32}},
        }
        errors, _ = maps.validate_map(maps.parse_map(document))
        assert errors == []
        assert not payload_too_large({'map': document}, max_bytes=max_bytes_for('save_map'))
        assert len(json.dumps(document)) < max_bytes_for('save_map')

    def test_excluded_hexes_are_absent_from_all_regions(self):
        """Hexes listed in frame.excluded must not appear in any region's hex
        list after parsing — the 'remaining' sea expands around them."""
        document = make_map()
        mainland = region_named(document, 'mainland')['hexes']
        # Exclude one mainland hex and one ocean hex.
        excluded = [mainland[0], maps.frame_hex_keys(3)[-1]]
        document['frame'] = {'radius': 3, 'excluded': excluded}
        defn = maps.parse_map(document)
        assert defn.excluded_hexes == tuple(maps.sort_hex_keys(excluded))
        all_region_hexes = {h for r in defn.regions for h in r.hexes}
        for key in excluded:
            assert key not in all_region_hexes, (
                f'excluded hex {key!r} appears in a region after parsing'
            )

    def test_excluded_hex_outside_the_frame_is_refused(self):
        document = make_map()
        document['frame'] = {'radius': 3, 'excluded': ['99,-99,0']}
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_round_trip_preserves_excluded_hexes(self):
        document = make_map()
        excluded = [maps.frame_hex_keys(3)[-1]]
        document['frame'] = {'radius': 3, 'excluded': excluded}
        defn = maps.parse_map(document)
        assert maps.parse_map(defn.to_json()) == defn


# --- map-format v2: hidden pools, new terrains, fixed pools, metadata -------

def make_v2_map(mainland_pool, *, meta=None, harbours=None) -> dict:
    """A v2 map: a 7-hex mainland with the given pool, ringed by shuffled sea.

    The mainland is `_hexagon(1)`, fully surrounded inside a radius-3 frame, so
    every land hex has its six neighbours and nothing lands on the rim.
    """
    mainland = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))
    sea_count = len(maps.frame_hex_keys(3)) - len(mainland)
    region = {'id': 'mainland', 'kind': 'main', 'hexes': mainland, 'pool': mainland_pool}
    if meta is not None:
        region['meta'] = meta
    return {
        'map_version': 2, 'id': 'v2-map', 'name': 'V2 Map', 'frame': {'radius': 3},
        'regions': [
            region,
            {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
             'pool': {'mode': 'shuffled', 'terrain': {'sea': sea_count}, 'numbers': []}},
        ],
        'harbours': {'mode': 'bag', 'types': harbours or {}},
    }


def mainland_keys() -> list:
    return maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))


class TestTheNewTerrains:
    """gold, fish and spice: accepted in a v2 file, refused in a v1 one."""

    @pytest.mark.parametrize('terrain, number', [
        ('gold', 6), ('fish', None), ('spice', None),
    ])
    def test_a_v2_map_accepts_the_terrain_v1_refused(self, terrain, number):
        pool = {'mode': 'shuffled',
                'terrain': {terrain: 1, 'wood': 5, 'desert': 1},
                'numbers': [3, 4, 5, 8, 9] + ([number] if number is not None else [])}
        document = make_v2_map(pool)
        errors, _ = maps.validate_map(maps.parse_map(document))
        assert errors == []

        document['map_version'] = 1
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)

    def test_only_gold_carries_a_number_token(self):
        """gold pays out on its roll; a fish-shoal and a spice hex do not, so a
        token on one is a number floating where production pays nobody."""
        assert maps.takes_a_token('gold')
        assert not maps.takes_a_token('fish')
        assert not maps.takes_a_token('spice')


class TestHiddenPools:
    def test_a_hidden_pool_deals_every_tile_face_down_with_no_number(self):
        """Exploration places the tiles icon-side-up; the number is drawn per
        icon at reveal, a later wave, so none sits on the board yet."""
        pool = {'mode': 'hidden',
                'terrain': {'wood': 2, 'wheat': 2, 'sheep': 1, 'brick': 1, 'desert': 1},
                'numbers': [3, 4, 5, 6, 9, 10]}
        defn = maps.parse_map(make_v2_map(pool))
        assert maps.validate_map(defn)[0] == []

        instance = maps.instantiate(defn, random.Random(7))
        assert instance.hidden == frozenset(mainland_keys())
        assert all(instance.placed[key][1] is None for key in mainland_keys())

    def test_a_hidden_tile_is_redacted_to_every_viewer(self):
        """Its identity is secret like a dev card until discovery reveals it."""
        pool = {'mode': 'hidden',
                'terrain': {'wood': 3, 'wheat': 2, 'desert': 2},
                'numbers': [3, 4, 5, 6, 9]}
        game = played(make_v2_map(pool))
        data = game.get_board_data(viewer='B')

        for key in mainland_keys():
            assert data['hexes'][key]['type'] == 'hidden'
            assert data['hexes'][key]['number'] is None
            assert data['hexes'][key]['hidden'] is True
        # A face-up sea hex is not touched by the redaction.
        sea_key = next(k for k, h in data['hexes'].items() if k not in mainland_keys())
        assert data['hexes'][sea_key]['type'] == 'ocean'
        assert 'hidden' not in data['hexes'][sea_key]

    def test_a_hidden_pool_needs_v2(self):
        pool = {'mode': 'hidden', 'terrain': {'desert': 7}, 'numbers': []}
        with pytest.raises(InvalidPayload):
            maps.parse_map(make_v2_map(pool, harbours={}) | {'map_version': 1})


class TestFixedPools:
    def _fixed_pool(self):
        keys = mainland_keys()
        placements = {'0,0,0': {'terrain': 'desert'}}
        tiles = [('wood', 2), ('brick', 3), ('sheep', 4), ('wheat', 5), ('ore', 6),
                 ('wood', 8)]
        for key, (terrain, number) in zip(
            [k for k in keys if k != '0,0,0'], tiles, strict=True
        ):
            placements[key] = {'terrain': terrain, 'number': number}
        return {'mode': 'fixed', 'placements': placements}, placements

    def test_a_fixed_pool_places_tiles_at_the_declared_positions(self):
        pool, placements = self._fixed_pool()
        defn = maps.parse_map(make_v2_map(pool))
        assert maps.validate_map(defn)[0] == []

        for seed in (1, 99):
            game = played(make_v2_map(pool), seed=seed)
            for key, spec in placements.items():
                assert game.hexes[key].type == spec['terrain']
                assert game.hexes[key].number == spec.get('number')

    def test_a_fixed_producing_tile_must_print_its_number(self):
        pool, placements = self._fixed_pool()
        del placements[next(k for k in placements if placements[k].get('number'))]['number']
        with pytest.raises(InvalidPayload):
            maps.parse_map(make_v2_map(pool))

    def test_a_fixed_pool_that_does_not_cover_its_hexes_is_refused(self):
        pool, placements = self._fixed_pool()
        placements.pop('0,0,0')
        assert 'FIXED_PLACEMENT' in problems(make_v2_map(pool))[0]

    def test_a_fixed_pool_needs_v2(self):
        pool, _ = self._fixed_pool()
        with pytest.raises(InvalidPayload):
            maps.parse_map(make_v2_map(pool) | {'map_version': 1})


class TestPerHexMetadata:
    def test_metadata_round_trips_and_reaches_the_board(self):
        pool = {'mode': 'shuffled',
                'terrain': {'wood': 3, 'wheat': 3, 'desert': 1},
                'numbers': [3, 4, 5, 6, 9, 10]}
        meta = {'0,0,0': {'docks': [0, 3], 'village': True},
                '3,-3,0': {'lair': True}}
        defn = maps.parse_map(make_v2_map(pool, meta=meta))
        assert maps.validate_map(defn)[0] == []
        assert maps.parse_map(defn.to_json()) == defn

        game = played(make_v2_map(pool, meta=meta))
        assert game.hexes['0,0,0'].meta.docks == (0, 3)
        assert game.hexes['0,0,0'].meta.village is True
        assert game.hexes['3,-3,0'].meta.lair is True
        assert game.get_board_data(viewer='A')['hexes']['0,0,0']['meta'] == {
            'docks': [0, 3], 'village': True,
        }

    def test_metadata_on_a_hex_the_region_does_not_own_is_refused(self):
        pool = {'mode': 'shuffled', 'terrain': {'wood': 6, 'desert': 1},
                'numbers': [3, 4, 5, 6, 8, 9]}
        # A sea hex outside the mainland region.
        assert 'META_OFF_REGION' in problems(make_v2_map(pool, meta={'6,-6,0': {'lair': True}}))[0]

    def test_metadata_needs_v2(self):
        document = make_map(map_version=1)
        region_named(document, 'mainland')['meta'] = {'0,0,0': {'lair': True}}
        with pytest.raises(InvalidPayload):
            maps.parse_map(document)


def test_a_v2_map_with_every_new_feature_round_trips():
    """Hidden and fixed regions, new terrains and per-hex metadata all at once,
    so `parse_map(defn.to_json()) == defn` covers the whole v2 surface."""
    keys = mainland_keys()
    placements = {}
    for key in keys:
        if key == '0,0,0':
            placements[key] = {'terrain': 'gold', 'number': 6}
        else:
            placements[key] = {'terrain': 'wood', 'number': 8}
    document = {
        'map_version': 2, 'id': 'v2-everything', 'name': 'Everything',
        'frame': {'radius': 3},
        'regions': [
            {'id': 'mainland', 'kind': 'main', 'hexes': keys,
             'pool': {'mode': 'fixed', 'placements': placements},
             'meta': {'0,0,0': {'docks': [1, 4], 'lair': True}}},
            {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
             'pool': {'mode': 'shuffled',
                      'terrain': {'sea': len(maps.frame_hex_keys(3)) - len(keys)},
                      'numbers': []}},
        ],
        'harbours': {'mode': 'bag', 'types': {}},
    }
    defn = maps.parse_map(document)
    assert maps.validate_map(defn)[0] == []
    assert maps.parse_map(defn.to_json()) == defn
