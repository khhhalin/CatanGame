"""Each scenario shows only its own side-panel, in a real browser.

A QA pass found the Fishermen panel (fish.js) leaking into every T&B scenario —
it showed whenever `board.tb` existed, but Caravans, Barbarian Attack and the
main scenario all build tb-state — and the Rivers panel (rivers.js) showing its
"The Rivers of Catan" title in Barbarian Attack and the main scenario, because
its gate included the shared `gold_coins`. The real panel was pushed below the
fold by one or two mislabelled strangers.

The regression these guard: a scenario carrying tb-state or gold_coins must not
show another scenario's panel, and the shared coin panel must not claim to be
Rivers when no river rule is on. Invisible to the unit suite, which never renders
the panels.

Run: pytest tests/test_browser_scenario_panels.py -m slow -q
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


def _scenario_game(rules_const, map_id):
    """A started, playing game on a scenario's own preset rules and built-in
    board — the state a table gets after picking the preset in the lobby."""
    chosen = dict(rules_const)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map(map_id))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


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


def test_caravans_shows_no_fishermen_panel(browser, tmp_path):
    """Caravans builds tb-state for its camels, which used to drag the Fishermen
    panel in with it."""
    persistence.save(_scenario_game(rules_module.TB_CARAVANS_RULES, 'caravans'),
                     os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-fish.hidden") is not None, \
            "the Fishermen panel leaked into a Caravans game"
        assert alice.page.query_selector("#right-rivers.hidden") is not None, \
            "the Rivers panel leaked into a Caravans game (no coin rule on)"
        assert alice.page.query_selector("#right-caravans:not(.hidden)") is not None, \
            "the Caravans panel did not appear"
    finally:
        stop_server(proc)


def test_barbarian_attack_shows_coins_not_a_rivers_panel(browser, tmp_path):
    """Barbarian Attack runs on gold_coins, so it wants the coin buy/sell — but
    under a neutral title, not "The Rivers of Catan", and with no Fishermen
    panel."""
    persistence.save(
        _scenario_game(rules_module.TB_BARBARIAN_ATTACK_RULES, 'barbarian-attack'),
        os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-fish.hidden") is not None, \
            "the Fishermen panel leaked into a Barbarian Attack game"
        # The coin panel is welcome (gold_coins is on) but must not claim to be
        # Rivers when no river rule is in play.
        # `.right-eyebrow` upper-cases via CSS, so compare case-insensitively —
        # the text content is what matters, not the styling.
        title = alice.page.inner_text("#rivers-title").strip().lower()
        assert title == "gold coins", \
            f"the coin panel mislabelled itself {title!r} in a Barbarian Attack game"
        assert alice.page.query_selector("#right-barbarian-attack:not(.hidden)") is not None, \
            "the Barbarian Attack panel did not appear"
    finally:
        stop_server(proc)
