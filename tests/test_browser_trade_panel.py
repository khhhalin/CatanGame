"""The shape of the Propose Trade dialog, measured where a player meets it.

Three things a tester filed after playing a game with commodities on:

  - "in your give/want section ore is too close to cloth (different distance
    than other resources)". Ore ends `.resource-selector` and cloth begins
    `#trade-give-commodities`; the two blocks sat flush at 0px while every
    picker inside a block was 8px from its neighbour.
  - "trade tab is too big in terms of height". At 390x780 the dialog's content
    was 879px in a 702px box, so Propose was below the fold and the player had
    to find a scrollbar inside a dialog to send an offer.
  - "in trade tab its hard to click the small arrows". Chromium paints the
    number field's spinners only on hover and sizes them off the field, which
    was 24.6px tall - about 12px of arrow to aim at. Growing the field was as
    far as CSS reached: the spinner is drawn inside it and splits its height,
    so the arrows are now real buttons either side of the field instead.

Every assertion here is a measurement of the rendered box, not of the DOM: the
markup was correct through all three of these.

Run: pytest tests/test_browser_trade_panel.py -m slow -v
"""

import os

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_road,
    build_settlement,
    edges_next_to,
    legal_setup_vertices,
    reveal_rule,
    start_server,
    stop_server,
    wait_for_rule,
)

pytestmark = pytest.mark.slow

# The phone the owner reads this on, and the desk it is played at. The dialog
# has to hold at both: the small one is where height bites, the large one is
# where an uneven gap is obvious.
PHONE = {"width": 390, "height": 780}
DESK = {"width": 1920, "height": 1080}

SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "trade",
)

GAME_SEED = 20260805

# Commodities are the case the tester played and the worst case for both the
# gap and the height: eight pickers a side rather than five.
RULES = {"commodities": True}

# Apple's Human Interface Guidelines and WCAG 2.5.8 both land near here; the
# field is what carries the spinner, so the field has to be this tall.
MIN_TAP = 40


def _measure_pickers(player):
    """Every picker in the You Give block, as rows of rendered boxes."""
    return player.page.evaluate("""
    () => {
      const section = document.querySelectorAll('#trade-modal .trade-modal-section')[0];
      const boxes = [...section.querySelectorAll('label')].map(label => {
        const r = label.getBoundingClientRect();
        return {
          name: label.textContent.trim().split(':')[0],
          top: r.top, bottom: r.bottom, left: r.left, right: r.right,
        };
      });
      const rows = [];
      for (const box of boxes) {
        const row = rows.find(r => Math.abs(r[0].top - box.top) < 1);
        if (row) { row.push(box); } else { rows.push([box]); }
      }
      return rows;
    }
    """)


def _gaps(rows):
    """Vertical gaps between consecutive picker rows, rounded to whole pixels."""
    return [
        (rows[i - 1][0]["name"], rows[i][0]["name"],
         round(rows[i][0]["top"] - rows[i - 1][-1]["bottom"]))
        for i in range(1, len(rows))
    ]


def _measure_steppers(player):
    """Every - and + button in the dialog, as rendered boxes with their names."""
    return player.page.evaluate("""
    () => [...document.querySelectorAll('#trade-modal .trade-step')].map(button => {
      const box = button.getBoundingClientRect();
      return {
        name: button.getAttribute('aria-label'),
        width: box.width, height: box.height,
      };
    })
    """)


def _step_button(card, delta):
    sign = "-1" if delta < 0 else "1"
    return f'#trade-modal .trade-stepper:has(#give-{card}) .trade-step[data-step="{sign}"]'


def _field_value(player, field_id):
    return player.page.input_value(f"#{field_id}")


def _open_trade_modal(player):
    player.page.click("#tab-trade")
    player.page.wait_for_selector("#propose-trade-btn", state="visible", timeout=5000)
    player.page.click("#propose-trade-btn")
    player.page.wait_for_selector("#trade-modal.show", timeout=5000)
    player.page.wait_for_selector("#trade-give-commodities:not(.hidden)", timeout=5000)


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    player.page.screenshot(path=os.path.join(SHOT_DIR, f"{label}.png"))


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture(scope="module")
def trader(browser, tmp_path_factory):
    """One player past setup with the dialog open and commodities in it.

    Two seats, because a trade dialog with nobody to trade with still renders
    the same pickers, and the second seat is what makes it the host's turn in a
    way the server agrees with.
    """
    proc, url = start_server(tmp_path_factory.mktemp("trade-panel"), seed=GAME_SEED)
    alice = Player(browser, url, "Alice", viewport=DESK, yolo=True)
    bob = Player(browser, url, "Bob", viewport=DESK, yolo=True)
    alice.join()
    bob.join()
    for rule_id, value in RULES.items():
        reveal_rule(alice, rule_id)
        control = alice.page.locator(f"#rule-{rule_id}")
        control.scroll_into_view_if_needed()
        control.set_checked(value)
        wait_for_rule(alice, rule_id, value)
    alice.page.click("#start-game-btn")
    for player in (alice, bob):
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)

    by_name = {"Alice": alice, "Bob": bob}
    for _step in range(12):
        board = alice.board()
        if board["game_phase"] != "setup":
            break
        actor = by_name[board["current_player"]]
        vertex = build_settlement(actor, legal_setup_vertices(board))
        build_road(actor, edges_next_to(actor.board(), vertex))
    assert alice.board()["game_phase"] == "playing", "setup never finished"

    current = by_name[alice.board()["current_player"]]
    _open_trade_modal(current)
    yield current
    stop_server(proc)


def test_every_pair_of_trade_pickers_is_the_same_distance_apart(trader):
    """Regression: "ore is too close to cloth (different distance than other
    resources)". The commodity pickers are a second block, and the gap between
    the blocks was not the gap inside them."""
    gaps = _gaps(_measure_pickers(trader))
    shot(trader, "trade-pickers-desk")
    assert len(gaps) >= 3, f"expected several rows of pickers, measured {gaps}"
    distinct = {gap for _before, _after, gap in gaps}
    assert len(distinct) == 1, f"pickers are unevenly spaced: {gaps}"


def test_the_trade_dialog_fits_a_phone_without_hiding_propose(trader):
    """Regression: "trade tab is too big in terms of height". Propose has to be
    on screen without scrolling inside the dialog, at the smallest size the
    game is played at."""
    trader.page.set_viewport_size(PHONE)
    trader.page.wait_for_timeout(150)
    try:
        fit = trader.page.evaluate("""
        () => {
          const content = document.querySelector('#trade-modal .modal-content');
          const button = document.getElementById('submit-trade-btn').getBoundingClientRect();
          return {
            scrollHeight: content.scrollHeight,
            clientHeight: content.clientHeight,
            buttonBottom: button.bottom,
            viewport: window.innerHeight,
          };
        }
        """)
        shot(trader, "trade-pickers-phone")
        assert fit["scrollHeight"] <= fit["clientHeight"] + 1, (
            f"the trade dialog scrolls inside itself: {fit}"
        )
        assert fit["buttonBottom"] <= fit["viewport"], (
            f"Propose is off the bottom of the screen: {fit}"
        )
    finally:
        trader.page.set_viewport_size(DESK)
        trader.page.wait_for_timeout(150)


def test_every_trade_field_is_tall_enough_to_carry_its_stepper(trader):
    """Regression: "in trade tab its hard to click the small arrows".

    The browser draws the spinner inside the field and splits its height
    between up and down, so the field's height is the arrows' height and there
    is nothing else to measure - headless Chromium does not paint the spinner
    at all, and Firefox offers no box for it. Every field, because the tester
    hit the commodity rows too.
    """
    fields = trader.page.evaluate(
        "() => [...document.querySelectorAll('#trade-modal .trade-modal-section input')]"
        "        .map(i => ({id: i.id, height: i.getBoundingClientRect().height}))"
    )
    assert len(fields) == 16, f"expected eight pickers a side, measured {len(fields)}"
    too_small = [f for f in fields if f["height"] < MIN_TAP]
    assert not too_small, f"fields too short for their arrows: {too_small}"


def test_every_trade_stepper_is_a_target_a_thumb_can_hit(trader):
    """Regression: "in trade tab its hard to click the small arrows".

    The native spinner is drawn inside the field and splits its height, so at
    the height this dialog can afford it was never going to be hittable. These
    are the buttons that replaced it - measured at both sizes the game is
    played at, because the phone is where the columns are tightest and the
    buttons are what has to give way there.
    """
    for label, viewport in (("desk", DESK), ("phone", PHONE)):
        trader.page.set_viewport_size(viewport)
        trader.page.wait_for_timeout(150)
        try:
            buttons = _measure_steppers(trader)
            shot(trader, f"trade-steppers-{label}")
            assert len(buttons) == 32, (
                f"expected a - and a + on all sixteen fields, measured {len(buttons)}"
            )
            too_small = [b for b in buttons
                         if b["width"] < MIN_TAP or b["height"] < MIN_TAP]
            assert not too_small, f"steppers too small to hit at {label}: {too_small}"
            # Sixteen fields in one dialog: "increase" would name none of them.
            assert len({b["name"] for b in buttons}) == 32, (
                f"steppers share accessible names: {sorted(b['name'] for b in buttons)}"
            )
        finally:
            trader.page.set_viewport_size(DESK)
            trader.page.wait_for_timeout(150)


def test_a_stepper_moves_its_field_and_stops_at_zero_and_at_the_hand(trader):
    """The buttons have to do what the arrows did, and refuse what the player
    cannot pay: the fields were capped at ten for every card, so the dialog let
    an offer of ore nobody held be typed and only the server said no."""
    hand = trader.me()["resources"]
    card = max(hand, key=hand.get)
    held = hand[card]
    assert held >= 1, f"the fixture's player holds nothing to give: {hand}"

    try:
        assert _field_value(trader, f"give-{card}") == "0"
        assert trader.page.is_disabled(_step_button(card, -1)), (
            "the - button is live at zero"
        )

        for _click in range(held):
            trader.page.click(_step_button(card, 1))
        assert _field_value(trader, f"give-{card}") == str(held)

        assert trader.page.is_disabled(_step_button(card, 1)), (
            f"+ is still live at {held} {card}, which is the whole hand"
        )
        assert not trader.page.is_disabled(_step_button(card, -1))

        trader.page.click(_step_button(card, -1))
        assert _field_value(trader, f"give-{card}") == str(held - 1)
    finally:
        trader.page.click("#trade-clear-btn")

    assert _field_value(trader, f"give-{card}") == "0", "Clear left a number behind"


def test_a_stepper_that_reaches_its_bound_is_greyed_out_without_moving(trader):
    """`test_arming_or_disabling_a_build_button_never_resizes_it` exists because
    a control that changes size under the finger moved the camera. A stepper
    disables at 0 and at the hand, sixteen times over, so it must disable in
    place."""
    hand = trader.me()["resources"]
    card = max(hand, key=hand.get)
    plus = _step_button(card, 1)

    before = trader.page.locator(plus).bounding_box()
    try:
        for _click in range(hand[card]):
            trader.page.click(plus)
        assert trader.page.is_disabled(plus), "the + never reached its bound"
        after = trader.page.locator(plus).bounding_box()
    finally:
        trader.page.click("#trade-clear-btn")

    assert before == after, f"the + moved or resized when it disabled: {before} -> {after}"
