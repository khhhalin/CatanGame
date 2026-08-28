"""The Dup button on a custom map really duplicates it, in a real browser.

Regression: the Dup button called `duplicateMap(m)` with `m` taken straight from
the map *list*, whose rows are summaries — `map_store._summary` sets `regions`
to an integer count and carries no frame/pool/harbours. `duplicateMap` then ran
`(m.regions || []).map(...)` on a number, threw a TypeError, and the click did
nothing. The Load button beside it was already correct: it fetches the full
definition with `request_map` first. Dup must do the same, then duplicate.

Run: pytest tests/test_browser_map_editor_dup.py -m slow -v
"""

import pytest
from browser_harness import Player, browser_session, start_server, stop_server

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture
def lobby(browser, tmp_path):
    proc, url = start_server(tmp_path)
    alice = Player(browser, url, "Alice", viewport=VIEWPORT)
    bob = Player(browser, url, "Bob", viewport=VIEWPORT)
    alice.join()
    bob.join()
    yield alice, bob
    stop_server(proc)


def _open_save_popover(page):
    page.click("#editor-save-btn")
    page.wait_for_selector("#editor-save-popover:not(.hidden)", timeout=5000)


def test_dup_on_a_custom_map_duplicates_it(lobby):
    """Save a custom map, then Dup it: the editor loads a fresh copy whose name
    gains another ' copy'. Before the fix the Dup click threw on the summary row
    and nothing changed."""
    alice, _ = lobby
    page = alice.page

    page.click("#maps-btn")
    page.wait_for_selector("#map-editor-screen:not(.hidden)", timeout=5000)

    # Make a custom map to duplicate: load a built-in (arrives as a copy) and
    # save it, so it appears in the list with a Dup button of its own.
    _open_save_popover(page)
    page.wait_for_selector(
        "#editor-save-popover li:has-text('Six Shores')", timeout=8000
    )
    page.locator(
        "#editor-save-popover li:has-text('Six Shores')"
    ).first.locator("button:text-is('Load')").click()
    page.wait_for_timeout(500)
    _open_save_popover(page)
    page.click("#editor-save-confirm-btn")
    page.wait_for_timeout(600)

    # Reopen the list; the saved custom copy now has a Dup button.
    _open_save_popover(page)
    custom = page.locator(
        "#editor-save-popover li:has(button:text-is('Dup'))"
    ).first
    page.wait_for_function(
        "() => !!document.querySelector"
        "('#editor-save-popover li button')",
        timeout=8000,
    )
    custom.locator("button:text-is('Dup')").click()

    # A working Dup loads a fresh copy: the name gains a second ' copy'.
    page.wait_for_function(
        "() => document.getElementById('editor-map-name')"
        ".value.trim().endsWith('copy copy')",
        timeout=8000,
    )
    name = page.eval_on_selector("#editor-map-name", "el => el.value")
    assert name.strip().endswith("copy copy"), name
