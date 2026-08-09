"""What each seafaring rule does, driven in a real browser.

This file used to play 141 turns of a seeded two-player game to a winner. It
cost five minutes - two fifths of the whole browser suite - and what it proved
depended on what the dice happened to produce: whichever rules that particular
run walked past were tested, and the rest were carried along for the ride.

So the game is gone and the rules are here one at a time. Each scenario is
arranged with the real engine and written to the save file the server restores
on boot, exactly as `test_browser_knights.py` and `test_browser_awards.py` do,
and then driven through the real canvas and the real buttons. Everything after
the save - the panel, the arming, the tap, the emit, the server's answer and
the redraw - is the client and the server a player uses.

What the long game asserted, and where each of those now lives:

  - a declared winner on a seafaring table, announced on screen
        -> TestAWinIsDeclaredOnASeafaringTable
  - the Longest Trade Route counting ships alongside roads, and the award
    panel naming who holds it
        -> TestAShipCompletesTheTradeRoute
  - a 7 answered by sailing the pirate
        -> TestThePirateAnswersASeven, which also takes the card the pirate
           steals and shows that it blocks the sides of the hex it sits on -
           neither of which the long game ever reached
  - the fleet stated in the Seafarers fold, a board still painted, no console
    errors -> asserted on the arranged tables, which carry ships, an island
           and a pirate at once

And two rules the long game never exercised at all, because nothing in it ever
tried: moving a ship, and the special victory points for reaching an island.

The lobby class below is unchanged: the preset, the picker and the starting
ship are the sea rules a table meets before the first roll.

Run: pytest tests/test_browser_seafaring_game.py -m slow -v
"""

import os
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    _arm_build,
    browser_session,
    build_road,
    build_settlement,
    build_ship,
    can_afford,
    click_edge,
    click_hex,
    click_vertex,
    confirm_placement,
    count_ships,
    edges_next_to,
    first_clickable,
    legal_settlement_vertices,
    open_seafarers_fold,
    reveal_rule,
    server_round_trip,
    start_server,
    stop_server,
    wait_for_rule,
)
from game import persistence
from seafarers_board import (
    build_ships_along,
    coastal_vertex,
    give_building,
    inland_edges_at,
    other_end,
    sea_edges_at,
    seafarers_game,
    ship_path,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

TABLE = ["Alice", "Bob"]

# The shortest game the picker allows. Both are real settings a table can
# choose, which is why a scenario may use them: a five-point game is a game.
VICTORY_TARGET = 5
LONGEST_ROAD_MINIMUM = 2

# Fixed board and dice.
GAME_SEED = 20260805

SETTLEMENT_COST = {"wood": 1, "brick": 1, "wheat": 1, "sheep": 1}
SHIP_COST = {"wood": 1, "sheep": 1}
EMPTY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0}


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("sea-game-data"), seed=GAME_SEED)
    yield url
    stop_server(proc)


@pytest.fixture(scope="module")
def table(browser, server):
    """Two seats, both in YOLO mode.

    A bot clicking through a setup phase has nothing to gain from confirming
    each placement, and the confirm flow is covered where it belongs —
    `test_browser_seafarers.py` builds and moves every ship through it.
    """
    alice = Player(browser, server, "Alice", yolo=True)
    bob = Player(browser, server, "Bob", yolo=True)
    alice.join()
    bob.join()
    return alice, bob


def set_rule(player, rule_id, value):
    """Set one rule through the picker, as a host would.

    `reveal_rule` is what makes the control clickable: the groups are
    `<details>`, and the picker is not even rendered yet when `join()` returns.
    """
    reveal_rule(player, rule_id)
    control = player.page.locator(f"#rule-{rule_id}")
    control.scroll_into_view_if_needed()
    control.fill(str(value))
    # The picker submits on `change`; blurring guarantees it fires.
    control.blur()
    wait_for_rule(player, rule_id, value)


# --- Reading a seafaring board --------------------------------------------


def coastal_setup_vertices(board):
    """Vacant, distance-legal intersections with a sea side leaving them.

    With ships on, the graph reaches out over the water, so most of the
    vertices in the payload are open sea and nothing may ever stand on one —
    the server lists land hexes only, so an empty list is exactly "this is at
    sea". Coastal, because a starting settlement with no sea side has no ship
    to place beside it.
    """
    return [
        key for key, vertex in sorted(board["vertices"].items())
        if vertex["neighbors"]["hexes"]
        and not vertex["building"]
        and not any(board["vertices"].get(n, {}).get("building")
                    for n in vertex["neighbors"]["vertices"])
        and any(board["edges"][edge]["sea"] and not board["edges"][edge]["ship"]
                and not board["edges"][edge]["road"]
                for edge in vertex["neighbors"]["edges"])
    ]


# Classic pips: how many of the 36 dice combinations each token pays out on.
PIPS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}

# What a ship costs. A seat that starts nowhere near either of them cannot
# build a ship all game however long the game runs, which is not a seafaring
# game at all — so the starting settlements are chosen for them, the way a
# person chooses a corner.
SHIP_RESOURCES = ("wood", "sheep")


def setup_ranking(board):
    """Coastal starting corners, the ones that pay for ships first.

    Scored the way a player scores a corner: the pips it collects, counting the
    two resources a ship is made of double. Picking the first legal vertex
    instead is what left an earlier run of this suite with two seats that never
    saw a sheep in eighty-six turns, and so never built a ship in a game whose
    whole subject is ships.
    """
    def score(vertex_key):
        total = 0
        for hex_key in board["vertices"][vertex_key]["neighbors"]["hexes"]:
            hex_data = board["hexes"][hex_key]
            pips = PIPS.get(hex_data.get("number"), 0)
            total += pips * (2 if hex_data["type"] in SHIP_RESOURCES else 1)
        return total

    return sorted(coastal_setup_vertices(board), key=score, reverse=True)


def sea_edges_of(board, vertex_key):
    return [
        key for key in sorted(board["vertices"][vertex_key]["neighbors"]["edges"])
        if board["edges"][key]["sea"]
        and not board["edges"][key]["ship"]
        and not board["edges"][key]["road"]
    ]


def ships_of(board, name):
    return sorted(
        key for key, edge in board["edges"].items()
        if (edge.get("ship") or {}).get("player") == name
    )


def roads_of(board, name):
    return sorted(
        key for key, edge in board["edges"].items()
        if (edge.get("road") or {}).get("player") == name
    )


def hand_of(player):
    return dict((player.me() or {}).get("resources") or {})


# --- The lobby -------------------------------------------------------------


class TestATableThatPlaysWithShips:
    def test_the_seafarers_preset_turns_every_sea_rule_on(self, table):
        """Through the preset button, the way a host reaches it: five rules
        have to be on before a single ship can be built, and nobody finds all
        five by reading thirty switches."""
        alice, bob = table
        alice.page.wait_for_function(
            "() => document.querySelectorAll('#players li').length === 2", timeout=8000
        )
        alice.page.click("#preset-seafarers")
        alice.page.wait_for_function(
            "() => window.__catanDebug.getRules().selected.ships === true", timeout=8000
        )

        chosen = alice.page.evaluate("() => window.__catanDebug.getRules().selected")
        for rule in ("ships", "ship_movement", "pirate",
                     "longest_trade_route", "island_victory_points"):
            assert chosen[rule] is True, f"{rule} is off after the preset"

    def test_the_host_can_shorten_the_game_through_the_picker(self, table):
        """The preset plays to 14 points, which is a two-hour game for a bot.
        The victory target and the trade-route minimum are real settings, so
        shortening the game this way is a table's choice and not a back door."""
        alice, bob = table
        set_rule(alice, "victory_target", VICTORY_TARGET)
        set_rule(alice, "longest_road_minimum", LONGEST_ROAD_MINIMUM)

        # Rule changes are table-wide, so the other tab must see them too.
        bob.page.wait_for_function(
            "target => document.getElementById('rule-victory_target').value === String(target)",
            arg=VICTORY_TARGET, timeout=8000,
        )

    def test_the_game_starts_with_the_chosen_rules_in_the_engine(self, table):
        """A picker that displays a value the engine ignored is worse than no
        picker at all, so check the running game's own rules."""
        alice, bob = table
        alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
        alice.page.click("#start-game-btn")
        for player in table:
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)

        rules = alice.board()["rules"]
        assert rules["victory_target"] == VICTORY_TARGET
        assert rules["longest_road_minimum"] == LONGEST_ROAD_MINIMUM
        assert rules["longest_trade_route"] is True and rules["ships"] is True

    def test_setup_is_played_by_clicking_and_takes_a_ship_where_it_may(self, table):
        """"A player who places a starting settlement on the coast may place a
        ship instead of a road next to that settlement" — so each seat takes one
        ship and one road, which is also what leaves the game with both kinds of
        piece for the trade route to count."""
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}
        took_a_ship = set()
        placements = 0

        for _step in range(len(by_name) * 4 + 4):
            board = alice.board()
            if board["game_phase"] != "setup":
                break
            actor = by_name[board["current_player"]]

            if board.get("setup_action") == "road":
                vertex = last_settlement_awaiting_a_piece(board, actor.name)
                sea = sea_edges_of(board, vertex)
                if sea and actor.name not in took_a_ship:
                    took_a_ship.add(actor.name)
                    build_ship(actor, sea)
                else:
                    build_road(actor, edges_next_to(board, vertex))
            else:
                build_settlement(actor, setup_ranking(board))
            placements += 1

        assert alice.board()["game_phase"] == "playing", (
            f"setup did not finish after {placements} placements"
        )
        board = alice.board()
        assert sorted(took_a_ship) == ["Alice", "Bob"], (
            "neither seat could take a starting ship, so no game is being sailed"
        )
        for name in ("Alice", "Bob"):
            assert ships_of(board, name), f"{name} has no ship on the board"
            assert roads_of(board, name), f"{name} has no road on the board"
        alice.shot("sea-01-setup-complete")


def last_settlement_awaiting_a_piece(board, name):
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


# --- Arranging one rule at a time -----------------------------------------
#
# Every scenario below hands the player on turn exactly what the action needs
# and nothing else, so "the rule did it" is not something the fixture can
# satisfy by accident.


def _hand(game, player_name, **cards):
    player = game.get_player(player_name)
    player.resources.update(EMPTY_HAND)
    player.resources.update(cards)


def _roads_from(game, player_name, vertex_key, length):
    """Lay an unbranched run of this player's roads inland from one corner.

    Long enough that the far end is distance-legal for a settlement, which is
    what makes a build reachable in one click rather than in several turns.
    """
    player = game.get_player(player_name)
    at = vertex_key
    laid = []
    for _ in range(length):
        edge_key = next(
            key for key in sorted(inland_edges_at(game, at))
            if key not in laid and not game.edges[key].road and not game.edges[key].ship
        )
        game.edges[edge_key].road = {"player": player_name}
        player.roads.append(edge_key)
        laid.append(edge_key)
        at = other_end(game, edge_key, at)
    return laid, at


def build_sea_game(build, **rules):
    """A started seafaring game, mid-turn, with `build` applied.

    The dice are already up: every scenario is a build or a move, and the
    client greys all of them out before the roll.
    """
    game = seafarers_game(
        TABLE, seed=GAME_SEED,
        victory_target=VICTORY_TARGET,
        longest_road_minimum=LONGEST_ROAD_MINIMUM,
        **rules,
    )
    game.set_dice_rolled()
    return game, build(game)


@contextmanager
def arranged(browser, data_dir, build, **rules):
    """A running server restored from `build`, with both seats connected."""
    game, marks = build_sea_game(build, **rules)
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
        yield tabs, marks
    finally:
        stop_server(proc)


# --- A win on a seafaring table -------------------------------------------


def one_settlement_short_of_the_target(game):
    """Alice on four points with the hand for the fifth.

    Two cities are four victory points and need no roads to stand up; the road
    run beside one of them is what makes a fifth building reachable in a single
    click. The hand is exactly a settlement, so the win cannot come from
    anything else she could have afforded.
    """
    actor = "Alice"
    home = coastal_vertex(game, with_inland_edge=True)
    give_building(game, actor, home, "city")

    roads, far_end = _roads_from(game, actor, home, 2)
    # A second city well away from the first, so neither blocks the target.
    other = max(
        (key for key, vertex in sorted(game.vertices.items())
         if vertex.neighbors["hexes"] and not vertex.building
         and not any(game.vertices[n].building for n in vertex.neighbors["vertices"])),
        key=lambda key: sum(
            abs(int(a) - int(b))
            for a, b in zip(key.split(","), home.split(","), strict=True)
        ),
    )
    give_building(game, actor, other, "city")
    _hand(game, actor, **SETTLEMENT_COST)
    return {"home": home, "roads": roads, "far_end": far_end}


@pytest.fixture
def one_point_from_a_win(browser, tmp_path):
    with arranged(browser, tmp_path, one_settlement_short_of_the_target) as live:
        yield live


class TestAWinIsDeclaredOnASeafaringTable:
    """The victory check on a table with ships, the pirate and islands on.

    Nothing about winning is seafaring-specific in the rulebook, which is
    exactly why it is worth clicking here: the seafaring board carries three
    times the graph and two extra sources of victory points, and "the game
    ends" is the one thing a player cannot work around.
    """

    def test_the_table_really_is_a_seafaring_one(self, one_point_from_a_win):
        """Without this the rest of the class asserts over a base game."""
        tabs, _ = one_point_from_a_win
        rules = tabs["Alice"].board()["rules"]
        for rule in ("ships", "pirate", "longest_trade_route",
                     "island_victory_points"):
            assert rules[rule] is True, f"{rule} is off"
        assert rules["victory_target"] == VICTORY_TARGET

    def test_the_building_that_reaches_the_target_ends_the_game(
        self, one_point_from_a_win
    ):
        """Built by clicking, from a hand that pays for exactly one settlement
        and one point short of the target the table chose."""
        tabs, _ = one_point_from_a_win
        alice = tabs["Alice"]

        assert alice.me()["victory_points"] == VICTORY_TARGET - 1, (
            f"the fixture did not leave Alice one point short: {alice.me()}"
        )
        assert can_afford(alice.me(), SETTLEMENT_COST)

        board = alice.board()
        build_settlement(alice, legal_settlement_vertices(board, "Alice"))

        alice.page.wait_for_function(
            "target => (window.__catanDebug.getBoard().players"
            "    .find(p => p.is_you) || {}).victory_points >= target",
            arg=VICTORY_TARGET, timeout=8000,
        )
        assert alice.me()["victory_points"] >= VICTORY_TARGET

    def test_both_tabs_are_told_the_game_is_over(self, one_point_from_a_win):
        """The banner is the only thing that announces a winner to a human, and
        it has to reach the seat that lost as well as the one that won."""
        tabs, _ = one_point_from_a_win
        alice = tabs["Alice"]
        build_settlement(alice, legal_settlement_vertices(alice.board(), "Alice"))

        for player in tabs.values():
            player.page.wait_for_function(
                "() => [...document.querySelectorAll('#notice-region *')]"
                "        .some(el => el.textContent.toUpperCase().includes('GAME OVER'))",
                timeout=8000,
            )
            text = " ".join(player.notices())
            assert "Alice" in text, (
                f"{player.name} was told the game ended without being told by "
                f"whom: {text!r}"
            )

    def test_no_console_errors(self, one_point_from_a_win):
        tabs, _ = one_point_from_a_win
        for player in tabs.values():
            assert player.noisy_errors() == [], f"{player.name}: {player.noisy_errors()}"


# --- The Longest Trade Route counts ships ---------------------------------


def a_route_one_ship_short(game):
    """Roads inland and ships out to sea, meeting at Alice's settlement.

    Three segments against a minimum the table set at two — so the route is
    already hers, and the ship built in the browser has to lengthen it past
    every road she owns. Roads and ships only chain into one route where their
    owner has a building at the intersection they meet on (expansions.md 81),
    which is what the settlement is here for.
    """
    actor = "Alice"
    home = coastal_vertex(game, with_inland_edge=True)
    give_building(game, actor, home)

    roads, _ = _roads_from(game, actor, home, 2)
    ships, reached = ship_path(game, home, 1)
    build_ships_along(game, actor, ships)
    reached = reached[-1]
    game.update_longest_road()

    _hand(game, actor, **SHIP_COST)
    return {"home": home, "roads": roads, "ships": ships, "reached": reached}


@pytest.fixture
def a_mixed_route(browser, tmp_path):
    with arranged(browser, tmp_path, a_route_one_ship_short) as live:
        yield live


class TestAShipCompletesTheTradeRoute:
    """The whole difference between the Longest Road and the Longest Trade
    Route is that ships count too (expansions.md 79). A route longer than every
    road its owner has on the board can only be made of both, so that is the
    shape of the proof — and the ship that makes it so is built by clicking."""

    def test_the_route_is_the_trade_route_and_not_the_road(self, a_mixed_route):
        tabs, _ = a_mixed_route
        text = tabs["Alice"].page.inner_text("#award-summary")
        assert "Longest Trade Route" in text
        assert "Longest Road" not in text

    def test_a_ship_built_by_clicking_lengthens_the_route_past_the_roads(
        self, a_mixed_route
    ):
        tabs, marks = a_mixed_route
        alice = tabs["Alice"]

        board = alice.board()
        before = board["longest_road_length"].get("Alice", 0)
        assert can_afford(alice.me(), SHIP_COST)

        build_ship(alice, sea_edges_of(board, marks["reached"]))

        alice.page.wait_for_function(
            "before => (window.__catanDebug.getBoard().longest_road_length"
            "    || {}).Alice > before",
            arg=before, timeout=8000,
        )

        board = alice.board()
        length = board["longest_road_length"]["Alice"]
        assert length > len(roads_of(board, "Alice")), (
            f"a route of {length} over {len(roads_of(board, 'Alice'))} roads and "
            f"{len(ships_of(board, 'Alice'))} ships counted no ship at all"
        )
        assert board["longest_road_holder"] == "Alice", (
            f"nobody holds the route: {board['longest_road_holder']!r}"
        )
        alice.shot("sea-02-trade-route")

    def test_the_award_panel_names_who_holds_the_route(self, a_mixed_route):
        """An award in the payload and on no screen is one nobody is playing
        for — which is exactly what Longest Road was before it was put here."""
        alice = a_mixed_route[0]["Alice"]
        holder = alice.board()["longest_road_holder"]
        summary = alice.page.inner_text("#award-summary")
        assert holder in summary, f"the award panel does not name {holder}: {summary!r}"

    def test_the_seafarers_fold_states_the_fleet(self, a_mixed_route):
        alice = a_mixed_route[0]["Alice"]
        open_seafarers_fold(alice)
        chip = alice.page.inner_text("#seafarers-chip-value")
        assert "/" in chip, f"the chip says nothing about the fleet: {chip!r}"
        assert alice.page.query_selector(
            "#seafarers-chip-value use[href='#i-ship']"
        ) is not None, f"the fleet's ship glyph is missing: {chip!r}"
        assert alice.page.is_visible("#island-points")
        alice.page.keyboard.press("Escape")

    def test_the_board_is_painted_with_a_fleet_on_it(self, a_mixed_route):
        """A blank canvas satisfies every DOM assertion, and the graph here is
        three times the size of a base game's."""
        alice = a_mixed_route[0]["Alice"]
        painted = alice.page.evaluate("""
            () => {
                const canvas = document.getElementById('board-canvas');
                const data = canvas.getContext('2d')
                    .getImageData(0, 0, canvas.width, canvas.height).data;
                let count = 0;
                for (let i = 3; i < data.length; i += 4) {
                    if (data[i] !== 0) count++;
                }
                return count;
            }
        """)
        assert painted > 1000, f"only {painted} painted pixels — the board is blank"


# --- The pirate -----------------------------------------------------------


def a_seven_owed_with_bobs_ship_at_sea(game):
    """A 7 outstanding against Alice, and one of Bob's ships out on the water.

    The pirate is not armed by anything: the player who owes the move simply
    taps a sea hex, and the server reads that as the pirate rather than the
    robber. Bob holds one card, so "a card was stolen" is a hand of one going
    to nothing rather than an arithmetic coincidence.
    """
    home = coastal_vertex(game, with_inland_edge=True)
    give_building(game, "Bob", home)
    ships, _ = ship_path(game, home, 1)
    build_ships_along(game, "Bob", ships)

    _hand(game, "Bob", wheat=1)
    _hand(game, "Alice")

    # The sea hex Bob's ship lies against, which is where the pirate has to go
    # to reach him.
    target = next(
        key for key in sorted(game.edges[ships[0]].neighbors["hexes"])
        if game.hexes[key].type == "ocean"
    )
    game.must_move_robber = True
    return {"ship": ships[0], "hex": target, "home": home}


@pytest.fixture
def a_seven_at_sea(browser, tmp_path):
    with arranged(browser, tmp_path, a_seven_owed_with_bobs_ship_at_sea) as live:
        yield live


class TestThePirateAnswersASeven:
    def test_tapping_a_sea_hex_sails_the_pirate_instead_of_the_robber(
        self, a_seven_at_sea
    ):
        """A 7 offers two moves on a seafaring table and which one is sent is
        decided by where the player taps. Nothing on screen arms it."""
        tabs, marks = a_seven_at_sea
        alice = tabs["Alice"]

        assert alice.board()["must_move_robber"] is True
        assert alice.board().get("pirate_hex") is None, "the pirate has already sailed"

        click_hex(alice, marks["hex"])
        confirm_placement(alice)
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().must_move_robber === false",
            timeout=8000,
        )

        board = alice.board()
        assert board["pirate_hex"] == marks["hex"], (
            f"the pirate is on {board.get('pirate_hex')!r}, not the hex that was "
            f"tapped ({marks['hex']!r})"
        )
        alice.shot("sea-03-pirate-sailed")

    def test_the_pirate_takes_a_card_from_the_ship_it_caught(self, a_seven_at_sea):
        """The pirate "steals from a player who has a ship adjacent to it"
        (expansions.md 108), and the card really leaves the other hand.

        Bob is the only seat with a ship beside that hex, and with one victim
        the client sends the choice itself rather than asking a question with a
        single answer — so what a player sees is simply the card arriving.
        """
        tabs, marks = a_seven_at_sea
        alice, bob = tabs["Alice"], tabs["Bob"]

        assert sum(hand_of(bob).values()) == 1, (
            f"the fixture did not leave Bob exactly one card: {hand_of(bob)}"
        )
        assert sum(hand_of(alice).values()) == 0, (
            f"the fixture did not leave Alice empty-handed: {hand_of(alice)}"
        )

        click_hex(alice, marks["hex"])
        confirm_placement(alice)

        alice.page.wait_for_function(
            "() => (window.__catanDebug.getBoard().players.find(p => p.is_you)"
            "        || {}).resources.wheat === 1",
            timeout=8000,
        )
        bob.page.wait_for_function(
            "() => Object.values((window.__catanDebug.getBoard().players"
            "    .find(p => p.is_you) || {}).resources || {})"
            "    .reduce((a, b) => a + b, 0) === 0",
            timeout=8000,
        )

    def test_the_pirate_blocks_every_side_of_the_hex_it_sits_on(self, a_seven_at_sea):
        """"The pirate blocks every side of the hex it sits on" — Bob's ship is
        against that hex, so the side beyond it may not be sailed on to."""
        tabs, marks = a_seven_at_sea
        alice, bob = tabs["Alice"], tabs["Bob"]

        click_hex(alice, marks["hex"])
        confirm_placement(alice)
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().must_move_robber === false",
            timeout=8000,
        )

        board = bob.board()
        blocked = [
            key for key in sorted(board["edges"])
            if board["edges"][key]["sea"] and not board["edges"][key]["ship"]
            and not board["edges"][key]["road"]
            and marks["hex"] in board["edges"][key]["neighbors"]["hexes"]
            and any(vertex in board["edges"][marks["ship"]]["neighbors"]["vertices"]
                    for vertex in board["edges"][key]["neighbors"]["vertices"])
        ]
        assert blocked, "the fixture left no blocked side beside Bob's ship"

        assert bob.page.evaluate(
            "([board, key, me]) => window.BoardRenderer.shipCanLie"
            "    ? window.BoardRenderer.shipCanLie(board, key, me) : null",
            [board, blocked[0], "Bob"],
        ) in (False, None), "the client offers a pirate-blocked side as a target"

        # The server is the authority, so ask it: Bob is not on turn, but a
        # refused build leaves the board exactly as it was either way.
        before = ships_of(bob.board(), "Bob")
        bob.page.evaluate(
            """async ([name, edge]) => {
                const socket = (await import('/static/js/socket.js')).socket;
                socket.emit('build_ship', { name, edge_key: edge });
            }""",
            ["Bob", blocked[0]],
        )
        server_round_trip(bob)
        assert ships_of(bob.board(), "Bob") == before, (
            "a ship was built on a side the pirate blocks"
        )


# --- Moving a ship --------------------------------------------------------


def an_open_ship_from_an_earlier_turn(game):
    """A run of two ships out from Alice's settlement, both laid before today.

    A ship may not be moved on the turn it was built, and only a ship with a
    free end may be moved at all — so the far one is the only legal pick-up on
    this board, which is what makes "it moved" mean the rule and not luck.
    """
    actor = "Alice"
    home = coastal_vertex(game, with_inland_edge=True)
    give_building(game, actor, home)
    ships, reached = ship_path(game, home, 2)
    build_ships_along(game, actor, ships)
    game.update_longest_road()
    _hand(game, actor)
    return {
        "home": home, "ships": ships, "far": ships[-1], "reached": reached[-1],
        "destinations": _legal_destinations(game, actor, ships[-1]),
    }


def _legal_destinations(game, player_name, from_edge):
    """Every side this ship could legally be laid down on, asked of the engine.

    The rulebook's "the ship's new position must satisfy all of the normal
    rules for placing a new ship" spelled out in the engine's own terms, so the
    test aims where the server would actually accept rather than at a guess
    that happens to be a dead end on this board.
    """
    return [
        key for key in sorted(game.edges)
        if key != from_edge
        and game.is_sea_edge(key)
        and game.edges[key].ship is None
        and game.edges[key].road is None
        and not game.pirate_blocks_edge(key)
        and game.ship_connects(player_name, key, ignoring=from_edge)
    ]


@pytest.fixture
def a_movable_ship(browser, tmp_path):
    with arranged(browser, tmp_path, an_open_ship_from_an_earlier_turn) as live:
        yield live


class TestAShipIsMoved:
    """Ship movement has never been driven in a browser. `test_browser_
    seafarers.py` checks that the control greys out with its reason once a move
    has been spent; the move itself — two taps, the first of which sends
    nothing — has only ever run in a unit fixture."""

    def test_the_first_tap_picks_the_ship_up_and_sends_nothing(self, a_movable_ship):
        tabs, marks = a_movable_ship
        alice = tabs["Alice"]

        open_seafarers_fold(alice)
        alice.page.wait_for_selector("#move-ship-btn:not([disabled])", timeout=8000)
        alice.page.click("#move-ship-btn")
        alice.page.keyboard.press("Escape")

        before = ships_of(alice.board(), "Alice")
        click_edge(alice, marks["far"])
        alice.page.wait_for_function(
            "from => window.__catanDebug.getSelection().shipMoveFrom === from",
            arg=marks["far"], timeout=8000,
        )
        server_round_trip(alice)
        assert ships_of(alice.board(), "Alice") == before, (
            "picking a ship up moved it"
        )

    def test_the_second_tap_moves_it(self, a_movable_ship):
        tabs, marks = a_movable_ship
        alice = tabs["Alice"]

        open_seafarers_fold(alice)
        alice.page.wait_for_selector("#move-ship-btn:not([disabled])", timeout=8000)
        alice.page.click("#move-ship-btn")
        alice.page.keyboard.press("Escape")

        before = ships_of(alice.board(), "Alice")
        destinations = marks["destinations"]
        assert destinations, "the fixture left the ship nowhere to sail to"

        click_edge(alice, marks["far"])
        alice.page.wait_for_function(
            "from => window.__catanDebug.getSelection().shipMoveFrom === from",
            arg=marks["far"], timeout=8000,
        )
        landed = first_clickable(alice, 'edge', destinations)
        assert landed, f"none of {destinations} could be clicked"
        click_edge(alice, landed)
        # The second tap asks before it moves, exactly as a build does; only
        # the first one - picking the ship up - sends nothing to confirm.
        confirm_placement(alice)

        alice.page.wait_for_function(
            "([gone, arrived]) => {"
            "  const edges = window.__catanDebug.getBoard().edges;"
            "  return !edges[gone].ship && (edges[arrived].ship || {}).player === 'Alice'; }",
            arg=[marks["far"], landed], timeout=8000,
        )
        after = ships_of(alice.board(), "Alice")
        assert len(after) == len(before), (
            f"moving a ship changed the fleet size: {before} -> {after}"
        )
        alice.shot("sea-04-ship-moved")

    def test_only_one_ship_may_be_moved_per_turn(self, a_movable_ship):
        """"You may move only one ship per turn" — and the client has to say so
        rather than simply refusing the tap."""
        tabs, marks = a_movable_ship
        alice = tabs["Alice"]

        open_seafarers_fold(alice)
        alice.page.click("#move-ship-btn")
        alice.page.keyboard.press("Escape")
        click_edge(alice, marks["far"])
        landed = first_clickable(alice, 'edge', marks["destinations"])
        assert landed, "none of the legal destinations could be clicked"
        click_edge(alice, landed)
        confirm_placement(alice)
        alice.page.wait_for_function(
            "arrived => (window.__catanDebug.getBoard().edges[arrived].ship || {})"
            "    .player === 'Alice'",
            arg=landed, timeout=8000,
        )

        open_seafarers_fold(alice)
        alice.page.wait_for_selector("#move-ship-btn[disabled]", timeout=8000)
        reason = alice.page.get_attribute("#move-ship-btn", "title") or ""
        assert reason.strip(), (
            "the move control is greyed out with no reason on it at all"
        )
        alice.page.keyboard.press("Escape")


# --- The special victory points for reaching an island --------------------


def split_the_board(game):
    """Sink the ring around the middle hex, leaving it alone in the sea.

    Turns the default one-island board into a two-island one. The graph is
    untouched — only the terrain changes, and an island is read off the terrain
    — which is the same trick `tests/game/test_islands.py` uses.
    """
    centre = '0,0,0'
    assert game.hexes[centre].type != 'ocean', "the middle hex is already sea"
    for hex_key in game.hexes[centre].neighbors:
        game.hexes[hex_key].type = 'ocean'
        game.hexes[hex_key].number = None
    return centre


def a_second_island_within_reach(game):
    """Alice's shipping route up against a corner of an island she has not
    settled, with the hand for the settlement that reaches it.

    "Each time a player builds their first settlement on one of the small
    islands, that player receives two special victory points" — so the island
    she started on has to be on her record already, or the very first
    settlement she builds would be paid for as a discovery.
    """
    actor = "Alice"
    centre = split_the_board(game)

    home = coastal_vertex(game, with_inland_edge=True)
    give_building(game, actor, home)
    game.player_islands.setdefault(actor, []).append(game.island_of_vertex(home))

    target = next(
        key for key, vertex in sorted(game.vertices.items())
        if centre in vertex.neighbors['hexes'] and not vertex.building
        and not any(game.vertices[n].building for n in vertex.neighbors['vertices'])
    )
    # A run of ships from her coast to the island's corner. Searched rather than
    # written down: which sides that is depends on where the land ended up.
    edges, _ = _ships_between(game, home, target)
    build_ships_along(game, actor, edges)
    game.update_longest_road()

    _hand(game, actor, **SETTLEMENT_COST)
    return {"home": home, "island": centre, "target": target, "ships": edges}


def _ships_between(game, start_vertex, end_vertex):
    """The shortest run of sea sides joining two intersections.

    Breadth-first over the sides a ship may lie on, so the route is the one the
    board actually offers rather than a guess at its shape.
    """
    frontier = [(start_vertex, [], [start_vertex])]
    seen = {start_vertex}
    while frontier:
        at, edges, vertices = frontier.pop(0)
        if at == end_vertex:
            return edges, vertices
        for edge_key in sea_edges_at(game, at):
            if game.edges[edge_key].ship or game.edges[edge_key].road:
                continue
            ahead = other_end(game, edge_key, at)
            if ahead in seen:
                continue
            seen.add(ahead)
            frontier.append((ahead, edges + [edge_key], vertices + [ahead]))
    raise AssertionError(f"no run of sea sides from {start_vertex} to {end_vertex}")


@pytest.fixture
def an_island_within_reach(browser, tmp_path):
    with arranged(browser, tmp_path, a_second_island_within_reach) as live:
        yield live


class TestReachingAnIslandScoresItsPoints:
    def test_the_board_really_has_two_islands(self, an_island_within_reach):
        """Without this the settlement below is just another one on the
        mainland, and the class passes for the wrong reason."""
        tabs, marks = an_island_within_reach
        board = tabs["Alice"].board()
        neighbours = board["hexes"][marks["island"]]["neighbors"]
        assert all(board["hexes"][key]["type"] == "ocean" for key in neighbours), (
            "the middle hex is not cut off, so there is only one island"
        )

    def test_a_settlement_on_a_new_island_scores_the_special_points(
        self, an_island_within_reach
    ):
        tabs, marks = an_island_within_reach
        alice = tabs["Alice"]

        before = alice.board().get("island_points", {}).get("Alice", 0)
        points_before = alice.me()["victory_points"]

        _arm_build(alice, "settlement", SETTLEMENT_COST)
        click_vertex(alice, marks["target"])
        confirm_placement(alice)
        alice.page.wait_for_function(
            "target => ((window.__catanDebug.getBoard().vertices[target] || {})"
            "    .building || {}).player === 'Alice'",
            arg=marks["target"], timeout=8000,
        )

        board = alice.board()
        scored = board.get("island_points", {}).get("Alice", 0)
        assert scored > before, (
            f"a settlement on a second island scored no special points: "
            f"{board.get('island_points')}"
        )
        assert scored - before == board["rules"]["island_points_per_island"], (
            f"the island paid {scored - before}, not the "
            f"{board['rules']['island_points_per_island']} the table set"
        )
        # One for the settlement and the island's own points on top of it.
        assert alice.me()["victory_points"] == points_before + 1 + (scored - before)
        alice.shot("sea-05-island-reached")

    def test_the_fold_states_the_island_points(self, an_island_within_reach):
        """Points in the payload and on no screen are points nobody is playing
        for."""
        tabs, marks = an_island_within_reach
        alice = tabs["Alice"]
        _arm_build(alice, "settlement", SETTLEMENT_COST)
        click_vertex(alice, marks["target"])
        confirm_placement(alice)
        alice.page.wait_for_function(
            "target => ((window.__catanDebug.getBoard().vertices[target] || {})"
            "    .building || {}).player === 'Alice'",
            arg=marks["target"], timeout=8000,
        )

        open_seafarers_fold(alice)
        scored = alice.board()["island_points"]["Alice"]
        assert str(scored) in alice.page.inner_text("#island-points"), (
            f"the fold does not state the {scored} island points"
        )
        alice.page.keyboard.press("Escape")

    def test_no_console_errors(self, an_island_within_reach):
        tabs, _ = an_island_within_reach
        for player in tabs.values():
            assert player.noisy_errors() == [], f"{player.name}: {player.noisy_errors()}"


def test_the_fleet_is_counted(a_mixed_route):
    """The fold's own count, against the board's. A chip that says a number
    nobody else agrees with is worse than no chip."""
    alice = a_mixed_route[0]["Alice"]
    assert count_ships(alice) == len(ships_of(alice.board(), "Alice"))
