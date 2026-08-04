"""The changelog panel, in a real browser.

The bug this whole feature answers is a tester on a stale tab, so the
assertions are the ones that decide whether it can answer it:

  - the collapsed panel names the build without being opened. If reading the
    build costs a click, it will not be in the bug report;
  - it opens, closes, and hands focus back - it is a disclosure, and a panel a
    keyboard user cannot put away is a panel that covers the game;
  - an unread entry badges it, and reading it clears the badge and keeps it
    clear across a reload. A badge that never clears is one nobody looks at;
  - expanded, at 1920x1080, it covers neither the hand nor the board controls
    nor the console. Two dialogs have already had to be fixed for exactly that.

Self-contained but for the browser itself, which comes from
`browser_harness`: one browser process is shared by the whole run, and a
second sync driver in the same process cannot start at all.

Run: pytest tests/test_browser_changelog.py -m slow -v
"""

import os
import signal
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright", reason="playwright is not installed")
from browser_harness import browser_session  # noqa: E402

pytestmark = pytest.mark.slow

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(REPO, "server")
SHOT_DIR = os.path.join(REPO, "test-artifacts", "ui", "changelog")

# The size the owner plays at, and the size the no-scroll rule is stated for.
VIEWPORT = {"width": 1920, "height": 1080}

SEEN_STORAGE_KEY = "catan.changelogSeen"

# Placing on the click rather than through the ✓ - this suite is not about
# placement, and the confirmation is a timeout per click for a test that never
# presses it.
YOLO_STORAGE_KEY = "catan.yoloMode"


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(data_dir, changelog=None):
    """A real gunicorn server on its own port and data directory.

    `changelog` points CATAN_CHANGELOG at another file, which is how the
    malformed-file case is reached without editing the shipped one.
    """
    port = _free_port()
    env = dict(
        os.environ,
        SECRET_KEY="browser-test",
        CATAN_DATA_DIR=str(data_dir),
        CATAN_CONFIG="development",
    )
    if changelog is not None:
        env["CATAN_CHANGELOG"] = str(changelog)

    log_dir = os.path.join(REPO, "test-artifacts", "server-logs")
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, f"changelog-{port}.log"), "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "-w", "1", "--threads", "50",
         "-b", f"127.0.0.1:{port}", "wsgi:app"],
        cwd=SERVER_DIR, env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
    )
    proc.log_file = log

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
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
    proc.wait(timeout=5)
    proc.log_file.close()


class Tab:
    """One browser tab, with its console errors collected."""

    def __init__(self, browser, url, name, theme=None, seen=None):
        self.name = name
        self.errors = []
        options = {"viewport": VIEWPORT}
        if theme:
            options["color_scheme"] = theme
        context = browser.new_context(**options)
        context.add_init_script(
            f"window.localStorage.setItem('{YOLO_STORAGE_KEY}', '1');"
        )
        if seen is not None:
            # A tester who has already read up to a release, written the way the
            # client writes it. Set before the page loads, because the badge is
            # decided the moment the changelog arrives.
            context.add_init_script(
                f"window.localStorage.setItem('{SEEN_STORAGE_KEY}', {seen!r});"
            )
        self.page = context.new_page()
        self.page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        self.page.on(
            "console",
            lambda m: self.errors.append(m.text) if m.type == "error" else None,
        )
        self.page.goto(url, wait_until="networkidle")
        self.page.wait_for_function(
            "() => !document.getElementById('changelog-build')"
            "        .textContent.includes('…')",
            timeout=8000,
        )

    def join(self):
        self.page.check("#role-player")
        self.page.fill("#username", self.name)
        self.page.click("#join-btn")
        self.page.wait_for_selector("#user-screen:not(.hidden)", timeout=5000)

    def open_panel(self):
        self.page.click("#changelog-toggle")
        self.page.wait_for_selector("#changelog-body:not(.hidden)", timeout=5000)

    def box(self, selector):
        return self.page.evaluate(
            "sel => { const el = document.querySelector(sel);"
            "         const r = el.getBoundingClientRect();"
            "         return {left: r.left, top: r.top,"
            "                 right: r.right, bottom: r.bottom}; }",
            selector,
        )

    def shot(self, label):
        os.makedirs(SHOT_DIR, exist_ok=True)
        path = os.path.join(SHOT_DIR, f"{label}.png")
        self.page.screenshot(path=path, full_page=False)
        return path

    def noisy_errors(self):
        return [e for e in self.errors if "favicon" not in e.lower()]


def overlaps(one, other):
    return (one["left"] < other["right"] and one["right"] > other["left"]
            and one["top"] < other["bottom"] and one["bottom"] > other["top"])


@pytest.fixture(scope="module")
def browser():
    # The harness's shared browser, not a `sync_playwright()` of this file's
    # own: the sync driver holds an asyncio loop open for as long as it is
    # running, so a second one anywhere in the process raises "please use the
    # Async API" and every test in this file errors at setup.
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """One lobby, shared by every test that only reads the panel."""
    proc, url = start_server(tmp_path_factory.mktemp("changelog"))
    yield url
    stop_server(proc)


@pytest.fixture
def game_server(tmp_path):
    """A server of its own for a test that starts a game.

    There is one game per process by design, so a suite that shares a server
    across tests has its second `start_game` refused and its tabs dropped
    straight into somebody else's board.
    """
    proc, url = start_server(tmp_path / "game")
    yield url
    stop_server(proc)


def start_game(browser, url, theme=None):
    """Two seated players and a running game - the mid-game a tester is in."""
    host = Tab(browser, url, "Ann", theme=theme)
    host.join()
    guest = Tab(browser, url, "Bo", theme=theme)
    guest.join()
    host.page.click("#start-game-btn")
    host.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    return host, guest


# --- Which build am I on --------------------------------------------------


def test_the_collapsed_panel_names_the_build_before_anyone_joins(browser, server):
    """The build id is readable without a click, and without a seat.

    A tester on a stale tab is exactly the person who has not joined yet, and
    if reading the build costs a click it will not reach the bug report.
    """
    tab = Tab(browser, server, "Ann")

    label = tab.page.inner_text("#changelog-build")
    assert label.startswith("build ")
    build = label.removeprefix("build ").strip()
    assert build and build != "unknown", label

    # Collapsed by default: it is reference material, not a dialog.
    assert tab.page.is_hidden("#changelog-body")
    assert tab.page.get_attribute("#changelog-toggle", "aria-expanded") == "false"

    tab.open_panel()
    # The line a tester pastes names the build and when the server started -
    # a long-lived process on an old build is the failure case.
    line = tab.page.inner_text("#changelog-line")
    assert build in line, line
    assert "server up since" in line, line
    assert "this tab loaded" in line, line


def test_the_panel_closes_from_the_keyboard_and_hands_focus_back(browser, server):
    """A disclosure a keyboard user cannot put away is one that covers the game."""
    tab = Tab(browser, server, "Ann")

    tab.page.focus("#changelog-toggle")
    tab.page.keyboard.press("Enter")
    tab.page.wait_for_selector("#changelog-body:not(.hidden)", timeout=5000)
    assert tab.page.get_attribute("#changelog-toggle", "aria-expanded") == "true"

    tab.page.keyboard.press("Escape")
    tab.page.wait_for_selector("#changelog-body.hidden", state="attached")
    assert tab.page.get_attribute("#changelog-toggle", "aria-expanded") == "false"
    # Back on the trigger, not dropped on the body: focus on the body sends the
    # next Tab to the top of the document.
    assert tab.page.evaluate("() => document.activeElement.id") == "changelog-toggle"


def test_the_entries_are_the_ones_the_server_parsed(browser, server):
    """The panel holds no entry of its own - it draws what the server sent."""
    tab = Tab(browser, server, "Ann")
    tab.open_panel()

    kinds = tab.page.eval_on_selector_all(
        "#changelog-releases .changelog-kind", "els => els.map(e => e.textContent)"
    )
    assert "Fixed" in kinds and "New" in kinds
    # Known issues matter as much as the fixes: a tester who knows the island
    # points cannot score on a built-in board will not file it.
    assert "Known issue" in kinds
    # And the entries that answer a tester's report say so, which is what tells
    # them what to go and re-test.
    assert tab.page.locator("#changelog-releases .changelog-reported").count() > 0


# --- The badge ------------------------------------------------------------


def test_an_unread_release_badges_the_panel_until_it_is_read(browser, server):
    """Badge, read, reload, no badge. The reload is the half that matters:
    a badge that comes back is a badge testers learn to ignore."""
    tab = Tab(browser, server, "Ann")

    assert tab.page.is_visible("#changelog-badge")
    unread = int(tab.page.inner_text("#changelog-badge"))
    assert unread > 0
    # The count reaches a screen reader too - a badge announces nothing.
    assert "new entries" in tab.page.get_attribute("#changelog-toggle", "aria-label")

    tab.open_panel()
    tab.page.wait_for_selector("#changelog-badge.hidden", state="attached")

    tab.page.reload(wait_until="networkidle")
    tab.page.wait_for_function(
        "() => !document.getElementById('changelog-build').textContent.includes('…')",
        timeout=8000,
    )
    assert tab.page.is_hidden("#changelog-badge")
    assert "new entries" not in tab.page.get_attribute("#changelog-toggle", "aria-label")


def test_a_tester_who_has_read_the_newest_release_is_not_badged(browser, server):
    """Acknowledging is per release, not "the panel was opened once".

    A marker naming an older release must still badge, or a deploy that lands
    while a tester is reading tells them nothing.
    """
    tab = Tab(browser, server, "Ann", seen="0c891ad@2026-08-01 20:12")
    assert tab.page.is_visible("#changelog-badge")

    newest = tab.page.evaluate(
        "() => { const head = document.querySelector('.changelog-release-head');"
        "        return head.querySelector('.changelog-release-build').textContent"
        "               + '@' + head.querySelector('.changelog-release-when')"
        "                            .textContent; }"
    )
    read = Tab(browser, server, "Ann", seen=newest)
    assert read.page.is_hidden("#changelog-badge")


# --- It must not cover the game -------------------------------------------


def test_the_expanded_panel_covers_neither_the_hand_nor_the_controls(browser, game_server):
    """1920x1080, in a running game, expanded.

    The hand is what a player reads to decide anything, and the console and the
    zoom buttons are what they act with. Two dialogs have already had to be
    fixed for covering the first of those.
    """
    host, _ = start_game(browser, game_server)

    must_stay_clear = [
        ("#player-resources-panel", "the hand"),
        (".board-controls", "the board's zoom controls"),
        ("#game-console", "the console"),
        ("#chat-form", "the chat box"),
    ]
    # Collapsed as well as expanded: the pill sits in the same corner all game,
    # and a button that covers a build button is no better than a panel that
    # does.
    for state in ("collapsed", "expanded"):
        if state == "expanded":
            host.open_panel()
        panel = host.box("#changelog-panel")
        for selector, what in must_stay_clear:
            assert not overlaps(panel, host.box(selector)), (
                f"the {state} changelog panel covers {what}: "
                f"{panel} over {host.box(selector)}"
            )

    # Its own content may scroll; nothing else may. The page itself is the one
    # the no-scroll rule is stated about.
    page = host.page.evaluate(
        "() => ({height: document.documentElement.scrollHeight,"
        "        width: document.documentElement.scrollWidth,"
        "        viewH: window.innerHeight, viewW: window.innerWidth})"
    )
    assert page["height"] <= page["viewH"] + 1, page
    assert page["width"] <= page["viewW"] + 1, page
    assert host.noisy_errors() == [], host.noisy_errors()


def test_the_panel_is_available_in_the_lobby_and_in_a_game(browser, game_server):
    """A tester mid-game is exactly who needs it."""
    host, _ = start_game(browser, game_server)

    assert host.page.is_visible("#changelog-toggle")
    host.open_panel()
    assert host.page.is_visible("#changelog-releases")


# --- A malformed file is a server error, not a broken panel ----------------


def test_a_broken_changelog_still_names_the_build(browser, tmp_path):
    """The two halves are independent on purpose.

    "Which build am I on" is the question that costs a triage round, and it must
    not depend on the changelog parsing.
    """
    broken = tmp_path / "CHANGELOG.md"
    broken.write_text("# Changelog\n\n## nonsense heading\n\n- **Improved** no.\n")
    proc, url = start_server(tmp_path / "data", changelog=broken)
    try:
        tab = Tab(browser, url, "Ann")
        assert tab.page.inner_text("#changelog-build").removeprefix("build ").strip()
        tab.open_panel()
        assert "could not read its changelog" in tab.page.inner_text(".changelog-error")
        # Nothing was drawn half-way: no release survived the refusal.
        assert tab.page.locator(".changelog-release").count() == 0
    finally:
        stop_server(proc)


# --- Screenshots ----------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_shoot_the_panel_in_both_themes(browser, server, game_server, theme):
    """Collapsed and expanded, in the lobby and in a game, for a human to look at.

    Every assertion above is about geometry and text. Whether it *reads* is a
    question only a person looking at it can answer, in both palettes.
    """
    lobby = Tab(browser, server, "Ann", theme=theme)
    lobby.shot(f"lobby-collapsed-{theme}")
    lobby.open_panel()
    lobby.shot(f"lobby-expanded-{theme}")

    host, _ = start_game(browser, game_server, theme=theme)
    host.shot(f"game-collapsed-{theme}")
    host.open_panel()
    host.shot(f"game-expanded-{theme}")
