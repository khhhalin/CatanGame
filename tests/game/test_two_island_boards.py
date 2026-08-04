"""A board whose pool can deal sea into a land slot, and whose coast is not one ring.

Three bugs the built-in layouts cannot reach, because for all three of them the
slots the layout sets aside for land and the land it actually deals are the same
set of hexes. A map file's pool may contain sea, and a map may have two islands,
and both were reproduced here before anything was fixed:

- 2 intersections ringed entirely by water accepted a settlement,
- the sea tile dealt into a land slot came out carrying a number token,
- the coastal walk claimed 18 of the board's coastal edges and hung every
  harbour on whichever coast it happened to find.

The layout below is a two-island map patched into `LAYOUTS`, which is what the
map creator will produce from a file. Nothing about these fixes is specific to
custom maps: the third is a wrong answer in the base game the moment any board
grows a second coastline.
"""

import random
from collections import Counter

import pytest
from game import board as board_module
from game import rules as rules_module
from game.game import Game

from .test_harbours import harbour_edges

# A 7-hex mainland and a 3-hex offshore line two hexes clear of it, with one
# `ocean` tile in a pool of ten. Which slot drowns is up to the shuffle, and
# that is the point: the pool decides the land, the layout only decides where
# land may be.
TWO_ISLANDS = {
    'hexes': board_module._hexagon(1) + ((9, -9, 0), (9, -6, -3), (9, -3, -6)),
    'resources': ('wood', 'wood', 'wheat', 'wheat', 'sheep', 'sheep',
                  'brick', 'ore', 'desert', 'ocean'),
    # Eight tokens for eight resource tiles: the desert takes none, and neither
    # does the sea tile.
    'numbers': (3, 4, 5, 6, 8, 9, 10, 11),
    'ports': board_module.PORT_TYPES,
    'island': None,
    'fixed': False,
}

SLOTS = {'{},{},{}'.format(*coords) for coords in TWO_ISLANDS['hexes']}


@pytest.fixture
def two_island_game(monkeypatch):
    """A game on the two-island layout, seeded so a slot is dealt to the sea."""
    monkeypatch.setitem(board_module.LAYOUTS, 'two_islands', TWO_ISLANDS)
    # `coerce` drops a layout the catalogue does not offer, so the option has to
    # be listed as well or every game below is quietly the standard board.
    layout_rule = rules_module.RULES_BY_ID['board_layout']
    monkeypatch.setitem(
        layout_rule, 'options',
        layout_rule['options'] + [{'id': 'two_islands', 'name': 'Two islands', 'summary': ''}],
    )

    def build(seed=7, **rules):
        chosen = {'board_layout': 'two_islands'}
        chosen.update(rules)
        return Game(['Alice', 'Bob'], [], rng=random.Random(seed), rules=chosen)

    return build


def slots_by_vertex(game) -> dict:
    """Which land *slots* each intersection touches, however they were dealt.

    Deliberately worked out from the layout rather than read off
    `vertex.neighbors['hexes']`, because whether those two agree is the bug.
    """
    touching = {}
    for hex_key in sorted(SLOTS):
        hx, hy, hz = game._parse_key(hex_key)
        for dx, dy, dz in Game.VERTEX_DIRECTIONS:
            vertex_key = game._hex_key(hx + dx, hy + dy, hz + dz)
            touching.setdefault(vertex_key, []).append(hex_key)
    return touching


class TestLandIsWhatWasDealt:
    def test_a_settlement_cannot_stand_on_a_slot_the_pool_dealt_to_the_sea(
            self, two_island_game):
        """The reproduction: 2 intersections ringed by open water took a settlement.

        `place_settlement` reads `vertex.neighbors['hexes']`, which was built
        from the slots the layout set aside for land. A slot the pool dealt an
        `ocean` tile into is water on the board, in the renderer and in every
        production rule — but it was still in that list, so the intersections
        around it looked inland.

        Played with ships, because that is the game a two-island map is for and
        it is the one that generates intersections out on the water at all.
        """
        game = two_island_game(ships=True)
        game.start()

        drowned = sorted(key for key in SLOTS if game.hexes[key].type == 'ocean')
        assert drowned, 'this seed must deal the sea tile into a land slot'

        adrift = [
            vertex_key
            for vertex_key, hex_keys in sorted(slots_by_vertex(game).items())
            if all(game.hexes[key].type == 'ocean' for key in hex_keys)
        ]
        assert adrift, 'the drowned slot must have intersections of its own'

        refused = game.place_settlement(game.current_player_name(), adrift[0])
        assert not refused['success'], f'{adrift[0]} is open water'
        assert refused['code'] == 'INVALID_PLACEMENT'

    def test_no_intersection_on_the_board_touches_only_water(self, two_island_game):
        """The same fix from the board's side: a vertex lists land, or nothing."""
        game = two_island_game(ships=True)
        for vertex in game.vertices.values():
            assert all(
                game.hexes[key].type != 'ocean' for key in vertex.neighbors['hexes']
            ), f'{vertex.key} lists water among its land hexes'


class TestTokensOnlyOnLand:
    def test_a_sea_tile_dealt_into_a_land_slot_takes_no_number(self, two_island_game):
        """The reproduction: the ocean tile came out carrying a 9.

        `_create_hexes` exempted the desert and nothing else, so a sea tile in a
        land pool popped a token out of the box. The renderer would draw a
        number on open water and production would pay nobody for rolling it.
        """
        game = two_island_game()

        assert all(
            hex_obj.number is None
            for hex_obj in game.hexes.values()
            if hex_obj.type in ('ocean', 'desert')
        )
        dealt = sorted(h.number for h in game.hexes.values() if h.number is not None)
        assert dealt == sorted(TWO_ISLANDS['numbers'])


class TestMoreThanOneCoastline:
    def test_every_coastal_edge_is_walked(self, two_island_game):
        """The reproduction: 18 of 32 coastal edges, one ring, walk over.

        The walk followed a single ring from the lowest coastal edge and
        returned it even when the board had a second coast it had never
        reached.
        """
        game = two_island_game(ships=True)
        rings = game._coastline_rings()
        coastal = sorted(key for key in game.edges if game.is_coastal_edge(key))

        assert len(rings) > 1, 'a two-island board has more than one coastline'
        assert sorted(key for ring in rings for key in ring) == coastal
        assert rings == sorted(rings, key=lambda ring: (-len(ring), ring[0]))

    def test_the_sunk_middle_board_walks_its_whole_coast(self):
        """The other reproduction: 18 of 54 edges, and none of the small island.

        `split_the_board` sinks the ring around the centre of a seafaring board,
        which leaves an island inside a lagoon — the coast the old walk missed
        entirely.
        """
        from seafarers_board import seafarers_game

        from .test_islands import split_the_board

        game = seafarers_game()
        split_the_board(game)

        rings = game._coastline_rings()
        coastal = sorted(key for key in game.edges if game.is_coastal_edge(key))
        assert sorted(key for ring in rings for key in ring) == coastal

    def test_harbours_are_shared_out_over_both_coasts(self, two_island_game):
        """Otherwise every harbour crowds onto one island, or onto a lagoon."""
        game = two_island_game(ships=True)
        rings = game._coastline_rings()
        harbours = harbour_edges(game)
        assert harbours

        per_ring = Counter(
            index
            for index, ring in enumerate(rings)
            for edge_key in ring
            if edge_key in harbours
        )
        assert len(per_ring) == len([ring for ring in rings if len(ring) >= 2]), (
            'every coast long enough for a harbour must have one'
        )
        for index, ring in enumerate(rings):
            assert per_ring[index] <= len(ring) // 2, (
                'harbours on one coast must still leave an edge between them'
            )

    def test_one_coast_still_places_the_harbours_it_always_did(self):
        """The hard constraint: the single-ring path must not move a harbour.

        Every seeded board in this suite and both browser suites are pinned to
        where the harbours currently land, and the built-in layouts all have
        exactly one coast. The walk itself takes nothing from `rng`, so what
        has to hold is the sequence of calls `_assign_ports` makes: one shuffle
        of the nine harbour types, then one `randrange` over the whole coast.
        """
        calls = []

        class Recording(random.Random):
            def shuffle(self, sequence):
                calls.append(('shuffle', len(sequence)))
                return super().shuffle(sequence)

            def randrange(self, *args, **kwargs):
                calls.append(('randrange', args))
                return super().randrange(*args, **kwargs)

        game = Game(['A', 'B'], [], rng=Recording(4242), rules={'board_layout': 'random'})
        coast = game._coastline_rings()
        assert len(coast) == 1, 'the standard island has one coastline'

        # Two shuffles for the box of terrain and tokens, then the harbours.
        assert calls == [
            ('shuffle', len(board_module.RESOURCE_TYPES)),
            ('shuffle', len(board_module.NUMBER_TOKENS)),
            ('shuffle', len(board_module.PORT_TYPES)),
            ('randrange', (len(coast[0]),)),
        ]
