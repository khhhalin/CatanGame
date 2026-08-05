"""The board payload carries the prices, so the client needs no copy of them.

What a player would notice if this broke: a build button greyed out against a
price nobody is charging. `panels.js` used to hold its own transcription of
`data/costs.json` — four builds, priced by hand — which no test could catch
drifting, because a test that copied the literal would have passed. Worse, a
house rule that changed a cost moved the engine's number and left the client's
alone, so the button would have said one price while the bank took another.

These tests read the payload the client actually receives.
"""

import random

from game import modifiers as modifiers_module
from game import rules as rules_module
from game.game import Game


def _game(rules=None):
    return Game(['Alice', 'Bob'], [], {}, rng=random.Random(11),
                rules=rules or rules_module.defaults())


def _costs(game):
    return game.get_board_data(viewer='Alice')['costs']


def _cheaper_roads(order=96):
    """A modifier that takes a card off every road, and nothing else."""
    return modifiers_module.Modifier(
        'test_roads_are_cheaper', modifiers_module.COST, order,
        lambda rules: True,
        lambda value, rules, context: (
            {card: max(0, amount - 1) for card, amount in value.items()}
            if context['building_type'] == 'road' else value
        ),
    )


class TestTheClientIsToldWhatThingsCost:
    def test_the_payload_prices_the_base_game_builds(self):
        """The rulebook prices, read off the payload a browser is sent."""
        costs = _costs(_game())
        assert costs['road'] == {'wood': 1, 'brick': 1}
        assert costs['settlement'] == {
            'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1,
        }
        assert costs['city'] == {'wheat': 2, 'ore': 3}
        assert costs['dev_card'] == {'wheat': 1, 'sheep': 1, 'ore': 1}

    def test_every_listed_price_is_sent(self):
        """A build the client can be offered but not priced greys out wrongly."""
        game = _game()
        assert set(_costs(game)) == set(game.building_costs)

    def test_the_payload_is_the_price_the_engine_charges(self):
        game = _game()
        payload = _costs(game)
        assert payload == {
            build_type: game.get_cost(build_type) for build_type in payload
        }


class TestAHouseRuleThatChangesAPriceIsVisible:
    def test_a_cost_modifier_reaches_the_payload(self):
        """Charged and shown have to be the same number."""
        game = _game()
        with modifiers_module.installed(_cheaper_roads()):
            costs = _costs(game)
            assert costs['road'] == {'wood': 0, 'brick': 0}
            # Only what the modifier claimed: the rest of the table is untouched.
            assert costs['city'] == {'wheat': 2, 'ore': 3}


class TestPricesPerLevelStayOutOfIt:
    def test_a_city_improvement_is_not_in_the_flat_table(self):
        """It is priced by level, and a level is not a key in a price list.

        Sending one line per track would mean picking a level for the client,
        and the client would then be reading a price that is only right until
        the track advances.
        """
        costs = _costs(_game(rules_module.preset_rules('cities_and_knights')))
        assert not [key for key in costs if key.startswith('improvement_')]
