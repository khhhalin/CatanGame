"""Map editor: the Maps button opens the editor and the canvas paints real pixels.

Both bugs this suite would catch are invisible to the unit suite:

  - the Maps button not appearing or not opening the screen
    (server state is untouched, so every socket test passes);
  - the editor canvas being blank
    (a blank canvas satisfies every DOM selector — only a pixel count catches it).

Run: pytest tests/test_browser_map_editor.py -m slow -v
"""

import os

import pytest
from browser_harness import (
    Player,
    browser_session,
    next_frame,
    start_server,
    stop_server,
)

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

SHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test-artifacts", "ui", "map-editor",
)


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


_EDITOR_CANVAS_PIXELS = """
() => {
    const canvas = document.getElementById('editor-canvas');
    if (!canvas || !canvas.width) { return 0; }
    const data = canvas.getContext('2d')
        .getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let i = 3; i < data.length; i += 4) {
        if (data[i] !== 0) { count++; }
    }
    return count;
}
"""


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture
def lobby(browser, tmp_path):
    """Two players in the lobby — enough to have someone click Maps."""
    proc, url = start_server(tmp_path)
    alice = Player(browser, url, "Alice", viewport=VIEWPORT)
    bob = Player(browser, url, "Bob", viewport=VIEWPORT)
    alice.join()
    bob.join()
    yield alice, bob
    stop_server(proc)


class TestMapsButtonOpensEditor:
    """The Maps button is present in the lobby and opens the editor screen."""

    def test_maps_button_is_visible_in_lobby(self, lobby):
        alice, _ = lobby
        btn = alice.page.query_selector("#maps-btn")
        assert btn is not None, "#maps-btn is missing from the DOM"
        assert btn.is_visible(), "#maps-btn exists but is not visible"

    def test_maps_button_opens_editor_screen(self, lobby):
        """Clicking Maps hides the lobby and shows the editor screen.

        Regression target: if enterEditor() is never called, or the screen
        toggle is broken, #map-editor-screen stays hidden and the player sees
        nothing at all — which the unit suite cannot catch because it never
        touches DOM visibility.
        """
        alice, _ = lobby
        alice.page.click("#maps-btn")
        alice.page.wait_for_selector(
            "#map-editor-screen:not(.hidden)", timeout=5000
        )
        assert alice.page.query_selector("#user-screen.hidden") is not None, (
            "lobby screen is still visible after Maps was clicked"
        )

    def test_editor_canvas_paints_real_pixels(self, lobby):
        """The editor canvas renders a frame of hexes, not a blank rectangle.

        A blank canvas satisfies every DOM assertion. Counting pixels is the
        only honest check that BoardRenderer actually drew something.
        """
        alice, _ = lobby
        # If the previous test already opened the editor, we are already there.
        # If not (tests run independently), click Maps first.
        if alice.page.query_selector("#map-editor-screen.hidden") is not None:
            alice.page.click("#maps-btn")
            alice.page.wait_for_selector(
                "#map-editor-screen:not(.hidden)", timeout=5000
            )

        # Wait for the renderer to paint at least one frame.
        alice.page.wait_for_function(
            f"() => ({_EDITOR_CANVAS_PIXELS.strip()})() > 1000",
            timeout=8000,
        )
        next_frame(alice.page)
        pixel_count = alice.page.evaluate(_EDITOR_CANVAS_PIXELS)
        shot(alice, "editor-01-canvas-painted")
        assert pixel_count > 1000, (
            f"editor canvas has only {pixel_count} painted pixels — "
            "BoardRenderer did not draw anything"
        )

    def test_done_button_returns_to_lobby(self, lobby):
        """Done closes the editor and reveals the lobby again.

        If exitEditor() is broken the player is stuck in the editor with no
        way back, which the server cannot detect.
        """
        alice, _ = lobby
        # Ensure we are in the editor.
        if alice.page.query_selector("#map-editor-screen.hidden") is not None:
            alice.page.click("#maps-btn")
            alice.page.wait_for_selector(
                "#map-editor-screen:not(.hidden)", timeout=5000
            )

        alice.page.click("#editor-done-btn")
        alice.page.wait_for_selector("#user-screen:not(.hidden)", timeout=5000)
        assert alice.page.query_selector("#map-editor-screen.hidden") is not None, (
            "editor screen is still visible after Done was clicked"
        )
        assert alice.noisy_errors() == [], alice.noisy_errors()
