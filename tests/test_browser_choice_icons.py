"""The pending-choice dialog draws SVG icons, not emoji, and names them.

choices.js used to head every question with an emoji and prefix every card
option with one (`🌲 wood`). Those are gone: a held card is now a filled
coloured tile that names itself, a piece or action is a monochrome line icon,
and the heading leads with the icon for what the choice is about.

A DOM assertion passes straight over a broken `<use>` - it renders nothing and
the option still reads. So this drives a real dialog and checks what a player
would actually notice:

  - no emoji survives in anything the dialog renders (the regression), and
  - the icons paint a non-zero box, and a card option's tile carries an
    accessible name - the icon is the whole option, so it must.

Both themes, because the tiles are drawn in terrain colours that differ between
them and a glyph that vanished into its tile in one theme would pass the other.

Run: pytest tests/test_browser_choice_icons.py -m slow -v
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
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1280, "height": 900}

TABLE = ["Alice", "Bob"]

EMPTY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0}

# Where the eyeball-it screenshots go. Overridable so a verification run can
# drop them wherever the reviewer is looking; the committed default keeps them
# in the repo's artifacts tree beside every other browser shot.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.environ.get(
    "CHOICES_SHOT_DIR", os.path.join(REPO, "test-artifacts", "ui", "choices")
)

# Anything a player would read as an emoji: the pictographic and symbol blocks
# the old dialog drew from, plus the variation selector that trailed several of
# them. A scan, not a list of the nine that were removed - a tenth creeping
# back in a future edit has to fail this too.
EMOJI = (
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff"
    "\U0001f1e6-\U0001f1ff\U0000fe0f\U000024c2\U00002190-\U000021ff]"
)


def _hand(game, player_name, **cards):
    player = game.get_player(player_name)
    player.resources.update(EMPTY_HAND)
    player.resources.update(cards)


def _give_card(game, player_name, card_id):
    game.ck.hand_of(player_name).append(card_id)


def build_game(build):
    game = Game(
        list(TABLE), [], rng=random.Random(7),
        rules=rules_module.preset_rules("cities_and_knights"),
    )
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    return game, build(game)


@contextmanager
def table(browser, data_dir, build, color_scheme="light"):
    game, marks = build_game(build)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    tabs = {}
    try:
        for name in TABLE:
            player = Player(browser, url, name, viewport=VIEWPORT,
                            color_scheme=color_scheme)
            player.page.check("#role-player")
            player.page.fill("#username", name)
            player.page.click("#join-btn")
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
            tabs[name] = player
        yield tabs[game.current_player_name()], marks, tabs
    finally:
        stop_server(proc)


def a_merchant_fleet_card(game):
    """The card that asks its own player which card type trades at 2:1 - eight
    held-card options, so eight filled tiles."""
    actor = game.current_player_name()
    _hand(game, actor)
    _give_card(game, actor, "merchant_fleet")
    return {}


def a_spy_card(game):
    """The Spy, whose question is answered with a progress card - a line icon,
    not a tile."""
    actor = game.current_player_name()
    victim = next(name for name in TABLE if name != actor)
    _hand(game, actor)
    _give_card(game, actor, "spy")
    _give_card(game, victim, "irrigation")
    return {"victim": victim}


def press_play(player, card_id):
    if player.page.get_attribute("#progress-cards-chip", "aria-expanded") != "true":
        player.page.click("#progress-cards-chip")
    player.page.wait_for_selector(
        f"[data-progress-card='{card_id}']:not([disabled])", timeout=5000
    )
    player.page.click(f"[data-progress-card='{card_id}']")


def open_merchant_fleet_choice(player):
    press_play(player, "merchant_fleet")
    player.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)


def dialog_text(player):
    """Everything the open dialog renders, as one string."""
    return player.page.evaluate(
        """() => ['#choice-prompt', '#choice-context', '#choice-options']
            .map(sel => document.querySelector(sel)?.textContent || '')
            .join(' ')"""
    )


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"choices-{label}.png")
    player.page.locator("#choice-panel").screenshot(path=path)
    return path


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_choice_dialog_draws_named_icons_and_no_emoji(browser, tmp_path, theme):
    """A card choice heads with a line icon and offers filled, named tiles."""
    with table(browser, tmp_path, a_merchant_fleet_card, color_scheme=theme) as live:
        player, _marks, _tabs = live
        open_merchant_fleet_choice(player)
        next_frame(player.page)

        text = dialog_text(player)
        leaked = re.findall(EMOJI, text)
        assert not leaked, f"the {theme} dialog still renders emoji: {leaked!r} in {text!r}"

        # The heading's line icon paints a real box.
        title_area = player.page.evaluate(
            """() => {
                const use = document.querySelector('#choice-prompt svg.icon use');
                if (!use) return null;
                const box = use.getBBox();
                return box.width * box.height;
            }"""
        )
        assert title_area, "the heading icon is missing or paints nothing"

        # Every option is a filled tile with an accessible name, and each one
        # paints. The tile is the whole option here - no text beside it - so a
        # nameless tile would leave the button unlabelled.
        options = player.page.evaluate(
            """() => Array.from(document.querySelectorAll('#choice-options .choice-option'))
                .map(button => {
                    const svg = button.querySelector('svg[role="img"]');
                    const box = svg && svg.querySelector('use')
                        ? (b => b.width * b.height)(svg.querySelector('use').getBBox())
                        : 0;
                    return {
                        tile: Boolean(button.querySelector('span.tile')),
                        name: svg && svg.getAttribute('aria-label'),
                        area: box,
                    };
                })"""
        )
        assert options, "the dialog offered no options"
        assert all(option["tile"] for option in options), (
            f"a card option was not a filled tile: {options}"
        )
        assert all(option["name"] for option in options), (
            f"a card option's icon has no accessible name: {options}"
        )
        assert all(option["area"] for option in options), (
            f"a card option's icon paints an empty box: {options}"
        )

        shot(player, f"merchant-fleet-{theme}")
        assert player.noisy_errors() == [], player.noisy_errors()


def test_a_line_icon_choice_option_has_no_emoji(browser, tmp_path):
    """The Spy's options are progress cards - a line icon and the card's name,
    not a tile - and still no emoji anywhere in the dialog."""
    with table(browser, tmp_path, a_spy_card) as live:
        player, _marks, _tabs = live
        press_play(player, "spy")
        player.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)
        next_frame(player.page)

        text = dialog_text(player)
        assert not re.findall(EMOJI, text), f"the Spy dialog renders emoji: {text!r}"

        area = player.page.evaluate(
            """() => {
                const use = document.querySelector('#choice-options .choice-option svg.icon use');
                if (!use) return null;
                const box = use.getBBox();
                return box.width * box.height;
            }"""
        )
        assert area, "the Spy option's line icon is missing or paints nothing"
        # The card's name is still there as text beside the icon.
        assert player.page.inner_text("#choice-options .choice-option").strip(), (
            "the Spy option lost its card name"
        )
        shot(player, "spy")
        assert player.noisy_errors() == [], player.noisy_errors()
