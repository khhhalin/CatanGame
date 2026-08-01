"""Play a whole game in a real browser.

Every bug the player hit during development was one the unit tests passed on:
`start_game` crashing on a payload, the Start button vanishing, chat having no
input in the lobby, the expansion toggle showing nothing. In each case a layer
was tested in isolation and green, and the break was where the layers met — or
where they met a browser.

These tests drive real Chromium against a real server. They are slow, so they
are marked `slow` and excluded from the fast suite.

Run: pytest tests/test_browser_playthrough.py -m slow -v
"""

import os
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright", reason="playwright is not installed")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(REPO, "server")

pytestmark = pytest.mark.slow


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """A real gunicorn server on its own port with its own data directory."""
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("browser-data")
    env = dict(
        os.environ,
        SECRET_KEY="browser-test",
        CATAN_DATA_DIR=str(data_dir),
        # Development, not testing: TestingConfig uses a 1s dice timer and a
        # 2s round timer, so the turn watchdog auto-rolls and advances turns
        # faster than a browser can click. Realistic timers are required for a
        # human-paced playthrough to mean anything.
        CATAN_CONFIG="development",
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "-w", "1", "--threads", "50",
         "-b", f"127.0.0.1:{port}", "wsgi:app"],
        cwd=SERVER_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("server never came up")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = play.chromium.launch()
        yield instance
        instance.close()


class Player:
    """One browser tab, with its console errors collected."""

    def __init__(self, browser, url, name):
        self.name = name
        self.errors = []
        self.page = browser.new_context().new_page()
        self.page.on("console", self._console)
        self.page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        self.page.goto(url, wait_until="networkidle")

    def _console(self, message):
        if message.type == "error":
            self.errors.append(message.text)

    def join(self, as_player=True):
        self.page.check("#role-player" if as_player else "#role-observer")
        self.page.fill("#username", self.name)
        self.page.click("#join-btn")
        self.page.wait_for_selector("#user-screen:not(.hidden)", timeout=5000)

    def board_state(self):
        return self.page.evaluate("() => window.__testBoard || null")


def _install_probe(player):
    """Expose the client's board data so assertions can read real state."""
    player.page.evaluate("""
        () => {
            const socket = window.__socket;
            if (socket) { return; }
        }
    """)


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


# --- Playing the game by clicking the board -------------------------------

CLICK_HELPERS = """
() => {
    // Board space is what findNearest* compare against: the raw layout
    // position plus the layout offset. Forward-transform it through the same
    // camera the renderer uses, so a click lands where the test intends.
    const board = window.__catanDebug.getBoard();
    const canvas = document.getElementById('board-canvas');
    const layout = window.BoardRenderer.computeLayout(board);
    const scale = window.BoardRenderer.getScale();
    const rect = canvas.getBoundingClientRect();
    return { board, layout, scale, rect: {left: rect.left, top: rect.top} };
}
"""


def _click_vertex(player, vertex_key):
    """Click the canvas where a given vertex is drawn."""
    info = player.page.evaluate(CLICK_HELPERS)
    pos = info["layout"]["vertexPositions"][vertex_key]
    # cssX = (pos + offset) * scale + camera.x ; camera.x is folded into the
    # renderer, so ask it to do the inverse-of-the-inverse for us.
    point = player.page.evaluate(
        """([vx, vy, ox, oy]) => {
            const canvas = document.getElementById('board-canvas');
            const rect = canvas.getBoundingClientRect();
            // Binary-search the client point whose clientToBoard maps to (vx,vy).
            // Simpler: clientToBoard is affine, so sample two points and invert.
            const p0 = window.BoardRenderer.clientToBoard(canvas, rect.left, rect.top);
            const p1 = window.BoardRenderer.clientToBoard(canvas, rect.left + 100, rect.top + 100);
            const sx = 100 / (p1.x - p0.x);
            const sy = 100 / (p1.y - p0.y);
            return {
                x: rect.left + (vx + ox - p0.x) * sx,
                y: rect.top + (vy + oy - p0.y) * sy,
            };
        }""",
        [pos["x"], pos["y"], info["layout"]["offsetX"], info["layout"]["offsetY"]],
    )
    player.page.mouse.click(point["x"], point["y"])


def _legal_setup_vertex(board):
    """A vacant vertex with no neighbouring building - the distance rule."""
    for key, vertex in board["vertices"].items():
        if vertex["building"]:
            continue
        if any(board["vertices"].get(n, {}).get("building")
               for n in vertex["neighbors"]["vertices"]):
            continue
        return key
    return None


def _legal_edge_for(board, vertex_key):
    for key, edge in board["edges"].items():
        if not edge["road"] and vertex_key in edge["neighbors"]["vertices"]:
            return key
    return None


def _click_edge(player, edge_key):
    info = player.page.evaluate(CLICK_HELPERS)
    pos = info["layout"]["edgePositions"][edge_key]
    mid_x = (pos["x1"] + pos["x2"]) / 2
    mid_y = (pos["y1"] + pos["y2"]) / 2
    point = player.page.evaluate(
        """([vx, vy, ox, oy]) => {
            const canvas = document.getElementById('board-canvas');
            const rect = canvas.getBoundingClientRect();
            const p0 = window.BoardRenderer.clientToBoard(canvas, rect.left, rect.top);
            const p1 = window.BoardRenderer.clientToBoard(canvas, rect.left + 100, rect.top + 100);
            const sx = 100 / (p1.x - p0.x);
            const sy = 100 / (p1.y - p0.y);
            return {
                x: rect.left + (vx + ox - p0.x) * sx,
                y: rect.top + (vy + oy - p0.y) * sy,
            };
        }""",
        [mid_x, mid_y, info["layout"]["offsetX"], info["layout"]["offsetY"]],
    )
    player.page.mouse.click(point["x"], point["y"])


def _click_hex(player, hex_key):
    info = player.page.evaluate(CLICK_HELPERS)
    pos = info["layout"]["hexPositions"][hex_key]
    point = player.page.evaluate(
        """([vx, vy, ox, oy]) => {
            const canvas = document.getElementById('board-canvas');
            const rect = canvas.getBoundingClientRect();
            const p0 = window.BoardRenderer.clientToBoard(canvas, rect.left, rect.top);
            const p1 = window.BoardRenderer.clientToBoard(canvas, rect.left + 100, rect.top + 100);
            const sx = 100 / (p1.x - p0.x);
            const sy = 100 / (p1.y - p0.y);
            return {
                x: rect.left + (vx + ox - p0.x) * sx,
                y: rect.top + (vy + oy - p0.y) * sy,
            };
        }""",
        [pos["x"], pos["y"], info["layout"]["offsetX"], info["layout"]["offsetY"]],
    )
    player.page.mouse.click(point["x"], point["y"])


def _resolve_robber_if_needed(actor):
    """A 7 blocks the turn until the robber moves - play it, as a player would."""
    board = actor.page.evaluate("() => window.__catanDebug.getBoard()")
    if not board.get("must_move_robber"):
        return False
    target = next(
        key for key, hex_data in board["hexes"].items()
        if hex_data["type"] not in ("ocean", "desert") and key != board.get("robber_hex")
    )
    _click_hex(actor, target)
    actor.page.wait_for_function(
        "() => window.__catanDebug.getBoard().must_move_robber === false", timeout=5000
    )
    return True


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

            vertex = _legal_setup_vertex(board)
            assert vertex, "no legal vertex left during setup"

            actor.page.click("#place-settlement-btn")
            _click_vertex(actor, vertex)
            actor.page.wait_for_function(
                "key => (window.__catanDebug.getBoard().vertices[key] || {}).building",
                arg=vertex, timeout=5000,
            )
            placed += 1

            board = actor.page.evaluate("() => window.__catanDebug.getBoard()")
            edge = _legal_edge_for(board, vertex)
            assert edge, "no legal road next to the settlement just placed"
            actor.page.click("#place-road-btn")
            _click_edge(actor, edge)
            actor.page.wait_for_function(
                "key => (window.__catanDebug.getBoard().edges[key] || {}).road",
                arg=edge, timeout=5000,
            )

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
        _resolve_robber_if_needed(actor)

    def test_the_turn_can_be_advanced(self, table):
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}
        board = alice.page.evaluate("() => window.__catanDebug.getBoard()")
        before = board["current_player"]

        actor = by_name[before]
        _resolve_robber_if_needed(actor)
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
