"""What a table is playing with has to be visible, not merely in force.

Two rules now ride the modifier funnel and neither one shows itself:

- `dice_set` constrains what the dice may come up. The console shows two faces
  and nothing else, so a table that will never see a 12 cannot tell a rule from
  a run of luck.
- `epidemic` quietly hands a city one card where it would take two. A player
  who counts two and collects one reports it as a bug — the Cities & Knights
  starting-city commodity was reported exactly that way.

Both suites below drive real games in a real browser and assert on what is on
the screen, because both defects leave server state perfectly correct.

Run: pytest tests/test_browser_dice_sets.py -m slow -v
"""

import os
import re

import pytest
from browser_harness import (
    Player,
    click_edge,
    click_vertex,
    count_pieces,
    edges_next_to,
    first_clickable,
    launch_browser,
    legal_setup_vertices,
    resolve_discard,
    resolve_robber,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

# The set this suite picks, and the name the catalogue gives it. The name is
# never asserted as a literal — it is read back from the server's own
# catalogue, because a picker showing the id is the failure being guarded
# against and a copied literal cannot notice it.
CUSTOM_DICE_SET = "no_two_or_twelve"

# A fixed board and fixed dice: this suite waits for a particular number to
# come up, and an unseeded run is a different wait every time.
GAME_SEED = 20260804

VIEWPORT = {"width": 1920, "height": 1080}

SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "dice",
)


def shot(player, label):
    """Save a screenshot where a human is meant to go and look at it."""
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


def set_rule(player, rule_id, value):
    """Set one rule through the picker, as a host would.

    The groups are `<details>`, so a collapsed section has to be opened before
    Playwright will treat the control as visible.
    """
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
    elif rule_id and control.evaluate("el => el.tagName") == "SELECT":
        control.select_option(value)
    else:
        control.fill(str(value))
        control.blur()
    player.page.wait_for_timeout(400)


def seat_two(browser, url, color_scheme=None, yolo=False):
    """Two joined tabs, ready to start a game."""
    alice = Player(browser, url, "Alice", viewport=VIEWPORT,
                   color_scheme=color_scheme, yolo=yolo)
    bob = Player(browser, url, "Bob", viewport=VIEWPORT,
                 color_scheme=color_scheme, yolo=yolo)
    alice.join()
    bob.join()
    alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    return alice, bob


def start_game(alice, others):
    alice.page.click("#start-game-btn")
    for player in (alice, *others):
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)


def catalogue_option_name(player, rule_id, option_id):
    """What the server calls this option — the words the player should see."""
    return player.page.evaluate(
        "([ruleId, optionId]) => window.__catanDebug.getRules().catalogue"
        "   .find(rule => rule.id === ruleId).options"
        "   .find(option => option.id === optionId).name",
        [rule_id, option_id],
    )


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = launch_browser(play)
        yield instance
        instance.close()


# --- The dice say which dice they are -------------------------------------


@pytest.fixture(scope="module")
def standard_table(browser, tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("dice-standard"), seed=GAME_SEED)
    alice, bob = seat_two(browser, url)
    start_game(alice, [bob])
    yield alice
    stop_server(proc)


@pytest.fixture(scope="module")
def custom_table(browser, tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("dice-custom"), seed=GAME_SEED)
    alice, bob = seat_two(browser, url, yolo=True)
    set_rule(alice, "dice_set", CUSTOM_DICE_SET)
    start_game(alice, [bob])
    # Played through setup so the dice area can be seen doing its job: two
    # faces, and the set they came out of.
    play_setup(alice, bob)
    yield alice, bob
    stop_server(proc)


class TestTheDiceSayWhichSetTheyAre:
    def test_a_table_playing_the_box_dice_is_told_nothing(self, standard_table):
        """A rule that changes nothing has nothing to explain, and the console
        is a fixed number of rows — every row it grows is a row the board
        loses."""
        assert standard_table.board()["rules"]["dice_set"] == "standard"
        assert not standard_table.page.is_visible("#dice-set"), (
            "the base game's console grew a note about the dice it always used"
        )

    def test_a_custom_set_is_named_beside_the_dice(self, custom_table):
        alice, _ = custom_table
        assert alice.board()["rules"]["dice_set"] == CUSTOM_DICE_SET

        alice.page.wait_for_selector("#dice-set:not(.hidden)", timeout=8000)
        shown = alice.page.inner_text("#dice-set")
        expected = catalogue_option_name(alice, "dice_set", CUSTOM_DICE_SET)

        assert expected in shown, f"the dice area reads {shown!r}, not {expected!r}"
        assert CUSTOM_DICE_SET not in shown, (
            f"the dice area shows the rule id: {shown!r}"
        )

    def test_every_seat_at_the_table_is_told_which_dice_these_are(self, custom_table):
        """The rule is the table's, not the roller's: a player watching someone
        else roll needs the same explanation for the numbers they never see."""
        _, bob = custom_table
        bob.page.wait_for_selector("#dice-set:not(.hidden)", timeout=8000)
        assert bob.page.inner_text("#dice-set").strip()

    def test_the_house_rules_summary_names_the_option_not_its_id(self, custom_table):
        """`no_two_or_twelve` is a key in a dict, not something to read."""
        alice, _ = custom_table
        alice.page.wait_for_selector("#active-rules-panel:not(.hidden)", timeout=8000)
        shown = alice.page.inner_text("#active-rules")
        expected = catalogue_option_name(alice, "dice_set", CUSTOM_DICE_SET)
        assert expected in shown, f"the house rules read {shown!r}"
        assert CUSTOM_DICE_SET not in shown, f"the house rules show an id: {shown!r}"

    def test_the_dice_area_is_worth_looking_at(self, custom_table):
        alice, bob = custom_table
        roller = alice if alice.board()["current_player"] == "Alice" else bob
        roller.page.click("#roll-dice-btn")
        roller.page.wait_for_function(
            "() => window.__catanDebug.getBoard().has_rolled_dice === true",
            timeout=8000,
        )
        shot(roller, "dice-set-light")


# --- A modifier that bites says so ----------------------------------------
#
# The engine does not yet report which modifiers fired, so nothing on the wire
# can tell the client that a city took one card instead of two. Working it back
# out of the board in JavaScript would be a second copy of the rule, free to
# drift from the one that was applied, so the client waits for the server to
# say. See the xfail below for the exact field.


@pytest.fixture(scope="module")
def epidemic_table(browser, tmp_path_factory):
    """A game with Epidemic on and a city on the board from the first round.

    `setup_second_city` is what makes this cheap: the second starting piece is
    a city, so a table has something Epidemic can act on before a single card
    has been earned.
    """
    proc, url = start_server(tmp_path_factory.mktemp("dice-epidemic"), seed=GAME_SEED)
    alice, bob = seat_two(browser, url, yolo=True)
    set_rule(alice, "setup_second_city", True)
    set_rule(alice, "epidemic", True)
    start_game(alice, [bob])
    play_setup(alice, bob)
    yield alice, bob
    stop_server(proc)


def red_number_vertices(board):
    """Vacant, distance-legal vertices, the ones touching a 6 or an 8 first.

    Epidemic only ever acts on a 6 or an 8, so a city anywhere else would leave
    the test rolling forever for an event that cannot happen.
    """
    hot = {
        key for key, hex_data in board["hexes"].items()
        if hex_data.get("number") in (6, 8)
    }

    def heat(vertex_key):
        touching = board["vertices"][vertex_key]["neighbors"]["hexes"]
        return -len([key for key in touching if key in hot])

    return sorted(legal_setup_vertices(board), key=heat)


def place_setup_piece(player, kind, candidates):
    """Click one starting piece into place.

    Nothing is armed first: during setup the client arms whatever the server is
    asking for, and pressing a build button would only arm the wrong piece.
    """
    field = 'road' if kind == 'edge' else 'building'
    before = count_pieces(player, field)
    target = first_clickable(player, kind, candidates)
    assert target, f"no clickable {kind} among {len(candidates)} candidates"
    (click_edge if kind == 'edge' else click_vertex)(player, target)
    player.page.wait_for_function(
        "([kind, owner, before]) => {"
        "  const board = window.__catanDebug.getBoard();"
        "  const group = kind === 'road' ? board.edges : board.vertices;"
        "  const field = kind === 'road' ? 'road' : 'building';"
        "  return Object.values(group)"
        "    .filter(entry => (entry[field] || {}).player === owner).length > before; }",
        arg=[field, player.name, before], timeout=8000,
    )
    return target


def play_setup(alice, bob):
    """Both players place their starting pieces, cities beside a 6 or an 8."""
    by_name = {"Alice": alice, "Bob": bob}
    for _step in range(len(by_name) * 2 + 4):
        board = alice.board()
        if board["game_phase"] != "setup":
            break
        actor = by_name[board["current_player"]]
        vertex = place_setup_piece(actor, 'vertex', red_number_vertices(board))
        place_setup_piece(actor, 'edge', edges_next_to(actor.board(), vertex))

    assert alice.board()["game_phase"] == "playing", "setup never finished"


def roll_and_pass(actor, everyone):
    """One turn of nothing but the dice, and the roll's log entry."""
    resolve_robber(actor)
    actor.page.wait_for_selector("#roll-dice-btn:not([disabled])", timeout=8000)
    actor.page.click("#roll-dice-btn")
    actor.page.wait_for_function(
        "() => window.__catanDebug.getBoard().has_rolled_dice === true", timeout=8000
    )
    for player in everyone:
        resolve_discard(player)
    resolve_robber(actor)

    entry = actor.page.evaluate(
        "() => { const rows = document.querySelectorAll('#log-entries .log-kind-dice');"
        "        return rows.length ? rows[rows.length - 1].textContent : ''; }"
    )

    before = actor.board()["current_player"]
    actor.page.wait_for_selector("#next-turn-btn:not([disabled])", timeout=10000)
    actor.page.click("#next-turn-btn")
    actor.page.wait_for_function(
        "prev => window.__catanDebug.getBoard().current_player !== prev",
        arg=before, timeout=8000,
    )
    return entry


def a_city_was_paid(player, total):
    """Whether that roll really did hand somebody's city its cards.

    Read off the board the server sent, so the test only makes its claim about
    a roll Epidemic actually acted on — a 6 nobody had a city on proves
    nothing about a rule that only touches cities.
    """
    board = player.board()
    paying = {
        key for key, hex_data in board["hexes"].items()
        if hex_data.get("number") == total and key != board.get("robber_hex")
    }
    return any(
        (vertex.get("building") or {}).get("type") == "city"
        and any(key in paying for key in vertex["neighbors"]["hexes"])
        for vertex in board["vertices"].values()
    )


class TestAModifierThatBitesSaysSo:
    @pytest.mark.xfail(
        strict=True,
        reason="the roll carries no record of which modifiers fired: the dice "
               "log entry needs details['modifiers'] = the rule ids of the "
               "modifiers that changed a value while resolving it",
    )
    def test_a_roll_epidemic_cut_names_the_rule_in_the_log(self, epidemic_table):
        """Epidemic is silent by construction: the roll reads like any other.

        Fails today because nothing on the wire says a modifier fired, and the
        client will not guess — recomputing the rule in JavaScript is a second
        implementation free to disagree with the one that was applied.
        """
        alice, bob = epidemic_table
        by_name = {"Alice": alice, "Bob": bob}

        for _turn in range(40):
            actor = by_name[alice.board()["current_player"]]
            entry = roll_and_pass(actor, (alice, bob))
            # The total, read out of the sentence rather than off the end of
            # it: the note this test is waiting for is appended after it.
            rolled = re.search(r"= (\d+)", entry)
            total = int(rolled.group(1)) if rolled else None
            if total not in (6, 8) or not a_city_was_paid(actor, total):
                continue

            shot(alice, "epidemic-log-light")
            assert "Epidemic" in entry, (
                f"a roll Epidemic acted on reads {entry!r} — the player is "
                "told nothing about the card they did not get"
            )
            return

        pytest.fail("no 6 or 8 paid a city in 40 rolls")


# --- Both themes ----------------------------------------------------------


def test_the_dice_set_note_is_readable_in_the_dark_theme(browser, tmp_path_factory):
    """Six contrast failures have been fixed in this UI; this is not a seventh."""
    proc, url = start_server(tmp_path_factory.mktemp("dice-dark"), seed=GAME_SEED)
    try:
        alice, bob = seat_two(browser, url, color_scheme="dark", yolo=True)
        set_rule(alice, "dice_set", CUSTOM_DICE_SET)
        start_game(alice, [bob])
        alice.page.wait_for_selector("#dice-set:not(.hidden)", timeout=8000)
        play_setup(alice, bob)
        roller = alice if alice.board()["current_player"] == "Alice" else bob
        roller.page.click("#roll-dice-btn")
        roller.page.wait_for_function(
            "() => window.__catanDebug.getBoard().has_rolled_dice === true",
            timeout=8000,
        )
        shot(roller, "dice-set-dark")
        assert roller.page.inner_text("#dice-set").strip()
    finally:
        stop_server(proc)
