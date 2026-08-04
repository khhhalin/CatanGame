"""A rule with more than two states needs a control that can express it.

The picker handled `int` and treated everything else as a checkbox, so the two
`choice` rules — which map to play on, and how turn order is decided — rendered
as a tick nobody could interpret. The beginner and large maps were in the
catalogue, honoured by the engine, and impossible to select.
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
    wait_for_rule,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("choice-rules"))
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


def open_rule(page, rule_id):
    page.evaluate(
        "id => { const el = document.getElementById(`rule-${id}`);"
        "        const group = el && el.closest('details');"
        "        if (group) { group.open = true; } }",
        rule_id,
    )


class TestAChoiceRuleIsSelectable:
    def test_every_choice_rule_renders_a_real_chooser(self, host):
        """Driven from the server's catalogue, not a list copied into the test."""
        choices = host.page.evaluate(
            "() => window.__catanDebug.getRules().catalogue"
            "        .filter(rule => rule.type === 'choice').map(rule => rule.id)"
        )
        assert choices, "no choice rules in the catalogue — this test is aimed wrong"

        for rule_id in choices:
            open_rule(host.page, rule_id)
            tag = host.page.evaluate(
                "id => document.getElementById(`rule-${id}`)?.tagName", rule_id
            )
            assert tag == "SELECT", f"{rule_id} rendered as {tag}, not a chooser"

    def test_the_map_offers_every_layout_the_server_advertises(self, host):
        open_rule(host.page, "board_layout")
        offered = host.page.eval_on_selector_all(
            "#rule-board_layout option", "els => els.map(e => e.value)"
        )
        advertised = host.page.evaluate(
            "() => window.__catanDebug.getRules().catalogue"
            "        .find(rule => rule.id === 'board_layout')"
            "        .options.map(option => option.id)"
        )
        assert offered == advertised, f"picker shows {offered}, server offers {advertised}"

    def test_choosing_the_beginner_map_reaches_the_engine(self, host):
        """The picker showing a value the engine ignored is the failure mode."""
        open_rule(host.page, "board_layout")
        host.page.select_option("#rule-board_layout", "beginner")
        wait_for_rule(host, "board_layout", "beginner")

        chosen = host.page.evaluate(
            "() => window.__catanDebug.getRules().selected.board_layout"
        )
        assert chosen == "beginner", f"server kept {chosen!r}"

        # Put it back so the module-scoped lobby is left as it was found.
        host.page.select_option("#rule-board_layout", "random")
        wait_for_rule(host, "board_layout", "random")
