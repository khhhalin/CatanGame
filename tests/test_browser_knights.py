"""Knights and city walls, driven in a real browser for the first time.

Building a knight, moving one and building a city wall have never been clicked
by any test. They are the placements that need a hand before they can be
reached at all — a knight is 1 sheep and 1 ore, a wall is 2 brick — and a
browser test that has to roll for that hand is not a gate. So the hand, the
roads and the cities are arranged with the real engine and written to the save
file the server restores on boot, exactly as `test_browser_pending_choice.py`
does. Everything after the save — the panel, the arming, the ✓, the emit, the
server's answer and the redraw — is the real client and the real server.

What is covered, and why each one is here:

  - a knight is built through the arm → tap → ✓ flow, and the hand pays for it;
  - the board stops asking for a knight once one has landed. This is the
    tester's bug: a build mode is deliberately left armed across board updates
    so a two-tap knight move cannot be interrupted, and the cost of that was
    that a *successful* placement left the board armed and the next tap
    anywhere built a second knight. The fix reads the answer off the board
    (`expectPlacement`/`clearSettledPlacement`) and has never been under test;
  - a knight move is two taps, and the first one only picks the knight up —
    nothing is sent, so there is nothing to confirm;
  - a city wall is built, and is drawn on the city it protects and on no other;
  - a knight sharing an intersection with a building does not hide it. No legal
    move puts the two there — that is a rule the engine enforces — so this one
    is arranged in the state a restored payload can still carry.

Each test gets its own server: every scenario is an arranged hand, and a shared
one would have the earlier tests spend it.

Run: pytest tests/test_browser_knights.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    browser_session,
    click_vertex,
    first_clickable,
    next_frame,
    start_server,
    stop_server,
)
from game import cities_knights as ck_module
from game import persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(REPO, "test-artifacts", "ui", "knights")

TABLE = ["Alice", "Bob"]

KNIGHT_COST = {"sheep": 1, "ore": 1}
CITY_WALL_COST = {"brick": 2}

EMPTY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0}


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- Arranging a hand ------------------------------------------------------


def _inland_vertices(game):
    """Intersections ringed by three land hexes, well in from the coast.

    A coastal one is just as legal; an inland one keeps the pixel comparisons
    off the ocean, where the board draws a wave pattern of its own.
    """
    return [
        key for key in sorted(game.vertices)
        if len(game.vertices[key].neighbors["hexes"]) == 3
        and all(game.hexes[h].type != "ocean"
                for h in game.vertices[key].neighbors["hexes"])
    ]


def _roads_around(game, player_name, vertex_key):
    """Give the player every road leaving one intersection.

    A knight may only stand where its owner has a road and it marches along
    them, so this is the smallest network that makes both legal: the
    intersection itself and each of its three neighbours.
    """
    player = game.get_player(player_name)
    for edge_key in game.vertices[vertex_key].neighbors["edges"]:
        game.edges[edge_key].road = {"player": player_name}
        player.roads.append(edge_key)


def _hand(game, player_name, **cards):
    player = game.get_player(player_name)
    player.resources.update(EMPTY_HAND)
    player.resources.update(cards)


def _give_city(game, player_name, vertex_key):
    game.vertices[vertex_key].building = {"type": "city", "player": player_name}
    game.get_player(player_name).cities.append(vertex_key)


def _distance(one, other):
    return sum(
        abs(int(a) - int(b))
        for a, b in zip(one.split(","), other.split(","), strict=True)
    )


def build_game(build):
    """A started Cities & Knights game, mid-turn, with `build` applied.

    The dice are already up: everything here is a build, and the client greys
    every build out before the roll. `build` returns the landmarks its scenario
    arranged, which is how a test knows where to aim.
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
#
# Each hands the player on turn exactly what the action costs and nothing else,
# so "the hand paid for it" is not something the fixture can satisfy by
# accident.


def a_hand_for_one_knight(game):
    """Roads to stand on, and 1 sheep + 1 ore: one knight and no more."""
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor, **KNIGHT_COST)
    return {"home": home, "spots": list(game.vertices[home].neighbors["vertices"])}


def an_active_knight(game):
    """A knight from an earlier turn, active and ready to march.

    Placed here rather than in the browser because a knight may never act on
    the turn it was built or the turn it was activated — a movable knight is
    two more turns of rolling away through the UI alone.
    """
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor)

    spots = list(game.vertices[home].neighbors["vertices"])
    knight = ck_module.Knight(spots[0])
    knight.active = True
    game.ck.knights_of(actor).append(knight)
    return {"home": home, "standing": spots[0], "spots": spots}


def two_cities_and_the_brick_for_one_wall(game):
    """Two cities and exactly one wall's worth of brick.

    Two, because "the wall is drawn on the city it protects" is only an
    assertion if there is another city it must *not* appear on.
    """
    actor = game.current_player_name()
    inland = _inland_vertices(game)
    home = inland[0]
    # As far apart as the island allows, so neither city's footprint can reach
    # into the pixels sampled around the other.
    other = max(inland, key=lambda key: _distance(key, home))
    _give_city(game, actor, home)
    _give_city(game, actor, other)
    _hand(game, actor, **CITY_WALL_COST)
    return {"home": home, "other": other}


def a_knight_standing_on_a_settlement(game):
    """A knight and a settlement on one intersection, arranged in the state.

    No legal move puts them there: a knight goes on a vacant intersection and
    a settlement will not go up where a knight stands. But a payload can still
    carry both — a save written before that rule was enforced restores one —
    and the renderer offsets the knight so the building underneath survives.
    That offset is what this arranges, because the flows cannot.
    """
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor)

    game.vertices[home].building = {"type": "settlement", "player": actor}
    game.get_player(actor).settlements.append(home)
    game.ck.knights_of(actor).append(ck_module.Knight(home))
    return {"home": home}


# --- Fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.fixture
def knight_hand(browser, tmp_path):
    with table(browser, tmp_path, a_hand_for_one_knight) as live:
        yield live


@pytest.fixture
def marching_knight(browser, tmp_path):
    with table(browser, tmp_path, an_active_knight) as live:
        yield live


@pytest.fixture
def walled_cities(browser, tmp_path):
    with table(browser, tmp_path, two_cities_and_the_brick_for_one_wall) as live:
        yield live


@pytest.fixture
def knight_under_a_building(browser, tmp_path):
    with table(browser, tmp_path, a_knight_standing_on_a_settlement) as live:
        yield live


# --- Driving the controls --------------------------------------------------


def open_knights_fold(player):
    """Raise the Knights fold if it is not already up. The chip toggles, so
    clicking it blind closes a panel a previous step left open."""
    if player.page.get_attribute("#knights-chip", "aria-expanded") != "true":
        player.page.click("#knights-chip")


def arm(player, button_id):
    """Open the fold and arm one of the three board modes, as a player would.

    The popover is fixed and can lie over the board, so it is dismissed before
    anything is aimed at: a target underneath it cannot be clicked at all.
    """
    open_knights_fold(player)
    player.page.wait_for_selector(f"#{button_id}:not([disabled])", timeout=5000)
    player.page.click(f"#{button_id}")
    player.page.keyboard.press("Escape")


def selection(player):
    return player.page.evaluate("() => window.__catanDebug.getSelection()")


def knights_of(player, name=None):
    return player.page.evaluate(
        "owner => (window.__catanDebug.getBoard().cities_knights.knights[owner] || [])",
        name or player.name,
    )


def wall_vertices(player, name=None):
    return player.page.evaluate(
        "owner => (window.__catanDebug.getBoard().cities_knights"
        ".city_wall_vertices[owner] || [])",
        name or player.name,
    )


def hand(player):
    return dict((player.me() or {}).get("resources") or {})


def settle_frames(player):
    """Let the render loop draw what the last input changed."""
    next_frame(player.page)


def aim(player, candidates):
    """The first of these intersections a click would actually land on.

    A canvas click snaps to the nearest target within a radius, so aiming at a
    point is not the same as hitting it.
    """
    key = first_clickable(player, "vertex", list(candidates))
    assert key, f"none of {list(candidates)} can be aimed at"
    click_vertex(player, key)
    return key


def confirm(player, expected_noun):
    """Press ✓, having checked the control says what it is about to place."""
    player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
    announced = player.page.inner_text("#placement-announce")
    assert expected_noun in announced, (
        f"the confirmation said {announced!r}, not {expected_noun!r}"
    )
    player.page.click("#placement-confirm-yes")


def aim_and_confirm(player, candidates, noun):
    key = aim(player, candidates)
    confirm(player, noun)
    return key


def wait_for_knight_at(player, vertex_key):
    player.page.wait_for_function(
        "([owner, vertex]) => (window.__catanDebug.getBoard().cities_knights"
        "  .knights[owner] || []).some(k => k.vertex === vertex)",
        arg=[player.name, vertex_key], timeout=8000,
    )


def wait_for_wall_at(player, vertex_key):
    player.page.wait_for_function(
        "([owner, vertex]) => (window.__catanDebug.getBoard().cities_knights"
        "  .city_wall_vertices[owner] || []).includes(vertex)",
        arg=[player.name, vertex_key], timeout=8000,
    )


def armed_state(player):
    """What a player can see about whether the board is still asking for a
    piece: the highlighted button, the placement cursor, and the half-finished
    selection a two-tap move leaves behind."""
    state = selection(player)
    return {
        "mode": state["mode"],
        "knightMoveFrom": state["knightMoveFrom"],
        "buttons": player.page.evaluate(
            "() => ['build-knight-btn', 'move-knight-btn', 'build-wall-btn']"
            "  .filter(id => document.getElementById(id).classList.contains('active'))"
        ),
        "board": player.page.evaluate(
            "() => document.getElementById('game-board')"
            "  .classList.contains('placement-mode')"
        ),
    }


DISARMED = {"mode": None, "knightMoveFrom": None, "buttons": [], "board": False}


# --- Building a knight -----------------------------------------------------


class TestBuildingAKnight:
    def test_a_knight_is_built_through_the_confirm_flow(self, knight_hand):
        """Arm, tap, ✓ — the three steps every other piece takes, and the hand
        pays for it. Nothing has ever clicked this before."""
        player, marks = knight_hand

        assert hand(player) == {**EMPTY_HAND, **KNIGHT_COST}
        arm(player, "build-knight-btn")
        spot = aim_and_confirm(player, marks["spots"], "Knight")

        wait_for_knight_at(player, spot)
        placed = knights_of(player)
        assert [k["vertex"] for k in placed] == [spot]
        # A new knight is basic and inactive: it takes grain to wake it up.
        assert placed[0]["rank"] == 1 and placed[0]["active"] is False
        assert hand(player) == EMPTY_HAND, "the sheep and ore were not spent"

        open_knights_fold(player)
        assert "Basic" in player.page.inner_text("#knight-list")
        shot(player, "knight-built-1920x1080")
        player.page.keyboard.press("Escape")

    def test_the_board_stops_asking_for_a_knight_once_one_is_placed(self, knight_hand):
        """The tester's bug, finally under test.

        A build mode survives every board update on purpose — a knight move is
        two taps, and someone else's trade landing between them must not disarm
        it halfway. The cost of that was that a *successful* build left the
        board armed and the next tap anywhere tried to build a second knight.
        The fix reads the answer off the board the server sent, and until now
        nothing has ever driven a knight placement to find out whether it works.
        """
        player, marks = knight_hand

        arm(player, "build-knight-btn")
        assert selection(player)["mode"] == "knight", "arming did nothing"
        spot = aim_and_confirm(player, marks["spots"], "Knight")
        wait_for_knight_at(player, spot)
        settle_frames(player)

        assert armed_state(player) == DISARMED

        # And why it matters: a tap on another legal intersection is no longer
        # a placement at all.
        elsewhere = [key for key in marks["spots"] if key != spot]
        aim(player, elsewhere)
        settle_frames(player)
        assert player.page.is_hidden("#placement-confirm"), (
            "a tap after the placement pinned another knight"
        )
        assert [k["vertex"] for k in knights_of(player)] == [spot]

    def test_the_knight_is_drawn_where_it_was_placed(self, knight_hand):
        """The board is a canvas: a piece that is in the payload and painted
        nowhere satisfies every DOM assertion there is, so count the pixels."""
        player, marks = knight_hand

        arm(player, "build-knight-btn")
        spot = aim_and_confirm(player, marks["spots"], "Knight")
        wait_for_knight_at(player, spot)
        settle_frames(player)

        with_knight = player.page.evaluate(SAMPLE_VERTEX, [spot, False, 0, 0, 14])
        without = player.page.evaluate(SAMPLE_VERTEX, [spot, True, 0, 0, 14])
        changed = differing(with_knight, without)
        assert changed > 100, (
            f"only {changed} pixels of the intersection changed — the knight's "
            f"shield is 16x19 and should cover far more than that"
        )


# --- Moving a knight -------------------------------------------------------


class TestMovingAKnight:
    def test_the_first_tap_only_picks_the_knight_up(self, marching_knight):
        """A move is two taps. The first sends nothing — there is nothing to
        undo yet, so there is nothing to confirm either, and the board must not
        raise a ✓ over a knight nobody has asked to go anywhere."""
        player, marks = marching_knight
        standing = marks["standing"]

        arm(player, "move-knight-btn")
        assert aim(player, [standing]) == standing
        settle_frames(player)

        assert selection(player)["knightMoveFrom"] == standing, (
            "the first tap did not pick the knight up"
        )
        assert player.page.is_hidden("#placement-confirm"), "picking up raised a ✓"
        assert [k["vertex"] for k in knights_of(player)] == [standing], (
            "the knight moved before it was confirmed"
        )
        open_knights_fold(player)
        assert "Now tap the intersection to move it to." in player.page.inner_text(
            "#knight-hint"
        )
        player.page.keyboard.press("Escape")

    def test_the_second_tap_moves_it_and_leaves_the_board_unarmed(self, marching_knight):
        """The other half of the two-tap flow, and the disarm that goes with it:
        a move settles on the knight having *left* where it stood, which is a
        different test from the one a build settles on."""
        player, marks = marching_knight
        standing = marks["standing"]

        arm(player, "move-knight-btn")
        aim(player, [standing])
        settle_frames(player)
        destination = aim_and_confirm(
            player, [key for key in marks["spots"] if key != standing], "Knight move"
        )

        wait_for_knight_at(player, destination)
        moved = knights_of(player)
        assert [k["vertex"] for k in moved] == [destination]
        # Acting always spends a knight; grain reactivates it on a later turn.
        assert moved[0]["active"] is False
        settle_frames(player)

        assert armed_state(player) == DISARMED
        shot(player, "knight-moved-1920x1080")


# --- City walls ------------------------------------------------------------


class TestBuildingACityWall:
    def test_a_wall_is_built_through_the_confirm_flow(self, walled_cities):
        """Two brick, tapped onto one of the player's own cities."""
        player, marks = walled_cities
        home = marks["home"]

        assert hand(player) == {**EMPTY_HAND, **CITY_WALL_COST}
        arm(player, "build-wall-btn")
        aim_and_confirm(player, [home], "City wall")

        wait_for_wall_at(player, home)
        assert wall_vertices(player) == [home]
        assert hand(player) == EMPTY_HAND, "the brick was not spent"
        settle_frames(player)
        assert armed_state(player) == DISARMED, (
            "the board stayed in wall-building mode after the wall went up"
        )

        open_knights_fold(player)
        assert "1/3" in player.page.inner_text("#build-wall-btn")
        player.page.keyboard.press("Escape")

    def test_the_wall_is_drawn_on_the_city_it_protects_and_no_other(self, walled_cities):
        """A wall was two brick spent on a number in a panel and nothing on the
        board at all. The player's second city is the control: the rampart has
        to appear around one of them and not around the other."""
        player, marks = walled_cities
        home, other = marks["home"], marks["other"]

        arm(player, "build-wall-btn")
        aim_and_confirm(player, [home], "City wall")
        wait_for_wall_at(player, home)
        settle_frames(player)
        shot(player, "city-wall-1920x1080")

        walled = player.page.evaluate(STONE_PIXELS, [home, 26])
        unwalled = player.page.evaluate(STONE_PIXELS, [other, 26])
        assert walled > 60, f"the walled city has only {walled}px of rampart on it"
        assert unwalled < walled / 4, (
            f"the unwalled city shows {unwalled}px of rampart against {walled}px "
            f"on the walled one"
        )

    def test_the_wall_goes_under_the_city_and_does_not_hide_it(self, walled_cities):
        """The rampart is drawn first and the city over the top of it, so the
        piece a player is looking for is never covered by its own defences."""
        player, marks = walled_cities
        home = marks["home"]

        before = player.page.evaluate(SAMPLE_VERTEX, [home, True, 0, 0, 6])

        arm(player, "build-wall-btn")
        aim_and_confirm(player, [home], "City wall")
        wait_for_wall_at(player, home)
        settle_frames(player)

        after = player.page.evaluate(SAMPLE_VERTEX, [home, True, 0, 0, 6])
        assert after == before, "the wall painted over the city it protects"


# --- A knight and a building on one intersection ---------------------------


class TestAKnightSharingAnIntersection:
    def test_a_knight_steps_off_a_built_intersection(self, knight_under_a_building):
        """Both pieces stand on the point, so one of them has to move aside.

        The knight steps up and to the right with a leader line back to the
        point, and the building's own footprint is untouched.
        """
        player, marks = knight_under_a_building
        spot = marks["home"]

        wait_for_knight_at(player, spot)
        settle_frames(player)
        shot(player, "knight-sharing-a-vertex-1920x1080")
        assert knights_of(player)[0]["vertex"] == spot

        # The building's own footprint, with the knight in the payload and with
        # it taken out: identical means nothing of the knight was drawn over it.
        with_knight = player.page.evaluate(SAMPLE_VERTEX, [spot, False, 0, 0, 6])
        without = player.page.evaluate(SAMPLE_VERTEX, [spot, True, 0, 0, 6])
        assert with_knight == without, (
            "the knight is drawn over the building sharing its intersection"
        )

        # And it really is on screen — up and to the right, which is where the
        # rampart leaves its gap.
        stepped = player.page.evaluate(SAMPLE_VERTEX, [spot, False, 16, -16, 12])
        empty = player.page.evaluate(SAMPLE_VERTEX, [spot, True, 16, -16, 12])
        changed = differing(stepped, empty)
        assert changed > 100, (
            f"only {changed} pixels changed up and to the right of the building "
            f"— the knight did not step off it, it vanished"
        )


class TestNothingBrokeOnTheWay:
    def test_no_console_errors(self, knight_hand, marching_knight, walled_cities):
        for player, _ in (knight_hand, marching_knight, walled_cities):
            assert player.noisy_errors() == [], (
                f"{player.name}: {player.noisy_errors()}"
            )


# --- Page-side helpers -----------------------------------------------------


def differing(one, other):
    """How many of the sampled pixels the two frames disagree about.

    Not "how many pixels are opaque": the board paints terrain edge to edge, so
    every sample is opaque everywhere and counting that measures nothing.
    """
    left = one.split(",")
    right = other.split(",")
    assert len(left) == len(right), "the two samples cover different areas"
    return sum(
        1 for index in range(0, len(left), 4)
        if left[index:index + 4] != right[index:index + 4]
    )


# Render one frame and read the pixels back around a point offset from a
# vertex, optionally with the knights taken out of the payload first. Both in
# one call, so the page's own render loop cannot repaint in between, and the
# board is put back before it returns.
SAMPLE_VERTEX = """
([vertexKey, hideKnights, offsetX, offsetY, half]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const ck = board.cities_knights;
    const saved = ck.knights;
    if (hideKnights) { ck.knights = {}; }
    window.BoardRenderer.render(board, 'board-canvas', null, null, []);
    ck.knights = saved;

    const layout = window.BoardRenderer.computeLayout(board);
    const point = layout.vertexPositions[vertexKey];
    const client = window.BoardRenderer.boardToClient(
        canvas, point.x + offsetX + layout.offsetX, point.y + offsetY + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = canvas.width / rect.width;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const data = canvas.getContext('2d')
        .getImageData(x - half, y - half, half * 2, half * 2).data;
    return Array.from(data).join(',');
}
"""

# How much pale rampart stone is painted around an intersection. The wall's
# colours are fixed rather than themed - it sits on a player-coloured piece on a
# terrain fill - so they are what tells a walled city from a bare one.
STONE_PIXELS = """
([vertexKey, radius]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const layout = window.BoardRenderer.computeLayout(board);
    const point = layout.vertexPositions[vertexKey];
    const client = window.BoardRenderer.boardToClient(
        canvas, point.x + layout.offsetX, point.y + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = canvas.width / rect.width;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const size = Math.round(radius * 2 * dpr);
    const data = canvas.getContext('2d')
        .getImageData(x - size / 2, y - size / 2, size, size).data;

    // #b9c4d0 stone and #f4f8fb halo, the two passes of the rampart.
    const stone = [[185, 196, 208], [244, 248, 251]];
    let matched = 0;
    for (let i = 0; i < data.length; i += 4) {
        for (const rgb of stone) {
            if (Math.abs(data[i] - rgb[0]) <= 8
                && Math.abs(data[i + 1] - rgb[1]) <= 8
                && Math.abs(data[i + 2] - rgb[2]) <= 8) {
                matched += 1;
                break;
            }
        }
    }
    return matched;
}
"""
