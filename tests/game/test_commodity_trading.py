"""Bug: a player holding commodities could not trade them at all.

`expansions.md` line 329 — "Commodities may be traded with other players and
with the bank in all the same ways that resources may be traded" — and line 330
gives the bank rate: "four identical commodities for one card of choice, or at
three-for-one using a generic 3:1 harbor". Line 331 is the one asymmetry:
"Commodities may never be traded at a 2:1 resource-specific harbor, because
those harbors only accept their own resource."

The engine validated a trade payload with `clean_resource_counts`, which knows
only the five resources, and then read `player.resources` alone, so three paper
could not be offered to anyone.
"""

import random

import pytest
from game import rules as rules_module
from game.game import Game


@pytest.fixture
def ck_table():
    """A C&K game past setup, with Alice on turn and holding commodities."""
    game = Game(['Alice', 'Bob'], [], rng=random.Random(7),
                rules=rules_module.preset_rules('cities_and_knights'))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = next(
        index for index, player in enumerate(game.players) if player.name == 'Alice'
    )
    game.get_player('Alice').commodities = {'paper': 4, 'cloth': 1}
    game.get_player('Bob').resources = {'wood': 3}
    return game


def give_harbour(game, player_name, port):
    """Seat the player on an intersection carrying `port`."""
    for vertex_key in sorted(game.vertices):
        vertex = game.vertices[vertex_key]
        if vertex.port and vertex.port['type'] == port['type']:
            if port['type'] == 'resource' and vertex.port['resource'] != port['resource']:
                continue
            game.get_player(player_name).settlements = [vertex_key]
            return vertex.port
    raise AssertionError(f"no {port} harbour on this board")


class TestPlayerToPlayer:
    def test_a_commodity_can_be_offered_to_the_table(self, ck_table):
        """Line 329. Before the fix this was INSUFFICIENT_RESOURCES: the check
        read `player.resources`, where no paper ever lives."""
        result = ck_table.propose_trade('Alice', {'paper': 1}, {'wood': 1})
        assert result['success'], result.get('error')
        assert result['kind'] == 'offer'

    def test_offering_a_commodity_nobody_holds_is_refused(self, ck_table):
        result = ck_table.propose_trade('Alice', {'coin': 1}, {'wood': 1})
        assert not result['success']
        assert result['code'] == 'INSUFFICIENT_RESOURCES'

    def test_a_completed_commodity_trade_moves_the_cards(self, ck_table):
        offer = ck_table.propose_trade('Alice', {'paper': 1}, {'wood': 1})['offer']
        assert ck_table.accept_trade(offer['id'], 'Bob')['success']
        assert ck_table.complete_trade(offer['id'], 'Alice', 'Bob')['success']

        alice, bob = ck_table.get_player('Alice'), ck_table.get_player('Bob')
        assert alice.commodities['paper'] == 3
        assert alice.resources['wood'] == 1
        assert bob.commodities['paper'] == 1
        assert bob.resources['wood'] == 2

    def test_a_responder_without_the_commodity_cannot_accept(self, ck_table):
        offer = ck_table.propose_trade('Alice', {'cloth': 1}, {'paper': 1})['offer']
        result = ck_table.accept_trade(offer['id'], 'Bob')
        assert not result['success']
        assert result['code'] == 'INSUFFICIENT_RESOURCES'


class TestTheBankRate:
    def test_four_identical_commodities_buy_one_card(self, ck_table):
        """Line 330's 4:1."""
        result = ck_table.propose_trade('Alice', {'paper': 4}, {'wood': 1})
        assert result['kind'] == 'bank'
        assert result['rate_used'] == 4
        assert ck_table.get_player('Alice').commodities['paper'] == 0
        assert ck_table.get_player('Alice').resources['wood'] == 1

    def test_a_generic_harbour_takes_three(self, ck_table):
        """Line 330's 3:1 on a generic harbour."""
        give_harbour(ck_table, 'Alice', {'type': 'generic'})
        assert ck_table.best_trade_rate('Alice', {'paper': 3}) == 3
        result = ck_table.propose_trade('Alice', {'paper': 3}, {'wood': 1})
        assert result['kind'] == 'bank'
        assert result['rate_used'] == 3

    def test_a_resource_harbour_never_takes_a_commodity(self, ck_table):
        """Line 331. The 2:1 harbour accepts its own resource and nothing else,
        so a paper offer stays at the table rate."""
        port = give_harbour(ck_table, 'Alice', {'type': 'resource', 'resource': 'wood'})
        assert ck_table.best_trade_rate('Alice', {port['resource']: 2}) == 2
        assert ck_table.best_trade_rate('Alice', {'paper': 2}) == 4
        # And a mixed offer must not launder commodities through the harbour.
        assert ck_table.best_trade_rate('Alice', {port['resource']: 2, 'paper': 2}) == 4

    def test_the_bank_pays_out_a_commodity(self, ck_table):
        """"one card of choice" — the wanted side may be a commodity too."""
        ck_table.get_player('Alice').resources = {'wood': 4}
        # Out of the bank first, or the four coming back hit the supply cap and
        # the assertion would pin nothing.
        ck_table.bank.take('wood', 4)
        wood_before = ck_table.bank.resources['wood']

        result = ck_table.propose_trade('Alice', {'wood': 4}, {'cloth': 1})
        assert result['kind'] == 'bank'
        assert ck_table.get_player('Alice').commodities['cloth'] == 2
        assert ck_table.bank.resources['wood'] == wood_before + 4

    def test_a_commodity_the_player_gave_up_does_not_join_the_resource_bank(self, ck_table):
        """The bank tracks the five resources only; a spent commodity leaves
        play, exactly as a discarded one does."""
        before = dict(ck_table.bank.resources)
        ck_table.propose_trade('Alice', {'paper': 4}, {'wood': 1})
        assert set(ck_table.bank.resources) == set(before)
        assert ck_table.bank.resources['wood'] == before['wood'] - 1


class TestResourceRatesAreUnchanged:
    def test_the_four_to_one_fallback_still_applies(self, ck_table):
        ck_table.get_player('Alice').resources = {'ore': 4}
        assert ck_table.best_trade_rate('Alice', {'ore': 4}) == 4
        assert ck_table.propose_trade('Alice', {'ore': 4}, {'wheat': 1})['kind'] == 'bank'
