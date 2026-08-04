"""Play a game from an empty lobby to a declared winner, in a real browser.

`test_browser_playthrough.py` covers setup and a single turn cycle. Nothing
until now has ever run the game to completion, so whole areas — Longest Road
changing hands, the victory check, the game-over banner — had never executed
outside a unit test's fixture.

The game is shortened through the rules picker, not through a test back door:
the victory target and the Longest Road minimum are real settings a table can
choose, so a short game is a legitimate game and exercises the same code.

Screenshots of each milestone are written to `test-artifacts/browser/` so the
run can be inspected by eye, which is the whole point of testing here rather
than against a socket client.

Run: pytest tests/test_browser_full_game.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    build_settlement,
    edges_next_to,
    legal_setup_vertices,
    play_one_turn,
    start_server,
    stop_server,
    wait_for_rule,
)

pytestmark = pytest.mark.slow

# Enough turns for two players to accumulate a hand and finish, without
# hanging a CI run forever if the game stalls.
MAX_TURNS = 120

# The shortest legal game the rules picker allows: 5 points to win, and
# Longest Road claimable at 2 segments.
VICTORY_TARGET = 5
LONGEST_ROAD_MINIMUM = 2

# Fixed board and dice. Unseeded, this test is a coin toss — it reached a
# winner, then stalled a point short on identical code — and a gate that
# passes two runs in three is not a gate.
GAME_SEED = 20260803


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("full-game-data"), seed=GAME_SEED)
    yield url
    stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def table(browser, server):
    """Two players and one observer, all watching the same game.

    Both seats play in YOLO mode: a bot clicking through a hundred turns has
    nothing to gain from confirming each one, and the confirm flow is the
    default everywhere else — `test_browser_playthrough.py` plays it, and
    `test_browser_confirm_placement.py` is about nothing else.
    """
    alice = Player(browser, server, "Alice", yolo=True)
    bob = Player(browser, server, "Bob", yolo=True)
    watcher = Player(browser, server, "Watcher")
    alice.join()
    bob.join()
    watcher.join(as_player=False)
    return alice, bob, watcher


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
    else:
        control.fill(str(value))
        # The picker submits on `change`; blurring guarantees it fires.
        control.blur()
    wait_for_rule(player, rule_id, value)


class TestLobbyCreation:
    def test_the_lobby_starts_empty_and_accepts_a_join(self, table):
        alice, _, _ = table
        assert alice.page.is_visible("#user-screen")
        assert not alice.page.is_visible("#join-screen")

    def test_players_and_observers_are_listed_separately(self, table):
        alice, _, _ = table
        alice.page.wait_for_function(
            "() => document.querySelectorAll('#players li').length === 2", timeout=8000
        )
        players = alice.page.eval_on_selector_all(
            "#players li", "els => els.map(e => e.textContent.trim().split(/\\s+/)[0])"
        )
        observers = alice.page.eval_on_selector_all(
            "#observers li", "els => els.map(e => e.textContent.trim().split(/\\s+/)[0])"
        )
        assert sorted(players) == ["Alice", "Bob"]
        assert "Watcher" in " ".join(observers)

    def test_an_observer_cannot_start_the_game(self, table):
        """An observer is not a seat, so the host controls must not be theirs."""
        _, _, watcher = table
        hidden = watcher.page.evaluate(
            "() => { const b = document.getElementById('start-game-btn');"
            "        return !b || b.classList.contains('hidden') || b.disabled; }"
        )
        assert hidden, "an observer was offered the Start button"

    def test_the_host_can_shorten_the_game_through_the_picker(self, table):
        alice, bob, _ = table
        set_rule(alice, "victory_target", VICTORY_TARGET)
        set_rule(alice, "longest_road_minimum", LONGEST_ROAD_MINIMUM)

        # Rule changes are table-wide, so the other tab must see them too.
        bob.page.wait_for_function(
            "target => document.getElementById('rule-victory_target').value === String(target)",
            arg=VICTORY_TARGET, timeout=8000,
        )
        alice.shot("01-lobby-configured")

    def test_the_start_button_is_offered_once_the_table_is_legal(self, table):
        alice, _, _ = table
        alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
        assert not alice.page.is_disabled("#start-game-btn")


class TestGameSetup:
    def test_the_game_starts_for_every_tab_including_the_observer(self, table):
        alice, bob, watcher = table
        alice.page.click("#start-game-btn")
        for player in (alice, bob, watcher):
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        watcher.shot("02-observer-sees-the-board")

    def test_both_bots_really_are_in_yolo_mode(self, table):
        """The preference is written to localStorage before the page loads, so
        a typo there would silently put this suite back on the confirm path -
        every placement waiting for a control that never appears."""
        alice, bob, watcher = table
        for player in (alice, bob):
            assert player.page.is_checked("#yolo-mode-toggle"), (
                f"{player.name} is not in YOLO mode"
            )
        assert not watcher.page.is_checked("#yolo-mode-toggle"), (
            "YOLO mode leaked into a tab that did not ask for it"
        )

    def test_the_chosen_rules_actually_reached_the_engine(self, table):
        """A picker that displays a value the engine ignored is worse than no
        picker at all, so check the running game's own rules, not the form."""
        alice, _, _ = table
        rules = alice.board()["rules"]
        assert rules["victory_target"] == VICTORY_TARGET
        assert rules["longest_road_minimum"] == LONGEST_ROAD_MINIMUM

    def test_the_shortened_rules_are_shown_to_the_table(self, table):
        alice, _, _ = table
        alice.page.wait_for_selector("#active-rules-panel:not(.hidden)", timeout=8000)
        shown = alice.page.inner_text("#active-rules")
        assert str(VICTORY_TARGET) in shown, f"active rules panel reads {shown!r}"

    def test_the_full_setup_phase_can_be_played_by_clicking(self, table):
        alice, bob, _ = table
        by_name = {"Alice": alice, "Bob": bob}

        expected = len(alice.board()["players"]) * 2
        placed = 0

        for _step in range(expected + 4):
            board = alice.board()
            if board["game_phase"] != "setup":
                break

            actor = by_name[board["current_player"]]

            vertex = build_settlement(actor, legal_setup_vertices(board))
            placed += 1

            edges = edges_next_to(actor.board(), vertex)
            assert edges, "no legal road beside the settlement just placed"
            build_road(actor, edges)

        assert placed == expected, f"only {placed} of {expected} setup placements landed"
        assert alice.board()["game_phase"] == "playing"
        alice.shot("03-setup-complete")

    def test_the_board_is_drawn_not_blank(self, table):
        """A blank canvas satisfies every DOM assertion, so count the pixels."""
        alice, _, _ = table
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

    def test_every_player_holds_starting_resources(self, table):
        alice, bob, _ = table
        for player in (alice, bob):
            held = sum((player.me()["resources"] or {}).values())
            assert held > 0, f"{player.name} got nothing from the second settlement"


class TestPlayingToAWinner:
    """The segment nothing has ever covered: Longest Road, and the last point."""

    def test_a_full_game_reaches_a_declared_winner(self, table, request):
        alice, bob, watcher = table
        by_name = {"Alice": alice, "Bob": bob}

        longest_road_seen_at = None
        winner = None
        turn = 0

        for turn in range(MAX_TURNS):
            board = alice.board()
            if board.get("game_phase") != "playing":
                break

            actor = by_name[board["current_player"]]
            play_one_turn(actor, (alice, bob))

            board = alice.board()

            if longest_road_seen_at is None and board.get("longest_road_holder"):
                longest_road_seen_at = turn
                holder = board["longest_road_holder"]
                by_name[holder].shot("04-longest-road-claimed")

            leader = max(board["players"], key=lambda p: p.get("victory_points", 0))
            if leader.get("victory_points", 0) >= VICTORY_TARGET:
                winner = leader
                break

        # Attach what happened either way — a stalled game needs the evidence
        # as much as a finished one does.
        request.node.game_summary = {
            "turns": turn,
            "longest_road_turn": longest_road_seen_at,
            "winner": winner["name"] if winner else None,
            "scores": {p["name"]: p.get("victory_points", 0) for p in alice.board()["players"]},
        }

        alice.shot("05-final-board")
        watcher.shot("06-observer-final-view")

        assert winner is not None, (
            f"no winner after {turn} turns; scores were "
            f"{request.node.game_summary['scores']}"
        )
        assert longest_road_seen_at is not None, (
            "the game finished without Longest Road ever being awarded, so that "
            "path is still untested"
        )

    def test_the_winner_is_announced_on_screen(self, table):
        """The banner is the only thing that tells a human the game ended."""
        alice, bob, watcher = table
        for player in (alice, bob, watcher):
            text = " ".join(player.notices())
            assert "GAME OVER" in text.upper(), (
                f"{player.name} was never told the game ended: {text!r}"
            )

    def test_the_scoreboard_agrees_with_the_victory_threshold(self, table):
        alice, _, _ = table
        board = alice.board()
        best = max(p.get("victory_points", 0) for p in board["players"])
        assert best >= VICTORY_TARGET

    def test_no_console_errors_across_the_whole_game(self, table):
        for player in table:
            assert player.noisy_errors() == [], f"{player.name}: {player.noisy_errors()}"
