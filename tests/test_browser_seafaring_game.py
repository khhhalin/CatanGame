"""A seafaring game played to a declared winner, in a real browser.

`test_browser_seafarers.py` covers placement: open water is not a target, a
ship is built, a ship is moved, the pirate sails. Nothing anywhere has ever
*played* a game with ships — so the Longest Trade Route, which counts roads and
ships together, and the victory check on a seafaring table have never run
outside a unit fixture.

The game is shortened through the rules picker rather than a test back door:
the victory target and the trade-route minimum are settings a table can
legitimately choose, so a short game is a real game and runs the same code. The
Seafarers preset is taken first, through the button a host uses, because five
separate rules have to be on before a single ship can be built.

Seeded, for the reason `test_browser_full_game.py` is: unseeded, a bot playing
to a winner is a coin toss, and a gate that passes two runs in three is not a
gate.

Run: pytest tests/test_browser_seafaring_game.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    build_settlement,
    build_ship,
    edges_next_to,
    open_seafarers_fold,
    play_one_turn,
    start_server,
    stop_server,
    wait_for_rule,
)

pytestmark = pytest.mark.slow

# Enough turns for two players to accumulate a hand and finish, without hanging
# a CI run forever if the game stalls.
MAX_TURNS = 180

# The shortest legal game the picker allows: 5 points to win, and the trade
# route claimable at 2 segments.
VICTORY_TARGET = 7
LONGEST_ROAD_MINIMUM = 2

# Fixed board and dice.
GAME_SEED = 20260805


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

    A bot clicking through a hundred turns has nothing to gain from confirming
    each one, and the confirm flow is covered where it belongs —
    `test_browser_seafarers.py` builds and moves every ship through it.
    """
    alice = Player(browser, server, "Alice", yolo=True)
    bob = Player(browser, server, "Bob", yolo=True)
    alice.join()
    bob.join()
    return alice, bob


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


def sea_edges_at(board, vertex_key):
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
        alice.page.wait_for_timeout(400)

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
                sea = sea_edges_at(board, vertex)
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


# --- The game --------------------------------------------------------------


class TestPlayingASeafaringGameToAWinner:
    """The segment nothing has ever covered: a table with ships on it played
    until somebody wins."""

    def test_the_game_reaches_a_declared_winner(self, table, request):
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}

        route_holder_at = None
        pirate_sailed_at = None
        ships_built = 0
        winner = None
        turn = 0

        for turn in range(MAX_TURNS):
            board = alice.board()
            if board.get("game_phase") != "playing":
                break

            actor = by_name[board["current_player"]]
            before = len(ships_of(board, actor.name))
            # The pirate until it has sailed once, the robber ever after: a 7
            # is the only thing that moves either, and there are not many of
            # them in a short game.
            play_one_turn(
                actor, (alice, bob),
                ships=True, prefer_pirate=board.get("pirate_hex") is None,
            )

            board = alice.board()
            ships_built += max(0, len(ships_of(board, actor.name)) - before)

            if pirate_sailed_at is None and board.get("pirate_hex"):
                pirate_sailed_at = turn
                actor.shot("sea-02-pirate-sailed")
            if route_holder_at is None and board.get("longest_road_holder"):
                route_holder_at = turn
                by_name[board["longest_road_holder"]].shot("sea-03-trade-route")

            leader = max(board["players"], key=lambda p: p.get("victory_points", 0))
            if leader.get("victory_points", 0) >= VICTORY_TARGET:
                winner = leader
                break

        board = alice.board()
        request.node.game_summary = {
            "turns": turn,
            "winner": winner["name"] if winner else None,
            "ships_built_in_play": ships_built,
            "ships": {name: len(ships_of(board, name)) for name in by_name},
            "roads": {name: len(roads_of(board, name)) for name in by_name},
            "route_holder": board.get("longest_road_holder"),
            "route_lengths": board.get("longest_road_length"),
            "island_points": board.get("island_points"),
            "pirate_hex": board.get("pirate_hex"),
            "scores": {p["name"]: p.get("victory_points", 0) for p in board["players"]},
        }

        alice.shot("sea-04-final-board")

        assert winner is not None, (
            f"no winner after {turn} turns; {request.node.game_summary}"
        )
        assert ships_built > 0, (
            "the winner was reached without a single ship being built in play, "
            "so this was a base game with a bigger board"
        )
        assert pirate_sailed_at is not None, (
            "no 7 was ever answered by sailing the pirate, so the pirate is "
            "still untested end to end"
        )

    def test_the_winner_is_announced_on_screen(self, table):
        """The banner is the only thing that tells a human the game ended."""
        for player in table:
            text = " ".join(player.notices())
            assert "GAME OVER" in text.upper(), (
                f"{player.name} was never told the game ended: {text!r}"
            )

    def test_the_trade_route_counted_ships_alongside_roads(self, table):
        """The Longest Trade Route is the rule that replaces the Longest Road on
        a seafaring table, and the whole of its difference is that ships count
        as well. A route longer than every road its owner has on the board can
        only be made of both, so that is the shape of the proof.

        Asked of the table rather than of the holder: which seat ends up with
        the longest mixed route is the game's business, and pinning it to one
        name would be pinning the dice.
        """
        alice, _ = table
        board = alice.board()
        assert board["longest_road_holder"], "nobody ever held the trade route"

        routes = {
            player["name"]: (
                board["longest_road_length"].get(player["name"], 0),
                len(roads_of(board, player["name"])),
                len(ships_of(board, player["name"])),
            )
            for player in board["players"]
        }
        assert any(length > roads for length, roads, _ in routes.values()), (
            f"no route on the board is longer than its owner's roads, so no "
            f"ship was ever counted into one: {routes}"
        )

    def test_the_award_panel_names_who_holds_the_route(self, table):
        """An award in the payload and on no screen is one nobody is playing
        for — which is exactly what Longest Road was before it was put here."""
        alice, _ = table
        holder = alice.board()["longest_road_holder"]
        summary = alice.page.inner_text("#award-summary")
        assert holder in summary, f"the award panel does not name {holder}: {summary!r}"

    def test_the_seafarers_fold_states_the_fleet_at_the_end(self, table):
        alice, _ = table
        open_seafarers_fold(alice)
        chip = alice.page.inner_text("#seafarers-chip-value")
        assert "🚢" in chip, f"the chip says nothing about the fleet: {chip!r}"
        assert alice.page.is_visible("#island-points")
        alice.page.keyboard.press("Escape")

    def test_the_board_is_still_painted_at_the_end(self, table):
        """A blank canvas satisfies every DOM assertion, and the graph here is
        three times the size of a base game's."""
        alice, _ = table
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

    def test_no_console_errors_across_the_whole_game(self, table):
        for player in table:
            assert player.noisy_errors() == [], f"{player.name}: {player.noisy_errors()}"
