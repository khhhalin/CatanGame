"""Mission: Spices for Catan — discovery, the crew-for-sack trade, delivery.

Discovering a spice hex stocks its village with one sack per player and deals it
an advantage; a crew-laden ship trades a crew for a sack and earns the advantage;
the village locks building until befriended; a spice-laden ship delivers at a
Council-of-Catan dock, advancing the marker one space per sack (expansions.md
1021-1039).
"""

import random

from game import board as board_module
from game import maps
from game import rules as rules_module
from game.ep import VILLAGE_ADVANTAGES
from game.game import Game
from game.missions_spices import SPICES_TRACK_LENGTH

MAINLAND = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))

# One spice hex among face-down mainland tiles. A spice hex takes no number token
# of its own, so only the five resource tiles each get one.
SPICE_POOL = {
    'mode': 'hidden',
    'terrain': {'spice': 1, 'wood': 2, 'wheat': 2, 'sheep': 1, 'desert': 1},
    'numbers': [3, 4, 5, 6, 9],
}


def _map() -> dict:
    sea_count = len(maps.frame_hex_keys(3)) - len(MAINLAND)
    return {
        'map_version': 2, 'id': 'spice-map', 'name': 'Spice Map',
        'frame': {'radius': 3},
        'regions': [
            {'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND, 'pool': SPICE_POOL},
            {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
             'pool': {'mode': 'shuffled', 'terrain': {'sea': sea_count}, 'numbers': []}},
        ],
        'harbours': {'mode': 'bag', 'types': {}},
    }


def _game(seed=5) -> Game:
    document = _map()
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_spices'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(seed), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    return game


def _spice_hex(game) -> str:
    return next(key for key, hex_obj in game.hexes.items() if hex_obj.type == 'spice')


def _corner_of(game, hex_key) -> str:
    return next(v for v in game.vertices
               if hex_key in game.vertices[v].neighbors['hexes'])


def _edges_touching(game, hex_key):
    return [e for e in sorted(game.edges)
            if any(hex_key in game.vertices[v].neighbors['hexes']
                   for v in game.edges[e].neighbors['vertices'])]


def _border_edges(game, hex_key):
    return [e for e, edge in sorted(game.edges.items())
            if hex_key in edge.neighbors['hexes']]


def _sea_hex(game) -> str:
    return next(key for key, hex_obj in game.hexes.items()
                if hex_obj.type == 'ocean' and _border_edges(game, key))


def _council_hex(game) -> str:
    council = _sea_hex(game)
    game.hexes[council].meta = maps.HexMeta(docks=(0,))
    return council


def _plant_ship(game, name, edge_key, cargo):
    game.edges[edge_key].ship = {
        'player': name, 'kind': 'transport', 'cargo': list(cargo),
        'id': 1, 'built_turn': 0,
    }
    game.get_player(name).ships.append(edge_key)


def _crew(n):
    return [{'type': 'crew', 'size': 'small'} for _ in range(n)]


class TestDiscoveringASpiceHex:
    def test_the_track_is_registered_when_the_mission_is_on(self):
        game = _game()
        assert game.ep.track_length('spices') == SPICES_TRACK_LENGTH

    def test_discovery_stocks_the_village_and_pays_two_gold(self):
        game = _game()
        spice = _spice_hex(game)
        gold_before = game.get_player('Alice').gold
        supply_before = game.ep.token_supply['spice_sack']

        game._reveal_hex(spice, 'Alice')

        assert spice in game.ep.spice_hexes
        village = game.ep.spice_hexes[spice]
        # One sack per player from the supply.
        assert village['sacks'] == len(game.players)
        assert game.ep.token_supply['spice_sack'] == supply_before - len(game.players)
        assert village['advantage'] in VILLAGE_ADVANTAGES
        assert village['crews'] == []
        assert game.get_player('Alice').gold == gold_before + 2

    def test_no_village_where_the_mission_is_off(self):
        game = _game()
        game.rules['mission_spices'] = False
        spice = _spice_hex(game)
        game._reveal_hex(spice, 'Alice')
        assert spice not in game.ep.spice_hexes


class TestTheBuildLock:
    def test_a_spice_hex_locks_building_until_the_player_befriends_it(self):
        game = _game()
        spice = _spice_hex(game)
        game._reveal_hex(spice, 'Alice')
        corner_hexes = game.vertices[_corner_of(game, spice)].neighbors['hexes']

        refusal = game.spice_build_refusal('Alice', corner_hexes)
        assert refusal is not None
        assert refusal['code'] == 'SPICE_VILLAGE_BLOCKS'

        # Befriending lifts the lock — for that player only.
        game.ep.spice_hexes[spice]['crews'].append('Alice')
        assert game.spice_build_refusal('Alice', corner_hexes) is None
        assert game.spice_build_refusal('Bob', corner_hexes) is not None


class TestBefriendingAVillage:
    def _befriend_setup(self, game):
        spice = _spice_hex(game)
        game._reveal_hex(spice, 'Alice')
        edge = _edges_touching(game, spice)[0]
        _plant_ship(game, 'Alice', edge, _crew(1))
        return spice, edge

    def test_a_crew_trades_for_a_sack_and_earns_the_advantage(self):
        game = _game()
        spice, edge = self._befriend_setup(game)
        advantage = game.ep.spice_hexes[spice]['advantage']
        sacks_before = game.ep.spice_hexes[spice]['sacks']

        result = game.befriend_spice_village('Alice', edge, spice)

        assert result['success'] is True and result['advantage'] == advantage
        village = game.ep.spice_hexes[spice]
        assert 'Alice' in village['crews']
        assert village['sacks'] == sacks_before - 1
        # The crew stepped off; a sack came aboard.
        cargo = [p['type'] for p in game.edges[edge].ship['cargo']]
        assert cargo == ['spice_sack']
        assert game.ep.has_advantage('Alice', advantage)

    def test_a_player_cannot_befriend_the_same_village_twice(self):
        game = _game()
        spice, edge = self._befriend_setup(game)
        game.befriend_spice_village('Alice', edge, spice)
        # Re-crew the ship and try again.
        game.edges[edge].ship['cargo'] = _crew(1)
        result = game.befriend_spice_village('Alice', edge, spice)
        assert result['code'] == 'ALREADY_FRIENDS'

    def test_a_ship_without_a_crew_cannot_befriend(self):
        game = _game()
        spice = _spice_hex(game)
        game._reveal_hex(spice, 'Alice')
        edge = _edges_touching(game, spice)[0]
        _plant_ship(game, 'Alice', edge, [])
        assert game.befriend_spice_village('Alice', edge, spice)['code'] == 'NO_CREWS'

    def test_a_ship_that_does_not_point_at_the_village_befriends_nothing(self):
        game = _game()
        spice = _spice_hex(game)
        game._reveal_hex(spice, 'Alice')
        far = next(e for e in sorted(game.edges) if e not in _edges_touching(game, spice))
        _plant_ship(game, 'Alice', far, _crew(1))
        assert game.befriend_spice_village('Alice', far, spice)['code'] == 'INVALID_PLACEMENT'


class TestDeliveringSpices:
    def test_delivery_advances_the_marker_per_sack_and_removes_them(self):
        game = _game()
        council = _council_hex(game)
        edge = _border_edges(game, council)[0]
        _plant_ship(game, 'Alice', edge,
                    [{'type': 'spice_sack', 'size': 'small'},
                     {'type': 'spice_sack', 'size': 'small'}])
        supply_before = game.ep.token_supply['spice_sack']

        result = game.deliver_spices('Alice', edge, council)

        assert result['success'] is True and result['delivered'] == 2
        assert result['marker'] == 2
        assert game.ep.marker('Alice', 'spices') == 2
        assert game.edges[edge].ship['cargo'] == []
        # Delivered sacks leave the game — they do not return to the supply.
        assert game.ep.token_supply['spice_sack'] == supply_before

    def test_delivery_needs_an_actual_dock(self):
        game = _game()
        plain = _sea_hex(game)
        edge = _border_edges(game, plain)[0]
        _plant_ship(game, 'Alice', edge, [{'type': 'spice_sack', 'size': 'small'}])
        assert game.deliver_spices('Alice', edge, plain)['code'] == 'INVALID_TARGET'
