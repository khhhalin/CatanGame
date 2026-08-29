"""Pool edits: the problem badge counts tokens, and an edit drops a preview.

Two regressions the editor shipped with:

- `regionHasProblem` compared only tile count to hex count, never the token
  count, so a region with the right number of tiles but the wrong number of
  number-tokens showed no '!' badge and slipped past the pre-preview auto-fill
  prompt — Preview then failed with a raw server TOKEN_COUNT rejection. The
  status strip already counted it as a pool problem, so the two disagreed.
- The module header promises "Any edit after that clears previewBoard and
  returns to the authored view", but pool and harbour counters mutated the
  document without clearing the dealt board, leaving a preview on screen that no
  longer matched the map.

Run: pytest tests/test_browser_map_pool_edits.py -m slow -v
"""

import pytest
from browser_harness import Player, browser_session, next_frame, start_server, stop_server

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}
TOKEN_PLUS = (
    "#editor-region-popover .editor-pool-section:"
    "has(.editor-pool-section-head:text-is('Token pool')) button:text-is('+')"
)


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


def _editor_with_six_shores(page):
    page.click("#maps-btn")
    page.wait_for_selector("#map-editor-screen:not(.hidden)", timeout=5000)
    page.click("#editor-save-btn")
    page.wait_for_selector(
        "#editor-save-popover li:has-text('Six Shores')", timeout=8000
    )
    page.locator(
        "#editor-save-popover li:has-text('Six Shores')"
    ).first.locator("button:text-is('Load')").click()
    page.wait_for_timeout(500)
    if page.query_selector("#editor-save-popover:not(.hidden)"):
        page.keyboard.press("Escape")
    page.wait_for_timeout(200)


def _add_a_token_to_the_first_region(page):
    # The first region item is the mainland (explicit hexes, so it can flag a
    # problem — a 'remaining' region never does).
    first = page.locator("#editor-region-list .editor-region-item").first
    first.locator(".editor-region-gear").click()
    page.wait_for_selector("#editor-region-popover:not(.hidden)", timeout=5000)
    page.locator(TOKEN_PLUS).first.click()
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)


def test_a_token_only_mismatch_flags_the_region(lobby):
    """One extra token, tiles untouched: the region gains its '!' badge. Before
    the fix regionHasProblem ignored tokens, so no badge appeared."""
    alice, _ = lobby
    page = alice.page
    _editor_with_six_shores(page)
    assert page.query_selector(".editor-region-warn") is None, "clean map already flagged"

    _add_a_token_to_the_first_region(page)
    # Force a sidebar re-render the way a normal click would, then check.
    page.locator("#editor-region-list .editor-region-item").first.click()
    page.wait_for_selector(".editor-region-item .editor-region-warn", timeout=3000)
    assert page.query_selector(".editor-region-warn") is not None


def test_editing_a_pool_after_preview_returns_to_authored_view(lobby):
    """Preview, then bump a token: the dealt board is dropped (status loses its
    'preview' marker). Before the fix the stale preview stayed on screen."""
    alice, _ = lobby
    page = alice.page
    _editor_with_six_shores(page)

    page.click("#editor-preview-btn")
    page.wait_for_function(
        "() => document.getElementById('editor-status')"
        ".textContent.includes('preview')",
        timeout=8000,
    )
    _add_a_token_to_the_first_region(page)
    next_frame(page)
    status = page.eval_on_selector("#editor-status", "el => el.textContent")
    assert "preview" not in status, status
