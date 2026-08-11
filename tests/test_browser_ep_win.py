"""An Explorers & Pirates game reaches a declared winner, in a real browser.

The victory path nothing had run end to end: a mission delivery that carries a
player over the line, the win check firing, and the game-over banner. Rather than
bot a whole E&P game to a natural win — the generic playthrough bot does not know
how to score missions, and an unseeded finish is a coin toss the CLAUDE notes
forbid as a gate — this drives to a state *one action short* of the target and
plays the winning action through the UI, which exercises the same
claim_victory → game_won → banner path a natural win would.

The setup is deterministic: Alice holds two harbour settlements (4 points) and a
laden ship at the Council dock, level with Bob on the Fish track. Delivering
takes the sole Fish lead — its 1-point card — to exactly the 5 needed. The
player-visible proof is the GAME OVER banner every tab is shown.

Run: pytest tests/test_browser_ep_win.py -m slow -q
"""

import os
import random

import pytest
from browser_harness import (
    _LAYOUT,
    Player,
    _board_point,
    _click_board_point,
    browser_session,
    game_is_over,
    next_frame,
    start_server,
    stop_server,
    wait_for_board_painted,
)
from game import map_store, maps, persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}

# The rules picker's floor for a legal game; two harbours plus one lead card
# reach it exactly, so the delivery is the winning move and nothing before it is.
VICTORY_TARGET = 5


def _win_game():
    document = map_store.read_map('pirate-cove')
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    rules['victory_target'] = VICTORY_TARGET
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    cove = next(key for key, hex_obj in game.hexes.items()
                if hex_obj.meta is not None and hex_obj.meta.docks)
    corners = set(game._hex_corner_vertices(cove))

    # Four points banked already — one short of the win. Set on the player's own
    # points rather than as placed buildings because that is what the save round
    # trips (harbour settlements are not yet serialized), and the number is all
    # this test needs: the delivery must be the move that crosses the line.
    game.get_player('Alice').victory_points = VICTORY_TARGET - 1

    # A laden ship at the dock, and the Fish track tied so the delivery takes the
    # lead card outright — the fifth point.
    deliver_edge = next(
        edge_key for edge_key in sorted(game.edges)
        if game.is_sea_edge(edge_key) and game.edges[edge_key].ship is None
        and any(vertex in corners for vertex in game.edges[edge_key].neighbors['vertices'])
    )
    game.edges[deliver_edge].ship = {
        'player': 'Alice', 'kind': 'transport', 'id': 7, 'built_turn': -1,
        'cargo': [{'type': 'fish_haul', 'size': 'large'}],
    }
    game.ep.markers['Alice']['fish'] = 1
    game.ep.markers['Bob']['fish'] = 1
    game.ep.recompute_lead_cards()
    return game, deliver_edge, cove


def _click_key(player, kind, key):
    board_x, board_y = _board_point(player, kind, key)
    layout = player.page.evaluate(_LAYOUT)
    _click_board_point(player, board_x, board_y, layout)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def test_a_mission_delivery_wins_the_game_and_banners_it(browser, tmp_path):
    game, deliver_edge, cove = _win_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = Player(browser, url, "Alice", viewport=VIEWPORT)
        alice.page.check("#role-player")
        alice.page.fill("#username", "Alice")
        alice.page.click("#join-btn")
        alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        wait_for_board_painted(alice)
        next_frame(alice.page)

        # One point short, and the game still running.
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').victory_points"
        ) == VICTORY_TARGET - 1
        assert not game_is_over(alice), "the game was already over before the winning move"

        # The winning delivery, through the mission gesture.
        alice.page.click("#ep-mission")
        _click_key(alice, 'edge', deliver_edge)
        _click_key(alice, 'hex', cove)

        # The banner every tab is shown is the thing that announces the winner.
        alice.page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#notice-region *'))"
            ".some(n => n.textContent.toUpperCase().includes('GAME OVER'))",
            timeout=8000,
        )
        assert game_is_over(alice), alice.notices()
        assert any("Alice" in notice for notice in alice.notices()), alice.notices()
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
