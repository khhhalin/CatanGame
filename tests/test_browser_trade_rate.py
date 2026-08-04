"""The rate a player is entitled to, before they hand the bank a free card.

A tester filed: "can trade with bank for higher price (eg: player has 3:1 port,
but can still trade 4:1 with bank)". The engine is right — the rulebook says the
4:1 trade is always possible, harbour or not — so the trap is the interface: the
dialog took four cards for one without ever mentioning that three was enough.

The harbour here is a real one, placed by clicking a harbour vertex during
setup, so the rate on screen is the rate the server would charge.

Run: pytest tests/test_browser_trade_rate.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    build_settlement,
    edges_next_to,
    end_turn,
    legal_setup_vertices,
    resolve_discard,
    resolve_robber,
    roll_dice,
    start_server,
    stop_server,
)

pytestmark = pytest.mark.slow

# Fixed board, so "which vertices carry a 3:1 harbour" is the same every run.
GAME_SEED = 20260804


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


def _harbour_vertices(board, port_type):
    """Legal setup vertices carrying a harbour of the given type."""
    return [
        key for key in legal_setup_vertices(board)
        if (board["vertices"][key].get("port") or {}).get("type") == port_type
    ]


@pytest.fixture(scope="module")
def table(browser, tmp_path_factory):
    """Alice on a 3:1 harbour, Bob nowhere near one, both past setup."""
    proc, url = start_server(tmp_path_factory.mktemp("trade-rate-data"), seed=GAME_SEED)
    alice = Player(browser, url, "Alice", yolo=True)
    bob = Player(browser, url, "Bob", yolo=True)
    alice.join()
    bob.join()
    alice.page.click("#start-game-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)

    by_name = {"Alice": alice, "Bob": bob}
    for _step in range(12):
        board = alice.board()
        if board["game_phase"] != "setup":
            break
        actor = by_name[board["current_player"]]

        candidates = legal_setup_vertices(board)
        if actor is alice:
            harbours = _harbour_vertices(board, "generic")
            # First placement only: the second is wherever is left, which keeps
            # the test honest about a player who holds exactly one harbour.
            if harbours and not board["players"][0]["settlements"]:
                candidates = harbours
        else:
            # Bob must stay off every harbour, or the no-harbour half of this
            # suite is testing a player who has one.
            plain = [key for key in candidates if not board["vertices"][key].get("port")]
            candidates = plain or candidates

        vertex = build_settlement(actor, candidates)
        build_road(actor, edges_next_to(actor.board(), vertex))

    assert alice.board()["game_phase"] == "playing", "setup never finished"
    yield alice, bob
    stop_server(proc)


def _open_trade_modal(player):
    player.page.click("#tab-trade")
    player.page.wait_for_selector("#propose-trade-btn", state="visible", timeout=5000)
    player.page.click("#propose-trade-btn")
    player.page.wait_for_selector("#trade-modal.show", timeout=5000)


def _close_trade_modal(player):
    player.page.click("#close-trade-modal")
    player.page.wait_for_function(
        "() => !document.getElementById('trade-modal').classList.contains('show')",
        timeout=5000,
    )


def _rate_chips(player):
    return dict(player.page.eval_on_selector_all(
        ".trade-rate-chip",
        "els => els.map(e => [e.dataset.resource, e.textContent.trim()])",
    ))


def _hand_turn_to(table, name):
    """Play whole turns until it is `name`'s, because the dialog is turn-gated.

    Driven through the real roll-and-pass buttons rather than a socket event:
    a turn that ends any other way is not a turn a player could have taken.
    """
    alice, bob = table
    for _round in range(6):
        board = alice.board()
        if board["current_player"] == name:
            return
        actor = alice if board["current_player"] == "Alice" else bob
        resolve_robber(actor)
        if not actor.board().get("has_rolled_dice"):
            roll_dice(actor)
        for player in (alice, bob):
            resolve_discard(player)
        resolve_robber(actor)
        end_turn(actor)
    raise AssertionError(f"the turn never came round to {name}")


class TestTheRateOnScreenIsTheRateHeld:
    def test_a_harbour_owner_sees_three_to_one(self, table):
        alice, _ = table
        _hand_turn_to(table, "Alice")
        ports = [
            v["port"] for key, v in alice.board()["vertices"].items()
            if key in alice.me()["settlements"] and v.get("port")
        ]
        assert any(p["type"] == "generic" for p in ports), (
            "Alice was meant to settle on a 3:1 harbour; the fixture missed it"
        )

        _open_trade_modal(alice)
        chips = _rate_chips(alice)
        assert chips["wood"] == "🌲 3:1", chips
        assert alice.page.eval_on_selector_all(
            ".trade-rate-chip.is-harbour", "els => els.length"
        ) == 5, "a 3:1 harbour improves every resource, so every chip is marked"
        _close_trade_modal(alice)


class TestTheDialogRefusesToOverpayQuietly:
    """Regression: 4 cards went to the bank from a player entitled to give 3.

    Nothing about the trade was illegal, and the server was right to settle it.
    What was missing was any sign, before the button, that a card was being
    thrown away.
    """

    def test_four_for_one_is_stopped_lowered_and_explained(self, table):
        alice, _ = table
        _hand_turn_to(table, "Alice")
        _open_trade_modal(alice)
        alice.page.fill("#give-wood", "4")
        alice.page.fill("#want-ore", "1")

        assert "is-warning" in alice.page.get_attribute("#trade-verdict", "class")
        assert "for nothing" in alice.page.inner_text("#trade-verdict")

        alice.page.click("#submit-trade-btn")

        assert alice.page.is_visible("#trade-modal.show"), "the trade was sent anyway"
        assert alice.page.input_value("#give-wood") == "3", (
            "the give side was not lowered to Alice's own rate"
        )
        assert "Lowered to 3" in alice.page.inner_text("#trade-verdict")
        assert alice.page.is_visible("#trade-send-anyway"), (
            "overpaying is legal and has to stay reachable"
        )
        assert "4" in alice.page.inner_text("#trade-send-anyway")
        _close_trade_modal(alice)

    def test_a_trade_at_the_players_own_rate_goes_straight_out(self, table):
        """The correction must not become a second trap: 3:1 is not warned about."""
        alice, _ = table
        _hand_turn_to(table, "Alice")
        _open_trade_modal(alice)
        alice.page.fill("#give-wood", "3")
        alice.page.fill("#want-ore", "1")

        assert "is-bank" in alice.page.get_attribute("#trade-verdict", "class")
        assert "3:1" in alice.page.inner_text("#trade-verdict")

        alice.page.click("#submit-trade-btn")
        alice.page.wait_for_function(
            "() => !document.getElementById('trade-modal').classList.contains('show')",
            timeout=5000,
        )

    def test_an_offer_below_the_rate_still_goes_to_the_table(self, table):
        """2 for 1 is nobody's bank trade — it must read as an offer, not a warning."""
        alice, _ = table
        _hand_turn_to(table, "Alice")
        _open_trade_modal(alice)
        alice.page.fill("#give-wood", "2")
        alice.page.fill("#want-ore", "1")

        verdict = alice.page.inner_text("#trade-verdict")
        assert "table" in verdict, verdict
        assert "is-warning" not in alice.page.get_attribute("#trade-verdict", "class")
        _close_trade_modal(alice)


class TestAPlayerWithNoHarbour:
    def test_four_to_one_is_their_rate_and_raises_no_warning(self, table):
        """The base rulebook's 4:1 is always available, so it must not be nagged at."""
        _, bob = table
        _hand_turn_to(table, "Bob")

        _open_trade_modal(bob)
        chips = _rate_chips(bob)
        assert set(chips.values()) == {"🌲 4:1", "🧱 4:1", "🐑 4:1", "🌾 4:1", "🪨 4:1"}, chips
        assert bob.page.eval_on_selector_all(
            ".trade-rate-chip.is-harbour", "els => els.length"
        ) == 0

        bob.page.fill("#give-wood", "4")
        bob.page.fill("#want-ore", "1")
        assert "is-bank" in bob.page.get_attribute("#trade-verdict", "class")
        assert "is-warning" not in bob.page.get_attribute("#trade-verdict", "class")
        _close_trade_modal(bob)

    def test_no_console_errors(self, table):
        alice, bob = table
        assert alice.noisy_errors() == []
        assert bob.noisy_errors() == []
