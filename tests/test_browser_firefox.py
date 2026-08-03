"""The paths whose breakage would make the game unusable, run under Firefox.

The rest of the browser suite runs on Chromium unless `CATAN_TEST_BROWSER` says
otherwise, so nothing pins Gecko by default and a Gecko-only regression would
reach players unseen. This file is that pin: it launches Firefox explicitly,
whatever the environment is set to.

It is deliberately a smoke suite rather than a second copy of the suite. Firefox
is a *supported* browser here, not a suspect one - the game is played in Zen
(Gecko) today, and a full run under Firefox passed 96 tests. So the risk worth
spending time on is a future regression in the handful of places the two engines
could plausibly disagree, which is what each test below is chosen for:

  - the page loads and no script on it throws;
  - the lobby renders, so a player can get in at all;
  - a game starts;
  - the board paints actual pixels - `<canvas>` sizing and the device pixel
    ratio are the most engine-sensitive thing in this codebase, and every DOM
    assertion in the suite passes over a blank canvas;
  - a placement can be aimed and confirmed, which is the whole game loop and
    depends on Gecko's `getBoundingClientRect` and pointer events agreeing with
    the camera maths;
  - the no-scroll layout holds at 1920x1080. This is the one with real history:
    the layout leans on `color-mix()`, `:has()` and `backdrop-filter`, all of
    which Firefox supports, and the assertion here is what would notice if a
    future rule used something it does not.

Anything that is pure game logic, or pure DOM with no engine-specific
dependency, is already covered once and is not repeated here.

Run: pytest tests/test_browser_firefox.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    click_vertex,
    confirm_placement,
    count_pieces,
    first_clickable,
    launch_browser,
    legal_setup_vertices,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright
from test_browser_layout import assert_nothing_scrolls_or_clips

pytestmark = pytest.mark.slow

# The no-scroll layout was designed against this size and is asserted at it in
# `test_browser_layout.py`; using the same one keeps the two comparable.
VIEWPORT = {"width": 1920, "height": 1080}

# Fixed board, so a failure here is a Firefox failure rather than a board that
# happened to deal an awkward setup.
GAME_SEED = 20260804

PAINTED_PIXELS = """
() => {
    const canvas = document.getElementById('board-canvas');
    const data = canvas.getContext('2d')
        .getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let i = 3; i < data.length; i += 4) {
        if (data[i] !== 0) count++;
    }
    return count;
}
"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("firefox-data"), seed=GAME_SEED)
    yield url
    stop_server(proc)


@pytest.fixture(scope="module")
def firefox():
    """Firefox specifically, ignoring CATAN_TEST_BROWSER.

    Pinned rather than configured: a cross-browser check that only runs when
    someone remembers to set an environment variable is not a check.
    """
    with sync_playwright() as play:
        instance = launch_browser(play, browser="firefox")
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def table(firefox, server):
    """Two seated players in a started game — shared, because it is a smoke run.

    One game for the whole file rather than one per test: these assertions do
    not disturb each other, and a server plus a browser per test would cost more
    than the coverage is worth.
    """
    host = Player(firefox, server, "Ann", viewport=VIEWPORT)
    guest = Player(firefox, server, "Bo", viewport=VIEWPORT)
    host.join()
    guest.join()
    host.page.click("#start-game-btn")
    for player in (host, guest):
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=8000)
    return host, guest


def test_the_lobby_renders_and_nothing_throws(firefox, server):
    """A fresh tab: the join form is there and no script on the page failed.

    Its own tab rather than the shared table, because this is about the state
    before anyone has joined - the only moment at which a module-level failure
    in an ES module would still be visible as an empty screen.
    """
    visitor = Player(firefox, server, "Solo", viewport=VIEWPORT)
    assert visitor.page.is_visible("#join-btn")
    assert visitor.page.is_visible("#username")
    assert visitor.noisy_errors() == [], visitor.noisy_errors()


def test_a_game_starts(table):
    host, _ = table
    assert host.board()["game_phase"] == "setup"
    assert host.page.is_visible("#board-canvas")


def test_the_board_paints_pixels(table):
    """A blank canvas satisfies every DOM assertion in this file.

    Canvas backing-store sizing against `devicePixelRatio` is the most
    engine-sensitive code here, and getting it wrong yields a correctly-sized,
    entirely empty canvas.
    """
    host, _ = table
    painted = host.page.evaluate(PAINTED_PIXELS)
    assert painted > 1000, f"only {painted} painted pixels — the board is blank"


def test_a_placement_can_be_aimed_and_confirmed(table):
    """The core loop: click the board, get the ✓, press it, own a settlement.

    This is the assertion that would catch the camera maths disagreeing with
    Gecko's `getBoundingClientRect` - a click that lands on the wrong vertex, or
    on none at all, breaks the game completely while leaving every panel on the
    screen looking correct.
    """
    host, guest = table
    actor = next(
        (p for p in (host, guest) if p.board()["current_player"] == p.name), None
    )
    assert actor, "neither tab is on turn"

    before = count_pieces(actor, "settlement")
    vertex = first_clickable(actor, "vertex", legal_setup_vertices(actor.board()))
    assert vertex, "no reachable vertex to place on"
    click_vertex(actor, vertex)
    assert confirm_placement(actor), "the ✓ never appeared"

    # Not keyed to the vertex aimed at: the canvas snaps to the nearest target,
    # so an equally legal neighbour is a correct outcome. That a piece was
    # placed at all is the thing under test.
    actor.page.wait_for_function(
        "([owner, before]) => Object.values(window.__catanDebug.getBoard().vertices)"
        ".filter(v => (v.building || {}).player === owner).length > before",
        arg=[actor.name, before], timeout=8000,
    )
    assert count_pieces(actor, "settlement") == before + 1


def test_the_layout_does_not_scroll_at_1920x1080(table):
    """The no-scroll layout holds in Gecko too.

    Same probe as `test_browser_layout.py` runs under Chromium. The layout
    depends on `color-mix()`, `:has()` and `backdrop-filter`; all three are
    supported, and this is what would say so if one stopped being.
    """
    host, _ = table
    host.shot("firefox-game-1920x1080")
    assert_nothing_scrolls_or_clips(host, "firefox, game screen at 1920x1080")
