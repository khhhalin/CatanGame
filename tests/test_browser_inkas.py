"""Rise of the Inkas in a real browser: the thicket markers and the tribe panel.

New visible surface the unit suite cannot see — the thicket (vines) drawn over a
declining building on the canvas, the tribe/culture panel, and the founding
prompt. The unit suite asserts server state, and a declined tribe leaves server
state perfectly correct while the board could render the ruin as an ordinary
settlement and the panel could be blank.

Run: pytest tests/test_browser_inkas.py -m slow -q
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


def _inkas_game():
    """A started, playing Inkas game with Alice's first tribe in decline: a
    thicket-covered ruin on the board and a founding settlement owed."""
    chosen = dict(rules_module.preset_rules('rise_of_the_inkas'))
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('rise-of-the-inkas'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    # A buildable inland vertex to cover with a thicket.
    ruin = next(key for key in sorted(game.vertices)
                if game.vertices[key].neighbors['hexes'])
    game.vertices[ruin].building = {
        'type': 'settlement', 'player': 'Alice', 'tribe': 1, 'ruined': True}
    alice = game.get_player('Alice')
    alice.settlements.append(ruin)
    alice.tribe = 2
    alice.culture_points = 4
    game.founding_player = 'Alice'
    return game


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def _join(browser, url, name):
    player = Player(browser, url, name, viewport=VIEWPORT)
    player.page.check("#role-player")
    player.page.fill("#username", name)
    player.page.click("#join-btn")
    player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    wait_for_board_painted(player)
    next_frame(player.page)
    return player


# Thicket dark-leaf colour (board-renderer.js THICKET_LEAF_DARK #1f5735 =
# 31,87,53), used by nothing else on the board, so a pixel this colour is a
# rendered thicket and nothing else.
_THICKET_PIXELS = """
() => {
    const canvas = document.getElementById('board-canvas');
    if (!canvas || !canvas.width) { return 0; }
    const data = canvas.getContext('2d')
        .getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
        if (Math.abs(data[i] - 31) <= 6
            && Math.abs(data[i + 1] - 87) <= 6
            && Math.abs(data[i + 2] - 53) <= 6) { count++; }
    }
    return count;
}
"""


def test_a_declining_tribe_shows_thickets_and_the_tribe_panel(browser, tmp_path):
    persistence.save(_inkas_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url, "Alice")

        # The panel is up and names the tribes.
        assert alice.page.query_selector("#right-inkas:not(.hidden)") is not None, \
            "the Rise of the Inkas panel did not appear"
        status = alice.page.inner_text("#inkas-status")
        assert "Tribe" in status, f"the tribe panel showed no tribe: {status!r}"
        assert "II" in status, f"Alice's second tribe was not shown: {status!r}"

        # The founding prompt is up for the player who owes a founding settlement.
        assert alice.page.query_selector("#inkas-hint:not(.hidden)") is not None, \
            "no founding prompt for the player who just declined"

        # The thicket is actually painted on the canvas — count its pixels, since
        # a blank canvas satisfies every DOM assertion.
        thicket_pixels = alice.page.evaluate(_THICKET_PIXELS)
        assert thicket_pixels > 40, \
            f"the ruin was not drawn with a thicket ({thicket_pixels} thicket pixels)"
    finally:
        stop_server(proc)
