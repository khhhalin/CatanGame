"""What a city wall looks like, checked in a real browser.

A player could spend two brick on a wall and see nothing at all: the engine
recorded it, the panel counted it, and the board had no art for it. That is the
same class of bug as the knights that were invisible for six builds — the game
state was perfect and the pixels were empty — so it is tested the same way, by
counting pixels rather than by asking the DOM.

The wall is drawn under the city and broken towards the top right, which is
where a knight sharing the intersection steps to. Both of those are load-bearing
and both are asserted here: a wall that covers the city it protects, or the
knight standing with it, is worse than no wall.

Run: pytest tests/test_browser_walls.py -m slow -v
"""

import os

import pytest
from browser_harness import (
    Player,
    launch_browser,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

# Screenshots of the thing this suite is about, kept for a human to look at.
SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "walls",
)

# The rules the Cities & Knights preset ticks. Named individually rather than
# through the retired `cities_and_knights` flag - there are no modes.
CITIES_AND_KNIGHTS = {
    "commodities": True, "city_improvements": True, "metropolis": True,
    "knights": True, "barbarians": True, "city_walls": True,
    "progress_cards": True, "setup_second_city": True,
    "victory_target": 13,
}

SET_RULES = """
async rules => {
    const socket = (await import('/static/js/socket.js')).socket;
    socket.emit('set_rules', { rules });
}
"""

# Put a city, a wall and any knights on the client's copy of the board. The
# server will not hand out two brick and a city on demand, and the subject here
# is the renderer: what it draws for a given payload.
PUT_WALLED_CITY = """
([vertexKey, owner, walled, knights]) => {
    const board = window.__catanDebug.getBoard();
    board.vertices[vertexKey].building = { player: owner, type: 'city' };
    board.cities_knights.city_wall_vertices = walled ? { [owner]: [vertexKey] } : {};
    board.cities_knights.knights[owner] = knights || [];
}
"""

# Render one frame and read a patch back. Both in the same call so the page's
# own render loop cannot repaint between them.
RENDER_AND_SAMPLE = """
([vertexKey, offsetPx, half]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    window.BoardRenderer.render(board, 'board-canvas', null, null);

    const layout = window.BoardRenderer.computeLayout(board);
    const point = layout.vertexPositions[vertexKey];
    const rect = canvas.getBoundingClientRect();
    const client = window.BoardRenderer.boardToClient(
        canvas,
        point.x + layout.offsetX + offsetPx[0],
        point.y + layout.offsetY + offsetPx[1]
    );
    const ratio = canvas.width / rect.width;
    const centreX = Math.round((client.x - rect.left) * ratio);
    const centreY = Math.round((client.y - rect.top) * ratio);
    const reach = Math.round(half * ratio);

    const x = Math.max(0, centreX - reach);
    const y = Math.max(0, centreY - reach);
    const width = Math.min(canvas.width - x, reach * 2);
    const height = Math.min(canvas.height - y, reach * 2);
    return Array.from(canvas.getContext('2d').getImageData(x, y, width, height).data);
}
"""

# Half-widths in CSS pixels. The wall reaches 16px from the vertex, the city is
# 16px across, and a knight steps 16px up and right.
WALL_PATCH = 26
CITY_PATCH = 6
KNIGHT_PATCH = 11
KNIGHT_OFFSET = (16, -16)


def differing_pixels(before, after):
    assert len(before) == len(after), "patches must be the same size to compare"
    return sum(1 for index in range(0, len(before), 4)
               if before[index:index + 4] != after[index:index + 4])


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = launch_browser(play)
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def table(browser, tmp_path_factory):
    """A Cities & Knights game, which is the only game walls exist in."""
    proc, url = start_server(tmp_path_factory.mktemp("walls-data"))
    alice = Player(browser, url, "Alice", viewport={"width": 1920, "height": 1080})
    bob = Player(browser, url, "Bob")
    alice.join()
    bob.join()
    alice.page.evaluate(SET_RULES, CITIES_AND_KNIGHTS)
    alice.page.wait_for_timeout(400)
    alice.page.click("#start-game-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    alice.page.wait_for_timeout(600)
    yield alice
    stop_server(proc)


def _inland_vertex(player):
    """A vertex ringed by land, so the patch sampled is terrain and not sea."""
    board = player.board()
    for key, vertex in sorted(board["vertices"].items()):
        hexes = vertex["neighbors"]["hexes"]
        if len(hexes) == 3 and all(
            board["hexes"][h]["type"] not in ("ocean", "desert") for h in hexes
        ):
            return key
    raise AssertionError("no inland vertex on this board")


def _sample(player, vertex_key, offset=(0, 0), half=WALL_PATCH):
    return player.page.evaluate(RENDER_AND_SAMPLE, [vertex_key, list(offset), half])


def _close_up(player, vertex_key, half=60):
    """A screenshot clip centred on one intersection."""
    point = player.page.evaluate(
        """([key]) => {
            const canvas = document.getElementById('board-canvas');
            const layout = window.BoardRenderer.computeLayout(
                window.__catanDebug.getBoard());
            const vertex = layout.vertexPositions[key];
            return window.BoardRenderer.boardToClient(
                canvas, vertex.x + layout.offsetX, vertex.y + layout.offsetY);
        }""",
        [vertex_key],
    )
    return {"x": point["x"] - half, "y": point["y"] - half,
            "width": half * 2, "height": half * 2}


def _put(player, vertex_key, walled, knights=None):
    player.page.evaluate(PUT_WALLED_CITY, [vertex_key, "Alice", walled, knights or []])


class TestThePayloadStillNamesTheWalledCities:
    """The renderer draws from `city_wall_vertices`. A rename there is invisible
    on screen and silent in every other test, so it is pinned here."""

    def test_walls_are_reported_per_player(self, table):
        walls = table.board()["cities_knights"]["city_wall_vertices"]
        assert set(walls) == {"Alice", "Bob"}, walls
        assert walls["Alice"] == [], "nobody has built a wall yet"


class TestAWallIsActuallyDrawn:
    """Regression: two brick bought a wall that appeared nowhere on the board."""

    def test_it_paints_pixels_around_the_city(self, table):
        vertex = _inland_vertex(table)
        _put(table, vertex, walled=False)
        bare = _sample(table, vertex)
        _put(table, vertex, walled=True)
        walled = _sample(table, vertex)

        changed = differing_pixels(bare, walled)
        assert changed > 200, f"only {changed} pixels changed - the wall is not drawn"

    def test_the_city_it_protects_is_not_covered(self, table):
        """The wall is drawn before the city, so the piece always wins the middle."""
        vertex = _inland_vertex(table)
        _put(table, vertex, walled=False)
        bare = _sample(table, vertex, half=CITY_PATCH)
        _put(table, vertex, walled=True)
        walled = _sample(table, vertex, half=CITY_PATCH)

        assert differing_pixels(bare, walled) == 0, (
            "the wall painted over the city standing inside it"
        )

    def test_a_knight_on_the_same_vertex_is_not_covered(self, table):
        """The ring is broken exactly where a knight sharing the vertex steps."""
        vertex = _inland_vertex(table)
        knight = [{"vertex": vertex, "rank": 2, "active": True}]

        _put(table, vertex, walled=False, knights=knight)
        without = _sample(table, vertex, offset=KNIGHT_OFFSET, half=KNIGHT_PATCH)
        _put(table, vertex, walled=True, knights=knight)
        with_wall = _sample(table, vertex, offset=KNIGHT_OFFSET, half=KNIGHT_PATCH)

        assert differing_pixels(without, with_wall) == 0, (
            "the wall reached into the knight standing with the city"
        )

    def test_two_walled_cities_side_by_side_do_not_run_together(self, table):
        """Vertices are 35px apart; a ring wider than half that would merge."""
        board = table.board()
        vertex = _inland_vertex(table)
        neighbour = next(
            key for key in board["vertices"][vertex]["neighbors"]["vertices"]
            if key in board["vertices"]
        )
        gap = table.page.evaluate(
            """([a, b]) => {
                const layout = window.BoardRenderer.computeLayout(
                    window.__catanDebug.getBoard());
                const first = layout.vertexPositions[a];
                const second = layout.vertexPositions[b];
                return Math.hypot(first.x - second.x, first.y - second.y);
            }""",
            [vertex, neighbour],
        )
        # 16 is WALL_MERLON_HIGH in board-renderer.js; two rings of it must
        # still leave daylight between neighbouring intersections.
        assert gap > 2 * 16, f"neighbouring vertices are only {gap:.1f}px apart"


class TestTheGhostShowsTheWallItWouldBuild:
    """A wall used to preview as a plain blob, which said "here" but not what.

    The ghost is drawn last of everything, so this also pins that a wall already
    standing on the vertex cannot hide the preview of the next one.
    """

    def test_aiming_a_wall_previews_a_wall(self, table):
        vertex = _inland_vertex(table)
        _put(table, vertex, walled=False)
        without = _sample(table, vertex)

        with_ghost = table.page.evaluate(
            RENDER_AND_SAMPLE.replace(
                "window.BoardRenderer.render(board, 'board-canvas', null, null)",
                "window.BoardRenderer.render(board, 'board-canvas', null, "
                "{ kind: 'city_wall', key: vertexKey, color: '#ffffff' })",
            ),
            [vertex, [0, 0], WALL_PATCH],
        )
        changed = differing_pixels(without, with_ghost)
        assert changed > 200, f"only {changed} pixels changed - no wall ghost is drawn"


class TestItLooksRightToAHuman:
    """Screenshots are the point of this suite as much as the assertions are."""

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_a_walled_city_screenshots_in_both_themes(self, table, theme):
        vertex = _inland_vertex(table)
        table.page.emulate_media(color_scheme=theme)
        os.makedirs(SHOT_DIR, exist_ok=True)

        for label, knights in (
            ("wall", []),
            ("wall-and-knight", [{"vertex": vertex, "rank": 3, "active": True}]),
        ):
            _put(table, vertex, walled=True, knights=knights)
            table.page.evaluate(
                "() => window.BoardRenderer.render("
                "window.__catanDebug.getBoard(), 'board-canvas', null, null)"
            )
            table.page.screenshot(path=os.path.join(SHOT_DIR, f"{label}-{theme}.png"))
            # And the piece itself, big enough to judge by eye: a wall is 36px
            # across on a 1920-wide board, which no full-page shot resolves.
            table.page.screenshot(
                path=os.path.join(SHOT_DIR, f"{label}-{theme}-close.png"),
                clip=_close_up(table, vertex),
            )

        table.page.emulate_media(color_scheme="light")

    def test_no_console_errors(self, table):
        assert table.noisy_errors() == []
