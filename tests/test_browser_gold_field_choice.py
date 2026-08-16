"""The Seafarers gold-field resource choice, in a real browser.

The new visible surface is the roll-time prompt: when a gold field's number is
rolled, its adjacent owner is asked to pick a resource of their choice, and the
existing pending-choice panel draws that pick as the five resource tiles. The
regression it guards against — invisible to the unit suite, which only sees the
resolver once it is called — is the panel not appearing, the tiles emitting
nothing, or the chosen resource never reaching the hand.

A gold field must also render distinctly on the board; the canvas assertion
counts the gold-coloured pixels in the gold hex so a hex that painted as plain
terrain (or not at all) fails.

Run: pytest tests/test_browser_gold_field_choice.py -m slow -q
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
from game import persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}


def _gold_choice_game():
    """A started game, Alice's settlement on a gold field, her resource choice
    already opened by the roll of the field's number. The caller only reads it.
    Returns the game and the gold hex's key so the canvas test can find it."""
    rules = dict(rules_module.defaults())
    rules['gold_field_choice'] = True
    rules['turn_order'] = 'lobby'
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0

    gold_key = None
    for vertex_key in sorted(game.vertices):
        vertex = game.vertices[vertex_key]
        for hex_key in vertex.neighbors.get('hexes', []):
            hex_obj = game.hexes.get(hex_key)
            if hex_obj and hex_obj.type != 'ocean':
                hex_obj.type, hex_obj.number = 'gold', 9
                # Silence the vertex's other hexes so the roll pays for the gold
                # field alone.
                for other in vertex.neighbors.get('hexes', []):
                    if other != hex_key and game.hexes[other].type != 'ocean':
                        game.hexes[other].number = None
                vertex.building = {'type': 'settlement', 'player': 'Alice'}
                game.get_player('Alice').settlements.append(vertex_key)
                gold_key = hex_key
                break
        if gold_key:
            break
    assert gold_key is not None

    game.set_dice_rolled()
    game.distribute_resources(9)
    assert game.pending_choice_for('Alice')['kind'] == 'gold_field_choice'
    return game, gold_key


# Render one frame, then count the gold-coloured pixels in the gold hex. The
# gold terrain paints #d9a441 (light) / #c99a3e (dark); the band spans both and
# excludes the ocean blue and the green land around it. A plain or blank hex
# leaves the count near zero.
SAMPLE_GOLD = """
(hexKey) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    window.BoardRenderer.render(board, 'board-canvas', null, null, []);
    const layout = window.BoardRenderer.computeLayout(board);
    const point = layout.hexPositions[hexKey];
    const client = window.BoardRenderer.boardToClient(
        canvas, point.x + layout.offsetX, point.y + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    // Wide enough to reach past the number token at the hex centre to the gold
    // body around it.
    const half = 40;
    const data = canvas.getContext('2d')
        .getImageData(x - half, y - half, half * 2, half * 2).data;
    let gold = 0;
    for (let i = 0; i < data.length; i += 4) {
        const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
        if (a !== 0 && r >= 170 && r <= 240 && g >= 120 && g <= 190
            && b >= 30 && b <= 110 && r > g && g > b && (r - b) > 80) {
            gold++;
        }
    }
    return gold;
}
"""


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def test_the_gold_field_prompts_the_owner_and_pays_the_pick(browser, tmp_path):
    game, gold_key = _gold_choice_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = Player(browser, url, "Alice", viewport=VIEWPORT)
        alice.page.check("#role-player")
        alice.page.fill("#username", "Alice")
        alice.page.click("#join-btn")
        alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        wait_for_board_painted(alice)
        next_frame(alice.page)

        # The gold field paints its own colour — a hex that rendered as plain
        # terrain or not at all leaves this near zero.
        gold_pixels = alice.page.evaluate(SAMPLE_GOLD, gold_key)
        assert gold_pixels > 800, gold_pixels

        # The roll opened Alice's resource choice: the panel is up and offers the
        # five resource tiles.
        alice.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)
        options = alice.page.eval_on_selector_all(
            "#choice-options .choice-option",
            "els => els.map(e => e.dataset.choiceOption)",
        )
        assert sorted(options) == ["brick", "ore", "sheep", "wheat", "wood"], options

        # Alice holds nothing until she picks.
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').resources.wood || 0"
        ) == 0

        # Pick wood: the chosen card reaches her hand and the panel closes.
        alice.page.click("#choice-options .choice-option[data-choice-option='wood']")
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').resources.wood === 1",
            timeout=8000,
        )
        alice.page.wait_for_function(
            "() => document.getElementById('choice-panel')"
            ".classList.contains('hidden')",
            timeout=8000,
        )
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
