"""What a tab is told when the server acts on its own initiative.

Two symptoms a tester filed, both with the same shape:

  - "after dice timer ends, round timer doesnt show — works correctly when
    player rolls dice manually";
  - "game log got stuck with no new messages".

The turn watchdog runs in a background task with no request behind it, and
`broadcast_board` and `log_event` once used the request-scoped
`flask_socketio.emit`, which raises there. Every board update and every log line
the server sent on its own initiative died inside the watchdog's `except`
clause, so a tab that was not clicking anything learned nothing: the dice were
rolled for the player, the round began, and the client never heard about either.

Nothing here clicks after setup. That is the whole point — the assertions are
about what arrives unbidden.

Run: pytest tests/test_browser_timers.py -m slow -v
"""

import re

import pytest
from browser_harness import (
    Player,
    build_road,
    build_settlement,
    edges_next_to,
    launch_browser,
    legal_setup_vertices,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

# TestingConfig: a 1s dice clock and a 2s round clock. A test that waited out
# development's 15s and 120s would not be run.
TIMER_CONFIG = "testing"

# Fixed board and dice, so a run that fails is reproducible.
GAME_SEED = 20260804

# Long enough for the 1s dice clock to expire and the broadcast to land, short
# enough that a lost broadcast fails rather than hangs.
WATCHDOG_GRACE_MS = 8000

# The round clock shows "Round: 2s"; before the roll it reads "Round: —".
ROUND_TIMER_RUNNING = re.compile(r"Round: \d+s")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = launch_browser(play)
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def table(browser, tmp_path_factory):
    """Two tabs past setup, with the watchdog's clocks running.

    YOLO mode on both: setup is 8 placements and every one of them would
    otherwise wait for a ✓ that this suite is not about.
    """
    proc, url = start_server(
        tmp_path_factory.mktemp("timers-data"), seed=GAME_SEED, config=TIMER_CONFIG
    )
    alice = Player(browser, url, "Alice", yolo=True)
    bob = Player(browser, url, "Bob", yolo=True)
    alice.join()
    bob.join()
    alice.page.click("#start-game-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)

    by_name = {"Alice": alice, "Bob": bob}
    for _step in range(12):
        board = alice.board()
        if board["game_phase"] != "setup":
            break
        actor = by_name[board["current_player"]]
        vertex = build_settlement(actor, legal_setup_vertices(board))
        build_road(actor, edges_next_to(actor.board(), vertex))

    assert alice.board()["game_phase"] == "playing", "setup never finished"
    yield alice, bob
    stop_server(proc)


class TestTheWatchdogsBroadcastReachesTheClient:
    """Regression: the round timer never appeared after an auto-roll.

    `broadcast_board` used the request-scoped `emit`, which raises in a
    background task, so the board update announcing the auto-roll was swallowed
    and every tab stayed on `has_rolled_dice: false` — which is exactly the
    state in which the round clock reads "—".
    """

    def test_the_round_timer_appears_after_the_dice_timer_expires(self, table):
        """Both tabs, and neither of them clicks: the roll can only be the
        watchdog's, and only a broadcast that survived the background task can
        put a tab into the state where the round clock is drawn at all."""
        alice, bob = table

        for player in (alice, bob):
            # Polled rather than sampled once: with a 2s round the table cycles
            # through auto-roll and auto-advance repeatedly, so the assertion is
            # that the running clock is reached at all, not that it is showing
            # at one particular instant.
            player.page.wait_for_function(
                "() => /Round: \\d+s/.test(document.getElementById('round-timer').textContent)",
                timeout=WATCHDOG_GRACE_MS,
            )
            assert ROUND_TIMER_RUNNING.search(player.page.inner_text("#round-timer"))


class TestTheLogKeepsMoving:
    """Regression: "game log got stuck with no new messages".

    `log_event` emits from the watchdog too — an auto-roll logs the dice, and an
    expiring round logs the turn change. With the request-scoped emit both were
    lost, and the log stopped dead the moment a player stopped clicking.
    """

    def test_entries_keep_arriving_with_nobody_touching_the_page(self, table):
        alice, bob = table

        before = bob.page.eval_on_selector_all("#log-entries .log-entry", "els => els.length")
        bob.page.wait_for_function(
            "before => document.querySelectorAll('#log-entries .log-entry').length > before + 2",
            arg=before, timeout=WATCHDOG_GRACE_MS,
        )

        texts = bob.page.eval_on_selector_all(
            "#log-entries .log-entry .log-text", "els => els.map(e => e.textContent)"
        )
        assert any("rolled" in text for text in texts), (
            f"no auto-rolled dice reached the log: {texts[-6:]}"
        )

    def test_no_console_errors(self, table):
        alice, bob = table
        assert alice.noisy_errors() == []
        assert bob.noisy_errors() == []
