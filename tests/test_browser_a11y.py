"""Accessibility of the things a player cannot see: announcements, focus, contrast.

Every assertion here is about a player who is not using a mouse and a pointing
eye. Three failures of that kind have already shipped in this project:

  - `#7f8c8d` on white, at 2.9:1, was the muted text colour everywhere;
  - a disabled label in the dark theme sat at 4.13:1;
  - the ✓/✗ raised by a board click was announced by nothing at all. The board
    is one canvas with one label, so a screen-reader user was left waiting on a
    confirmation they were never told existed.

The contrast test below is a sweep, not a list of known-bad pairs: it walks
every element that actually paints text, resolves what it is painted on, and
measures. A list would only ever re-check the two colours already fixed.

Run: pytest tests/test_browser_a11y.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    click_vertex,
    client_point,
    first_clickable,
    launch_browser,
    legal_setup_vertices,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1600, "height": 1000}

# WCAG AA. The large-text allowance is real and worth honouring - a 24px
# heading at 3.2:1 is a pass, and failing it would push the design towards
# darker headings for no benefit to anyone.
AA_NORMAL = 4.5
AA_LARGE = 3.0

# Sub-pixel differences in how a browser composites a translucent layer put a
# genuinely-4.5 pair a hair under. This is slack for the arithmetic, not for
# the design: 4.49 is the same colour as 4.5, 4.1 is not.
CONTRAST_EPSILON = 0.05


# --- The sweep -------------------------------------------------------------
#
# Resolving "what is this text painted on" is the whole difficulty. An
# element's own background is usually `transparent`, so the answer is up the
# ancestor chain, and any translucent layer on the way has to be composited
# rather than skipped.

AUDIT_CONTRAST = """
() => {
    // Two serialisations, not one. `color-mix()` comes back from both Chromium
    // and Firefox as `color(srgb 1 1 1 / 0.88)` - channels 0-1, not 0-255 - and
    // reading those as bytes turns the translucent white behind the zoom
    // buttons into rgb(1, 1, 1), i.e. black. That reported the board controls
    // at 1.25:1 when they are actually fine, which is the failure mode that
    // makes an audit worth ignoring.
    const parseColor = (value) => {
        const text = String(value);
        const match = text.match(/[\\d.]+/g);
        if (!match || match.length < 3) {
            return null;
        }
        const scale = text.startsWith('color(') ? 255 : 1;
        const [r, g, b] = match.map(part => Number(part) * scale);
        const alpha = match.length > 3 ? Number(match[3]) : 1;
        return { r, g, b, a: alpha };
    };

    // sRGB -> relative luminance, exactly as WCAG defines it.
    const luminance = ({ r, g, b }) => {
        const channel = (value) => {
            const v = value / 255;
            return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        };
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    };

    const over = (top, bottom) => ({
        r: top.r * top.a + bottom.r * (1 - top.a),
        g: top.g * top.a + bottom.g * (1 - top.a),
        b: top.b * top.a + bottom.b * (1 - top.a),
        a: 1,
    });

    const ratio = (fg, bg) => {
        const [light, dark] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
        return (light + 0.05) / (dark + 0.05);
    };

    // The stack of translucent layers between this element and the first
    // opaque thing under it, composited top-down onto the page background.
    const backgroundBehind = (element) => {
        const layers = [];
        let node = element;
        while (node) {
            const color = parseColor(getComputedStyle(node).backgroundColor);
            if (color && color.a > 0) {
                layers.push(color);
                if (color.a === 1) {
                    break;
                }
            }
            node = node.parentElement;
        }
        // White is the last resort: a page with no opaque background anywhere
        // is painted on the canvas default, which is white.
        let base = { r: 255, g: 255, b: 255, a: 1 };
        for (let i = layers.length - 1; i >= 0; i -= 1) {
            base = layers[i].a === 1 ? layers[i] : over(layers[i], base);
        }
        return base;
    };

    const hasOwnText = (element) => Array.from(element.childNodes).some(
        node => node.nodeType === Node.TEXT_NODE && node.textContent.trim()
    );

    const findings = [];
    document.querySelectorAll('*').forEach(element => {
        if (!hasOwnText(element)) {
            return;
        }
        const box = element.getBoundingClientRect();
        // Nothing invisible: a hidden panel's colours are not on screen, and
        // failing on them would make the test unfixable by looking at the page.
        if (!box.width || !box.height) {
            return;
        }
        const style = getComputedStyle(element);
        if (style.visibility === 'hidden' || Number(style.opacity) === 0) {
            return;
        }

        const fg = parseColor(style.color);
        if (!fg || fg.a === 0) {
            return;
        }
        const bg = backgroundBehind(element);
        // Translucent text is painted onto its own background first.
        const painted = fg.a < 1 ? over(fg, bg) : fg;

        const size = parseFloat(style.fontSize);
        const weight = Number(style.fontWeight) || 400;
        const large = size >= 24 || (size >= 18.66 && weight >= 700);

        findings.push({
            selector: element.tagName.toLowerCase()
                + (element.id ? '#' + element.id : '')
                + (element.className && typeof element.className === 'string'
                    ? '.' + element.className.trim().split(/\\s+/).join('.') : ''),
            text: element.textContent.trim().slice(0, 40),
            color: style.color,
            background: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
            ratio: Math.round(ratio(painted, bg) * 100) / 100,
            large,
        });
    });
    return findings;
}
"""


# Buttons transition `background-color` over --dur-med, and the Start button
# crosses the whole way from the disabled grey to the accent fill the moment the
# table fills up. Sampled mid-flight it reads as a 1.2:1 failure that exists in
# neither the before state nor the after one. Longer than --dur-slow.
TRANSITION_SETTLE_MS = 400


def contrast_failures(player):
    """Every on-screen text element below its WCAG AA threshold."""
    player.page.wait_for_timeout(TRANSITION_SETTLE_MS)
    return [
        finding for finding in player.page.evaluate(AUDIT_CONTRAST)
        if finding["ratio"] < (AA_LARGE if finding["large"] else AA_NORMAL) - CONTRAST_EPSILON
    ]


def describe(failures):
    return "\n".join(
        f"  {f['ratio']}:1  {f['color']} on {f['background']}"
        f"  {'(large)' if f['large'] else ''}  {f['selector']}  {f['text']!r}"
        for f in failures
    )


# --- Contrast, both themes -------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_visible_label_meets_wcag_aa(tmp_path, theme):
    """No text on the lobby or the board is below AA, in either theme.

    Both themes, because the two failures already found here were one of each:
    `#7f8c8d` was a light-theme colour and the 4.13:1 disabled label was a dark
    one. A sweep of one theme would have found exactly one of them.
    """
    proc, url = start_server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                host = Player(browser, url, "Ann", viewport=VIEWPORT,
                              color_scheme=theme)
                lobby_failures = contrast_failures(host)
                assert not lobby_failures, (
                    f"join screen, {theme} theme:\n{describe(lobby_failures)}"
                )

                host.join()
                guest = Player(browser, url, "Bo", viewport=VIEWPORT,
                               color_scheme=theme)
                guest.join()
                # The lobby is where the disabled-label failure lived: Start is
                # disabled until the table is full enough, and the disabled
                # style is not reachable any other way.
                seated_failures = contrast_failures(host)
                assert not seated_failures, (
                    f"lobby, {theme} theme:\n{describe(seated_failures)}"
                )

                host.page.click("#start-game-btn")
                host.page.wait_for_selector("#game-screen:not(.hidden)", timeout=8000)
                # The rail, the scoreboard, the build buttons and the log all
                # carry text and none of them exist before the game starts.
                playing_failures = contrast_failures(host)
                assert not playing_failures, (
                    f"game screen, {theme} theme:\n{describe(playing_failures)}"
                )
            finally:
                browser.close()
    finally:
        stop_server(proc)


# --- The confirmation announces itself -------------------------------------


def test_placement_confirmation_is_announced_and_takes_focus(tmp_path):
    """A board click raises the ✓/✗, says so, and puts focus on ✓.

    The regression this pins: the confirmation used to appear with no
    announcement of any kind. The board is a single `role="img"` canvas, so
    there is nothing for a screen reader to notice - the pending placement was
    visible only as pixels, and the player was left waiting on a question they
    had not been asked.
    """
    proc, url = start_server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                actor = _player_to_move(*_start_game(browser, url))

                board = actor.board()
                vertex = first_clickable(actor, 'vertex', legal_setup_vertices(board))
                assert vertex, "no reachable vertex to place on"
                click_vertex(actor, vertex)
                actor.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)

                announcement = actor.page.inner_text("#placement-announce")
                assert "Settlement" in announcement, announcement
                # The keys are the part that makes it operable at all: a screen
                # reader user has no way to find a button positioned over a
                # canvas by pixel coordinates.
                assert "Enter" in announcement and "Escape" in announcement, announcement

                assert actor.page.evaluate(
                    "() => document.activeElement.id"
                ) == "placement-confirm-yes"

                # And answering it hands focus back rather than dropping it on
                # the body, which would send the next Tab to the top of the page.
                actor.page.keyboard.press("Escape")
                actor.page.wait_for_selector("#placement-confirm.hidden", state="attached")
                assert actor.page.evaluate("() => document.activeElement.id") == "board-canvas"
                assert actor.page.inner_text("#placement-announce") == ""
            finally:
                browser.close()
    finally:
        stop_server(proc)


# A real mouse tap focuses the canvas on pointerdown, so the pending placement
# and the focus move happen with focus already off the chat box. This drives the
# same two pointer events and then puts focus back in the chat box, all
# synchronously - the confirmation is shown on the next animation frame, so this
# is exactly the state the guard exists for: a confirmation arriving while the
# player is mid-word.
TAP_THEN_TYPE = """
([x, y]) => {
    const canvas = document.getElementById('board-canvas');
    const options = { clientX: x, clientY: y, pointerId: 1, bubbles: true, isPrimary: true };
    canvas.dispatchEvent(new PointerEvent('pointerdown', options));
    canvas.dispatchEvent(new PointerEvent('pointerup', options));
    const chat = document.getElementById('chat-input');
    chat.focus();
    chat.value = 'hold on';
}
"""


def test_a_confirmation_does_not_steal_focus_from_the_chat_box(tmp_path):
    """A confirmation must not take the keystroke a player is mid-word on.

    Focus is the player's. Taking it while they are typing into chat means the
    next character lands on a button that places a settlement - both a lost
    message and a move nobody asked for.
    """
    proc, url = start_server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                actor = _player_to_move(*_start_game(browser, url))

                board = actor.board()
                vertex = first_clickable(actor, 'vertex', legal_setup_vertices(board))
                assert vertex, "no reachable vertex to place on"
                point = client_point(actor, 'vertex', vertex)
                actor.page.evaluate(TAP_THEN_TYPE, [point["x"], point["y"]])

                actor.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
                assert actor.page.evaluate("() => document.activeElement.id") == "chat-input"
                # Announced anyway: not stealing focus is not a reason to leave
                # the player unaware the confirmation is there.
                assert "Enter" in actor.page.inner_text("#placement-announce")
            finally:
                browser.close()
    finally:
        stop_server(proc)


# --- Popovers, from the keyboard only --------------------------------------


POPOVERS = [
    ("bank-chip", "bank-popover"),
    ("dev-cards-chip", "dev-cards-popover"),
    ("active-rules-chip", "active-rules-popover"),
]


@pytest.mark.parametrize("chip_id,popover_id", POPOVERS)
def test_popover_opens_closes_and_returns_focus_from_the_keyboard(
    tmp_path, chip_id, popover_id
):
    """A fold is fully operable without a mouse, and never traps focus.

    The no-scroll layout moved several whole panels behind these chips, so a
    keyboard user who cannot open one has lost the panel entirely rather than
    merely lost a shortcut.
    """
    proc, url = start_server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                host, _ = _start_game(browser, url)

                host.page.focus(f"#{chip_id}")
                host.page.keyboard.press("Enter")
                host.page.wait_for_selector(f"#{popover_id}:not(.hidden)", timeout=5000)
                assert host.page.get_attribute(f"#{chip_id}", "aria-expanded") == "true"

                # Not a trap: Tab moves on, and the popover's own controls are
                # reachable rather than being skipped over.
                host.page.keyboard.press("Tab")
                assert host.page.evaluate("() => document.activeElement.id") != chip_id

                host.page.keyboard.press("Escape")
                host.page.wait_for_selector(f"#{popover_id}.hidden", state="attached")
                assert host.page.get_attribute(f"#{chip_id}", "aria-expanded") == "false"
                # Back on the chip, not on the body: focus dropped on the body
                # sends the next Tab to the top of the document, which on this
                # screen is a very long way from where the player was.
                assert host.page.evaluate("() => document.activeElement.id") == chip_id
            finally:
                browser.close()
    finally:
        stop_server(proc)


@pytest.mark.parametrize("chip_id,popover_id", POPOVERS)
def test_popover_close_button_returns_focus_to_its_chip(tmp_path, chip_id, popover_id):
    """The × inside a popover is about to be hidden along with the popover.

    Pressing it left focus on a `display: none` element, which the browser
    resolves by dropping focus on the body.
    """
    proc, url = start_server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                host, _ = _start_game(browser, url)

                host.page.click(f"#{chip_id}")
                host.page.wait_for_selector(f"#{popover_id}:not(.hidden)", timeout=5000)
                host.page.click(f"#{popover_id} [data-close-popover]")
                host.page.wait_for_selector(f"#{popover_id}.hidden", state="attached")

                assert host.page.evaluate("() => document.activeElement.id") == chip_id
            finally:
                browser.close()
    finally:
        stop_server(proc)


def _start_game(browser, url):
    """Two seated players and a started game — the state everything here needs."""
    host = Player(browser, url, "Ann", viewport=VIEWPORT)
    host.join()
    guest = Player(browser, url, "Bo", viewport=VIEWPORT)
    guest.join()
    host.page.click("#start-game-btn")
    host.page.wait_for_selector("#game-screen:not(.hidden)", timeout=8000)
    guest.page.wait_for_selector("#game-screen:not(.hidden)", timeout=8000)
    return host, guest


def _player_to_move(host, guest):
    """The tab whose turn it is. Seat order is not fixed, so it has to be asked.

    A placement test driven through the wrong tab raises no confirmation at all
    and fails as a timeout, which reads like a broken feature rather than a
    coin toss.
    """
    for player in (host, guest):
        board = player.board()
        if board and board.get("current_player") == player.name:
            return player
    raise AssertionError("neither tab is on turn")
