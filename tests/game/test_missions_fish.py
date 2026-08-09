"""Mission: Fish for Catan — discovery, placement, the catch and the delivery.

Discovering a fish shoal pins a placement number to it and pays 2 gold; a
matching placement roll drops a haul from the supply onto it; an empty ship
scoops the haul; a fish-laden ship unloads it at a Council-of-Catan dock and
advances the mission marker (expansions.md 1000-1019).
"""

import random

from game import board as board_module
from game import maps
from game import rules as rules_module
from game.game import Game
from game.missions_fish import FISH_TRACK_LENGTH

MAINLAND = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))

# One fish shoal among face-down mainland tiles. A shoal takes no number token of
# its own (it is not a producing tile), so only the five token-taking resource
# tiles each get one number.
FISH_POOL = {
    'mode': 'hidden',
    'terrain': {'fish': 1, 'wood': 2, 'wheat': 2, 'sheep': 1, 'desert': 1},
    'numbers': [3, 4, 5, 6, 9],
}


class _FixedDie:
    """A drop-in for `game.rng` that always rolls the same face, so a placement
    roll can be pinned to a shoal's number in a test."""

    def __init__(self, value):
        self.value = value

    def randint(self, low, high):
        return self.value


def _map() -> dict:
    sea_count = len(maps.frame_hex_keys(3)) - len(MAINLAND)
    return {
        'map_version': 2, 'id': 'fish-map', 'name': 'Fish Map',
        'frame': {'radius': 3},
        'regions': [
            {'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND, 'pool': FISH_POOL},
            {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
             'pool': {'mode': 'shuffled', 'terrain': {'sea': sea_count}, 'numbers': []}},
        ],
        'harbours': {'mode': 'bag', 'types': {}},
    }


def _game(seed=5) -> Game:
    document = _map()
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(seed), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    return game


def _fish_hex(game) -> str:
    # The board holds the real terrain even while the tile is face-down.
    return next(key for key, hex_obj in game.hexes.items() if hex_obj.type == 'fish')


def _edges_touching(game, hex_key):
    return [e for e in sorted(game.edges)
            if any(hex_key in game.vertices[v].neighbors['hexes']
                   for v in game.edges[e].neighbors['vertices'])]


def _plant_ship(game, name, edge_key, cargo):
    game.edges[edge_key].ship = {
        'player': name, 'kind': 'transport', 'cargo': list(cargo),
        'id': 1, 'built_turn': 0,
    }
    game.get_player(name).ships.append(edge_key)


def _border_edges(game, hex_key):
    """Edges that border a hex, sea included — a sea hex is absent from a
    vertex's hex list but every edge lists whichever hexes it separates."""
    return [e for e, edge in sorted(game.edges.items())
            if hex_key in edge.neighbors['hexes']]


def _sea_hex(game) -> str:
    """A sea hex with border edges, so a ship can sit on its coast."""
    return next(key for key, hex_obj in game.hexes.items()
                if hex_obj.type == 'ocean' and _border_edges(game, key))


def _council_hex(game) -> str:
    """Turn a sea hex into a Council-of-Catan hex by giving it a dock."""
    council = _sea_hex(game)
    game.hexes[council].meta = maps.HexMeta(docks=(0,))
    return council


class TestDiscoveringAShoal:
    def test_the_track_is_registered_when_the_mission_is_on(self):
        game = _game()
        assert game.ep.track_length('fish') == FISH_TRACK_LENGTH

    def test_revealing_a_shoal_pins_a_number_and_pays_two_gold(self):
        game = _game()
        shoal = _fish_hex(game)
        before = game.get_player('Alice').gold

        game._reveal_hex(shoal, 'Alice')

        assert shoal in game.ep.fish_shoals
        assert 1 <= game.ep.fish_shoals[shoal]['number'] <= 6
        assert game.ep.fish_shoals[shoal]['haul'] is False
        assert game.get_player('Alice').gold == before + 2

    def test_no_shoal_where_the_mission_is_off(self):
        game = _game()
        game.rules['mission_fish'] = False
        shoal = _fish_hex(game)
        game._reveal_hex(shoal, 'Alice')
        assert shoal not in game.ep.fish_shoals


class TestPlacingAHaul:
    def test_a_matching_roll_lands_a_haul_from_the_supply(self):
        game = _game()
        shoal = _fish_hex(game)
        game._reveal_hex(shoal, 'Alice')
        game.ep.fish_shoals[shoal]['number'] = 4
        game.rng = _FixedDie(4)
        before = game.ep.token_supply['fish_haul']

        result = game.roll_fish_haul('Alice')

        assert result['roll'] == 4 and result['placed'] == shoal
        assert game.ep.fish_shoals[shoal]['haul'] is True
        assert game.ep.token_supply['fish_haul'] == before - 1

    def test_a_roll_matching_nothing_lands_no_haul(self):
        game = _game()
        shoal = _fish_hex(game)
        game._reveal_hex(shoal, 'Alice')
        game.ep.fish_shoals[shoal]['number'] = 4
        game.rng = _FixedDie(2)
        before = game.ep.token_supply['fish_haul']

        result = game.roll_fish_haul('Alice')

        assert result['placed'] is None
        assert game.ep.token_supply['fish_haul'] == before

    def test_a_shoal_that_already_holds_a_haul_takes_no_second(self):
        game = _game()
        shoal = _fish_hex(game)
        game._reveal_hex(shoal, 'Alice')
        game.ep.fish_shoals[shoal].update(number=4, haul=True)
        game.rng = _FixedDie(4)
        before = game.ep.token_supply['fish_haul']

        assert game.roll_fish_haul('Alice')['placed'] is None
        assert game.ep.token_supply['fish_haul'] == before

    def test_a_shoal_under_a_pirate_takes_no_haul(self):
        game = _game()
        shoal = _fish_hex(game)
        game._reveal_hex(shoal, 'Alice')
        game.ep.fish_shoals[shoal]['number'] = 4
        game.ep.place_pirate('Bob', shoal)
        game.rng = _FixedDie(4)

        assert game.roll_fish_haul('Alice')['placed'] is None


class TestCatchingAndDelivering:
    def _shoal_with_haul(self, game):
        shoal = _fish_hex(game)
        game._reveal_hex(shoal, 'Alice')
        game.ep.fish_shoals[shoal]['haul'] = True
        return shoal

    def test_an_empty_ship_scoops_the_haul(self):
        game = _game()
        shoal = self._shoal_with_haul(game)
        edge = _edges_touching(game, shoal)[0]
        _plant_ship(game, 'Alice', edge, [])

        result = game.catch_fish('Alice', edge, shoal)

        assert result['success'] is True
        assert game.ep.fish_shoals[shoal]['haul'] is False
        cargo = game.edges[edge].ship['cargo']
        assert [p['type'] for p in cargo] == ['fish_haul']

    def test_a_laden_ship_cannot_catch_a_second_haul(self):
        game = _game()
        shoal = self._shoal_with_haul(game)
        edge = _edges_touching(game, shoal)[0]
        _plant_ship(game, 'Alice', edge, [{'type': 'fish_haul', 'size': 'large'}])

        result = game.catch_fish('Alice', edge, shoal)

        assert result['code'] == 'HOLD_FULL'
        assert game.ep.fish_shoals[shoal]['haul'] is True

    def test_a_ship_that_does_not_point_at_the_shoal_catches_nothing(self):
        game = _game()
        shoal = self._shoal_with_haul(game)
        far = next(e for e in sorted(game.edges) if e not in _edges_touching(game, shoal))
        _plant_ship(game, 'Alice', far, [])

        assert game.catch_fish('Alice', far, shoal)['code'] == 'INVALID_PLACEMENT'

    def test_delivering_at_a_dock_returns_the_haul_and_advances_the_marker(self):
        game = _game()
        council = _council_hex(game)
        edge = _border_edges(game, council)[0]
        _plant_ship(game, 'Alice', edge, [{'type': 'fish_haul', 'size': 'large'}])
        supply_before = game.ep.token_supply['fish_haul']

        result = game.deliver_fish('Alice', edge, council)

        assert result['success'] is True and result['marker'] == 1
        assert game.ep.marker('Alice', 'fish') == 1
        assert game.ep.token_supply['fish_haul'] == supply_before + 1
        assert game.edges[edge].ship['cargo'] == []

    def test_delivering_needs_an_actual_dock(self):
        game = _game()
        plain = _sea_hex(game)
        edge = _border_edges(game, plain)[0]
        _plant_ship(game, 'Alice', edge, [{'type': 'fish_haul', 'size': 'large'}])

        assert game.deliver_fish('Alice', edge, plain)['code'] == 'INVALID_TARGET'


class TestThePirateScattersAHaul:
    def test_strip_returns_a_haul_to_the_supply(self):
        game = _game()
        shoal = _fish_hex(game)
        game._reveal_hex(shoal, 'Alice')
        game.ep.fish_shoals[shoal]['haul'] = True
        before = game.ep.token_supply['fish_haul']

        game.strip_fish_haul(shoal)

        assert game.ep.fish_shoals[shoal]['haul'] is False
        assert game.ep.token_supply['fish_haul'] == before + 1
