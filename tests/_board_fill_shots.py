"""Screenshot the board and report how much of its pane it fills.

Not a test — a scratch driver used to see the layout padding change by eye and
by number. Run:
    ./.venv/bin/python tests/_board_fill_shots.py after
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from browser_harness import (  # noqa: E402
    Player,
    launch_browser,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "test-artifacts", "ui", "choices")

MEASURE = """
() => {
    const canvas = document.getElementById('board-canvas');
    const layout = window.BoardRenderer.computeLayout(window.__catanDebug.getBoard());
    const rect = canvas.getBoundingClientRect();
    const scale = window.BoardRenderer.getScale();

    // Where the drawn board actually starts and stops, in device pixels.
    const ctx = canvas.getContext('2d');
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let minX = canvas.width, maxX = -1, minY = canvas.height, maxY = -1;
    for (let y = 0; y < canvas.height; y += 1) {
        for (let x = 0; x < canvas.width; x += 1) {
            if (data[(y * canvas.width + x) * 4 + 3] > 8) {
                if (x < minX) { minX = x; }
                if (x > maxX) { maxX = x; }
                if (y < minY) { minY = y; }
                if (y > maxY) { maxY = y; }
            }
        }
    }
    return {
        layoutWidth: Math.round(layout.width),
        layoutHeight: Math.round(layout.height),
        offsetX: Math.round(layout.offsetX),
        offsetY: Math.round(layout.offsetY),
        scale: Number(scale.toFixed(3)),
        paneWidth: Math.round(rect.width),
        paneHeight: Math.round(rect.height),
        inkWidth: maxX - minX + 1,
        inkHeight: maxY - minY + 1,
        bufferWidth: canvas.width,
        bufferHeight: canvas.height,
    };
}
"""


def main(label):
    os.makedirs(OUT, exist_ok=True)
    import tempfile

    with tempfile.TemporaryDirectory() as data_dir, sync_playwright() as playwright:
        browser = launch_browser(playwright)
        proc, url = start_server(data_dir, seed=20260803)
        try:
            tabs = []
            for name in ("Ann", "Ben"):
                player = Player(browser, url, name,
                                viewport={"width": 1920, "height": 1080})
                player.join()
                tabs.append(player)
            tabs[0].page.click("#start-game-btn")
            for player in tabs:
                player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
            tabs[0].page.wait_for_timeout(1500)

            print(label, tabs[0].page.evaluate(MEASURE))
            tabs[0].page.screenshot(
                path=os.path.join(OUT, f"board-{label}-1920x1080.png"), full_page=False
            )
        finally:
            stop_server(proc)
            browser.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "after")
