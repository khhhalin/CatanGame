"""The screen fits, at the size the owner plays at, in the worst case there is.

The complaint this suite exists for: "i dont like that i have to scroll to see
some things, id prefer everything visible and details hidden under buttons."

Measured before the change, at 1920x1080 with four players and Cities & Knights
on, `.game-rail` overflowed its column by 46px and clipped the House Rules panel
off the bottom of the screen. The page itself never scrolled, so a test that
only checked `document.scrollHeight` would have passed over it — the overflow
was inside a panel, which is exactly where it hides.

So the assertions here are per element, not per page:

  - nothing scrolls, anywhere, except the log's own message list;
  - nothing is clipped: every panel's contents fit inside the box drawn round
    them, and every box is inside the viewport;
  - each folded subject states its numbers without being opened, and opens and
    closes on demand.

Four players and Cities & Knights is the worst case deliberately: it is the most
rows in the scoreboard and the most subjects in the rail. An empty base game
fits anything.

Run: pytest tests/test_browser_layout.py -m slow -v
"""

import os

import pytest
from browser_harness import (
    Player,
    build_road,
    build_settlement,
    edges_next_to,
    launch_browser,
    legal_setup_vertices,
    start_server,
)
from browser_harness import (
    stop_server as harness_stop_server,
)
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

# Screenshots land where a human can look at them; that is the point.
SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "layout",
)

GAME_SEED = 20260803

# The folds, as (chip id, popover id). Every one of these must state its
# headline numbers on the chip and open its detail on demand.
BASE_FOLDS = [
    ("dev-cards-chip", "dev-cards-popover"),
    ("bank-chip", "bank-popover"),
    ("active-rules-chip", "active-rules-popover"),
]

CK_FOLDS = [
    ("barbarian-chip", "barbarian-popover"),
    ("improvements-chip", "improvements-popover"),
    ("knights-chip", "knights-popover"),
    ("progress-cards-chip", "progress-cards-popover"),
    ("bank-chip", "bank-popover"),
    ("active-rules-chip", "active-rules-popover"),
]


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- The measurement ------------------------------------------------------
#
# Deliberately not a screenshot diff. "Does it fit" is a numeric question about
# every box on the page, and the answer has to name the element that failed or
# it is useless to whoever has to fix it.
#
# `#log-entries` is the one sanctioned scroller: a game log is unbounded, and
# the owner exempted it by name.

_OVERFLOWING = """
() => {
    const allowed = new Set(['log-entries']);
    const out = [];
    const describe = (el) => el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}.${el.className}`;

    for (const el of document.querySelectorAll('#game-screen *, .table-aside *')) {
        if (allowed.has(el.id) || el.closest('#log-entries')) {
            continue;
        }
        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') {
            continue;
        }
        // A `position: fixed` popover is measured on its own terms below; it is
        // not part of any flow and cannot push anything.
        if (style.position === 'fixed') {
            continue;
        }
        // 1px of slack: fractional layout rounds, and a half pixel is not a
        // scrollbar.
        if (el.scrollHeight > el.clientHeight + 1 && el.clientHeight > 0) {
            out.push({ el: describe(el), axis: 'y',
                       content: el.scrollHeight, box: el.clientHeight });
        }
        if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) {
            out.push({ el: describe(el), axis: 'x',
                       content: el.scrollWidth, box: el.clientWidth });
        }
    }
    return out;
}
"""

# Overflow is only half of it: a flex column whose children do not fit lets them
# spill *outside* the box with no scrollHeight to show for it, and the bottom one
# simply leaves the screen. That is the exact shape of the reported bug, so it is
# measured separately — every visible box must be inside the viewport.
_OFF_SCREEN = """
() => {
    const out = [];
    const describe = (el) => el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}.${el.className}`;
    for (const el of document.querySelectorAll(
            '#game-screen .panel, #game-screen .fold, .table-aside .panel')) {
        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') {
            continue;
        }
        const box = el.getBoundingClientRect();
        if (box.width === 0 && box.height === 0) {
            continue;
        }
        if (box.bottom > window.innerHeight + 1 || box.top < -1
            || box.right > window.innerWidth + 1 || box.left < -1) {
            out.push({ el: describe(el),
                       box: [box.left, box.top, box.right, box.bottom],
                       viewport: [window.innerWidth, window.innerHeight] });
        }
    }
    return out;
}
"""

_PAGE_SCROLLS = """
() => ({
    height: document.documentElement.scrollHeight,
    width: document.documentElement.scrollWidth,
    viewH: window.innerHeight,
    viewW: window.innerWidth,
})
"""


def assert_nothing_scrolls_or_clips(player, where):
    overflowing = player.page.evaluate(_OVERFLOWING)
    assert overflowing == [], f"{where}: these boxes cannot show their contents: {overflowing}"

    off_screen = player.page.evaluate(_OFF_SCREEN)
    assert off_screen == [], f"{where}: these boxes are off the screen: {off_screen}"

    page = player.page.evaluate(_PAGE_SCROLLS)
    assert page["height"] <= page["viewH"] + 1, f"{where}: the page scrolls vertically: {page}"
    assert page["width"] <= page["viewW"] + 1, f"{where}: the page scrolls horizontally: {page}"


def set_rule(player, rule_id, value):
    """Set one rule through the picker, as a host would."""
    player.page.evaluate(
        "id => { const el = document.getElementById(`rule-${id}`);"
        "        const group = el && el.closest('details');"
        "        if (group) { group.open = true; } }",
        rule_id,
    )
    control = player.page.locator(f"#rule-{rule_id}")
    control.scroll_into_view_if_needed()
    if isinstance(value, bool):
        control.set_checked(value)
    else:
        control.fill(str(value))
        control.blur()
    player.page.wait_for_timeout(300)


def place_setup_round(players):
    """Drive the whole setup phase, so the board is a real mid-game board.

    An empty board understates the problem: the scoreboard is at its shortest,
    no knights exist and nothing has been improved. The layout has to hold once
    there is something in it.
    """
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
    with sync_playwright() as play:
        instance = launch_browser(play)
        yield instance
        instance.close()


def make_table(browser, url, names, rules):
    players = [
        Player(browser, url, name, viewport=VIEWPORT, yolo=True) for name in names
    ]
    for player in players:
        player.join()
    for rule_id, value in rules.items():
        set_rule(players[0], rule_id, value)
    players[0].page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    players[0].page.click("#start-game-btn")
    for player in players:
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    return players


@pytest.fixture(scope="module")
def ck_table(browser, tmp_path_factory):
    """Four players, Cities & Knights on, past setup. The worst case."""
    proc, url = start_server(tmp_path_factory.mktemp("layout-ck"), seed=GAME_SEED)
    players = make_table(
        browser, url, ["Alice", "Bob", "Carol", "Dave"],
        {"cities_and_knights": True},
    )
    place_setup_round(players)
    yield players
    harness_stop_server(proc)


@pytest.fixture(scope="module")
def base_table(browser, tmp_path_factory):
    """Two players, base game, past setup."""
    proc, url = start_server(tmp_path_factory.mktemp("layout-base"), seed=GAME_SEED)
    players = make_table(browser, url, ["Ann", "Ben"], {})
    place_setup_round(players)
    yield players
    harness_stop_server(proc)


class TestCitiesAndKnightsFits:
    """1920x1080, four players, Cities & Knights: the case that overflowed."""

    def test_the_expansion_really_is_on(self, ck_table):
        board = ck_table[0].board()
        assert board["rules"]["cities_and_knights"] is True
        assert board["cities_knights"] is not None
        assert len(board["players"]) == 4

    def test_nothing_scrolls_and_nothing_is_clipped(self, ck_table):
        for player in ck_table:
            assert_nothing_scrolls_or_clips(player, f"{player.name} (C&K, 4 players)")
        shot(ck_table[0], "ck-4p-1920x1080")

    def test_the_things_that_must_always_be_visible_are(self, ck_table):
        """The owner's list, checked one by one. Every one of these was on the
        list of what must never be behind a button."""
        player = ck_table[0]
        for selector in (
            "#board-canvas",        # the board
            "#resource-display",    # your own hand
            "#turn-indicator",      # whose turn it is
            "#game-players",        # the full scoreboard
            "#award-summary",       # who holds longest road / largest army
            "#place-settlement-btn", "#place-road-btn", "#upgrade-city-btn",
            "#log-entries",         # the event log
            "#chat-input",          # chat
        ):
            assert player.page.is_visible(selector), f"{selector} is not on screen"

    def test_every_player_is_listed_with_their_score(self, ck_table):
        player = ck_table[0]
        rows = player.page.eval_on_selector_all(
            "#game-players li", "els => els.map(e => e.textContent)"
        )
        assert len(rows) == 4, f"the scoreboard is not showing four players: {rows}"
        for name in ("Alice", "Bob", "Carol", "Dave"):
            assert any(name in row for row in rows), f"{name} is missing from the scoreboard"
        assert all("pts" in row for row in rows), f"a row has no score: {rows}"

    def test_the_build_buttons_state_their_costs(self, ck_table):
        player = ck_table[0]
        costs = player.page.eval_on_selector_all(
            "#place-settlement-btn .build-cost, #place-road-btn .build-cost,"
            " #upgrade-city-btn .build-cost",
            "els => els.map(e => e.textContent.trim())",
        )
        assert len(costs) == 3, f"a build button has no cost on it: {costs}"
        assert all(costs), f"a build button's cost is blank: {costs}"

    def test_each_fold_summarises_itself_without_being_opened(self, ck_table):
        """A chip that says nothing is a button, not a summary."""
        player = ck_table[0]
        for chip, _ in CK_FOLDS:
            text = player.page.inner_text(f"#{chip}").strip()
            assert text and "—" not in text, f"#{chip} has no summary: {text!r}"

    def test_the_improvements_chip_reads_as_the_owner_asked(self, ck_table):
        value = ck_table[0].page.inner_text("#improvements-chip-value").strip()
        assert value == "Trade 0/5 · Politics 0/5 · Science 0/5", value

    def test_every_popover_opens_and_closes(self, ck_table):
        player = ck_table[0]
        for chip, popover in CK_FOLDS:
            player.page.click(f"#{chip}")
            player.page.wait_for_selector(f"#{popover}:not(.hidden)", timeout=3000)
            assert player.page.get_attribute(f"#{chip}", "aria-expanded") == "true"
            # An open popover must still fit the screen, or it has swapped one
            # unreachable thing for another.
            box = player.page.evaluate(
                "id => { const r = document.getElementById(id).getBoundingClientRect();"
                "        return [r.left, r.top, r.right, r.bottom,"
                "                window.innerWidth, window.innerHeight]; }",
                popover,
            )
            left, top, right, bottom, width, height = box
            assert left >= -1 and top >= -1 and right <= width + 1 and bottom <= height + 1, (
                f"#{popover} hangs off the screen: {box}"
            )
            shot(player, f"ck-popover-{chip}")

            player.page.click(f"#{chip}")
            player.page.wait_for_function(
                "id => document.getElementById(id).classList.contains('hidden')",
                arg=popover, timeout=3000,
            )
            assert player.page.get_attribute(f"#{chip}", "aria-expanded") == "false"

    def test_only_one_popover_is_ever_open(self, ck_table):
        """Two overlapping popovers on a 15rem rail are unreadable."""
        player = ck_table[0]
        player.page.click("#knights-chip")
        player.page.wait_for_selector("#knights-popover:not(.hidden)", timeout=3000)
        player.page.click("#improvements-chip")
        player.page.wait_for_selector("#improvements-popover:not(.hidden)", timeout=3000)
        assert player.page.evaluate(
            "() => document.getElementById('knights-popover').classList.contains('hidden')"
        ), "opening a second popover left the first one up"
        player.page.click("#improvements-chip")

    def test_an_open_popover_does_not_move_the_board(self, ck_table):
        """The bug this guards: anything in flow beside the board resizes the
        canvas, the camera re-fits, and a click already in flight lands
        somewhere else."""
        player = ck_table[0]
        measure = (
            "() => { const c = document.getElementById('board-canvas');"
            "        const r = c.getBoundingClientRect();"
            "        return [r.left, r.top, r.width, r.height, c.width, c.height,"
            "                window.BoardRenderer.getScale()]; }"
        )
        before = player.page.evaluate(measure)
        player.page.click("#knights-chip")
        player.page.wait_for_selector("#knights-popover:not(.hidden)", timeout=3000)
        player.page.wait_for_timeout(250)
        during = player.page.evaluate(measure)
        player.page.click("#knights-chip")
        player.page.wait_for_timeout(250)
        after = player.page.evaluate(measure)

        assert before == during == after, (
            f"a popover moved the board: {before} vs {during} vs {after}"
        )

    def test_arming_or_disabling_a_build_button_never_resizes_it(self, ck_table):
        """The bug this guards: a 2px border on `.active` grew a button, which
        rewrapped the console, which resized the board box, which moved the
        camera — under a click the player had already started.

        Driven by setting the classes rather than by pressing the buttons: the
        buttons are correctly disabled when the hand cannot pay, and this is a
        question about the stylesheet, not about affordability. Both states are
        checked, because the new disabled treatment paints a border too."""
        player = ck_table[0]
        measure = (
            "() => { const console_ = document.getElementById('game-console');"
            "        const board = document.getElementById('board-canvas');"
            "        const c = console_.getBoundingClientRect();"
            "        const b = board.getBoundingClientRect();"
            "        return [c.width, c.height, b.left, b.top, b.width, b.height,"
            "                board.width, board.height]; }"
        )
        set_state = """
        ([armed, disabled]) => {
            for (const id of ['place-settlement-btn', 'place-road-btn', 'upgrade-city-btn']) {
                const button = document.getElementById(id);
                button.classList.toggle('active', armed);
                button.disabled = disabled;
            }
        }
        """
        player.page.evaluate(set_state, [False, False])
        player.page.wait_for_timeout(250)
        baseline = player.page.evaluate(measure)

        for armed, disabled in ((True, False), (False, True), (True, True)):
            player.page.evaluate(set_state, [armed, disabled])
            player.page.wait_for_timeout(250)
            assert player.page.evaluate(measure) == baseline, (
                f"armed={armed} disabled={disabled} moved the board or the console"
            )

        # Hand the buttons back; the next board payload re-derives them anyway.
        player.page.evaluate(set_state, [False, False])

    def test_an_unaffordable_action_greys_out_and_says_why(self, ck_table):
        """The tester's complaint: some actions grey out and others let you
        click and then show an error. Every action greys out now, and a
        disabled button with no `title` is the same dead end as before."""
        # A tab that is not on turn: deterministic, unlike affordability, and
        # the case where "let you click, then show an error" was worst.
        current = ck_table[0].board()["current_player"]
        player = next(p for p in ck_table if p.name != current)

        states = player.page.eval_on_selector_all(
            "#place-settlement-btn, #place-road-btn, #upgrade-city-btn, #buy-dev-card-btn",
            "els => els.map(e => ({ id: e.id, off: e.disabled, why: e.title }))",
        )
        assert states, "no build buttons found"
        for state in states:
            assert state["off"], f"{state['id']} is live on someone else's turn"
            assert current in state["why"], (
                f"{state['id']} is disabled but does not say why: {state['why']!r}"
            )

    def test_a_players_own_turn_is_named_in_the_console(self, ck_table):
        current = ck_table[0].board()["current_player"]
        for player in ck_table:
            text = player.page.inner_text("#turn-indicator")
            expected = "Your turn" if player.name == current else f"{current}'s turn"
            assert expected in text, f"{player.name} sees {text!r}, expected {expected!r}"

    def test_the_console_stays_one_row(self, ck_table):
        """Every row the console grows is a row the board loses."""
        height = ck_table[0].page.evaluate(
            "() => document.getElementById('game-console').getBoundingClientRect().height"
        )
        assert height <= 72, f"the console has wrapped onto a second row: {height}px"

    def test_the_board_gets_most_of_the_screen(self, ck_table):
        """The rail was doing all the work while the board had dead margins."""
        share = ck_table[0].page.evaluate(
            "() => { const b = document.getElementById('game-board').getBoundingClientRect();"
            "        return (b.width * b.height) / (window.innerWidth * window.innerHeight); }"
        )
        assert share > 0.55, f"the board is only {share:.0%} of the screen"

    def test_no_console_errors_were_logged(self, ck_table):
        for player in ck_table:
            assert player.noisy_errors() == [], (
                f"{player.name} logged console errors: {player.noisy_errors()}"
            )


class TestBaseGameFits:
    """The base game must not have regressed while the expansion was fixed."""

    def test_nothing_scrolls_and_nothing_is_clipped(self, base_table):
        for player in base_table:
            assert_nothing_scrolls_or_clips(player, f"{player.name} (base game)")
        shot(base_table[0], "base-2p-1920x1080")

    def test_the_expansion_folds_are_absent(self, base_table):
        player = base_table[0]
        for fold in ("barbarian-panel", "improvements-panel",
                     "knights-panel", "progress-cards-panel"):
            assert not player.page.is_visible(f"#{fold}"), (
                f"#{fold} is showing in a base game"
            )

    def test_the_development_cards_fold_is_present_here(self, base_table):
        """Cities & Knights replaces the deck; a base game still has one."""
        assert base_table[0].page.is_visible("#dev-cards-chip")

    def test_every_base_popover_opens_and_closes(self, base_table):
        player = base_table[0]
        for chip, popover in BASE_FOLDS:
            player.page.click(f"#{chip}")
            player.page.wait_for_selector(f"#{popover}:not(.hidden)", timeout=3000)
            player.page.click(f"#{chip}")
            player.page.wait_for_function(
                "id => document.getElementById(id).classList.contains('hidden')",
                arg=popover, timeout=3000,
            )

    def test_the_trade_panel_folds_without_hiding_the_log(self, base_table):
        """Trade used to take the log's place, which is why a chat message
        arriving behind it read as "chat is broken"."""
        player = base_table[0]
        player.page.click("#tab-trade")
        player.page.wait_for_selector("#trade-panel:not(.hidden)", timeout=3000)
        assert player.page.is_visible("#log-entries"), "opening Trade hid the log"
        assert player.page.is_visible("#chat-input"), "opening Trade hid chat"
        assert player.page.is_visible("#propose-trade-btn")
        player.page.click("#tab-log")
        player.page.wait_for_function(
            "() => document.getElementById('trade-panel').classList.contains('hidden')",
            timeout=3000,
        )

    def test_no_console_errors_were_logged(self, base_table):
        for player in base_table:
            assert player.noisy_errors() == [], (
                f"{player.name} logged console errors: {player.noisy_errors()}"
            )


class TestTheLobbyFits:
    def test_the_lobby_does_not_scroll_at_1920x1080(self, browser, tmp_path_factory):
        proc, url = start_server(tmp_path_factory.mktemp("layout-lobby"))
        try:
            player = Player(browser, url, "Solo", viewport=VIEWPORT)
            player.join()
            player.page.wait_for_selector("#user-screen:not(.hidden)", timeout=8000)
            player.page.wait_for_timeout(400)
            shot(player, "lobby-1920x1080")

            page = player.page.evaluate(_PAGE_SCROLLS)
            assert page["height"] <= page["viewH"] + 1, f"the lobby page scrolls: {page}"
            assert page["width"] <= page["viewW"] + 1, f"the lobby scrolls sideways: {page}"
        finally:
            harness_stop_server(proc)
