"""Play a whole game in a real browser.

Every bug the player hit during development was one the unit tests passed on:
`start_game` crashing on a payload, the Start button vanishing, chat having no
input in the lobby, the expansion toggle showing nothing. In each case a layer
was tested in isolation and green, and the break was where the layers met — or
where they met a browser.

These tests drive real Chromium against a real server. They are slow, so they
are marked `slow` and excluded from the fast suite.

The canvas click maths lives in `browser_harness`, shared with
`test_browser_full_game.py`. It used to be duplicated here, and the copy broke
the moment the board grew an ocean ring: it aimed at a fixed vertex key and
asserted that exact key appeared, where a canvas click actually snaps to
whatever target is nearest.

Run: pytest tests/test_browser_playthrough.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    build_road,
    build_settlement,
    edges_next_to,
    launch_browser,
    legal_setup_vertices,
    resolve_robber,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("browser-data"))
    yield url
    stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = launch_browser(play)
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def table(browser, server):
    """Two joined players in the lobby."""
    alice = Player(browser, server, "Alice")
    bob = Player(browser, server, "Bob")
    alice.join()
    bob.join()
    return alice, bob


class TestLobbyInABrowser:
    def test_the_page_loads_without_console_errors(self, browser, server):
        player = Player(browser, server, "Loader")
        assert player.errors == [], player.errors

    def test_joining_shows_the_lobby(self, table):
        alice, _ = table
        assert alice.page.is_visible("#user-screen")
        assert not alice.page.is_visible("#join-screen")

    def test_both_players_appear_in_the_roster(self, table):
        alice, _ = table
        alice.page.wait_for_function(
            "() => document.querySelectorAll('#players li').length === 2", timeout=5000
        )
        names = alice.page.eval_on_selector_all(
            "#players li", "els => els.map(e => e.textContent.trim())"
        )
        assert sorted(n.split()[0] for n in names) == ["Alice", "Bob"]

    def test_the_start_button_is_enabled_with_two_players(self, table):
        """The button vanishing entirely is exactly what a unit test missed."""
        alice, _ = table
        alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=5000)
        assert not alice.page.is_disabled("#start-game-btn")

    def test_the_rules_picker_renders_grouped(self, table):
        alice, _ = table
        alice.page.wait_for_selector("#rules-list .rule-group", timeout=5000)
        groups = alice.page.eval_on_selector_all(
            "#rules-list .rule-group", "els => els.length"
        )
        assert groups >= 2, "expansions and variants at minimum"

    def test_chat_works_from_the_lobby(self, table):
        """No chat input existed here at all until it was reported."""
        alice, bob = table
        alice.page.fill("#chat-input", "hello from the lobby")
        alice.page.click("#chat-send-btn")
        bob.page.wait_for_function(
            "() => document.querySelector('#log-entries').textContent"
            ".includes('hello from the lobby')",
            timeout=5000,
        )

    def test_a_hostile_chat_message_renders_as_text(self, table):
        alice, bob = table
        payload = "<img src=x onerror=\"window.PWNED=1\">"
        alice.page.fill("#chat-input", payload)
        alice.page.click("#chat-send-btn")
        bob.page.wait_for_function(
            "() => document.querySelector('#log-entries').textContent.includes('onerror')",
            timeout=5000,
        )
        assert bob.page.evaluate("() => window.PWNED") is None
        assert bob.page.eval_on_selector_all("#log-entries img", "els => els.length") == 0


class TestPlayingAGame:
    def test_the_game_starts_and_shows_the_board(self, table):
        alice, bob = table
        alice.page.click("#start-game-btn")
        for player in (alice, bob):
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=8000)
        # The canvas must have a real drawing buffer, or the board is invisible.
        size = alice.page.evaluate(
            "() => { const c = document.getElementById('board-canvas');"
            "        return {w: c.width, h: c.height}; }"
        )
        assert size["w"] > 0 and size["h"] > 0, f"canvas has no buffer: {size}"

    def test_the_board_actually_drew_something(self, table):
        """A blank canvas passes every DOM assertion, so check the pixels."""
        alice, _ = table
        non_blank = alice.page.evaluate("""
            () => {
                const c = document.getElementById('board-canvas');
                const ctx = c.getContext('2d');
                const data = ctx.getImageData(0, 0, c.width, c.height).data;
                let painted = 0;
                for (let i = 3; i < data.length; i += 4) {
                    if (data[i] !== 0) painted++;
                }
                return painted;
            }
        """)
        assert non_blank > 1000, f"only {non_blank} painted pixels - board is blank"

    def test_zoom_changes_the_camera(self, table):
        alice, _ = table
        before = alice.page.evaluate("() => window.BoardRenderer.getScale()")
        alice.page.evaluate("() => window.BoardRenderer.zoomAt(1.5, 100, 100)")
        after = alice.page.evaluate("() => window.BoardRenderer.getScale()")
        assert after > before, f"scale did not change: {before} -> {after}"
        alice.page.evaluate("() => window.BoardRenderer.fitToView()")

    def test_no_console_errors_during_the_whole_session(self, table):
        alice, bob = table
        for player in (alice, bob):
            noisy = [e for e in player.errors if "favicon" not in e.lower()]
            assert noisy == [], f"{player.name}: {noisy}"


class TestSetupByClicking:
    """Drive the whole setup phase through the canvas, as a player would."""

    def test_a_full_setup_phase_can_be_played(self, table):
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}

        expected = len(alice.page.evaluate(
            "() => window.__catanDebug.getBoard().players")) * 2

        placed = 0
        for _step in range(expected + 2):
            board = alice.page.evaluate("() => window.__catanDebug.getBoard()")
            if board["game_phase"] != "setup":
                break

            whose = board["current_player"]
            actor = by_name[whose]

            vertex = build_settlement(actor, legal_setup_vertices(board))
            placed += 1

            edges = edges_next_to(actor.board(), vertex)
            assert edges, "no legal road next to the settlement just placed"
            build_road(actor, edges)

        assert placed == expected, f"only {placed} of {expected} setup placements landed"

        board = alice.page.evaluate("() => window.__catanDebug.getBoard()")
        assert board["game_phase"] == "playing", "setup must hand over to play"

    def test_players_hold_starting_resources(self, table):
        alice, _ = table
        board = alice.page.evaluate("() => window.__catanDebug.getBoard()")
        me = next(p for p in board["players"] if p["is_you"])
        assert sum(me["resources"].values()) > 0, "the second settlement grants resources"

    def test_rolling_the_dice_works(self, table):
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}
        board = alice.page.evaluate("() => window.__catanDebug.getBoard()")
        actor = by_name[board["current_player"]]

        actor.page.wait_for_selector("#roll-dice-btn:not([disabled])", timeout=5000)
        actor.page.click("#roll-dice-btn")
        actor.page.wait_for_function(
            "() => window.__catanDebug.getBoard().has_rolled_dice === true", timeout=5000
        )
        # A 7 leaves the robber pending; the turn cannot advance until it moves.
        resolve_robber(actor)

    def test_the_turn_can_be_advanced(self, table):
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}
        board = alice.page.evaluate("() => window.__catanDebug.getBoard()")
        before = board["current_player"]

        actor = by_name[before]
        resolve_robber(actor)
        actor.page.wait_for_selector("#next-turn-btn:not([disabled])", timeout=8000)
        actor.page.click("#next-turn-btn")
        alice.page.wait_for_function(
            "prev => window.__catanDebug.getBoard().current_player !== prev",
            arg=before, timeout=5000,
        )

    def test_still_no_console_errors_after_playing(self, table):
        for player in table:
            noisy = [e for e in player.errors if "favicon" not in e.lower()]
            assert noisy == [], f"{player.name}: {noisy}"
