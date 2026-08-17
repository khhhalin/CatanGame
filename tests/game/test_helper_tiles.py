"""CATAN - The Helpers: the tile framework and the reference advantage.

The framework is the container the whole scenario hangs off - the display the
tiles are drawn from, the one tile each player holds, and the exchange-or-flip
step that follows every use (Helpers_Rules.pdf pp. 2-4). These tests pin the
catalogue coherence, the deal, the sun->moon->exchange lifecycle, the once-a-turn
and not-the-turn-you-received-it prohibitions, and the one advantage wired in
this chunk (Kaja, Take Robber's Resource) end to end against real state a player
would see - a card gained, the display one tile lighter.

Everything is asserted against the live engine: a game is dealt, a tile is
activated, a resource lands in a hand - never against a copied literal.
"""

import random

from game import helper_tiles, tiles
from game import rules as rules_module
from game.game import Game


def make_game(rules=None, players=("Alice", "Bob")):
    return Game(list(players), [], rng=random.Random(4242), rules=rules)


def helpers_rules(**overrides):
    chosen = dict(rules_module.PRESETS_BY_ID["helpers_of_catan"]["rules"])
    chosen.update(overrides)
    return rules_module.coerce(chosen)


def playing_game(players=("Alice", "Bob"), **overrides):
    """A Helpers game rolled into play with each seat holding its first tile."""
    game = make_game(rules=helpers_rules(**overrides), players=players)
    game.game_phase = "playing"
    game.grant_starting_helpers()
    game.has_rolled_dice = True
    return game


def _held_ids(game):
    return {held["tile"] for held in game.helper_held.values()}


def _hex_producing(game, resource):
    for key, hex_obj in game.hexes.items():
        if tiles.produces(hex_obj.type) == resource:
            return key
    raise AssertionError(f"no {resource} hex on the dealt board")


def _desert_hex(game):
    for key, hex_obj in game.hexes.items():
        if hex_obj.type == "desert":
            return key
    raise AssertionError("no desert on the dealt board")


class TestCatalogue:
    def test_the_preset_ticks_the_framework_and_all_twelve_advantages(self):
        chosen = rules_module.preset_rules("helpers_of_catan")
        assert chosen["helper_tiles"] is True
        for rule_id in helper_tiles.HELPER_ABILITY_RULES:
            assert chosen[rule_id] is True

    def test_an_advantage_without_the_framework_is_refused(self):
        problems = rules_module.dependency_problems(
            helpers_rules(helper_tiles=False)
        )
        blob = " ".join(problems)
        assert "Helper: Take Robber's Resource (Kaja)" in blob
        assert "Helper tiles" in blob

    def test_no_tile_touches_the_victory_target(self):
        assert playing_game().victory_points_to_win == 10


class TestDealAndDisplay:
    def test_the_display_and_hands_together_are_exactly_the_enabled_tiles(self):
        game = playing_game()
        in_play = set(helper_tiles.tiles_in_play(game.rules))
        assert len(in_play) == 12
        assert set(game.helper_pile) | _held_ids(game) == in_play
        # No tile is both held and in the display.
        assert not (set(game.helper_pile) & _held_ids(game))

    def test_a_table_that_ticks_fewer_advantages_plays_with_fewer_tiles(self):
        game = playing_game(helper_forced_trade=False, helper_dev_card_swap=False)
        in_play = set(game.helper_pile) | _held_ids(game)
        assert "asla" not in in_play
        assert "carla" not in in_play
        assert len(in_play) == 10

    def test_each_player_is_dealt_one_helper_sun_side_up(self):
        game = playing_game()
        for player in game.players:
            held = game.helper_held[player.name]
            assert held["side"] == "sun"
            assert held["tile"] in helper_tiles.HELPER_TILES_BY_ID

    def test_a_seeded_deal_is_reproducible(self):
        first = playing_game().helper_held["Alice"]["tile"]
        second = playing_game().helper_held["Alice"]["tile"]
        assert first == second


class TestLifecycle:
    def _give_kaja_on_ore(self, game, player="Alice"):
        """Put Kaja in the player's hand with the robber on a mountain hex."""
        game.helper_held[player] = {"tile": "kaja", "side": "sun", "received_turn": None}
        game.robber_hex = _hex_producing(game, "ore")

    def test_a_sun_tile_may_be_flipped_and_a_moon_tile_only_exchanged(self):
        game = playing_game()
        self._give_kaja_on_ore(game)

        activated = game.activate_helper("Alice", "kaja", {})
        assert activated["success"], activated
        choice = game.pending_choice_for("Alice")
        assert choice["options"] == ["exchange", "flip"]

        game.resolve_choice("Alice", "helper_resolution", "flip")
        assert game.helper_held["Alice"]["side"] == "moon"
        assert game.helper_held["Alice"]["tile"] == "kaja"

        # A fresh turn, and the moon-side tile may be used once more.
        game.helper_used_this_turn.clear()
        game.turn_count += 1
        again = game.activate_helper("Alice", "kaja", {})
        assert again["success"], again
        moon_choice = game.pending_choice_for("Alice")
        assert moon_choice["options"] == ["exchange"]

    def test_exchange_returns_the_used_tile_and_draws_a_new_one(self):
        game = playing_game()
        self._give_kaja_on_ore(game)
        pile_before = len(game.helper_pile)

        game.activate_helper("Alice", "kaja", {})
        game.resolve_choice("Alice", "helper_resolution", "exchange")

        new_held = game.helper_held["Alice"]
        assert new_held["tile"] != "kaja"
        assert new_held["side"] == "sun"
        assert "kaja" in game.helper_pile
        # The display keeps its size: one tile out, one tile in.
        assert len(game.helper_pile) == pile_before

    def test_a_helper_cannot_be_used_twice_in_one_turn(self):
        game = playing_game()
        self._give_kaja_on_ore(game)
        game.activate_helper("Alice", "kaja", {})
        game.resolve_choice("Alice", "helper_resolution", "flip")

        second = game.activate_helper("Alice", "kaja", {})
        assert not second["success"]
        assert second["code"] == "HELPER_ALREADY_USED"

    def test_you_cannot_play_a_helper_the_turn_you_received_it(self):
        game = playing_game()
        game.robber_hex = _hex_producing(game, "ore")
        # A tile taken this very turn: received_turn matches the live counter.
        game.helper_held["Alice"] = {
            "tile": "kaja", "side": "sun", "received_turn": game.turn_count,
        }
        refused = game.activate_helper("Alice", "kaja", {})
        assert not refused["success"]
        assert refused["code"] == "HELPER_TOO_SOON"

    def test_a_helper_is_refused_on_another_players_turn(self):
        game = playing_game()
        game.robber_hex = _hex_producing(game, "ore")
        game.helper_held["Bob"] = {"tile": "kaja", "side": "sun", "received_turn": None}
        refused = game.activate_helper("Bob", "kaja", {})
        assert not refused["success"]
        assert refused["code"] == "NOT_YOUR_TURN"


class TestKaja:
    def test_kaja_takes_the_resource_of_the_hex_the_robber_sits_on(self):
        game = playing_game()
        game.helper_held["Alice"] = {"tile": "kaja", "side": "sun", "received_turn": None}
        game.robber_hex = _hex_producing(game, "ore")
        bank_before = game.bank.resources["ore"]

        result = game.activate_helper("Alice", "kaja", {})
        assert result["success"], result
        assert result["taken"] == "ore"
        assert game.get_player("Alice").resources.get("ore", 0) == 1
        assert game.bank.resources["ore"] == bank_before - 1

    def test_kaja_on_the_desert_needs_a_choice_and_honours_it(self):
        game = playing_game()
        game.helper_held["Alice"] = {"tile": "kaja", "side": "sun", "received_turn": None}
        game.robber_hex = _desert_hex(game)

        needs = game.activate_helper("Alice", "kaja", {})
        assert not needs["success"]
        assert needs["code"] == "NEEDS_RESOURCE"

        chosen = game.activate_helper("Alice", "kaja", {"resource": "sheep"})
        assert chosen["success"], chosen
        assert game.get_player("Alice").resources.get("sheep", 0) == 1


def _hold(game, player, tile):
    game.helper_held[player] = {"tile": tile, "side": "sun", "received_turn": None}


class TestDigur:
    def test_digur_chases_the_robber_to_the_desert_and_pays_the_hex_it_left(self):
        game = playing_game()
        _hold(game, "Alice", "digur")
        game.robber_hex = _hex_producing(game, "wheat")
        bank_before = game.bank.resources["wheat"]

        result = game.activate_helper("Alice", "digur", {})
        assert result["success"], result
        assert game.hexes[game.robber_hex].type == "desert"
        assert result["taken"] == "wheat"
        assert game.get_player("Alice").resources.get("wheat", 0) == 1
        assert game.bank.resources["wheat"] == bank_before - 1

    def test_digur_is_refused_when_the_robber_is_already_in_the_desert(self):
        game = playing_game()
        _hold(game, "Alice", "digur")
        game.robber_hex = _desert_hex(game)
        refused = game.activate_helper("Alice", "digur", {})
        assert not refused["success"]
        assert refused["code"] == "ROBBER_IN_DESERT"


class TestHilda:
    def test_hilda_pays_an_empty_roll(self):
        game = playing_game()
        _hold(game, "Bob", "hilda")  # off-turn: any player's roll
        game.last_roll_total = 8
        game.last_roll_gains = {"Alice": {"wood": 1}}  # Bob got nothing

        result = game.activate_helper("Bob", "hilda", {"resource": "ore"})
        assert result["success"], result
        assert game.get_player("Bob").resources.get("ore", 0) == 1

    def test_hilda_is_refused_when_you_did_receive_resources(self):
        game = playing_game()
        _hold(game, "Bob", "hilda")
        game.last_roll_total = 8
        game.last_roll_gains = {"Bob": {"wood": 1}}
        refused = game.activate_helper("Bob", "hilda", {"resource": "ore"})
        assert not refused["success"]
        assert refused["code"] == "HELPER_NO_NEED"

    def test_hilda_will_not_fire_on_a_seven(self):
        game = playing_game()
        _hold(game, "Bob", "hilda")
        game.last_roll_total = 7
        game.last_roll_gains = {}
        refused = game.activate_helper("Bob", "hilda", {"resource": "ore"})
        assert not refused["success"]
        assert refused["code"] == "HELPER_WRONG_TIME"


class TestThorolf:
    def test_thorolf_waives_the_discard_for_an_over_full_hand(self):
        game = playing_game()
        _hold(game, "Bob", "thorolf")
        game.get_player("Bob").resources = {"wood": 5, "brick": 5}  # 10 cards
        game.last_roll_total = 7
        game.players_needing_discard = {"Bob": 5}

        result = game.activate_helper("Bob", "thorolf", {})
        assert result["success"], result
        assert "Bob" not in game.players_needing_discard
        # Not a card is discarded: the whole hand is kept.
        assert game.get_player("Bob").total_resources() == 10

    def test_thorolf_pays_a_small_hand_a_resource(self):
        game = playing_game()
        _hold(game, "Bob", "thorolf")
        game.get_player("Bob").resources = {"wood": 2}
        game.last_roll_total = 7
        game.players_needing_discard = {}

        result = game.activate_helper("Bob", "thorolf", {"resource": "sheep"})
        assert result["success"], result
        assert game.get_player("Bob").resources.get("sheep", 0) == 1

    def test_thorolf_only_fires_on_a_seven(self):
        game = playing_game()
        _hold(game, "Bob", "thorolf")
        game.last_roll_total = 8
        refused = game.activate_helper("Bob", "thorolf", {"resource": "sheep"})
        assert not refused["success"]
        assert refused["code"] == "HELPER_WRONG_TIME"


class TestRyan:
    def _leader_bob(self, game):
        """Give Bob more victory points than Alice via extra settlements."""
        game.get_player("Bob").settlements = ["v1", "v2", "v3"]
        game.get_player("Alice").settlements = ["v9"]

    def test_ryan_takes_a_chosen_card_from_a_richer_opponent(self):
        game = playing_game()
        _hold(game, "Alice", "ryan")
        self._leader_bob(game)
        game.get_player("Bob").resources = {"ore": 2}
        game.last_roll_total = 6  # Alice's roll is resolved

        result = game.activate_helper("Alice", "ryan", {"target": "Bob", "resource": "ore"})
        assert result["success"], result
        assert game.get_player("Alice").resources.get("ore", 0) == 1
        assert game.get_player("Bob").resources.get("ore", 0) == 1

    def test_ryan_refuses_a_target_who_is_not_ahead(self):
        game = playing_game()
        _hold(game, "Alice", "ryan")
        game.get_player("Alice").settlements = ["v1", "v2"]
        game.get_player("Bob").settlements = ["v9"]
        game.get_player("Bob").resources = {"ore": 2}
        game.last_roll_total = 6
        refused = game.activate_helper("Alice", "ryan", {"target": "Bob", "resource": "ore"})
        assert not refused["success"]
        assert refused["code"] == "NOT_A_LEADER"


class TestAsla:
    def test_asla_takes_a_resource_and_returns_one_of_your_choice(self):
        game = playing_game()
        _hold(game, "Alice", "asla")
        game.get_player("Alice").resources = {"wheat": 1}
        game.get_player("Bob").resources = {"ore": 2}

        result = game.activate_helper(
            "Alice", "asla",
            {"resource": "ore", "targets": ["Bob"], "returns": ["wheat"]},
        )
        assert result["success"], result
        assert game.get_player("Alice").resources.get("ore", 0) == 1
        assert game.get_player("Alice").resources.get("wheat", 0) == 0
        assert game.get_player("Bob").resources.get("ore", 0) == 1
        assert game.get_player("Bob").resources.get("wheat", 0) == 1

    def test_asla_requests_from_two_players_in_turn(self):
        game = playing_game(players=("Alice", "Bob", "Cara"))
        _hold(game, "Alice", "asla")
        game.get_player("Alice").resources = {"wheat": 2}
        game.get_player("Bob").resources = {"ore": 1}
        game.get_player("Cara").resources = {"ore": 1}

        result = game.activate_helper(
            "Alice", "asla",
            {"resource": "ore", "targets": ["Bob", "Cara"], "returns": ["wheat", "wheat"]},
        )
        assert result["success"], result
        assert game.get_player("Alice").resources.get("ore", 0) == 2

    def test_asla_refuses_when_you_cannot_pay_the_return(self):
        game = playing_game()
        _hold(game, "Alice", "asla")
        game.get_player("Alice").resources = {}  # nothing to give back
        game.get_player("Bob").resources = {"ore": 1}
        refused = game.activate_helper(
            "Alice", "asla",
            {"resource": "ore", "targets": ["Bob"], "returns": ["wheat"]},
        )
        assert not refused["success"]
        assert refused["code"] == "CANNOT_RETURN"


class TestStina:
    def test_stina_trades_a_resource_two_for_one_several_times(self):
        game = playing_game()
        _hold(game, "Alice", "stina")
        game.get_player("Alice").resources = {"wood": 4}
        brick_bank = game.bank.resources["brick"]
        ore_bank = game.bank.resources["ore"]

        result = game.activate_helper(
            "Alice", "stina",
            {"resource_out": "wood", "resources": ["brick", "ore"]},
        )
        assert result["success"], result
        alice = game.get_player("Alice")
        assert alice.resources.get("wood", 0) == 0
        assert alice.resources.get("brick", 0) == 1
        assert alice.resources.get("ore", 0) == 1
        # The received cards came out of the bank's own piles.
        assert game.bank.resources["brick"] == brick_bank - 1
        assert game.bank.resources["ore"] == ore_bank - 1

    def test_stina_refuses_without_enough_of_the_traded_resource(self):
        game = playing_game()
        _hold(game, "Alice", "stina")
        game.get_player("Alice").resources = {"wood": 3}  # only enough for one 2:1
        refused = game.activate_helper(
            "Alice", "stina",
            {"resource_out": "wood", "resources": ["brick", "ore"]},
        )
        assert not refused["success"]
        assert refused["code"] == "CANNOT_AFFORD"


class TestDiara:
    def test_diara_buys_with_substitution_then_keeps_one_of_three(self):
        game = playing_game()
        _hold(game, "Alice", "diara")
        # No wheat: substitute it with brick to pay brick + sheep + ore.
        game.get_player("Alice").resources = {"brick": 1, "sheep": 1, "ore": 1}

        opened = game.activate_helper(
            "Alice", "diara",
            {"substitute_from": "wheat", "substitute_with": "brick"},
        )
        assert opened["success"], opened
        assert game.get_player("Alice").resources.get("brick", 0) == 0

        keep = game.pending_choice_for("Alice")
        assert keep["kind"] == "helper_keep_dev"
        assert len(keep["options"]) == 3

        before = game.get_player("Alice").total_dev_cards()
        game.resolve_choice("Alice", "helper_keep_dev", keep["options"][0])
        assert game.get_player("Alice").total_dev_cards() == before + 1
        # The exchange-or-flip step follows the keep.
        assert game.pending_choice_for("Alice")["kind"] == "helper_resolution"

    def test_diara_refuses_when_you_cannot_pay(self):
        game = playing_game()
        _hold(game, "Alice", "diara")
        game.get_player("Alice").resources = {}
        refused = game.activate_helper("Alice", "diara", {})
        assert not refused["success"]
        assert refused["code"] == "CANNOT_AFFORD"


class TestCarla:
    def test_carla_swaps_an_unplayed_card_for_a_fresh_draw(self):
        game = playing_game()
        _hold(game, "Alice", "carla")
        alice = game.get_player("Alice")
        alice.dev_cards["knight"]["count"] = 1
        alice.dev_cards["knight"]["purchase_turn"] = 0

        result = game.activate_helper("Alice", "carla", {"dev_card": "knight"})
        assert result["success"], result
        # One card in, one card out: the hand size holds.
        assert alice.total_dev_cards() == 1
        # The drawn card cannot be played this turn.
        drawn_type = result["drawn"]
        assert alice.dev_cards[drawn_type]["purchase_turn"] == game.turn_count

    def test_carla_refuses_a_card_you_do_not_hold(self):
        game = playing_game()
        _hold(game, "Alice", "carla")
        refused = game.activate_helper("Alice", "carla", {"dev_card": "monopoly"})
        assert not refused["success"]
        assert refused["code"] == "NOT_HELD"


def _edges_at(game, vertex):
    return [key for key in sorted(game.edges)
            if vertex in game.edges[key].neighbors["vertices"]]


def _far_vertex(game, edge, near):
    return next(v for v in game.edges[edge].neighbors["vertices"] if v != near)


class TestYngvi:
    def test_yngvi_builds_a_road_paying_a_substitute_for_brick(self):
        game = playing_game()
        _hold(game, "Alice", "yngvi")
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        alice = game.get_player("Alice")
        alice.settlements.append(home)
        edge = _edges_at(game, home)[0]
        # No brick: pay a sheep instead. Wood is still owed normally.
        alice.resources = {"wood": 1, "sheep": 1}

        result = game.activate_helper(
            "Alice", "yngvi", {"edge": edge, "drop": "brick", "resource": "sheep"},
        )
        assert result["success"], result
        assert game.edges[edge].road == {"player": "Alice"}
        assert alice.resources.get("wood", 0) == 0
        assert alice.resources.get("sheep", 0) == 0
        assert alice.resources.get("brick", 0) == 0

    def test_yngvi_without_an_edge_opens_a_board_choice_of_legal_sides(self):
        # A player who names no edge is picking on the board: the engine offers
        # the legal road sides as a pending choice, and its answer lays the road.
        game = playing_game()
        _hold(game, "Alice", "yngvi")
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        alice = game.get_player("Alice")
        alice.settlements.append(home)
        alice.resources = {"wood": 1, "sheep": 1}

        opened = game.activate_helper("Alice", "yngvi", {"drop": "brick", "resource": "sheep"})
        assert opened["success"], opened
        choice = game.pending_choice_for("Alice")
        assert choice["kind"] == "helper_makeshift_road"
        edge = _edges_at(game, home)[0]
        assert edge in choice["options"]
        # No side is offered that already carries a road or floats out at sea.
        for offered in choice["options"]:
            assert game.edges[offered].road is None
            assert game.land_hexes_of_edge(offered)

        game.resolve_choice("Alice", "helper_makeshift_road", edge)
        assert game.edges[edge].road == {"player": "Alice"}
        assert alice.resources.get("wood", 0) == 0
        assert alice.resources.get("sheep", 0) == 0
        assert game.pending_choice_for("Alice")["kind"] == "helper_resolution"

    def test_yngvi_refuses_without_the_substitute_in_hand(self):
        game = playing_game()
        _hold(game, "Alice", "yngvi")
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        game.get_player("Alice").settlements.append(home)
        game.get_player("Alice").resources = {"wood": 1}  # no sheep to pay
        edge = _edges_at(game, home)[0]
        refused = game.activate_helper(
            "Alice", "yngvi", {"edge": edge, "drop": "brick", "resource": "sheep"},
        )
        assert not refused["success"]
        assert refused["code"] == "CANNOT_AFFORD"


class TestHogni:
    def test_hogni_moves_an_end_road_to_another_spot(self):
        game = playing_game()
        _hold(game, "Alice", "hogni")
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        alice = game.get_player("Alice")
        alice.settlements.append(home)
        edges = _edges_at(game, home)
        from_edge, to_edge = edges[0], edges[1]
        game.edges[from_edge].road = {"player": "Alice"}
        alice.roads.append(from_edge)

        result = game.activate_helper(
            "Alice", "hogni", {"from_edge": from_edge, "to_edge": to_edge},
        )
        assert result["success"], result
        assert game.edges[from_edge].road is None
        assert game.edges[to_edge].road == {"player": "Alice"}
        assert from_edge not in alice.roads
        assert to_edge in alice.roads

    def test_hogni_without_edges_lifts_then_lays_by_two_board_taps(self):
        # With no edges named the move is two board taps: a first choice of the
        # player's end roads, then a second of where the lifted road may go.
        game = playing_game()
        _hold(game, "Alice", "hogni")
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        alice = game.get_player("Alice")
        alice.settlements.append(home)
        edges = _edges_at(game, home)
        from_edge, to_edge = edges[0], edges[1]
        game.edges[from_edge].road = {"player": "Alice"}
        alice.roads.append(from_edge)

        opened = game.activate_helper("Alice", "hogni", {})
        assert opened["success"], opened
        first = game.pending_choice_for("Alice")
        assert first["kind"] == "helper_move_road_from"
        assert from_edge in first["options"]

        game.resolve_choice("Alice", "helper_move_road_from", from_edge)
        assert game.edges[from_edge].road is None
        second = game.pending_choice_for("Alice")
        assert second["kind"] == "helper_move_road_to"
        assert to_edge in second["options"]

        game.resolve_choice("Alice", "helper_move_road_to", to_edge)
        assert game.edges[to_edge].road == {"player": "Alice"}
        assert to_edge in alice.roads
        assert from_edge not in alice.roads
        assert game.pending_choice_for("Alice")["kind"] == "helper_resolution"

    def test_hogni_refuses_a_road_that_is_not_an_end(self):
        game = playing_game()
        _hold(game, "Alice", "hogni")
        home = next(iter(sorted(game.vertices)))
        alice = game.get_player("Alice")
        edges = _edges_at(game, home)
        from_edge = edges[0]
        middle = _far_vertex(game, from_edge, home)
        # Both ends carry an Alice building, so neither end is free.
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        game.vertices[middle].building = {"type": "settlement", "player": "Alice"}
        alice.settlements.extend([home, middle])
        game.edges[from_edge].road = {"player": "Alice"}
        alice.roads.append(from_edge)
        other = _edges_at(game, home)[1]

        refused = game.activate_helper(
            "Alice", "hogni", {"from_edge": from_edge, "to_edge": other},
        )
        assert not refused["success"]
        assert refused["code"] == "NOT_END_ROAD"


class TestGregor:
    def test_gregor_discards_a_knight_to_build_a_city_cheaply(self):
        game = playing_game()
        _hold(game, "Alice", "gregor")
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        alice = game.get_player("Alice")
        alice.settlements.append(home)
        alice.knights_played = 3
        game.largest_army_holder = "Alice"
        # Gregor's city is 2 ore + 1 wheat, not the usual 3 ore + 2 wheat.
        alice.resources = {"ore": 2, "wheat": 1}

        result = game.activate_helper("Alice", "gregor", {"build": "city", "vertex": home})
        assert result["success"], result
        assert game.vertices[home].building["type"] == "city"
        assert alice.resources.get("ore", 0) == 0
        assert alice.resources.get("wheat", 0) == 0
        # The discarded knight no longer counts toward the Largest Army.
        assert alice.knights_played == 2

    def test_gregor_without_a_vertex_opens_a_board_choice_of_build_spots(self):
        # A player who names no intersection is picking on the board: the engine
        # offers the legal build spots (their settlements, for a city) and its
        # answer raises the building at Gregor's reduced price.
        game = playing_game()
        _hold(game, "Alice", "gregor")
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        alice = game.get_player("Alice")
        alice.settlements.append(home)
        alice.knights_played = 3
        game.largest_army_holder = "Alice"
        alice.resources = {"ore": 2, "wheat": 1}

        opened = game.activate_helper("Alice", "gregor", {"build": "city"})
        assert opened["success"], opened
        choice = game.pending_choice_for("Alice")
        assert choice["kind"] == "helper_knight_to_building"
        assert home in choice["options"]

        game.resolve_choice("Alice", "helper_knight_to_building", home)
        assert game.vertices[home].building["type"] == "city"
        assert alice.resources.get("ore", 0) == 0
        assert alice.resources.get("wheat", 0) == 0
        assert alice.knights_played == 2
        assert game.pending_choice_for("Alice")["kind"] == "helper_resolution"

    def test_gregor_refuses_without_a_played_knight(self):
        game = playing_game()
        _hold(game, "Alice", "gregor")
        home = next(iter(sorted(game.vertices)))
        game.vertices[home].building = {"type": "settlement", "player": "Alice"}
        game.get_player("Alice").settlements.append(home)
        game.get_player("Alice").knights_played = 0
        game.get_player("Alice").resources = {"ore": 2, "wheat": 1}
        refused = game.activate_helper("Alice", "gregor", {"build": "city", "vertex": home})
        assert not refused["success"]
        assert refused["code"] == "NO_KNIGHT"


class TestPersistence:
    def test_the_display_and_hands_survive_a_save(self):
        from game import persistence

        game = playing_game()
        game.helper_held["Alice"]["side"] = "moon"
        saved = persistence.serialize(game)
        restored = persistence.deserialize(saved)
        assert restored.helper_pile == game.helper_pile
        assert restored.helper_held == game.helper_held
