# `server/static/js/board-renderer.js` — LEAVE ALONE

2252 lines, 80 KB. The largest file in the repository, and the wrong target.

## 1. Why it is not contended

Window: `--since='2026-08-03 00:00'`, 135 commits.

- **5 distinct work-scopes**: `board`, `feat`, `render`, `ui`, and one commit
  titled "Drop the findNearest\* tie-breaker now that edges are unique".
- **7 commits.**
- **1 adjacent cross-scope pair under 45 minutes** — against `panels.js`'s five
  and `game.py`'s ten.
- It does not appear in the top 25 co-change pairs at all. Nothing routinely
  changes with it.

Twice the size of `panels.js`, half the scopes, one fifth the interleaving. In
three days of heavy parallel work it was the source of essentially no queueing.

This file is the single best illustration of why this audit ranked by measured
contention rather than by `wc -l`. Ranked by size it would be first. Ranked by
the thing that actually costs throughput it is nowhere.

## 2. Why splitting it would be actively harmful

**It is a classic script, not an ES module.** `index.html` loads it as
`<script src=…>` before the module entry point, and it ends with:

```js
window.BoardRenderer = { … };
```

`board.js`, `choices.js` and `placement.js` reach it through that global
precisely because a classic script cannot import from modules. That is a
deliberate arrangement, and it means there are exactly two ways to split it,
both bad:

1. **More `<script>` tags.** Every top-level `const` in this file — and there
   are roughly sixty (`BOARD_CONFIG`, `PALETTE_TOKENS`, `GHOST_RING_RADIUS`,
   `TEXTURE_INK`, `FOREST_TREES`, `BRICK_COURSES`, `WALL_RADIUS`,
   `KNIGHT_OFFSET`, `HARBOUR_REACH`, …) currently lives in the *global* scope,
   because classic scripts have no module scope. Splitting into several tagged
   files does not isolate them; it spreads the same global namespace across
   more files, adds a hard load-order dependency between them, and makes a
   name collision with any future script a silent redefinition. This is a
   strictly worse version of the problem `constants.js` was created to solve.
2. **Convert it to a module.** That breaks `window.BoardRenderer` timing. Module
   scripts are deferred; `window.BoardRenderer` would be assigned after the
   parser finishes rather than before `main.js` runs, and — more importantly —
   the browser suite calls `window.BoardRenderer.render(…)`,
   `window.BoardRenderer.computeLayout(…)`, `window.BoardRenderer.clientToBoard(…)`
   and `window.BoardRenderer.findNearest*(…)` from `page.evaluate` in
   `tests/_visual_shots.py`, `tests/_board_fill_shots.py`,
   `tests/test_browser_firefox.py` and `placement.js`. A conversion is a change
   to a documented public surface dressed up as a refactor.

**It is also not really six concerns; it is one.** The file is a sprite library:
`cubeToPixel`, `drawHex`, `hexPath`, `drawTerrainTexture`, `drawConifer`,
`drawResourceGlyph`, `drawNumberToken`, `drawVertex`, `drawEdge`, `drawHarbour`,
`drawSettlement`, `drawCity`, `drawCityWall`, `drawKnight` — each a pure canvas
routine sitting immediately below the tuned constants it consumes
(`WALL_RADIUS = 15.5  // corners; kept clear of the city's 16px footprint`).
Those constants are meaningless away from their function. Separating them is how
a 15.5 drifts to 16 and the walls stop clearing the city.

## 3. If it ever does become contended

The measurement, not the size, should trigger the work. Re-run:

```bash
git log --since='<date>' --format='MARK|%s' --name-only \
  -- server/static/js/board-renderer.js
```

and if the scope count approaches `panels.js`'s eleven, the only split worth
considering is **`board-camera.js`** — `cubeToPixel`, `parseKey`,
`computeLayout`, `clientToBoard`, `boardToClient`, `findNearestVertex`,
`findNearestEdge`, `findNearestHex`. Those are the geometry functions with no
canvas state, they are what `placement.js` and `choices.js` actually use, and
they are the only part of `window.BoardRenderer` that has an existence
independent of drawing.

Even then: **arming a build mode must not change the canvas box or the camera**
(`test_browser_layout.py::test_arming_or_disabling_a_build_button_never_resizes_it`,
and `test_an_open_popover_does_not_move_the_board`). Any change to the camera
functions has to be verified against those two tests specifically, and against
the screenshot suites in `tests/_visual_shots.py` and `tests/_board_fill_shots.py`,
which are pixel-counting and will catch a half-pixel shift.

## 4. How much parallelism a split would buy

Roughly none. Seven commits from five scopes in three days, one of which was a
tie-breaker deletion. There is no second agent waiting for this file.

**Recommendation: leave it alone. Spend the churn budget on `panels.js`, which
is 40% its size and had eleven scopes fighting over it.**
</content>
