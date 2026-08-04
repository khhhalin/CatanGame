"""The pending-choice phase, driven end to end in a real browser.

`server/game/pending_choice.py` shipped with a full protocol and no client. A
progress card or a lost barbarian attack opened a choice, the server froze the
whole table — `MUST_CHOOSE` for the chooser, `AWAITING_CHOICE` for everyone
else — and nothing on any screen said so or offered a way out. Thirty seconds
later the timeout answered it by taking the first option. That was live.

So every test here asserts what a *player* can see and do:

  - the chooser is asked, with the options the server actually offered;
  - everybody else is told who the table is waiting for and what for;
  - answering resolves it and the table plays on;
  - an option the server never offered is refused, and the refusal is visible.

The scenario is built with the real engine and written to the save file the
server restores on boot. That is the only way to reach these rules at all: a
barbarian attack that a table loses with two cities standing is many
non-deterministic turns away, and a browser test that has to roll for it is not
a gate. Everything after the save — the protocol, the payload filtering, the
freeze, the answer — is the real server.

Every choice carries a 30-second deadline that restarts when the save is
loaded, and the watchdog answers it when that runs out. Each test therefore
gets its own server rather than sharing one: a shared fixture would have the
question answered out from under the later tests.

Run: pytest tests/test_browser_pending_choice.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    browser_session,
    client_point,
    first_clickable,
    next_frame,
    start_server,
    stop_server,
)
from game import persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(REPO, "test-artifacts", "ui", "choices")

TABLE = ["Alice", "Bob"]


def wait_until_gone(player, element_id):
    """Wait for an overlay to take its `hidden` class back.

    Deliberately not `wait_for_selector('#id.hidden')`: that selector matches a
    display:none element and wait_for_selector waits for *visibility*, so it can
    never be satisfied by the thing having gone away.
    """
    player.page.wait_for_function(
        "id => document.getElementById(id).classList.contains('hidden')",
        arg=element_id, timeout=8000,
    )


def shot(player, label):
    """Save a screenshot where a human can look at it afterwards."""
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- Building a table that is already mid-question -------------------------


def _land_vertices(game, count):
    """Intersections ringed by land, so a city on one has terrain to name.

    The panel describes a vertex option by what it touches — "City on wheat 6,
    ore 9" — because a raw "3,-3,0" tells a player nothing. Picking coastal
    intersections here would let that fall back to the key and the test would
    stop covering the thing it is for.
    """
    chosen = []
    for key in sorted(game.vertices):
        hex_keys = game.vertices[key].neighbors["hexes"]
        if len(hex_keys) < 3:
            continue
        if any(game.hexes[h].type in ("ocean", "desert") for h in hex_keys):
            continue
        chosen.append(key)
        if len(chosen) == count:
            break
    assert len(chosen) == count, "the board has too few inland intersections"
    return chosen


def build_game(build):
    """A started Cities & Knights game, mid-turn, with `build` applied."""
    game = Game(
        list(TABLE), [], rng=random.Random(7),
        rules=rules_module.preset_rules("cities_and_knights"),
    )
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    build(game)
    return game


@contextmanager
def table(browser, data_dir, build):
    """A running server restored from `build`, with both players connected."""
    game = build_game(build)
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
        yield game, tabs
    finally:
        stop_server(proc)


# --- The two scenarios -----------------------------------------------------


def barbarians_sack_one_of_bobs_cities(game):
    """Bob loses a city he has to pick; Alice is on turn and can do nothing.

    Deliberately not the player on turn: a choice is owed by whoever the rule
    names, and the first client draft only ever looked at the current player.
    """
    bob = game.get_player("Bob")
    for key in _land_vertices(game, 2):
        game.vertices[key].building = {"type": "city", "player": "Bob"}
        bob.cities.append(key)

    result = game.resolve_barbarian_attack()
    assert result["won"] is False, "Bob has no knights, so the barbarians win"
    assert result["awaiting"] == ["Bob"], "Bob owns two cities and must pick one"


def alice_holds_the_merchant(game):
    """The merchant standing on a land hex, with Alice controlling it.

    Set on the game rather than on the payload in the browser, so the piece and
    the holder reach the client the way they do in a real game — through
    `get_board_data`.
    """
    game.merchant_hex = next(
        key for key in sorted(game.hexes)
        if game.hexes[key].type not in ("ocean", "desert")
    )
    game.merchant_holder = "Alice"


def alice_plays_a_commercial_harbor(game):
    """Bob is asked which commodity he hands over, and for what."""
    game.get_player("Alice").resources["wheat"] = 1
    bob = game.get_player("Bob")
    bob.commodities["cloth"] = 1
    bob.commodities["coin"] = 1

    result = game._progress_commercial_harbor("Alice", "wheat")
    assert result["success"], result
    assert result["asked"] == ["Bob"]


# --- Fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.fixture
def sacked_city(browser, tmp_path):
    with table(browser, tmp_path, barbarians_sack_one_of_bobs_cities) as live:
        yield live


@pytest.fixture
def merchant(browser, tmp_path):
    with table(browser, tmp_path, alice_holds_the_merchant) as live:
        yield live


@pytest.fixture
def harbor(browser, tmp_path):
    with table(browser, tmp_path, alice_plays_a_commercial_harbor) as live:
        yield live


# --- What the chooser sees -------------------------------------------------


def option_labels(player):
    return player.page.eval_on_selector_all(
        "#choice-options .choice-option", "els => els.map(e => e.textContent)"
    )


class TestTheChooserIsAsked:
    def test_the_panel_offers_exactly_the_cities_the_server_recorded(self, sacked_city):
        """The options are the server's list, not a list the client re-derived.

        Asserted against the engine's own recorded options: a client that
        offered every city on the board, or none, would satisfy a test that
        only counted buttons.
        """
        game, tabs = sacked_city
        bob = tabs["Bob"]
        bob.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)

        offered = game.pending_choice_for("Bob")["options"]
        assert len(option_labels(bob)) == len(offered) == 2
        shot(bob, "chooser-barbarian-city-1920x1080")

        # Both themes, because the panel and the ring are new surfaces and the
        # dark theme is the one nobody looks at until a player reports it.
        bob.page.evaluate(
            "() => document.documentElement.setAttribute('data-theme', 'dark')"
        )
        next_frame(bob.page)
        shot(bob, "chooser-barbarian-city-dark-1920x1080")
        bob.page.evaluate(
            "() => document.documentElement.removeAttribute('data-theme')"
        )

    def test_a_city_is_named_by_the_terrain_it_stands_on(self, sacked_city):
        """"3,-3,0" is not an answer to "which city?". The kinds whose options
        are vertex keys have to be described, or the player is being asked to
        pick between two coordinates."""
        _, tabs = sacked_city
        bob = tabs["Bob"]
        bob.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)

        for label in option_labels(bob):
            assert label.startswith("City on "), label
            assert "," in label, f"{label} names no terrain"

    def test_the_cities_on_offer_are_ringed_on_the_board(self, sacked_city):
        """The board is a canvas: every DOM assertion here passes on a blank
        one, so this counts pixels. The ring is what turns two coordinates into
        two places a player can see."""
        game, tabs = sacked_city
        bob = tabs["Bob"]
        bob.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)

        first = game.pending_choice_for("Bob")["options"][0]
        with_ring = bob.page.evaluate(SAMPLE_VERTEX, [first, True])
        without = bob.page.evaluate(SAMPLE_VERTEX, [first, False])
        assert with_ring != without, "nothing was drawn around the chosen city"

    def test_a_card_choice_names_the_cards_and_who_is_asking(self, harbor):
        """The Commercial Harbor's options are commodity ids and its context
        carries who wants them and what they are paying."""
        _, tabs = harbor
        bob = tabs["Bob"]
        bob.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)

        labels = option_labels(bob)
        assert [label.split()[-1] for label in labels] == ["cloth", "coin"]

        context = bob.page.inner_text("#choice-context")
        assert "Alice" in context and "wheat" in context, context
        shot(bob, "chooser-commercial-harbor-1920x1080")


# --- What everybody else sees ----------------------------------------------


class TestTheTableIsToldWhyItStopped:
    def test_a_non_chooser_is_told_who_is_holding_the_game_up(self, sacked_city):
        """The bug this whole suite exists for: the table froze and no screen
        said anything at all."""
        _, tabs = sacked_city
        alice = tabs["Alice"]
        alice.page.wait_for_selector("#choice-indicator:not(.hidden)", timeout=8000)

        waiting = alice.page.inner_text("#choice-waiting-text")
        assert "Bob" in waiting, waiting
        assert "cities" in waiting, waiting
        shot(alice, "waiting-barbarian-city-1920x1080")

    def test_a_non_chooser_is_never_shown_the_options(self, sacked_city):
        """The server sends the options to the chooser's sockets alone, and the
        panel must not appear for anyone else — a Master Merchant is choosing
        out of somebody's hand."""
        _, tabs = sacked_city
        alice = tabs["Alice"]
        alice.page.wait_for_selector("#choice-indicator:not(.hidden)", timeout=8000)

        assert alice.page.is_hidden("#choice-panel")
        pending = alice.board()["pending_choices"]
        assert pending and "options" not in pending[0]

    def test_acting_anyway_is_refused_and_says_who_it_is_waiting_for(self, sacked_city):
        """Alice is on turn and the freeze is real. The refusal has to name Bob,
        or "Next Turn does nothing" is all she learns."""
        _, tabs = sacked_city
        alice = tabs["Alice"]
        alice.page.wait_for_selector("#choice-indicator:not(.hidden)", timeout=8000)

        alice.page.click("#next-turn-btn")
        alice.page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#notice-region *'))"
            "  .some(n => n.textContent.includes('Waiting for Bob'))",
            timeout=5000,
        )
        assert alice.board()["current_player"] == "Alice", "the turn advanced anyway"

    def test_the_waiting_notice_is_shown_for_a_card_choice_too(self, harbor):
        _, tabs = harbor
        alice = tabs["Alice"]
        alice.page.wait_for_selector("#choice-indicator:not(.hidden)", timeout=8000)
        assert "Bob" in alice.page.inner_text("#choice-waiting-text")


# --- Answering -------------------------------------------------------------


class TestAnsweringUnfreezesTheTable:
    def test_tapping_a_ringed_city_gives_it_up_and_play_resumes(self, sacked_city):
        """The whole round trip a player makes: tap the board, the city goes,
        the panel and the waiting notice clear, and Alice's turn ends."""
        game, tabs = sacked_city
        bob, alice = tabs["Bob"], tabs["Alice"]
        bob.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)

        offered = list(game.pending_choice_for("Bob")["options"])
        target = first_clickable(bob, "vertex", offered)
        assert target, f"none of {offered} could be aimed at"

        point = client_point(bob, "vertex", target)
        bob.page.mouse.click(point["x"], point["y"])

        wait_until_gone(bob, "choice-panel")
        wait_until_gone(alice, "choice-indicator")

        # The city really is gone, on the payload every client draws from.
        assert bob.board()["vertices"][target]["building"] != {
            "type": "city", "player": "Bob"
        }

        # And the table plays on, which is the point of answering at all.
        alice.page.click("#next-turn-btn")
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().current_player === 'Bob'", timeout=8000
        )

    def test_a_card_choice_is_answered_from_its_button(self, harbor):
        """The commodity leaves Bob's hand and Alice's wheat arrives in it."""
        _, tabs = harbor
        bob = tabs["Bob"]
        bob.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)

        bob.page.click("#choice-options .choice-option")
        wait_until_gone(bob, "choice-panel")

        mine = bob.me()
        assert mine["resources"]["wheat"] == 1, "the harbour paid nothing"
        assert mine["commodities"]["cloth"] == 0, "no commodity was handed over"


class TestAnOptionTheServerNeverOfferedIsRefused:
    def test_a_forged_option_is_rejected_and_the_question_stays_open(self, sacked_city):
        """The recorded option list is the server's allowlist.

        Driven by tampering with the payload the client answers from, which is
        exactly what a modified client would do — the panel itself only ever
        offers what arrived. The refusal has to reach the player, and the
        question has to still be there afterwards.
        """
        game, tabs = sacked_city
        bob = tabs["Bob"]
        bob.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)

        forged = "99,-99,0"
        assert forged not in game.pending_choice_for("Bob")["options"]
        bob.page.evaluate(FORGE_OPTION, forged)

        bob.page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#notice-region *'))"
            "  .some(n => n.textContent.includes('not one of the options'))",
            timeout=5000,
        )
        assert bob.page.is_visible("#choice-panel"), "the question was closed by a refusal"
        assert game.pending_choice_for("Bob") is not None


# --- The merchant ----------------------------------------------------------


class TestTheMerchantIsOnTheBoard:
    """It is worth a victory point for as long as its owner keeps it, and it
    was in the payload and on no screen: `merchant_hex` and `merchant_holder`
    were both sent, and neither was drawn nor named anywhere."""

    def test_the_piece_is_drawn_on_its_hex(self, merchant):
        """The board is a canvas, so this counts pixels: a piece that is in the
        payload and painted nowhere satisfies every DOM assertion there is."""
        game, tabs = merchant
        alice = tabs["Alice"]
        hex_key = game.merchant_hex
        assert alice.board()["merchant_hex"] == hex_key
        # Before the sampling below, which leaves the canvas holding the frame
        # drawn *without* the piece.
        shot(alice, "merchant-on-the-board-1920x1080")

        with_piece = alice.page.evaluate(SAMPLE_MERCHANT, [hex_key, True])
        without = alice.page.evaluate(SAMPLE_MERCHANT, [hex_key, False])
        assert with_piece != without, "the merchant painted nothing"

    def test_the_holder_is_named_with_the_point_it_scores(self, merchant):
        _, tabs = merchant
        summary = tabs["Bob"].page.inner_text("#award-summary")
        assert "Merchant" in summary, summary
        assert "Alice" in summary and "1 pt" in summary, summary


class TestNothingBrokeOnTheWay:
    def test_no_console_errors(self, sacked_city, harbor, merchant):
        for _, tabs in (sacked_city, harbor, merchant):
            for player in tabs.values():
                assert player.noisy_errors() == []


# --- Page-side helpers -----------------------------------------------------

# Render one frame with and one without the choice rings, reading the pixels
# back around the vertex in between. Both in one call so the page's own render
# loop cannot repaint between drawing and sampling.
SAMPLE_VERTEX = """
([vertexKey, ringed]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    window.BoardRenderer.render(board, 'board-canvas', null, null,
                                ringed ? [vertexKey] : []);

    const layout = window.BoardRenderer.computeLayout(board);
    const point = layout.vertexPositions[vertexKey];
    const client = window.BoardRenderer.boardToClient(
        canvas, point.x + layout.offsetX, point.y + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const half = 20;
    const data = canvas.getContext('2d')
        .getImageData(x - half, y - half, half * 2, half * 2).data;
    return Array.from(data).join(',');
}
"""

# The same, for the merchant: the piece is drawn straight from the payload, so
# the two frames differ by one field rather than by an argument.
SAMPLE_MERCHANT = """
([hexKey, present]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const before = board.merchant_hex;
    board.merchant_hex = present ? hexKey : null;
    window.BoardRenderer.render(board, 'board-canvas', null, null, []);
    board.merchant_hex = before;

    const layout = window.BoardRenderer.computeLayout(board);
    const point = layout.hexPositions[hexKey];
    const client = window.BoardRenderer.boardToClient(
        canvas, point.x + layout.offsetX, point.y + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const half = 26;
    const data = canvas.getContext('2d')
        .getImageData(x - half, y - half, half * 2, half * 2).data;
    return Array.from(data).join(',');
}
"""

# A tampered client: the option list the panel answers from is edited, and a
# button for the forged value is clicked through the client's own listener.
FORGE_OPTION = """
option => {
    const board = window.__catanDebug.getBoard();
    board.pending_choices[0].options.push(option);
    const button = document.createElement('button');
    button.className = 'choice-option';
    button.dataset.choiceOption = option;
    document.getElementById('choice-options').appendChild(button);
    button.click();
}
"""
