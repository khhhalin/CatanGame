"""The command bar, in a real browser.

Everything asserted here is invisible to the unit suite: the server is
perfectly correct whether or not typing "/" raises a list, whether or not
Enter runs the highlighted row, and whether or not an ordinary message
containing a slash is quietly eaten as a command. That last one is the
regression this suite exists for — chat is the thing players notice first when
it breaks, and it now shares its input with the commands.

Run: pytest tests/test_browser_commands.py -m slow -v
"""

import os

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
    wait_for_rule,
)

pytestmark = pytest.mark.slow

# The full-screen size the layout is held to.
VIEWPORT = {"width": 1920, "height": 1080}

GAME_SEED = 20260804

SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "commands",
)


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


def set_rule(player, rule_id, value):
    """Tick one rule in the picker, as a host would."""
    player.page.evaluate(
        "id => { const el = document.getElementById(`rule-${id}`);"
        "        const group = el && el.closest('details');"
        "        if (group) { group.open = true; } }",
        rule_id,
    )
    control = player.page.locator(f"#rule-{rule_id}")
    control.scroll_into_view_if_needed()
    control.set_checked(value)
    wait_for_rule(player, rule_id, value)


def seat_two(browser, url, color_scheme=None):
    alice = Player(browser, url, "Alice", viewport=VIEWPORT, color_scheme=color_scheme)
    bob = Player(browser, url, "Bob", viewport=VIEWPORT, color_scheme=color_scheme)
    alice.join()
    bob.join()
    alice.page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    return alice, bob


def start_game(alice, others):
    alice.page.click("#start-game-btn")
    for player in (alice, *others):
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)


def type_command(player, text):
    """Type into the chat box the way a person does, character by character.

    `fill` sets the value in one write and fires one input event, which is not
    what filtering as you type looks like.
    """
    player.page.click("#chat-input")
    player.page.fill("#chat-input", "")
    player.page.type("#chat-input", text, delay=20)


def bar_is_open(player):
    return player.page.is_visible("#command-bar:not(.hidden)")


def listed_commands(player):
    return player.page.eval_on_selector_all(
        "#command-list .command-name", "els => els.map(e => e.textContent)"
    )


def private_lines(player):
    return player.page.eval_on_selector_all(
        "#log-entries .log-private", "els => els.map(e => e.textContent)"
    )


def log_texts(player):
    return player.page.eval_on_selector_all(
        "#log-entries .log-entry", "els => els.map(e => e.textContent)"
    )


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def table(browser, tmp_path_factory):
    """A started game with commands switched on, in the light theme."""
    proc, url = start_server(tmp_path_factory.mktemp("commands"), seed=GAME_SEED)
    alice, bob = seat_two(browser, url)
    set_rule(alice, "chat_commands", True)
    start_game(alice, [bob])
    yield alice, bob
    stop_server(proc)


class TestTheBarOpensAndFilters:
    def test_a_slash_raises_the_list(self, table):
        alice, _ = table
        assert not bar_is_open(alice), "the bar is not up before anybody types"

        type_command(alice, "/")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)

        assert "/help" in listed_commands(alice)
        assert alice.page.get_attribute("#chat-input", "aria-expanded") == "true"

    def test_the_list_is_the_server_s_catalogue(self, table):
        """Not a copy in the client: a command added server-side must appear."""
        alice, _ = table
        type_command(alice, "/")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)

        served = alice.page.evaluate(
            "() => window.__catanDebug.getCommands().commands.map(c => c.name)"
        )
        assert served, "the client never received a catalogue"
        assert listed_commands(alice) == served

    def test_typing_narrows_it_fuzzily(self, table):
        alice, _ = table
        type_command(alice, "/adr")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)

        shown = listed_commands(alice)
        assert shown == ["/add_resource"], f"fuzzy filter showed {shown}"

    def test_a_command_this_table_cannot_run_says_why(self, table):
        """/barbarians is listed with its reason rather than hidden: a bar that
        omits it teaches the player the command does not exist."""
        alice, _ = table
        type_command(alice, "/barb")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)

        summary = alice.page.inner_text("#command-list .command-item")
        assert "unavailable" in summary.lower()
        assert "Barbarian attacks" in summary

    def test_escape_puts_it_away(self, table):
        alice, _ = table
        type_command(alice, "/he")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)

        alice.page.keyboard.press("Escape")
        alice.page.wait_for_selector("#command-bar.hidden", state="attached", timeout=4000)

        assert not bar_is_open(alice)
        assert alice.page.get_attribute("#chat-input", "aria-expanded") == "false"
        assert alice.page.input_value("#chat-input") == "/he", "Escape closes, it does not erase"


class TestRunningACommand:
    def test_enter_runs_the_highlighted_command(self, table):
        alice, _ = table
        type_command(alice, "/whoa")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)
        alice.page.keyboard.press("ArrowDown")
        alice.page.keyboard.press("Enter")

        alice.page.wait_for_selector("#log-entries .log-private", timeout=6000)
        assert "Alice" in ' '.join(private_lines(alice))
        assert alice.page.input_value("#chat-input") == "", "the box is cleared"

    def test_the_reply_is_this_player_s_alone(self, table):
        alice, bob = table
        assert private_lines(bob) == [], "a /whoami reached the other tab"

    def test_a_command_with_arguments_is_completed_not_run_blind(self, table):
        """Running /add_resource with nothing typed can only earn a usage
        message, so the row fills the name in and waits."""
        alice, _ = table
        type_command(alice, "/add")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)
        alice.page.keyboard.press("ArrowDown")
        alice.page.keyboard.press("Enter")

        assert alice.page.input_value("#chat-input") == "/add_resource "
        assert not bar_is_open(alice)

    def test_a_command_that_changes_the_game_reaches_the_table_s_log(self, table):
        alice, bob = table
        held = (alice.me() or {}).get("resources", {}).get("wheat", 0)

        type_command(alice, "/add_resource wheat 2")
        alice.page.keyboard.press("Enter")

        bob.page.wait_for_function(
            "() => [...document.querySelectorAll('#log-entries .log-kind-command')]"
            "        .some(e => e.textContent.includes('added 2 wheat'))",
            timeout=6000,
        )
        alice.page.wait_for_function(
            "before => {"
            "  const me = window.__catanDebug.getBoard().players.find(p => p.is_you);"
            "  return (me.resources.wheat || 0) > before; }",
            arg=held, timeout=6000,
        )

    def test_the_arrow_keys_move_the_active_row(self, table):
        alice, _ = table
        type_command(alice, "/")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)

        alice.page.keyboard.press("ArrowDown")
        first = alice.page.get_attribute("#chat-input", "aria-activedescendant")
        alice.page.keyboard.press("ArrowDown")
        second = alice.page.get_attribute("#chat-input", "aria-activedescendant")

        assert first and second and first != second
        assert alice.page.get_attribute(f"#{second}", "aria-selected") == "true"
        assert alice.page.get_attribute(f"#{first}", "aria-selected") == "false"
        alice.page.keyboard.press("Escape")


class TestOrdinaryChatStillWorks:
    def test_a_plain_message_is_sent(self, table):
        alice, bob = table
        type_command(alice, "hello table")
        assert not bar_is_open(alice), "a message with no slash raises no list"
        alice.page.keyboard.press("Enter")

        bob.page.wait_for_function(
            "() => [...document.querySelectorAll('#log-entries .log-chat')]"
            "        .some(e => e.textContent.includes('hello table'))",
            timeout=6000,
        )

    def test_a_message_that_merely_contains_a_slash_is_chat(self, table):
        """The regression this suite exists for: one input, two jobs."""
        alice, bob = table
        type_command(alice, "back in 5 w/ coffee")
        assert not bar_is_open(alice)
        alice.page.keyboard.press("Enter")

        bob.page.wait_for_function(
            "() => [...document.querySelectorAll('#log-entries .log-chat')]"
            "        .some(e => e.textContent.includes('back in 5 w/ coffee'))",
            timeout=6000,
        )
        assert alice.page.input_value("#chat-input") == ""

    def test_the_send_button_still_sends(self, table):
        alice, bob = table
        type_command(alice, "pressing the button")
        alice.page.click("#chat-send-btn")

        bob.page.wait_for_function(
            "() => [...document.querySelectorAll('#log-entries .log-chat')]"
            "        .some(e => e.textContent.includes('pressing the button'))",
            timeout=6000,
        )

    def test_nothing_in_the_console_broke(self, table):
        alice, bob = table
        assert alice.noisy_errors() == []
        assert bob.noisy_errors() == []


class TestItLooksRight:
    def test_the_page_does_not_scroll_with_the_bar_open(self, table):
        """The bar floats over the log; a bar that pushed the input down would
        take the height out of the board."""
        alice, _ = table
        type_command(alice, "/")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)

        overflow = alice.page.evaluate(
            "() => ({"
            "  x: document.documentElement.scrollWidth > window.innerWidth,"
            "  y: document.documentElement.scrollHeight > window.innerHeight })"
        )
        assert overflow == {"x": False, "y": False}

    def test_the_bar_sits_over_the_log_and_above_the_input(self, table):
        alice, _ = table
        type_command(alice, "/")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)

        bar = alice.page.evaluate(
            "() => document.getElementById('command-bar').getBoundingClientRect().bottom"
        )
        input_top = alice.page.evaluate(
            "() => document.getElementById('chat-input').getBoundingClientRect().top"
        )
        assert bar <= input_top + 1, "the list covers the box being typed in"

    def test_the_light_theme_is_worth_looking_at(self, table):
        alice, _ = table
        type_command(alice, "/")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)
        alice.page.keyboard.press("ArrowDown")
        shot(alice, "command-bar-light")

        type_command(alice, "/ad")
        alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)
        alice.page.keyboard.press("ArrowDown")
        shot(alice, "command-bar-filtered-light")


class TestTheDarkTheme:
    def test_the_dark_theme_is_worth_looking_at(self, browser, tmp_path_factory):
        proc, url = start_server(tmp_path_factory.mktemp("commands-dark"), seed=GAME_SEED)
        try:
            alice, bob = seat_two(browser, url, color_scheme="dark")
            set_rule(alice, "chat_commands", True)
            start_game(alice, [bob])

            type_command(alice, "/")
            alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)
            alice.page.keyboard.press("ArrowDown")
            shot(alice, "command-bar-dark")

            type_command(alice, "/ad")
            alice.page.wait_for_selector("#command-bar:not(.hidden)", timeout=4000)
            alice.page.keyboard.press("ArrowDown")
            shot(alice, "command-bar-filtered-dark")

            # And a reply in the log, which is the other new surface.
            type_command(alice, "/rules")
            alice.page.keyboard.press("Enter")
            alice.page.wait_for_selector("#log-entries .log-private", timeout=6000)
            assert any("Chat commands" in line for line in private_lines(alice)), (
                f"/rules did not name the rule this table changed: {log_texts(alice)}"
            )
            shot(alice, "command-result-dark")
            assert alice.noisy_errors() == []
        finally:
            stop_server(proc)
