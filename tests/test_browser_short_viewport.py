"""The whole shell fits a short laptop viewport, with the hand fully on screen.

The regression this suite was written for: the v2 UI overhaul moved the resource
hand into a bottom tray of physical cards, and the layout was only ever
screenshotted at 1000-1080px tall. On a normal laptop after browser chrome
(~768-900px) the board is a greedy vertical track that eats every spare row, the
rail's fold stack spills past the fold, and the page grows taller than the
viewport - so the "YOUR HAND" cards are jammed against, or below, the bottom
edge. Measured at 1366x768 with four players and Cities & Knights on, the
document was 930px tall inside a 768px viewport.

The failing state, before the fix:
  - `document.documentElement.scrollHeight` was 930 at 768 tall - the page
    overflowed by 162px, the rail's folds hanging off the bottom;
  - the hand sat flush against the viewport's bottom edge with no clearance.

So the assertions here are, at the sizes the regression bites (four players,
Cities & Knights, 1366x768 and 1440x800):
  - the page does not scroll, in either axis;
  - every physical card in the hand is fully inside the viewport, with a little
    clearance below it - not clipped, not flush against the edge;
  - the whole tray is inside the viewport.

Four players and Cities & Knights is the worst case for the same reason
`test_browser_layout.py` uses it: the tallest scoreboard and the most folds in
the rail. The 1080 layout that was already good is checked here too, so a fix
that shrank the short-viewport case cannot quietly regress it.

Arranged from a saved game rather than played through the UI, as
`test_browser_hand.py` does: only the layout is under test, and a mid-game board
with four players and every C&K fold is many non-deterministic turns away.

Run: pytest tests/test_browser_short_viewport.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    browser_session,
    next_frame,
    start_server,
    stop_server,
)
from game import persistence, rules
from game.game import Game

pytestmark = pytest.mark.slow

# Where the sign-off screenshots land, beside the other v2 UI shots.
SHOT_DIR = "/home/kalin/.claude/jobs/824814a1/tmp"

TABLE = ["Alice", "Bob", "Carol", "Dave"]

# The two short laptop viewports the regression bites. Both are above the
# 1200px width where the layout folds to a single scrolling column, so both
# exercise the two-column desktop shell where the bug lives.
SHORT_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 800},
]

TALL_VIEWPORT = {"width": 1920, "height": 1080}

# At a short height the hand must clear the bottom edge, not merely touch it: a
# card resting on the fold reads as clipped on a real browser, where dvh and the
# console's wrap point differ by a pixel or two from headless. The short-height
# rules reserve a real strip below the tray, so we require that clearance where
# the regression bit. The 1080 layout is only asked to keep the hand on screen -
# it already rests a few pixels off the edge and the fix may not change that.
SHORT_HEIGHT_CLEARANCE = 10


def build_game():
    """A four-player Cities & Knights game, mid-play, with a full hand.

    The preset ticks the individual C&K rules (there is no expansion mode); the
    rail then renders every fold, which is what overflows at a short height.
    """
    game = Game(list(TABLE), [], rng=random.Random(7),
                rules=rules.preset_rules("cities_and_knights"))
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    actor = game.get_player(game.current_player_name())
    actor.resources.update({"wood": 3, "brick": 1, "sheep": 2, "wheat": 4, "ore": 5})
    # Commodities add three more cards to the fan, the widest the hand ever is.
    if hasattr(actor, "commodities"):
        actor.commodities.update({"cloth": 2, "coin": 1, "paper": 3})
    return game


@contextmanager
def table(browser, data_dir, viewport):
    persistence.save(build_game(), os.path.join(str(data_dir), "game.json"))
    proc, url = start_server(data_dir)
    try:
        game = build_game()
        active = game.current_player_name()
        player = Player(browser, url, active, viewport=viewport)
        player.page.check("#role-player")
        player.page.fill("#username", active)
        player.page.click("#join-btn")
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        player.page.wait_for_selector("#resource-display .hand-card", timeout=8000)
        next_frame(player.page)
        yield player
    finally:
        stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


# --- The measurements ------------------------------------------------------

_FIT = """
() => {
    const doc = document.documentElement;
    const cards = [...document.querySelectorAll('#resource-display .hand-card')]
        .map(c => c.getBoundingClientRect());
    const tray = document.querySelector('.game-tray').getBoundingClientRect();
    return {
        viewH: window.innerHeight,
        viewW: window.innerWidth,
        scrollH: doc.scrollHeight,
        scrollW: doc.scrollWidth,
        cardCount: cards.length,
        cardBottomMax: Math.max(...cards.map(r => r.bottom)),
        cardTopMin: Math.min(...cards.map(r => r.top)),
        cardHeight: cards.length ? cards[0].height : 0,
        trayBottom: tray.bottom,
        trayTop: tray.top,
    };
}
"""


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"ui-fit-{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


def shot_themed(player, label):
    paths = []
    for theme in ("light", "dark"):
        player.page.evaluate(
            "t => document.documentElement.setAttribute('data-theme', t)", theme
        )
        next_frame(player.page)
        paths.append(shot(player, f"{label}-{theme}"))
    player.page.evaluate("() => document.documentElement.removeAttribute('data-theme')")
    next_frame(player.page)
    return paths


@pytest.mark.parametrize("viewport", SHORT_VIEWPORTS, ids=lambda v: f"{v['width']}x{v['height']}")
def test_the_shell_fits_and_the_hand_is_not_clipped(browser, tmp_path_factory, viewport):
    """At a short laptop viewport the page must not scroll and every hand card
    must sit fully inside it. Both parts failed before the fix: the rail's folds
    pushed the document to 930px inside 768, and the greedy board left the hand
    flush against the bottom edge."""
    where = f"{viewport['width']}x{viewport['height']}"
    with table(browser, tmp_path_factory.mktemp(f"short-{where}"), viewport) as player:
        fit = player.page.evaluate(_FIT)

        assert fit["scrollH"] <= fit["viewH"] + 1, (
            f"{where}: the page scrolls vertically - document is {fit['scrollH']}px "
            f"in a {fit['viewH']}px viewport"
        )
        assert fit["scrollW"] <= fit["viewW"] + 1, (
            f"{where}: the page scrolls horizontally - {fit['scrollW']} vs {fit['viewW']}"
        )

        assert fit["cardCount"] == 8, (
            f"{where}: expected the eight-card C&K hand, saw {fit['cardCount']}"
        )
        assert fit["cardBottomMax"] <= fit["viewH"] - SHORT_HEIGHT_CLEARANCE, (
            f"{where}: the hand is clipped or flush - lowest card bottom is "
            f"{fit['cardBottomMax']:.0f}px, viewport is {fit['viewH']}px"
        )
        assert fit["cardTopMin"] >= -1, (
            f"{where}: the top of the hand is above the viewport: {fit['cardTopMin']:.0f}px"
        )
        assert fit["trayBottom"] <= fit["viewH"] + 1, (
            f"{where}: the tray hangs off the bottom: {fit['trayBottom']:.0f}px "
            f"in {fit['viewH']}px"
        )

        shot(player, where)


def test_the_1080_layout_is_unregressed(browser, tmp_path_factory):
    """The tall layout the shell was tuned for must still fit with the hand on
    screen - the short-viewport fix is gated on height and may not touch it."""
    with table(browser, tmp_path_factory.mktemp("short-tall"), TALL_VIEWPORT) as player:
        fit = player.page.evaluate(_FIT)
        assert fit["scrollH"] <= fit["viewH"] + 1, (
            f"1080: the page scrolls: {fit['scrollH']} vs {fit['viewH']}"
        )
        assert fit["cardBottomMax"] <= fit["viewH"] + 1, (
            f"1080: the hand is clipped: {fit['cardBottomMax']:.0f}px vs {fit['viewH']}px"
        )
        # The full-size card is kept at 1080; the compact face is a short-height
        # concession, and swapping it in here would regress the layout on the
        # screen the sign-off was read from.
        assert fit["cardHeight"] >= 44, (
            f"1080: the hand cards were shrunk to the compact size: {fit['cardHeight']:.0f}px"
        )
        shot(player, "1920x1080")


def test_a_human_can_look_at_it(browser, tmp_path_factory):
    """Not an assertion - the screenshots the sign-off is read from, both themes
    at the short viewport where the hand used to clip."""
    with table(browser, tmp_path_factory.mktemp("short-shots"),
               SHORT_VIEWPORTS[0]) as player:
        shot_themed(player, "1366x768")
        assert not player.noisy_errors(), player.noisy_errors()
