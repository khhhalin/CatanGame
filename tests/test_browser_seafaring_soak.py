"""Many real turns on a seafaring board, in a real browser.

`test_browser_seafaring_game.py` used to play a 141-turn game and was rewritten
into per-rule scenarios, which was the right trade: five minutes of dice to
prove whichever rules that particular run happened to walk past. But every one
of those scenarios is arranged into the save file and starts after
`set_dice_rolled()`, so the ordinary loop of a turn — rolling, production being
paid out, a 7 forcing a discard, a bank trade breaking a deadlock — stopped
being exercised on the sea board entirely. The base-board long game
(`test_browser_full_game.py`) still covers that loop, on a graph a third the
size and with no ships in it.

The sea graph is not the same graph. It carries every ocean hex, every sea
side and every intersection out at sea, which is roughly three times the
vertices and edges the base board has, and production, discarding and the
trade dialog all walk it. So this is a short soak rather than a game: a fixed
number of turns on a seeded seafaring table, asserting that the loop really
ran there — rolls that paid somebody, a 7 answered with a discard, a bank
trade settled, and no console error anywhere across the whole run.

It does not play to a winner. A winner is `test_browser_seafaring_game.py`'s
job, and reaching one is what made the old file cost five minutes.

Run: pytest tests/test_browser_seafaring_soak.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    bank_trade,
    browser_session,
    build_road,
    build_settlement,
    build_ship,
    edges_next_to,
    end_turn,
    game_is_over,
    resolve_discard,
    resolve_robber,
    reveal_rule,
    roll_dice,
    spend_what_you_can,
    start_server,
    stop_server,
    wait_for_rule,
)

pytestmark = pytest.mark.slow

TABLE = ["Alice", "Bob"]

RESOURCES = ("wood", "brick", "sheep", "wheat", "ore")

# Fixed board and dice. Unseeded, "was a 7 ever rolled" is a coin toss and a
# gate that passes two runs in three is not a gate.
GAME_SEED = 20260806

# Turns to play. Enough that both seats collect, build and run out of the
# thing they need; few enough that the whole module stays well under a minute.
SOAK_TURNS = 24

# The lowest hand limit the picker offers. A real setting a table can choose,
# and it is what makes a 7 inside two dozen turns actually cost somebody
# cards rather than passing unnoticed — which is the discard path this soak
# exists to walk on the sea graph.
HAND_LIMIT = 5

# High enough that nobody wins and cuts the soak short. Also a real setting.
VICTORY_TARGET = 20


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("sea-soak-data"), seed=GAME_SEED)
    yield url
    stop_server(proc)


@pytest.fixture(scope="module")
def table(browser, server):
    alice = Player(browser, server, "Alice", yolo=True)
    bob = Player(browser, server, "Bob", yolo=True)
    alice.join()
    bob.join()
    return alice, bob


@pytest.fixture(scope="module")
def tally():
    """What the soak saw, filled in by the run and read by the assertions.

    One long run, several things to check about it: replaying it per assertion
    would multiply the module's cost by the number of questions asked of it.
    """
    return {"turns": 0, "rolls": 0, "discards": 0, "trades": 0, "built": []}


def set_rule(player, rule_id, value):
    """Set one rule through the picker, as a host would."""
    reveal_rule(player, rule_id)
    control = player.page.locator(f"#rule-{rule_id}")
    control.scroll_into_view_if_needed()
    control.fill(str(value))
    # The picker submits on `change`; blurring guarantees it fires.
    control.blur()
    wait_for_rule(player, rule_id, value)


def coastal_setup_vertices(board):
    """Vacant, distance-legal intersections with a free sea side leaving them.

    With ships on, the graph reaches out over the water and most vertices in
    the payload are open sea where nothing may ever stand — the server lists
    land hexes only, so an empty hex list means "this is at sea".
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


# Classic pips: how many of the 36 dice combinations each token pays on.
PIPS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}


def pips_at(board, vertex_key):
    return sum(
        PIPS.get(board["hexes"][hex_key].get("number"), 0)
        for hex_key in board["vertices"][vertex_key]["neighbors"]["hexes"]
    )


def setup_ranking(board, coastal_only):
    """Where to put a starting settlement, best corner first.

    A soak whose subject is the turn loop has to start where production
    happens, and on a sea board those are not the same corners: a coastal
    intersection touches one or two land hexes where an inland one touches
    three. So each seat takes its *first* corner on the coast, because that is
    the only place a starting ship may go, and its second wherever the board
    pays best. Sending both to the coast is what left this soak collecting
    about one card a turn between two players — too poor to ever fill a hand,
    so no 7 ever cost anybody anything and the discard path went unwalked.
    """
    candidates = (
        coastal_setup_vertices(board) if coastal_only
        else [
            key for key, vertex in sorted(board["vertices"].items())
            if vertex["neighbors"]["hexes"]
            and not vertex["building"]
            and not any(board["vertices"].get(n, {}).get("building")
                        for n in vertex["neighbors"]["vertices"])
        ]
    )
    return sorted(candidates, key=lambda key: pips_at(board, key), reverse=True)


def sea_edges_of(board, vertex_key):
    return [
        key for key in sorted(board["vertices"][vertex_key]["neighbors"]["edges"])
        if board["edges"][key]["sea"]
        and not board["edges"][key]["ship"]
        and not board["edges"][key]["road"]
    ]


def last_settlement_awaiting_a_piece(board, name):
    """The settlement this seat has just placed and not yet built beside."""
    return next(
        key for key, vertex in board["vertices"].items()
        if (vertex.get("building") or {}).get("player") == name
        and not any(
            (board["edges"][edge].get("road") or board["edges"][edge].get("ship") or {})
            .get("player") == name
            for edge in vertex["neighbors"]["edges"]
        )
    )


def log_lines(player):
    """The shared history as a human reads it, one string per entry."""
    return player.page.eval_on_selector_all(
        "#log-entries .log-text", "els => els.map(e => e.textContent)"
    )


def hand_of(player):
    return dict((player.me() or {}).get("resources") or {})


def trade_a_surplus(actor):
    """Turn four of whatever this seat holds most of into one of the least.

    `spend_what_you_can` already trades towards a build, but only when it can
    name a target it is short of — so on a turn where it built something the
    trade dialog is never opened at all. Opening it here means the dialog, the
    bank rate and the settlement are walked on a sea board every time a hand
    can pay for it, which is the thing the rewrite stopped covering.
    """
    held = hand_of(actor)
    give = max(RESOURCES, key=lambda res: held.get(res, 0))
    if held.get(give, 0) < 4:
        return False
    want = min(RESOURCES, key=lambda res: held.get(res, 0))
    if want == give:
        return False
    return bank_trade(actor, give, 4, want)


def soak_turn(actor, everyone, tally):
    """One ordinary turn, counting what the loop actually did."""
    resolve_robber(actor, prefer_pirate=True)
    if not actor.board().get("has_rolled_dice"):
        roll_dice(actor)
        tally["rolls"] += 1

    # A 7 makes every over-stocked tab discard, not just the roller, and the
    # turn cannot advance until they all have.
    for player in everyone:
        if resolve_discard(player):
            tally["discards"] += 1

    resolve_robber(actor, prefer_pirate=True)

    built = spend_what_you_can(actor, ships=True)
    tally["built"].extend(kind for kind, _ in built)

    if trade_a_surplus(actor):
        tally["trades"] += 1

    if not game_is_over(actor):
        end_turn(actor)


class TestASeafaringTableIsSetUp:
    def test_the_preset_and_the_picker_configure_a_long_sea_game(self, table):
        alice, bob = table
        alice.page.wait_for_function(
            "() => document.querySelectorAll('#players li').length === 2", timeout=8000
        )
        alice.page.click("#preset-seafarers")
        alice.page.wait_for_function(
            "() => window.__catanDebug.getRules().selected.ships === true", timeout=8000
        )
        set_rule(alice, "victory_target", VICTORY_TARGET)
        set_rule(alice, "max_hand_before_discard", HAND_LIMIT)

        bob.page.wait_for_function(
            "limit => document.getElementById('rule-max_hand_before_discard').value"
            "        === String(limit)",
            arg=HAND_LIMIT, timeout=8000,
        )

    def test_setup_is_played_by_clicking_and_each_seat_takes_a_ship(self, table):
        alice, bob = table
        alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
        alice.page.click("#start-game-btn")
        for player in table:
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)

        rules = alice.board()["rules"]
        assert rules["ships"] is True
        assert rules["max_hand_before_discard"] == HAND_LIMIT

        by_name = {"Alice": alice, "Bob": bob}
        took_a_ship = set()

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
                build_settlement(
                    actor, setup_ranking(board, coastal_only=actor.name not in took_a_ship)
                )

        assert alice.board()["game_phase"] == "playing", "setup never finished"
        assert sorted(took_a_ship) == TABLE, (
            "neither seat took a starting ship, so no sea game is being played"
        )


class TestTheOrdinaryTurnLoopOnTheSeaBoard:
    """The whole soak is one run; each test below reads what it produced."""

    def test_two_dozen_turns_can_be_played_without_the_game_jamming(
        self, table, tally, request
    ):
        alice, bob = table
        by_name = {"Alice": alice, "Bob": bob}

        for _turn in range(SOAK_TURNS):
            board = alice.board()
            if board.get("game_phase") != "playing":
                break
            soak_turn(by_name[board["current_player"]], table, tally)
            tally["turns"] += 1

        request.node.soak_summary = dict(tally)
        alice.shot("sea-soak-final-board")

        assert tally["turns"] == SOAK_TURNS, (
            f"the sea table stalled after {tally['turns']} turns: {tally}"
        )
        assert alice.board()["turn_count"] >= SOAK_TURNS, (
            "the server counted fewer turns than the browser played"
        )

    def test_the_rolls_paid_somebody_on_the_sea_board(self, table, tally):
        """Production is what a roll is for, and it is the part the per-rule
        scenarios skip entirely: they all begin after the dice."""
        alice, _ = table
        paid = [
            line for line in log_lines(alice)
            if line.startswith("Production:") and "paid nobody" not in line
        ]

        assert tally["rolls"] >= SOAK_TURNS - 1, tally
        assert len(paid) >= SOAK_TURNS // 3, (
            f"only {len(paid)} of {tally['rolls']} rolls on the sea board paid "
            f"anybody anything"
        )

    def test_a_seven_cost_somebody_cards(self, table, tally):
        """The discard path, walked on the big graph. The modal was answered by
        a tab, and the table was told about it in the shared log."""
        alice, _ = table
        discarded = [line for line in log_lines(alice) if "discarded" in line]

        assert tally["discards"] >= 1, (
            f"no 7 ever cost anybody a card in {tally['turns']} turns: {tally}"
        )
        assert discarded, "a discard happened and the log never mentioned it"

    def test_a_bank_trade_settled_at_sea(self, tally):
        """Through the real trade dialog: propose, the rate the engine quotes,
        and the bank settling it."""
        assert tally["trades"] >= 1, f"no bank trade completed: {tally}"

    def test_the_seats_really_built_things_across_the_run(self, table, tally):
        """A soak where nobody builds is a soak of an empty board — the
        accumulated state is the point."""
        alice, _ = table
        assert len(tally["built"]) >= 4, f"almost nothing was built: {tally}"
        assert "ship" in tally["built"], (
            "no ship was built in the whole run, so this was not a sea game"
        )

        board = alice.board()
        for player in board["players"]:
            assert player["name"] in TABLE

    def test_the_board_is_still_drawn_after_the_whole_run(self, table):
        """A blank canvas satisfies every DOM assertion, so count the pixels.
        Two dozen turns of redraws on the largest graph the renderer handles is
        exactly where it would give out."""
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

    def test_no_console_errors_across_the_whole_soak(self, table):
        for player in table:
            assert player.noisy_errors() == [], f"{player.name}: {player.noisy_errors()}"
