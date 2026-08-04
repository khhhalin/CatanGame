"""Drive a real game and screenshot the board, for looking at by eye.

Not a test — a scratch driver used while working on board-renderer.js. Run:
    ./.venv/bin/python tests/_visual_shots.py before
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from browser_harness import (  # noqa: E402
    Player,
    browser_session,
    next_frame,
    start_server,
    stop_server,
    wait_for_board_painted,
    wait_for_rules,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "test-artifacts", "ui", "render")

VIEWPORTS = {"1920x1080": (1920, 1080), "1366x768": (1366, 768)}

# Two of each rank so basic/strong/mighty and active/inactive all appear.
FAKE_KNIGHTS = """
([owner, vertexKeys]) => {
    const board = window.__catanDebug.getBoard();
    if (!board.cities_knights) { return 0; }
    const ranks = [1, 1, 2, 2, 3, 3];
    board.cities_knights.knights[owner] = vertexKeys.slice(0, 6).map((v, i) => ({
        vertex: v, rank: ranks[i], active: i % 2 === 0, can_act: i % 2 === 0
    }));
    return board.cities_knights.knights[owner].length;
}
"""


CITIES_AND_KNIGHTS = {"commodities": True, "city_improvements": True, "metropolis": True,
     "knights": True, "barbarians": True, "city_walls": True,
     "progress_cards": True, "setup_second_city": True,
     "victory_target": 13}


def set_rules(player, rules):
    """Set lobby rules over the real socket.

    Not through the picker: the picker has no control for a choice rule yet,
    so the map cannot be selected by clicking at all.
    """
    player.page.evaluate(
        """async rules => {
            const socket = (await import('/static/js/socket.js')).socket;
            socket.emit('set_rules', { rules });
        }""",
        rules,
    )
    wait_for_rules(player, rules)


def shoot(browser, url, label, size, rules, theme=None, knights=False):
    os.makedirs(OUT, exist_ok=True)
    width, height = size
    alice = Player(browser, url, "Alice", viewport={"width": width, "height": height})
    bob = Player(browser, url, "Bob", viewport={"width": width, "height": height})
    alice.join()
    bob.join()
    if rules:
        set_rules(alice, rules)
    if theme:
        for player in (alice, bob):
            player.page.evaluate(
                "t => document.documentElement.setAttribute('data-theme', t)", theme
            )
    alice.page.click("#start-game-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    wait_for_board_painted(alice)

    if knights:
        board = alice.board()
        # Vertices with hex neighbours on all sides read best: they are inland,
        # so the knight is not half over the ocean in the screenshot.
        keys = sorted(board["vertices"].keys())[20:60:6]
        # Put buildings under two of them, which is the collision case.
        alice.page.evaluate(
            "([keys, owner]) => { const b = window.__catanDebug.getBoard();"
            "  b.vertices[keys[0]].building = {player: owner, type: 'settlement'};"
            "  b.vertices[keys[1]].building = {player: owner, type: 'city'}; }",
            [keys, "Alice"],
        )
        placed = alice.page.evaluate(FAKE_KNIGHTS, ["Alice", keys])
        print(f"  knights injected: {placed}")
        alice.page.evaluate(
            "() => { const c = document.getElementById('board-canvas');"
            "        window.BoardRenderer.render(window.__catanDebug.getBoard(),"
            "            'board-canvas', null, null); }"
        )
        next_frame(alice.page)

    path = os.path.join(OUT, f"{label}.png")
    alice.page.screenshot(path=path)
    print(f"  wrote {path}")

    counts = alice.page.evaluate(
        "() => { const b = window.__catanDebug.getBoard();"
        " return {edgePorts: Object.values(b.edges).filter(e => e.port).length,"
        "         vertexPorts: Object.values(b.vertices).filter(v => v.port).length}; }"
    )
    print(f"  ports: {counts}")
    for player in (alice, bob):
        player.page.close()
    return path


def data_dir(name):
    """A fresh directory per server: a reused one still holds the last run's
    roster, and the join is then refused as a duplicate name."""
    path = f"/tmp/catan-shots-{name}"
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path)
    return path


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "shot"
    with browser_session() as browser:
        for name, size in VIEWPORTS.items():
            proc, url = start_server(data_dir(f"{stage}-{name}"))
            try:
                shoot(browser, url, f"{stage}-base-{name}", size, {})
            finally:
                stop_server(proc)

            proc, url = start_server(data_dir(f"{stage}-ck-{name}"))
            try:
                shoot(browser, url, f"{stage}-ck-{name}", size,
                      CITIES_AND_KNIGHTS, knights=True)
            finally:
                stop_server(proc)

        proc, url = start_server(data_dir(f"{stage}-large"))
        try:
            shoot(browser, url, f"{stage}-large-1920x1080", (1920, 1080),
                  {"board_layout": "large"})
        finally:
            stop_server(proc)

        proc, url = start_server(data_dir(f"{stage}-dark"))
        try:
            shoot(browser, url, f"{stage}-dark-1920x1080", (1920, 1080), {},
                  theme="dark")
        finally:
            stop_server(proc)
        browser.close()


if __name__ == "__main__":
    main()
