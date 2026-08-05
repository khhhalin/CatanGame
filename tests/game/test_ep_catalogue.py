"""Explorers & Pirates catalogue (Wave 0).

These pin the rule catalogue the way the rest of the registry is pinned: a
preset materialises the exact set of switches a table would get by clicking it,
an incomplete set is refused by name, the two ship models exclude each other,
and the state container is built exactly when a rule needs it.

The mechanics themselves land in later waves; nothing here drives a ship or a
mission, because none of that engine code exists yet. What a player would notice
if one of these broke: a scenario button that ticks the wrong rules, or a game
that silently plays half of one.
"""

import random

from game import modifiers as modifiers_module
from game import rules as rules_module
from game.game import Game


def make_game(rules=None, players=("Alice", "Bob")):
    return Game(list(players), [], rng=random.Random(4242), rules=rules)


def expansion_ticks(chosen: dict) -> set:
    """The EXPANSION-group bools a coerced rule set switches on."""
    return {
        rule_id
        for rule_id, value in chosen.items()
        if value is True
        and rules_module.RULES_BY_ID[rule_id]["group"] == rules_module.EXPANSION
        and rules_module.RULES_BY_ID[rule_id]["type"] == rules_module.BOOL
    }


class TestCatalogue:
    def test_the_seventeen_reuses_are_not_reinvented(self):
        """The plan reuses max_ships, bank_trade_rate, the two award cards and
        victory_target rather than adding E&P copies of them."""
        for reused in ("max_ships", "bank_trade_rate", "longest_road_card",
                       "largest_army_card", "victory_target"):
            assert reused in rules_module.RULES_BY_ID
        # No second ships-count rule was added alongside the reuse.
        assert "max_transport_ships" not in rules_module.RULES_BY_ID

    def test_every_ep_int_default_leaves_the_base_game_unchanged(self):
        chosen = rules_module.defaults()
        assert chosen["max_harbor_settlements"] == 4
        assert chosen["max_settlers"] == 2
        assert chosen["max_crews"] == 9
        assert chosen["ship_movement_points"] == 4
        assert chosen["starting_gold"] == 0

    def test_every_ep_bool_is_off_in_the_base_game(self):
        chosen = rules_module.defaults()
        for rule_id in ("movement_phase", "gold", "no_dev_cards",
                        "no_city_upgrades", "transport_ships",
                        "harbor_settlements", "ships_explore", "cargo_settlers",
                        "crews", "transshipping", "pirate_ship_instead_of_robber",
                        "chase_pirate", "missions", "mission_pirate_lairs",
                        "mission_fish", "mission_spices"):
            assert chosen[rule_id] is False, rule_id


class TestPresets:
    def test_land_ho_ticks_exactly_the_intro_mechanics(self):
        chosen = rules_module.preset_rules("ep_land_ho")
        assert expansion_ticks(chosen) == {
            "harbor_settlements", "transport_ships", "ships_explore",
            "cargo_settlers", "movement_phase", "gold", "no_dev_cards",
            "no_city_upgrades",
        }
        assert chosen["victory_target"] == 8
        assert chosen["longest_road_card"] is False
        assert chosen["largest_army_card"] is False
        assert chosen["bank_trade_rate"] == 3
        assert chosen["max_ships"] == 3
        assert chosen["starting_gold"] == 2

    def test_pirate_lairs_adds_the_pirate_and_its_mission(self):
        chosen = rules_module.preset_rules("ep_pirate_lairs")
        assert expansion_ticks(chosen) >= {
            "crews", "transshipping", "pirate_ship_instead_of_robber",
            "chase_pirate", "missions", "mission_pirate_lairs",
        }
        assert chosen["mission_fish"] is False
        assert chosen["mission_spices"] is False
        assert chosen["victory_target"] == 12

    def test_fish_is_pirate_lairs_plus_the_fish_mission(self):
        chosen = rules_module.preset_rules("ep_fish")
        assert chosen["mission_fish"] is True
        assert chosen["mission_pirate_lairs"] is True
        assert chosen["mission_spices"] is False
        assert chosen["victory_target"] == 15

    def test_spices_removes_the_lairs_mission(self):
        """1071: the Pirate Lairs hexes and mission are taken out for Spices."""
        chosen = rules_module.preset_rules("ep_spices")
        assert chosen["mission_pirate_lairs"] is False
        assert chosen["mission_fish"] is True
        assert chosen["mission_spices"] is True
        assert chosen["victory_target"] == 15

    def test_the_full_game_runs_all_three_missions_to_seventeen(self):
        chosen = rules_module.preset_rules("explorers_and_pirates")
        assert chosen["mission_pirate_lairs"] is True
        assert chosen["mission_fish"] is True
        assert chosen["mission_spices"] is True
        assert chosen["victory_target"] == 17

    def test_no_ep_preset_ships_an_incomplete_set(self):
        for preset_id in ("ep_land_ho", "ep_pirate_lairs", "ep_fish",
                          "ep_spices", "explorers_and_pirates"):
            chosen = rules_module.preset_rules(preset_id)
            assert rules_module.dependency_problems(chosen) == [], preset_id
            assert rules_module.exclusion_problems(chosen) == [], preset_id


class TestDependencies:
    def test_transport_ships_needs_a_harbor_to_build_from(self):
        chosen = rules_module.coerce({"transport_ships": True})
        problems = rules_module.dependency_problems(chosen)
        assert any("Transport ships" in p and "Harbor settlements" in p
                   for p in problems), problems

    def test_the_pirate_needs_gold_for_its_tribute(self):
        chosen = rules_module.coerce({"pirate_ship_instead_of_robber": True})
        problems = rules_module.dependency_problems(chosen)
        assert any("Pirate ship" in p and "Gold" in p for p in problems), problems

    def test_a_mission_without_its_container_is_refused(self):
        chosen = rules_module.coerce({"mission_fish": True})
        problems = rules_module.dependency_problems(chosen)
        assert any("Fish" in p and "Missions" in p for p in problems), problems


class TestSeaShipModelExclusion:
    """Risk 1: Seafarers ships and E&P transport ships are one physical piece
    read two opposite ways, so a table may not have both on."""

    def test_transport_and_seafarers_ships_both_on_is_refused(self):
        problems = rules_module.exclusion_problems(
            rules_module.coerce({"transport_ships": True, "ships": True,
                                 "harbor_settlements": True})
        )
        assert any("Transport ships" in p for p in problems), problems

    def test_transport_ships_alone_is_fine(self):
        assert rules_module.exclusion_problems(
            rules_module.coerce({"transport_ships": True,
                                 "harbor_settlements": True})
        ) == []

    def test_the_group_is_live_and_excludes_transport_from_ships(self):
        """The pair (transport_ships, ships) is enough: ship_movement and the
        Longest Trade Route both depend on ships, so no coherent set reaches
        them without it — and listing all four would refuse Seafarers itself."""
        group = next(g for g in rules_module.EXCLUSIONS
                     if g["id"] == "sea_ship_model")
        assert set(group["rules"]) == {"transport_ships", "ships"}

    def test_transport_with_the_moving_ships_rider_is_still_refused(self):
        """ship_movement cannot be on without ships, so a table reaching for it
        alongside transport ships is caught — by the ships exclusion once ships
        is present, or by the ship_movement dependency if it is not."""
        chosen = rules_module.coerce({"transport_ships": True,
                                      "harbor_settlements": True,
                                      "ship_movement": True, "ships": True})
        assert rules_module.exclusion_problems(chosen) != []


class TestEpStateContainer:
    def test_a_base_game_builds_no_container(self):
        assert make_game().ep is None

    def test_needs_ep_state_flips_on_exactly_the_state_rules(self):
        for rule_id in rules_module.EP_STATE_RULES:
            assert rules_module.needs_ep_state(
                rules_module.coerce({rule_id: True})
            ), rule_id

    def test_the_transport_system_alone_needs_no_container(self):
        """Ships, harbors and cargo hang state on the players and the board, so
        a game with only those on stays containerless."""
        chosen = rules_module.coerce({
            "harbor_settlements": True, "transport_ships": True,
            "cargo_settlers": True, "gold": True,
        })
        assert rules_module.needs_ep_state(chosen) is False

    def test_a_scenario_with_missions_gets_a_registered_container(self):
        game = make_game(rules_module.preset_rules("explorers_and_pirates"))
        assert game.ep is not None
        for name in ("Alice", "Bob"):
            assert game.ep.pirate_of(name) is None
            assert game.ep.marker(name, "fish") == 0

    def test_the_container_round_trips_its_accessors(self):
        game = make_game(rules_module.preset_rules("ep_pirate_lairs"))
        ep = game.ep
        ep.place_pirate("Alice", "hex_3_4")
        ep.advance_marker("Alice", "pirate_lairs", 2)
        ep.recompute_lead_cards()
        ep.take_token("Alice", "lair_token")
        ep.grant_advantage("Alice", "swift_voyage")
        ep.seed_hidden_tiles(["t1", "t2", "t3"])
        ep.reveal("t2", "Alice")

        data = ep.to_dict("Alice")
        assert data["pirate_hex"]["Alice"] == "hex_3_4"
        assert data["markers"]["Alice"]["pirate_lairs"] == 2
        assert data["lead_cards"]["pirate_lairs"] == "Alice"
        assert data["tokens_held"]["Alice"]["lair_token"] == 1
        assert data["village_advantages"]["Alice"] == ["swift_voyage"]
        assert data["reveal_order"] == ["t2"]
        # The pool's remaining tiles are counted, never named.
        assert data["hidden_count"] == 2
        assert "t1" not in data and "hidden_tiles" not in data

    def test_land_ho_needs_the_container_for_its_hidden_tiles(self):
        """Land Ho! has no missions but does explore, and the undiscovered pool
        lives on the container — so it is built even here."""
        assert make_game(rules_module.preset_rules("ep_land_ho")).ep is not None

    def test_start_turn_clears_the_fresh_discovery_flag(self):
        game = make_game(rules_module.preset_rules("ep_pirate_lairs"))
        game.ep.reveal("t9", "Alice")
        assert game.ep.last_discovery == "t9"
        game.ep.start_turn()
        assert game.ep.last_discovery is None


class TestReservedModifierSlots:
    """The catalogue commit reserves the two E&P production-modifier orders so
    the feature agents do not race for a number; `register` refuses a clash. A
    slot stays free until the wave that reads its rule lands and claims it."""

    def test_harbor_settlement_yield_stays_free_until_its_wave(self):
        taken = {m.order for m in modifiers_module.registered(modifiers_module.PRODUCTION)}
        assert modifiers_module._EP_RESERVED_PRODUCTION_ORDERS["harbor_settlement_yield"] \
            not in taken

    def test_gold_field_claims_its_reserved_order(self):
        """The gold wave has landed, so `gold_field` now sits at its slot."""
        by_id = {m.rule_id: m for m in modifiers_module.registered(modifiers_module.PRODUCTION)}
        assert by_id["gold_field"].order == \
            modifiers_module._EP_RESERVED_PRODUCTION_ORDERS["gold_field"]
