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
