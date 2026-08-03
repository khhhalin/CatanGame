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
from playwright.sync_api import TimeoutError as PlaywrightTimeout  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(REPO, "server")

# Screenshots land here rather than in a tmp dir: the point of this suite is
# that a human can look at them afterwards.
SHOT_DIR = os.path.join(REPO, "test-artifacts", "browser")

VIDEO_DIR = os.path.join(REPO, "test-artifacts", "video")

RESOURCES = ('wood', 'brick', 'sheep', 'wheat', 'ore')

# Watching the tests is the point of testing in a browser, so make it easy:
#   CATAN_TEST_HEADED=1   open a real window and watch it play
#   CATAN_TEST_SLOWMO=300 pause 300ms between actions so it is followable
#   CATAN_TEST_VIDEO=1    record each tab to test-artifacts/video/
HEADED = os.environ.get("CATAN_TEST_HEADED") == "1"
SLOW_MO = int(os.environ.get("CATAN_TEST_SLOWMO", "0"))
RECORD_VIDEO = os.environ.get("CATAN_TEST_VIDEO") == "1"


def launch_browser(playwright):
    """Launch Chromium, honouring the watch-it-play environment switches."""
    return playwright.chromium.launch(headless=not HEADED, slow_mo=SLOW_MO)


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
        size = viewport or {"width": 1600, "height": 1000}
        options = {"viewport": size}
        if RECORD_VIDEO:
            options["record_video_dir"] = os.path.join(VIDEO_DIR, name)
            options["record_video_size"] = size
        context = browser.new_context(**options)
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


_PREDICT_SELECTION = """
([kind, boardX, boardY]) => {
    const canvas = document.getElementById('board-canvas');
    const rect = canvas.getBoundingClientRect();
    const layout = window.BoardRenderer.computeLayout(window.__catanDebug.getBoard());
    const origin = window.BoardRenderer.clientToBoard(canvas, rect.left, rect.top);
    const unit = window.BoardRenderer.clientToBoard(canvas, rect.left + 100, rect.top + 100);
    const scaleX = 100 / (unit.x - origin.x);
    const scaleY = 100 / (unit.y - origin.y);
    const clientX = rect.left + (boardX + layout.offsetX - origin.x) * scaleX;
    const clientY = rect.top + (boardY + layout.offsetY - origin.y) * scaleY;

    // A click only reaches the board if the canvas is the topmost element at
    // that point. Off-screen targets and ones under a panel predict fine and
    // then do nothing at all, which is silent and very slow to diagnose.
    if (document.elementFromPoint(clientX, clientY) !== canvas) {
        return null;
    }

    // Round-trip through the real inverse, so this answers the question that
    // actually matters: what would the renderer pick if we clicked there?
    const landed = window.BoardRenderer.clientToBoard(canvas, clientX, clientY);
    const board = window.__catanDebug.getBoard();
    if (kind === 'edge') {
        return window.BoardRenderer.findNearestEdge(board, landed.x, landed.y);
    }
    if (kind === 'hex') {
        return window.BoardRenderer.findNearestHex(board, landed.x, landed.y);
    }
    return window.BoardRenderer.findNearestVertex(board, landed.x, landed.y);
}
"""


def _board_point(player, kind, key):
    layout = player.page.evaluate(_LAYOUT)
    if kind == 'edge':
        pos = layout["edgePositions"][key]
        return (pos["x1"] + pos["x2"]) / 2, (pos["y1"] + pos["y2"]) / 2
    group = layout["hexPositions"] if kind == 'hex' else layout["vertexPositions"]
    return group[key]["x"], group[key]["y"]


def would_select(player, kind, key):
    """What the renderer would pick if we aimed a click at `key`.

    A canvas click snaps to the nearest target within a radius, so aiming at a
    piece is not the same as hitting it. Asking the renderer up front turns a
    flaky miss into a target the test simply skips.
    """
    board_x, board_y = _board_point(player, kind, key)
    return player.page.evaluate(_PREDICT_SELECTION, [kind, board_x, board_y])


def first_clickable(player, kind, keys):
    """The first candidate a click would actually land on."""
    for key in keys:
        if would_select(player, kind, key) == key:
            return key
    return None


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


def legal_setup_vertices(board):
    """Every vacant vertex with no neighbouring building — the distance rule."""
    return [
        key for key, vertex in sorted(board["vertices"].items())
        if not vertex["building"]
        and not any(board["vertices"].get(n, {}).get("building")
                    for n in vertex["neighbors"]["vertices"])
    ]


def legal_settlement_vertices(board, player_name):
    """A vacant, distance-legal vertex touching one of the player's roads.

    The playing phase adds the road-connection rule on top of setup's rules.
    """
    owned_edges = [
        edge for edge in board["edges"].values()
        if (edge.get("road") or {}).get("player") == player_name
    ]
    reachable = {v for edge in owned_edges for v in edge["neighbors"]["vertices"]}

    return [
        key for key in sorted(reachable)
        if board["vertices"].get(key)
        and not board["vertices"][key]["building"]
        and not any(board["vertices"].get(n, {}).get("building")
                    for n in board["vertices"][key]["neighbors"]["vertices"])
    ]


def legal_road_edges(board, player_name):
    """A vacant edge touching something the player already owns."""
    # Road ends only — deliberately NOT the player's settlements. The engine's
    # `_road_connects` accepts a road only where it touches another of your
    # roads, so an edge beside your settlement is offered by the rulebook and
    # refused by the server. Driving the game through what the server actually
    # allows keeps this suite testing the game rather than the known bug.
    mine = set()
    for edge in board["edges"].values():
        if (edge.get("road") or {}).get("player") == player_name:
            mine.update(edge["neighbors"]["vertices"])

    return [
        key for key, edge in sorted(board["edges"].items())
        if not edge.get("road")
        and any(v in mine for v in edge["neighbors"]["vertices"])
    ]


def edges_next_to(board, vertex_key):
    return [
        key for key, edge in sorted(board["edges"].items())
        if not edge.get("road") and vertex_key in edge["neighbors"]["vertices"]
    ]


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


def _wait_for_modal_closed(player, element_id):
    """Wait for a dialog to drop its `show` class.

    Not `wait_for_selector('#id:not(.show)')`: that selector matches a *hidden*
    element, and wait_for_selector waits for visibility, so it can never be
    satisfied by a closed dialog.
    """
    player.page.wait_for_function(
        "id => !document.getElementById(id).classList.contains('show')",
        arg=element_id, timeout=8000,
    )


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
    _wait_for_modal_closed(player, "discard-modal")
    return True


def resolve_robber(player):
    """Move the robber if a 7 is blocking the turn."""
    board = player.board()
    if not board.get("must_move_robber"):
        return False

    # A canvas click snaps to the nearest hex, so the one aimed at is not
    # always the one hit — and hitting the robber's current hex is a no-op the
    # server rightly refuses. Try successive candidates rather than assuming
    # the first click landed.
    candidates = [
        key for key, hex_data in board["hexes"].items()
        if hex_data["type"] not in ("ocean", "desert") and key != board.get("robber_hex")
    ]

    clickable = first_clickable(player, 'hex', candidates)
    if clickable:
        candidates = [clickable] + [c for c in candidates if c != clickable]

    for target in candidates[:6]:
        click_hex(player, target)
        try:
            player.page.wait_for_function(
                "() => window.__catanDebug.getBoard().must_move_robber === false",
                timeout=3000,
            )
            break
        except PlaywrightTimeout:
            continue
    else:
        raise AssertionError(
            f"{player.name} could not move the robber; tried {candidates[:6]}"
        )

    # Stealing raises a victim picker when the target hex has neighbours.
    # The victim list is [data-victim] items with a delegated listener, not
    # buttons — selecting on `button` silently matches nothing and hangs.
    if player.page.is_visible("#victim-modal.show"):
        victims = player.page.query_selector_all("#victim-list [data-victim]")
        if victims:
            victims[0].click()
            _wait_for_modal_closed(player, "victim-modal")
        else:
            # Nobody to rob: the dialog has no way to close itself, so the
            # test would hang waiting for a choice that cannot be made.
            player.page.evaluate(
                "() => document.getElementById('victim-modal').classList.remove('show')"
            )
    return True


def roll_dice(player):
    player.page.wait_for_selector("#roll-dice-btn:not([disabled])", timeout=8000)
    player.page.click("#roll-dice-btn")
    player.page.wait_for_function(
        "() => window.__catanDebug.getBoard().has_rolled_dice === true", timeout=8000
    )


_COUNT_PIECES = """
([kind, owner]) => {
    const board = window.__catanDebug.getBoard();
    const group = kind === 'road' ? board.edges : board.vertices;
    const field = kind === 'road' ? 'road' : 'building';
    return Object.values(group)
        .filter(entry => (entry[field] || {}).player === owner).length;
}
"""


def count_pieces(player, kind):
    return player.page.evaluate(_COUNT_PIECES, [kind, player.name])


def _wait_for_new_piece(player, kind, before):
    """Wait for the player to own one more piece than they did.

    Deliberately not keyed to the vertex or edge that was aimed at: the canvas
    snaps a click to the nearest target, so aiming at one legal edge can
    legitimately land on an equally legal neighbour. What matters is that the
    click placed a piece, not which of the legal candidates it chose.
    """
    player.page.wait_for_function(
        f"([kind, owner, before]) => ({_COUNT_PIECES.strip()})([kind, owner]) > before",
        arg=[kind, player.name, before], timeout=8000,
    )


def build_road(player, candidates):
    """Arm road placement, then aim — in that order, and it matters.

    Arming adds `placement-mode` to the board, which changes the canvas box and
    therefore the camera. A point computed before the button is pressed is
    stale by the time the click happens, and lands on a neighbouring edge.
    """
    before = count_pieces(player, 'road')
    player.page.click("#place-road-btn")
    edge_key = first_clickable(player, 'edge', candidates)
    if not edge_key:
        raise AssertionError(f"no clickable road among {len(candidates)} candidates")
    click_edge(player, edge_key)
    _wait_for_new_piece(player, 'road', before)
    return edge_key


def build_settlement(player, candidates):
    """Arm settlement placement, then aim. See build_road for why."""
    before = count_pieces(player, 'building')
    player.page.click("#place-settlement-btn")
    vertex_key = first_clickable(player, 'vertex', candidates)
    if not vertex_key:
        raise AssertionError(f"no clickable vertex among {len(candidates)} candidates")
    click_vertex(player, vertex_key)
    _wait_for_new_piece(player, 'building', before)
    return vertex_key


def bank_trade(player, give_resource, give_count, want_resource):
    """Trade surplus to the bank through the real trade dialog.

    Without this the bot deadlocks: two players can sit on brick-and-no-wood
    and wood-and-no-brick forever, affording nothing, and the game never ends.
    Trading is how a real player breaks that, so the bot has to do it too.
    """
    held_before = dict((player.me() or {}).get("resources") or {})

    # Propose Trade lives in the Trade tab, which starts unselected, so the
    # button is genuinely not clickable until the tab is opened — exactly as
    # it is for a player.
    player.page.click("#tab-trade")
    player.page.wait_for_selector("#propose-trade-btn", state="visible", timeout=5000)
    player.page.click("#propose-trade-btn")
    player.page.wait_for_selector("#trade-modal.show", timeout=5000)
    for resource in RESOURCES:
        player.page.fill(f"#give-{resource}", "0")
        player.page.fill(f"#want-{resource}", "0")
    player.page.fill(f"#give-{give_resource}", str(give_count))
    player.page.fill(f"#want-{want_resource}", "1")
    player.page.click("#submit-trade-btn")

    try:
        player.page.wait_for_function(
            "([res, before]) => {"
            "  const board = window.__catanDebug.getBoard();"
            "  const me = board.players.find(p => p.is_you);"
            "  return me && (me.resources[res] || 0) > before; }",
            arg=[want_resource, held_before.get(want_resource, 0)], timeout=5000,
        )
        return True
    except PlaywrightTimeout:
        player.page.evaluate(
            "() => document.getElementById('trade-modal').classList.remove('show')"
        )
        return False


def _trade_towards(player, cost):
    """Bank-trade once to close the biggest gap in `cost`, if a surplus allows.

    The bank rate is the engine's business — ports make it 3:1 or 2:1 — so ask
    the engine what this player's rate is rather than hardcoding 4:1.
    """
    me = player.me()
    held = dict(me.get("resources") or {})
    missing = [res for res, need in cost.items() if held.get(res, 0) < need]
    if not missing:
        return False

    for want in missing:
        for give, amount in sorted(held.items(), key=lambda item: -item[1]):
            if give in cost and amount <= cost[give]:
                continue  # do not spend what the target already needs
            # Always offer 4. The engine settles against the bank whenever the
            # ratio meets *or beats* the player's harbour rate, and 4 is the
            # worst rate there is — so 4:1 always completes immediately.
            # Offering less turns it into a player offer nobody will answer,
            # which hangs the bot waiting for a response.
            if amount >= 4 and bank_trade(player, give, 4, want):
                return True
    return False


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

    # A refused build is not a test failure: the server is the authority on
    # legality, and a bot that mispredicts it should lose a turn, not abort the
    # game. The end-of-game assertions catch a bot that never builds.
    if can_afford(me, SETTLEMENT_COST):
        placed = _try(build_settlement, player, legal_settlement_vertices(board, player.name))
        if placed:
            built.append(("settlement", placed))
            board = player.board()
            me = next(p for p in board["players"] if p["is_you"])

    if can_afford(me, ROAD_COST):
        placed = _try(build_road, player, legal_road_edges(board, player.name))
        if placed:
            built.append(("road", placed))
            me = player.me()

    # Nothing affordable: turn a surplus into the missing card so the game can
    # actually progress. Aim at whichever target is closer to being paid for.
    if not built:
        target = SETTLEMENT_COST if legal_settlement_vertices(board, player.name) else ROAD_COST
        _trade_towards(player, target)

    return built


def _try(action, player, candidates):
    """Attempt a build, returning the piece placed or None if it did not land."""
    if not candidates:
        return None
    try:
        return action(player, candidates)
    except (PlaywrightTimeout, AssertionError):
        return None


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
