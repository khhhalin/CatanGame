"""Taking somebody's seat has to be asked for, and the question never appeared.

`join(takeover = false)` was registered as the click listener itself, so the
browser handed it the MouseEvent as `takeover`. A MouseEvent is truthy, so
every Join click claimed the seat outright: the server never answered
NAME_TAKEN, and `handleNameTaken` — with its "Take over {name}'s seat?" prompt
— could not run at all. The Enter key beside it called `join()` with no
argument and behaved correctly the whole time, which is what hid it.

Harmless while two sockets on one name both worked. Since every game action is
bound to the socket that holds the seat, the older tab now goes dead instead:
its clicks are refused until it reloads. A player is entitled to be asked
before that happens to somebody.

Run: pytest tests/test_browser_join_takeover.py -m slow -v
"""

import pytest
from browser_harness import Player, launch_browser, start_server, stop_server
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

SEAT = "Alice"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("join-takeover"))
    yield url
    stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = launch_browser(play)
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def holder(browser, server):
    """The tab that got there first and owns the seat."""
    player = Player(browser, server, SEAT)
    player.join()
    return player


@pytest.fixture(scope="module")
def latecomer(browser, server):
    """A second tab, typing the same name a player is already using."""
    return Player(browser, server, SEAT)


def click_join_as(player, name, answer):
    """Press Join and answer whatever the page asks, returning the question.

    Playwright dismisses an unhandled dialog, which would make "no prompt at
    all" and "prompt declined" the same observation — the exact confusion this
    suite exists to tell apart.
    """
    asked = []

    def respond(dialog):
        asked.append(dialog.message)
        dialog.accept() if answer else dialog.dismiss()

    player.page.once("dialog", respond)
    player.page.check("#role-player")
    player.page.fill("#username", name)
    player.page.click("#join-btn")
    player.page.wait_for_timeout(1200)
    return asked[0] if asked else None


class TestTakingASeatIsAsked:
    def test_the_first_tab_holds_the_seat(self, holder):
        assert holder.page.is_visible("#user-screen")

    def test_joining_under_a_name_in_use_asks_before_taking_it(self, holder, latecomer):
        question = click_join_as(latecomer, SEAT, answer=False)
        assert question is not None, (
            "Join took the seat without asking - the confirmation is unreachable"
        )
        assert SEAT in question and "take over" in question.lower(), (
            f"the prompt reads {question!r}"
        )

    def test_declining_leaves_the_seat_where_it_was(self, holder, latecomer):
        """The decline path is the whole point: refusing must cost nothing."""
        assert latecomer.page.is_visible("#join-screen"), (
            "the tab that declined was let in anyway"
        )
        assert latecomer.page.input_value("#username") == "", (
            "the declined name was left in the box, one click from taking the seat"
        )
        assert not any("took over" in notice for notice in holder.notices()), (
            f"the seat was taken despite the refusal: {holder.notices()}"
        )

    def test_accepting_really_does_hand_the_seat_over(self, holder, latecomer):
        """The confirmation has to be a question, not a formality."""
        question = click_join_as(latecomer, SEAT, answer=True)
        assert question is not None, "the second attempt was not asked about either"

        latecomer.page.wait_for_selector("#user-screen:not(.hidden)", timeout=8000)
        holder.page.wait_for_function(
            "() => [...document.querySelectorAll('#notice-region *')]"
            "        .some(el => el.textContent.includes('took over'))",
            timeout=8000,
        )


class TestThisBrowserRemembersItsName:
    def test_a_reload_does_not_ask_the_player_to_retype_their_name(self, latecomer):
        """A player recovering mid-game met an empty box and had to remember
        exactly how they had spelled it."""
        latecomer.page.reload(wait_until="networkidle")
        assert latecomer.page.input_value("#username") == SEAT
