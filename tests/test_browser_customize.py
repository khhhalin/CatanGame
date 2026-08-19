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
