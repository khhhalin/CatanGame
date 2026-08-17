"""The explicit-adjacency channel: non-standard pieces a map injects.

The board is one cube-coordinate lattice, and everything on it — corners, sides,
their neighbours — is derived algebraically from the %3 invariant. That makes a
piece the lattice does not predict impossible to express: a plaza vertex at a hex
centre, or an interior spoke edge bordering one hex from inside (the Traders &
Barbarians trade-hex plaza is the motivating case). This channel lets a map
declare such pieces with explicit neighbour lists, without loosening the %3
guards for the standard pieces.

These tests pin the mechanism against the *generated* board — never a copied
literal — and pin that a map with no such pieces still produces only standard
ones, so every existing board is unchanged.
"""

import random

from game import board as board_module
from game import maps, persistence
from game.game import Game

# A plaza at the centre hex, and one spoke running from it to the centre hex's
# top-right corner. The corner is a standard lattice vertex the board generates
# on its own (VERTEX_DIRECTIONS[0] off 0,0,0), so the spoke splices a
# non-standard side onto a real corner.
CENTRE_HEX = '0,0,0'
CORNER = '1,-2,1'
PLAZA = 'plaza:0,0,0'
SPOKE = 'spoke:0,0,0|1,-2,1'


def base_map(**overrides) -> dict:
    """A small valid map: a 7-hex mainland in a radius-3 frame, sea around it."""
    mainland = maps.sort_hex_keys(
        '{},{},{}'.format(*coords) for coords in board_module._hexagon(1)
    )
    document = {
        'map_version': 2,
        'id': 'plaza-test',
        'name': 'Plaza Test',
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


def plaza_map(**overrides) -> dict:
    """`base_map` with the plaza vertex and one spoke edge declared."""
    return base_map(
        plaza_vertices={
            PLAZA: {'hexes': [CENTRE_HEX], 'vertices': [], 'edges': [SPOKE]},
        },
        spoke_edges={
            SPOKE: {'hexes': [CENTRE_HEX], 'vertices': [PLAZA, CORNER], 'edges': []},
        },
        **overrides,
    )


def game_on(document, seed=1, **rules) -> Game:
    chosen = {'board_layout': 'custom', 'board_map': document['id']}
    chosen.update(rules)
    return Game(['A', 'B'], [], rng=random.Random(seed), rules=chosen,
                map_definition=maps.parse_map(document))


def playing(game) -> Game:
    """Drop the game straight into normal play with A to act."""
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.start_turn()
    game.get_player('A').resources = {
        'wood': 5, 'brick': 5, 'sheep': 5, 'wheat': 5, 'ore': 5,
    }
    return game


def give_building(game, player_name, vertex_key, building_type='settlement'):
    """Seed a starting building without going through the placement rules.

    A playing-phase build must connect to the player's existing network, so the
    starting anchor is set up directly and the *next* piece — the one on the
    tagged geometry — is what the real rules place.
    """
    game.vertices[vertex_key].building = {'type': building_type, 'player': player_name}
    game.get_player(player_name).settlements.append(vertex_key)


class TestTheTaggedPiecesAreOnTheBoard:
    def test_the_plaza_and_the_spoke_exist_and_are_tagged(self):
        game = game_on(plaza_map())
        assert game.vertices[PLAZA].kind == 'plaza'
        assert game.edges[SPOKE].kind == 'spoke'

    def test_their_neighbours_are_exactly_what_the_map_declared(self):
        """Read off the generated board, not a copy of the literal."""
        game = game_on(plaza_map())
        plaza = game.vertices[PLAZA]
        spoke = game.edges[SPOKE]
        assert plaza.neighbors['hexes'] == [CENTRE_HEX]
        assert plaza.neighbors['edges'] == [SPOKE]
        assert spoke.neighbors['hexes'] == [CENTRE_HEX]
        assert spoke.neighbors['vertices'] == [PLAZA, CORNER]

    def test_the_relationship_is_spliced_back_onto_the_standard_corner(self):
        """The corner is a standard lattice vertex; the spoke must join its
        edge list, or a walk from the corner would never find the spoke."""
        game = game_on(plaza_map())
        corner = game.vertices[CORNER]
        assert corner.kind == 'standard'
        assert SPOKE in corner.neighbors['edges']


class TestBuildingOnTheTaggedPieces:
    def test_a_road_builds_on_the_spoke_and_a_settlement_on_the_plaza(self):
        game = playing(game_on(plaza_map()))
        # A settlement on the standard corner anchors A's network to the spoke.
        give_building(game, 'A', CORNER)
        # The road sits on the interior spoke, connected through that corner.
        assert game.build_road('A', SPOKE)['success']
        assert game.edges[SPOKE].road == {'player': 'A'}
        # The plaza carries a settlement: it stands on a hex (its centre), and
        # the spoke road connects it — the whole point of an injectable corner.
        assert game.place_settlement('A', PLAZA)['success']
        assert game.vertices[PLAZA].building == {'type': 'settlement', 'player': 'A'}

    def test_the_spoke_is_not_mistaken_for_coast(self):
        """It borders one hex, so the coastal test would count it — but it is
        interior, never coast, and must never take a harbour."""
        game = game_on(plaza_map())
        assert game.land_hexes_of_edge(SPOKE) == [CENTRE_HEX]
        assert not game.is_coastal_edge(SPOKE)
        assert game.edges[SPOKE].port is None


class TestAMapWithNoSuchPiecesIsUnchanged:
    def test_the_plain_map_declares_no_explicit_pieces(self):
        defn = maps.parse_map(base_map())
        assert defn.plaza_vertices == ()
        assert defn.spoke_edges == ()

    def test_every_piece_on_a_plain_board_is_standard(self):
        game = game_on(base_map())
        assert all(v.kind == 'standard' for v in game.vertices.values())
        assert all(e.kind == 'standard' for e in game.edges.values())

    def test_the_plaza_only_appears_where_it_is_declared(self):
        without = game_on(base_map())
        assert PLAZA not in without.vertices
        assert SPOKE not in without.edges


class TestPersistence:
    def test_the_definition_round_trips_through_json(self):
        defn = maps.parse_map(plaza_map())
        assert maps.parse_map(defn.to_json()) == defn

    def test_the_tagged_pieces_and_a_spoke_road_survive_a_save(self):
        game = playing(game_on(plaza_map()))
        give_building(game, 'A', CORNER)
        assert game.build_road('A', SPOKE)['success']

        restored = persistence.deserialize(persistence.serialize(game))

        assert restored.vertices[PLAZA].kind == 'plaza'
        assert restored.edges[SPOKE].kind == 'spoke'
        assert restored.vertices[PLAZA].neighbors['hexes'] == [CENTRE_HEX]
        assert SPOKE in restored.vertices[CORNER].neighbors['edges']
        assert restored.edges[SPOKE].road == {'player': 'A'}
