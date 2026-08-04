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
        ('a version from the future', make_map(map_version=2)),
        ('an id that is a path', make_map(id='../../etc/passwd')),
        ('an id with a slash', make_map(id='maps/mine')),
        ('an empty id', make_map(id='')),
        ('a name that is too long', make_map(name='x' * 65)),
        ('no frame', make_map(frame=None)),
        ('a frame of nothing', make_map(frame={'radius': 0})),
        ('a frame bigger than the cap', make_map(frame={'radius': 7})),
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
        hardest on. The cap is global (`MAX_PAYLOAD_BYTES`) and is applied
        before any handler sees the message, so this is the format's problem."""
        inner = [key for key in maps.frame_hex_keys(6) if maps.ring_of(key) < 6]
        rim = [key for key in maps.frame_hex_keys(6) if maps.ring_of(key) == 6]
        document = {
            'map_version': 1, 'id': 'the-biggest-map-that-fits',
            'name': 'x' * 64, 'author': 'y' * 64, 'notes': 'z' * 512,
            'frame': {'radius': 6},
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
        assert not payload_too_large({'map': document})
        assert len(json.dumps(document)) < 8192
