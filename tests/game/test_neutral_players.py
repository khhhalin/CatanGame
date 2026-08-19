"""Catan for Two: the two non-producing neutral colours.

Source [OFFICIAL]: Traders & Barbarians 2020 rulebook, "Catan for Two", pp. 6-7
(catan-t_b_2020_rule_book_200820.pdf). "Place the two sets of game pieces not
chosen by the players beside the game board. They will serve as game components
for the two imaginary neutral players... For each neutral player, place 1
settlement (without a road)... The neutral players do not receive resources...
When you build a road or a settlement, you must also build (for free) 1 road or
1 settlement for either of the two neutral players. If there is no legal
settlement location for the neutral players, you must build a road instead."
"""

import random

from game.game import Game


def _two_player_neutral_game():
    game = Game(["Alice", "Bob"], [], rng=random.Random(7),
                rules={"neutral_players": True})
    return game


def test_two_neutral_colours_each_open_with_one_settlement():
    """Rulebook Set-Up: two neutral players, each with exactly one opening
    settlement and no road."""
    game = _two_player_neutral_game()
    assert len(game.neutral_players) == 2
    for neutral in game.neutral_players:
        assert len(neutral.settlements) == 1
        assert len(neutral.roads) == 0
    # Their colours are distinct from each other and from the two real seats.
    colours = {p.color for p in game.players} | {n.color for n in game.neutral_players}
    assert len(colours) == 4


def test_a_neutral_settlement_stands_on_a_real_board_vertex_and_blocks():
    """Board test: each opening settlement sits on a real land vertex, is
    recorded on the vertex, and honours the distance rule against its twin.
    Asserted against the generated board, never a copied literal."""
    game = _two_player_neutral_game()
    seats = [s for neutral in game.neutral_players for s in neutral.settlements]
    assert len(seats) == 2
    for vertex_key in seats:
        vertex = game.vertices[vertex_key]
        assert vertex.building is not None
        assert vertex.building["type"] == "settlement"
        # A settlement stands on land: the vertex touches at least one land hex.
        assert vertex.neighbors["hexes"]
    # The two neutral settlements are not adjacent (the distance rule held).
    first, second = seats
    assert second not in game.vertices[first].neighbors["vertices"]


def test_neutral_settlements_produce_no_resources_on_a_roll():
    """Rulebook: 'The neutral players do not receive resources.' A neutral
    colour's settlement pays nothing when its number is rolled — the failure a
    player would notice is a neutral hoarding cards it can never spend."""
    game = _two_player_neutral_game()
    game.start()
    game.game_phase = "playing"

    neutral = game.neutral_players[0]
    vertex = game.vertices[neutral.settlements[0]]
    numbers = [
        game.hexes[hex_key].number
        for hex_key in vertex.neighbors["hexes"]
        if game.hexes[hex_key].number is not None
    ]
    assert numbers, "the neutral's settlement must touch at least one numbered hex"

    for number in numbers:
        gained = game.distribute_resources(number)
        assert neutral.name not in gained
    assert neutral.resources == {}


def test_a_real_build_forces_a_free_neutral_piece():
    """Rulebook 'Building Progress of the Neutral Players': building a road or a
    settlement in play forces one free neutral piece onto the board. Early on,
    with a neutral holding a lone settlement and no road, that piece is a road."""
    game = _two_player_neutral_game()
    game.start()
    game.game_phase = "playing"

    before = sum(len(n.settlements) + len(n.roads) for n in game.neutral_players)
    placed = game.expand_neutral_players("Alice")
    after = sum(len(n.settlements) + len(n.roads) for n in game.neutral_players)

    assert placed is not None
    assert after == before + 1
    # The very first expansion cannot be a settlement — a neutral has no road to
    # connect one to yet — so the rulebook's "build a road instead" applies.
    assert placed["piece"] == "road"
    # The road it placed is recorded on the board and blocks that side.
    assert game.edges[placed["key"]].road["player"] == placed["neutral"]


def test_neutrals_never_take_a_turn():
    """A neutral colour occupies the board but is not a seat: it is never in the
    turn rotation, so advancing turns only ever lands on a real player."""
    game = _two_player_neutral_game()
    game.start()
    real_names = {p.name for p in game.players}
    assert real_names == {"Alice", "Bob"}
    for _ in range(6):
        game.current_player_index = (game.current_player_index + 1) % len(game.players)
        assert game.players[game.current_player_index].name in real_names


def test_neutrals_default_off():
    """Off unless the table ticks the rule: a plain game has no neutral colours."""
    game = Game(["Alice", "Bob"], [], rng=random.Random(7))
    assert game.neutral_players == []
