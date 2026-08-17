"""The left log rail must not scroll as a whole — only the log messages do.

The tester's report on v3.7.0 (verbatim): "w ui mało zmian, mieści się ale lewą
stronę trzeba scrollować co jest niewygodne" — it fits, but you have to scroll
the LEFT SIDE, which is uncomfortable.

On a crowded four-player Cities & Knights table the left `.table-aside` rail
carries the bank, the titles, the C&K folds and the game log, and their combined
height once exceeded the column, so the WHOLE rail scrolled (a rail-level
scrollbar), pushing the log below the fold. Reaching the log by scrolling the
entire rail is the discomfort.

The fix caps `.table-aside` to the viewport so the rail itself never scrolls,
and makes `#log-entries` the single region that shrinks and scrolls internally,
like a chat log. So the always-visible sections (bank, titles, costs, folds)
stay whole and on-screen, and at most the log messages scroll within their own
bounded box.

These pin the complaint: the aside does not overflow (`scrollHeight <=
clientHeight`, no rail scroll), the fixed sections are fully on-screen, and
`#log-entries` is the scrollable element — at 1920x1080 and at 1600x1000.

Run: pytest tests/test_browser_left_rail_no_scroll.py -m slow -v
"""

import os
import random

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
)
from game import persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT_1920 = {"width": 1920, "height": 1080}
VIEWPORT_1600 = {"width": 1600, "height": 1000}
GAME_SEED = 20260817

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(REPO, "test-artifacts", "ui", "left-rail")

TABLE = ["Alice", "Bob", "Carol", "Dave"]


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


def build_ck_game():
    """A started four-player Cities & Knights game, dice up — the crowded table
    the tester hit. The rail carries the full bank, the titles and every C&K
    fold, which is what once overran the column."""
    game = Game(
        list(TABLE), [], rng=random.Random(GAME_SEED),
        rules=rules_module.preset_rules("cities_and_knights"),
    )
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    return game


def connect(browser, url, viewport):
    tabs = {}
    for name in TABLE:
        player = Player(browser, url, name, viewport=viewport)
        # Not Player.join(): a join into a running game answers with the game
        # screen, not the lobby.
        player.page.check("#role-player")
        player.page.fill("#username", name)
        player.page.click("#join-btn")
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        tabs[name] = player
    return tabs


def rail_metrics(player):
    """The aside's own overflow, and the log's role, in one round-trip."""
    return player.page.evaluate(
        """() => {
            const aside = document.querySelector('.table-aside');
            const log = document.querySelector('#log-entries');
            if (!aside || !log) return null;
            const view = { w: window.innerWidth, h: window.innerHeight };
            const ar = aside.getBoundingClientRect();
            const lr = log.getBoundingClientRect();
            const logStyle = getComputedStyle(log);
            // The always-visible fixed sections: everything in the rail that is
            // not the log message list. Each must sit fully inside the viewport.
            const fixedSelectors = [
                '#right-bank', '#right-titles', '#folds-panel', '.tab-bar',
            ];
            const fixed = {};
            for (const sel of fixedSelectors) {
                const el = document.querySelector(sel);
                if (!el) continue;
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                fixed[sel] = {
                    top: r.top, bottom: r.bottom, left: r.left, right: r.right,
                };
            }
            return {
                view,
                aside: {
                    scrollHeight: aside.scrollHeight,
                    clientHeight: aside.clientHeight,
                    top: ar.top, bottom: ar.bottom,
                    left: ar.left, right: ar.right,
                    overflowY: getComputedStyle(aside).overflowY,
                },
                log: {
                    scrollHeight: log.scrollHeight,
                    clientHeight: log.clientHeight,
                    top: lr.top, bottom: lr.bottom,
                    left: lr.left, right: lr.right,
                    overflowY: logStyle.overflowY,
                },
                fixed,
            };
        }"""
    )


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


def _serve(browser, tmp_path_factory, viewport, tag):
    data_dir = tmp_path_factory.mktemp(f"left-rail-{tag}")
    game = build_ck_game()
    persistence.save(game, os.path.join(str(data_dir), "game.json"))
    proc, url = start_server(data_dir)
    tabs = connect(browser, url, viewport)
    return proc, tabs


@pytest.fixture(scope="module")
def table_1920(browser, tmp_path_factory):
    proc, tabs = _serve(browser, tmp_path_factory, VIEWPORT_1920, "1920")
    yield tabs
    stop_server(proc)


@pytest.fixture(scope="module")
def table_1600(browser, tmp_path_factory):
    proc, tabs = _serve(browser, tmp_path_factory, VIEWPORT_1600, "1600")
    yield tabs
    stop_server(proc)


def _assert_no_rail_scroll(player, label):
    metrics = rail_metrics(player)
    shot(player, label)
    assert metrics, "the rail or the log is not present"
    aside = metrics["aside"]
    log = metrics["log"]

    # The rail itself does not scroll: its content is no taller than its box, so
    # there is no rail-level scrollbar for the player to drag.
    assert aside["scrollHeight"] <= aside["clientHeight"] + 1, (
        f"the left rail overflows and scrolls as a whole "
        f"(scrollHeight {aside['scrollHeight']} > clientHeight "
        f"{aside['clientHeight']}) — the tester's complaint"
    )

    # The rail is inside the viewport top to bottom.
    assert aside["top"] >= -1 and aside["bottom"] <= metrics["view"]["h"] + 1, (
        f"the rail {aside} is not fully within the {metrics['view']} viewport"
    )

    # The log IS the scrollable element, present and on-screen, with real room.
    assert log["overflowY"] in ("auto", "scroll"), (
        f"the log is not the scrollable element (overflow-y {log['overflowY']})"
    )
    assert log["clientHeight"] >= 48, (
        f"the log is only {log['clientHeight']}px tall — collapsed below use"
    )
    assert log["top"] >= aside["top"] - 1 and log["bottom"] <= aside["bottom"] + 1, (
        f"the log {log} is not inside the rail {aside}"
    )

    # Every always-visible fixed section is fully on-screen and un-clipped.
    for sel, box in metrics["fixed"].items():
        assert box["top"] >= -1 and box["bottom"] <= metrics["view"]["h"] + 1, (
            f"the fixed section {sel} {box} is clipped by the "
            f"{metrics['view']} viewport"
        )


class TestLeftRailDoesNotScroll:
    """The rail never scrolls as a whole; only the log messages do."""

    def test_no_rail_scroll_at_1920(self, table_1920):
        alice = table_1920["Alice"]
        _assert_no_rail_scroll(alice, "left-rail-1920")

    def test_no_rail_scroll_at_1600(self, table_1600):
        ann = table_1600["Alice"]
        _assert_no_rail_scroll(ann, "left-rail-1600")

    def test_no_console_errors(self, table_1920):
        alice = table_1920["Alice"]
        assert alice.noisy_errors() == [], alice.noisy_errors()
