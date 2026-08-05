"""Six people at one table, from the join box to the first turn.

The cap was a config constant, so a fifth tab was answered with "Cannot join as
player. Max 4 players allowed." and there was no board with room for six
anyway. Both are settings now: `max_players` is a rule like `min_players`, and
`six-shores` is a built-in map with four landmasses.

Only a browser test can say the whole path works — the lobby heading, the seat
refusal, six scoreboard rows in six legible colours and a board that actually
paints. The unit suite is happy with all of this while the screen is blank.

Run: pytest tests/test_browser_six_players.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
    wait_for_board_painted,
    wait_for_rule,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

SIX = ["Ana", "Ben", "Cleo", "Dev", "Esi", "Finn"]


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
    elif control.evaluate("el => el.tagName") == "SELECT":
        control.select_option(value)
    else:
        control.fill(str(value))
        control.blur()
    wait_for_rule(player, rule_id, value)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.fixture(scope="module")
def six_player_table(browser, tmp_path_factory):
    """Six tabs at a table playing `six-shores`, mid-setup."""
    proc, url = start_server(tmp_path_factory.mktemp("six"), seed="6")
    players = []
    try:
        host = Player(browser, url, SIX[0], viewport=VIEWPORT)
        host.join()
        players.append(host)

        set_rule(host, "max_players", 6)
        set_rule(host, "ships", True)
        set_rule(host, "board_layout", "custom")
        set_rule(host, "board_map", "six-shores")

        for name in SIX[1:]:
            player = Player(browser, url, name, viewport=VIEWPORT)
            player.join()
            players.append(player)

        host.page.wait_for_function(
            "() => document.getElementById('players').children.length === 6",
            timeout=10000,
        )
        host.page.click("#start-game-btn")
        for player in players:
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=15000)
        wait_for_board_painted(host)
        yield players
    finally:
        stop_server(proc)


class TestTheLobbySeatsSix:
    def test_the_heading_counts_up_to_the_table_s_own_cap(self, six_player_table):
        """It read "/4" out of the markup, whatever the server said."""
        host = six_player_table[0]
        assert host.page.inner_text("#player-limit") == "6"
        assert host.page.inner_text("#player-count") == "6"

    def test_the_fifth_and_sixth_players_are_seated_as_players(self, six_player_table):
        """The fifth join used to be refused with GAME_FULL."""
        names = six_player_table[0].page.eval_on_selector_all(
            "#players li", "els => els.map(e => e.textContent)"
        )
        assert sorted(names) == sorted(SIX)


class TestTheGameIsPlayableBySix:
    def test_the_board_paints(self, six_player_table):
        """A blank canvas satisfies every DOM assertion, so count pixels."""
        painted = six_player_table[0].page.evaluate(
            "() => { const c = document.querySelector('#board-canvas');"
            "        const ctx = c.getContext('2d');"
            "        const data = ctx.getImageData(0, 0, c.width, c.height).data;"
            "        let lit = 0;"
            "        for (let i = 3; i < data.length; i += 4) { if (data[i]) lit++; }"
            "        return lit; }"
        )
        assert painted > 10000, painted

    def test_the_scoreboard_shows_six_rows_in_six_colours(self, six_player_table):
        """A fifth player used to be white, and so was the sixth."""
        rows = six_player_table[0].page.eval_on_selector_all(
            "#game-players li",
            "els => els.map(e => [e.textContent, getComputedStyle(e).backgroundColor])",
        )
        assert len(rows) == 6
        assert len({colour for _, colour in rows}) == 6

    def test_the_sixth_seat_gets_its_setup_turn(self, six_player_table):
        """Setup runs out to the last seat and back; a cycle that stopped at
        four would leave two players never asked to place."""
        host = six_player_table[0]
        seats = host.page.evaluate(
            "() => window.__catanDebug.getBoard().players.map(p => p.name)"
        )
        assert sorted(seats) == sorted(SIX)
        assert host.page.evaluate(
            "() => window.__catanDebug.getBoard().game_phase"
        ) == "setup"

    def test_no_console_errors(self, six_player_table):
        for player in six_player_table:
            assert player.noisy_errors() == [], (player.name, player.noisy_errors())
