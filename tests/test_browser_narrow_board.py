"""The board must not collapse to a dead strip on a narrow window.

Regression for a real report: testing a 2-player scenario game by tiling two
browser windows side by side, ONE player's map was unusable — frozen, nothing
tappable. The two windows straddled the 900px responsive breakpoint, and below
it the board collapsed to a 224px strip with the rest of the tall window empty.

Cause: the `@media (max-width: 900px)` block was written for the old docked-rail
layout — it drops `.container`/`.table` to `height: auto` and leans on
`.game-main { grid-template-rows: 50dvh auto }` to give the board a share of the
viewport. The TEST 6 relayout made `.game-main` a flex box (so the grid rule is
inert) and floated the aside out of flow, so the height chain fell through to the
board's `min-height: 14rem` — a 224px strip. Above 900px the board filled fine;
below it, the map was dead.

The board is the only in-flow content under the floating-overlay layout, so it
must fill the window at every width. This pins the canvas to a real share of a
narrow window and checks its centre is the element a tap lands on — in a base
game and under the Explorers & Pirates and Fishermen presets, because that is
where it was seen.

Run: pytest tests/test_browser_narrow_board.py -m slow -q
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    next_frame,
    start_server,
    stop_server,
    wait_for_board_painted,
    wait_for_preset,
)

pytestmark = pytest.mark.slow

# Narrow enough to be under the 900px breakpoint (a tiled half-screen window),
# tall enough that a collapsed board leaves an obvious dead band.
VIEWPORT = {"width": 850, "height": 1000}

_BOARD_HEIGHT = """
() => Math.round(document.getElementById('board-canvas').getBoundingClientRect().height)
"""

_CENTER_IS_BOARD = """
() => {
    const canvas = document.getElementById('board-canvas');
    const r = canvas.getBoundingClientRect();
    const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return el === canvas;
}
"""


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def _start(browser, url, preset):
    alice = Player(browser, url, "Alice", viewport=VIEWPORT, yolo=True)
    bob = Player(browser, url, "Bob", viewport=VIEWPORT, yolo=True)
    alice.join()
    bob.join()
    alice.page.wait_for_function(
        "() => document.querySelectorAll('#players li').length === 2", timeout=8000
    )
    if preset:
        alice.page.click(f"#preset-{preset}")
        wait_for_preset(alice, preset)
    alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    alice.page.click("#start-game-btn")
    for player in (alice, bob):
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        wait_for_board_painted(player)
        next_frame(player.page)
    return alice, bob


@pytest.mark.parametrize("preset", [None, "explorers_and_pirates", "tb_fishermen"])
def test_the_board_fills_a_narrow_window_for_both_players(browser, tmp_path_factory, preset):
    proc, url = start_server(tmp_path_factory.mktemp("narrow"))
    try:
        alice, bob = _start(browser, url, preset)
        for player in (alice, bob):
            height = player.page.evaluate(_BOARD_HEIGHT)
            # The window is 1000px tall; a board that filled it is ~950px. The
            # collapse pinned it to 224px. Anything under half the window is the
            # dead strip, so this fails loudly on the bug and passes on a fill.
            assert height > 600, (
                f"{player.name} ({preset}): board is only {height}px tall in a "
                f"{VIEWPORT['height']}px window — the map collapsed to a strip"
            )
            assert player.page.evaluate(_CENTER_IS_BOARD), (
                f"{player.name} ({preset}): the board centre is covered — a tap "
                "there would not reach the map"
            )
    finally:
        stop_server(proc)
