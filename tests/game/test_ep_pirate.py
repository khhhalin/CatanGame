"""The Explorers & Pirates pirate ship (expansions.md 841, 843, 934-949).

Each test names something a player would notice break: a 7 that placed no
pirate, a pirate that stole from nobody though a ship sat beside it, an
empty-handed victim who paid no gold, a ship that crossed an opponent's pirate
without paying tribute, and the base-game robber path left untouched when the
rule is off.

`gold` rides along because the pirate rule depends on it (an empty victim pays
gold, tribute is paid in gold); `transport_ships` and `harbor_settlements` ride
along because the only ships to steal from or charge tribute on are transports.
"""

import random

from game import rules as rules_module
from game.game import Game


def _game(pirate=True, **overrides):
    rules = dict(rules_module.defaults())
    if pirate:
        rules['pirate_ship_instead_of_robber'] = True
        rules['gold'] = True
        rules['transport_ships'] = True
        rules['harbor_settlements'] = True
    rules['turn_order'] = 'lobby'
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _place_harbor(game, name):
    for key in sorted(game.vertices):
        vertex = game.vertices[key]
        if vertex.neighbors.get('hexes') and game.is_coastal_settlement_site(key):
            vertex.building = {'type': 'harbor_settlement', 'player': name, 'basin': []}
            game.get_player(name).harbor_settlements.append(key)
            return key
    raise AssertionError('no coastal vertex on this board')


def _sea_edge_at(game, vertex_key):
    for edge_key in game.vertices[vertex_key].neighbors['edges']:
        if game.is_sea_edge(edge_key):
            return edge_key
    raise AssertionError('coastal vertex has no sea edge')


def _build_ship(game, name):
    """Plant a harbor and a transport ship for any player; return (edge, sea hex).

    The ship is placed directly rather than through `build_transport_ship` so a
    non-current player (the victim) can own one — the build method enforces the
    turn, and the pirate steals from whoever's turn it is not.
    """
    harbor = _place_harbor(game, name)
    edge = _sea_edge_at(game, harbor)
    game.transport_ship_counter += 1
    game.edges[edge].ship = {
        'player': name,
        'built_turn': 0,
        'kind': 'transport',
        'cargo': [],
        'id': game.transport_ship_counter,
    }
    game.get_player(name).ships.append(edge)
    sea_hex = next(
        key for key in game.edges[edge].neighbors['hexes']
        if game.hexes[key].type == 'ocean'
    )
    return edge, sea_hex


class TestPlacingOnASeven:
    def test_a_seven_makes_the_roller_place_the_pirate_ship(self):
        """843: a 7 puts the roller's own pirate on a sea hex, not the robber."""
        game = _game()
        robber_was = game.robber_hex
        game.pending_dice = (3, 4)
        assert game.roll_dice('Alice')['total'] == 7
        assert game.must_move_robber is True

        sea_hex = next(
            key for key, hex_obj in sorted(game.hexes.items()) if hex_obj.type == 'ocean'
        )
        assert game.place_pirate_ship('Alice', sea_hex)['success']
        assert game.ep.pirate_of('Alice') == sea_hex
        assert game.must_move_robber is False
        assert game.robber_hex == robber_was, 'the robber never moved'

    def test_the_pirate_ship_only_sits_on_a_sea_hex(self):
        """934: it sails, so a land hex is refused and nothing is placed."""
        game = _game()
        game.must_move_robber = True
        land_hex = next(
            key for key, hex_obj in sorted(game.hexes.items()) if hex_obj.type != 'ocean'
        )
        assert game.place_pirate_ship('Alice', land_hex)['code'] == 'INVALID_TARGET'
        assert game.ep.pirate_of('Alice') is None

    def test_a_table_without_the_rule_places_no_pirate_ship(self):
        game = _game(pirate=False)
        game.must_move_robber = True
        sea_hex = next(
            key for key, hex_obj in sorted(game.hexes.items()) if hex_obj.type == 'ocean'
        )
        assert game.place_pirate_ship('Alice', sea_hex)['code'] == 'RULE_NOT_IN_PLAY'


class TestStealing:
    def test_a_ship_beside_the_pirate_is_robbed_of_a_card(self):
        """943: the roller steals one card from an adjacent ship's owner."""
        game = _game()
        _edge, sea_hex = _build_ship(game, 'Bob')
        game.must_move_robber = True
        game.get_player('Bob').resources = {'ore': 1}

        result = game.place_pirate_ship('Alice', sea_hex)
        assert result['victims'] == ['Bob']
        assert game.must_choose_victim is True

        assert game.steal_from_victim('Alice', 'Bob')['stolen'] == 'ore'
        assert game.get_player('Alice').resources['ore'] == 1

    def test_an_empty_handed_victim_yields_one_gold_instead(self):
        """943: no cards to take, so 1 gold changes hands instead of a card."""
        game = _game()
        _edge, sea_hex = _build_ship(game, 'Bob')
        game.must_move_robber = True
        bob = game.get_player('Bob')
        bob.resources = {}
        bob.gold = 1
        alice = game.get_player('Alice')
        alice.gold = 0

        assert game.place_pirate_ship('Alice', sea_hex)['victims'] == ['Bob']
        assert game.steal_from_victim('Alice', 'Bob')['stolen'] == 'gold'
        assert alice.gold == 1
        assert bob.gold == 0

    def test_a_sea_hex_with_no_ship_beside_it_robs_nobody(self):
        game = _game()
        _build_ship(game, 'Bob')
        game.must_move_robber = True
        empty_sea = next(
            key for key, hex_obj in sorted(game.hexes.items())
            if hex_obj.type == 'ocean'
            and not any(
                edge.ship for edge in game.edges.values()
                if key in edge.neighbors['hexes']
            )
        )
        assert game.place_pirate_ship('Alice', empty_sea)['victims'] == []
        assert game.must_choose_victim is False


class TestTribute:
    def test_a_ship_crossing_an_opponents_pirate_pays_one_gold(self):
        """949: the mover pays the pirate's owner 1 gold to cross its hex."""
        game = _game()
        edge, _sea_hex = _build_ship(game, 'Alice')

        points = game.ship_movement_points_for('Alice')
        reachable = game._reachable_sea_edges(edge, points)
        destination, pirate_hex = next(
            (dest, key)
            for dest in reachable
            for key in game.edges[dest].neighbors['hexes']
            if game.hexes[key].type == 'ocean'
        )
        game.ep.place_pirate('Bob', pirate_hex)
        game.get_player('Alice').gold = 1
        game.get_player('Bob').gold = 0

        assert game.move_transport_ship('Alice', edge, destination)['success']
        assert game.get_player('Alice').gold == 0
        assert game.get_player('Bob').gold == 1

    def test_no_pirate_no_tribute(self):
        """A table playing transport ships without the pirate pays nothing."""
        game = _game(pirate_ship_instead_of_robber=False, gold=True)
        edge, _sea_hex = _build_ship(game, 'Alice')
        points = game.ship_movement_points_for('Alice')
        destination = next(iter(game._reachable_sea_edges(edge, points)))
        game.get_player('Alice').gold = 1

        assert game.move_transport_ship('Alice', edge, destination)['success']
        assert game.get_player('Alice').gold == 1


class TestRobberUntouchedWhenOff:
    def test_the_base_game_robber_still_moves_and_steals(self):
        game = _game(pirate=False)
        game.must_move_robber = True
        land_hex = next(
            key for key, hex_obj in sorted(game.hexes.items())
            if hex_obj.type not in ('ocean', 'desert') and key != game.robber_hex
        )
        assert game.move_robber('Alice', land_hex)['success']
        assert game.robber_hex == land_hex
        assert game.must_move_robber is False

    def test_a_seven_still_forces_a_discard_with_the_pirate_on(self):
        """842: the discard-half path is unchanged; the pirate touches the board only."""
        game = _game()
        bob = game.get_player('Bob')
        bob.resources = {'wood': 4, 'brick': 4}  # 8 cards, over the limit of 7
        game.pending_dice = (3, 4)
        game.roll_dice('Alice')
        assert game.players_needing_discard.get('Bob') == 4
