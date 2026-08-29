"""The Fishermen of Catan panel, in a real browser.

The new client code is fish.js and its strip: the panel shows the player's own
fish tokens (private) and the spend ladder, and a benefit button fires the
matching handler. The regression it guards against is the panel never appearing,
the hand rendering blank, or a spend button emitting nothing — invisible to the
unit suite, which only sees the handler once it is called. The player-visible
proof is a fish token in the hand and a free road appearing after a spend.

A base game must show no fish panel at all.

Run: pytest tests/test_browser_fishermen.py -m slow -q
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
from game import map_store, maps, persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}


def _fishermen_game():
    """A started Fishermen game, Alice mid-turn holding a 2- and a 3-fish token
    (enough for the 5-fish free road) and no free roads yet, so the spend is an
    isolated change."""
    chosen = dict(rules_module.TB_FISHERMEN_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('fishermen'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    game.tb.hands['Alice'] = [2, 3]
    game.free_roads_remaining = 0
    return game


def _boot_game():
    """A started Fishermen game, Alice mid-turn holding the old boot, with Bob on
    as many victory points as her — so Bob is an eligible taker and the pass is
    allowed (a sole leader would have to keep it)."""
    chosen = dict(rules_module.TB_FISHERMEN_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('fishermen'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    game.tb.old_boot_holder = 'Alice'
    game.get_player('Alice').victory_points = 3
    game.get_player('Bob').victory_points = 3
    return game


def _base_game():
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def _join(browser, url):
    alice = Player(browser, url, "Alice", viewport=VIEWPORT)
    alice.page.check("#role-player")
    alice.page.fill("#username", "Alice")
    alice.page.click("#join-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    wait_for_board_painted(alice)
    next_frame(alice.page)
    return alice


def test_the_fish_panel_shows_a_hand_and_spends_for_a_free_road(browser, tmp_path):
    persistence.save(_fishermen_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The Fishermen panel is up and shows Alice's two fish tokens.
        assert alice.page.query_selector("#right-fish:not(.hidden)") is not None, \
            "the Fishermen panel did not appear"
        tokens = alice.page.query_selector_all("#fish-hand .fish-token")
        assert len(tokens) == 2, "Alice's two fish tokens did not render"

        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().free_roads_remaining"
        ) == 0

        # Spend the 5-fish free road (no pick needed): the button fires at once.
        alice.page.click("#fish-free-road")

        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().free_roads_remaining === 1",
            timeout=5000,
        )
        # The spent fish leave the hand.
        alice.page.wait_for_function(
            "() => (window.__catanDebug.getBoard().tb.fish_hand || []).length === 0",
            timeout=5000,
        )
    finally:
        stop_server(proc)


def test_the_boot_holder_can_pass_the_old_boot(browser, tmp_path):
    persistence.save(_boot_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # Alice holds the boot; the supply row names her as the holder.
        assert alice.page.query_selector("#right-fish:not(.hidden)") is not None, \
            "the Fishermen panel did not appear"
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().tb.old_boot_holder === 'Alice'",
            timeout=5000,
        )

        # Open the pass affordance and hand the boot to Bob (an eligible taker).
        alice.page.click("#fish-pass-boot")
        alice.page.click("#fish-boot-pick [data-target='Bob']")

        # The boot is Bob's now — a change every player sees.
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().tb.old_boot_holder === 'Bob'",
            timeout=5000,
        )
    finally:
        stop_server(proc)


def test_the_lake_shows_which_numbers_pay_fish(browser, tmp_path):
    """The lake pays on 2/3/11/12 but carries no number token; the board now
    prints those numbers on it. Count the pill's dark-green ink at the lake
    centre — a plain lake tile (the old behaviour) has none there."""
    persistence.save(_fishermen_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        lake = alice.page.evaluate(
            "() => window.__catanDebug.getBoard().tb.lake_hex"
        )
        assert lake == "0,0,0", lake  # fishermen.json places the lake at origin
        green = alice.page.evaluate(
            """() => {
                const canvas = document.getElementById('board-canvas');
                const board = window.__catanDebug.getBoard();
                const layout = window.BoardRenderer.computeLayout(board);
                const raw = layout.hexPositions[board.tb.lake_hex];
                // boardToClient expects the offset board coord the renderer draws at.
                const pos = window.BoardRenderer.boardToClient(
                    canvas, raw.x + layout.offsetX, raw.y + layout.offsetY);
                const rect = canvas.getBoundingClientRect();
                const cx = Math.round((pos.x - rect.left) * canvas.width / rect.width);
                const cy = Math.round((pos.y - rect.top) * canvas.height / rect.height);
                const box = 45;
                const d = canvas.getContext('2d')
                    .getImageData(cx - box, cy - box, box * 2, box * 2).data;
                let n = 0;
                for (let i = 0; i < d.length; i += 4) {
                    const r = d[i], g = d[i + 1], b = d[i + 2];
                    if (r < 60 && g > 30 && g < 100 && b < 75 && g > r && g > b) n++;
                }
                return n;
            }"""
        )
        assert green > 30, f"lake production pill not drawn (dark-green px={green})"
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_fish_panel(browser, tmp_path):
    persistence.save(_base_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-fish.hidden") is not None, \
            "the Fishermen panel showed in a base game"
    finally:
        stop_server(proc)
