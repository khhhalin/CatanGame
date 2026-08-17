"""The individual-rules picker as a collapsible tree of category sections.

The rules list had grown to ~140 entries sectioned only by the coarse
core/expansion/variant group, so the expansion section was one long open list a
player had to scroll past. It is now one collapsible section per functional
category, and the requirement a unit test cannot see is that they are COLLAPSED
by default: a rule's control is in the DOM but not on screen until a player
opens the section it lives in. This drives that through a real browser.

  - the section headers a player scans are there and named for the category
    (Sea & Ships, Knights & Barbarians), read off the server's own category list;
  - a rule's control is hidden until its section is expanded - the collapsed-by-
    default assertion, watched failing if a section is built open;
  - a rule lands under the category the engine filed it in - `ships` under Sea &
    Ships, `knights` under Knights & Barbarians - so the tree is not just present
    but correct.

Run: pytest tests/test_browser_rule_categories.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1600, "height": 1000}

# The section label the picker put a given rule's row under, read from the DOM
# the way a screen reader would trace it: the row's own collapsible ancestor.
_SECTION_LABEL_FOR_RULE = """
(ruleId) => {
    const row = document.getElementById(`rule-${ruleId}`);
    if (!row) { return null; }
    const section = row.closest('details.rule-group');
    if (!section) { return null; }
    return section.querySelector('summary span').textContent;
}
"""


def section_label_for(player, rule_id):
    return player.page.evaluate(_SECTION_LABEL_FOR_RULE, rule_id)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def lobby(browser, tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("rule-categories"))
    host = Player(browser, url, "Alice", viewport=VIEWPORT)
    host.join()
    host.page.wait_for_selector("#rules-list .rule-group", timeout=8000)
    yield host
    stop_server(proc)


class TestTheCategoryTree:
    def test_the_picker_shows_named_category_sections(self, lobby):
        """The tree replaces the flat list with a section per category, each
        headed by the category's label - the thing a player reads to decide
        which section to open."""
        labels = lobby.page.eval_on_selector_all(
            "#rules-list .rule-group > summary > span:first-child",
            "els => els.map(e => e.textContent)",
        )
        assert "Sea & Ships" in labels, f"no Sea & Ships section: {labels}"
        assert "Knights & Barbarians" in labels, (
            f"no Knights & Barbarians section: {labels}"
        )

    def test_sections_are_collapsed_by_default(self, lobby):
        """The load-bearing assertion: with the sections collapsed, a rule's
        control is in the DOM but not on screen. A section built open would show
        the control from the start and fail here."""
        # The row exists...
        assert lobby.page.query_selector("#rule-ships") is not None, (
            "the Ships row was never rendered"
        )
        # ...but is not visible, because its section starts collapsed.
        assert not lobby.page.is_visible("#rule-ships"), (
            "the Ships control is visible before its section was opened - the "
            "sections are not collapsed by default"
        )

    def test_opening_a_section_reveals_its_rules(self, lobby):
        """Clicking a section header opens it and brings its rules on screen -
        the other half of the collapse assertion above."""
        summary = lobby.page.locator(
            "#rule-ships"
        ).locator("xpath=ancestor::details[1]/summary")
        summary.click()
        lobby.page.wait_for_selector("#rule-ships", state="visible", timeout=4000)
        assert lobby.page.is_visible("#rule-ships"), (
            "opening the section did not reveal the Ships control"
        )

    def test_a_rule_lands_under_its_engine_category(self, lobby):
        """The tree is correct, not just present: the engine files `ships` under
        Sea & Ships and `knights` under Knights & Barbarians, and the picker has
        to put the rows there."""
        assert section_label_for(lobby, "ships") == "Sea & Ships", (
            f"Ships is under {section_label_for(lobby, 'ships')!r}, not Sea & Ships"
        )
        assert section_label_for(lobby, "knights") == "Knights & Barbarians", (
            f"Knights is under {section_label_for(lobby, 'knights')!r}"
        )


def test_no_console_errors_were_logged(lobby):
    assert lobby.noisy_errors() == [], f"Alice logged: {lobby.noisy_errors()}"
