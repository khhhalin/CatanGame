"""The Cities & Knights and dev-card panels draw the icon set, not emoji.

Every glyph in `cities-knights.js` and `dev-cards.js` was an emoji until the
inline-SVG icon set replaced them. Two things can go wrong and both are silent:
a stray emoji left behind reads as text a screen reader spells out, and a
misspelled `<use href="#i-...">` resolves to nothing and paints an empty box
that satisfies every DOM assertion there is.

So this drives a real C&K table and a real dev-card hand in the browser and, for
each panel a player actually sees:

  - scans its rendered text for any emoji, catching one left behind;
  - reads the SVG geometry back, so a glyph whose sprite id does not resolve
    fails here rather than shipping as a blank.

The hands and the board are arranged with the real engine and written to the
save the server restores on boot, exactly as `test_browser_knights.py` does.
Screenshots land in test-artifacts (or CK_ICON_SHOT_DIR, both themes) for a
human to sign the look off against the mockup.

Run: pytest tests/test_browser_ck_icons.py -m slow -v
"""

import os
import random
import re
from contextlib import contextmanager

import pytest
from browser_harness import Player, browser_session, start_server, stop_server
from game import cities_knights as ck_module
from game import persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Overridable so the sign-off run can drop the shots wherever the reviewer looks;
# a committed default keeps them in the repo's own artifact tree otherwise.
SHOT_DIR = os.environ.get(
    "CK_ICON_SHOT_DIR", os.path.join(REPO, "test-artifacts", "ui", "ck-icons")
)

TABLE = ["Alice", "Bob"]
EMPTY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0}

# Pictographic emoji, the regional-indicator pair, the two dingbats the old code
# used (heavy check / sword-ish), and the VS-16 that turns a glyph coloured. Not
# `·` (00B7), `—` (2014) or `’` (2019): those are punctuation, and the panels
# keep using them.
EMOJI = re.compile(
    "[\U0001f000-\U0001faff"
    "\U00002600-\U000027bf"
    "\U00002190-\U000021ff"
    "\U00002b00-\U00002bff"
    "\U0001f1e6-\U0001f1ff"
    "\U0000fe0f\U00002705\U00002714\U00002716]"
)


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"ck-{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- Arranging the board ---------------------------------------------------


def _inland_vertices(game):
    return [
        key for key in sorted(game.vertices)
        if len(game.vertices[key].neighbors["hexes"]) == 3
        and all(game.hexes[h].type != "ocean"
                for h in game.vertices[key].neighbors["hexes"])
    ]


def _roads_around(game, player_name, vertex_key):
    player = game.get_player(player_name)
    for edge_key in game.vertices[vertex_key].neighbors["edges"]:
        game.edges[edge_key].road = {"player": player_name}
        player.roads.append(edge_key)


def build_game(build, rules=None):
    game = Game(list(TABLE), [], rng=random.Random(7), rules=rules)
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    return game, build(game)


@contextmanager
def table(browser, data_dir, build, scheme, rules=None):
    """A running server restored from `build`, with the player on turn joined
    under the given colour scheme."""
    game, marks = build_game(build, rules)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    try:
        name = game.current_player_name()
        player = Player(browser, url, name, viewport=VIEWPORT, color_scheme=scheme)
        player.page.check("#role-player")
        player.page.fill("#username", name)
        player.page.click("#join-btn")
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        yield player, marks
    finally:
        stop_server(proc)


def a_full_ck_board(game):
    """Knights of two ranks, a walled city, a built improvement track with its
    metropolis, a Defender card, and a progress card in hand.

    Every icon the C&K panels can draw is on screen at once: the knight rank
    swords, the wall and knight chips, the commodity tiles on the tracks, the
    city glyph on the metropolis, the shield on the Defender note, the ship /
    knight / city on the barbarian chip and the dev glyph on the progress fold.
    """
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)

    spots = list(game.vertices[home].neighbors["vertices"])
    basic = ck_module.Knight(spots[0])
    basic.active = True
    strong = ck_module.Knight(spots[1], 2)
    game.ck.knights_of(actor).append(basic)
    game.ck.knights_of(actor).append(strong)

    game.vertices[home].building = {"type": "city", "player": actor}
    game.get_player(actor).cities.append(home)
    game.ck.register(actor)
    game.ck.city_walls[actor] = [home]
    game.ck.improvements[actor]["trade"] = 3
    game.ck.metropolis["trade"] = actor
    game.ck.metropolis_vertex["trade"] = home
    game.ck.defender_cards[actor] = 1
    game.ck.hand_of(actor).append("merchant")
    return {"home": home}


def a_hand_of_dev_cards(game):
    """The player holding one of every development card type.

    A base game, deliberately: progress cards replace the dev deck and hide its
    fold, so the dev-card fold is only on screen with the progress-card rule off.
    """
    actor = game.current_player_name()
    for card_type in ("knight", "two_roads", "invention", "monopoly", "victory_point"):
        game.get_player(actor).dev_cards[card_type]["count"] = 1
    return {}


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


# --- Reading the panels ----------------------------------------------------


# Every SVG glyph in a container, with the geometry that proves it painted and
# whether its `<use>` actually resolves to a symbol in the sprite. A broken
# reference gives an empty box (0x0) and a null target, which is the failure a
# DOM-only assertion sails straight past.
_ICONS_IN = """
selector => {
    const root = document.querySelector(selector);
    if (!root) { return null; }
    return [...root.querySelectorAll('svg.icon')].map(svg => {
        let box = {width: 0, height: 0};
        try { box = svg.getBBox(); } catch (e) { /* not rendered */ }
        const use = svg.querySelector('use');
        const href = use && (use.getAttribute('href')
            || use.getAttribute('xlink:href'));
        return {
            width: box.width,
            height: box.height,
            href: href,
            resolves: Boolean(href && document.querySelector(href)),
        };
    });
}
"""


def icons_in(player, selector):
    result = player.page.evaluate(_ICONS_IN, selector)
    assert result is not None, f"{selector} is not in the DOM"
    return result


def text_of(player, selector):
    return player.page.evaluate(
        "selector => (document.querySelector(selector)"
        "  || {}).textContent || ''",
        selector,
    )


def open_fold(player, chip_id):
    if player.page.get_attribute(chip_id, "aria-expanded") != "true":
        player.page.click(chip_id)


def assert_icons_paint(player, selector):
    glyphs = icons_in(player, selector)
    assert glyphs, f"{selector} drew no icons at all"
    for glyph in glyphs:
        assert glyph["resolves"], (
            f"{selector}: <use href={glyph['href']!r}> resolves to no sprite"
        )
        assert glyph["width"] > 0 and glyph["height"] > 0, (
            f"{selector}: {glyph['href']} painted an empty {glyph['width']}x"
            f"{glyph['height']} box"
        )


def assert_no_emoji(player, selector):
    text = text_of(player, selector)
    found = EMOJI.findall(text)
    assert not found, f"{selector} still renders emoji {found}: {text!r}"


# The chip summaries are on screen collapsed; the detail lives behind a fold.
# The improvements chip is text only ("Trade 0/5 · …"), so it is emoji-scanned
# but carries no glyph to paint.
CK_ICON_CHIPS = [
    "#knights-chip-value",
    "#barbarian-chip-value",
    "#progress-cards-chip-value",
]
CK_TEXT_CHIPS = CK_ICON_CHIPS + ["#improvements-chip-value"]
CK_FOLDS = [
    ("#knights-chip", "#knights-panel"),
    ("#barbarian-chip", "#barbarian-panel"),
    ("#improvements-chip", "#improvements-panel"),
    ("#progress-cards-chip", "#progress-cards-panel"),
]

CK_RULES = rules_module.preset_rules("cities_and_knights")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_ck_panels_draw_the_icon_set_without_emoji(browser, tmp_path, scheme):
    with table(browser, tmp_path, a_full_ck_board, scheme, CK_RULES) as (player, _m):
        # The chips first, while everything is still collapsed.
        for chip in CK_TEXT_CHIPS:
            assert_no_emoji(player, chip)
        for chip in CK_ICON_CHIPS:
            assert_icons_paint(player, chip)

        for chip_id, panel in CK_FOLDS:
            open_fold(player, chip_id)
            player.page.wait_for_selector(f"{panel}:not(.hidden)", timeout=5000)
            assert_no_emoji(player, panel)
            assert_icons_paint(player, panel)
            shot(player, f"{panel.strip('#')}-{scheme}")
            player.page.keyboard.press("Escape")

        assert player.noisy_errors() == [], player.noisy_errors()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_dev_card_fold_draws_the_icon_set_without_emoji(browser, tmp_path, scheme):
    with table(browser, tmp_path, a_hand_of_dev_cards, scheme) as (player, _marks):
        assert_no_emoji(player, "#dev-cards-chip-value")
        assert_icons_paint(player, "#dev-cards-chip-value")

        open_fold(player, "#dev-cards-chip")
        player.page.wait_for_selector("#dev-cards-panel:not(.hidden)", timeout=5000)
        assert_no_emoji(player, "#dev-cards-panel")
        assert_icons_paint(player, "#dev-cards-panel")
        shot(player, f"dev-cards-{scheme}")

        assert player.noisy_errors() == [], player.noisy_errors()
