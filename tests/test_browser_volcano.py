"""Krakatoa in a real browser: a volcano hex renders, and an eruption is seen.

The whole variant is read off the board payload and the roll broadcast; a
volcano tile that never painted, or a building that vanished with nothing said,
would leave the eruption invisible while the server scored it — and the unit
suite would still pass, because the server state is perfectly correct (the bar
CLAUDE.md sets for a browser test).

This pins two player-visible things:
- the volcano hex paints its registry volcanic red (pixels, not DOM), so it
  reads apart from every resource hex — drawn entirely from the resource
  registry the server sent, with no volcano hardcoded in the client;
- rolling a volcano's number erupts it: a building disappears from the board and
  the event log names it as an eruption.

The board is set so all six corners of the 5-volcano carry a settlement, so
whichever corner the eruption die picks, exactly one building is destroyed —
the disappearance is deterministic without scripting the server's RNG.

Run: pytest tests/test_browser_volcano.py -m slow -v
"""

import os
import random

import pytest
from browser_harness import (
    Player,
    browser_session,
    next_frame,
    start_server,
    stop_server,
    wait_for_board_painted,
)
from game import map_store, maps, persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1600, "height": 1000}

# Reddish painted pixels on the volcano tile. The volcano's registry fill is a
# dark volcanic red (#b5361f: R~181, G~54, B~31); a resource or sea hex has
# nothing this red, so a cluster of these on the tile is the volcano painting its
# own colour. Sampled at the tile's four edge-midpoints rather than its centre: a
# number token disc covers the centre and a settlement piece sits on each corner,
# so the bare terrain reads at the flat sides between them (~0.55 of the radius
# out). Summed across the four so the count does not hinge on one orientation.
_HEX_RED = """
([hexKey, boxRadius]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const layout = window.BoardRenderer.computeLayout(board);
    const pos = layout.hexPositions[hexKey];
    if (!pos) { return -1; }
    const rect = canvas.getBoundingClientRect();
    const dpr = canvas.width / rect.width;
    const ctx = canvas.getContext('2d');
    const offset = 0.55 * 35;  // 0.55 of BOARD_CONFIG.hexRadius (35)
    const probes = [[offset, 0], [-offset, 0], [0, offset], [0, -offset]];
    let reddish = 0;
    for (const [dx, dy] of probes) {
        const client = window.BoardRenderer.boardToClient(
            canvas, pos.x + layout.offsetX + dx, pos.y + layout.offsetY + dy
        );
        const x = Math.round((client.x - rect.left) * dpr);
        const y = Math.round((client.y - rect.top) * dpr);
        const data = ctx.getImageData(
            x - boxRadius, y - boxRadius, boxRadius * 2, boxRadius * 2
        ).data;
        for (let i = 0; i < data.length; i += 4) {
            if (data[i + 3] > 0 && data[i] > 120
                && data[i] > data[i + 1] + 50 && data[i] > data[i + 2] + 50) {
                reddish += 1;
            }
        }
    }
    return reddish;
}
"""


def _krakatoa_game():
    """A Krakatoa game past setup, Alice to roll, every corner of the 5-volcano
    holding a settlement so the eruption destroys one whatever the die shows.

    Gold-of-choice is off so the roll opens no production choices — the eruption
    is what is under test — and the dice are fixed to total 5, the 5-volcano's
    number, so the roll lands on it every run.
    """
    defn = maps.parse_map(map_store.read_map("krakatoa"))
    rules = dict(rules_module.preset_rules("krakatoa"))
    rules["turn_order"] = "lobby"
    rules["gold_field_choice"] = False
    game = Game(["Alice", "Bob"], [], rng=random.Random(7), rules=rules,
                map_definition=defn)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.start_turn()

    volcano = next(k for k in game.volcano_hexes if game.hexes[k].number == 5)
    corners = [game._volcano_corner(volcano, i) for i in range(6)]
    for index, vertex in enumerate(corners):
        owner = "Alice" if index % 2 == 0 else "Bob"
        game.vertices[vertex].building = {"type": "settlement", "player": owner}
        game.get_player(owner).settlements.append(vertex)

    # A pair that totals the 5-volcano's number, consumed on Alice's next roll.
    game.pending_dice = (2, 3)
    return game, volcano, corners


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def _join(browser, url):
    alice = Player(browser, url, "Alice", viewport=VIEWPORT)
    alice.page.check("#role-player")
    alice.page.fill("#username", "Alice")
    alice.page.click("#join-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    wait_for_board_painted(alice)
    next_frame(alice.page)
    return alice


def test_a_volcano_paints_its_colour_and_an_eruption_destroys_a_building(browser, tmp_path):
    game, volcano, corners = _krakatoa_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The volcano tile paints its registry volcanic red — distinct from every
        # resource and sea hex, and drawn from the registry the server sent.
        red = alice.page.evaluate(_HEX_RED, [volcano, 6])
        assert red > 10, f"the volcano hex did not paint its volcanic red (red {red})"

        # All six corners carry a building before the roll.
        before = alice.page.evaluate(
            """(corners) => {
                const v = window.__catanDebug.getBoard().vertices || {};
                return corners.filter(k => v[k] && v[k].building).length;
            }""",
            corners,
        )
        assert before == 6, before

        # Alice rolls the 5: the volcano erupts and one building is destroyed.
        alice.page.click("#roll-dice-btn")
        alice.page.wait_for_function(
            """(corners) => {
                const v = window.__catanDebug.getBoard().vertices || {};
                return corners.filter(k => v[k] && v[k].building).length === 5;
            }""",
            arg=corners,
            timeout=10000,
        )

        # And the event log names it an eruption — the disappearance is not left
        # to be read as a bug.
        log_text = alice.page.inner_text("#log-entries")
        assert "erupt" in log_text.lower(), log_text

        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
