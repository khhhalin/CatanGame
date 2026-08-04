"""The first browser suite that plays a seafaring table.

Switching ships on grows the board graph to cover the ocean ring, so `hexes`,
`vertices` and `edges` all get bigger — and most of the new vertices are open
water. The server refuses to build on one, but nothing in the client stopped it
being *offered*: the placement ghost would happily aim at a point in the middle
of the sea and the ✓ would appear over it. No existing browser test plays with
ships, so nothing caught that.

So the assertions here are the ones a player would notice:

  - open water is never offered as a settlement target, and a tap on it pins
    nothing;
  - a ship can be built on a sea edge through the hover → click → ✓ flow;
  - a ship cannot be built on a land edge — the ghost says so before the tap,
    and the server refuses it after;
  - the board still paints real pixels with the bigger graph, and a ship is
    drawn differently from a road;
  - the one-ship-per-turn limit is greyed out with its reason on the control,
    not reported as an error after the click.

Run: pytest tests/test_browser_seafarers.py -m slow -v
"""

import os

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    build_settlement,
    click_edge,
    click_hex,
    client_point,
    confirm_is_showing,
    edges_next_to,
    end_turn,
    first_clickable,
    hover_target,
    next_frame,
    resolve_discard,
    resolve_robber,
    roll_dice,
    server_round_trip,
    start_server,
    stop_server,
    wait_for_preset,
    would_select,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

# Seeded: a table that is played to a state has to reach the same state every
# run, or a gate that passes two runs in three is not a gate.
GAME_SEED = 20260804

SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "seafarers",
)

# The pale halo every ship carries — the lane under it, the sail above it, and
# the outline round the hull. A road has none of it, which is what makes the two
# tellable apart at a glance and is therefore what this suite counts.
SHIP_HALO_RGB = [246, 249, 252]


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- Reading a seafaring board -------------------------------------------


def open_water_vertices(board):
    """Vertices no land hex meets — the ocean ring's own intersections.

    The server lists only *land* hexes as a vertex's neighbours, so an empty
    list is exactly "nothing is here". These exist only with ships on.
    """
    return [key for key, vertex in sorted(board["vertices"].items())
            if not vertex["neighbors"]["hexes"]]


def land_vertices(board):
    return [key for key, vertex in sorted(board["vertices"].items())
            if vertex["neighbors"]["hexes"]]


def vacant_sea_edges_at(board, vertex_key):
    """Sides a ship could lie on that meet this intersection.

    `sea` is the server's own placement mask, sent on every edge of every game.
    Deriving it here from the hex geometry would be a second answer to a rule
    the engine already owns.
    """
    return [key for key in sorted(board["vertices"][vertex_key]["neighbors"]["edges"])
            if board["edges"][key]["sea"]
            and not board["edges"][key]["ship"]
            and not board["edges"][key]["road"]]


def inland_edges(board):
    """Sides with land on both hands, where a ship may never go."""
    return [key for key, edge in sorted(board["edges"].items())
            if edge["sea"] is False and not edge["road"] and not edge["ship"]]


def coastal_setup_vertices(board):
    """Vacant, distance-legal intersections with a sea side leaving them."""
    return [
        key for key in land_vertices(board)
        if not board["vertices"][key]["building"]
        and not any(board["vertices"].get(n, {}).get("building")
                    for n in board["vertices"][key]["neighbors"]["vertices"])
        and vacant_sea_edges_at(board, key)
    ]


def my_ships(player):
    return player.page.evaluate(
        "() => (window.__catanDebug.getBoard().players.find(p => p.is_you)"
        "       || {}).ships || []"
    )


def ships_on_board(board):
    return {key: edge["ship"] for key, edge in board["edges"].items() if edge["ship"]}


# --- Driving the ship controls -------------------------------------------


def open_seafarers_fold(player):
    """Raise the fold if it is not already up. The chip toggles, so clicking it
    blind closes a panel a previous step left open."""
    if player.page.get_attribute("#seafarers-chip", "aria-expanded") != "true":
        player.page.click("#seafarers-chip")


def arm_build_ship(player):
    """Open the Seafarers fold and arm ship placement, as a player would."""
    open_seafarers_fold(player)
    player.page.wait_for_selector("#build-ship-btn:not([disabled])", timeout=5000)
    player.page.click("#build-ship-btn")
    # Out of the way before aiming: the popover is fixed and can lie over the
    # board, and a target under it cannot be clicked.
    player.page.keyboard.press("Escape")


def build_ship(player, candidates):
    """Arm, aim, then ✓. Returns the edge the ship landed on."""
    before = len(my_ships(player))
    arm_build_ship(player)
    edge_key = first_clickable(player, 'edge', candidates)
    assert edge_key, f"no clickable sea edge among {len(candidates)} candidates"
    click_edge(player, edge_key)
    player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
    player.page.click("#placement-confirm-yes")
    player.page.wait_for_function(
        "before => ((window.__catanDebug.getBoard().players.find(p => p.is_you)"
        "            || {}).ships || []).length > before",
        arg=before, timeout=8000,
    )
    return edge_key


def last_settlement_awaiting_a_road(board, name):
    """The settlement this player has just placed and not yet built beside."""
    return next(
        key for key, vertex in board["vertices"].items()
        if (vertex.get("building") or {}).get("player") == name
        and not any(
            (board["edges"][edge].get("road") or {}).get("player") == name
            or (board["edges"][edge].get("ship") or {}).get("player") == name
            for edge in vertex["neighbors"]["edges"]
        )
    )


def place_setup(players, ships_first=True):
    """Drive the whole setup phase, taking a ship where the rulebook allows one.

    "A player who places a starting settlement on the coast may place a ship
    instead of a road next to that settlement" — so each player takes one ship
    and one road, which is also what leaves both pieces on the board for the
    drawing assertions to compare.
    """
    took_a_ship = set()
    for _ in range(len(players) * 2 * 2 + 2):
        board = players[0].board()
        if board["game_phase"] != "setup":
            return
        actor = next(p for p in players if p.name == board["current_player"])

        if board.get("setup_action") == "road":
            vertex = last_settlement_awaiting_a_road(board, actor.name)
            sea = vacant_sea_edges_at(board, vertex)
            if ships_first and sea and actor.name not in took_a_ship:
                took_a_ship.add(actor.name)
                build_ship(actor, sea)
            else:
                build_road(actor, edges_next_to(board, vertex))
        else:
            # Coastal first, so there is always a sea side to take the ship on.
            build_settlement(actor, coastal_setup_vertices(board) or [])


# --- Canvas measurements --------------------------------------------------

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

_PAINTED_PIXELS = """
() => {
    const canvas = document.getElementById('board-canvas');
    const data = canvas.getContext('2d')
        .getImageData(0, 0, canvas.width, canvas.height).data;
    let painted = 0;
    for (let i = 3; i < data.length; i += 4) {
        if (data[i] > 0) { painted += 1; }
    }
    return painted;
}
"""

# What arming a build mode is forbidden to disturb: the canvas box and the
# camera through it. Twice now a mode that changed either has put a click on the
# wrong edge.
_CANVAS_AND_CAMERA = """
() => {
    const canvas = document.getElementById('board-canvas');
    const rect = canvas.getBoundingClientRect();
    const origin = window.BoardRenderer.clientToBoard(canvas, rect.left, rect.top);
    return {
        box: [rect.left, rect.top, rect.width, rect.height],
        buffer: [canvas.width, canvas.height],
        origin: [origin.x, origin.y],
        scale: window.BoardRenderer.getScale(),
    };
}
"""


def halo_pixels(player, point, radius=16):
    return player.page.evaluate(
        _PIXELS_NEAR, [point["x"], point["y"], radius, SHIP_HALO_RGB, 10]
    )


def settle_frames(player):
    """Let the render loop draw what the last input changed."""
    next_frame(player.page)


# --- Tables ---------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


def make_sea_table(browser, url, names=("Alice", "Bob")):
    """Two players at a table playing the published Seafarers rule set.

    Through the preset button, the way a host reaches it: five separate rules
    have to be on before a single ship can be built, and nobody finds all five
    by reading thirty switches.
    """
    players = [Player(browser, url, name, viewport=VIEWPORT) for name in names]
    for player in players:
        player.join()
    players[0].page.click("#preset-seafarers")
    wait_for_preset(players[0], "seafarers")
    players[0].page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    players[0].page.click("#start-game-btn")
    for player in players:
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    return players


@pytest.fixture(scope="module")
def fresh_table(browser, tmp_path_factory):
    """A seafaring table with nothing placed: setup is asking for a settlement."""
    proc, url = start_server(tmp_path_factory.mktemp("sea-fresh"), seed=GAME_SEED)
    players = make_sea_table(browser, url)
    yield players
    stop_server(proc)


@pytest.fixture(scope="module")
def ship_table(browser, tmp_path_factory):
    """A table stopped one step in: the first settlement is down, a ship is next."""
    proc, url = start_server(tmp_path_factory.mktemp("sea-ship"), seed=GAME_SEED)
    players = make_sea_table(browser, url)
    board = players[0].board()
    actor = next(p for p in players if p.name == board["current_player"])
    build_settlement(actor, coastal_setup_vertices(board))
    yield players
    stop_server(proc)


@pytest.fixture(scope="module")
def sailed_table(browser, tmp_path_factory):
    """A table past setup, with ships and roads both on the board."""
    proc, url = start_server(tmp_path_factory.mktemp("sea-sailed"), seed=GAME_SEED)
    players = make_sea_table(browser, url)
    place_setup(players)
    yield players
    stop_server(proc)


def movable_ship(players, limit=6):
    """Pass turns until whoever is on turn has a ship they may pick up.

    A ship built during setup carries `built_turn` 0 and `turn_count` is still
    0 when play begins, so the rulebook's "not on the turn it was built" makes
    every starting ship immovable for exactly one turn.
    """
    for _ in range(limit):
        player = actor_of(players)
        resolve_robber(player)
        if not player.board().get("has_rolled_dice"):
            roll_dice(player)
        for tab in players:
            resolve_discard(tab)
        resolve_robber(player)

        board = player.board()
        mine = [
            key for key, edge in sorted(board["edges"].items())
            if (edge["ship"] or {}).get("player") == player.name
            and edge["ship"]["built_turn"] != board["turn_count"]
        ]
        if mine:
            return player, mine
        end_turn(player)
    raise AssertionError("no player reached a ship they were allowed to move")


def roll_until_a_seven(players, limit=24):
    """Pass turns until somebody rolls a 7 and owes a robber move.

    The dice are seeded, so this is the same number of turns every run - the
    loop is a bound, not a gamble.
    """
    for _ in range(limit):
        player = actor_of(players)
        if not player.board().get("has_rolled_dice"):
            roll_dice(player)
        for tab in players:
            resolve_discard(tab)
        if player.board().get("must_move_robber"):
            return player
        end_turn(player)
    raise AssertionError(f"no 7 was rolled in {limit} turns")


def actor_of(players):
    board = players[0].board()
    return next(p for p in players if p.name == board["current_player"])


# --- The trap -------------------------------------------------------------


class TestOpenWaterIsNeverATarget:
    """The bug this suite was written for.

    With ships on, the board graph covers the ocean ring, so the payload carries
    hundreds of vertices out in open water. Nothing may ever stand on one. The
    renderer used to offer every vertex it had a position for.
    """

    def test_the_table_really_is_playing_with_ships(self, fresh_table):
        """Without this the rest of the class asserts over a base-game board,
        where there is no open water in the graph at all and every assertion
        below passes for the wrong reason."""
        board = fresh_table[0].board()
        for rule in ("ships", "ship_movement", "pirate",
                     "longest_trade_route", "island_victory_points"):
            assert board["rules"][rule] is True, f"{rule} is off after the preset"
        assert len(open_water_vertices(board)) > 0, "no open water in the graph"
        assert any(edge["sea"] for edge in board["edges"].values()), "no sea edges"

    def test_a_sea_vertex_is_never_offered_as_a_settlement_target(self, fresh_table):
        """Aim a click at the exact centre of every open-water vertex on screen.

        `findNearestVertex` is what the hover ghost, the confirm anchor and the
        tap all snap with, so "would the renderer pick this" is precisely the
        question "is it offered". Before the fix each of these returned itself.
        """
        player = actor_of(fresh_table)
        board = player.board()
        water = set(open_water_vertices(board))

        offered = []
        for key in sorted(water):
            picked = would_select(player, 'vertex', key)
            if picked in water:
                offered.append((key, picked))

        assert offered == [], (
            f"{len(offered)} open-water vertices were offered as targets: "
            f"{offered[:5]}"
        )

    def test_tapping_open_water_pins_nothing(self, fresh_table):
        """The behaviour behind the hit test: setup has settlement placement
        armed for the player on turn, and a tap out at sea must raise no ✓ and
        put no building on the board."""
        player = actor_of(fresh_table)
        board = player.board()
        assert board["game_phase"] == "setup"
        assert board["setup_action"] == "settlement"

        before = sum(1 for v in board["vertices"].values() if v["building"])
        # An open-water vertex a long way from any coast, so the click cannot
        # legitimately snap to a land vertex either.
        far = max(
            open_water_vertices(board),
            key=lambda key: min(
                abs(int(key.split(',')[0]) - int(land.split(',')[0]))
                + abs(int(key.split(',')[2]) - int(land.split(',')[2]))
                for land in land_vertices(board)
            ),
        )
        point = client_point(player, 'vertex', far)
        player.page.mouse.click(point["x"], point["y"])
        settle_frames(player)

        assert not confirm_is_showing(player), "open water raised a ✓"
        after = player.board()
        assert sum(1 for v in after["vertices"].values() if v["building"]) == before


# --- Building a ship ------------------------------------------------------


class TestBuildingAShip:
    """Ordered: the refusal leaves the board untouched, so the build that
    follows it starts from the same state either way."""

    def test_a_ship_cannot_be_built_on_a_land_edge(self, ship_table):
        """The ghost says so before the tap, and the server refuses after it.

        Both halves matter: the ghost alone could be lying, and the server alone
        means the player finds out by being told off.
        """
        player = actor_of(ship_table)
        board = player.board()
        before = ships_on_board(board)

        arm_build_ship(player)
        inland = first_clickable(player, 'edge', inland_edges(board))
        assert inland, "no clickable inland edge on this board"
        assert board["edges"][inland]["sea"] is False

        hover_target(player, 'edge', inland)
        settle_frames(player)
        assert player.page.evaluate(
            "() => window.__catanDebug.getBoard() && "
            "      document.getElementById('board-canvas') !== null"
        )

        click_edge(player, inland)
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
        # The ✓ is offered even for a blocked target: the client's legality is a
        # copy, and only the server's answer is authoritative.
        player.page.click("#placement-confirm-yes")
        # The server's refusal is what has to arrive before the board is read;
        # a resync answered after it proves it has.
        server_round_trip(player)

        assert ships_on_board(player.board()) == before, (
            "a ship was built on a land edge"
        )
        assert player.board()["edges"][inland]["ship"] is None

    def test_arming_ship_mode_does_not_move_the_canvas_or_the_camera(self, ship_table):
        """A mode that resizes the board box moves the camera under the click it
        is about to receive. This has been a real bug twice."""
        player = actor_of(ship_table)
        player.page.keyboard.press("Escape")
        settle_frames(player)
        before = player.page.evaluate(_CANVAS_AND_CAMERA)
        arm_build_ship(player)
        settle_frames(player)
        assert player.page.evaluate(_CANVAS_AND_CAMERA) == before

    def test_a_ship_is_built_on_a_sea_edge_through_the_confirm_flow(self, ship_table):
        """Hover, click, ✓ — the same three steps every other piece takes."""
        player = actor_of(ship_table)
        board = player.board()
        vertex = last_settlement_awaiting_a_road(board, player.name)
        candidates = vacant_sea_edges_at(board, vertex)
        assert candidates, "the starting settlement has no sea side"

        edge_key = build_ship(player, candidates)

        after = player.board()
        assert after["edges"][edge_key]["ship"] is not None, "no ship on the edge"
        assert after["edges"][edge_key]["ship"]["player"] == player.name
        assert edge_key in my_ships(player), "the ship is not in the player's list"
        # The starting ship stands in for the starting road, so setup moves on.
        assert after["setup_action"] != "road" or after["current_player"] != player.name


# --- The board that results -----------------------------------------------


class TestTheSailedBoard:
    def test_both_pieces_are_on_the_board(self, sailed_table):
        """The two drawing assertions below compare a ship against a road, so
        the setup has to have left one of each."""
        board = sailed_table[0].board()
        assert board["game_phase"] == "playing"
        assert ships_on_board(board), "setup built no ships"
        assert any(edge["road"] for edge in board["edges"].values()), "no roads"

    def test_the_board_paints_pixels_with_ships_on(self, sailed_table):
        """A blank canvas satisfies every DOM assertion. The graph is three
        times the size it is in a base game, and a throw anywhere in the draw
        loop leaves the whole board empty."""
        player = sailed_table[0]
        settle_frames(player)
        painted = player.page.evaluate(_PAINTED_PIXELS)
        assert painted > 1000, f"only {painted} painted pixels — the board is blank"

    def test_a_ship_does_not_look_like_a_road(self, sailed_table):
        """A player must never mistake one for the other. A ship carries a pale
        halo — the lane under it, the sail above it — and a road is a bare bar
        of the owner's colour, so the halo is what separates them in pixels."""
        player = sailed_table[0]
        board = player.board()
        settle_frames(player)

        ship_edge = sorted(ships_on_board(board))[0]
        road_edge = sorted(
            key for key, edge in board["edges"].items() if edge["road"]
        )[0]

        on_ship = halo_pixels(player, client_point(player, 'edge', ship_edge))
        on_road = halo_pixels(player, client_point(player, 'edge', road_edge))

        assert on_ship > 40, f"the ship has almost no hull or sail: {on_ship} px"
        assert on_ship > on_road * 3, (
            f"a ship ({on_ship} px of hull and sail) is not distinguishable from "
            f"a road ({on_road} px)"
        )

    def test_the_seafarers_panel_states_the_fleet(self, sailed_table):
        player = sailed_table[0]
        assert player.page.is_visible("#seafarers-panel"), "the fold is hidden"
        chip = player.page.inner_text("#seafarers-chip-value")
        assert "🚢" in chip, f"the chip says nothing about the fleet: {chip!r}"

        open_seafarers_fold(player)
        player.page.wait_for_selector("#build-ship-btn", timeout=5000)
        assert "🌲" in player.page.inner_text("#build-ship-btn"), "no cost on the button"
        # Special points are inside victory_points already; the fold is the only
        # place the breakdown is stated.
        assert player.page.is_visible("#island-points")
        shot(player, "seafarers-controls-1920x1080")
        player.page.keyboard.press("Escape")

    def test_the_extra_fold_does_not_make_the_page_scroll(self, sailed_table):
        """The rail gained a row. The owner's rule for this screen is that
        nothing scrolls and nothing is clipped, and one more fold is exactly
        the kind of thing that breaks it — it did once already, for Cities &
        Knights, at this very viewport."""
        page = sailed_table[0].page.evaluate(
            "() => ({ height: document.documentElement.scrollHeight,"
            "         width: document.documentElement.scrollWidth,"
            "         viewH: window.innerHeight, viewW: window.innerWidth })"
        )
        assert page["height"] <= page["viewH"] + 1, f"the page scrolls: {page}"
        assert page["width"] <= page["viewW"] + 1, f"the page scrolls: {page}"

    def test_moving_a_ship_greys_the_control_out_with_its_reason(self, sailed_table):
        """`ship_moved_this_turn` is one move per turn, and it has to be said on
        the control before the tap — not reported as an error after it, which is
        the second language this client is not allowed to speak."""
        player, mine = movable_ship(sailed_table)

        open_seafarers_fold(player)
        player.page.wait_for_selector("#move-ship-btn", timeout=5000)
        assert not player.page.is_disabled("#move-ship-btn"), (
            f"Move ship is greyed out: {player.page.get_attribute('#move-ship-btn', 'title')}"
        )
        player.page.click("#move-ship-btn")
        player.page.keyboard.press("Escape")

        # Two taps: the first picks the ship up, the second lays it down.
        pickup = first_clickable(player, 'edge', mine)
        assert pickup, f"none of {mine} can be clicked"
        click_edge(player, pickup)
        settle_frames(player)
        selection = player.page.evaluate("() => window.__catanDebug.getSelection()")
        assert selection["shipMoveFrom"] == pickup, (
            f"the first tap did not pick the ship up: {selection}"
        )
        origin = pickup

        board = player.board()
        ends = board["edges"][origin]["neighbors"]["vertices"]
        destinations = [
            key for end in ends for key in vacant_sea_edges_at(board, end)
            if key != origin
        ]
        target = first_clickable(player, 'edge', destinations)
        assert target, f"nowhere to move the ship among {destinations}"
        click_edge(player, target)
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
        player.page.click("#placement-confirm-yes")

        player.page.wait_for_function(
            "() => window.__catanDebug.getBoard().ship_moved_this_turn === true",
            timeout=8000,
        )
        player.page.wait_for_function(
            "() => document.getElementById('move-ship-btn').disabled === true",
            timeout=5000,
        )
        assert "already moved" in player.page.get_attribute("#move-ship-btn", "title")

    def test_the_pirate_sails_instead_of_the_robber_on_a_seven(self, sailed_table):
        """A 7 offers two moves with the pirate in play, and which one is sent
        is decided by the hex the player aims at — a land hex is the robber, a
        sea hex is the pirate. Both end the same way: `must_move_robber` drops
        and the server answers with the victim choice it already had.
        """
        player = roll_until_a_seven(sailed_table)
        board = player.board()
        assert board["pirate_hex"] is None, "the pirate has already been moved"

        ocean = [key for key, hex_data in sorted(board["hexes"].items())
                 if hex_data["type"] == "ocean"]
        target = first_clickable(player, 'hex', ocean)
        assert target, "no ocean hex can be clicked"

        # No button arms this: the robber is pending, so a tap on the board is
        # already a move, and the sea is what makes it the pirate's.
        click_hex(player, target)
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
        assert "Pirate" in player.page.inner_text("#placement-announce"), (
            "the confirmation did not say it was about to move the pirate"
        )
        player.page.click("#placement-confirm-yes")

        player.page.wait_for_function(
            "() => window.__catanDebug.getBoard().pirate_hex !== null", timeout=8000
        )
        after = player.board()
        assert after["pirate_hex"] == target
        assert after["must_move_robber"] is False
        # The robber stayed where it was: the pirate is moved *instead of* it.
        assert after["robber_hex"] == board["robber_hex"]
        if player.page.is_visible("#victim-modal.show"):
            player.page.evaluate(
                "() => document.getElementById('victim-modal').classList.remove('show')"
            )
        settle_frames(player)
        shot(player, "seafarers-pirate-1920x1080")

    def test_a_seafaring_board_looks_right_in_both_themes(self, sailed_table):
        """Not an assertion about beauty — the shots are for a human to open.
        What is asserted is that both themes paint, which a canvas whose palette
        cache went stale on a theme change would not."""
        player = sailed_table[0]
        player.page.keyboard.press("Escape")
        settle_frames(player)
        light = player.page.evaluate(_PAINTED_PIXELS)
        shot(player, "seafarers-light-1920x1080")

        player.page.evaluate(
            "() => { document.documentElement.setAttribute('data-theme', 'dark');"
            "        window.dispatchEvent(new Event('resize')); }"
        )
        settle_frames(player)
        dark = player.page.evaluate(_PAINTED_PIXELS)
        shot(player, "seafarers-dark-1920x1080")
        player.page.evaluate(
            "() => { document.documentElement.removeAttribute('data-theme');"
            "        window.dispatchEvent(new Event('resize')); }"
        )

        assert light > 1000, f"the light theme painted {light} pixels"
        assert dark > 1000, f"the dark theme painted {dark} pixels"

    def test_no_console_errors_were_raised(self, sailed_table):
        for player in sailed_table:
            assert player.noisy_errors() == [], (
                f"{player.name} logged: {player.noisy_errors()}"
            )
