"""Ticking one Longest-line award unchecks its rival, and says why.

Two rules feed the single Longest Road / Trade Route slot. Ticking the Trade
Route while the base Longest Road card is on used to leave both ticked — an
incoherent set that played only because the trade route silently won. The picker
now unchecks the rival live, and the owner's requirement is that the uncheck is
never silent: the row that lost its tick has to say why, on screen, to a player.

This is the only kind of test that catches that — a unit test sees the server
state, and the whole point is that the removal is visible in the DOM.
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    reveal_rule,
    server_round_trip,
    start_server,
    stop_server,
    wait_for_rules,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("rule-exclusions"))
    yield url
    stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def host(browser, server):
    alice = Player(browser, server, "Alice", viewport={"width": 1920, "height": 1080})
    bob = Player(browser, server, "Bob", viewport={"width": 1920, "height": 1080})
    alice.join()
    bob.join()
    alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    return alice


class TestTheAwardUnchecksItsRival:
    def test_the_excluding_rows_wear_an_exclusive_badge(self, host):
        """A player reads that the pair share a slot before ticking either."""
        reveal_rule(host, "longest_road_card")
        reveal_rule(host, "longest_trade_route")

        badge = host.page.locator(
            "#rule-longest_road_card"
        ).locator("xpath=ancestor::div[@class='rule-row']").locator(
            ".rule-exclusion-badge"
        )
        assert badge.is_visible()
        assert badge.inner_text().strip().lower() == "exclusive"

    def test_ticking_the_trade_route_unchecks_the_road_card_visibly(self, host):
        """The base Longest Road card is on by default; ticking the Trade Route
        must remove it AND show the player why — a silent flip is the specific
        thing the owner does not want."""
        reveal_rule(host, "longest_road_card")
        reveal_rule(host, "longest_trade_route")
        assert host.page.locator("#rule-longest_road_card").is_checked()

        host.page.locator("#rule-longest_trade_route").set_checked(True)

        # The rival's box goes off...
        host.page.wait_for_function(
            "() => document.getElementById('rule-longest_road_card').checked === false",
            timeout=4000,
        )
        # ...and the reason is on the row, visible, in words a player reads.
        note = host.page.locator("#rule-exclusion-longest_road_card")
        assert note.is_visible()
        note_text = note.inner_text().lower()
        assert "unchecked because" in note_text
        assert "longest trade route" in note_text

        # The notice channel repeats it, so a player looking away from the row
        # still learns what happened.
        notices = " ".join(host.notices()).lower()
        assert "unchecked because" in notices

        # The coherent set reaches the server — road card off, trade route on.
        wait_for_rules(host, {"longest_road_card": False, "longest_trade_route": True})
        server_round_trip(host)
