"""Preview works before the map has ever been saved, in a real browser.

Regression: `requestPreview()` built the wire with `mapDocToWire()`, which
refuses a map with an empty `id` — and `id` is assigned only inside
`saveMap`/`saveMapAsCopy`. A freshly painted map, or a built-in just loaded (it
arrives through `duplicateMap`, which sets `id: ''`), therefore could not be
previewed at all: the press failed silently with the misleading notice "Enter a
map name first" even though a name was shown. That defeats the whole point of
Preview as the fast iteration tool (map-creator.md §4.6).

No editor browser test ever clicked Preview, so the unit and e2e suites were
both green over it.

Run: pytest tests/test_browser_map_preview.py -m slow -v
"""

import pytest
from browser_harness import Player, browser_session, next_frame, start_server, stop_server

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


def _open_editor_with_six_shores(page):
    page.click("#maps-btn")
    page.wait_for_selector("#map-editor-screen:not(.hidden)", timeout=5000)
    page.click("#editor-save-btn")
    page.wait_for_selector("#editor-save-popover:not(.hidden)", timeout=5000)
    page.wait_for_selector(
        "#editor-save-popover li:has-text('Six Shores')", timeout=8000
    )
    row = page.locator("#editor-save-popover li:has-text('Six Shores')").first
    row.locator("button:text-is('Load')").click()
    page.wait_for_timeout(500)
    # A built-in loads through duplicateMap(): a copy with id:'' — never saved.
    assert page.eval_on_selector("#editor-map-name", "el => el.value")
    if page.query_selector("#editor-save-popover:not(.hidden)"):
        page.keyboard.press("Escape")
    page.wait_for_timeout(200)


def test_preview_deals_a_board_before_the_map_is_saved(lobby):
    """Loading a built-in and pressing Preview — with no save in between —
    renders a dealt board. Before the fix the press bailed on the empty id and
    the status never gained its 'preview' marker."""
    alice, _ = lobby
    page = alice.page
    _open_editor_with_six_shores(page)

    page.click("#editor-preview-btn")
    # The server deals the map and returns it; the editor sets previewBoard and
    # the status strip gains a 'preview' segment (map-editor.js renderStatus).
    page.wait_for_function(
        "() => document.getElementById('editor-status')"
        ".textContent.includes('preview')",
        timeout=8000,
    )
    next_frame(page)
    status = page.eval_on_selector("#editor-status", "el => el.textContent")
    assert "preview" in status, status
