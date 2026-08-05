"""Shared machinery for driving the game in a real browser.

`test_browser_playthrough.py` proved the layers meet correctly. This harness
exists so a *whole game* can be played the same way — through the canvas and
the real buttons — without every suite re-deriving the canvas click maths.

Nothing here asserts. Suites assert; this only drives and observes.

Take the browser from `browser_session()` and never from a `sync_playwright()`
of your own. One browser process is shared by the whole run, and the sync
driver holds an asyncio loop open for as long as it is running - so a second
driver anywhere in the same process raises "please use the Async API" and
every test in that file errors at setup.
"""

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest

pytest.importorskip("playwright", reason="playwright is not installed")
from playwright.sync_api import TimeoutError as PlaywrightTimeout  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(REPO, "server")

# Screenshots land here rather than in a tmp dir: the point of this suite is
# that a human can look at them afterwards.
SHOT_DIR = os.path.join(REPO, "test-artifacts", "browser")

VIDEO_DIR = os.path.join(REPO, "test-artifacts", "video")

# Each test server's own log. See start_server for why it is not a pipe.
LOG_DIR = os.path.join(REPO, "test-artifacts", "server-logs")

RESOURCES = ('wood', 'brick', 'sheep', 'wheat', 'ore')

# Watching the tests is the point of testing in a browser, so make it easy:
#   CATAN_TEST_HEADED=1   open a real window and watch it play
#   CATAN_TEST_SLOWMO=300 pause 300ms between actions so it is followable
#   CATAN_TEST_VIDEO=1    record each tab to test-artifacts/video/
HEADED = os.environ.get("CATAN_TEST_HEADED") == "1"
SLOW_MO = int(os.environ.get("CATAN_TEST_SLOWMO", "0"))
RECORD_VIDEO = os.environ.get("CATAN_TEST_VIDEO") == "1"

# The owner plays in Zen, which is Firefox-based, but every suite here has only
# ever run in Chromium. This switch lets the same suites be pointed at Gecko:
#   CATAN_TEST_BROWSER=firefox
# The default stays chromium deliberately - the existing runs are the baseline
# and must keep behaving exactly as they did.
BROWSER = os.environ.get("CATAN_TEST_BROWSER", "chromium")


def launch_browser(playwright, browser=None):
    """Launch the configured engine, honouring the watch-it-play switches.

    `browser` overrides CATAN_TEST_BROWSER, so a cross-browser suite can pin
    itself to Firefox without the whole run being switched over.
    """
    name = browser or BROWSER
    engine = getattr(playwright, name, None)
    if engine is None:
        raise ValueError(f"unknown browser {name!r}; expected chromium or firefox")
    return engine.launch(headless=not HEADED, slow_mo=SLOW_MO)


# One driver and one browser process for the whole run, keyed by engine name.
# Launching Chromium costs about a second and every suite here used to pay it
# again: twenty-two modules, twenty-two launches. A browser holds no game state
# - the servers do, and those stay per-module - so sharing it is invisible to
# the tests as long as each module's contexts are closed after it, which
# `browser_session` does.
_DRIVER = None
_ENGINES = {}


def _shared_engine(name):
    global _DRIVER
    if _DRIVER is None:
        _DRIVER = sync_playwright().start()
        atexit.register(_shutdown_shared_browsers)
    if name not in _ENGINES:
        _ENGINES[name] = launch_browser(_DRIVER, name)
    return _ENGINES[name]


def _shutdown_shared_browsers():
    global _DRIVER
    for engine in _ENGINES.values():
        try:
            engine.close()
        except Exception:  # noqa: BLE001 - interpreter teardown, nothing to report to
            pass
    _ENGINES.clear()
    if _DRIVER is not None:
        try:
            _DRIVER.stop()
        except Exception:  # noqa: BLE001
            pass
        _DRIVER = None


@contextmanager
def browser_session(browser=None):
    """The run's shared browser, with this module's tabs closed on the way out.

    A drop-in replacement for `with sync_playwright() as p: launch_browser(p)`.
    Every context opened inside the block is closed at the end of it, so tabs do
    not accumulate across modules the way they would on a browser nobody ever
    closes - and a recorded video is still flushed, which only happens on
    context close.
    """
    engine = _shared_engine(browser or BROWSER)
    before = {id(context) for context in engine.contexts}
    try:
        yield engine
    finally:
        for context in list(engine.contexts):
            if id(context) not in before:
                try:
                    context.close()
                except Exception:  # noqa: BLE001 - a crashed tab is not this test's news
                    pass


def next_frame(page):
    """Return once the render loop has painted what the last input changed.

    Two frames, because a change made during one frame's callbacks is drawn in
    the next. This is the honest version of a fixed settle: it is exact on a
    fast machine and still correct on a loaded one, where a 250ms sleep is
    merely a guess in both directions.
    """
    page.evaluate(
        "() => new Promise(resolve =>"
        "    requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )


_SETTLE_TRANSITIONS = """
async cap => {
    const finite = document.getAnimations().filter(animation => {
        const timing = animation.effect && animation.effect.getComputedTiming();
        return timing && timing.iterations !== Infinity;
    });
    await Promise.race([
        Promise.all(finite.map(animation => animation.finished.catch(() => {}))),
        new Promise(resolve => setTimeout(resolve, cap)),
    ]);
    await new Promise(resolve =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)));
}
"""


def wait_for_transitions(page, cap_ms=1000):
    """Return once every running CSS transition has finished.

    Sampling a colour mid-transition reads a value that exists in neither the
    before state nor the after one - which is what the contrast sweep's fixed
    settle was for. Asking the animations themselves is exact where a guess is
    both too long and too short; the cap is only there so a looping animation
    cannot hang the sweep.
    """
    page.evaluate(_SETTLE_TRANSITIONS, cap_ms)


def wait_for_rule(player, rule_id, value, timeout=8000):
    """Wait for the server to echo a rule change back to this tab.

    The picker sends on `change` and the table is only really set once the
    server has answered - which is the condition a fixed sleep after every
    tick was standing in for.
    """
    player.page.wait_for_function(
        "([id, want]) => {"
        "  const selected = window.__catanDebug.getRules().selected;"
        "  return String(selected[id]) === String(want); }",
        arg=[rule_id, value], timeout=timeout,
    )


def reveal_rule(player, rule_id, timeout=10000):
    """Wait for one rule's control to exist, and open the group it sits in.

    The groups are `<details>`, so a collapsed section has to be opened before
    Playwright will treat the control as visible - and the picker is not there
    to be opened the moment `join()` returns. `#user-screen` is un-hidden
    synchronously in the Join click handler, while `request_rules` is still in
    flight, so the rows arrive one socket round trip later.

    Waiting is what makes that safe. A one-shot `getElementById` finds nothing,
    silently leaves the `<details>` shut, and the fill that follows spends its
    whole 30-second timeout on a control nobody will ever open -
    `scroll_into_view_if_needed` does not object, because it does not wait for
    visibility. On an idle machine the round trip usually wins the race; under
    the load of the full browser suite it lost it every time, and
    `test_browser_six_players.py` reported six setup errors that read as
    cross-suite interference.
    """
    player.page.wait_for_function(
        "id => { const el = document.getElementById(`rule-${id}`);"
        "        if (!el) { return false; }"
        "        const group = el.closest('details');"
        "        if (group) { group.open = true; }"
        "        return true; }",
        arg=rule_id, timeout=timeout,
    )


# Deliberately `request_log` and not `request_state`: a resync answers with a
# whole board, and a board payload is not inert. It runs the client's
# placement bookkeeping, which is what decides whether an armed build mode
# survives - so using one here would change the thing being observed. Asking
# for the log after its last entry replies with an empty list and touches
# nothing at all.
_ASK_FOR_AN_EMPTY_ANSWER = """
async () => {
    const socket = (await import('/static/js/socket.js')).socket;
    if (window.__pings === undefined) {
        window.__pings = 0;
        socket.on('log_history', () => { window.__pings += 1; });
    }
    const before = window.__pings;
    socket.emit('request_log', { after_id: 2000000000 });
    return before;
}
"""


def server_round_trip(player, timeout=3000, attempts=4):
    """Wait out one full trip to the server and back.

    This is what "give the server the time it would have needed to answer an
    emit" means, said exactly. Socket.io delivers in order, so once the answer
    to a question asked afterwards is in, anything sent before it has already
    been handled.

    Better than a fixed sleep in both directions: it is a few milliseconds on
    an idle machine, and on a loaded one it actually waits - where a 500ms
    sleep would let a "nothing happened" assertion pass because the server had
    not got round to the thing yet. These are rate limited to about one a
    second, so a dropped ask is retried rather than treated as a failure.
    """
    for _ in range(attempts):
        before = player.page.evaluate(_ASK_FOR_AN_EMPTY_ANSWER)
        try:
            player.page.wait_for_function(
                "before => window.__pings > before", arg=before, timeout=timeout,
            )
            return
        except PlaywrightTimeout:
            continue
    raise AssertionError(f"{player.name}: the server never answered")


def wait_for_rules(player, rules, timeout=8000):
    """Wait for the server to echo a whole set of rule changes back."""
    player.page.wait_for_function(
        "want => {"
        "  const selected = window.__catanDebug.getRules().selected;"
        "  return Object.entries(want).every("
        "      ([id, value]) => String(selected[id]) === String(value)); }",
        arg=dict(rules), timeout=timeout,
    )


def wait_for_preset(player, preset_id, timeout=8000):
    """Wait for every rule a preset ticks to come back from the server.

    The preset button sends one message and the table changes a dozen rules, so
    "the click landed" is only true once the last of them has been echoed. Read
    from the catalogue the server sent rather than from a copy here: a preset
    that gained a rule would otherwise be waited on incompletely.
    """
    player.page.wait_for_function(
        "id => {"
        "  const state = window.__catanDebug.getRules();"
        "  const preset = state.presets.find(entry => entry.id === id);"
        "  if (!preset) { return false; }"
        "  return Object.entries(preset.rules || {}).every("
        "      ([rule, value]) => String(state.selected[rule]) === String(value)); }",
        arg=preset_id, timeout=timeout,
    )


_PAINTED_PIXELS = """
() => {
    const canvas = document.getElementById('board-canvas');
    if (!canvas || !canvas.width) { return 0; }
    const data = canvas.getContext('2d')
        .getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let i = 3; i < data.length; i += 4) {
        if (data[i] !== 0) { count++; }
    }
    return count;
}
"""


def wait_for_board_painted(player, timeout=10000):
    """Wait until the board has actually been drawn, not merely inserted.

    What the fixed settles after `#game-screen` appeared were standing in for.
    A blank canvas satisfies every DOM assertion, so this is also the only
    honest signal that a screenshot or a pixel comparison has something to look
    at.
    """
    player.page.wait_for_function(
        f"() => ({_PAINTED_PIXELS.strip()})() > 1000", timeout=timeout
    )
    next_frame(player.page)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(data_dir, seed=None, config="development"):
    """A real gunicorn server on its own port and its own data directory.

    Returns (process, url). The caller owns shutdown.

    `config` defaults to development and not TestingConfig: the latter's 1s dice
    timer and 2s round timer let the turn watchdog auto-play faster than a
    browser can click, which silently invalidates any assertion about who did
    what. A suite whose subject *is* the watchdog passes `config="testing"` on
    purpose — there is no other way to make the clocks run out inside a test.
    """
    port = free_port()
    env = dict(
        os.environ,
        SECRET_KEY="browser-test",
        CATAN_DATA_DIR=str(data_dir),
        CATAN_CONFIG=config,
    )
    # A seeded server replays the same board and the same dice every run. A
    # test that plays a whole game is otherwise a coin toss: it passed, then
    # stalled a player short of winning, on identical code.
    if seed is not None:
        env["CATAN_SEED"] = str(seed)
    # The server's own log, to a file rather than a pipe. Nothing reads the
    # pipe, so a long game fills the kernel buffer and the worker blocks inside
    # a log call — a five-minute run had one killed and restarted underneath it,
    # which arrives in the browser as ERR_CONNECTION_REFUSED and in the test as
    # nonsense. A file also leaves the log where a human can read it afterwards.
    os.makedirs(LOG_DIR, exist_ok=True)
    log = open(os.path.join(LOG_DIR, f"server-{port}.log"), "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "-w", "1", "--threads", "50",
         "-b", f"127.0.0.1:{port}", "wsgi:app"],
        cwd=SERVER_DIR, env=env,
        stdout=log, stderr=subprocess.STDOUT, text=True,
        # Its own process group, so stop_server can take the worker down with
        # the master. Killing the master alone leaves the worker holding the
        # port, which is how orphaned gunicorns accumulated for hours.
        start_new_session=True,
    )
    # Closed by stop_server, which is the only thing that knows the run is over.
    proc.log_file = log

    # Poll hard: gunicorn is usually listening within a few hundred
    # milliseconds, and a 100ms interval spent up to half of that waiting for a
    # server that was already up. The deadline, not the interval, is what keeps
    # a wedged boot from hanging the run.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.01)
    else:
        proc.kill()
        raise RuntimeError("server never came up")

    return proc, f"http://127.0.0.1:{port}"


def stop_server(proc):
    """Kill the server outright rather than asking it to retire.

    SIGTERM starts gunicorn's graceful shutdown, which runs to its 30-second
    timeout while a test suite waits. The old code sent it, waited five
    seconds, then killed the process anyway - so every server cost exactly
    five wasted seconds, roughly three minutes across the suite. A test server
    holds nothing worth draining: its data directory is a temp dir.
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log = getattr(proc, "log_file", None)
    if log is not None:
        log.close()


# Personal, per-browser preference: a click places outright instead of raising
# a ✓/✗. It is written straight into localStorage rather than clicked, so it is
# already on for the very first placement a tab makes.
YOLO_STORAGE_KEY = "catan.yoloMode"


class Player:
    """One browser tab, with its console errors collected."""

    def __init__(self, browser, url, name, viewport=None, yolo=False,
                 color_scheme=None):
        self.name = name
        self.errors = []
        # Every helper below has to know which of the two flows this tab is on:
        # waiting for a confirmation that YOLO mode will never raise is a
        # timeout per placement, and a whole game of them is minutes.
        self.yolo = yolo
        size = viewport or {"width": 1600, "height": 1000}
        options = {"viewport": size}
        # The app has no theme control: light and dark come from
        # prefers-color-scheme, so this is the only way to see the dark theme.
        if color_scheme:
            options["color_scheme"] = color_scheme
        if RECORD_VIDEO:
            options["record_video_dir"] = os.path.join(VIDEO_DIR, name)
            options["record_video_size"] = size
        context = browser.new_context(**options)
        if yolo:
            # A statement, not a function expression: an init script is run as
            # source, so an arrow function here would only be defined.
            context.add_init_script(
                f"window.localStorage.setItem('{YOLO_STORAGE_KEY}', '1');"
            )
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


# --- The confirmation a click raises -------------------------------------
#
# A click selects; it no longer places. Every helper below drives the ✓ the
# way a player does, because that is now the default experience — a suite that
# skipped it would be testing a path only YOLO players ever see.


def confirm_placement(player, timeout=3000):
    """Press ✓ on the pending placement. False if nothing was pending."""
    if player.yolo:
        return False
    try:
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=timeout)
    except PlaywrightTimeout:
        return False
    player.page.click("#placement-confirm-yes")
    return True


def cancel_placement(player, timeout=3000):
    """Press ✗ on the pending placement. False if nothing was pending."""
    if player.yolo:
        return False
    try:
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=timeout)
    except PlaywrightTimeout:
        return False
    player.page.click("#placement-confirm-no")
    return True


def confirm_is_showing(player):
    return player.page.is_visible("#placement-confirm:not(.hidden)")


def set_yolo_mode(player, enabled):
    """Flip YOLO mode through the console toggle, as a player would."""
    player.page.set_checked("#yolo-mode-toggle", enabled)
    player.yolo = enabled


def client_point(player, kind, key):
    """Where on screen a vertex, edge or hex is, right now."""
    layout = player.page.evaluate(_LAYOUT)
    board_x, board_y = _board_point(player, kind, key)
    return player.page.evaluate(
        _TO_CLIENT, [board_x, board_y, layout["offsetX"], layout["offsetY"]]
    )


def hover_target(player, kind, key):
    """Rest the cursor over a target, which is what raises the hover ghost."""
    point = client_point(player, kind, key)
    player.page.mouse.move(point["x"], point["y"])
    return point


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
SHIP_COST = {"wood": 1, "sheep": 1}

# How many ships a seafaring bot builds before it starts taking victory points.
STARTING_FLEET = 3


def legal_ship_edges(board, player_name):
    """Vacant sea sides a ship of this player's could be built on.

    Own ships and own buildings only — a road meeting the same intersection
    does not extend a shipping route — and never a side of the hex the pirate
    is sitting on, which it blocks entirely. `sea` is the server's own mask,
    sent on every edge, so the geometry is read rather than re-derived.
    """
    mine = {
        key for key, vertex in board["vertices"].items()
        if (vertex.get("building") or {}).get("player") == player_name
    }
    for edge in board["edges"].values():
        if (edge.get("ship") or {}).get("player") == player_name:
            mine.update(edge["neighbors"]["vertices"])

    pirate = board.get("pirate_hex")
    return [
        key for key, edge in sorted(board["edges"].items())
        if edge.get("sea") and not edge.get("ship") and not edge.get("road")
        and not (pirate and pirate in edge["neighbors"]["hexes"])
        and any(vertex in mine for vertex in edge["neighbors"]["vertices"])
    ]


def open_seafarers_fold(player):
    """Raise the Seafarers fold if it is not already up.

    The chip toggles, so clicking it blind closes a panel a previous step left
    open.
    """
    if player.page.get_attribute("#seafarers-chip", "aria-expanded") != "true":
        player.page.click("#seafarers-chip")


def count_ships(player):
    return len(
        (player.me() or {}).get("ships") or []
    )


def build_ship(player, candidates):
    """Arm ship placement in the Seafarers fold, then aim. See build_road.

    The popover is fixed and can lie over the board, so it is dismissed before
    anything is aimed at: a target underneath it cannot be clicked at all.
    """
    before = count_ships(player)
    open_seafarers_fold(player)
    player.page.wait_for_selector("#build-ship-btn:not([disabled])", timeout=5000)
    player.page.click("#build-ship-btn")
    player.page.keyboard.press("Escape")

    edge_key = first_clickable(player, 'edge', candidates)
    if not edge_key:
        raise AssertionError(f"no clickable sea edge among {len(candidates)} candidates")
    click_edge(player, edge_key)
    confirm_placement(player)
    player.page.wait_for_function(
        "before => ((window.__catanDebug.getBoard().players.find(p => p.is_you)"
        "            || {}).ships || []).length > before",
        arg=before, timeout=8000,
    )
    return edge_key


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


def resolve_robber(player, prefer_pirate=False):
    """Move the robber if a 7 is blocking the turn.

    `prefer_pirate` aims at the open sea instead, which is how the pirate is
    moved: nothing arms it, the roller simply taps a sea hex and the server
    reads that as the pirate rather than the robber. It falls back to the land
    hexes if the sea cannot be reached, because leaving a 7 unanswered blocks
    the rest of the game.
    """
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

    if prefer_pirate and board.get("rules", {}).get("pirate"):
        ocean = [
            key for key, hex_data in sorted(board["hexes"].items())
            if hex_data["type"] == "ocean" and key != board.get("pirate_hex")
        ]
        candidates = ocean + candidates

    clickable = first_clickable(player, 'hex', candidates)
    if clickable:
        candidates = [clickable] + [c for c in candidates if c != clickable]

    for target in candidates[:6]:
        click_hex(player, target)
        # The click only picked the hex; the robber moves on ✓.
        confirm_placement(player)
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
    confirm_placement(player)
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
    confirm_placement(player)
    _wait_for_new_piece(player, 'building', before)
    return vertex_key


def legal_city_vertices(board, player_name):
    """The player's own settlements, which are what a city upgrades."""
    return [
        key for key, vertex in sorted(board["vertices"].items())
        if (vertex.get("building") or {}).get("player") == player_name
        and (vertex.get("building") or {}).get("type") == 'settlement'
    ]


def build_city(player, candidates):
    """Upgrade a settlement. See build_road for why the button comes first."""
    player.page.click("#upgrade-city-btn")
    vertex_key = first_clickable(player, 'vertex', candidates)
    if not vertex_key:
        raise AssertionError(f"no clickable settlement among {len(candidates)}")
    before = player.page.evaluate(
        "owner => Object.values(window.__catanDebug.getBoard().vertices)"
        ".filter(v => (v.building || {}).player === owner"
        "          && v.building.type === 'city').length",
        player.name,
    )
    click_vertex(player, vertex_key)
    confirm_placement(player)
    player.page.wait_for_function(
        "([owner, before]) => Object.values(window.__catanDebug.getBoard().vertices)"
        ".filter(v => (v.building || {}).player === owner"
        "          && v.building.type === 'city').length > before",
        arg=[player.name, before], timeout=8000,
    )
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

    # A player holding a harbour is offering the bank more than it may charge
    # them, so the dialog lowers the give side to their own rate and waits to be
    # told again. A person reads the line and presses Propose; so does this.
    if player.page.is_visible("#trade-modal.show"):
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


def spend_what_you_can(player, ships=False):
    """Buy whatever this hand affords, preferring settlements over roads.

    A settlement is a victory point outright; roads only pay off through
    Longest Road. Both are needed to finish a game, so try both.

    `ships` adds a ship to the list, for a table playing Seafarers: a ship is
    the same price as a road in a different pair of resources, and it counts
    towards the Longest Trade Route alongside them, so a bot that never builds
    one leaves the whole of Seafarers unplayed.
    """
    built = []

    board = player.board()
    me = next((p for p in board["players"] if p["is_you"]), None)
    if me is None:
        return built

    # A fleet first, on a table that sails. A city is a victory point and a
    # ship is not, so a bot that always takes the point reaches the target with
    # the ships it was dealt in setup and no others — a seafaring game with no
    # sailing in it. Three is enough to have a shipping route worth the name and
    # few enough that it costs a handful of turns.
    fleet = len(me.get("ships") or [])
    if ships and fleet < STARTING_FLEET and can_afford(me, SHIP_COST):
        placed = _try(build_ship, player, legal_ship_edges(board, player.name))
        if placed:
            built.append(("ship", placed))
            board = player.board()
            me = next(p for p in board["players"] if p["is_you"])

    # A refused build is not a test failure: the server is the authority on
    # legality, and a bot that mispredicts it should lose a turn, not abort the
    # game. The end-of-game assertions catch a bot that never builds.
    # Cities first: a city is a victory point with no placement constraint at
    # all, and it spends the ore and wheat that otherwise pile up unused while
    # the bot waits for wood and brick it may never see.
    if can_afford(me, CITY_COST):
        placed = _try(build_city, player, legal_city_vertices(board, player.name))
        if placed:
            built.append(("city", placed))
            board = player.board()
            me = next(p for p in board["players"] if p["is_you"])

    if can_afford(me, SETTLEMENT_COST):
        placed = _try(build_settlement, player, legal_settlement_vertices(board, player.name))
        if placed:
            built.append(("settlement", placed))
            board = player.board()
            me = next(p for p in board["players"] if p["is_you"])

    # Ships before roads, once the fleet above has been paid for: they cost the
    # same as a road in a different pair of resources and count towards the same
    # award, and a bot that reaches for the road first spends the wood every
    # time.
    if ships and can_afford(me, SHIP_COST):
        placed = _try(build_ship, player, legal_ship_edges(board, player.name))
        if placed:
            built.append(("ship", placed))
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
        if legal_city_vertices(board, player.name):
            target = CITY_COST
        elif legal_settlement_vertices(board, player.name):
            target = SETTLEMENT_COST
        elif ships and not legal_road_edges(board, player.name):
            target = SHIP_COST
        else:
            target = ROAD_COST
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


def play_one_turn(actor, everyone, ships=False, prefer_pirate=False):
    """Roll, settle any 7, build what the hand allows, then pass.

    Returns what was built, so a caller can tell progress from a stalemate.

    `ships` lets the bot build ships as well; `prefer_pirate` answers a 7 by
    sailing the pirate rather than walking the robber. Both default off, so a
    base-game caller plays exactly the turn it always did.
    """
    resolve_robber(actor, prefer_pirate)
    if not actor.board().get("has_rolled_dice"):
        roll_dice(actor)

    # A 7 makes *every* over-stocked tab discard, not just the roller, and the
    # turn cannot advance until they all have.
    for player in everyone:
        resolve_discard(player)

    resolve_robber(actor, prefer_pirate)
    built = spend_what_you_can(actor, ships=ships)

    # A winning build ends the game, so there is no next turn to advance to.
    # Without this the bot wins and then hangs waiting for a turn change that
    # correctly never comes.
    if not game_is_over(actor):
        end_turn(actor)
    return built


def game_is_over(player):
    """Whether this tab has been told the game ended.

    Read from the notice a human would see rather than from board state: the
    banner is the only thing that announces a winner, so testing it is testing
    the thing that matters.
    """
    return any("GAME OVER" in notice.upper() for notice in player.notices())
