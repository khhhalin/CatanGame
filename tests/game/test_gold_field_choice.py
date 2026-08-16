"""Seafarers gold fields that pay resources of the player's CHOICE.

Source [OFFICIAL]: base Seafarers rulebook, Section 9 "Gold Fields":
"Whenever the number on a gold field hex is rolled, players collect resources
for each adjacent settlement or city. As normal, each settlement is entitled to
one resource, while each city is entitled to two resources. Players who are
eligible for resources from a gold field hex may select ANY of the five
resources (grain, lumber, ore, brick, or wool). They may choose any mix of these
resources that they desire, up to the limit of 1 for each settlement and 2 for
each city adjacent to the gold-producing hex."

This is a different mechanic from the Explorers & Pirates gold *currency* field
(`test_gold.py`), which pays 2 gold coins per building and no card. The two are
mutually exclusive (`rules.EXCLUSIONS`): a hex pays a currency or a
resource-of-choice, never both.

Each test names a payout a player would notice go wrong: a gold field that opens
no choice, a city owed the settlement's one instead of two, a chosen resource
that never reaches the hand or the bank, a scarcity case that pays past an empty
bank, or the currency field paying a coin under the wrong rule.
"""

import random

from game import rules as rules_module
from game.game import Game
from game.validation import BASE_RESOURCE_TYPES


def _game(**overrides):
    rules = dict(rules_module.defaults())
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _settle_on(game, name, terrain, number, building_type='settlement'):
    """Put a building on a hex forced to this terrain and number.

    Returns the vertex and the hex it now borders, mirroring the gold-currency
    tests: gold fields never fall on a base-game board, so the board is mutated
    rather than searched.
    """
    for vertex in (game.vertices[key] for key in sorted(game.vertices)):
        for hex_key in vertex.neighbors.get('hexes', []):
            hex_obj = game.hexes.get(hex_key)
            if hex_obj and hex_obj.type != 'ocean':
                hex_obj.type = terrain
                hex_obj.number = number
                vertex.building = {'type': building_type, 'player': name}
                return vertex, hex_obj
    raise AssertionError('no land hex adjacent to any vertex')


def _gold_shared_by_two(game, first, second, number=9):
    """One gold hex bordered by a settlement (first) and a city (second).

    Every other hex those two intersections touch is silenced, so a roll of
    `number` pays for the shared gold field alone.
    """
    for hex_key in sorted(game.hexes):
        hex_obj = game.hexes[hex_key]
        if hex_obj.type == 'ocean':
            continue
        verts = [vk for vk in sorted(game.vertices)
                 if hex_key in game.vertices[vk].neighbors.get('hexes', [])]
        if len(verts) < 2:
            continue
        hex_obj.type, hex_obj.number = 'gold', number
        first_vertex, second_vertex = verts[0], verts[1]
        game.vertices[first_vertex].building = {'type': 'settlement', 'player': first}
        game.vertices[second_vertex].building = {'type': 'city', 'player': second}
        for vertex_key in (first_vertex, second_vertex):
            for other in game.vertices[vertex_key].neighbors.get('hexes', []):
                if other != hex_key and game.hexes[other].type != 'ocean':
                    game.hexes[other].number = None
        return hex_obj, first_vertex, second_vertex
    raise AssertionError('no land hex shared by two vertices')


def _choices_for(game, name):
    return [c for c in game.pending_choices
            if c['player'] == name and c['kind'] == 'gold_field_choice']


class TestTheChoiceOpensOnTheRoll:
    def test_a_settlement_opens_one_resource_choice_and_pays_no_card_yet(self):
        game = _game(gold_field_choice=True)
        _settle_on(game, 'Alice', 'gold', 9)
        game.distribute_resources(9)

        owed = _choices_for(game, 'Alice')
        assert len(owed) == 1
        assert owed[0]['options'] == list(BASE_RESOURCE_TYPES)
        # Nothing paid until the player answers.
        assert game.get_player('Alice').resources == {}

    def test_a_city_is_owed_two_choices(self):
        """The rulebook's one per settlement, two per city."""
        game = _game(gold_field_choice=True)
        _settle_on(game, 'Alice', 'gold', 9, building_type='city')
        game.distribute_resources(9)

        assert len(_choices_for(game, 'Alice')) == 2

    def test_no_choice_without_the_rule(self):
        game = _game(gold_field_choice=False)
        _settle_on(game, 'Alice', 'gold', 9)
        game.distribute_resources(9)

        assert _choices_for(game, 'Alice') == []

    def test_a_robber_on_the_field_opens_no_choice(self):
        """A robber on a gold field blocks it exactly as it blocks a resource
        hex — no card, and here no choice either."""
        game = _game(gold_field_choice=True)
        _, hex_obj = _settle_on(game, 'Alice', 'gold', 9)
        game.robber_hex = hex_obj.key
        game.distribute_resources(9)

        assert _choices_for(game, 'Alice') == []


class TestAnsweringPaysTheChosenResource:
    def test_resolving_takes_the_chosen_card_from_the_bank(self):
        game = _game(gold_field_choice=True)
        _settle_on(game, 'Alice', 'gold', 9)
        game.distribute_resources(9)
        ore_before = game.bank.resources['ore']

        result = game.resolve_choice('Alice', 'gold_field_choice', 'ore')

        assert result['success']
        assert game.get_player('Alice').resources == {'ore': 1}
        assert game.bank.resources['ore'] == ore_before - 1
        assert _choices_for(game, 'Alice') == []

    def test_a_city_may_pick_two_different_resources(self):
        """"Any mix" — a city takes one wheat and one ore if it wants."""
        game = _game(gold_field_choice=True)
        _settle_on(game, 'Alice', 'gold', 9, building_type='city')
        game.distribute_resources(9)

        game.resolve_choice('Alice', 'gold_field_choice', 'wheat')
        game.resolve_choice('Alice', 'gold_field_choice', 'ore')

        assert game.get_player('Alice').resources == {'wheat': 1, 'ore': 1}


class TestEveryAdjacentOwnerChoosesForThemselves:
    def test_both_owners_are_owed_their_own_choices(self):
        game = _game(gold_field_choice=True)
        _gold_shared_by_two(game, 'Alice', 'Bob', number=9)
        game.distribute_resources(9)

        assert len(_choices_for(game, 'Alice')) == 1   # settlement
        assert len(_choices_for(game, 'Bob')) == 2      # city

        game.resolve_choice('Alice', 'gold_field_choice', 'wood')
        game.resolve_choice('Bob', 'gold_field_choice', 'brick')
        game.resolve_choice('Bob', 'gold_field_choice', 'brick')

        assert game.get_player('Alice').resources == {'wood': 1}
        assert game.get_player('Bob').resources == {'brick': 2}


class TestBankScarcity:
    def test_a_pick_the_bank_cannot_cover_pays_nothing(self):
        """Bank limit, as normal production respects it: a city owed two picks
        of a resource with a single card left banks one, not two."""
        game = _game(gold_field_choice=True)
        _settle_on(game, 'Alice', 'gold', 9, building_type='city')
        for resource in BASE_RESOURCE_TYPES:
            game.bank.resources[resource] = 0
        game.bank.resources['ore'] = 1
        game.distribute_resources(9)

        owed = _choices_for(game, 'Alice')
        # Only the resource still in stock is offered.
        assert all(choice['options'] == ['ore'] for choice in owed)

        game.resolve_choice('Alice', 'gold_field_choice', 'ore')
        game.resolve_choice('Alice', 'gold_field_choice', 'ore')

        assert game.get_player('Alice').resources == {'ore': 1}
        assert game.bank.resources['ore'] == 0

    def test_a_dry_bank_opens_no_choice(self):
        game = _game(gold_field_choice=True)
        _settle_on(game, 'Alice', 'gold', 9)
        for resource in BASE_RESOURCE_TYPES:
            game.bank.resources[resource] = 0
        game.distribute_resources(9)

        assert _choices_for(game, 'Alice') == []
        assert game.get_player('Alice').resources == {}


class TestTheCurrencyFieldIsUntouched:
    def test_the_ep_gold_currency_field_still_pays_coins_and_opens_no_choice(self):
        """The Explorers & Pirates gold field is the other rule and is unaffected:
        2 gold coins per building, no card, no resource choice."""
        game = _game(gold=True)
        vertex, _ = _settle_on(game, 'Alice', 'gold', 9)
        # A wood hex on the same roll keeps Alice off the empty-roll bonus, so
        # the 2 gold asserted below is the field's coins alone.
        for other in vertex.neighbors.get('hexes', []):
            hex_obj = game.hexes.get(other)
            if hex_obj and hex_obj.type not in ('ocean', 'gold'):
                hex_obj.type, hex_obj.number = 'wood', 9
                break
        game.distribute_resources(9)

        assert game.get_player('Alice').gold == 2
        assert game.get_player('Alice').resources.get('wood') == 1
        assert _choices_for(game, 'Alice') == []

    def test_the_two_gold_rules_cannot_both_be_on(self):
        chosen = dict(rules_module.defaults())
        chosen.update(gold=True, gold_field_choice=True)
        problems = rules_module.exclusion_problems(chosen)
        assert any('gold' in problem.lower() for problem in problems)
