"""Three things a human tester reported, driven in a real browser.

  - "when discard/trade you cant see your cards due to blur". Both dialogs sit
    over the aside the hand panel lives in, and both ask a question that can
    only be answered from it: how many wheat do I hold, is that cloth worth
    offering. A player mid-discard and mid-trade must be able to read their own
    counts without closing the dialog.
  - "clicking on allied knight should show small ui icon over him that allows
    to activate the knight or promote him". The actions existed, in a fold, with
    no connection to the piece on the board.
  - a turn is several phases with a clock each now, and the console has to say
    which one is running.

Every scenario is arranged with the real engine and written to the save file the
server restores on boot, exactly as `test_browser_knights.py` does: a hand of
eight card types, an inactive knight and an outstanding discard are all many
non-deterministic turns away through the UI, and a browser test that has to roll
for them is not a gate. Everything after the save is the real client and the
real server.

Run: pytest tests/test_browser_tester_round_three.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    click_vertex,
    first_clickable,
    launch_browser,
    start_server,
    stop_server,
)
from game import cities_knights as ck_module
from game import persistence
from game import rules as rules_module
from game.game import Game
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(REPO, "test-artifacts", "ui", "tester-round-3")

TABLE = ["Alice", "Bob"]

# A hand with something of everything, so "the dialog shows my counts" cannot
# pass by showing five zeroes, and so no two card types share a number.
FULL_RESOURCES = {"wood": 3, "brick": 1, "sheep": 4, "wheat": 2, "ore": 5}
FULL_COMMODITIES = {"cloth": 2, "coin": 3, "paper": 1}

# One wheat and nothing else: activating costs exactly that, promoting costs
# sheep and ore, and an inactive knight may not move at all. So the overlay this
# hand produces has exactly one action enabled, which is the only shape of
# assertion that can fail for the right reason.
ACTIVATE_ONLY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 1, "ore": 0}


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- Arranging a table -----------------------------------------------------


def _inland_vertices(game):
    return [
        key for key in sorted(game.vertices)
        if len(game.vertices[key].neighbors["hexes"]) == 3
        and all(game.hexes[h].type != "ocean"
                for h in game.vertices[key].neighbors["hexes"])
    ]


def _roads_around(game, player_name, vertex_key):
    player = game.get_player(player_name)
    for edge_key in game.vertices[vertex_key].neighbors["edges"]:
        game.edges[edge_key].road = {"player": player_name}
        player.roads.append(edge_key)


def _hand(game, player_name, resources, commodities=None):
    player = game.get_player(player_name)
    player.resources.update(resources)
    player.commodities.update(commodities or {})


def build_game(build):
    """A started Cities & Knights game, mid-turn, with `build` applied.

    Commodities are part of the preset, which is what makes "resource *and*
    commodity counts" a question this table can be asked at all.
    """
    game = Game(
        list(TABLE), [], rng=random.Random(7),
        rules=rules_module.preset_rules("cities_and_knights"),
    )
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    return game, build(game)


@contextmanager
def table(browser, data_dir, build):
    """A running server restored from `build`, with both players connected."""
    game, marks = build_game(build)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    tabs = {}
    try:
        for name in TABLE:
            player = Player(browser, url, name, viewport=VIEWPORT)
            # Not Player.join(): that waits for the lobby, and a join into a
            # running game is answered with the game screen instead.
            player.page.check("#role-player")
            player.page.fill("#username", name)
            player.page.click("#join-btn")
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
            tabs[name] = player
        yield tabs[game.current_player_name()], marks
    finally:
        stop_server(proc)


# --- The scenarios ---------------------------------------------------------


def a_full_hand_owing_a_discard(game):
    """Eight card types in hand and a 7 outstanding against them."""
    actor = game.current_player_name()
    _hand(game, actor, FULL_RESOURCES, FULL_COMMODITIES)
    game.players_needing_discard = {actor: 10}
    return {"actor": actor}


def a_full_hand_to_trade_from(game):
    """The same hand, with nothing owed - the trade dialog opens on demand."""
    actor = game.current_player_name()
    _hand(game, actor, FULL_RESOURCES, FULL_COMMODITIES)
    return {"actor": actor}


def an_inactive_knight(game):
    """A knight standing on its owner's roads, inactive, with 1 wheat behind it."""
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor, ACTIVATE_ONLY_HAND)
    game.ck.knights_of(actor).append(ck_module.Knight(home))
    return {"actor": actor, "standing": home,
            "spots": list(game.vertices[home].neighbors["vertices"])}


def an_active_knight(game):
    """A knight from an earlier turn, active and free to march.

    Placed here rather than through the UI because a knight may never act on
    the turn it was built or the turn it was activated.
    """
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor, {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0})
    knight = ck_module.Knight(home)
    knight.active = True
    game.ck.knights_of(actor).append(knight)
    return {"actor": actor, "standing": home,
            "spots": list(game.vertices[home].neighbors["vertices"])}


# --- Fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        engine = launch_browser(playwright)
        yield engine
        engine.close()


@pytest.fixture
def discarding(browser, tmp_path):
    with table(browser, tmp_path, a_full_hand_owing_a_discard) as live:
        yield live


@pytest.fixture
def trading(browser, tmp_path):
    with table(browser, tmp_path, a_full_hand_to_trade_from) as live:
        yield live


@pytest.fixture
def sleeping_knight(browser, tmp_path):
    with table(browser, tmp_path, an_inactive_knight) as live:
        yield live


@pytest.fixture
def marching_knight(browser, tmp_path):
    with table(browser, tmp_path, an_active_knight) as live:
        yield live


# --- Reading what is on screen ---------------------------------------------

# The chip row inside a dialog, as counts. Read out of the rendered DOM rather
# than out of the payload: the payload being right is exactly the state this bug
# was reported in.
READ_CHIPS = """
selector => Array.from(
    document.querySelectorAll(selector + ' .resource-display .resource')
).map(chip => chip.textContent.trim())
"""

# Whether an element is really readable where it is: on screen, laid out, not
# transparent, and with nothing painted over its middle. `is_visible` answers
# none of that, and "you cannot see your cards" is a report about exactly it.
IS_LEGIBLE = """
selector => {
    const el = document.querySelector(selector);
    if (!el) return {found: false};
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const middle = document.elementFromPoint(
        box.left + box.width / 2, box.top + box.height / 2
    );
    return {
        found: true,
        onScreen: box.width > 0 && box.height > 0 && box.top >= 0 && box.left >= 0
            && box.bottom <= window.innerHeight && box.right <= window.innerWidth,
        opacity: Number(style.opacity),
        covered: !el.contains(middle),
    };
}
"""

MODAL_FILTER = """
id => getComputedStyle(document.getElementById(id)).backdropFilter
"""


def expected_chips(commodities=True):
    counts = [f"{icon}{FULL_RESOURCES[card]}" for card, icon in
              (("wood", "🌲"), ("brick", "🧱"), ("sheep", "🐑"),
               ("wheat", "🌾"), ("ore", "🪨"))]
    if commodities:
        counts += [f"{icon}{FULL_COMMODITIES[card]}" for card, icon in
                   (("cloth", "🧵"), ("coin", "🪙"), ("paper", "📜"))]
    return counts


def assert_legible(player, selector, what):
    state = player.page.evaluate(IS_LEGIBLE, selector)
    assert state["found"], f"{what}: {selector} is not in the document"
    assert state["onScreen"], f"{what}: {selector} is off screen or has no box"
    assert state["opacity"] == 1, f"{what}: {selector} is faded to {state['opacity']}"
    assert not state["covered"], f"{what}: something is painted over {selector}"


# --- The hand, while a dialog is asking about it ---------------------------


class TestTheHandIsReadableWhileDiscarding:
    """The tester's report, half of it: a 7 opens a dialog over the hand panel
    and then asks how many of each card to give back."""

    def test_the_discard_dialog_states_every_count_in_hand(self, discarding):
        player, _marks = discarding

        player.page.wait_for_selector("#discard-modal.show", timeout=8000)
        assert player.page.evaluate(READ_CHIPS, "#discard-hand") == expected_chips(), (
            "the discard dialog does not restate the hand it is asking about"
        )
        assert_legible(player, "#discard-hand", "mid-discard")
        shot(player, "discard-hand-light-1920x1080")

    def test_the_discard_dialog_does_not_blur_what_is_behind_it(self, discarding):
        """"you cant see your cards due to blur", named precisely."""
        player, _marks = discarding
        player.page.wait_for_selector("#discard-modal.show", timeout=8000)
        assert player.page.evaluate(MODAL_FILTER, "discard-modal") == "none"

    def test_the_counts_follow_the_hand_while_the_dialog_is_open(self, discarding):
        """A discard that is partly paid, or a card taken by somebody else's
        card, must not leave a stale number in front of the player. The strip is
        redrawn from every board payload, and this is what says so."""
        player, marks = discarding

        player.page.wait_for_selector("#discard-modal.show", timeout=8000)
        player.page.fill("#discard-wood", "3")
        player.page.fill("#discard-sheep", "4")
        player.page.fill("#discard-ore", "3")
        player.page.click("#submit-discard-btn")

        # Ten owed, ten given: the dialog closes and the hand is what is left.
        player.page.wait_for_function(
            "() => !document.getElementById('discard-modal').classList.contains('show')",
            timeout=8000,
        )
        left = player.page.evaluate(
            "() => window.__catanDebug.getBoard().players.find(p => p.is_you).resources"
        )
        assert left["wood"] == 0 and left["sheep"] == 0 and left["ore"] == 2


class TestTheHandIsReadableWhileTrading:
    """The other half, and the one no previous fix touched: an offer is decided
    entirely by what is in hand, and the dialog covered it."""

    def test_the_trade_dialog_states_every_count_in_hand(self, trading):
        player, _marks = trading

        player.page.click("#tab-trade")
        player.page.wait_for_selector("#propose-trade-btn", state="visible", timeout=5000)
        player.page.click("#propose-trade-btn")
        player.page.wait_for_selector("#trade-modal.show", timeout=5000)

        assert player.page.evaluate(READ_CHIPS, "#trade-hand") == expected_chips(), (
            "the trade dialog does not say what the player holds"
        )
        assert_legible(player, "#trade-hand", "mid-trade")
        assert player.page.evaluate(MODAL_FILTER, "trade-modal") == "none"
        shot(player, "trade-hand-light-1920x1080")


# --- A knight's own actions, at the knight ---------------------------------


def overlay_state(player):
    """What the overlay is offering, as a player sees it: the label on each
    button, whether it can be pressed, and the reason if it cannot."""
    return player.page.evaluate(
        """() => {
            const panel = document.getElementById('knight-actions');
            if (panel.classList.contains('hidden')) return null;
            return Array.from(panel.querySelectorAll('[data-knight-overlay]')).map(b => ({
                action: b.dataset.knightOverlay,
                label: b.textContent,
                enabled: !b.disabled,
                reason: b.title,
            }));
        }"""
    )


def tap_knight(player, vertex_key):
    click_vertex(player, vertex_key)
    player.page.wait_for_timeout(300)


class TestClickingYourOwnKnightOffersItsActions:
    def test_the_overlay_offers_exactly_the_legal_actions(self, sleeping_knight):
        """One wheat behind an inactive knight: it can be woken and nothing
        else. Promoting wants sheep and ore this hand does not hold, and an
        inactive knight cannot march at all - both are greyed with the reason
        on them rather than failing on click, which is how every other action
        in this client behaves."""
        player, marks = sleeping_knight

        assert overlay_state(player) is None, "the overlay was up before anything was tapped"
        tap_knight(player, marks["standing"])

        offered = overlay_state(player)
        assert offered is not None, "tapping my own knight raised nothing"
        assert [entry["action"] for entry in offered] == ["activate", "promote", "move"]

        enabled = {entry["action"]: entry["enabled"] for entry in offered}
        assert enabled == {"activate": True, "promote": False, "move": False}

        reasons = {entry["action"]: entry["reason"] for entry in offered}
        assert "sheep" in reasons["promote"], reasons["promote"]
        assert reasons["move"] == "Activate it first", reasons["move"]
        shot(player, "knight-overlay-light-1920x1080")

    def test_taking_an_action_sends_it_and_puts_the_overlay_away(self, sleeping_knight):
        """The knight wakes up, the wheat is spent, and the three-button strip
        does not stay behind describing a knight that has changed."""
        player, marks = sleeping_knight

        tap_knight(player, marks["standing"])
        player.page.click("#knight-action-activate")

        player.page.wait_for_function(
            "owner => (window.__catanDebug.getBoard().cities_knights.knights[owner] || [])"
            "  .every(k => k.active)",
            arg=player.name, timeout=8000,
        )
        assert player.page.evaluate(
            "() => window.__catanDebug.getBoard().players.find(p => p.is_you).resources.wheat"
        ) == 0, "activating did not spend the wheat"
        player.page.wait_for_timeout(300)
        assert overlay_state(player) is None, "the overlay stayed up after the action"

    def test_a_tap_away_from_the_knight_dismisses_it(self, sleeping_knight):
        player, marks = sleeping_knight

        tap_knight(player, marks["standing"])
        assert overlay_state(player) is not None
        elsewhere = first_clickable(player, "vertex", marks["spots"])
        assert elsewhere, "nowhere to tap that is not the knight"
        tap_knight(player, elsewhere)
        assert overlay_state(player) is None, "tapping empty board left the overlay up"

    def test_anchoring_the_overlay_never_moves_the_board(self, sleeping_knight):
        """The constraint learned twice: an overlay that changes the canvas box
        re-fits the camera, and the click that raised it was aimed under the old
        one. Arming a build mode once resized the board this way."""
        player, marks = sleeping_knight
        measure = (
            "() => { const c = document.getElementById('board-canvas');"
            "        const r = c.getBoundingClientRect();"
            "        return [r.left, r.top, r.width, r.height, c.width, c.height,"
            "                window.BoardRenderer.getScale()]; }"
        )
        before = player.page.evaluate(measure)
        tap_knight(player, marks["standing"])
        assert overlay_state(player) is not None
        during = player.page.evaluate(measure)
        assert before == during, f"raising the overlay moved the board: {before} vs {during}"


class TestTheOverlayDoesNotFightTheTwoTapMove:
    def test_the_first_tap_of_an_armed_move_still_only_picks_the_knight_up(
        self, marching_knight
    ):
        """A move is two taps and the first sends nothing. With Move knight
        armed that tap belongs to the move, not to the overlay - otherwise the
        knight is picked up and buried under a strip of buttons."""
        player, marks = marching_knight

        player.page.click("#knights-chip")
        player.page.wait_for_selector("#move-knight-btn:not([disabled])", timeout=5000)
        player.page.click("#move-knight-btn")
        player.page.keyboard.press("Escape")

        tap_knight(player, marks["standing"])
        assert player.page.evaluate(
            "() => window.__catanDebug.getSelection().knightMoveFrom"
        ) == marks["standing"], "the first tap did not pick the knight up"
        assert overlay_state(player) is None, "the overlay swallowed the first tap of a move"
        assert player.page.is_hidden("#placement-confirm"), "picking up raised a ✓"

    def test_the_overlays_move_button_picks_the_knight_up_and_sends_nothing(
        self, marching_knight
    ):
        """The same first tap, reached from the overlay instead. It must leave
        the board in the state the second tap expects, and it must not move
        anything on its own."""
        player, marks = marching_knight

        tap_knight(player, marks["standing"])
        offered = {entry["action"]: entry["enabled"] for entry in overlay_state(player)}
        assert offered["move"] is True, "an active knight was refused a move"
        player.page.click("#knight-action-move")
        player.page.wait_for_timeout(300)

        selection = player.page.evaluate("() => window.__catanDebug.getSelection()")
        assert selection["mode"] == "knight_move"
        assert selection["knightMoveFrom"] == marks["standing"]
        assert overlay_state(player) is None
        assert [k["vertex"] for k in player.page.evaluate(
            "owner => window.__catanDebug.getBoard().cities_knights.knights[owner]",
            player.name,
        )] == [marks["standing"]], "the knight moved before anything was confirmed"


# --- The phase clocks ------------------------------------------------------


class TestTheRunningClockIsNamed:
    def test_the_discard_clock_is_shown_while_a_discard_is_owed(self, discarding):
        """A turn is several phases with a clock each. While a 7 is unpaid the
        table is waiting on the discard, not on the roll or on the turn - and a
        console that showed the turn clock counting down through it was telling
        every player the wrong thing about how long they had."""
        player, _marks = discarding

        player.page.wait_for_function(
            "() => /^Discard: \\d+s$/.test("
            "  document.getElementById('dice-timer').textContent)",
            timeout=8000,
        )
        assert player.page.inner_text("#round-timer") == "Round: —", (
            "the turn clock is counting while the table waits on a discard"
        )
