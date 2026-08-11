"""Regressions for the TEST 5 player report (UI bugs a player hit, on main).

Collisions: the overlays layered on the board must not sit on top of one another
— the players panel, the build/"what changed" pill, the zoom controls, the dice
and the log panel each keep their own space. Each test asserts a real overlap of
the two elements' on-screen boxes, so it fails on the code as it was when the bug
was filed and passes on the fix.

The trade-decrement, discard-staging and offer-popup regressions drive the trade
tray and a second player; they are added separately once their tray DOM is pinned.

Run: pytest tests/test_browser_test5_fixes.py -m slow -v
"""

import os

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    build_settlement,
    edges_next_to,
    legal_setup_vertices,
    next_frame,
    start_server,
)
from browser_harness import (
    stop_server as harness_stop_server,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}
GAME_SEED = 20260803

SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "test5",
)


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


def make_table(browser, url, names, viewport=None):
    players = [
        Player(browser, url, name, viewport=viewport or VIEWPORT, yolo=True)
        for name in names
    ]
    for player in players:
        player.join()
    players[0].page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    players[0].page.click("#start-game-btn")
    for player in players:
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    return players


def place_setup_round(players):
    """Drive the whole setup phase, so the board is a real mid-game board with a
    full scoreboard — the worst case for the top-left collision."""
    for _ in range(len(players) * 2 * 2):
        board = players[0].board()
        if board["game_phase"] != "setup":
            return
        actor = next(p for p in players if p.name == board["current_player"])
        if board.get("setup_action") == "road":
            vertex = next(
                key for key, v in board["vertices"].items()
                if (v.get("building") or {}).get("player") == actor.name
                and not any(
                    (board["edges"][e].get("road") or {}).get("player") == actor.name
                    for e in v["neighbors"]["edges"]
                )
            )
            build_road(actor, edges_next_to(board, vertex))
        else:
            build_settlement(actor, legal_setup_vertices(board))


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def table(browser, tmp_path_factory):
    """Four players, past setup — the most rows in the scoreboard, so the
    top-left overlays are at their tallest and worst for a collision."""
    proc, url = start_server(tmp_path_factory.mktemp("test5"), seed=GAME_SEED)
    players = make_table(browser, url, ["Alice", "Bob", "Carol", "Dave"])
    place_setup_round(players)
    yield players
    harness_stop_server(proc)


@pytest.fixture(scope="module")
def table_1600(browser, tmp_path_factory):
    """A game at the harness default 1600x1000 — the width test_browser_full_game
    plays at. The dice-vs-hand overlap that stalled a full game at a 7-roll is a
    bottom-row geometry that tightens as the board narrows, so it is pinned here
    at that exact width rather than only at 1920."""
    proc, url = start_server(tmp_path_factory.mktemp("test5-1600"), seed=GAME_SEED)
    players = make_table(browser, url, ["Ann", "Ben"],
                         viewport={"width": 1600, "height": 1000})
    place_setup_round(players)
    yield players
    harness_stop_server(proc)


def rect(player, selector):
    """The on-screen box of a visible element, or None if it is hidden."""
    return player.page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
        }""",
        selector,
    )


def overlaps(a, b):
    """Whether two boxes share any area."""
    return not (
        a["right"] <= b["left"] or b["right"] <= a["left"]
        or a["bottom"] <= b["top"] or b["bottom"] <= a["top"]
    )


class TestOverlaysDoNotCollide:
    """The three collisions the player reported, each asserted as a real overlap
    of the two elements' on-screen boxes."""

    def test_the_build_pill_does_not_sit_on_the_players_panel(self, table):
        alice = table[0]
        next_frame(alice.page)
        players = rect(alice, "#players-panel")
        pill = rect(alice, "#changelog-panel")
        shot(alice, "test5-01-top-left")
        assert players and pill, "players panel or build pill is not visible"
        assert not overlaps(players, pill), (
            f"the build/'what changed' pill {pill} overlaps the players panel {players}"
        )

    def test_the_zoom_controls_are_not_behind_the_log_panel(self, table):
        alice = table[0]
        controls = rect(alice, ".board-controls")
        aside = rect(alice, ".table-aside")
        assert controls and aside, "zoom controls or log panel is not visible"
        assert not overlaps(controls, aside), (
            f"the zoom controls {controls} are covered by the log panel {aside}"
        )

    def test_the_dice_are_not_under_the_log_panel(self, table):
        alice = table[0]
        dice = rect(alice, "#dice-footer")
        aside = rect(alice, ".table-aside")
        assert dice and aside, "dice or log panel is not visible"
        assert not overlaps(dice, aside), (
            f"the dice {dice} overlap the log panel {aside} "
            f"(dice height {dice['bottom'] - dice['top']:.0f}px)"
        )

    def test_the_dice_do_not_cover_the_hand(self, table):
        """The dice float must not sit over the hand fan — a dice float on top of
        the cards makes them unclickable (the discard/trade tap lands on the dice
        instead), which is exactly what stalled a full game at a 7-roll."""
        alice = table[0]
        dice = rect(alice, "#dice-footer")
        hand = rect(alice, "#resource-display")
        assert dice and hand, "dice or hand is not visible"
        assert not overlaps(dice, hand), (
            f"the dice {dice} cover the hand {hand}"
        )

    def test_no_console_errors(self, table):
        assert table[0].noisy_errors() == [], table[0].noisy_errors()


class TestTheBottomRowAtFullGameWidth:
    """At 1600x1000 — the width the full-game playthrough uses — the dice must
    still clear the hand and the log panel. This is the regression that stalled
    test_browser_full_game: the dice float covered the hand cards, so a discard
    tap after a 7 landed on the dice and the game could not continue."""

    def test_the_dice_clear_the_hand(self, table_1600):
        ann = table_1600[0]
        next_frame(ann.page)
        dice = rect(ann, "#dice-footer")
        hand = rect(ann, "#resource-display")
        shot(ann, "test5-02-bottom-row-1600")
        assert dice and hand, "dice or hand is not visible"
        assert not overlaps(dice, hand), f"the dice {dice} cover the hand {hand}"

    def test_the_dice_clear_the_log_panel(self, table_1600):
        ann = table_1600[0]
        dice = rect(ann, "#dice-footer")
        aside = rect(ann, ".table-aside")
        assert dice and aside, "dice or log panel is not visible"
        assert not overlaps(dice, aside), f"the dice {dice} overlap the log {aside}"
