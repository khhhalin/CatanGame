"""The Customize panel, in a real browser.

This is a client-only restyle of one browser's own view. Nothing here touches
the server, so every assertion is about what the *local* player sees change,
measured as computed style, not as DOM presence — a panel whose token did not
actually reach the CSS satisfies every DOM check while painting unchanged.

The load-bearing one is persistence: the whole point is that a customization
survives a reload (it is applied from localStorage in a <head> script before
the body paints). A panel that forgets on reload is a panel nobody keeps.

Run: pytest tests/test_browser_customize.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    browser_session,
    start_server,
    stop_server,
)

pytestmark = pytest.mark.slow

STORAGE_KEY = "catan.customize"


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture
def server(tmp_path):
    proc, url = start_server(tmp_path / "data")
    yield url
    stop_server(proc)


def open_customize(page):
    page.click("#customize-toggle")
    page.wait_for_selector("#customize-body:not(.hidden)", timeout=5000)


def set_range(page, selector, value):
    """Set a range/color input and fire the `input` the listeners bind to.

    `fill` does not drive a range slider, so the value is set and the event
    dispatched explicitly — the same path a drag takes.
    """
    page.eval_on_selector(
        selector,
        "(el, v) => { el.value = v;"
        "             el.dispatchEvent(new Event('input', {bubbles: true})); }",
        value,
    )


def bg_color(page, selector):
    return page.eval_on_selector(
        selector, "el => getComputedStyle(el).backgroundColor"
    )


def alpha_of(rgba):
    """The alpha channel of a computed `rgba(r, g, b, a)` string, or 1.0."""
    inside = rgba[rgba.index("(") + 1 : rgba.index(")")]
    parts = [p.strip() for p in inside.split(",")]
    return float(parts[3]) if len(parts) == 4 else 1.0


def start_game(browser, url):
    host = Player(browser, url, "Ann")
    host.join()
    guest = Player(browser, url, "Bo")
    guest.join()
    host.page.click("#start-game-btn")
    host.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    return host, guest


def test_the_opacity_slider_thins_a_real_glass_panel(browser, server):
    """Panel opacity drives --panel-opacity -> --glass -> every glass float.

    Asserted on the scoreboard float's own computed background: an unconfigured
    browser paints it at the shipped 0.62, and the slider must actually change
    the pixels, not just the token. The 0.62 baseline is the byte-identical
    guard — a default browser is exactly as it was.
    """
    host, _ = start_game(browser, server)
    host.page.wait_for_selector(".players-float", timeout=5000)

    before = bg_color(host.page, ".players-float")
    # The default is untouched frosted glass: rgb(17 23 29 / 0.62).
    assert alpha_of(before) == pytest.approx(0.62, abs=0.01), before

    open_customize(host.page)
    set_range(host.page, "#cz-opacity", "0.2")

    after = bg_color(host.page, ".players-float")
    assert alpha_of(after) < 0.4, (before, after)
    assert host.noisy_errors() == [], host.noisy_errors()


def test_the_accent_recolours_the_title_and_survives_a_reload(browser, server):
    """The accent lever moves --accent, which the title paints itself from, and
    the choice is still there after a reload — the localStorage round trip that
    is the whole reason the panel persists at all."""
    player = Player(browser, url=server, name="Ann")
    title_color = "() => getComputedStyle(document.getElementById('game-title')).color"

    before = player.page.evaluate(title_color)
    assert before != "rgb(20, 200, 40)", before

    open_customize(player.page)
    set_range(player.page, "#cz-accent", "#14c828")  # rgb(20, 200, 40)

    assert player.page.evaluate(title_color) == "rgb(20, 200, 40)"

    # The reload is the load-bearing half: applied from storage in <head>,
    # before the body paints, so the title comes back already recoloured.
    player.page.reload(wait_until="networkidle")
    assert player.page.evaluate(title_color) == "rgb(20, 200, 40)"
    stored = player.page.evaluate(
        f"() => window.localStorage.getItem('{STORAGE_KEY}')"
    )
    assert stored and "14c828" in stored, stored


def test_custom_css_applies_locally_and_reset_restores_the_default(browser, server):
    """A raw rule reaches a real panel, persists a reload, and Reset takes the
    whole thing back to the default look and clears the stored config."""
    player = Player(browser, url=server, name="Ann")
    page_bg = "() => getComputedStyle(document.body).backgroundColor"

    default_bg = player.page.evaluate(page_bg)
    assert default_bg != "rgb(9, 12, 15)", default_bg

    open_customize(player.page)
    player.page.fill("#cz-custom", "body { background-color: rgb(9, 12, 15); }")

    assert player.page.evaluate(page_bg) == "rgb(9, 12, 15)"

    # It is injected into its own <style id="user-custom-css"> — a bad rule
    # there can never take the structured overrides down with it.
    assert player.page.evaluate(
        "() => document.getElementById('user-custom-css').textContent"
    ).strip().startswith("body")

    player.page.reload(wait_until="networkidle")
    assert player.page.evaluate(page_bg) == "rgb(9, 12, 15)", "custom CSS lost on reload"

    open_customize(player.page)
    player.page.click("#cz-reset")

    assert player.page.evaluate(page_bg) == default_bg
    assert player.page.evaluate(
        f"() => window.localStorage.getItem('{STORAGE_KEY}')"
    ) is None
    assert player.page.evaluate(
        "() => document.getElementById('user-custom-css').textContent"
    ) == ""
    assert player.noisy_errors() == [], player.noisy_errors()


def box(page, selector):
    """The panel's viewport bounding box, as {x, y, width, height}."""
    return page.query_selector(selector).bounding_box()


def drag(page, box_before, dx, dy):
    """Grab a panel at its centre and drag it by (dx, dy) as a pointer would."""
    cx = box_before["x"] + box_before["width"] / 2
    cy = box_before["y"] + box_before["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    # Stepped so the pointermove listener runs the same path a real drag takes.
    page.mouse.move(cx + dx, cy + dy, steps=8)
    page.mouse.up()


def test_edit_layout_drags_the_scoreboard_and_it_survives_a_reload(browser, server):
    """Phase B: a dragged panel moves by the drag delta, the position persists a
    reload (the load-bearing half — applied from localStorage in <head> before
    the body paints), and Reset layout returns it to default while a Phase-A
    appearance override (the accent) is left untouched.

    Catches the failure the layout pass exists to prevent: a panel that forgets
    where it was dragged the moment the tab reloads.
    """
    host, _ = start_game(browser, server)
    page = host.page
    # A reload mid-game resumes the seat; accept the takeover prompt if one is
    # raised so the game (and the scoreboard) comes back.
    page.on("dialog", lambda d: d.accept())
    page.wait_for_selector(".players-float", timeout=5000)

    # A Phase-A override first, so we can prove Reset layout does not clear it.
    open_customize(page)
    set_range(page, "#cz-accent", "#14c828")  # rgb(20, 200, 40)
    title_color = "() => getComputedStyle(document.getElementById('game-title')).color"
    assert page.evaluate(title_color) == "rgb(20, 200, 40)"

    # Enter Edit layout mode, then close the panel so its dropdown does not sit
    # over the top-right scoreboard we are about to grab (edit mode stays on).
    page.check("#cz-layout-edit")
    page.click("#customize-close")
    page.wait_for_selector("#customize-body.hidden", state="attached", timeout=5000)
    before = box(page, ".players-float")
    delta_x, delta_y = -140, 90
    drag(page, before, delta_x, delta_y)

    after = box(page, ".players-float")
    assert after["x"] - before["x"] == pytest.approx(delta_x, abs=6), (before, after)
    assert after["y"] - before["y"] == pytest.approx(delta_y, abs=6), (before, after)
    moved_x, moved_y = after["x"], after["y"]

    # The reload is the assertion that matters: rejoin the running game and the
    # scoreboard must return already displaced, not at its default corner.
    page.reload(wait_until="networkidle")
    page.click("#join-btn")
    page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    page.wait_for_selector(".players-float", timeout=5000)
    reloaded = box(page, ".players-float")
    assert reloaded["x"] == pytest.approx(moved_x, abs=6), (moved_x, reloaded)
    assert reloaded["y"] == pytest.approx(moved_y, abs=6), (moved_y, reloaded)

    # Reset layout returns the panel to default WITHOUT wiping the accent.
    open_customize(page)
    page.click("#cz-reset-layout")
    reset = box(page, ".players-float")
    assert reset["x"] == pytest.approx(before["x"], abs=6), (before, reset)
    assert reset["y"] == pytest.approx(before["y"], abs=6), (before, reset)
    assert page.evaluate(title_color) == "rgb(20, 200, 40)", "Reset layout wiped the accent"
    assert host.noisy_errors() == [], host.noisy_errors()


# --- Phase C: the HUD builder ---------------------------------------------
#
# The readouts are pulled out of the rail and composed into the player's own
# HUD. These assert on what a player sees change - a readout gone, a readout
# moved out of the rail and still showing its live value - and, as ever here,
# that the composition survives the reload it is applied from before paint.


def parent_id(page, selector):
    return page.eval_on_selector(
        selector, "el => (el.parentElement && el.parentElement.id) || ''"
    )


def rejoin_running_game(page):
    """Reload and rejoin the seat, so the aside readouts come back on screen."""
    page.on("dialog", lambda d: d.accept())
    page.reload(wait_until="networkidle")
    page.click("#join-btn")
    page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)


def hide_widget(page, widget_id, shown):
    """Tick/untick a widget's checklist row (ticked = shown)."""
    page.eval_on_selector(
        f'#cz-widget-list input[data-widget-id="{widget_id}"]',
        "(el, show) => { if (el.checked !== show) { el.checked = show;"
        "                el.dispatchEvent(new Event('change', {bubbles: true})); } }",
        shown,
    )


def test_hud_hides_a_readout_and_it_stays_hidden_across_a_reload(browser, server):
    """A widget unticked in the HUD builder leaves the screen, and - the load-
    bearing half - is still gone after a reload, because the composition is
    applied from localStorage before the body paints.

    Catches a HUD that forgets what the player hid the moment the tab reloads,
    and proves the hide is real (the Bank is on screen by default first).
    """
    host, _ = start_game(browser, server)
    page = host.page
    page.wait_for_selector("#right-bank", timeout=5000)
    assert page.is_visible("#right-bank"), "the Bank readout is not on screen by default"

    open_customize(page)
    hide_widget(page, "right-bank", shown=False)
    assert not page.is_visible("#right-bank"), "unticking the Bank did not hide it"

    rejoin_running_game(page)
    assert not page.is_visible("#right-bank"), "the Bank came back after a reload"
    # And the checklist reflects the stored state when the panel reopens.
    open_customize(page)
    assert page.eval_on_selector(
        '#cz-widget-list input[data-widget-id="right-bank"]', "el => el.checked"
    ) is False
    assert host.noisy_errors() == [], host.noisy_errors()


def test_hud_free_drags_a_readout_out_and_reset_hud_restores_it(browser, server):
    """A readout dragged out of the rail is re-parented into the board overlay
    layer, keeps showing its live value there (it is the same live element, not
    a copy), survives a reload, and Reset HUD returns it to the rail while a
    Phase-A appearance override (the accent) is left untouched.

    The live-value assertion is the one that matters: a moved widget the renderer
    can no longer find would sit there empty. And Reset HUD's scoping is the
    other: it must clear the composition without touching the look.
    """
    host, _ = start_game(browser, server)
    page = host.page
    page.on("dialog", lambda d: d.accept())
    page.wait_for_selector("#right-bank", timeout=5000)
    # The Bank renders its live tiles into #bank-display; capture that it is
    # non-empty so we can prove it is still live after the move.
    def bank_filled():
        return page.eval_on_selector("#bank-display", "el => el.textContent.trim().length") > 0
    page.wait_for_function(
        "() => document.querySelector('#bank-display').textContent.trim().length > 0",
        timeout=5000,
    )
    assert parent_id(page, "#right-bank") == "side-tabs", "the Bank did not start in the rail"

    # A Phase-A override first, so we can prove Reset HUD does not clear it.
    open_customize(page)
    set_range(page, "#cz-accent", "#14c828")  # rgb(20, 200, 40)
    title_color = "() => getComputedStyle(document.getElementById('game-title')).color"
    assert page.evaluate(title_color) == "rgb(20, 200, 40)"

    # Enter edit mode, close the dropdown so it is clear of the rail, and drag
    # the Bank onto the board (any drop off a custom panel free-floats it).
    page.check("#cz-layout-edit")
    page.click("#customize-close")
    page.wait_for_selector("#customize-body.hidden", state="attached", timeout=5000)

    before = box(page, "#right-bank")
    overlays = box(page, "#board-overlays")
    target_x = overlays["x"] + overlays["width"] / 2
    target_y = overlays["y"] + overlays["height"] / 2
    cx = before["x"] + before["width"] / 2
    cy = before["y"] + before["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(target_x, target_y, steps=10)
    page.mouse.up()

    assert parent_id(page, "#right-bank") == "board-overlays", (
        "the Bank was not re-parented into the overlay layer"
    )
    moved = box(page, "#right-bank")
    assert abs(moved["x"] - before["x"]) > 40 or abs(moved["y"] - before["y"]) > 40, (
        f"the Bank did not move: {before} -> {moved}"
    )
    assert bank_filled(), "the Bank stopped showing its live value after the move"

    # Persistence: rejoin the running game and the Bank must return already in
    # the overlay layer, not back in the rail.
    rejoin_running_game(page)
    assert parent_id(page, "#right-bank") == "board-overlays", (
        "the moved Bank fell back to the rail after a reload"
    )
    assert bank_filled(), "the reloaded Bank shows no live value"

    # Reset HUD returns the Bank to the rail WITHOUT wiping the accent.
    open_customize(page)
    page.click("#cz-reset-hud")
    assert parent_id(page, "#right-bank") == "side-tabs", "Reset HUD did not restore the Bank"
    assert page.evaluate(title_color) == "rgb(20, 200, 40)", "Reset HUD wiped the accent"
    assert host.noisy_errors() == [], host.noisy_errors()


def widget_panel(page, selector):
    """The data-panel-id of the custom panel a widget sits in, or '' if none."""
    return page.eval_on_selector(
        selector,
        "el => { const p = el.closest('.hud-panel'); return p ? p.dataset.panelId : ''; }",
    )


def drag_between(page, from_box, to_x, to_y):
    """Grab a box at its centre and drop it at an absolute point, stepped."""
    cx = from_box["x"] + from_box["width"] / 2
    cy = from_box["y"] + from_box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(to_x, to_y, steps=10)
    page.mouse.up()


def test_hud_docks_a_readout_in_a_custom_panel_that_persists_and_resets(browser, server):
    """The composition layer end to end: create an empty custom panel, drag a
    readout into it (DOM parentage + on-screen position, still showing its live
    value), move the panel, reload and find the whole composition intact, and
    Reset HUD take it all back to the default rail.

    The reload is the load-bearing assertion - a builder whose panels evaporate
    on reload is useless - and it is checked on DOM parentage, not a class, so a
    widget that merely looks docked but is no longer the panel's child fails.
    """
    host, _ = start_game(browser, server)
    page = host.page
    page.on("dialog", lambda d: d.accept())
    page.wait_for_selector("#right-bank", timeout=5000)
    page.wait_for_function(
        "() => document.querySelector('#bank-display').textContent.trim().length > 0",
        timeout=5000,
    )

    def bank_filled():
        return page.eval_on_selector("#bank-display", "el => el.textContent.trim().length") > 0

    # Create an empty panel (this also turns Edit layout on), then close the
    # dropdown so it is clear of the board.
    open_customize(page)
    page.click("#cz-hud-add-panel")
    page.wait_for_selector(".hud-panel", timeout=5000)
    panel_id = page.eval_on_selector(".hud-panel", "el => el.dataset.panelId")
    page.click("#customize-close")
    page.wait_for_selector("#customize-body.hidden", state="attached", timeout=5000)

    # Drag the Bank onto the panel; it must become the panel's child and stay live.
    panel_box = box(page, ".hud-panel")
    bank_box = box(page, "#right-bank")
    drag_between(
        page, bank_box,
        panel_box["x"] + panel_box["width"] / 2,
        panel_box["y"] + panel_box["height"] / 2,
    )

    assert widget_panel(page, "#right-bank") == panel_id, (
        "the Bank was not docked inside the custom panel"
    )
    docked = box(page, "#right-bank")
    outer = box(page, ".hud-panel")
    # On-screen: the Bank sits within the panel it was dropped on.
    assert outer["x"] - 4 <= docked["x"] and docked["x"] <= outer["x"] + outer["width"] + 4, (
        f"the docked Bank is not within the panel horizontally: {docked} vs {outer}"
    )
    assert docked["y"] >= outer["y"] - 4, (
        f"the docked Bank sits above its panel: {docked} vs {outer}"
    )
    assert bank_filled(), "the docked Bank stopped showing its live value"

    # Move the panel by its header and confirm it actually moved.
    head_box = box(page, ".hud-panel-head")
    before_panel = box(page, ".hud-panel")
    drag_between(page, head_box, head_box["x"] + head_box["width"] / 2 + 70,
                 head_box["y"] + head_box["height"] / 2 + 120)
    after_panel = box(page, ".hud-panel")
    assert abs(after_panel["x"] - before_panel["x"]) > 30 or (
        abs(after_panel["y"] - before_panel["y"]) > 30), (
        f"the panel did not move: {before_panel} -> {after_panel}"
    )

    # The reload: rejoin the running game and the panel and its docked Bank must
    # both come back, from localStorage, before the body paints.
    rejoin_running_game(page)
    page.wait_for_selector(".hud-panel", timeout=5000)
    assert widget_panel(page, "#right-bank") == panel_id, (
        "the docked Bank was lost after a reload"
    )
    assert bank_filled(), "the reloaded docked Bank shows no live value"

    # Reset HUD dissolves the panel and returns the Bank to the rail.
    open_customize(page)
    page.click("#cz-reset-hud")
    assert page.query_selector(".hud-panel") is None, "Reset HUD left a custom panel behind"
    assert parent_id(page, "#right-bank") == "side-tabs", "Reset HUD did not restore the Bank"
    assert host.noisy_errors() == [], host.noisy_errors()
