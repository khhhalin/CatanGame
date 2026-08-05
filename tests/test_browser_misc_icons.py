"""The Seafarers controls and the command bar draw icons, never emoji.

The emoji shim was pulled out of `seafarers.js` and `panels.js` and replaced
with the inline-SVG icon set. Three things could regress and leave the render
looking fine to a DOM assertion:

  - the ship count chip and the Build-ship cost fell back to `🚢`/`🌲` text;
  - a `<use href="#i-...">` points at a sprite id the index.html sprite does
    not define, so the box lays out at its CSS size but paints nothing;
  - a player-controlled name reaches the island-points line through innerHTML.

So this suite scans the rendered text for emoji, and — because a broken `<use>`
satisfies every geometry check — it also proves each referenced sprite id is a
`<symbol>` that actually exists in the document.

Run: pytest tests/test_browser_misc_icons.py -m slow -v
"""

import os
import re

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
    wait_for_preset,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1400, "height": 1000}
GAME_SEED = 20260804

SHOT_DIR = "/home/kalin/.claude/jobs/824814a1/tmp"

# Every emoji a panel here ever carried, plus the block they live in: the
# resource/commodity faces, the ship, the island, the party popper, and the
# pieces. A scan, not a whitelist - any pictographic codepoint fails.
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
    "\U0001F1E6-\U0001F1FF\U00002693\U00002694\U0000FE0F]"
)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


def make_sea_table(browser, url, names=("Alice", "Bob")):
    players = [Player(browser, url, name, viewport=VIEWPORT) for name in names]
    for player in players:
        player.join()
    players[0].page.click("#preset-seafarers")
    wait_for_preset(players[0], "seafarers")
    players[0].page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    players[0].page.click("#start-game-btn")
    for player in players:
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    return players


@pytest.fixture(scope="module")
def table(browser, tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("misc-icons"), seed=GAME_SEED)
    players = make_sea_table(browser, url)
    yield players
    stop_server(proc)


def open_seafarers_fold(player):
    if player.page.get_attribute("#seafarers-chip", "aria-expanded") != "true":
        player.page.click("#seafarers-chip")


def open_command_bar(player):
    """Raise the slash-command bar the way a player does: a '/' in the chat."""
    player.page.fill("#chat-input", "/")
    player.page.dispatch_event("#chat-input", "input")
    player.page.wait_for_selector("#command-bar:not(.hidden)", timeout=5000)


def sprite_ids_resolve(player, selector):
    """Every `<use>` under `selector` names a `<symbol>` present in the document.

    A renamed or dropped sprite id leaves the `<svg>` box laid out at its CSS
    size but paints nothing - the exact failure a bounding-box check waves
    through. This is the check that would actually catch it.
    """
    return player.page.eval_on_selector_all(
        f"{selector} use",
        """uses => uses.map(u => {
            const ref = (u.getAttribute('href') || '').replace('#', '');
            return { ref, defined: ref !== '' && !!document.getElementById(ref) };
        })""",
    )


def test_ship_chip_and_build_button_draw_icons_not_emoji(table):
    player = next(p for p in table if p.board()["current_player"] == p.name)
    open_seafarers_fold(player)
    player.page.wait_for_selector("#seafarers-chip-value svg.icon use", timeout=5000)
    player.page.wait_for_selector("#build-ship-btn svg.icon use", timeout=5000)

    chip_text = player.page.text_content("#seafarers-chip-value") or ""
    button_text = player.page.text_content("#build-ship-btn") or ""
    panel_text = player.page.text_content("#seafarers-panel") or ""
    assert not EMOJI_RE.search(chip_text), f"emoji in ship chip: {chip_text!r}"
    assert not EMOJI_RE.search(button_text), f"emoji in build button: {button_text!r}"
    assert not EMOJI_RE.search(panel_text), f"emoji in seafarers panel: {panel_text!r}"

    # The ship chip and the build-ship cost tiles must both point at real
    # sprites, or they lay out empty.
    refs = sprite_ids_resolve(player, "#seafarers-panel")
    assert refs, "no sprite <use> rendered in the seafarers panel"
    broken = [r["ref"] for r in refs if not r["defined"]]
    assert not broken, f"seafarers panel references undefined sprites: {broken}"

    box = player.page.locator("#seafarers-chip-value svg.icon").first.bounding_box()
    assert box and box["width"] > 0 and box["height"] > 0, "ship icon has no box"


def test_command_bar_has_no_emoji(table):
    player = table[0]
    open_command_bar(player)
    player.page.wait_for_selector("#command-list .command-item", timeout=5000)
    bar_text = player.page.text_content("#command-bar") or ""
    assert not EMOJI_RE.search(bar_text), f"emoji in command bar: {bar_text!r}"
    # Any icon the command rows do carry must resolve to a real sprite.
    broken = [r["ref"] for r in sprite_ids_resolve(player, "#command-bar")
              if not r["defined"]]
    assert not broken, f"command bar references undefined sprites: {broken}"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_screenshots_both_themes(table, scheme):
    player = next(p for p in table if p.board()["current_player"] == p.name)
    player.page.emulate_media(color_scheme=scheme)
    open_seafarers_fold(player)
    player.page.wait_for_selector("#seafarers-chip-value svg.icon use", timeout=5000)
    # The build-ship cost tiles live in the popover, not the chip - screenshot
    # it open so the converted resource tiles are in the artifact too.
    player.page.wait_for_selector("#seafarers-popover:not(.hidden)", timeout=5000)
    player.page.wait_for_selector("#build-ship-btn svg.icon use", timeout=5000)
    os.makedirs(SHOT_DIR, exist_ok=True)
    player.page.locator("#seafarers-popover").screenshot(
        path=os.path.join(SHOT_DIR, f"misc-seafarers-{scheme}.png"))
    open_command_bar(player)
    player.page.wait_for_selector("#command-list .command-item", timeout=5000)
    player.page.locator("#command-bar").screenshot(
        path=os.path.join(SHOT_DIR, f"misc-command-bar-{scheme}.png"))
