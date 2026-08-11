"""Cotton in the hand, in a real browser.

`test_browser_hand.py` proves a standard game shows exactly the five resource
cards and no cotton — that is the base-UI-unchanged half of this feature. This is
the other half: a game on a map that deals cotton must show a sixth card, drawn
entirely from the resource registry the server sent — its cream fill, the cloth
glyph, the name "Cotton" — with no cotton hardcoded anywhere in the client.

The glyph is proved through the SVG engine's own getBBox, as the hand suite does:
a `<use>` pointed at a missing sprite paints nothing while every DOM check over it
still passes, so a zero-area box is the real failure. The fill is read back as the
computed colour, so a cotton card left grey (no registry colour applied) fails
here rather than sailing through on the card box.

The game is a custom cotton map, persisted inline to the save file the server
restores on boot — a custom map travels in the game file itself, so no map store
is needed.

Run: pytest tests/test_browser_cotton.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import Player, browser_session, start_server, stop_server
from game import board as board_module
from game import maps, persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

# A small island with one cotton hex (mirrors tests/game/test_cotton.py; inlined
# because that module is not importable from the tests root).
MAINLAND = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))
COTTON_MAP = {
    'map_version': 2, 'id': 'cotton-map', 'name': 'Cotton Map',
    'frame': {'radius': 3},
    'regions': [
        {'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND,
         'pool': {'mode': 'shuffled',
                  'terrain': {'cotton': 1, 'wood': 2, 'wheat': 2, 'sheep': 1, 'desert': 1},
                  'numbers': [3, 4, 5, 6, 9, 10]}},
        {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
         'pool': {'mode': 'shuffled',
                  'terrain': {'sea': len(maps.frame_hex_keys(3)) - len(MAINLAND)},
                  'numbers': []}},
    ],
    'harbours': {'mode': 'bag', 'types': {}},
}


def cotton_game():
    rules = dict(rules_module.defaults())
    rules['board_layout'] = 'custom'
    rules['board_map'] = COTTON_MAP['id']
    game = Game(TABLE, [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(COTTON_MAP))
    game.start()
    game.game_phase = 'playing'
    return game

VIEWPORT = {"width": 1600, "height": 1000}
TABLE = ["Alice", "Bob"]

# A hand with cotton in it, so the sixth card is a state the panel is actually in.
HAND = {"wood": 2, "brick": 0, "sheep": 1, "wheat": 0, "ore": 3, "cotton": 2}

# The registry cream cotton is defined with (server/game/resources.py). The card
# must paint this, not a grey fallback — proof the colour is registry-driven.
COTTON_RGB = "rgb(232, 226, 208)"

HAND_CARDS = """
() => Array.from(document.querySelectorAll('#resource-display .hand-card')).map(card => {
    const use = card.querySelector('.hand-card-glyph use');
    const href = use && (use.getAttribute('href') || use.getAttribute('xlink:href'));
    let glyph = {width: 0, height: 0};
    try { const b = use.getBBox(); glyph = {width: b.width, height: b.height}; }
    catch (e) { /* an unresolved use throws; a zero box below reports it */ }
    return {
        card: card.getAttribute('data-card'),
        label: card.querySelector('.hand-card-label').textContent.trim(),
        symbolFound: !!(href && document.querySelector(href)),
        glyphW: glyph.width, glyphH: glyph.height,
        bg: getComputedStyle(card).backgroundColor,
    };
})
"""


def build_game():
    game = cotton_game()
    game.game_state = "started"
    game.start_turn()
    game.set_dice_rolled()
    game.get_player("Alice").resources.update(HAND)
    return game


@contextmanager
def table(browser, data_dir):
    game = build_game()
    persistence.save(game, os.path.join(str(data_dir), "game.json"))
    proc, url = start_server(data_dir)
    tabs = {}
    try:
        for name in TABLE:
            player = Player(browser, url, name, viewport=VIEWPORT)
            player.page.check("#role-player")
            player.page.fill("#username", name)
            player.page.click("#join-btn")
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
            tabs[name] = player
        yield tabs["Alice"]
    finally:
        stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.fixture
def player(browser, tmp_path):
    with table(browser, tmp_path) as active:
        active.page.wait_for_selector("#resource-display .hand-card", timeout=8000)
        yield active


def test_a_cotton_map_shows_a_sixth_card_drawn_from_the_registry(player):
    """The hand has six cards, the sixth is cotton, and it is drawn from the
    registry: the cloth glyph resolves and renders, its label is "Cotton", and
    its face is the registry cream — none of which is hardcoded in the client."""
    cards = player.page.evaluate(HAND_CARDS)
    assert [c["card"] for c in cards] == [
        "wood", "brick", "sheep", "wheat", "ore", "cotton",
    ], cards

    cotton = next(c for c in cards if c["card"] == "cotton")
    assert cotton["label"] == "Cotton"
    assert cotton["symbolFound"], f"the cotton card's <use> resolves to no sprite: {cotton}"
    assert cotton["glyphW"] > 0 and cotton["glyphH"] > 0, (
        f"the cotton glyph did not render (empty getBBox): {cotton}"
    )
    assert cotton["bg"] == COTTON_RGB, (
        f"the cotton card is not painted its registry cream: {cotton['bg']}"
    )
