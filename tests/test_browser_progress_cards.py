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
    click_edge,
    click_hex,
    click_vertex,
    first_clickable,
    legal_road_edges,
    next_frame,
    roll_dice,
    start_server,
    stop_server,
)
from game import cities_knights as ck_module
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


def build_game(build, rolled=True):
    """A started Cities & Knights game, mid-turn, with `build` applied.

    The dice are up by default: every card but the Alchemist is refused before
    the roll, and the client greys them out for the same reason. The Alchemist
    is the one card played before them, so it asks for `rolled=False`.
    """
    game = Game(
        list(TABLE), [], rng=random.Random(7),
        rules=rules_module.preset_rules("cities_and_knights"),
    )
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    if rolled:
        game.set_dice_rolled()
    return game, build(game)


@contextmanager
def table(browser, data_dir, build, rolled=True):
    """A running server restored from `build`, with both players connected."""
    game, marks = build_game(build, rolled=rolled)
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


def arm_pick(player, card_id):
    """Press "Pick on board", then get the popover out of the way.

    The popover is fixed and can lie over the board, so a target underneath it
    cannot be clicked at all.
    """
    press_play(player, card_id)
    close_progress_fold(player)
    assert selection(player)["progressPick"]["card"] == card_id, (
        f"pressing Pick on board did not arm the board for {card_id}"
    )


def selection(player):
    return player.page.evaluate("() => window.__catanDebug.getSelection()")


def aim_at(player, kind, candidates):
    """Click the first candidate a click would really land on.

    Computed *after* arming: arming adds `placement-mode`, which changes the
    canvas box and therefore the camera, so a point taken before the button was
    pressed lands on the neighbour.
    """
    key = first_clickable(player, kind, list(candidates))
    assert key, f"none of {list(candidates)} can be aimed at"
    if kind == "hex":
        click_hex(player, key)
    elif kind == "edge":
        click_edge(player, key)
    else:
        click_vertex(player, key)
    return key


def confirm_pick(player, expected_noun):
    """Press ✓, having checked it says which card it is about to play."""
    player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
    announced = player.page.inner_text("#placement-announce")
    assert expected_noun in announced, (
        f"the confirmation said {announced!r}, not {expected_noun!r}"
    )
    player.page.click("#placement-confirm-yes")


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


def a_merchant_card(game):
    """A settlement to stand the merchant beside, and the card to do it with."""
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    game.vertices[home].building = {"type": "settlement", "player": actor}
    game.get_player(actor).settlements.append(home)
    _hand(game, actor)
    _give_card(game, actor, "merchant")
    # Where the card may go, and one hex it may not: the merchant has to touch
    # a building of the player's own.
    mine = list(game.vertices[home].neighbors["hexes"])
    return {
        "home": home,
        "hexes": mine,
        "far": [
            key for key, hex_obj in sorted(game.hexes.items())
            if hex_obj.type != "ocean" and key not in mine
        ],
    }


@pytest.fixture
def merchant(browser, tmp_path):
    with table(browser, tmp_path, a_merchant_card) as live:
        yield live


def a_spy_and_a_hand_to_spy_on(game):
    """The Spy, and an opponent holding one card for it to take."""
    actor = game.current_player_name()
    victim = next(name for name in TABLE if name != actor)
    _hand(game, actor)
    _give_card(game, actor, "spy")
    _give_card(game, victim, "irrigation")
    return {"victim": victim, "taken": "irrigation"}


@pytest.fixture
def spy(browser, tmp_path):
    with table(browser, tmp_path, a_spy_and_a_hand_to_spy_on) as live:
        yield live


def an_alchemist_card(game):
    """The one card played before the dice, held with the dice still down."""
    actor = game.current_player_name()
    _hand(game, actor)
    _give_card(game, actor, "alchemist")
    return {}


@pytest.fixture
def alchemist(browser, tmp_path):
    with table(browser, tmp_path, an_alchemist_card, rolled=False) as live:
        yield live


def a_medicine_card(game):
    """A settlement to upgrade and the discounted price of a city."""
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    game.vertices[home].building = {"type": "settlement", "player": actor}
    game.get_player(actor).settlements.append(home)
    _hand(game, actor, ore=2, wheat=1)
    _give_card(game, actor, "medicine")
    return {"home": home}


@pytest.fixture
def medicine(browser, tmp_path):
    with table(browser, tmp_path, a_medicine_card) as live:
        yield live


def an_inventor_card(game):
    """The card, and the two number tokens it is allowed to swap."""
    actor = game.current_player_name()
    _hand(game, actor)
    _give_card(game, actor, "inventor")
    movable = [
        key for key, hex_obj in sorted(game.hexes.items())
        if hex_obj.number is not None and hex_obj.number not in (2, 6, 8, 12)
    ]
    assert len(movable) >= 2, "the board has too few movable number tokens"
    protected = [
        key for key, hex_obj in sorted(game.hexes.items())
        if hex_obj.number in (2, 6, 8, 12)
    ]
    return {"movable": movable, "protected": protected}


@pytest.fixture
def inventor(browser, tmp_path):
    with table(browser, tmp_path, an_inventor_card) as live:
        yield live


def a_smith_and_two_knights(game):
    """Two of the player's own basic knights, both promotable, and the Smith."""
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor)
    _give_card(game, actor, "smith")
    spots = list(game.vertices[home].neighbors["vertices"])[:2]
    for spot in spots:
        game.ck.knights_of(actor).append(ck_module.Knight(spot))
    return {"knights": spots}


@pytest.fixture
def smith(browser, tmp_path):
    with table(browser, tmp_path, a_smith_and_two_knights) as live:
        yield live


def a_bishop_card(game):
    """The Bishop, and somewhere to send the robber that is not where it is."""
    actor = game.current_player_name()
    _hand(game, actor)
    _give_card(game, actor, "bishop")
    return {
        "land": [
            key for key, hex_obj in sorted(game.hexes.items())
            if hex_obj.type != "ocean" and key != game.robber_hex
        ],
        "ocean": [
            key for key, hex_obj in sorted(game.hexes.items())
            if hex_obj.type == "ocean"
        ],
    }


@pytest.fixture
def bishop(browser, tmp_path):
    with table(browser, tmp_path, a_bishop_card) as live:
        yield live


def an_engineer_card(game):
    """A city with no wall, and the card that walls one for free."""
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    game.vertices[home].building = {"type": "city", "player": actor}
    game.get_player(actor).cities.append(home)
    _hand(game, actor)
    _give_card(game, actor, "engineer")
    return {"home": home}


@pytest.fixture
def engineer(browser, tmp_path):
    with table(browser, tmp_path, an_engineer_card) as live:
        yield live


def an_intrigue_card(game):
    """An opponent's knight standing next to one of the player's own roads."""
    actor = game.current_player_name()
    victim = next(name for name in TABLE if name != actor)
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor)
    _give_card(game, actor, "intrigue")
    spot = list(game.vertices[home].neighbors["vertices"])[0]
    game.ck.knights_of(victim).append(ck_module.Knight(spot))
    return {"knight": spot, "victim": victim}


@pytest.fixture
def intrigue(browser, tmp_path):
    with table(browser, tmp_path, an_intrigue_card) as live:
        yield live


def a_merchant_fleet_card(game):
    """The card that asks its own player which card type trades at 2:1."""
    actor = game.current_player_name()
    _hand(game, actor)
    _give_card(game, actor, "merchant_fleet")
    return {}


@pytest.fixture
def merchant_fleet(browser, tmp_path):
    with table(browser, tmp_path, a_merchant_fleet_card) as live:
        yield live


def a_diplomat_card(game):
    """Roads with a free end apiece, which is what a Diplomat may remove."""
    actor = game.current_player_name()
    home = _inland_vertices(game)[0]
    _roads_around(game, actor, home)
    _hand(game, actor)
    _give_card(game, actor, "diplomat")
    return {"roads": list(game.vertices[home].neighbors["edges"])}


@pytest.fixture
def diplomat(browser, tmp_path):
    with table(browser, tmp_path, a_diplomat_card) as live:
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


# --- The Merchant ----------------------------------------------------------
#
# Six of the 54 cards and the most common in the deck. Everything downstream of
# the pick already worked — the piece renders, the 2:1 rate applies, the point
# counts — and until now the only way to reach any of it was to edit a save.


class TestMerchant:
    def test_the_merchant_is_placed_by_picking_a_hex(self, merchant):
        """Arm, tap a hex beside the player's own settlement, ✓.

        The point and the 2:1 rate follow the piece, so both are asserted here:
        a merchant that lands somewhere and grants nothing is the same bug in a
        different place.
        """
        player, marks, _ = merchant

        arm_pick(player, "merchant")
        chosen = aim_at(player, "hex", marks["hexes"])
        confirm_pick(player, "Merchant")
        wait_for_card_spent(player, "merchant")

        board = player.board()
        assert board["merchant_hex"] == chosen
        assert board["merchant_holder"] == player.name
        # A victory point for as long as it is held, which is the half of the
        # card a player counts on.
        assert (player.me() or {}).get("victory_points", 0) >= 1
        next_frame(player.page)
        shot(player, "merchant-placed")

        assert selection(player)["mode"] is None, (
            "the board stayed armed after the merchant landed"
        )
        assert player.noisy_errors() == [], player.noisy_errors()

    def test_a_hex_away_from_your_buildings_is_shown_as_blocked(self, merchant):
        """The ghost has to say no before the round trip, not after it.

        `_progress_merchant` refuses a hex that touches none of the player's own
        buildings, and a ✓ that looks the same either way is a lie the player
        cannot argue with.
        """
        player, marks, _ = merchant

        arm_pick(player, "merchant")
        aim_at(player, "hex", marks["far"])
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
        assert "not allowed here" in player.page.inner_text("#placement-announce")

    def test_cancelling_leaves_the_card_in_hand(self, merchant):
        """Pressing Cancel is not a play: nothing was ever sent for it."""
        player, _marks, _tabs = merchant

        arm_pick(player, "merchant")
        press_play(player, "merchant")       # the same button, now Cancel
        assert selection(player)["progressPick"]["card"] is None
        assert selection(player)["mode"] is None
        assert hand_of(player) == ["merchant"], "cancelling ate the card"


# --- Cards aimed at another player -----------------------------------------
#
# Spy, Master Merchant and Deserter: seven cards between them, each needing a
# name and nothing else. Their follow-up questions were already built and
# rendering; only the way to name the player was missing.


class TestSpy:
    def test_the_spy_takes_a_card_out_of_the_named_player(self, spy):
        """Name the opponent inline, play, then answer the question it opens.

        The pending choice at the end is the proof the card really resolved:
        the options are the victim's actual hand, which only the server knows.
        """
        player, marks, tabs = spy
        victim = tabs[marks["victim"]]

        open_progress_fold(player)
        offered = player.page.eval_on_selector_all(
            ".progress-card select.progress-target option",
            "options => options.map(option => option.value)",
        )
        assert offered == [marks["victim"]], (
            f"the Spy offered {offered}, not just the other player at the table"
        )

        press_play(player, "spy")
        wait_for_card_spent(player, "spy")

        player.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)
        assert "Spy" in player.page.inner_text("#choice-prompt")
        assert marks["victim"] in player.page.inner_text("#choice-context")
        shot(player, "spy-choice")
        player.page.click("#choice-options .choice-option")

        player.page.wait_for_function(
            "card => window.__catanDebug.getBoard()"
            "  .cities_knights.progress_hand.includes(card)",
            arg=marks["taken"], timeout=8000,
        )
        victim.page.wait_for_function(
            "card => !window.__catanDebug.getBoard()"
            "  .cities_knights.progress_hand.includes(card)",
            arg=marks["taken"], timeout=8000,
        )
        assert player.noisy_errors() == [], player.noisy_errors()


# --- The Alchemist ---------------------------------------------------------
#
# The only card played before the roll, so it is the one a player reaches for
# every turn they hold it — and the only one whose "no flow yet" note a player
# saw before every single roll.


class TestAlchemist:
    def test_the_alchemist_decides_both_dice(self, alchemist):
        """Choose 2 and 3 inline, play, then roll and get 2 and 3.

        The roll is the assertion: the card writes `pending_dice`, and nothing
        else on screen would tell a player whether it took.
        """
        player, _marks, _tabs = alchemist

        open_progress_fold(player)
        selects = player.page.query_selector_all(
            ".progress-card select.progress-target"
        )
        assert len(selects) == 2, "the Alchemist names two dice, not one"
        selects[0].select_option("2")
        selects[1].select_option("3")
        shot(player, "alchemist-dice-picked")

        press_play(player, "alchemist")
        wait_for_card_spent(player, "alchemist")
        close_progress_fold(player)

        roll_dice(player)
        player.page.wait_for_function(
            "() => document.querySelectorAll('#dice-display .die').length === 2",
            timeout=8000,
        )
        # The dice are physical pip dice now, so the face is read from the pip
        # count drawn on it, not a printed number.
        faces = player.page.eval_on_selector_all(
            "#dice-display .die",
            "dice => dice.map(die => die.querySelectorAll('.pip').length)",
        )
        assert faces == [2, 3], f"the dice came up {faces}, not the pair chosen"
        assert player.noisy_errors() == [], player.noisy_errors()


# --- Targets on the board: an intersection, a road, a knight, two tokens ----


class TestMedicine:
    def test_medicine_upgrades_the_settlement_that_was_tapped(self, medicine):
        """A vertex pick, and the discounted city it pays for."""
        player, marks, _ = medicine

        arm_pick(player, "medicine")
        aim_at(player, "vertex", [marks["home"]])
        confirm_pick(player, "Medicine")
        wait_for_card_spent(player, "medicine")

        player.page.wait_for_function(
            "vertex => (window.__catanDebug.getBoard().vertices[vertex].building"
            "  || {}).type === 'city'",
            arg=marks["home"], timeout=8000,
        )
        assert dict((player.me() or {}).get("resources") or {}) == EMPTY_HAND, (
            "the discounted price was not taken"
        )
        next_frame(player.page)
        shot(player, "medicine-city")


class TestDiplomat:
    def test_the_diplomat_removes_the_road_that_was_tapped(self, diplomat):
        """An edge pick — and the free road the card gives back for it."""
        player, marks, _ = diplomat

        arm_pick(player, "diplomat")
        removed = aim_at(player, "edge", marks["roads"])
        confirm_pick(player, "Diplomat")
        wait_for_card_spent(player, "diplomat")

        player.page.wait_for_function(
            "edge => !window.__catanDebug.getBoard().edges[edge].road",
            arg=removed, timeout=8000,
        )
        # It was the player's own road, so they may rebuild it elsewhere free.
        assert player.board()["free_roads_remaining"] == 1
        next_frame(player.page)
        shot(player, "diplomat-road-removed")


class TestSmith:
    def test_the_smith_promotes_both_knights_that_were_tapped(self, smith):
        """Two picks, and only the second one sends anything.

        The first tap records the knight the way a knight move records the one
        it picked up: nothing has been sent, so there is nothing to confirm.
        """
        player, marks, _ = smith

        arm_pick(player, "smith")
        first = aim_at(player, "vertex", [marks["knights"][0]])
        next_frame(player.page)
        assert player.page.is_hidden("#placement-confirm"), (
            "the first knight raised a ✓ for a card that had sent nothing"
        )
        assert selection(player)["progressPick"]["picked"] == [first]

        aim_at(player, "vertex", [marks["knights"][1]])
        confirm_pick(player, "Smith")
        wait_for_card_spent(player, "smith")

        player.page.wait_for_function(
            "owner => (window.__catanDebug.getBoard().cities_knights.knights[owner]"
            "  || []).every(knight => knight.rank === 2)",
            arg=player.name, timeout=8000,
        )
        assert selection(player)["mode"] is None
        assert player.noisy_errors() == [], player.noisy_errors()

    def test_one_knight_is_a_legal_smith(self, smith):
        """"Up to two": a player who wants to promote one may say so.

        Without this the only way out of a half-finished Smith is to cancel it,
        which is a worse deal than the card offers.
        """
        player, marks, _ = smith

        arm_pick(player, "smith")
        chosen = aim_at(player, "vertex", [marks["knights"][0]])
        open_progress_fold(player)
        player.page.click("[data-progress-action='send']")
        wait_for_card_spent(player, "smith")

        player.page.wait_for_function(
            "([owner, vertex]) => (window.__catanDebug.getBoard()"
            "  .cities_knights.knights[owner] || [])"
            "  .some(knight => knight.vertex === vertex && knight.rank === 2)",
            arg=[player.name, chosen], timeout=8000,
        )
        promoted = player.page.evaluate(
            "owner => (window.__catanDebug.getBoard().cities_knights.knights[owner]"
            "  || []).filter(knight => knight.rank === 2).length",
            player.name,
        )
        assert promoted == 1, "playing with one knight promoted the other as well"


class TestInventor:
    def test_two_tokens_are_picked_in_turn_and_then_swapped(self, inventor):
        """The odd card out: it takes two picks, and the player has to be able
        to tell which one they are on and to get out of a half-finished one."""
        player, marks, _ = inventor

        arm_pick(player, "inventor")
        assert "pick 1 of 2" in player.page.inner_text("#progress-cards-chip")

        first = aim_at(player, "hex", marks["movable"])
        next_frame(player.page)
        assert player.page.is_hidden("#placement-confirm"), (
            "the first token raised a ✓ for a swap that had sent nothing"
        )
        assert "pick 2 of 2" in player.page.inner_text("#progress-cards-chip")
        shot(player, "inventor-first-token")

        before = player.board()["hexes"]
        second = aim_at(
            player, "hex", [key for key in marks["movable"] if key != first]
        )
        confirm_pick(player, "Inventor")
        wait_for_card_spent(player, "inventor")

        player.page.wait_for_function(
            "([one, other, was]) => {"
            "  const hexes = window.__catanDebug.getBoard().hexes;"
            "  return hexes[one].number === was; }",
            arg=[first, second, before[second]["number"]], timeout=8000,
        )
        after = player.board()["hexes"]
        assert after[first]["number"] == before[second]["number"]
        assert after[second]["number"] == before[first]["number"]
        next_frame(player.page)
        shot(player, "inventor-tokens-swapped")

    def test_a_protected_token_is_shown_as_blocked(self, inventor):
        """2, 6, 8 and 12 do not move, and the ghost says so before the trip."""
        player, marks, _ = inventor
        if not marks["protected"]:
            pytest.skip("this board has no protected tokens to aim at")

        arm_pick(player, "inventor")
        aim_at(player, "hex", marks["protected"])
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
        assert "not allowed here" in player.page.inner_text("#placement-announce")

    def test_a_half_finished_swap_can_be_taken_back(self, inventor):
        """Tapping the first token again unpicks it, and Cancel drops the lot —
        neither of which may cost the player the card."""
        player, marks, _ = inventor

        arm_pick(player, "inventor")
        first = aim_at(player, "hex", marks["movable"])
        next_frame(player.page)
        aim_at(player, "hex", [first])
        next_frame(player.page)
        assert selection(player)["progressPick"]["picked"] == []

        aim_at(player, "hex", marks["movable"])
        open_progress_fold(player)
        press_play(player, "inventor")   # the same button, now Cancel
        assert selection(player)["progressPick"]["card"] is None
        assert selection(player)["mode"] is None
        assert hand_of(player) == ["inventor"], "cancelling ate the card"


class TestBishop:
    def test_the_bishop_moves_the_robber_to_the_hex_that_was_tapped(self, bishop):
        """The other card that takes a hex, and it wants a different one from
        the Merchant: any land hex, whether the player is anywhere near it."""
        player, marks, _ = bishop

        arm_pick(player, "bishop")
        chosen = aim_at(player, "hex", marks["land"])
        confirm_pick(player, "Bishop")
        wait_for_card_spent(player, "bishop")

        player.page.wait_for_function(
            "hex => window.__catanDebug.getBoard().robber_hex === hex",
            arg=chosen, timeout=8000,
        )
        # And unlike a 7, it leaves nothing for the player to answer.
        assert player.board()["must_move_robber"] is False
        next_frame(player.page)
        shot(player, "bishop-robber-moved")

    def test_the_sea_is_shown_as_blocked(self, bishop):
        """"The robber goes on a land hex" — said before the round trip."""
        player, marks, _ = bishop
        if not marks["ocean"]:
            pytest.skip("this board has no reachable ocean hex")

        arm_pick(player, "bishop")
        aim_at(player, "hex", marks["ocean"])
        player.page.wait_for_selector("#placement-confirm:not(.hidden)", timeout=5000)
        assert "not allowed here" in player.page.inner_text("#placement-announce")


class TestEngineer:
    def test_the_engineer_walls_the_city_that_was_tapped(self, engineer):
        """One wall, free, on a city the player owns — an empty hand proves it
        was the card and not two brick that paid."""
        player, marks, _ = engineer

        arm_pick(player, "engineer")
        aim_at(player, "vertex", [marks["home"]])
        confirm_pick(player, "Engineer")
        wait_for_card_spent(player, "engineer")

        player.page.wait_for_function(
            "([owner, vertex]) => (window.__catanDebug.getBoard().cities_knights"
            "  .city_wall_vertices[owner] || []).includes(vertex)",
            arg=[player.name, marks["home"]], timeout=8000,
        )
        assert dict((player.me() or {}).get("resources") or {}) == EMPTY_HAND
        next_frame(player.page)
        shot(player, "engineer-wall")


class TestIntrigue:
    def test_the_intrigue_displaces_the_knight_that_was_tapped(self, intrigue):
        """A knight pick aimed at somebody else's piece, which is the only card
        that does that — the Smith's picks are the player's own."""
        player, marks, tabs = intrigue

        arm_pick(player, "intrigue")
        aim_at(player, "vertex", [marks["knight"]])
        confirm_pick(player, "Intrigue")
        wait_for_card_spent(player, "intrigue")

        player.page.wait_for_function(
            "([owner, vertex]) => !(window.__catanDebug.getBoard().cities_knights"
            "  .knights[owner] || []).some(knight => knight.vertex === vertex)",
            arg=[marks["victim"], marks["knight"]], timeout=8000,
        )
        assert tabs[marks["victim"]].noisy_errors() == []
        next_frame(player.page)
        shot(player, "intrigue-knight-displaced")


class TestMerchantFleet:
    def test_the_question_says_which_card_asked_it(self, merchant_fleet):
        """The dialog was headed "Your decision" with nothing to say why.

        Every other pending choice names the rule that raised it; this one had
        no title of its own, so a player was handed eight card types and no
        clue which of their cards had asked.
        """
        player, _marks, _tabs = merchant_fleet

        press_play(player, "merchant_fleet")
        player.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)
        assert "Merchant Fleet" in player.page.inner_text("#choice-prompt")
        assert player.page.inner_text("#choice-context").strip() != ""
        shot(player, "merchant-fleet-choice")

        player.page.click("#choice-options .choice-option")
        player.page.wait_for_function(
            "() => window.__catanDebug.getBoard().pending_choices.length === 0",
            timeout=8000,
        )


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
