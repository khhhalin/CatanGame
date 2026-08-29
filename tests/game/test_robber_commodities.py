"""The robber steals commodities too, not only resources.

Reported bug: with Cities & Knights commodities on, the robber (and the progress
cards that steal "in the same way") could never take cloth/coin/paper — the
steal pool was built from `victim.resources` alone, while commodities live in a
separate `victim.commodities` dict. A victim holding only commodities was immune.
The rulebook is explicit: "Commodities may be stolen by the robber and by
progress cards in the same way as resources." (expansions.md:328)

Run: pytest tests/game/test_robber_commodities.py -q
"""

import random

from conftest import ScriptedRandom
from game import rules as rules_module
from game.game import Game


def ck_game(players=("Alice", "Bob"), seed=12345, rng=None, **overrides):
    chosen = dict(rules_module.preset_rules("cities_and_knights"))
    chosen["turn_order"] = "lobby"
    chosen.update(overrides)
    game = Game(list(players), [], rng=rng or random.Random(seed), rules=chosen)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.start_turn()
    return game


def test_the_robber_can_steal_a_commodity():
    game = ck_game(rng=ScriptedRandom())
    assert game.rules["commodities"], "preset should have commodities on"
    victim = game.get_player("Bob")
    victim.resources = {}                 # only commodities in hand
    victim.commodities = {"cloth": 2}
    thief = game.get_player("Alice")
    thief.commodities = {}

    stolen = game.steal_resource("Bob", "Alice")

    assert stolen == "cloth", stolen
    assert victim.commodities["cloth"] == 1
    assert thief.commodities.get("cloth", 0) == 1


def test_commodities_are_not_stealable_without_the_rule():
    """With commodities off there are none to hold, and the steal pool must not
    reach into the commodities dict — a victim with only (stray) commodities and
    no resources yields nothing."""
    game = ck_game(rng=ScriptedRandom(), commodities=False)
    victim = game.get_player("Bob")
    victim.resources = {}
    victim.commodities = {"cloth": 2}
    stolen = game.steal_resource("Bob", "Alice")
    assert stolen is None
