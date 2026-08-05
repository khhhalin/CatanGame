"""Playing progress cards, driven in a real browser.

Every one of the 54 Cities & Knights progress cards has been dealt, held and
described by the client since the expansion landed, and 26 of them could never
be played: the hand rendered a card whose target had to be picked on the board,
greyed the Play button out and said so. A player drew a Merchant — the most
common card in the deck — and watched it sit in their hand for the rest of the
game.

So these tests play the cards. Each one asserts the *effect* landed, not that a
button was clickable: a Play that emits and is refused looks identical in the
DOM to one that worked.

The hands are arranged with the real engine and written to the save file the
server restores on boot, exactly as `test_browser_knights.py` does — a card is
drawn on a city gate at a rate no browser test can wait for. Everything after
the save is the real client and the real server.

Run: pytest tests/test_browser_progress_cards.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    legal_road_edges,
    start_server,
    stop_server,
)
from game import persistence, progress_cards
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(REPO, "test-artifacts", "ui", "progress-cards")

TABLE = ["Alice", "Bob"]

EMPTY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0}


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- Arranging a hand ------------------------------------------------------


def _inland_vertices(game):
    """Intersections ringed by three land hexes, well in from the coast."""
    return [
        key for key in sorted(game.vertices)
        if len(game.vertices[key].neighbors["hexes"]) == 3
        and all(game.hexes[h].type != "ocean"
                for h in game.vertices[key].neighbors["hexes"])
    ]


def _roads_around(game, player_name, vertex_key):
    """Give the player every road leaving one intersection."""
    player = game.get_player(player_name)
    for edge_key in game.vertices[vertex_key].neighbors["edges"]:
        game.edges[edge_key].road = {"player": player_name}
        player.roads.append(edge_key)


def _hand(game, player_name, **cards):
    player = game.get_player(player_name)
    player.resources.update(EMPTY_HAND)
    player.resources.update(cards)


def _give_card(game, player_name, card_id):
    game.ck.hand_of(player_name).append(card_id)


def build_game(build):
    """A started Cities & Knights game, mid-turn, with `build` applied.

    The dice are already up: every card but the Alchemist is refused before the
    roll, and the client greys them out for the same reason.
    """
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
def table(browser, data_dir, build):
    """A running server restored from `build`, with both players connected."""
    game, marks = build_game(build)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    tabs = {}
    try:
        for name in TABLE:
            player = Player(browser, url, name, viewport=VIEWPORT)
            # Not Player.join(): that waits for the lobby, and a join into a
            # running game is answered with the game screen instead.
            player.page.check("#role-player")
            player.page.fill("#username", name)
            player.page.click("#join-btn")
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
            tabs[name] = player
        yield tabs[game.current_player_name()], marks, tabs
    finally:
        stop_server(proc)


# --- Driving the progress card fold ----------------------------------------


def open_progress_fold(player):
    """Raise the Progress Cards fold if it is not already up."""
    if player.page.get_attribute("#progress-cards-chip", "aria-expanded") != "true":
        player.page.click("#progress-cards-chip")


def close_progress_fold(player):
    player.page.keyboard.press("Escape")


def press_play(player, card_id):
    open_progress_fold(player)
    player.page.wait_for_selector(
        f"[data-progress-card='{card_id}']:not([disabled])", timeout=5000
    )
    player.page.click(f"[data-progress-card='{card_id}']")


def hand_of(player):
    return player.page.evaluate(
        "() => window.__catanDebug.getBoard().cities_knights.progress_hand"
    )


def wait_for_card_spent(player, card_id):
    player.page.wait_for_function(
        "id => !window.__catanDebug.getBoard()"
        "  .cities_knights.progress_hand.includes(id)",
        arg=card_id, timeout=8000,
    )


# --- Fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def a_road_building_card(game):
    """A road network to extend, an empty hand, and the card."""
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor)
    _give_card(game, actor, "road_building")
    return {"home": home}


@pytest.fixture
def road_building(browser, tmp_path):
    with table(browser, tmp_path, a_road_building_card) as live:
        yield live


# --- Road Building ---------------------------------------------------------
#
# The cheapest of the 13 blocked cards: the server already takes no target for
# it — the roads go down afterwards through the ordinary free-road flow — and
# the client greyed it out anyway, because its catalogue entry says `road`.


class TestRoadBuilding:
    def test_road_building_is_playable_and_pays_for_two_roads(self, road_building):
        """Play it with an empty hand, then build two roads that cost nothing.

        Both halves matter: the card was unplayable, and a card that granted
        the roads without the build flow arming would be just as useless.
        """
        player, marks, _ = road_building

        assert hand_of(player) == ["road_building"]
        press_play(player, "road_building")
        wait_for_card_spent(player, "road_building")

        player.page.wait_for_function(
            "() => window.__catanDebug.getBoard().free_roads_remaining === 2",
            timeout=8000,
        )
        close_progress_fold(player)
        assert player.page.is_visible("#free-roads-indicator"), (
            "the free roads were granted with nothing on screen to say so"
        )
        shot(player, "road-building-free-roads")

        for expected_left in (1, 0):
            board = player.board()
            build_road(player, legal_road_edges(board, player.name))
            player.page.wait_for_function(
                "left => window.__catanDebug.getBoard().free_roads_remaining === left",
                arg=expected_left, timeout=8000,
            )

        assert dict((player.me() or {}).get("resources") or {}) == EMPTY_HAND, (
            "the free roads were paid for out of the hand"
        )
        assert player.noisy_errors() == [], player.noisy_errors()


# --- Nothing may be permanently unplayable ---------------------------------


class TestEveryCardCanBeReached:
    """The test that stops this whole class of bug coming back.

    Driven from the catalogue the server sends, never from a list copied into
    the test: a card added to `progress_cards.py` with no client flow has to
    fail here rather than quietly join the 26 that a player could hold forever.
    """

    def test_no_card_type_is_permanently_unplayable(self, road_building):
        player, _marks, _tabs = road_building

        stuck = player.page.evaluate(
            """
            () => {
                const board = window.__catanDebug.getBoard();
                const catalogue = board.cities_knights.progress_cards;
                return Object.entries(catalogue)
                    .filter(([, card]) => window.__catanDebug
                        .progressCardHasNoFlow(card))
                    .map(([id]) => id);
            }
            """
        )
        assert stuck == [], (
            f"{len(stuck)} progress card types can be held but never played: {stuck}"
        )

    def test_the_catalogue_the_client_sees_is_the_whole_deck(self, road_building):
        """And the check above is worth something only if it covers every card."""
        player, _marks, _tabs = road_building
        catalogue = player.page.evaluate(
            "() => Object.keys("
            "  window.__catanDebug.getBoard().cities_knights.progress_cards)"
        )
        assert sorted(catalogue) == sorted(progress_cards.CARDS_BY_ID)
