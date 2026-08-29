"""The first-run discovery hint for the layout editor, in a real browser.

Testers played the default screen, disliked how it was arranged, and never found
that the gear is where you rearrange and hide panels. The fix is a one-time
bubble pointing at the gear, plus wording on the gear and the panel that names
"layout". These pin that the hint appears once, dismisses, never nags again, and
that the wording actually mentions arranging a layout.

The hint is suppressed for an automated browser (navigator.webdriver) so it does
not appear on the first load of every other browser suite; a test opts back in
by setting `catan.customize.coach.force` before the page loads, the same
init-script trick the YOLO fixture uses.

Run: pytest tests/test_browser_customize_discovery.py -m slow -v
"""

import pytest
from browser_harness import (
    browser_session,
    start_server,
    stop_server,
)

pytestmark = pytest.mark.slow

COACH_KEY = "catan.customize.coach"
FORCE_KEY = "catan.customize.coach.force"


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture
def server(tmp_path):
    proc, url = start_server(tmp_path / "data")
    yield url
    stop_server(proc)


def page_opted_into_the_hint(browser, url):
    """A fresh tab that has opted the hint back in before anything loads.

    The force flag is written by an init script, so it is in place before the
    <head> customize.js runs and decides whether to show the hint — exactly how
    a real (non-automated) browser reaches that code with the flag absent.
    """
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    context.add_init_script(
        f"window.localStorage.setItem('{FORCE_KEY}', '1');"
    )
    page = context.new_page()
    page.goto(url, wait_until="networkidle")
    return context, page


def rect(page, selector):
    return page.eval_on_selector(
        selector,
        "el => { const r = el.getBoundingClientRect();"
        "        return {left: r.left, top: r.top, right: r.right,"
        "                bottom: r.bottom}; }",
    )


def test_the_hint_appears_once_and_dismisses_for_good(browser, server):
    """The bubble shows on a first visit, "Got it" clears it, and it does not
    come back on the next load — the seen-flag outlives the reload."""
    context, page = page_opted_into_the_hint(browser, server)
    try:
        page.wait_for_selector(".customize-coach", timeout=5000)

        # It points players at *arranging* their layout, not just restyling.
        text = page.eval_on_selector(".customize-coach", "el => el.innerText")
        assert "drag" in text.lower() and "layout" in text.lower(), text

        # The container cannot intercept a click meant for the screen beneath —
        # only its own button is live. This is what keeps it from disturbing
        # play (and every other browser suite, were it ever shown to one).
        assert page.eval_on_selector(
            ".customize-coach", "el => getComputedStyle(el).pointerEvents"
        ) == "none"

        # Wholly on screen — a hint half off the edge advertises nothing.
        box = rect(page, ".customize-coach")
        view = page.evaluate("() => ({w: innerWidth, h: innerHeight})")
        assert box["left"] >= 0 and box["top"] >= 0
        assert box["right"] <= view["w"] + 1 and box["bottom"] <= view["h"] + 1

        # The gear draws the eye while the hint is up.
        assert page.eval_on_selector(
            "#customize-toggle", "el => el.classList.contains('coach-pulse')"
        )

        # Dismiss, and it is gone and remembered.
        page.click(".customize-coach-btn")
        page.wait_for_selector(".customize-coach", state="detached", timeout=3000)
        assert page.evaluate(
            f"() => localStorage.getItem('{COACH_KEY}')"
        ) == "1"
        assert not page.eval_on_selector(
            "#customize-toggle", "el => el.classList.contains('coach-pulse')"
        )

        # Reload: still opted in via the init script, but the seen-flag wins and
        # nothing shows.
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(200)
        assert page.query_selector(".customize-coach") is None
    finally:
        context.close()


def test_opening_the_gear_is_itself_the_dismissal(browser, server):
    """A player who just clicks the gear has discovered the panel; the hint
    should clear on that click rather than linger over the open panel."""
    context, page = page_opted_into_the_hint(browser, server)
    try:
        page.wait_for_selector(".customize-coach", timeout=5000)
        page.click("#customize-toggle")
        page.wait_for_selector("#customize-body:not(.hidden)", timeout=5000)
        page.wait_for_selector(".customize-coach", state="detached", timeout=3000)
        assert page.evaluate(
            f"() => localStorage.getItem('{COACH_KEY}')"
        ) == "1"
    finally:
        context.close()


def test_the_gear_and_panel_name_the_layout(browser, server):
    """The standing wording, with no hint involved: the gear's tooltip and the
    panel's own heading both say "layout", so a player looking to rearrange
    panels has a reason to open it. This is what the tester was missing."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        page.goto(server, wait_until="networkidle")
        title = page.get_attribute("#customize-toggle", "title") or ""
        assert "layout" in title.lower(), title

        page.click("#customize-toggle")
        page.wait_for_selector("#customize-body:not(.hidden)", timeout=5000)
        head = page.eval_on_selector(".customize-head span", "el => el.textContent")
        assert "layout" in head.lower(), head
    finally:
        context.close()
