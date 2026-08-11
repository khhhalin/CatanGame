"""Regressions for the TEST 6 overlay relayout (a player report, on main).

Three placement bugs the tester hit, plus a full non-overlap sweep of the new
arrangement, each asserted as a real overlap (or a real position) of the
elements' on-screen boxes so it fails on the pre-relayout geometry and passes on
the fix:

  item 2  the incoming trade-offer popup floated over the CENTRE of the board
          instead of sitting in a side gutter;
  item 3  the robber prompt strip's left edge ran UNDER the top-left scoreboard;
  item 4  the log/chat panel was a narrow right column the tester called "too
          small" — it must be a wide left rail.

The relayout moves the scoreboard to the top-right, the log to a wide left rail,
the offers to a right rail under the scoreboard, and offsets the robber strip to
clear both rails. The sweep pins that nothing collides at either viewport.

Run: pytest tests/test_browser_test6_fixes.py -m "" -v
"""

import os

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    build_settlement,
    edges_next_to,
    legal_setup_vertices,
    next_frame,
    start_server,
)
from browser_harness import (
    stop_server as harness_stop_server,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}
VIEWPORT_1600 = {"width": 1600, "height": 1000}
GAME_SEED = 20260803

SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "test6",
)


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


def make_table(browser, url, names, viewport=None):
    players = [
        Player(browser, url, name, viewport=viewport or VIEWPORT, yolo=True)
        for name in names
    ]
    for player in players:
        player.join()
    players[0].page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    players[0].page.click("#start-game-btn")
    for player in players:
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    return players


def place_setup_round(players):
    """Drive the whole setup phase, so the board is a real mid-game board with a
    full scoreboard — the worst case for the rail/strip collisions."""
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


def show_overlays(player):
    """Force the two situational overlays visible without playing to them: an
    incoming trade offer and the robber prompt. The relayout must place both
    clear of everything else, and the sweep needs them on-screen at once — the
    genuine worst case where every float is up together."""
    player.page.evaluate(
        """() => {
            const robber = document.querySelector('#robber-indicator');
            if (robber) robber.classList.remove('hidden');
            const offers = document.querySelector('#incoming-offers');
            if (offers) {
                offers.classList.remove('hidden');
                const card = document.createElement('div');
                card.className = 'trade-offer';
                card.innerHTML =
                    '<div class="trade-offer-header">'
                    + '<span class="trade-offer-player">Bob offers</span></div>'
                    + '<div class="trade-offer-resources">2 wood for 1 ore</div>';
                offers.replaceChildren(card);
            }
        }"""
    )
    next_frame(player.page)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def table(browser, tmp_path_factory):
    """Four players, past setup — the tallest scoreboard, the worst case for the
    rails and the robber strip pressing against one another."""
    proc, url = start_server(tmp_path_factory.mktemp("test6"), seed=GAME_SEED)
    players = make_table(browser, url, ["Alice", "Bob", "Carol", "Dave"])
    place_setup_round(players)
    show_overlays(players[0])
    yield players
    harness_stop_server(proc)


@pytest.fixture(scope="module")
def table_1600(browser, tmp_path_factory):
    """The same worst case at 1600x1000 — the narrower width where the two rails
    and the robber strip between them have the least room."""
    proc, url = start_server(tmp_path_factory.mktemp("test6-1600"), seed=GAME_SEED)
    players = make_table(browser, url, ["Ann", "Ben", "Cy", "Deb"],
                         viewport=VIEWPORT_1600)
    place_setup_round(players)
    show_overlays(players[0])
    yield players
    harness_stop_server(proc)


def rect(player, selector):
    """The on-screen box of a visible element, or None if it is hidden."""
    return player.page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
        }""",
        selector,
    )


def viewport_width(player):
    return player.page.evaluate("() => window.innerWidth")


def overlaps(a, b):
    """Whether two boxes share any area."""
    return not (
        a["right"] <= b["left"] or b["right"] <= a["left"]
        or a["bottom"] <= b["top"] or b["bottom"] <= a["top"]
    )


REM = 16  # the root font-size the shell is tuned at


class TestItemTwoOffersLeaveBoardCentre:
    """item 2: the incoming-offers popup sat centred over the board. It must
    live in a side gutter — entirely right of the board's horizontal centre —
    so it never covers the map the players are reading."""

    def test_offers_sit_in_a_side_gutter(self, table):
        alice = table[0]
        offers = rect(alice, "#incoming-offers")
        board = rect(alice, "#game-board")
        assert offers and board, "offers popup or board is not visible"
        centre_x = (board["left"] + board["right"]) / 2
        assert offers["left"] >= centre_x, (
            f"the incoming-offers popup {offers} reaches across the board's "
            f"centre line ({centre_x:.0f}px) instead of staying in a side gutter"
        )


class TestItemThreeRobberClearsScoreboard:
    """item 3: the robber prompt strip's left edge ran under the top-left
    scoreboard. The prompt and the scoreboard must not overlap."""

    def test_robber_prompt_clears_the_scoreboard(self, table):
        alice = table[0]
        robber = rect(alice, "#robber-indicator")
        players = rect(alice, "#players-panel")
        assert robber and players, "robber prompt or scoreboard is not visible"
        assert not overlaps(robber, players), (
            f"the robber prompt {robber} overlaps the scoreboard {players}"
        )


class TestItemFourLogIsAWideLeftRail:
    """item 4: the log/chat panel was a narrow right column ("too small"). It
    must be a wide left rail — its left edge on the left half of the screen and
    at least 20rem wide."""

    def test_log_is_a_wide_left_rail(self, table):
        alice = table[0]
        aside = rect(alice, ".table-aside")
        assert aside, "log panel is not visible"
        centre_x = viewport_width(alice) / 2
        width = aside["right"] - aside["left"]
        assert aside["left"] < centre_x, (
            f"the log panel {aside} is not on the left half "
            f"(centre {centre_x:.0f}px)"
        )
        assert width >= 20 * REM, (
            f"the log panel is only {width:.0f}px wide, under the 20rem "
            f"({20 * REM}px) a readable rail needs"
        )


def sweep_pairs(player):
    """Every overlay that stands over the board at once, with a friendly name."""
    named = {
        "log": rect(player, ".table-aside"),
        "scoreboard": rect(player, "#players-panel"),
        "offers": rect(player, "#incoming-offers"),
        "tray": rect(player, ".action-tray"),
        "dice": rect(player, "#dice-footer"),
        "robber-strip": rect(player, "#robber-indicator"),
        "zoom": rect(player, ".board-controls"),
        "changelog": rect(player, "#changelog-panel"),
        "settings": rect(player, ".settings-float"),
        "hand": rect(player, "#resource-display"),
    }
    return {name: box for name, box in named.items() if box is not None}


# The pairs that genuinely share the board plane and would be a real collision.
# The hand fan is only paired with the dice — the past regression the dice must
# never re-create (a dice float over the cards makes a discard tap unclickable).
SWEEP_PAIRS = [
    ("log", "scoreboard"), ("log", "offers"), ("log", "tray"),
    ("log", "dice"), ("log", "robber-strip"), ("log", "changelog"),
    ("scoreboard", "offers"), ("scoreboard", "robber-strip"),
    ("scoreboard", "zoom"), ("scoreboard", "settings"),
    ("offers", "robber-strip"), ("offers", "zoom"),
    ("robber-strip", "settings"),
    ("tray", "dice"), ("zoom", "dice"),
    ("dice", "hand"),
]


class TestFullNonOverlapSweep:
    """The whole new arrangement, at both viewports: no two floats that share
    the board plane may overlap."""

    def _assert_clear(self, player, label):
        boxes = sweep_pairs(player)
        shot(player, label)
        clashes = []
        for a, b in SWEEP_PAIRS:
            if a in boxes and b in boxes and overlaps(boxes[a], boxes[b]):
                clashes.append(f"{a} {boxes[a]} overlaps {b} {boxes[b]}")
        assert not clashes, "\n".join(clashes)

    def test_nothing_overlaps_at_1920(self, table):
        self._assert_clear(table[0], "test6-final-1920")

    def test_nothing_overlaps_at_1600(self, table_1600):
        self._assert_clear(table_1600[0], "test6-final-1600")

    def test_no_console_errors(self, table):
        assert table[0].noisy_errors() == [], table[0].noisy_errors()
