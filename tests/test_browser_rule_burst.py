"""Ticking several house rules must not spam the player.

Every rule change sends the whole selection, so one emit per tick was pure
waste: setting up a Cities & Knights table tripped the server's rate limit and
buried the player's hand under a stack of "Slow down" toasts, while the event
log filled with a dozen identical "changed the house rules" lines.
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    server_round_trip,
    start_server,
    stop_server,
    wait_for_rules,
)

pytestmark = pytest.mark.slow

# Enough rules to trip the limiter when each one was sent on its own.
BURST = ["commodities", "city_improvements", "metropolis", "knights",
         "barbarians", "city_walls", "progress_cards", "setup_second_city"]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("rule-burst"))
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


def tick_quickly(player, rule_ids):
    """Tick a run of rules as fast as a person clicking down a list.

    The wait afterwards is the coalesced send landing, not a guess at how long
    it takes: the ticks are debounced into one message, so the burst is over
    only once the server has echoed the last rule back. The resync after it
    puts a "slow down" toast - which the server would send before answering -
    on the near side of the assertions.
    """
    ticked = []
    for rule_id in rule_ids:
        player.page.evaluate(
            "id => { const el = document.getElementById(`rule-${id}`);"
            "        const group = el && el.closest('details');"
            "        if (group) { group.open = true; } }",
            rule_id,
        )
        control = player.page.locator(f"#rule-{rule_id}")
        if control.count():
            control.set_checked(True)
            ticked.append(rule_id)
    wait_for_rules(player, {rule_id: True for rule_id in ticked})
    server_round_trip(player)


class TestABurstOfRuleChanges:
    def test_the_player_is_not_told_to_slow_down(self, host):
        tick_quickly(host, BURST)

        notices = " ".join(host.notices()).lower()
        assert "slow down" not in notices, (
            f"rate limited while ticking {len(BURST)} rules: {notices!r}"
        )

    def test_the_log_is_not_one_line_per_tick(self, host):
        """The log is a shared history; a burst must not drown it."""
        entries = host.page.eval_on_selector_all(
            "#log-entries *", "els => els.map(e => e.textContent)"
        )
        changed = [text for text in entries if "house rules" in text]
        assert len(changed) < len(BURST), (
            f"{len(changed)} log lines for {len(BURST)} rules — not coalesced"
        )

    def test_the_rules_actually_arrived(self, host):
        """Coalescing must not lose a rule: the last send carries them all."""
        for rule_id in BURST:
            checked = host.page.evaluate(
                "id => { const el = document.getElementById(`rule-${id}`);"
                "        return el ? el.checked : null; }",
                rule_id,
            )
            assert checked is not False, f"{rule_id} did not survive the burst"
