"""Every price is listed once, and an unlisted one is an error.

`costs.json` carried a line per development card type — `two_roads` at
brick/wheat/wood, `monopoly` at wheat/brick/ore — none of which any code read,
because `buy_dev_card` charged the `knight` line for all five. Every card costs
the same in the rulebook, so the extra lines were both wrong and dead: exactly
the sort of literal that gets wired up years later and ships the wrong price.

An unlisted build type used to price at nothing, which meant a typo bought the
piece for free.
"""

import random

import pytest
from game import rules as rules_module
from game.game import Game


def _game():
    game = Game(['Alice', 'Bob'], [], {}, rules=rules_module.defaults(),
                rng=random.Random(6))
    game.start()
    game.game_phase = 'playing'
    game.set_dice_rolled()
    return game


class TestADevelopmentCardHasOnePrice:
    def test_it_is_the_rulebook_price(self):
        """Ore, wool and grain — the same for every card in the deck."""
        assert _game().get_cost('dev_card') == {'ore': 1, 'sheep': 1, 'wheat': 1}

    def test_no_per_card_prices_survive(self):
        """A price per card type is a lie the rulebook does not tell."""
        game = _game()
        for card_type in ('two_roads', 'invention', 'monopoly', 'victory_point'):
            with pytest.raises(KeyError):
                game.get_cost(card_type)

    def test_buying_charges_exactly_that(self):
        game = _game()
        player = game.get_player('Alice')
        player.resources = {'ore': 1, 'sheep': 1, 'wheat': 1}

        assert game.buy_dev_card('Alice')['success']
        assert sum(player.resources.values()) == 0, "a card cost more or less than its price"


class TestAnUnlistedPriceIsRefused:
    def test_a_typo_does_not_buy_something_free(self):
        """It used to return {}, and an empty cost is affordable to anyone."""
        game = _game()
        with pytest.raises(KeyError):
            game.get_cost('setlement')

    def test_every_listed_type_still_prices(self):
        """Driven from the file, so a new line cannot be silently unreachable."""
        game = _game()
        for build_type in game.building_costs:
            assert game.get_cost(build_type), f"{build_type} priced at nothing"
