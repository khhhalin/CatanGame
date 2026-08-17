"""The lobby's scenario picker: a scrollable list, a live preview, one start.

The presets used to be a row of shortcut buttons that ticked rules and said
nothing about what a scenario *was*. The picker turns each into a row a player
can read, and selecting one now shows three things a player decides on before
committing a table to it:

  - a preview of the board the scenario deals, painted on a small canvas the
    same renderer draws the game board with — so what you preview is what you
    play, and a blank canvas (a throw anywhere in the deal or the draw) fails
    the pixel count here rather than reaching the table;
  - the rules the scenario turns on, read off the server's catalogue — a
    Seafarers scenario has to say "Ships", which is the whole reason a player
    would pick it over the base game;
  - the scenario's description and the rulebook it comes from.

And picking a scenario still applies its preset — the same `set_rules` path the
shortcut buttons used — so a two-player table can start straight from the pick.

The pixel assertion is the load-bearing one: it was watched failing (the canvas
paints nothing until the `preview_scenario` round trip lands) before the preview
was wired, exactly as a canvas assertion is required to.

Run: pytest tests/test_browser_scenario_picker.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
    wait_for_preset,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1600, "height": 1000}

# Painted pixels on the scenario preview canvas — any pixel whose alpha is not
# zero. A blank canvas (the bug this guards) counts zero.
_PREVIEW_PIXELS = """
() => {
    const canvas = document.getElementById('scenario-preview-canvas');
    if (!canvas || !canvas.width) { return 0; }
    const data = canvas.getContext('2d')
        .getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let i = 3; i < data.length; i += 4) {
        if (data[i] !== 0) { count++; }
    }
    return count;
}
"""


def preview_pixels(player):
    return player.page.evaluate(_PREVIEW_PIXELS)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def lobby(browser, tmp_path_factory):
    """Two players in the lobby: enough to start once a scenario is picked."""
    proc, url = start_server(tmp_path_factory.mktemp("scenario-picker"))
    players = [Player(browser, url, name, viewport=VIEWPORT)
               for name in ("Alice", "Bob")]
    for player in players:
        player.join()
    yield players
    stop_server(proc)


def select_seafarers(host):
    """Pick the Seafarers scenario and wait for its rules to echo back.

    Seafarers is the scenario with a rule no base game has — Ships — so it is
    the one whose 'rules turned on' list the detail panel must be able to show.
    """
    host.page.click("#preset-seafarers")
    wait_for_preset(host, "seafarers")


class TestTheScenarioList:
    def test_every_preset_is_one_row_in_the_list(self, lobby):
        """A scenario the server offers with no row in the picker is a scenario
        a player cannot reach — the failure the old one-button-each rule caught,
        now for the list."""
        from game import rules

        rendered = set(lobby[0].page.eval_on_selector_all(
            "#rule-presets [data-preset-id]", "els => els.map(e => e.dataset.presetId)"
        ))
        missing = [p["id"] for p in rules.presets() if p["id"] not in rendered]
        assert missing == [], f"these scenarios have no row: {missing}"

    def test_a_row_shows_the_scenario_name_and_a_blurb(self, lobby):
        """The row a player scans is a name and a one-line description, not a
        bare id."""
        row = lobby[0].page.query_selector("#preset-seafarers")
        assert row is not None, "the Seafarers row is missing"
        name = row.query_selector(".scenario-row-name").inner_text()
        blurb = row.query_selector(".scenario-row-blurb").inner_text()
        assert name == "Seafarers", f"the row is not named: {name!r}"
        assert blurb, "the row shows no blurb"


class TestTheDetailPanel:
    def test_the_preview_is_blank_until_a_scenario_is_picked(self, lobby):
        """The pixel assertion below is only meaningful if the canvas starts
        empty — otherwise it could pass over a board that never changed."""
        assert preview_pixels(lobby[0]) == 0, "the preview painted before a pick"

    def test_selecting_a_scenario_paints_its_map_preview(self, lobby):
        """The load-bearing assertion: a real board comes back from the server
        and the same renderer paints it. A blank canvas satisfies every DOM
        assertion, so this counts pixels."""
        host = lobby[0]
        select_seafarers(host)
        host.page.wait_for_function(
            f"() => ({_PREVIEW_PIXELS.strip()})() > 500", timeout=10000
        )
        assert preview_pixels(host) > 500, "the preview canvas is blank"

    def test_the_rules_turned_on_list_names_ships(self, lobby):
        """Seafarers turns on Ships; the detail panel has to say so, because
        that is the rule a player picks the scenario for."""
        host = lobby[0]
        select_seafarers(host)
        chips = host.page.eval_on_selector_all(
            "#scenario-detail-rules .scenario-rule-chip",
            "els => els.map(e => e.textContent)",
        )
        assert any(chip == "Ships" for chip in chips), (
            f"the rules-turned-on list does not name Ships: {chips}"
        )

    def test_the_description_and_rulebook_show(self, lobby):
        host = lobby[0]
        select_seafarers(host)
        summary = host.page.inner_text("#scenario-detail-summary")
        source = host.page.inner_text("#scenario-detail-source")
        assert "Ships" in summary or "ship" in summary.lower(), (
            f"the description is missing: {summary!r}"
        )
        assert source.startswith("Rulebook:"), (
            f"the rulebook citation is missing: {source!r}"
        )
        assert "Seafarers" in source, f"the citation is not the scenario's: {source!r}"


class TestStartingFromAScenario:
    def test_selecting_a_scenario_leaves_the_game_startable(self, lobby):
        """A two-player table that picks a scenario can start it: the pick
        applies the preset through the same path the switches use, so Start Game
        is offered and enabled."""
        host = lobby[0]
        select_seafarers(host)
        host.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
        assert not host.page.is_disabled("#start-game-btn"), (
            "Start Game is disabled after picking a scenario: "
            f"{host.page.get_attribute('#start-game-btn', 'title')!r}"
        )

    def test_the_individual_rules_list_is_still_reachable(self, lobby):
        """The picker did not replace the switches: a table can still open the
        individual rule the scenario ticked and change it."""
        host = lobby[0]
        select_seafarers(host)
        # The Ships switch the Seafarers preset ticked is in the list, checked.
        host.page.wait_for_function(
            "() => document.getElementById('rule-ships')?.checked === true",
            timeout=5000,
        )
        assert host.page.is_visible("#rules-list"), "the individual-rules list is gone"


def test_no_console_errors_were_logged(lobby):
    for player in lobby:
        assert player.noisy_errors() == [], (
            f"{player.name} logged: {player.noisy_errors()}"
        )
