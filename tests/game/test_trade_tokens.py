"""Catan for Two: the Trade Token economy.

Source [OFFICIAL]: Traders & Barbarians 2020 rulebook, "Catan for Two", pp. 6-7
(catan-t_b_2020_rule_book_200820.pdf). "At the beginning of the game, each player
receives 5 trade tokens... When you build a settlement adjacent to the desert
hex, take 2 trade tokens... on the coast, you take 1 trade token... adjacent to
both the desert and the coast, you take 3 trade tokens... Once during your turn,
you may discard one of your face-up knight cards and take 2 trade tokens... If
your victory point total is fewer than or equal to your opponent's total, you
must pay 1 trade token to take an action. Otherwise, an action costs you 2."
"""

import random

from game.game import Game


def _two_token_game(seed=1):
    game = Game(["Alice", "Bob"], [], rng=random.Random(seed),
                rules={"trade_tokens": True})
    return game


def _playing(game):
    game.start()
    game.game_phase = "playing"
    game.start_turn()
    # Pin the current seat to Alice so the token-action guards are deterministic
    # whatever order start() seated the two players in.
    game.current_player_index = next(
        i for i, p in enumerate(game.players) if p.name == "Alice"
    )
    return game


def test_each_player_opens_with_five_trade_tokens():
    game = _two_token_game()
    assert [player.trade_tokens for player in game.players] == [5, 5]


def test_default_off_means_no_trade_tokens():
    game = Game(["Alice", "Bob"], [], rng=random.Random(1))
    assert [player.trade_tokens for player in game.players] == [0, 0]


def test_settlement_award_matches_the_boards_desert_and_coast():
    """The token award for every land vertex equals the rulebook classification
    read off the *generated board*: 3 by desert-and-coast, 2 by desert, 1 by
    coast, 0 inland. Asserted against the board, never a copied literal."""
    game = _two_token_game()
    saw = {0: 0, 1: 0, 2: 0, 3: 0}
    for key, vertex in game.vertices.items():
        land = vertex.neighbors["hexes"]
        if not land:
            continue
        desert = any(game.hexes[h].type == "desert" for h in land)
        coast = len(land) < 3
        expected = 3 if (desert and coast) else 2 if desert else 1 if coast else 0
        player = game.get_player("Alice")
        player.trade_tokens = 0
        assert game.grant_settlement_trade_tokens("Alice", key) == expected, key
        saw[expected] += 1
    # A standard board always has inland, coastal and desert-adjacent corners,
    # so the non-trivial branches are actually exercised.
    assert saw[1] and saw[2], f"board did not exercise coast/desert awards: {saw}"


def test_building_a_settlement_by_the_desert_earns_two_tokens_in_setup():
    """End-to-end: the earn fires through the real build path during set-up."""
    game = _two_token_game()
    game.game_state = "started"
    actor = game.current_player_name()
    desert = next(h for h, hx in game.hexes.items() if hx.type == "desert")
    # A desert corner that is inland (three land hexes) earns exactly 2, not 3.
    vertex_key = next(
        key
        for key, vertex in game.vertices.items()
        if desert in vertex.neighbors["hexes"] and len(vertex.neighbors["hexes"]) == 3
    )
    before = game.get_player(actor).trade_tokens
    result = game.place_settlement(actor, vertex_key)
    assert result["success"], result
    assert result["trade_tokens_earned"] == 2
    assert game.get_player(actor).trade_tokens == before + 2


def test_discarding_a_face_up_knight_earns_two_and_is_once_per_turn():
    game = _playing(_two_token_game())
    alice = game.get_player("Alice")
    alice.knights_played = 2
    alice.trade_tokens = 0

    first = game.discard_knight_for_trade_tokens("Alice")
    assert first["success"], first
    assert alice.trade_tokens == 2
    assert alice.knights_played == 1

    second = game.discard_knight_for_trade_tokens("Alice")
    assert not second["success"]
    assert second["code"] == "ALREADY_DISCARDED"
    assert alice.trade_tokens == 2


def test_discarding_with_no_knight_is_refused():
    game = _playing(_two_token_game())
    game.get_player("Alice").knights_played = 0
    result = game.discard_knight_for_trade_tokens("Alice")
    assert not result["success"]
    assert result["code"] == "NO_KNIGHT"


def test_action_costs_one_for_the_trailing_player_and_two_for_the_leader():
    """The asymmetric price is the whole point of the economy."""
    game = _playing(_two_token_game())
    alice = game.get_player("Alice")
    bob = game.get_player("Bob")

    # Level on points: the trailing/level rule charges 1.
    alice.settlements = ["a"]
    bob.settlements = ["b"]
    assert game.trade_token_cost("Alice") == 1

    # Alice pulls ahead: as the leader she now pays 2.
    alice.settlements = ["a", "c"]
    assert game.trade_token_cost("Alice") == 2
    # And Bob, now trailing, pays 1.
    assert game.trade_token_cost("Bob") == 1


def test_move_robber_action_charges_the_leader_two_tokens():
    game = _playing(_two_token_game())
    alice = game.get_player("Alice")
    bob = game.get_player("Bob")
    alice.settlements = ["a", "c"]  # leader
    bob.settlements = ["b"]
    alice.trade_tokens = 5
    # Make sure the robber is not already in the desert, so the move is legal.
    game.robber_hex = next(h for h, hx in game.hexes.items() if hx.type != "desert"
                           and hx.type != "ocean")

    result = game.spend_trade_tokens_move_robber("Alice")
    assert result["success"], result
    desert = next(h for h, hx in game.hexes.items() if hx.type == "desert")
    assert game.robber_hex == desert
    assert alice.trade_tokens == 3  # leader paid 2


def test_forced_trade_draws_two_and_gives_two_and_costs_a_token():
    game = _playing(_two_token_game())
    alice = game.get_player("Alice")
    bob = game.get_player("Bob")
    # Level on points -> costs 1.
    alice.settlements = ["a"]
    bob.settlements = ["b"]
    alice.trade_tokens = 5
    alice.resources = {"wood": 2}
    bob.resources = {"ore": 3}

    result = game.spend_trade_tokens_forced_trade("Alice", {"wood": 2})
    assert result["success"], result
    assert alice.trade_tokens == 4  # paid 1
    # Alice drew 2 ore from Bob and gave 2 wood.
    assert alice.resources.get("ore", 0) == 2
    assert alice.resources.get("wood", 0) == 0
    assert bob.resources.get("wood", 0) == 2
    assert bob.resources.get("ore", 0) == 1
    # Cards are conserved: nothing minted or destroyed.
    assert sum(alice.resources.values()) + sum(bob.resources.values()) == 5


def test_forced_trade_refuses_when_you_cannot_give_two():
    game = _playing(_two_token_game())
    alice = game.get_player("Alice")
    alice.settlements = ["a"]
    game.get_player("Bob").settlements = ["b"]
    alice.trade_tokens = 5
    alice.resources = {"wood": 1}
    result = game.spend_trade_tokens_forced_trade("Alice", {"wood": 2})
    assert not result["success"]
    assert result["code"] == "INSUFFICIENT_RESOURCES"
    # Refused actions change nothing.
    assert alice.trade_tokens == 5


def test_a_token_action_is_refused_when_you_cannot_pay():
    game = _playing(_two_token_game())
    alice = game.get_player("Alice")
    alice.settlements = ["a", "c"]  # leader -> costs 2
    game.get_player("Bob").settlements = ["b"]
    alice.trade_tokens = 1
    game.robber_hex = next(h for h, hx in game.hexes.items() if hx.type not in ("desert", "ocean"))
    result = game.spend_trade_tokens_move_robber("Alice")
    assert not result["success"]
    assert result["code"] == "NOT_ENOUGH_TOKENS"
    assert alice.trade_tokens == 1


def test_win_target_is_ten_for_the_variant():
    """Catan for Two is a 10-point game; the preset must not push the target."""
    from game import rules
    chosen = rules.preset_rules("catan_for_two")
    assert chosen["victory_target"] == 10
    assert chosen["neutral_players"] is True
    assert chosen["trade_tokens"] is True
