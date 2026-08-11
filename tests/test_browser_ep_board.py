"""The Explorers & Pirates board renders — it does not crash or come up blank.

The renderer meets four hex types it never had before — `hidden` (a face-down
undiscovered tile), `gold`, `fish` and `spice`. A type it has no colour or draw
path for would throw mid-render or paint nothing, and a blank canvas satisfies
every DOM assertion — so this waits for the board to actually paint (>1000
pixels) and checks the console stayed clean, with a full-explore map whose
mainland starts entirely face-down.

Run: pytest tests/test_browser_ep_board.py -m slow -q
"""

import os
import random

import pytest
from browser_harness import (
    Player,
    browser_session,
    next_frame,
    start_server,
    stop_server,
    wait_for_board_painted,
)
from game import board as board_module
from game import maps, persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}
SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "ep",
)


def _ep_game():
    mainland = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(2))
    sea = len(maps.frame_hex_keys(4)) - len(mainland)
    document = {
        'map_version': 2, 'id': 'ep-shot', 'name': 'EP Shot',
        'frame': {'radius': 4},
        'regions': [
            {'id': 'mainland', 'kind': 'main', 'hexes': mainland,
             'pool': {'mode': 'hidden',
                      'terrain': {'fish': 2, 'gold': 1, 'spice': 1, 'wood': 4,
                                  'wheat': 4, 'sheep': 4, 'ore': 2, 'brick': 1},
                      'numbers': [2, 3, 4, 5, 6, 8, 9, 10, 11, 3, 4, 5, 6, 8, 9, 10]}},
            {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
             'pool': {'mode': 'shuffled', 'terrain': {'sea': sea}, 'numbers': []}},
        ],
        'harbours': {'mode': 'bag', 'types': {}},
    }
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish', 'mission_spices', 'mission_pirate_lairs'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def test_the_ep_board_paints_its_new_hex_types(browser, tmp_path):
    game = _ep_game()
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
        os.makedirs(SHOT_DIR, exist_ok=True)
        alice.page.screenshot(path=os.path.join(SHOT_DIR, "ep-01-hidden-tiles.png"))
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
