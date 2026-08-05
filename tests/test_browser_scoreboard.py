"""The scoreboard rail, read the way a player reads it.

The redesign replaced every emoji on the scoreboard with an inline-SVG icon and
rebuilt the player cards and the titles panel. Two things this pins that a DOM
assertion on its own would pass straight over:

  - a broken `<use href>` renders nothing at all, and an emoji creeping back in
    renders fine - so this scans the panel's own text for any emoji, which fails
    the moment a literal returns, and screenshots both themes so the glyphs are
    proven to paint;
  - a scoreboard that shows plausible numbers of its own is worse than none, so
    each rendered count is checked against that player's payload entry rather
    than against a copy of the number the card was built from.

The table is arranged with the real engine and written to the save file the
server restores on boot, as `test_browser_awards.py` does: the scoreboard is
what is under test, not the play that reaches it.

Run: pytest tests/test_browser_scoreboard.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import Player, browser_session, start_server, stop_server
from game import persistence
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1600, "height": 1000}

TABLE = ["Alice", "Bob"]

# Every codepoint an emoji lives at, and none a middot, dash or ellipsis does:
# the panel's own separators (·, —, …) must not read as a smuggled glyph.
_EMOJI = (
    "["
    "\U0001F000-\U0001FAFF"   # symbols, pieces, faces - the bulk of the old set
    "\u2600-\u26FF"           # misc symbols: anchor U+2693, crossed swords U+2694
    "\u2700-\u27BF"           # dingbats
    "\u2B00-\u2BFF"           # stars and arrows
    "\uFE0F"                   # the variation selector that trails many of them
    "]"
)


def _chain(game, player_name, start, length):
    """Lay `length` of one player's roads in an unbranched line from `start`."""
    player = game.get_player(player_name)
    at = start
    laid = []
    for _ in range(length):
        edge_key = next(
            key for key in game.vertices[at].neighbors["edges"]
            if key not in laid and not game.edges[key].road
            and not game.is_sea_edge(key)
        )
        game.edges[edge_key].road = {"player": player_name}
        player.roads.append(edge_key)
        laid.append(edge_key)
        at = next(v for v in game.edges[edge_key].neighbors["vertices"] if v != at)
    return laid


def _settle(game, player_name, vertex):
    game.vertices[vertex].building = {"type": "settlement", "player": player_name}
    game.get_player(player_name).settlements.append(vertex)


def a_table_with_both_awards_held(game):
    """Alice takes Longest Road off a chain of roads; Bob holds Largest Army.

    Both players carry a settlement, some resources and a development card, so
    every chip on the card has a non-zero and a zero to draw across the two.
    """
    home = next(
        key for key, vertex in sorted(game.vertices.items())
        if len(vertex.neighbors["hexes"]) >= 1
        and sum(1 for e in vertex.neighbors["edges"] if not game.is_sea_edge(e)) >= 2
    )
    _settle(game, "Alice", home)
    _chain(game, "Alice", home, 5)
    game.update_longest_road()

    # A settlement for Bob well clear of Alice's, so his own road does not
    # accidentally chain into hers.
    bob_home = next(
        key for key, vertex in sorted(game.vertices.items(), reverse=True)
        if len(vertex.neighbors["hexes"]) >= 1
        and key != home
        and not any(
            (game.edges[e].road or {}).get("player") for e in vertex.neighbors["edges"]
        )
    )
    _settle(game, "Bob", bob_home)

    bob = game.get_player("Bob")
    bob.knights_played = 3
    game.update_largest_army()

    game.get_player("Alice").resources = {"wood": 3, "wheat": 2}
    game.get_player("Alice").dev_cards["knight"]["count"] = 1
    bob.resources = {"ore": 1}

    return {
        "longest_road_holder": game.longest_road_holder,
        "largest_army_holder": game.largest_army_holder,
    }


def build_game(build):
    game = Game(list(TABLE), [], rng=random.Random(7),
                rules={"longest_road_card": True, "largest_army_card": True})
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    marks = build(game)
    return game, marks


@contextmanager
def table(browser, data_dir, build, color_scheme=None):
    game, marks = build_game(build)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    try:
        player = Player(browser, url, TABLE[0], viewport=VIEWPORT,
                        color_scheme=color_scheme)
        # Not Player.join(): a join into a running game is answered with the
        # game screen rather than the lobby.
        player.page.check("#role-player")
        player.page.fill("#username", TABLE[0])
        player.page.click("#join-btn")
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        player.page.wait_for_selector("#game-players .pcard", timeout=10000)
        player.page.wait_for_selector("#award-summary .award", timeout=10000)
        yield player, marks
    finally:
        stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.fixture
def light_table(browser, tmp_path):
    with table(browser, tmp_path, a_table_with_both_awards_held) as live:
        yield live


@pytest.fixture
def dark_table(browser, tmp_path):
    with table(browser, tmp_path, a_table_with_both_awards_held,
               color_scheme="dark") as live:
        yield live


def _panel_text(player):
    """The rendered text of the two panels, together, as a screen reader hears
    it - textContent, so a glyph baked into the markup is caught even where no
    label repeats it."""
    return player.page.evaluate(
        """() => ['#game-players', '#award-summary']
            .map(sel => document.querySelector(sel).textContent).join(' ')"""
    )


def _cards(player):
    return player.page.evaluate(
        """() => Array.from(document.querySelectorAll('#game-players .pcard')).map(card => ({
            name: card.querySelector('.pname').textContent,
            points: card.querySelector('.pvp b').textContent,
            chips: Array.from(card.querySelectorAll('.chip')).map(chip => ({
                text: chip.querySelector('b').textContent,
                label: chip.getAttribute('aria-label'),
            })),
        }))"""
    )


class TestNoEmojiSurvivesOnTheScoreboard:
    def test_the_panels_carry_no_emoji(self, light_table):
        """A literal emoji renders fine where a broken sprite renders nothing,
        so the redesign is only done if the panel's own text has none left."""
        import re

        player, _ = light_table
        text = _panel_text(player)
        found = re.findall(_EMOJI, text)
        assert found == [], f"emoji left on the scoreboard: {found!r} in {text!r}"

    def test_every_glyph_actually_paints(self, light_table):
        """A `<use>` into a missing sprite id draws an empty box that every DOM
        assertion passes over: each icon must have a non-zero rendered size."""
        player, _ = light_table
        boxes = player.page.evaluate(
            """() => Array.from(
                document.querySelectorAll('#game-players .icon, #award-summary .icon')
            ).map(svg => { const r = svg.getBoundingClientRect(); return [r.width, r.height]; })"""
        )
        assert boxes, "no icons rendered on the scoreboard at all"
        assert all(w > 0 and h > 0 for w, h in boxes), (
            f"an icon painted an empty box: {boxes}"
        )


class TestTheNumbersAreTheOnesTheServerSent:
    def test_each_count_matches_that_players_payload(self, light_table):
        """Not a copy of the number the card was built from: each chip is read
        back against that player's entry in the board the server sent."""
        player, _ = light_table
        cards = {card["name"]: card for card in _cards(player)}
        for entry in player.board()["players"]:
            card = cards[entry["name"]]
            chips = {chip["label"]: chip["text"] for chip in card["chips"]}

            settlements = next(t for lbl, t in chips.items() if "settlement" in lbl)
            assert settlements == str(len(entry["settlements"])), (
                f"{entry['name']} has {len(entry['settlements'])} settlements, "
                f"card says {settlements!r}"
            )
            roads = next(t for lbl, t in chips.items() if lbl.endswith("roads"))
            assert roads == str(len(entry["roads"])), entry["name"]
            cards_in_hand = next(t for lbl, t in chips.items() if "resource cards" in lbl)
            assert cards_in_hand == str(entry["resource_count"]), (
                f"{entry['name']} holds {entry['resource_count']} cards, "
                f"card says {cards_in_hand!r}"
            )
            knights = next(t for lbl, t in chips.items() if "knights" in lbl)
            assert knights == str(entry["knights_played"]), entry["name"]
            assert card["points"] == str(entry["victory_points"]), entry["name"]

    def test_the_titles_panel_names_the_right_holder(self, light_table):
        """The point of the panel: Longest Road and Largest Army were in the
        payload and on no screen, so a player could lose one without being
        told."""
        player, marks = light_table
        pills = player.page.evaluate(
            """() => Array.from(document.querySelectorAll('#award-summary .award')).map(p => ({
                title: p.querySelector('b').textContent,
                who: p.querySelector('.who').textContent,
            }))"""
        )
        by_title = {pill["title"]: pill["who"] for pill in pills}
        assert marks["longest_road_holder"] in by_title["Longest Road"], by_title
        assert marks["largest_army_holder"] in by_title["Largest Army"], by_title

    def test_no_console_errors(self, light_table):
        player, _ = light_table
        assert player.noisy_errors() == [], player.noisy_errors()


class TestBothThemesArePainted:
    def test_light_theme_shot(self, light_table):
        player, _ = light_table
        player.shot("scoreboard-2p-awards-light")

    def test_dark_theme_shot(self, dark_table):
        player, _ = dark_table
        player.shot("scoreboard-2p-awards-dark")
