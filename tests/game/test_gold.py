"""Gold, the Explorers & Pirates second currency (expansions.md 854, 960-998).

Each test names a payout or a limit a player would notice go wrong: an empty
roll that pays no gold when it should, a gold field that pays the wrong amount,
a conversion that a player could repeat past its cap, or a 7 that made someone
discard gold it never should have counted.
"""

import random

from game import rules as rules_module
from game.game import Game


def _game(**overrides):
    rules = dict(rules_module.defaults())
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _settle_on(game, name, terrain, number):
    """Put a settlement on a hex forced to this terrain and number.

    Returns the vertex and the hex it now borders. The board is mutated rather
    than searched for a matching hex because gold fields never appear on a
    base-game board and a shuffled one rarely lands the number where the walk
    finds it.
    """
    for vertex in (game.vertices[key] for key in sorted(game.vertices)):
        for hex_key in vertex.neighbors.get('hexes', []):
            hex_obj = game.hexes.get(hex_key)
            if hex_obj and hex_obj.type != 'ocean':
                hex_obj.type = terrain
                hex_obj.number = number
                vertex.building = {'type': 'settlement', 'player': name}
                return vertex, hex_obj
    raise AssertionError('no land hex adjacent to any vertex')


def _vertex_on_two_land(game, name):
    """A settlement bordering two mutable land hexes, and those two hexes."""
    for vertex in (game.vertices[key] for key in sorted(game.vertices)):
        land = [
            game.hexes[key]
            for key in vertex.neighbors.get('hexes', [])
            if key in game.hexes and game.hexes[key].type != 'ocean'
        ]
        if len(land) >= 2:
            vertex.building = {'type': 'settlement', 'player': name}
            return vertex, land[0], land[1]
    raise AssertionError('no vertex borders two land hexes')


class TestTheEmptyRollBonus:
    def test_a_dry_non_seven_roll_pays_one_gold_under_the_rule(self):
        """854: a non-7 roll that pays you no resources hands you 1 gold."""
        game = _game(gold=True)
        _settle_on(game, 'Alice', 'wood', 8)
        # Nobody borders a 5, so 5 pays no resources to anybody.
        game.distribute_resources(5)
        assert game.get_player('Alice').gold == 1
        assert game.get_player('Bob').gold == 1

    def test_no_gold_without_the_rule(self):
        game = _game(gold=False)
        _settle_on(game, 'Alice', 'wood', 8)
        game.distribute_resources(5)
        assert game.get_player('Alice').gold == 0

    def test_a_paid_player_gets_no_bonus(self):
        """The bonus compensates a dry roll, not every roll."""
        game = _game(gold=True)
        _, hex_obj = _settle_on(game, 'Alice', 'wood', 8)
        game.distribute_resources(8)
        assert game.get_player('Alice').gold == 0
        assert game.get_player('Alice').resources.get('wood') == 1
        # Bob bordered nothing, so his roll was dry.
        assert game.get_player('Bob').gold == 1

    def test_a_seven_pays_no_bonus(self):
        game = _game(gold=True)
        _settle_on(game, 'Alice', 'wood', 8)
        game.distribute_resources(7)
        assert game.get_player('Alice').gold == 0


class TestGoldFields:
    def test_a_gold_field_produces_two_gold_per_building(self):
        """998: the production modifier pays 2 gold per building, no resource."""
        game = _game(gold=True)
        vertex, hex_obj = _settle_on(game, 'Alice', 'gold', 9)
        produced = game.production_for(vertex, hex_obj, 9, robber_here=False)
        assert produced == {'resources': 0, 'commodity': None, 'gold': 2}

    def test_the_field_credits_gold_on_its_number(self):
        """A settlement bordering a gold field banks 2 gold when it rolls."""
        game = _game(gold=True)
        vertex, gold_hex, other = _vertex_on_two_land(game, 'Alice')
        gold_hex.type, gold_hex.number = 'gold', 9
        # A resource on the same roll keeps Alice off the empty-roll bonus, so
        # the 2 gold asserted below is the field's alone.
        other.type, other.number = 'wood', 9
        game.distribute_resources(9)
        assert game.get_player('Alice').gold == 2
        assert game.get_player('Alice').resources.get('wood') == 1

    def test_a_gold_field_pays_nothing_without_the_rule(self):
        game = _game(gold=False)
        vertex, hex_obj = _settle_on(game, 'Alice', 'gold', 9)
        game.distribute_resources(9)
        assert game.get_player('Alice').gold == 0


class TestSupplyConversions:
    def test_three_of_a_kind_buys_one_gold(self):
        game = _game(gold=True)
        alice = game.get_player('Alice')
        alice.resources['wood'] = 3
        result = game.sell_resources_for_gold('Alice', 'wood')
        assert result['success']
        assert alice.gold == 1
        assert alice.resources['wood'] == 0

    def test_the_sale_is_capped_per_turn(self):
        """Nine wood could buy three gold, but the cap stops it at two."""
        game = _game(gold=True)
        alice = game.get_player('Alice')
        alice.resources['wood'] = 9
        assert game.sell_resources_for_gold('Alice', 'wood')['success']
        assert game.sell_resources_for_gold('Alice', 'wood')['success']
        third = game.sell_resources_for_gold('Alice', 'wood')
        assert third['code'] == 'GOLD_LIMIT'
        assert alice.gold == 2
        assert alice.resources['wood'] == 3  # the untouched third trade's worth

    def test_two_gold_buys_one_resource(self):
        game = _game(gold=True)
        alice = game.get_player('Alice')
        alice.gold = 2
        result = game.buy_resource_with_gold('Alice', 'ore')
        assert result['success']
        assert alice.gold == 0
        assert alice.resources.get('ore') == 1

    def test_the_buy_is_capped_at_twice_a_turn(self):
        game = _game(gold=True)
        alice = game.get_player('Alice')
        alice.gold = 10
        assert game.buy_resource_with_gold('Alice', 'ore')['success']
        assert game.buy_resource_with_gold('Alice', 'ore')['success']
        third = game.buy_resource_with_gold('Alice', 'ore')
        assert third['code'] == 'GOLD_LIMIT'
        assert alice.gold == 6
        assert alice.resources.get('ore') == 2

    def test_the_cap_resets_with_the_turn(self):
        game = _game(gold=True)
        alice = game.get_player('Alice')
        alice.gold = 10
        game.buy_resource_with_gold('Alice', 'ore')
        game.buy_resource_with_gold('Alice', 'ore')
        game.start_turn()
        assert game.buy_resource_with_gold('Alice', 'ore')['success']


class TestGoldIsNotACard:
    def test_gold_does_not_count_toward_the_seven_discard(self):
        """842: a 7 discards half your resource cards; gold is never one of them.

        Eight resources force a discard of four; five gold would push a card
        count to thirteen and a discard of six if it were wrongly counted.
        """
        game = _game(gold=True)
        alice = game.get_player('Alice')
        alice.resources['wood'] = 8
        alice.gold = 5
        game.check_discard_required()
        assert game.players_needing_discard['Alice'] == 4
        assert alice.gold == 5
