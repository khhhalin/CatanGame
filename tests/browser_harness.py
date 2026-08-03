"""Shared machinery for driving the game in a real browser.

`test_browser_playthrough.py` proved the layers meet correctly. This harness
exists so a *whole game* can be played the same way — through the canvas and
the real buttons — without every suite re-deriving the canvas click maths.

Nothing here asserts. Suites assert; this only drives and observes.
"""

import os
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright", reason="playwright is not installed")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(REPO, "server")

# Screenshots land here rather than in a tmp dir: the point of this suite is
# that a human can look at them afterwards.
SHOT_DIR = os.path.join(REPO, "test-artifacts", "browser")

RESOURCES = ('wood', 'brick', 'sheep', 'wheat', 'ore')


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(data_dir):
    """A real gunicorn server on its own port and its own data directory.

    Returns (process, url). The caller owns shutdown.
    """
    port = free_port()
    env = dict(
        os.environ,
        SECRET_KEY="browser-test",
        CATAN_DATA_DIR=str(data_dir),
        # Not TestingConfig: its 1s dice timer and 2s round timer let the turn
        # watchdog auto-play faster than a browser can click, which silently
        # invalidates any assertion about who did what.
        CATAN_CONFIG="development",
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "-w", "1", "--threads", "50",
         "-b", f"127.0.0.1:{port}", "wsgi:app"],
        cwd=SERVER_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("server never came up")

    return proc, f"http://127.0.0.1:{port}"


def stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


class Player:
    """One browser tab, with its console errors collected."""

    def __init__(self, browser, url, name, viewport=None):
        self.name = name
        self.errors = []
        context = browser.new_context(viewport=viewport or {"width": 1600, "height": 1000})
        self.page = context.new_page()
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

    def board(self):
        return self.page.evaluate("() => window.__catanDebug.getBoard()")

    def me(self):
        board = self.board()
        return next((p for p in board["players"] if p["is_you"]), None)

    def notices(self):
        return self.page.eval_on_selector_all(
            "#notice-region *", "els => els.map(e => e.textContent)"
        )

    def noisy_errors(self):
        """Console errors worth failing on. A missing favicon is not one."""
        return [e for e in self.errors if "favicon" not in e.lower()]

    def shot(self, label):
        """Save a full-page screenshot and return its path."""
        os.makedirs(SHOT_DIR, exist_ok=True)
        path = os.path.join(SHOT_DIR, f"{label}.png")
        self.page.screenshot(path=path, full_page=False)
        return path


# --- Canvas click maths ---------------------------------------------------
#
# `clientToBoard` is affine, so rather than re-deriving the camera transform
# here we sample it at two points and invert. That keeps the tests correct if
# the camera implementation changes underneath them.

_TO_CLIENT = """
([boardX, boardY, offsetX, offsetY]) => {
    const canvas = document.getElementById('board-canvas');
    const rect = canvas.getBoundingClientRect();
    const origin = window.BoardRenderer.clientToBoard(canvas, rect.left, rect.top);
    const unit = window.BoardRenderer.clientToBoard(canvas, rect.left + 100, rect.top + 100);
    const scaleX = 100 / (unit.x - origin.x);
    const scaleY = 100 / (unit.y - origin.y);
    return {
        x: rect.left + (boardX + offsetX - origin.x) * scaleX,
        y: rect.top + (boardY + offsetY - origin.y) * scaleY,
    };
}
"""

_LAYOUT = """
() => {
    const board = window.__catanDebug.getBoard();
    return window.BoardRenderer.computeLayout(board);
}
"""


def _click_board_point(player, board_x, board_y, layout):
    point = player.page.evaluate(
        _TO_CLIENT, [board_x, board_y, layout["offsetX"], layout["offsetY"]]
    )
    player.page.mouse.click(point["x"], point["y"])


def click_vertex(player, vertex_key):
    layout = player.page.evaluate(_LAYOUT)
    pos = layout["vertexPositions"][vertex_key]
    _click_board_point(player, pos["x"], pos["y"], layout)


def click_edge(player, edge_key):
    layout = player.page.evaluate(_LAYOUT)
    pos = layout["edgePositions"][edge_key]
    _click_board_point(player, (pos["x1"] + pos["x2"]) / 2, (pos["y1"] + pos["y2"]) / 2, layout)


def click_hex(player, hex_key):
    layout = player.page.evaluate(_LAYOUT)
    pos = layout["hexPositions"][hex_key]
    _click_board_point(player, pos["x"], pos["y"], layout)


# --- Reading the board ----------------------------------------------------


def legal_setup_vertex(board):
    """A vacant vertex with no neighbouring building — the distance rule."""
    for key, vertex in board["vertices"].items():
        if vertex["building"]:
            continue
        if any(board["vertices"].get(n, {}).get("building")
               for n in vertex["neighbors"]["vertices"]):
            continue
        return key
    return None


def legal_settlement_vertex(board, player_name):
    """A vacant, distance-legal vertex touching one of the player's roads.

    The playing phase adds the road-connection rule on top of setup's rules.
    """
    owned_edges = [
        edge for edge in board["edges"].values()
        if (edge.get("road") or {}).get("player") == player_name
    ]
    reachable = {v for edge in owned_edges for v in edge["neighbors"]["vertices"]}

    for key in sorted(reachable):
        vertex = board["vertices"].get(key)
        if not vertex or vertex["building"]:
            continue
        if any(board["vertices"].get(n, {}).get("building")
               for n in vertex["neighbors"]["vertices"]):
            continue
        return key
    return None


def legal_road_edge(board, player_name):
    """A vacant edge touching something the player already owns."""
    mine = set()
    for key, vertex in board["vertices"].items():
        if (vertex.get("building") or {}).get("player") == player_name:
            mine.add(key)
    for edge in board["edges"].values():
        if (edge.get("road") or {}).get("player") == player_name:
            mine.update(edge["neighbors"]["vertices"])

    for key, edge in sorted(board["edges"].items()):
        if edge.get("road"):
            continue
        if any(v in mine for v in edge["neighbors"]["vertices"]):
            return key
    return None


def edge_next_to(board, vertex_key):
    for key, edge in sorted(board["edges"].items()):
        if not edge.get("road") and vertex_key in edge["neighbors"]["vertices"]:
            return key
    return None


def can_afford(player_data, cost):
    held = player_data.get("resources") or {}
    return all(held.get(res, 0) >= need for res, need in cost.items())


ROAD_COST = {"wood": 1, "brick": 1}
SETTLEMENT_COST = {"wood": 1, "brick": 1, "wheat": 1, "sheep": 1}
CITY_COST = {"wheat": 2, "ore": 3}


# --- Playing a turn -------------------------------------------------------
#
# Every step below goes through the same buttons and canvas a person uses.
# Nothing here emits a socket event directly: an assertion is only worth
# something if the path it exercised is the path a player takes.


def resolve_discard(player):
    """Answer the discard modal if a 7 raised it for this tab."""
    if not player.page.is_visible("#discard-modal.show"):
        return False

    owed = int(player.page.inner_text("#discard-amount"))
    held = dict((player.me() or {}).get("resources") or {})

    for resource in RESOURCES:
        if owed <= 0:
            break
        give = min(owed, held.get(resource, 0))
        if give:
            player.page.fill(f"#discard-{resource}", str(give))
            owed -= give

    player.page.click("#submit-discard-btn")
    player.page.wait_for_selector("#discard-modal:not(.show)", timeout=5000)
    return True


def resolve_robber(player):
    """Move the robber if a 7 is blocking the turn."""
    board = player.board()
    if not board.get("must_move_robber"):
        return False

    target = next(
        key for key, hex_data in board["hexes"].items()
        if hex_data["type"] not in ("ocean", "desert") and key != board.get("robber_hex")
    )
    click_hex(player, target)
    player.page.wait_for_function(
        "() => window.__catanDebug.getBoard().must_move_robber === false", timeout=8000
    )

    # Stealing raises a victim picker when the target hex has neighbours.
    if player.page.is_visible("#victim-modal.show"):
        buttons = player.page.query_selector_all("#victim-modal button")
        if buttons:
            buttons[0].click()
        player.page.wait_for_selector("#victim-modal:not(.show)", timeout=5000)
    return True


def roll_dice(player):
    player.page.wait_for_selector("#roll-dice-btn:not([disabled])", timeout=8000)
    player.page.click("#roll-dice-btn")
    player.page.wait_for_function(
        "() => window.__catanDebug.getBoard().has_rolled_dice === true", timeout=8000
    )


def build_road(player, edge_key):
    player.page.click("#place-road-btn")
    click_edge(player, edge_key)
    player.page.wait_for_function(
        "key => (window.__catanDebug.getBoard().edges[key] || {}).road",
        arg=edge_key, timeout=8000,
    )


def build_settlement(player, vertex_key):
    player.page.click("#place-settlement-btn")
    click_vertex(player, vertex_key)
    player.page.wait_for_function(
        "key => (window.__catanDebug.getBoard().vertices[key] || {}).building",
        arg=vertex_key, timeout=8000,
    )


def spend_what_you_can(player):
    """Buy whatever this hand affords, preferring settlements over roads.

    A settlement is a victory point outright; roads only pay off through
    Longest Road. Both are needed to finish a game, so try both.
    """
    built = []

    board = player.board()
    me = next((p for p in board["players"] if p["is_you"]), None)
    if me is None:
        return built

    if can_afford(me, SETTLEMENT_COST):
        vertex = legal_settlement_vertex(board, player.name)
        if vertex:
            build_settlement(player, vertex)
            built.append(("settlement", vertex))
            board = player.board()
            me = next(p for p in board["players"] if p["is_you"])

    if can_afford(me, ROAD_COST):
        edge = legal_road_edge(board, player.name)
        if edge:
            build_road(player, edge)
            built.append(("road", edge))

    return built


def end_turn(player):
    player.page.wait_for_selector("#next-turn-btn:not([disabled])", timeout=10000)
    before = player.board()["current_player"]
    player.page.click("#next-turn-btn")
    player.page.wait_for_function(
        "prev => window.__catanDebug.getBoard().current_player !== prev",
        arg=before, timeout=8000,
    )


def play_one_turn(actor, everyone):
    """Roll, settle any 7, build what the hand allows, then pass.

    Returns what was built, so a caller can tell progress from a stalemate.
    """
    resolve_robber(actor)
    if not actor.board().get("has_rolled_dice"):
        roll_dice(actor)

    # A 7 makes *every* over-stocked tab discard, not just the roller, and the
    # turn cannot advance until they all have.
    for player in everyone:
        resolve_discard(player)

    resolve_robber(actor)
    built = spend_what_you_can(actor)
    end_turn(actor)
    return built
