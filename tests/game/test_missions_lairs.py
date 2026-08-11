"""Mission: Pirate Lairs — the discovery entry point (expansions.md 980-984).

Every gold field is occupied by a pirate lair, so discovering one drops a
face-down lair token on it, and while that lair sits unturned the gold field is
locked: no road on its edges, no settlement at its corners, until it is captured.
The capture (crews, the die-roll hero battle, the payout) is a later increment.
"""

import random

from game import board as board_module
from game import maps
from game import rules as rules_module
from game.game import Game
from game.missions_lairs import LAIRS_TRACK_LENGTH

MAINLAND = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))

# One gold field among face-down mainland tiles. Gold takes a number token (it
# pays out on its roll), so the six token-taking tiles each get one number.
GOLD_POOL = {
    'mode': 'hidden',
    'terrain': {'gold': 1, 'wood': 2, 'wheat': 2, 'sheep': 1, 'desert': 1},
    'numbers': [3, 4, 5, 6, 9, 10],
}


def _map() -> dict:
    sea_count = len(maps.frame_hex_keys(3)) - len(MAINLAND)
    return {
        'map_version': 2, 'id': 'lair-map', 'name': 'Lair Map',
        'frame': {'radius': 3},
        'regions': [
            {'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND, 'pool': GOLD_POOL},
            {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
             'pool': {'mode': 'shuffled', 'terrain': {'sea': sea_count}, 'numbers': []}},
        ],
        'harbours': {'mode': 'bag', 'types': {}},
    }


def _game(seed=5) -> Game:
    document = _map()
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_pirate_lairs'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(seed), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    return game


def _gold_hex(game) -> str:
    # The board holds the real terrain even while the tile is face-down.
    return next(key for key, hex_obj in game.hexes.items() if hex_obj.type == 'gold')


def _corner_of(game, hex_key) -> str:
    return next(v for v in game.vertices
               if hex_key in game.vertices[v].neighbors['hexes'])


class TestDiscoveringAGoldFieldPlacesALair:
    def test_the_track_is_registered_when_the_mission_is_on(self):
        game = _game()
        assert game.ep.track_length('pirate_lairs') == LAIRS_TRACK_LENGTH

    def test_revealing_a_gold_field_drops_a_lair_from_the_supply(self):
        game = _game()
        gold = _gold_hex(game)
        before = game.ep.token_supply['lair_token']

        game._reveal_hex(gold, 'Alice')

        assert gold in game.ep.lairs, 'discovering a gold field placed no lair'
        assert game.ep.lairs[gold]['captured'] is False
        assert game.ep.token_supply['lair_token'] == before - 1

    def test_a_lair_locks_building_on_its_field_until_captured(self):
        game = _game()
        gold = _gold_hex(game)
        game._reveal_hex(gold, 'Alice')
        corner_hexes = game.vertices[_corner_of(game, gold)].neighbors['hexes']

        refusal = game.pirate_lair_build_refusal(corner_hexes)
        assert refusal is not None
        assert refusal['code'] == 'PIRATE_LAIR_BLOCKS'

        # Capturing the lair lifts the lock.
        game.ep.lairs[gold]['captured'] = True
        assert game.pirate_lair_build_refusal(corner_hexes) is None

    def test_no_lair_where_the_mission_is_off(self):
        game = _game()
        game.rules['mission_pirate_lairs'] = False
        gold = _gold_hex(game)
        game._reveal_hex(gold, 'Alice')
        assert gold not in game.ep.lairs


def _edges_touching(game, hex_key):
    return [e for e in sorted(game.edges)
            if any(hex_key in game.vertices[v].neighbors['hexes']
                   for v in game.edges[e].neighbors['vertices'])]


def _plant_crew_ship(game, name, edge_key, crews):
    game.edges[edge_key].ship = {
        'player': name, 'kind': 'transport',
        'cargo': [{'type': 'crew', 'size': 'small'} for _ in range(crews)],
        'id': 1, 'built_turn': 0,
    }
    game.get_player(name).ships.append(edge_key)
    game.get_player(name).crews += crews


class TestCapturingALair:
    def _marker(self, game, name):
        return game.ep.markers[name]['pirate_lairs']

    def test_the_third_crew_captures_and_rewards_both_players(self):
        game = _game(seed=3)
        gold = _gold_hex(game)
        game._reveal_hex(gold, 'Alice')
        edges = _edges_touching(game, gold)
        _plant_crew_ship(game, 'Alice', edges[0], 2)
        _plant_crew_ship(game, 'Bob', edges[1], 1)

        # Two crews from Alice do not fill the lair.
        first = game.land_crews_on_lair('Alice', edges[0], gold)
        assert first['landed'] == 2 and first['captured'] is False
        assert game.ep.lairs[gold]['captured'] is False

        # Bob's crew is the third — it captures.
        second = game.land_crews_on_lair('Bob', edges[1], gold)
        assert second['captured'] is True
        assert game.ep.lairs[gold]['captured'] is True

        # Both participants moved at least a space; the hero moved one extra.
        assert self._marker(game, 'Alice') >= 1
        assert self._marker(game, 'Bob') >= 1
        hero = second['hero']
        assert self._marker(game, hero) == 2

        # The hero returned one crew to their supply.
        assert game.get_player(hero).crews == (2 if hero == 'Alice' else 1) - 1

    def test_a_captured_lair_unlocks_its_field(self):
        game = _game()
        gold = _gold_hex(game)
        game._reveal_hex(gold, 'Alice')
        edges = _edges_touching(game, gold)
        _plant_crew_ship(game, 'Alice', edges[0], 2)
        _plant_crew_ship(game, 'Bob', edges[1], 1)
        game.land_crews_on_lair('Alice', edges[0], gold)
        game.land_crews_on_lair('Bob', edges[1], gold)

        corner = game.vertices[_corner_of(game, gold)].neighbors['hexes']
        assert game.pirate_lair_build_refusal(corner) is None

    def test_a_ship_that_does_not_point_at_the_lair_lands_nothing(self):
        game = _game()
        gold = _gold_hex(game)
        game._reveal_hex(gold, 'Alice')
        far = next(e for e in sorted(game.edges) if e not in _edges_touching(game, gold))
        _plant_crew_ship(game, 'Alice', far, 2)
        result = game.land_crews_on_lair('Alice', far, gold)
        assert result['code'] == 'INVALID_PLACEMENT'

    def test_a_ship_picks_surviving_crews_back_up(self):
        game = _game(seed=3)
        gold = _gold_hex(game)
        game._reveal_hex(gold, 'Alice')
        edges = _edges_touching(game, gold)
        _plant_crew_ship(game, 'Alice', edges[0], 2)
        _plant_crew_ship(game, 'Bob', edges[1], 1)
        game.land_crews_on_lair('Alice', edges[0], gold)
        game.land_crews_on_lair('Bob', edges[1], gold)

        survivors = dict(game.ep.lairs[gold]['crews'])
        assert survivors, 'a capture should leave some crews beside the lair'
        name = next(iter(survivors))
        edge = edges[0] if name == 'Alice' else edges[1]  # their now-empty ship
        before = survivors[name]

        result = game.pickup_crews_from_lair(name, edge, gold)
        assert result['picked_up'] == min(before, 2)
        ship = game.edges[edge].ship
        aboard = sum(1 for piece in ship['cargo'] if piece['type'] == 'crew')
        assert aboard == result['picked_up']
        assert game.ep.lairs[gold]['crews'].get(name, 0) == before - result['picked_up']
