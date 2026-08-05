"""The award panel, read the way a player reads it.

Two things it got wrong, both found by playing rather than by any assertion in
the suite — the server state was right in each case, which is why nothing here
caught them:

  - a seafaring table plays for the Longest Trade Route, not the Longest Road,
    and the route is roads *and* ships. A screenshot of a route that was mostly
    ships read "Alice · 10 roads";
  - the two thresholds were literals in the client. A table that set the
    Longest Road minimum to 2 was still told "needs 5".

Both tables are arranged with the real engine and written to the save file the
server restores on boot, as `test_browser_knights.py` does: the panel is what is
under test, not the play that reaches it.

Run: pytest tests/test_browser_awards.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import Player, browser_session, start_server, stop_server
from game import persistence
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

TABLE = ["Alice", "Bob"]


def _chain(game, player_name, start, length, kind):
    """Lay `length` of the player's pieces in an unbranched line from `start`.

    Roads go on the inland sides and ships on the ones a ship may lie on, which
    is the engine's own mask rather than a second answer to it here.
    """
    player = game.get_player(player_name)
    at = start
    laid = []
    for _ in range(length):
        edge_key = next(
            key for key in game.vertices[at].neighbors["edges"]
            if key not in laid
            and not game.edges[key].road and not game.edges[key].ship
            and (not game.is_sea_edge(key) if kind == "road" else game.is_sea_edge(key))
        )
        edge = game.edges[edge_key]
        if kind == "road":
            edge.road = {"player": player_name}
            player.roads.append(edge_key)
        else:
            edge.ship = {"player": player_name, "built_turn": 0}
            player.ships.append(edge_key)
        laid.append(edge_key)
        at = next(v for v in edge.neighbors["vertices"] if v != at)
    return laid


def a_route_of_roads_and_ships(game):
    """A settlement on the coast with roads inland and ships out to sea.

    Roads and ships only chain into one route where their owner has a building
    at the intersection they meet on (expansions.md 81), so the settlement is
    what makes this a single route rather than two.
    """
    actor = "Alice"
    home = next(
        key for key, vertex in sorted(game.vertices.items())
        if vertex.neighbors["hexes"]
        and sum(1 for e in vertex.neighbors["edges"] if not game.is_sea_edge(e)) >= 1
        and sum(1 for e in vertex.neighbors["edges"] if game.is_sea_edge(e)) >= 1
    )
    game.vertices[home].building = {"type": "settlement", "player": actor}
    game.get_player(actor).settlements.append(home)

    roads = _chain(game, actor, home, 2, "road")
    ships = _chain(game, actor, home, 1, "ship")
    game.update_longest_road()
    return {"holder": actor, "roads": len(roads), "ships": len(ships)}


def nobody_near_either_award(game):
    """An empty board on a table that lowered both minimums to 2."""
    return {}


def build_game(rules, build):
    game = Game(list(TABLE), [], rng=random.Random(7), rules=rules)
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    return game, build(game)


@contextmanager
def table(browser, data_dir, rules, build):
    game, marks = build_game(rules, build)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    try:
        player = Player(browser, url, TABLE[0], viewport=VIEWPORT)
        # Not Player.join(): a join into a running game is answered with the
        # game screen rather than the lobby.
        player.page.check("#role-player")
        player.page.fill("#username", TABLE[0])
        player.page.click("#join-btn")
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        player.page.wait_for_selector("#award-summary .award", timeout=10000)
        yield player, marks
    finally:
        stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.fixture
def seafaring_table(browser, tmp_path):
    rules = {
        "ships": True,
        "longest_trade_route": True,
        "largest_army_card": True,
        # Short enough that three segments take the card: a browser test that
        # has to lay five of each piece is testing the fixture, not the panel.
        "longest_road_minimum": 2,
    }
    with table(browser, tmp_path, rules, a_route_of_roads_and_ships) as live:
        yield live


@pytest.fixture
def short_minimums_table(browser, tmp_path):
    rules = {
        "longest_road_card": True,
        "largest_army_card": True,
        "longest_road_minimum": 2,
        "largest_army_minimum": 2,
    }
    with table(browser, tmp_path, rules, nobody_near_either_award) as live:
        yield live


def award_text(player):
    return player.page.inner_text("#award-summary")


class TestTheRouteIsNamedForTheRuleBeingPlayed:
    def test_a_trade_route_table_does_not_say_longest_road(self, seafaring_table):
        """Reported from play: the panel said "Longest Road" on a seafaring
        table, where the card being competed for is the Longest Trade Route
        (expansions.md 77)."""
        player, _ = seafaring_table

        text = award_text(player)
        assert "Longest Trade Route" in text
        assert "Longest Road" not in text

    def test_the_route_is_not_counted_as_roads(self, seafaring_table):
        """Reported from play: "Alice · 10 roads" for a route that was mostly
        ships. Both count toward it (expansions.md 79), and the rulebook calls
        them segments (84)."""
        player, marks = seafaring_table
        length = marks["roads"] + marks["ships"]

        text = award_text(player)
        assert f"Alice · {length} segments" in text
        assert "roads" not in text, (
            f"a route of {marks['roads']} roads and {marks['ships']} ships was "
            f"reported in roads: {text!r}"
        )


class TestTheThresholdsComeFromTheTable:
    def test_the_minimums_are_the_ones_the_engine_uses(self, short_minimums_table):
        """Reported from play: a table that lowered both minimums to 2 was told
        "needs 5" and "needs 3" — the client held its own copy of the base
        game's numbers."""
        player, _ = short_minimums_table

        text = award_text(player)
        assert "needs 2" in text
        assert "needs 5" not in text
        assert "needs 3" not in text

    def test_no_console_errors(self, short_minimums_table):
        player, _ = short_minimums_table
        assert player.noisy_errors() == [], player.noisy_errors()
