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

    def test_region_popover_fits_in_viewport(self, lobby):
        """Clicking a region gear opens the region popover inside the viewport.

        Regression target: the original pool popover stacked 17 rows in a
        single column, pushing Auto-fill / Done off the bottom of the screen.
        The region popover uses a scrollable body with terrain+token columns
        side by side so it stays within its max-height cap on any viewport.
        """
        alice, _ = lobby
        if alice.page.query_selector("#map-editor-screen.hidden") is not None:
            alice.page.click("#maps-btn")
            alice.page.wait_for_selector(
                "#map-editor-screen:not(.hidden)", timeout=5000
            )

        # Click the gear of the first region in the sidebar.
        alice.page.click("#editor-region-list .editor-region-gear")
        alice.page.wait_for_selector(
            "#editor-region-popover:not(.hidden)", timeout=5000
        )

        popover_bottom = alice.page.evaluate(
            "() => document.getElementById('editor-region-popover')"
            "         .getBoundingClientRect().bottom"
        )
        viewport_height = alice.page.evaluate("() => window.innerHeight")
        shot(alice, "editor-02-region-popover")
        assert popover_bottom <= viewport_height, (
            f"region popover bottom ({popover_bottom:.0f}px) is below the viewport "
            f"({viewport_height}px) — Auto-fill and Done are unreachable"
        )

        # Close so later tests start clean
        alice.page.keyboard.press("Escape")

    def test_resources_download_link_is_present_and_wired(self, lobby):
        """The editor toolbar's `Resources ↓` link downloads the registry.

        If the link is missing, or its href does not resolve to the registry
        route, the player has no way to get the file the whole feature exists to
        hand them. The DOM assertion catches a missing/misplaced button; fetching
        the href and parsing it proves the route behind it actually serves the
        registry (a JSON object keyed by resource id).
        """
        alice, _ = lobby
        if alice.page.query_selector("#map-editor-screen.hidden") is not None:
            alice.page.click("#maps-btn")
            alice.page.wait_for_selector(
                "#map-editor-screen:not(.hidden)", timeout=5000
            )

        link = alice.page.query_selector("#editor-resources-btn")
        assert link is not None and link.is_visible(), (
            "the Resources download link is not visible in the editor toolbar"
        )
        shot(alice, "editor-03-resources-link")

        body = alice.page.evaluate(
            "async (href) => { const r = await fetch(href); "
            "return { ok: r.ok, text: await r.text() }; }",
            link.get_attribute("href"),
        )
        assert body["ok"], "the resources link did not resolve"
        import json
        registry = json.loads(body["text"])
        assert "wood" in registry and "color" in registry["wood"], (
            f"the downloaded file is not the resource registry: {body['text'][:120]}"
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


class TestV2Authoring:
    """The Explorers & Pirates authoring controls the editor grew: a per-region
    deal mode, the gold/fish/spice terrains, and a per-hex Inspect popover for
    docks and villages.

    The wire shape these produce is pinned server-side by
    tests/game/test_map_editor_wire.py; what only a browser can show is that the
    controls render, react, and raise no JavaScript error — a broken v2 branch
    would take the whole editor module down with it.
    """

    def _open_editor(self, player):
        if player.page.query_selector("#map-editor-screen.hidden") is not None:
            player.page.click("#maps-btn")
            player.page.wait_for_selector(
                "#map-editor-screen:not(.hidden)", timeout=5000
            )

    def _open_region_popover(self, player):
        player.page.click("#editor-region-list .editor-region-gear")
        player.page.wait_for_selector(
            "#editor-region-popover:not(.hidden)", timeout=5000
        )

    def test_deal_mode_selector_offers_the_v2_modes(self, lobby):
        alice, _ = lobby
        self._open_editor(alice)
        self._open_region_popover(alice)

        deal = alice.page.locator(
            "#editor-region-popover select:has(option[value='hidden'])"
        )
        assert deal.count() == 1, "the Deal mode selector is missing"
        for mode in ("shuffled", "hidden", "fixed"):
            assert deal.locator(f"option[value='{mode}']").count() == 1, (
                f"the Deal selector has no '{mode}' option"
            )
        # Selecting hidden rebuilds the popover without error.
        deal.select_option("hidden")
        alice.page.wait_for_selector(
            "#editor-region-popover:not(.hidden)", timeout=5000
        )
        alice.page.keyboard.press("Escape")
        assert alice.noisy_errors() == [], alice.noisy_errors()

    def test_ep_terrains_are_offered_in_the_resource_grid(self, lobby):
        alice, _ = lobby
        self._open_editor(alice)
        self._open_region_popover(alice)

        for terrain in ("gold", "fish", "spice"):
            check = alice.page.locator(
                "#editor-region-popover .editor-resource-check", has_text=terrain
            )
            assert check.count() >= 1, f"'{terrain}' is not offered as a pool terrain"

        # Enabling gold gives it a terrain-pool counter row, without error.
        alice.page.locator(
            "#editor-region-popover .editor-resource-check", has_text="gold"
        ).locator("input").check()
        alice.page.wait_for_timeout(100)
        alice.page.keyboard.press("Escape")
        assert alice.noisy_errors() == [], alice.noisy_errors()

    def test_inspect_a_hex_opens_the_docks_and_village_popover(self, lobby):
        alice, _ = lobby
        self._open_editor(alice)

        # Inspect mode, then click the middle of the canvas — the centre hex.
        alice.page.click("#editor-inspect-btn")
        box = alice.page.evaluate(
            "() => { const r = document.getElementById('editor-canvas')"
            ".getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; }"
        )
        alice.page.mouse.click(box["x"], box["y"])

        alice.page.wait_for_selector(
            "#editor-inspect-popover:not(.hidden)", timeout=5000
        )
        popover = alice.page.locator("#editor-inspect-popover")
        assert popover.get_by_text("Docks", exact=False).count() >= 1, (
            "the Inspect popover has no docks section"
        )
        # Six dock sides plus the village toggle are all checkboxes.
        checks = popover.locator("input[type='checkbox']")
        assert checks.count() >= 7, (
            f"expected 6 dock sides + a village toggle, found {checks.count()}"
        )
        # Toggling a dock writes state without error.
        checks.first.check()
        shot(alice, "editor-03-inspect-docks")
        alice.page.keyboard.press("Escape")
        assert alice.noisy_errors() == [], alice.noisy_errors()
