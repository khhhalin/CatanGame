"""What a human tester found by playing, driven back through a real browser.

Four complaints, each one a thing a player could see and could not do:

  - a hand of cloth, coin and paper could not be discarded on a 7. The engine
    has taken commodities in a discard for as long as they have counted toward
    the hand limit; the dialog had five inputs, so a player over the limit on
    commodities alone could not comply at all and the table stopped;
  - Buy Card was offered on a table playing progress cards and then refused by
    the server, which is the "click, then be told" pattern every other action
    in this client has already stopped doing;
  - every player's state should be readable at once. The scoreboard row was a
    run of abbreviations and left out the pieces entirely;
  - there is now a sound on every placement, so there has to be a way to turn
    it off, and it has to survive a reload.

The hands here are arranged with the real engine and written to the save file
the server restores on boot, the way `test_browser_knights.py` does: a discard
of commodities cannot be reached by rolling, and a browser test that waits for
the right 7 is not a gate.

Run: pytest tests/test_browser_tester_round.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    build_settlement,
    legal_setup_vertices,
    next_frame,
    start_server,
    stop_server,
    wait_for_rules,
)
from game import persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(REPO, "test-artifacts", "ui", "tester-round")

TABLE = ["Alice", "Bob"]

GAME_SEED = 20260804

EMPTY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0}

# Every expansion at once, which is the worst case the rail has to survive:
# the most folds, the most awards and four scoreboard rows. Built by merging
# the two presets rather than by copying a rule list into here — a list copied
# from the catalogue passes even when the catalogue has moved on.
EVERY_EXPANSION = {
    **rules_module.preset_rules("cities_and_knights"),
    **{
        rule: value
        for rule, value in rules_module.preset_rules("seafarers").items()
        # The seafaring preset turns the C&K rules back off; only what it adds
        # is wanted here.
        if value is not False
    },
}

SET_RULES = """
async rules => {
    const socket = (await import('/static/js/socket.js')).socket;
    socket.emit('set_rules', { rules });
}
"""


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- Arranging a hand ------------------------------------------------------


def build_game(build):
    """A started Cities & Knights game, mid-turn, with `build` applied."""
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
def table(browser, data_dir, build, color_scheme=None):
    """A running server restored from `build`, with both players connected.

    `color_scheme` is the only way to see the dark theme: the app has no theme
    control, both themes come from prefers-color-scheme.
    """
    game, marks = build_game(build)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    tabs = {}
    try:
        for name in TABLE:
            player = Player(browser, url, name, viewport=VIEWPORT,
                            color_scheme=color_scheme)
            # Not Player.join(): that waits for the lobby, and a join into a
            # running game is answered with the game screen instead.
            player.page.check("#role-player")
            player.page.fill("#username", name)
            player.page.click("#join-btn")
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
            tabs[name] = player
        yield tabs[game.current_player_name()], marks
    finally:
        stop_server(proc)


def a_hand_of_commodities_owing_a_discard(game):
    """Six commodity cards, no resources at all, and three owed to the bank.

    The exact shape of the tester's report: on a 7 the hand limit counts
    commodities, so this hand is over the limit and every card that could pay
    the debt is a commodity.
    """
    actor = game.current_player_name()
    player = game.get_player(actor)
    player.resources.update(EMPTY_HAND)
    player.commodities.update({"cloth": 2, "coin": 2, "paper": 2})
    game.players_needing_discard = {actor: 3}
    return {"actor": actor}


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def a_hand_that_could_buy_a_development_card(game):
    """Enough wheat, sheep and ore to buy one, on a table that has no deck.

    Affordability is the only thing the Buy Card button ever checked, so the
    hand has to cover the cost or the button would be greyed out for the wrong
    reason and the test would pass over the bug.
    """
    actor = game.current_player_name()
    player = game.get_player(actor)
    player.resources.update(EMPTY_HAND)
    player.resources.update({"wheat": 2, "sheep": 2, "ore": 2})
    return {"actor": actor}


@pytest.fixture
def owes_a_commodity_discard(browser, tmp_path):
    with table(browser, tmp_path, a_hand_of_commodities_owing_a_discard) as live:
        yield live


@pytest.fixture
def progress_card_table(browser, tmp_path):
    with table(browser, tmp_path, a_hand_that_could_buy_a_development_card) as live:
        yield live


# Both themes are a standing requirement, and the only way to see the dark one
# is a context that asks for it.
@pytest.fixture
def owes_a_commodity_discard_dark(browser, tmp_path):
    with table(browser, tmp_path, a_hand_of_commodities_owing_a_discard,
               color_scheme="dark") as live:
        yield live


@pytest.fixture
def progress_card_table_dark(browser, tmp_path):
    with table(browser, tmp_path, a_hand_that_could_buy_a_development_card,
               color_scheme="dark") as live:
        yield live


# --- 1. Discarding commodities --------------------------------------------


class TestACommodityHandCanPayADiscard:
    """The tester's report: "a player over the limit on cloth, coin or paper
    cannot comply at all"."""

    def test_the_dialog_opens_with_an_input_for_every_card_the_limit_counts(
        self, owes_a_commodity_discard
    ):
        player, _ = owes_a_commodity_discard
        player.page.wait_for_selector("#discard-modal.show", timeout=8000)
        for card in ("wood", "brick", "sheep", "wheat", "ore",
                     "cloth", "coin", "paper"):
            assert player.page.is_visible(f"#discard-{card}"), (
                f"the discard dialog has no input for {card}"
            )
        shot(player, "discard-commodities-light")

    def test_a_discard_of_commodities_is_accepted(self, owes_a_commodity_discard):
        """Before the fix there was nothing to type into: the hand was six
        commodities, the dialog offered five resources, and no entry summed to
        the three cards owed."""
        player, marks = owes_a_commodity_discard
        player.page.wait_for_selector("#discard-modal.show", timeout=8000)

        player.page.fill("#discard-cloth", "2")
        player.page.fill("#discard-paper", "1")
        player.page.click("#submit-discard-btn")

        player.page.wait_for_function(
            "() => !document.getElementById('discard-modal').classList.contains('show')",
            timeout=8000,
        )
        player.page.wait_for_function(
            "() => window.__catanDebug.getBoard()"
            "        .players.find(p => p.is_you).commodity_count === 3",
            timeout=8000,
        )
        held = player.me()["commodities"]
        assert held == {"cloth": 0, "coin": 2, "paper": 1}, held

    def test_the_total_counts_commodities_too(self, owes_a_commodity_discard):
        """A discard that is short is refused by the client with the count it
        wants, and nothing is sent."""
        player, _ = owes_a_commodity_discard
        player.page.wait_for_selector("#discard-modal.show", timeout=8000)

        player.page.fill("#discard-cloth", "1")
        player.page.click("#submit-discard-btn")
        # The refusal is the client's own, so wait for what it says rather than
        # for a guessed number of milliseconds.
        player.page.wait_for_function(
            "() => [...document.querySelectorAll('#notice-region *')]"
            "        .some(el => el.textContent.includes('exactly 3'))",
            timeout=5000,
        )

        assert player.page.is_visible("#discard-modal.show"), (
            "a short discard closed the dialog"
        )
        assert any("exactly 3" in text for text in player.notices()), player.notices()

    def test_the_dialog_reads_in_the_dark_theme_too(self, owes_a_commodity_discard_dark):
        """Both themes, every time: seven contrast failures have been fixed in
        this client and the way each one was found was by looking."""
        player, _ = owes_a_commodity_discard_dark
        player.page.wait_for_selector("#discard-modal.show", timeout=8000)
        assert player.page.is_visible("#discard-cloth")
        shot(player, "discard-commodities-dark")

    def test_no_console_errors(self, owes_a_commodity_discard):
        player, _ = owes_a_commodity_discard
        assert player.noisy_errors() == [], player.noisy_errors()


# --- 2. Buying a card a progress-card table has no deck for ---------------


class TestBuyCardIsNotOfferedWhereItIsRefused:
    """The server answers `buy_dev_card` with DEV_CARDS_NOT_IN_PLAY whenever
    progress cards are on - they replace the development deck outright. The
    button was gated on affordability alone, so a player with the cost in hand
    could click it and be told no."""

    def test_the_hand_really_could_pay_for_one(self, progress_card_table):
        """Otherwise the button would be greyed for want of ore and this suite
        would prove nothing."""
        player, _ = progress_card_table
        held = player.me()["resources"]
        assert held["wheat"] >= 1 and held["sheep"] >= 1 and held["ore"] >= 1, held
        assert player.board()["rules"]["progress_cards"] is True

    def test_buy_card_is_greyed_out_and_says_the_table_has_no_deck(
        self, progress_card_table
    ):
        player, _ = progress_card_table
        state = player.page.evaluate(
            "() => { const b = document.getElementById('buy-dev-card-btn');"
            "        return { off: b.disabled, why: b.title }; }"
        )
        assert state["off"], "Buy Card is live on a table that plays progress cards"
        assert "progress cards" in state["why"], (
            f"Buy Card is disabled but does not say why: {state['why']!r}"
        )

    def test_the_progress_hand_replaces_the_development_fold(self, progress_card_table):
        """A Development Cards fold on such a table offers a deck that does not
        exist; the progress hand is what the player actually holds."""
        player, _ = progress_card_table
        assert not player.page.is_visible("#dev-cards-panel"), (
            "the development card fold is still offered alongside progress cards"
        )
        assert player.page.is_visible("#progress-cards-chip"), (
            "the progress card fold is not on screen"
        )
        player.page.click("#progress-cards-chip")
        player.page.wait_for_selector("#progress-cards-popover:not(.hidden)", timeout=3000)
        shot(player, "progress-cards-panel-light")
        player.page.click("#progress-cards-chip")

    def test_the_progress_panel_reads_in_the_dark_theme_too(
        self, progress_card_table_dark
    ):
        player, _ = progress_card_table_dark
        player.page.click("#progress-cards-chip")
        player.page.wait_for_selector("#progress-cards-popover:not(.hidden)", timeout=3000)
        shot(player, "progress-cards-panel-dark")

    def test_no_console_errors(self, progress_card_table):
        player, _ = progress_card_table
        assert player.noisy_errors() == [], player.noisy_errors()


# --- 3. Every player's state, readable at once ----------------------------
#
# The tester: "ui zrobic czytelniejsze przynajmniej graczy wszystkich stan
# wyswietlac naraz". The row was `Rd 0 · Kn 0 · 🃏0 · 🏺0 com · 📜0` - a run of
# abbreviations that named neither the pieces on the board nor what any of it
# meant.
#
# The measurement is the layout suite's, because this is the change most likely
# to push the rail off the bottom of the screen: nothing may scroll or clip at
# 1920x1080 with four players and every expansion on.

_OVERFLOWING = """
() => {
    const allowed = new Set(['log-entries']);
    const out = [];
    const describe = (el) => el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}.${el.className}`;
    for (const el of document.querySelectorAll('#game-screen *, .table-aside *')) {
        if (allowed.has(el.id) || el.closest('#log-entries')) {
            continue;
        }
        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden'
            || style.position === 'fixed') {
            continue;
        }
        if (el.scrollHeight > el.clientHeight + 1 && el.clientHeight > 0) {
            out.push({ el: describe(el), axis: 'y',
                       content: el.scrollHeight, box: el.clientHeight });
        }
        if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) {
            out.push({ el: describe(el), axis: 'x',
                       content: el.scrollWidth, box: el.clientWidth });
        }
    }
    return out;
}
"""

_OFF_SCREEN = """
() => {
    const out = [];
    const describe = (el) => el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}.${el.className}`;
    for (const el of document.querySelectorAll(
            '#game-screen .panel, #game-screen .fold, .table-aside .panel')) {
        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') {
            continue;
        }
        const box = el.getBoundingClientRect();
        if (box.width === 0 && box.height === 0) {
            continue;
        }
        if (box.bottom > window.innerHeight + 1 || box.top < -1
            || box.right > window.innerWidth + 1 || box.left < -1) {
            out.push({ el: describe(el),
                       box: [box.left, box.top, box.right, box.bottom] });
        }
    }
    return out;
}
"""

# One row per player, as a reader sees it: the name, the score, and every chip
# with the label it carries for a screen reader.
_SCOREBOARD = """
() => Array.from(document.querySelectorAll('#game-players li')).map(row => ({
    name: row.querySelector('.score-name').textContent,
    points: row.querySelector('.score-points').textContent,
    badges: Array.from(row.querySelectorAll('.score-badge'))
        .map(b => b.getAttribute('aria-label')),
    chips: Array.from(row.querySelectorAll('.score-chip')).map(chip => ({
        text: chip.textContent,
        label: chip.getAttribute('aria-label'),
    })),
}))
"""


def place_setup_round(players):
    """Drive the whole setup phase, so the scoreboard has pieces to report."""
    for _ in range(len(players) * 2 * 2 + 4):
        board = players[0].board()
        if board["game_phase"] != "setup":
            return
        actor = next(p for p in players if p.name == board["current_player"])
        if board.get("setup_action") == "road":
            vertex = next(
                key for key, vertex_data in board["vertices"].items()
                if (vertex_data.get("building") or {}).get("player") == actor.name
                and not any(
                    (board["edges"][edge].get("road") or {}).get("player") == actor.name
                    for edge in vertex_data["neighbors"]["edges"]
                )
            )
            # With ships on, the sides leaving a coastal settlement include sea
            # edges, where a road may never go.
            build_road(actor, [
                edge for edge in board["vertices"][vertex]["neighbors"]["edges"]
                if not board["edges"][edge]["sea"]
            ])
        else:
            # Only intersections a road can leave: with ships on, an
            # intersection touching one land hex has nothing but sea sides, and
            # the next half of setup asks for a road.
            build_settlement(actor, [
                vertex for vertex in legal_setup_vertices(board)
                if any(not board["edges"][edge]["sea"]
                       for edge in board["vertices"][vertex]["neighbors"]["edges"])
            ])


@pytest.fixture(scope="module")
def crowded_table(browser, tmp_path_factory):
    """Four players, every expansion on, past setup: the worst case for the rail."""
    proc, url = start_server(tmp_path_factory.mktemp("tester-crowded"), seed=GAME_SEED)
    # Dave plays in the dark theme: both themes have to be looked at, and a
    # fourth server for one screenshot is a minute of the suite for nothing.
    players = [
        Player(browser, url, name, viewport=VIEWPORT, yolo=True,
               color_scheme="dark" if name == "Dave" else None)
        for name in ("Alice", "Bob", "Carol", "Dave")
    ]
    for player in players:
        player.join()
    players[0].page.evaluate(SET_RULES, EVERY_EXPANSION)
    wait_for_rules(players[0], EVERY_EXPANSION)
    players[0].page.wait_for_selector("#start-game-btn:not(.hidden)", timeout=8000)
    players[0].page.click("#start-game-btn")
    for player in players:
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    place_setup_round(players)
    yield players
    stop_server(proc)


class TestTheWholeTableIsReadableAtAGlance:
    def test_every_expansion_really_is_on(self, crowded_table):
        """Asserted against the running game rather than against the dict that
        was sent: a rule set the server rejected would leave a base game here
        and every assertion below would be measuring the easy case."""
        board = crowded_table[0].board()
        for rule in ("commodities", "knights", "barbarians", "city_walls",
                     "progress_cards", "ships", "island_victory_points"):
            assert board["rules"][rule] is True, f"{rule} is off"
        assert len(board["players"]) == 4

    def test_each_row_states_points_cards_pieces_and_knights(self, crowded_table):
        """The tester's ask, one item at a time. Every one of these is public in
        the payload and none of it was on the scoreboard."""
        rows = crowded_table[0].page.evaluate(_SCOREBOARD)
        assert len(rows) == 4, rows
        for row in rows:
            assert "pts" in row["points"], row
            labels = " ".join(chip["label"] for chip in row["chips"])
            for subject in ("resource cards", "settlement", "cities", "roads",
                            "knights", "ships", "commodit"):
                assert subject in labels, (
                    f"{row['name']} says nothing about {subject}: {labels}"
                )

    def test_the_numbers_are_the_ones_the_server_sent(self, crowded_table):
        """A scoreboard that shows plausible numbers of its own is worse than
        none, so each row is checked against that player's payload entry."""
        player = crowded_table[0]
        rows = {row["name"].split(" ")[0]: row for row in player.page.evaluate(_SCOREBOARD)}
        for entry in player.board()["players"]:
            row = rows[entry["name"]]
            chips = {chip["label"]: chip["text"] for chip in row["chips"]}
            settlements = next(
                text for label, text in chips.items() if "settlement" in label
            )
            assert str(len(entry["settlements"])) in settlements, (
                f"{entry['name']} has {len(entry['settlements'])} settlements, "
                f"the row says {settlements!r}"
            )
            cards = next(text for label, text in chips.items() if "resource cards" in label)
            assert str(entry["resource_count"]) in cards, (
                f"{entry['name']} holds {entry['resource_count']} cards, "
                f"the row says {cards!r}"
            )

    def test_an_opponents_hand_is_a_count_and_never_its_contents(self, crowded_table):
        """Hidden information stays hidden: the payload sends no per-type hand
        for anyone but the viewer, so the row cannot show one."""
        player = crowded_table[0]
        for entry in player.board()["players"]:
            if entry["is_you"]:
                continue
            assert entry["resources"] is None, entry["name"]
            assert entry["commodities"] is None, entry["name"]
            assert entry["dev_cards"] is None, entry["name"]

    def test_who_holds_each_award_is_on_the_row_that_holds_it(self, crowded_table):
        """A badge beside the name, so "who has Longest Road" is answered
        without reading the award panel underneath."""
        player = crowded_table[0]
        # Arranged on the client's own copy: the awards are won over a whole
        # game, and this is a question about what the scoreboard draws for a
        # given payload.
        player.page.evaluate(
            """async name => {
                const board = window.__catanDebug.getBoard();
                board.longest_road_holder = name;
                board.largest_army_holder = name;
                const panels = await import('/static/js/panels.js');
                panels.renderGameSidebar({ players: board.players });
            }""",
            "Carol",
        )
        rows = {row["name"].split(" ")[0]: row for row in player.page.evaluate(_SCOREBOARD)}
        held = " ".join(rows["Carol"]["badges"])
        assert "Longest" in held or "Trade Route" in held, held
        assert "Largest Army" in held, held
        for name in ("Alice", "Bob", "Dave"):
            assert rows[name]["badges"] == [], f"{name} wears an award they do not hold"

    def test_nothing_scrolls_and_nothing_is_clipped(self, crowded_table):
        """The standing requirement: 1920x1080, four players, every expansion."""
        for player in crowded_table:
            overflowing = player.page.evaluate(_OVERFLOWING)
            assert overflowing == [], f"{player.name}: these boxes clip: {overflowing}"
            off_screen = player.page.evaluate(_OFF_SCREEN)
            assert off_screen == [], f"{player.name}: off the screen: {off_screen}"
        shot(crowded_table[0], "scoreboard-4p-every-expansion-light")
        shot(crowded_table[3], "scoreboard-4p-every-expansion-dark")

    def test_no_console_errors(self, crowded_table):
        for player in crowded_table:
            assert player.noisy_errors() == [], f"{player.name}: {player.noisy_errors()}"


# --- 4. A sound on every placement, and a way to turn it off ---------------
#
# The cues are synthesised with the Web Audio API - no audio files were added -
# so "was a sound made" is answerable by counting the oscillators the page
# started. Patched on the prototype rather than on the context, because the
# context is built lazily on the first cue and there is nothing to patch before
# then.

COUNT_OSCILLATORS = """
() => {
    if (window.__cues) {
        window.__cues.length = 0;
        return;
    }
    window.__cues = [];
    const start = OscillatorNode.prototype.start;
    OscillatorNode.prototype.start = function (...args) {
        window.__cues.push(this.type);
        return start.apply(this, args);
    };
    const play = HTMLMediaElement.prototype.play;
    window.__samples = [];
    HTMLMediaElement.prototype.play = function (...args) {
        window.__samples.push(this.src);
        return play.apply(this, args);
    };
}
"""

SET_MUTE = """
async wanted => {
    const toggle = document.getElementById('mute-toggle');
    if (toggle.checked !== wanted) {
        toggle.click();
    }
}
"""

PLAY_TURN_SOUND = """
async () => {
    const sound = await import('/static/js/sound.js');
    sound.playTurnSound();
}
"""


def a_hand_for_two_roads(game):
    """Roads to build from, and exactly four cards: two roads and no more."""
    actor = game.current_player_name()
    player = game.get_player(actor)
    home = next(
        key for key in sorted(game.vertices)
        if len(game.vertices[key].neighbors["hexes"]) == 3
        and all(game.hexes[h].type != "ocean"
                for h in game.vertices[key].neighbors["hexes"])
    )
    for edge_key in game.vertices[home].neighbors["edges"]:
        game.edges[edge_key].road = {"player": actor}
        player.roads.append(edge_key)
    player.resources.update(EMPTY_HAND)
    player.resources.update({"wood": 2, "brick": 2})
    return {"home": home}


@pytest.fixture
def road_builder(browser, tmp_path):
    with table(browser, tmp_path, a_hand_for_two_roads) as live:
        yield live


def build_one_road(player):
    board = player.board()
    build_road(player, [
        key for key, edge in sorted(board["edges"].items())
        if not edge.get("road") and not edge["sea"]
        and any(
            (board["edges"][other].get("road") or {}).get("player") == player.name
            for vertex in edge["neighbors"]["vertices"]
            for other in board["vertices"][vertex]["neighbors"]["edges"]
        )
    ])


class TestPlacementSoundsAndTheMuteToggle:
    def test_a_placement_makes_a_sound(self, road_builder):
        player, _ = road_builder
        player.page.evaluate(COUNT_OSCILLATORS)
        player.page.evaluate(SET_MUTE, False)

        build_one_road(player)
        player.page.wait_for_function("() => window.__cues.length > 0", timeout=5000)

        assert player.page.evaluate("() => window.__cues.length") > 0, (
            "a road went down and nothing was played"
        )

    def test_muting_silences_the_placement_cue(self, road_builder):
        """The point of the toggle: with a cue on every placement, a player who
        cannot turn it off has a real problem."""
        player, _ = road_builder
        player.page.evaluate(COUNT_OSCILLATORS)
        player.page.evaluate(SET_MUTE, True)

        build_one_road(player)
        # `build_one_road` already waited for the piece to appear, and the cue
        # is played by the same board update that put it there - so there is
        # nothing still in flight, only a frame left to draw.
        next_frame(player.page)

        assert player.page.evaluate("() => window.__cues") == [], (
            "muted, and a placement still played something"
        )

    def test_muting_silences_the_turn_sound_too(self, road_builder):
        """The sample that was here before the cues were, and the only sound
        the game had. Muting has to reach it as well."""
        player, _ = road_builder
        player.page.evaluate(COUNT_OSCILLATORS)

        player.page.evaluate(SET_MUTE, False)
        player.page.evaluate(PLAY_TURN_SOUND)
        assert player.page.evaluate("() => window.__samples.length") == 1

        player.page.evaluate(SET_MUTE, True)
        player.page.evaluate(PLAY_TURN_SOUND)
        assert player.page.evaluate("() => window.__samples.length") == 1, (
            "muted, and the turn sound still played"
        )

    def test_the_setting_survives_a_reload(self, road_builder):
        """Personal, per-browser, in localStorage - the `catan.yoloMode`
        pattern. A mute that has to be set again every reload is not one."""
        player, _ = road_builder
        player.page.evaluate(SET_MUTE, True)
        assert player.page.evaluate(
            "() => window.localStorage.getItem('catan.muted')"
        ) == "1"

        player.page.reload(wait_until="networkidle")
        player.page.check("#role-player")
        player.page.fill("#username", player.name)
        player.page.click("#join-btn")
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)

        assert player.page.is_checked("#mute-toggle"), (
            "the mute setting did not survive a reload"
        )

    def test_reduced_motion_starts_the_game_muted(self, browser, road_builder):
        """A browser asking for reduced motion is asking for less of
        everything, so it is taken as the *starting* setting - a stored
        preference still wins, which is why this tab is a fresh one."""
        player, _ = road_builder
        context = browser.new_context(viewport=VIEWPORT, reduced_motion="reduce")
        page = context.new_page()
        try:
            page.goto(player.page.url, wait_until="networkidle")
            page.check("#role-player")
            page.fill("#username", "Quiet")
            page.click("#join-btn")
            page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
            assert page.is_checked("#mute-toggle"), (
                "a browser asking for reduced motion was given sound anyway"
            )
        finally:
            context.close()

    def test_no_console_errors(self, road_builder):
        player, _ = road_builder
        assert player.noisy_errors() == [], player.noisy_errors()


# --- 5. Commodity trading, now that the engine takes it -------------------
#
# `propose_trade` runs both sides through `clean_card_counts`, and
# `TradeRules._move_cards` hands a commodity over exactly as it hands over a
# resource (`expansions.md` 329). Until that landed the modal deliberately did
# not offer commodities: a control that sends what the server rejects is worse
# than none.


def a_hand_of_cloth_and_a_partner_with_ore(game):
    """One player holding cloth, the other holding ore. Between them, a trade."""
    actor = game.current_player_name()
    other = next(name for name in TABLE if name != actor)
    giver = game.get_player(actor)
    giver.resources.update(EMPTY_HAND)
    giver.commodities.update({"cloth": 3, "coin": 0, "paper": 0})
    taker = game.get_player(other)
    taker.resources.update(EMPTY_HAND)
    taker.resources.update({"ore": 2})
    return {"actor": actor, "other": other}


@pytest.fixture
def commodity_traders(browser, tmp_path):
    with table(browser, tmp_path, a_hand_of_cloth_and_a_partner_with_ore) as live:
        yield live


class TestCommoditiesCanBeOffered:
    def test_the_dialog_offers_commodities_when_the_table_plays_them(
        self, commodity_traders
    ):
        player, _ = commodity_traders
        player.page.click("#tab-trade")
        player.page.click("#propose-trade-btn")
        player.page.wait_for_selector("#trade-modal.show", timeout=5000)
        for card in ("cloth", "coin", "paper"):
            assert player.page.is_visible(f"#give-{card}"), f"no give input for {card}"
            assert player.page.is_visible(f"#want-{card}"), f"no want input for {card}"

    def test_an_offer_of_cloth_reaches_the_table(self, commodity_traders):
        """The whole point: the server takes it, so the client may send it."""
        player, marks = commodity_traders
        player.page.click("#tab-trade")
        player.page.click("#propose-trade-btn")
        player.page.wait_for_selector("#trade-modal.show", timeout=5000)
        player.page.fill("#give-cloth", "2")
        player.page.fill("#want-ore", "1")
        player.page.click("#submit-trade-btn")

        player.page.wait_for_function(
            "() => (window.__catanDebug.getBoard().trades.active || []).length > 0",
            timeout=8000,
        )
        offer = player.board()["trades"]["active"][0]
        assert offer["offered_resources"] == {"cloth": 2}, offer
        assert offer["wanted_resources"] == {"ore": 1}, offer
        assert player.noisy_errors() == [], player.noisy_errors()
