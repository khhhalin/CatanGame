"""A trade offer's accept/deny state, seen by the whole table.

The v3.7.0 tester's report, driven back through real browsers:

  - "in trade offers deny nie jest responsywne" — a Deny gave no feedback;
  - "all players should see which players already agreed to a trade or denied
    it" — no screen showed another player's answer;
  - "if every not-proposing player denies a trade offer it should disappear".

Two browser assertions a player would make with their own eyes: after a
responder denies, the proposer's offer card shows that responder marked ✗; and
once every non-proposing player has denied, the offer card is gone for everyone.
Three tabs, because a persistent ✗ only exists while another responder is still
pending — with a single responder a deny clears the offer at once.

Run: pytest tests/test_browser_trade_responses.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
)
from game import persistence
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1400, "height": 1000}

TABLE = ["Alice", "Bob", "Carol"]

EMPTY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0}


def a_live_offer_the_table_can_answer(game):
    """The proposer holds one wood; both responders hold a brick to answer with.

    One-for-one, which no bank rate settles, so the offer stands on the table
    waiting for a response rather than paying out against the bank.
    """
    proposer = game.current_player_name()
    responders = [name for name in TABLE if name != proposer]
    game.get_player(proposer).resources.update({**EMPTY_HAND, "wood": 1})
    for name in responders:
        game.get_player(name).resources.update({**EMPTY_HAND, "brick": 1})
    return {"proposer": proposer, "responders": responders}


def build_game(build):
    """A started three-player base game, mid-turn, with `build` applied."""
    game = Game(list(TABLE), [], rng=random.Random(7))
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    return game, build(game)


@contextmanager
def three_tabs(browser, data_dir, build):
    """A running server restored from `build`, with all three players connected.

    Yields the marks plus a name->Player map, so a test can drive the proposer
    and each responder independently.
    """
    game, marks = build_game(build)
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
        yield marks, tabs
    finally:
        stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.fixture
def offer_table(browser, tmp_path):
    with three_tabs(browser, tmp_path, a_live_offer_the_table_can_answer) as live:
        yield live


def _propose_wood_for_brick(proposer):
    """Stage 1 wood, ask for 1 brick, and press Offer through the tray."""
    proposer.page.click('.hand-card[data-card="wood"]')
    proposer.page.click(".trade-add")
    proposer.page.click('.trade-pick[data-card="brick"]')
    proposer.page.click(".tray-action.is-offer")
    proposer.page.wait_for_function(
        "() => (window.__catanDebug.getBoard().trades.active || []).length > 0",
        timeout=8000,
    )


class TestEveryoneSeesAcceptDenyState:
    def test_a_deny_marks_the_responder_for_the_proposer_and_a_full_deny_clears_it(
        self, offer_table
    ):
        marks, tabs = offer_table
        proposer = tabs[marks["proposer"]]
        first, second = (tabs[name] for name in marks["responders"])

        _propose_wood_for_brick(proposer)

        # The first responder's Deny is on their incoming-offer popup. Before the
        # fix this click changed nothing anyone could see.
        first.page.wait_for_selector('.incoming-offers [data-action="decline"]', timeout=8000)
        first.page.click('.incoming-offers [data-action="decline"]')

        # The proposer's own offer card now shows that responder marked denied,
        # and the offer is still on the table because the second responder has
        # not answered.
        proposer.page.wait_for_function(
            """
            name => Array.from(document.querySelectorAll('.trade-response.is-denied'))
                .some(el => el.querySelector('.trade-response-name')?.textContent === name)
            """,
            arg=first.name,
            timeout=8000,
        )
        assert len(proposer.board()["trades"]["active"]) == 1, (
            "the offer vanished while a responder was still pending"
        )

        # The second responder denies too: no non-proposer could take it now, so
        # it comes off the table for everyone.
        second.page.wait_for_selector('.incoming-offers [data-action="decline"]', timeout=8000)
        second.page.click('.incoming-offers [data-action="decline"]')

        for tab in (proposer, first, second):
            tab.page.wait_for_function(
                "() => (window.__catanDebug.getBoard().trades.active || []).length === 0",
                timeout=8000,
            )
            assert tab.page.query_selector(".trade-offer") is None, (
                f"{tab.name} still sees an offer card every responder denied"
            )

        assert proposer.noisy_errors() == [], proposer.noisy_errors()
