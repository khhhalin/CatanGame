"""Duplicating a scenario and saving keeps its per-hex meta, in a real browser.

Regression: HexMeta carries docks, village, lair, fishing_ground and oil_spring,
but the editor's `metaToWire` serialised only docks + village (and
`serverMapToDoc` read only those two, and `pruneHexMeta` judged an entry empty by
those two alone). So loading a built-in scenario like The Fishermen of Catan and
saving the copy silently dropped every fishing ground — the derived map was no
longer the scenario. The check is end-to-end: drive the editor, then read the
JSON the server actually wrote to disk.

Run: pytest tests/test_browser_map_meta_roundtrip.py -m slow -v
"""

import glob
import json
import os

import pytest
from browser_harness import Player, browser_session, start_server, stop_server

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}


@pytest.fixture(scope="module")
def browser():
    with browser_session() as instance:
        yield instance


@pytest.fixture
def server_dir(tmp_path):
    return tmp_path


@pytest.fixture
def lobby(browser, server_dir):
    proc, url = start_server(server_dir)
    alice = Player(browser, url, "Alice", viewport=VIEWPORT)
    bob = Player(browser, url, "Bob", viewport=VIEWPORT)
    alice.join()
    bob.join()
    yield alice, bob
    stop_server(proc)


def test_duplicating_a_scenario_preserves_its_per_hex_meta(lobby, server_dir):
    alice, _ = lobby
    page = alice.page

    page.click("#maps-btn")
    page.wait_for_selector("#map-editor-screen:not(.hidden)", timeout=5000)

    # Load The Fishermen of Catan (a fixed-pool scenario whose meta carries
    # fishing grounds), which arrives as an editable copy.
    page.click("#editor-save-btn")
    page.wait_for_selector(
        "#editor-save-popover li:has-text('Fishermen')", timeout=8000
    )
    page.locator(
        "#editor-save-popover li:has-text('Fishermen')"
    ).first.locator("button:text-is('Load')").click()
    page.wait_for_timeout(500)

    # Save the copy, then read what the server wrote.
    page.click("#editor-save-btn")
    page.wait_for_selector("#editor-save-popover:not(.hidden)", timeout=5000)
    page.click("#editor-save-confirm-btn")
    page.wait_for_timeout(800)

    files = glob.glob(os.path.join(str(server_dir), "maps", "*.json"))
    assert files, f"no custom map written under {server_dir}/maps"
    saved = json.load(open(files[0]))
    metas = [
        entry
        for region in saved["regions"]
        for entry in (region.get("meta") or {}).values()
    ]
    grounds = [m for m in metas if "fishing_ground" in m]
    assert grounds, f"fishing grounds were stripped on save: {saved}"


def test_duplicating_a_fixed_pool_keeps_its_placed_terrains_selectable(lobby):
    """A fixed-pool scenario places terrains beyond the six base lands (The
    Fishermen of Catan puts a `lake` at the centre). Duplicating it must keep
    those terrains offered in a hex's Tile dropdown — else the placed tile shows
    blank and editing that hex drops it. Before the fix duplicateMap derived the
    region's resources from its (empty) terrain map, yielding base lands only."""
    alice, _ = lobby
    page = alice.page

    page.click("#maps-btn")
    page.wait_for_selector("#map-editor-screen:not(.hidden)", timeout=5000)
    page.click("#editor-save-btn")
    page.wait_for_selector(
        "#editor-save-popover li:has-text('Fishermen')", timeout=8000
    )
    page.locator(
        "#editor-save-popover li:has-text('Fishermen')"
    ).first.locator("button:text-is('Load')").click()
    page.wait_for_timeout(500)
    if page.query_selector("#editor-save-popover:not(.hidden)"):
        page.keyboard.press("Escape")

    # Inspect the centre hex — the lake at 0,0,0.
    page.click("#editor-inspect-btn")
    box = page.evaluate(
        "() => { const r = document.getElementById('editor-canvas')"
        ".getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; }"
    )
    page.mouse.click(box["x"], box["y"])
    page.wait_for_selector("#editor-inspect-popover:not(.hidden)", timeout=5000)

    options = page.eval_on_selector_all(
        "#editor-inspect-popover select option", "els => els.map(o => o.value)"
    )
    assert "lake" in options, f"placed 'lake' terrain not selectable: {options}"
