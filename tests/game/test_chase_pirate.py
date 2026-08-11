"""Chasing an opponent's pirate ship (expansions.md 951-958).

Each test names something a player would notice break: a battle-ready ship that
rolled a 6 but chased nobody, a failed roll that still shoved the pirate off, a
ship that already moved yet got to fight anyway, a ship nowhere near a pirate
that rolled all the same, and the base game left untouched when the rule is off.

The die is made deterministic the way the rest of the engine is: a seeded
`random.Random` is swapped onto the game just before the roll, so seed 19 rolls
a 6 (a chase) and seed 0 rolls a 4 (no chase, unless the Pirate Bonus advantage
widens the winning faces). Board generation has already consumed the fixture's
own RNG by then, so the swap is what fixes the single face the chase reads.
"""

import random

from game import rules as rules_module
from game.game import Game

# random.Random(19).randint(1, 6) == 6; random.Random(0).randint(1, 6) == 4.
SEED_ROLLS_SIX = 19
SEED_ROLLS_FOUR = 0


def _game(chase=True, **overrides):
    rules = dict(rules_module.defaults())
    if chase:
        rules['pirate_ship_instead_of_robber'] = True
        rules['gold'] = True
        rules['transport_ships'] = True
        rules['harbor_settlements'] = True
        rules['chase_pirate'] = True
    rules['turn_order'] = 'lobby'
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _build_ship(game, name, used_vertices):
    """Plant a harbor and a transport ship for a player; return (edge, sea hex).

    Skips vertices already used so Alice and Bob get distinct harbors. Placed
    directly rather than through `build_transport_ship` so a non-current player
    can own one — the build method enforces the turn.
    """
    for key in sorted(game.vertices):
        if key in used_vertices:
            continue
        vertex = game.vertices[key]
        if not (vertex.neighbors.get('hexes') and game.is_coastal_settlement_site(key)):
            continue
        sea_edge = next(
            (e for e in vertex.neighbors['edges']
             if game.is_sea_edge(e) and game.edges[e].ship is None),
            None,
        )
        if sea_edge is None:
            continue
        used_vertices.add(key)
        vertex.building = {'type': 'harbor_settlement', 'player': name, 'basin': []}
        game.get_player(name).harbor_settlements.append(key)
        game.transport_ship_counter += 1
        game.edges[sea_edge].ship = {
            'player': name,
            'built_turn': 0,
            'kind': 'transport',
            'cargo': [],
            'id': game.transport_ship_counter,
        }
        game.get_player(name).ships.append(sea_edge)
        sea_hex = next(
            h for h in game.edges[sea_edge].neighbors['hexes']
            if game.hexes[h].type == 'ocean'
        )
        return sea_edge, sea_hex
    raise AssertionError('no free coastal vertex with a sea edge on this board')


def _setup(game):
    """Alice's ship beside Bob's pirate; Bob's ship elsewhere to steal from."""
    used = set()
    alice_edge, alice_hex = _build_ship(game, 'Alice', used)
    _bob_edge, bob_hex = _build_ship(game, 'Bob', used)
    game.ep.place_pirate('Bob', alice_hex)  # a pirate sits beside Alice's ship
    return alice_edge, alice_hex, bob_hex


class TestChasingSucceeds:
    def test_a_six_chases_the_pirate_and_spends_the_ship(self):
        game = _game()
        alice_edge, _alice_hex, bob_hex = _setup(game)
        ship_id = game.edges[alice_edge].ship['id']
        game.get_player('Bob').resources = {'ore': 1}
        game.rng = random.Random(SEED_ROLLS_SIX)

        result = game.chase_pirate('Alice', alice_edge)
        assert result['success'] and result['chased'] is True
        assert result['roll'] == 6
        assert game.ep.pirate_of('Bob') is None, 'the chased pirate left the board'
        assert game.must_move_robber is True
        assert ship_id in game.transport_ships_moved, 'the ship spent its action'

        # The chaser repositions and steals exactly as a fresh placement does.
        assert game.place_pirate_ship('Alice', bob_hex)['victims'] == ['Bob']
        assert game.steal_from_victim('Alice', 'Bob')['stolen'] == 'ore'


class TestChasingFails:
    def test_a_non_six_leaves_the_pirate_but_still_spends_the_ship(self):
        game = _game()
        alice_edge, alice_hex, _bob_hex = _setup(game)
        ship_id = game.edges[alice_edge].ship['id']
        game.rng = random.Random(SEED_ROLLS_FOUR)

        result = game.chase_pirate('Alice', alice_edge)
        assert result['success'] and result['chased'] is False
        assert result['roll'] == 4
        assert game.ep.pirate_of('Bob') == alice_hex, 'the pirate did not move'
        assert game.must_move_robber is False
        assert ship_id in game.transport_ships_moved, 'the ship still spent its action'

    def test_the_pirate_bonus_advantage_wins_the_chase_on_a_four(self):
        """A spice village's Pirate Bonus widens the winning faces to 4-5-6."""
        game = _game()
        alice_edge, _alice_hex, _bob_hex = _setup(game)
        game.ep.grant_advantage('Alice', 'pirate_bonus')
        game.rng = random.Random(SEED_ROLLS_FOUR)

        result = game.chase_pirate('Alice', alice_edge)
        assert result['roll'] == 4 and result['chased'] is True
        assert game.ep.pirate_of('Bob') is None


class TestNotBattleReady:
    def test_a_ship_that_already_moved_cannot_chase(self):
        game = _game()
        alice_edge, _alice_hex, _bob_hex = _setup(game)
        game.transport_ships_moved.add(game.edges[alice_edge].ship['id'])
        game.rng = random.Random(SEED_ROLLS_SIX)

        assert game.chase_pirate('Alice', alice_edge)['code'] == 'NOT_BATTLE_READY'
        assert game.ep.pirate_of('Bob') is not None

    def test_a_ship_beside_no_pirate_cannot_chase(self):
        game = _game()
        used = set()
        alice_edge, _alice_hex = _build_ship(game, 'Alice', used)
        game.rng = random.Random(SEED_ROLLS_SIX)

        assert game.chase_pirate('Alice', alice_edge)['code'] == 'NO_PIRATE_ADJACENT'


class TestRuleOff:
    def test_a_table_with_transports_but_not_the_chase_rule_chases_nothing(self):
        # Transports and the pirate stay on so a real ship and pirate exist; only
        # the chase rule is off, which is the one thing the guard must catch.
        game = _game(
            chase=False,
            pirate_ship_instead_of_robber=True,
            gold=True,
            transport_ships=True,
            harbor_settlements=True,
        )
        alice_edge, alice_hex, _bob_hex = _setup(game)
        game.rng = random.Random(SEED_ROLLS_SIX)

        assert game.chase_pirate('Alice', alice_edge)['code'] == 'RULE_NOT_IN_PLAY'
        assert game.ep.pirate_of('Bob') == alice_hex
