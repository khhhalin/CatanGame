"""Hover, then confirm: the two steps a placement now takes, in a browser.

`test_browser_playthrough.py` and `test_browser_full_game.py` play games; this
file is about the interaction itself — that a ghost appears under the cursor,
that a click asks rather than places, that ✓ places and ✗ does not, and that
YOLO mode puts the click back in charge for the one browser that asked for it.

The robber is covered too. It has no button to arm, so the only way to reach it
is to roll a 7, which is why the server here is seeded: the roll that raises the
robber has to be the same roll every run.

Run: pytest tests/test_browser_confirm_placement.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    build_road,
    build_settlement,
    cancel_placement,
    click_edge,
    click_hex,
    click_vertex,
    confirm_is_showing,
    confirm_placement,
    edges_next_to,
    end_turn,
    first_clickable,
    hover_target,
    launch_browser,
    legal_setup_vertices,
    resolve_discard,
    roll_dice,
    set_yolo_mode,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

# Fixed board and dice, so the turn that rolls a 7 is the same one every run.
GAME_SEED = 20260803

# Rolling until a 7 turns up. Twelve turns is far more than the seed needs and
# still bounds the run if the engine's dice ever change.
MAX_TURNS_LOOKING_FOR_A_SEVEN = 24

# What the client draws a refused placement in - board-renderer.js's
# GHOST_BLOCKED_COLOR. Duplicated deliberately: a test that read the constant
# from the module under test would pass whatever it was changed to.
BLOCKED_RGB = [231, 76, 60]

# Carries the target chosen by one test into the next. These tests are steps of
# one interaction, in one game, and splitting them into independent fixtures
# would mean replaying the whole setup phase per assertion.
chosen = {}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("confirm-data"), seed=GAME_SEED)
    yield url
    stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = launch_browser(play)
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def table(browser, server):
    """Two players, both on the default confirm-every-placement path."""
    alice = Player(browser, server, "Alice")
    bob = Player(browser, server, "Bob")
    alice.join()
    bob.join()
    alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    alice.page.click("#start-game-btn")
    for player in (alice, bob):
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    return alice, bob


def actor(table):
    """Whichever tab the server says is on turn."""
    alice, bob = table
    return alice if alice.board()["current_player"] == "Alice" else bob


# Counts pixels near a point that match a colour, which is how a canvas is
# asked what it drew. Everything else about the ghost - that it moved, that it
# is a different thing when the target is illegal - is a comparison of these.
_PIXELS_NEAR = """
([clientX, clientY, radius, rgb, tolerance]) => {
    const canvas = document.getElementById('board-canvas');
    const rect = canvas.getBoundingClientRect();
    const ratio = canvas.width / rect.width;
    const size = Math.max(2, Math.round(radius * 2 * ratio));
    const left = Math.max(0, Math.round((clientX - rect.left) * ratio - size / 2));
    const top = Math.max(0, Math.round((clientY - rect.top) * ratio - size / 2));
    const width = Math.min(size, canvas.width - left);
    const height = Math.min(size, canvas.height - top);
    if (width <= 0 || height <= 0) {
        return 0;
    }
    const data = canvas.getContext('2d').getImageData(left, top, width, height).data;
    let matched = 0;
    for (let i = 0; i < data.length; i += 4) {
        if (Math.abs(data[i] - rgb[0]) <= tolerance
            && Math.abs(data[i + 1] - rgb[1]) <= tolerance
            && Math.abs(data[i + 2] - rgb[2]) <= tolerance) {
            matched += 1;
        }
    }
    return matched;
}
"""

_REGION_SIGNATURE = """
([clientX, clientY, radius]) => {
    const canvas = document.getElementById('board-canvas');
    const rect = canvas.getBoundingClientRect();
    const ratio = canvas.width / rect.width;
    const size = Math.max(2, Math.round(radius * 2 * ratio));
    const left = Math.max(0, Math.round((clientX - rect.left) * ratio - size / 2));
    const top = Math.max(0, Math.round((clientY - rect.top) * ratio - size / 2));
    const data = canvas.getContext('2d').getImageData(left, top, size, size).data;
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) {
        sum += data[i] * ((i % 7) + 1);
    }
    return sum;
}
"""

# The two things the confirm control is forbidden to disturb. Measured together
# so one call answers "is the board where it was, and is it seen the same way?"
_CANVAS_AND_CAMERA = """
() => {
    const canvas = document.getElementById('board-canvas');
    const rect = canvas.getBoundingClientRect();
    const origin = window.BoardRenderer.clientToBoard(canvas, rect.left, rect.top);
    return {
        left: rect.left, top: rect.top, width: rect.width, height: rect.height,
        buffer: [canvas.width, canvas.height],
        originX: origin.x, originY: origin.y,
        scale: window.BoardRenderer.getScale(),
    };
}
"""


def region_signature(player, point, radius=26):
    return player.page.evaluate(_REGION_SIGNATURE, [point["x"], point["y"], radius])


def blocked_pixels(player, point, radius=26):
    return player.page.evaluate(
        _PIXELS_NEAR, [point["x"], point["y"], radius, BLOCKED_RGB, 18]
    )


def settle_frames(player):
    """Let the render loop draw what the last input changed."""
    player.page.wait_for_timeout(250)


def building_count(player):
    return player.page.evaluate(
        "() => Object.values(window.__catanDebug.getBoard().vertices)"
        ".filter(v => v.building).length"
    )


class TestHoverGhost:
    def test_hovering_a_target_draws_a_ghost(self, table):
        player = actor(table)
        board = player.board()
        vertex = first_clickable(player, 'vertex', legal_setup_vertices(board))
        assert vertex, "no clickable vertex to hover"
        chosen["vertex"] = vertex

        point = hover_target(player, 'vertex', vertex)
        # Off the target first, so the comparison is against a board with no
        # ghost on it rather than against the previous frame.
        player.page.mouse.move(point["x"] + 400, point["y"])
        settle_frames(player)
        empty = region_signature(player, point)

        hover_target(player, 'vertex', vertex)
        settle_frames(player)
        hovered = region_signature(player, point)

        assert hovered != empty, "hovering a legal target drew nothing"
        chosen["empty_signature"] = empty

    def test_the_ghost_follows_the_cursor_off_the_target(self, table):
        player = actor(table)
        point = chosen_point(player)
        player.page.mouse.move(point["x"] + 400, point["y"])
        settle_frames(player)
        assert region_signature(player, point) == chosen["empty_signature"], (
            "the ghost stayed behind after the cursor left"
        )


def chosen_point(player):
    return hover_target(player, 'vertex', chosen["vertex"])


class TestClickAsksRatherThanPlaces:
    def test_a_click_does_not_place_anything(self, table):
        player = actor(table)
        before = building_count(player)
        click_vertex(player, chosen["vertex"])
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=3000)
        # Give the server the time it would have needed to answer an emit
        player.page.wait_for_timeout(500)
        assert building_count(player) == before, "the click placed a piece by itself"

    def test_the_confirmation_is_two_named_buttons(self, table):
        player = actor(table)
        names = player.page.eval_on_selector_all(
            "#placement-confirm button",
            "els => els.map(e => [e.tagName, e.getAttribute('aria-label')])",
        )
        assert names == [
            ["BUTTON", "Confirm placement"],
            ["BUTTON", "Cancel placement"],
        ], names

    def test_clicking_elsewhere_moves_the_selection_rather_than_committing(self, table):
        player = actor(table)
        before = building_count(player)
        first = player.page.evaluate(
            "() => document.getElementById('placement-confirm').getBoundingClientRect().x"
        )

        other = next(
            key for key in legal_setup_vertices(player.board())
            if key != chosen["vertex"] and first_clickable(player, 'vertex', [key]) == key
        )
        click_vertex(player, other)
        settle_frames(player)

        assert building_count(player) == before, "a second click committed the first"
        moved = player.page.evaluate(
            "() => document.getElementById('placement-confirm').getBoundingClientRect().x"
        )
        assert moved != first, "the selection did not follow the second click"

        # Put the question back on the target the rest of these tests use
        click_vertex(player, chosen["vertex"])
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=3000)

    def test_the_confirmation_moves_neither_the_canvas_nor_the_camera(self, table):
        """The bug this guards: an in-flow control resizes the board, the camera
        re-fits, and the click that raised it now points somewhere else."""
        player = actor(table)
        with_control = player.page.evaluate(_CANVAS_AND_CAMERA)

        cancel_placement(player)
        settle_frames(player)
        without_control = player.page.evaluate(_CANVAS_AND_CAMERA)

        assert with_control == without_control, (
            f"the confirm control moved the board: {with_control} vs {without_control}"
        )

    def test_cancelling_leaves_the_build_mode_armed(self, table):
        player = actor(table)
        assert not confirm_is_showing(player), "✗ left the control on screen"

        # Still armed: the same click raises the same question again, with no
        # need to press the build button a second time.
        click_vertex(player, chosen["vertex"])
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=3000)

    def test_escape_cancels_as_well(self, table):
        player = actor(table)
        before = building_count(player)
        player.page.keyboard.press("Escape")
        player.page.wait_for_function(
            "() => document.getElementById('placement-confirm')"
            ".classList.contains('hidden')",
            timeout=3000,
        )
        player.page.wait_for_timeout(400)
        assert building_count(player) == before, "Escape placed the piece"

    def test_confirming_places_the_settlement(self, table):
        player = actor(table)
        before = building_count(player)
        click_vertex(player, chosen["vertex"])
        assert confirm_placement(player), "no confirmation was raised"
        player.page.wait_for_function(
            "before => Object.values(window.__catanDebug.getBoard().vertices)"
            ".filter(v => v.building).length > before",
            arg=before, timeout=8000,
        )
        assert not confirm_is_showing(player), "the control outlived the placement"

    def test_enter_confirms_the_road_that_follows(self, table):
        player = actor(table)
        board = player.board()
        settlement = next(
            key for key, vertex in board["vertices"].items()
            if (vertex.get("building") or {}).get("player") == player.name
        )
        edges = edges_next_to(board, settlement)
        edge = first_clickable(player, 'edge', edges)
        assert edge, "no clickable road beside the settlement"

        click_edge(player, edge)
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=3000)
        player.page.keyboard.press("Enter")
        player.page.wait_for_function(
            "owner => Object.values(window.__catanDebug.getBoard().edges)"
            ".filter(e => (e.road || {}).player === owner).length > 0",
            arg=player.name, timeout=8000,
        )


class TestBlockedGhost:
    def test_an_illegal_target_is_drawn_differently_from_a_legal_one(self, table):
        """"Nothing there" and "not allowed there" have to look different."""
        player = actor(table)
        board = player.board()

        occupied = next(
            key for key, vertex in board["vertices"].items() if vertex.get("building")
        )
        assert first_clickable(player, 'vertex', [occupied]) == occupied, (
            "the settlement already placed is not reachable by a click"
        )

        blocked_point = hover_target(player, 'vertex', occupied)
        settle_frames(player)
        on_blocked = blocked_pixels(player, blocked_point)

        legal = first_clickable(player, 'vertex', legal_setup_vertices(board))
        legal_point = hover_target(player, 'vertex', legal)
        settle_frames(player)
        on_legal = blocked_pixels(player, legal_point)

        assert on_blocked > on_legal, (
            f"the blocked ghost is not distinct: {on_blocked} vs {on_legal} "
            "pixels of the refusal colour"
        )


class TestYoloMode:
    def test_the_toggle_starts_off_so_confirming_is_the_default(self, table):
        alice, bob = table
        for player in (alice, bob):
            assert player.page.is_checked("#yolo-mode-toggle") is False

    def test_switching_it_on_is_remembered_by_the_browser(self, table):
        player = actor(table)
        set_yolo_mode(player, True)
        stored = player.page.evaluate(
            "() => window.localStorage.getItem('catan.yoloMode')"
        )
        assert stored == "1", f"YOLO mode was not persisted: {stored!r}"

    def test_a_click_places_immediately_with_no_confirmation(self, table):
        player = actor(table)
        before = building_count(player)
        vertex = first_clickable(player, 'vertex', legal_setup_vertices(player.board()))
        assert vertex, "no clickable vertex"
        click_vertex(player, vertex)
        player.page.wait_for_function(
            "before => Object.values(window.__catanDebug.getBoard().vertices)"
            ".filter(v => v.building).length > before",
            arg=before, timeout=8000,
        )
        assert not confirm_is_showing(player), "YOLO mode still asked"

    def test_the_hover_ghost_is_still_drawn_in_yolo_mode(self, table):
        player = actor(table)
        board = player.board()
        settlement = next(
            key for key, vertex in sorted(board["vertices"].items())
            if (vertex.get("building") or {}).get("player") == player.name
        )
        edge = first_clickable(player, 'edge', edges_next_to(board, settlement))
        assert edge, "no clickable road beside the settlement"

        point = hover_target(player, 'edge', edge)
        player.page.mouse.move(point["x"] + 400, point["y"] + 400)
        settle_frames(player)
        empty = region_signature(player, point)

        hover_target(player, 'edge', edge)
        settle_frames(player)
        assert region_signature(player, point) != empty, "no ghost in YOLO mode"

        chosen["yolo_edge"] = edge

    def test_switching_it_off_brings_the_confirmation_back(self, table):
        player = actor(table)
        set_yolo_mode(player, False)
        assert player.page.evaluate(
            "() => window.localStorage.getItem('catan.yoloMode')"
        ) == "0"

        click_edge(player, chosen["yolo_edge"])
        assert confirm_placement(player), "the confirmation did not come back"
        player.page.wait_for_function(
            "owner => Object.values(window.__catanDebug.getBoard().edges)"
            ".filter(e => (e.road || {}).player === owner).length > 0",
            arg=player.name, timeout=8000,
        )


class TestTheRobberConfirmsToo:
    """The robber has no armed mode - it is implicit while the server says a 7
    is outstanding - so it is the one placement that could have been missed."""

    def test_the_rest_of_setup_can_be_played(self, table):
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}

        for _step in range(8):
            board = alice.board()
            if board["game_phase"] != "setup":
                break
            player = by_name[board["current_player"]]
            vertex = build_settlement(player, legal_setup_vertices(board))
            build_road(player, edges_next_to(player.board(), vertex))

        assert alice.board()["game_phase"] == "playing"

    def test_a_seven_raises_a_ghost_and_a_confirmation_for_the_robber(self, table):
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}

        player = None
        for _turn in range(MAX_TURNS_LOOKING_FOR_A_SEVEN):
            board = alice.board()
            player = by_name[board["current_player"]]
            if not board.get("has_rolled_dice"):
                roll_dice(player)
            for tab in (alice, bob):
                resolve_discard(tab)
            if player.board().get("must_move_robber"):
                break
            end_turn(player)
        else:
            pytest.fail("no 7 was rolled, so the robber flow never came up")

        board = player.board()
        target = first_clickable(player, 'hex', [
            key for key, hex_data in board["hexes"].items()
            if hex_data["type"] != "ocean" and key != board.get("robber_hex")
        ])
        assert target, "no reachable hex to move the robber to"

        point = hover_target(player, 'hex', target)
        player.page.mouse.move(point["x"] + 300, point["y"])
        settle_frames(player)
        empty = region_signature(player, point, radius=30)

        hover_target(player, 'hex', target)
        settle_frames(player)
        assert region_signature(player, point, radius=30) != empty, (
            "the robber has no hover ghost"
        )

        click_hex(player, target)
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=3000)
        player.page.wait_for_timeout(400)
        assert player.board()["must_move_robber"] is True, (
            "the click moved the robber without being confirmed"
        )

        player.page.click("#placement-confirm-yes")
        player.page.wait_for_function(
            "() => window.__catanDebug.getBoard().must_move_robber === false",
            timeout=8000,
        )

    def test_no_console_errors_through_any_of_it(self, table):
        for player in table:
            assert player.noisy_errors() == [], f"{player.name}: {player.noisy_errors()}"
