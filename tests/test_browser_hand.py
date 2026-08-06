"""The resource hand and the bank, in a real browser.

The hand is a fan of physical cards in the bottom tray: each held card is a
terrain-coloured face with the resource glyph, a count in the corner and a label
strip, and a card at zero greys rather than disappearing. The bank stays a tile,
a thin stock meter and the real card count. These assertions are written against
what a broken conversion actually does, not what the DOM merely says:

  - a card whose `<use>` points at a missing sprite id renders nothing while
    every DOM assertion over it still passes, so the glyph is proved through the
    SVG engine's own getBBox - a zero-area box is a glyph that did not paint;
  - the bank counts are read back against the real payload bank, so a cell that
    quietly showed a client constant instead of the game's stock would fail;
  - the meter width is checked against that stock over the table's own
    bank_resource_limit, the number the old hardcoded 19 got wrong; and
  - a resource at zero is proved greyed and still present, not dropped.

Arranged with the real engine and written to the save file the server restores
on boot, as the other browser suites do: a hand with chosen zeros and a bank
drawn down unevenly are many non-deterministic turns away through the UI.

Run: pytest tests/test_browser_hand.py -m slow -v
"""

import os
import random
import re
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    browser_session,
    next_frame,
    start_server,
    stop_server,
)
from game import persistence
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1600, "height": 1000}

# Screenshots land beside the mockup this was signed off against, so a human can
# put the two side by side.
SHOT_DIR = "/home/kalin/.claude/jobs/824814a1/tmp"

TABLE = ["Alice", "Bob"]
RESOURCE_ORDER = ["wood", "brick", "sheep", "wheat", "ore"]

# Two zeros in hand (brick, wheat), so "greyed not gone" is a state the panel is
# actually in, and no two held counts share a number.
HAND = {"wood": 3, "brick": 0, "sheep": 2, "wheat": 0, "ore": 5}

# A bank drawn down unevenly against the base-game 19: brick nearly full, sheep
# out entirely, the rest partway. Every width is a different fraction, so a meter
# stuck at one value cannot pass.
BANK = {"wood": 15, "brick": 18, "sheep": 0, "wheat": 8, "ore": 12}

# The emoji ranges the old hand/bank drew from. A player must see none of them.
EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f300-\U0001f6ff]"
)


def shot(player, label):
    """One screenshot per theme, with the bank fold open so both are in frame."""
    os.makedirs(SHOT_DIR, exist_ok=True)
    paths = []
    for theme in ("light", "dark"):
        player.page.evaluate(
            "t => document.documentElement.setAttribute('data-theme', t)", theme
        )
        next_frame(player.page)
        path = os.path.join(SHOT_DIR, f"ui-hand-{label}-{theme}.png")
        player.page.screenshot(path=path, full_page=False)
        paths.append(path)
    player.page.evaluate("() => document.documentElement.removeAttribute('data-theme')")
    return paths


def shot_narrow(player, label):
    """The fan at a phone width, to prove it neither overflows nor pushes the
    page wide - shot after the viewport is narrowed so the responsive rules run."""
    os.makedirs(SHOT_DIR, exist_ok=True)
    player.page.set_viewport_size({"width": 390, "height": 780})
    next_frame(player.page)
    path = os.path.join(SHOT_DIR, f"ui-hand-{label}-390.png")
    player.page.screenshot(path=path, full_page=False)
    player.page.set_viewport_size(VIEWPORT)
    next_frame(player.page)
    return path


# --- Arranging a table -----------------------------------------------------


def build_game():
    game = Game(list(TABLE), [], rng=random.Random(7))
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    actor = game.current_player_name()
    game.get_player(actor).resources.update(HAND)
    game.bank.resources = dict(BANK)
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
        yield tabs[game.current_player_name()]
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


# --- Reading what is on screen ---------------------------------------------

# Per bank tile: its own box, whether its `<use>` resolves to a symbol that
# exists, and the SVG-rendered bounding box of the glyph the `<use>`
# instantiates. A broken or empty `<use>` reports a zero-area getBBox even though
# the tile box is a perfectly good 30x30 - exactly the trap a DOM check falls
# into.
TILES = """
selector => Array.from(document.querySelectorAll(selector + ' .tile')).map(tile => {
    const box = tile.getBoundingClientRect();
    const use = tile.querySelector('use');
    const href = use && (use.getAttribute('href') || use.getAttribute('xlink:href'));
    let glyph = {width: 0, height: 0};
    try { const b = use.getBBox(); glyph = {width: b.width, height: b.height}; }
    catch (e) { /* an unresolved use throws; a zero box below reports it */ }
    return {
        tileW: box.width, tileH: box.height,
        symbolFound: !!(href && document.querySelector(href)),
        glyphW: glyph.width, glyphH: glyph.height,
    };
})
"""

# Per hand card: the card's own box (a fanned card is a real physical rectangle,
# not a zero-height strip), and its glyph the same way the bank's is proved - a
# card whose `<use>` names a renamed sprite paints an empty getBBox while the
# card box stays a perfect 70x98.
HAND_CARDS = """
() => Array.from(document.querySelectorAll('#resource-display .hand-card')).map(card => {
    const box = card.getBoundingClientRect();
    const use = card.querySelector('.hand-card-glyph use');
    const href = use && (use.getAttribute('href') || use.getAttribute('xlink:href'));
    let glyph = {width: 0, height: 0};
    try { const b = use.getBBox(); glyph = {width: b.width, height: b.height}; }
    catch (e) { /* an unresolved use throws; a zero box below reports it */ }
    return {
        cardW: box.width, cardH: box.height,
        symbolFound: !!(href && document.querySelector(href)),
        glyphW: glyph.width, glyphH: glyph.height,
    };
})
"""

HAND_CELLS = """
() => Array.from(document.querySelectorAll('#resource-display .hand-card')).map(card => ({
    count: card.querySelector('.hand-card-count').textContent.trim(),
    spent: card.classList.contains('spent'),
    gone: getComputedStyle(card).display === 'none',
}))
"""

# The greyed count and a kept one must differ in colour, and the greyed card must
# still be laid out - "spent, not gone" is a class doing visible work, not a
# name on an invisible node.
SPENT_STYLE = """
() => {
    const cards = Array.from(document.querySelectorAll('#resource-display .hand-card'));
    const spent = cards.find(c => c.classList.contains('spent'));
    const kept = cards.find(c => !c.classList.contains('spent'));
    return {
        spentColor: getComputedStyle(spent.querySelector('.hand-card-count')).color,
        keptColor: getComputedStyle(kept.querySelector('.hand-card-count')).color,
        spentVisible: getComputedStyle(spent).display !== 'none'
            && spent.getBoundingClientRect().width > 0,
    };
}
"""

BANK_CELLS = """
() => Array.from(document.querySelectorAll('#bank-display .bank-cell')).map(cell => {
    const track = cell.querySelector('.meter').getBoundingClientRect().width;
    const fill = cell.querySelector('.meter i').getBoundingClientRect().width;
    return {
        count: cell.querySelector('.pct').textContent.trim(),
        fillFraction: track > 0 ? fill / track : 0,
    };
})
"""


def open_bank(player):
    # v2.1: the bank is a big, always-on panel in the right column, not a fold -
    # there is nothing to open, so this just waits for it to have rendered.
    player.page.wait_for_selector("#bank-display .bank-cell", timeout=5000)


# --- The hand --------------------------------------------------------------


def test_every_hand_card_paints_its_glyph(player):
    """A card is a coloured rectangle and a glyph; the rectangle alone is not the
    card. Each card has a real box and a non-zero glyph bbox, so a `<use>` pointed
    at a renamed sprite - which paints nothing - fails here rather than sailing
    through on the box."""
    cards = player.page.evaluate(HAND_CARDS)
    assert len(cards) == len(RESOURCE_ORDER), cards
    for card in cards:
        assert card["cardW"] > 0 and card["cardH"] > 0, card
        assert card["symbolFound"], f"a card's <use> resolves to no sprite: {card}"
        assert card["glyphW"] > 0 and card["glyphH"] > 0, (
            f"a card's glyph did not render (empty getBBox): {card}"
        )


def test_the_hand_counts_match_the_payload(player):
    """The count beside each tile is the game's own, in board order."""
    cells = player.page.evaluate(HAND_CELLS)
    held = player.me()["resources"]
    assert [c["count"] for c in cells] == [str(held[r]) for r in RESOURCE_ORDER], cells


def test_a_zero_resource_is_greyed_not_gone(player):
    """brick and wheat are held at zero: their cells stay, marked `.spent`, and
    every non-zero cell is not."""
    cells = player.page.evaluate(HAND_CELLS)
    spent = {RESOURCE_ORDER[i] for i, c in enumerate(cells) if c["spent"]}
    assert spent == {"brick", "wheat"}, spent
    assert not any(c["gone"] for c in cells), "a resource cell was dropped, not greyed"

    style = player.page.evaluate(SPENT_STYLE)
    assert style["spentVisible"], "the greyed cell is not actually on screen"
    assert style["spentColor"] != style["keptColor"], (
        "the greyed count is styled no differently from a kept one"
    )


def test_the_rendered_hand_has_no_emoji(player):
    """The whole point of the tile set: not one of the old glyphs survives."""
    text = player.page.inner_text("#resource-display")
    assert not EMOJI.search(text), f"an emoji is still in the hand: {text!r}"


# --- The bank --------------------------------------------------------------


def test_every_bank_tile_paints_its_glyph(player):
    open_bank(player)
    tiles = player.page.evaluate(TILES, "#bank-display")
    assert len(tiles) == len(RESOURCE_ORDER), tiles
    for tile in tiles:
        assert tile["tileW"] > 0 and tile["tileH"] > 0, tile
        assert tile["symbolFound"], f"a bank tile's <use> resolves to nothing: {tile}"
        assert tile["glyphW"] > 0 and tile["glyphH"] > 0, (
            f"a bank tile's glyph did not render: {tile}"
        )


def test_the_bank_shows_the_real_stock_not_a_constant(player):
    """The count under each meter is the game's bank, read from the payload the
    server sent - a cell that printed a client-side limit instead would disagree
    with a bank drawn down like this one."""
    open_bank(player)
    cells = player.page.evaluate(BANK_CELLS)
    bank = player.board()["bank"]
    assert [c["count"] for c in cells] == [str(bank[r]) for r in RESOURCE_ORDER], cells
    # And it is the arranged stock, so the assertion above is checking a real
    # depletion and not two copies of the same wrong number.
    assert [c["count"] for c in cells] == [str(BANK[r]) for r in RESOURCE_ORDER]


def test_the_bank_meter_tracks_the_stock_over_the_table_limit(player):
    """Each fill is count / bank_resource_limit, the limit read from the table's
    rules and not a hardcoded 19. sheep is out, so its fill is empty."""
    open_bank(player)
    cells = player.page.evaluate(BANK_CELLS)
    limit = player.board()["rules"]["bank_resource_limit"]
    for resource, cell in zip(RESOURCE_ORDER, cells, strict=True):
        expected = BANK[resource] / limit
        assert abs(cell["fillFraction"] - expected) < 0.03, (
            f"{resource}: meter at {cell['fillFraction']:.2f}, stock says {expected:.2f}"
        )


def test_the_rendered_bank_has_no_emoji(player):
    open_bank(player)
    text = player.page.inner_text("#bank-display")
    assert not EMOJI.search(text), f"an emoji is still in the bank: {text!r}"


def test_the_fan_does_not_push_the_page_wide_at_phone_width(player):
    """At 390px the fan tightens or scrolls within the tray; the document body
    must not gain a horizontal scrollbar - a fan that overran would."""
    player.page.set_viewport_size({"width": 390, "height": 780})
    next_frame(player.page)
    overflow = player.page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    player.page.set_viewport_size(VIEWPORT)
    next_frame(player.page)
    assert overflow <= 1, f"the page scrolls horizontally by {overflow}px at 390 wide"


def test_a_human_can_look_at_it(player):
    """Not an assertion - the screenshots the sign-off is read from."""
    open_bank(player)
    assert player.page.is_visible("#resource-display")
    shot(player, "fan")
    shot_narrow(player, "fan")
    assert not player.noisy_errors(), player.noisy_errors()
