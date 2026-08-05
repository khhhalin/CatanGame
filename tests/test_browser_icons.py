"""The icon sprite resolves every id the icon module hands out.

The foundation for the emoji-to-SVG conversion is a sprite of <symbol>s in
index.html and an icons.js that maps game concepts onto their ids. Five panels
will render `<use href="#i-...">` against that sprite. If the module offers an
id the sprite does not define, the <use> resolves to nothing: the panel's DOM
assertion still passes over an empty box, and a player sees a blank where a
resource or an award should be - the same class of bug as the blank canvas.

So this drives the real page and checks two things a player would notice:
  - every id icons.js exports (SPRITE_IDS) has a <symbol> in the sprite, and
  - each one renders a non-zero box when actually <use>d.

The list is read from the module, never copied here: a symbol the module names
but the sprite forgets must fail this, and a copied literal would hide exactly
that drift (CLAUDE.md, "assert the literal against what it has to match").
"""

import pytest
from browser_harness import Player, browser_session, start_server, stop_server

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1200, "height": 800}


def test_the_sprite_defines_and_paints_every_id_the_module_exports(tmp_path):
    proc, url = start_server(tmp_path)
    try:
        with browser_session() as browser:
            player = Player(browser, url, "Ann", viewport=VIEWPORT)

            # The ids the module actually hands to panels, read from the module.
            sprite_ids = player.page.evaluate(
                "async () => (await import('/static/js/icons.js')).SPRITE_IDS"
            )
            assert sprite_ids, "icons.js exported no SPRITE_IDS"

            # The ids the sprite in index.html actually defines.
            defined = player.page.evaluate(
                "() => Array.from(document.querySelectorAll('svg symbol[id]'))"
                "        .map(s => s.id)"
            )
            missing = [i for i in sprite_ids if i not in defined]
            assert not missing, (
                f"icons.js names these ids but the sprite has no <symbol>: {missing}"
            )

            # Each id, actually <use>d, renders a non-zero box. A broken href
            # paints nothing and getBBox comes back empty.
            boxes = player.page.evaluate(
                """(ids) => {
                    const svgNS = 'http://www.w3.org/2000/svg';
                    const results = {};
                    for (const id of ids) {
                        const svg = document.createElementNS(svgNS, 'svg');
                        svg.setAttribute('width', '24');
                        svg.setAttribute('height', '24');
                        svg.setAttribute('viewBox', '0 0 24 24');
                        const use = document.createElementNS(svgNS, 'use');
                        use.setAttribute('href', '#' + id);
                        svg.appendChild(use);
                        document.body.appendChild(svg);
                        const box = use.getBBox();
                        results[id] = box.width * box.height;
                        svg.remove();
                    }
                    return results;
                }""",
                sprite_ids,
            )
            empty = [i for i, area in boxes.items() if not area]
            assert not empty, f"these ids resolve to an empty box: {empty}"
    finally:
        stop_server(proc)
