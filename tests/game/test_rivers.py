"""The Rivers of Catan (Traders & Barbarians, expansions.md 527-570).

Decomposed into individual switches like every other expansion: the shared
`gold_coins` currency, `river_gold`, `bridges`, and the two scoring tiles
`wealthiest_settler` / `poor_settler`. These tests pin the catalogue coherence,
the coin economy (buy/sell/immunity), the river coin grants, bridge building and
the Longest-Road counting, and the two victory-point tiles.

Everything is asserted against the live engine — a game is dealt, a coin is
earned or spent, a tile moves — never against a copied literal.
"""

import random

import pytest

from game import rules as rules_module
from game.game import Game


def make_game(rules=None, players=("Alice", "Bob")):
    return Game(list(players), [], rng=random.Random(4242), rules=rules)


def rivers_rules(**overrides):
    """The Rivers preset, coerced, with any overrides applied."""
    chosen = dict(rules_module.TB_RIVERS_RULES)
    # No board_map so tests deal the default board; they set river hexes and
    # bridge sites directly rather than lean on a dealt map.
    chosen.pop("board_map", None)
    chosen.update(overrides)
    return rules_module.coerce(chosen)


class TestCatalogue:
    def test_the_five_rivers_rules_are_off_in_the_base_game(self):
        chosen = rules_module.defaults()
        for rule_id in ("gold_coins", "river_gold", "bridges",
                        "wealthiest_settler", "poor_settler"):
            assert chosen[rule_id] is False, rule_id

    def test_max_bridges_defaults_to_three(self):
        assert rules_module.defaults()["max_bridges"] == 3

    def test_the_river_rules_need_the_coin_currency(self):
        problems = rules_module.dependency_problems({
            "river_gold": True,
            "wealthiest_settler": True,
            "poor_settler": True,
        })
        assert len(problems) == 3
        assert all("Gold coins" in p for p in problems)

    def test_bridges_stand_alone_without_the_coin_currency(self):
        # Bridges depend on the river map's crossing sites, not on gold_coins:
        # a table could build them for the Longest Road with no coin economy.
        assert rules_module.dependency_problems({"bridges": True}) == []

    def test_gold_coins_excludes_ep_gold(self):
        problems = rules_module.exclusion_problems({"gold": True, "gold_coins": True})
        assert len(problems) == 1

    def test_gold_coins_alone_is_fine(self):
        assert rules_module.exclusion_problems({"gold_coins": True}) == []
        assert rules_module.exclusion_problems({"gold": True}) == []

    def test_the_rivers_preset_is_coherent(self):
        chosen = rules_module.preset_rules("tb_rivers")
        assert rules_module.dependency_problems(chosen) == []
        assert rules_module.exclusion_problems(chosen) == []

    def test_the_rivers_preset_ticks_its_rules_and_suggests_ten(self):
        chosen = rules_module.preset_rules("tb_rivers")
        for rule_id in ("gold_coins", "river_gold", "bridges",
                        "wealthiest_settler", "poor_settler"):
            assert chosen[rule_id] is True, rule_id
        assert chosen["victory_target"] == 10
        assert chosen["board_map"] == "rivers"

    def test_a_rivers_game_builds_no_fish_container(self):
        # Rivers needs no TB fish state: coins live on the player and bridge
        # sites on the board, so `tb` stays None exactly as in a base game.
        assert make_game(rules=rivers_rules()).tb is None
