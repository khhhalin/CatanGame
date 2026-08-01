# Board Zoom & Pan — Implementation Plan

Research output, not yet implemented. Groundwork for custom maps (Seafarers-style
multi-island boards, 5–6 player boards) that will not fit on screen at a fixed scale.

## Recommendation: a camera matrix inside the 2D context

Keep the canvas sized to the **viewport** and apply a pan/zoom transform when drawing,
rather than making a huge canvas or CSS-scaling it.

- **Crispness** — vector paths re-rasterize every frame, so the board is sharp at any
  zoom. A large canvas that is CSS-scaled down is bitmap-resampled and soft.
- **Memory** — the buffer stays `viewport × dpr²` regardless of board size. Browsers cap
  canvas area, and **Safari caps it at 16,777,216 px (~4096×4096)** — a Seafarers board at
  the current hex radius and dpr 2 would exceed it. A camera makes board size irrelevant.
- **One coordinate convention** — `coding-rules.md` Part IV requires the renderer and the
  hit-tester to agree. A camera adds exactly one inverse in `clientToBoard()`; CSS scaling
  would require inverting two different transforms.

**The current code is already a degraded version of the "huge canvas" approach**:
`sizeCanvas()` sizes the canvas to the whole board and `#board-canvas { max-width: 100% }`
downscales it to fit. That is why the board softens on small windows today. The camera
fixes that as a side effect.

## The math

Camera state lives at module scope in `board-renderer.js`:

```js
const camera = { scale: 1, x: 0, y: 0 };
```

Forward, composed with the existing DPR transform:

```js
ctx.setTransform(dpr, 0, 0, dpr, 0, 0);   // sizeCanvas, unchanged
ctx.clearRect(0, 0, viewWidth, viewHeight);  // viewport, NOT layout size
ctx.save();
ctx.translate(camera.x, camera.y);
ctx.scale(camera.scale, camera.scale);
ctx.translate(offsetX, offsetY);          // existing line, now inside the camera
// ... existing draw calls unchanged ...
ctx.restore();
```

Inverse — the only change `clientToBoard()` needs:

```js
const cssX = (clientX - rect.left) * (canvas.width / rect.width) / dpr;
const cssY = (clientY - rect.top) * (canvas.height / rect.height) / dpr;
return { x: (cssX - camera.x) / camera.scale,
         y: (cssY - camera.y) / camera.scale };
```

Zoom-to-cursor — the board point under the pointer must not move:

```js
camera.x = cssX - (cssX - camera.x) * (next / camera.scale);
camera.y = cssY - (cssY - camera.y) * (next / camera.scale);
camera.scale = next;
```

Because `findNearest*` already work in board space, they need **no coordinate change** —
only a tolerance fix, so the click target stays constant on screen:

```js
const radius = BOARD_CONFIG.clickRadius / camera.scale;   // vertices and edges
```

## Gestures

- **Wheel**: normalize `deltaMode` (Firefox reports lines, Edge reports a flat 100), cap
  outliers, and register with `{ passive: false }` — otherwise `preventDefault()` is a
  no-op and the *page* zooms instead of the board.
- **Trackpad pinch arrives as `ctrl+wheel`** — there is no separate pinch event. Use a
  larger multiplier for it.
- **Drag to pan** composes with the existing 10px/700ms tap threshold: past the threshold
  the gesture becomes a pan and must not also place a settlement. Add an explicit
  `panning` flag, because a slow pan ending near its start would otherwise still count as
  a tap.
- **Two-finger pinch** via a `Map` of cached pointers (the existing single
  `pointerDownState` cannot represent two fingers).
- `touch-action: none` on the canvas is already correct. Add `overscroll-behavior: contain`
  on `.game-board` so an edge pan cannot trigger pull-to-refresh.

## Clamping

Centre the board on any axis where it is smaller than the viewport; otherwise stop it
before the last hex leaves the screen. `fitToView()` on first board and on board
replacement, but **not** on window resize — a resize should not yank the player's view.

## Performance

Do **culling** first (cheap and exact): compute the visible board rect once per frame into
a module-scope object (no per-frame allocation) and skip hexes outside it.

Defer pre-rendering: a raster blitted under a changing zoom reintroduces the bitmap-scaling
artifact the camera exists to avoid. The cheaper 80% is pre-rendering one tile *per terrain
type* and blitting it, which scales to any board size.

Pan/zoom will be the first time this app renders at 60fps, so cache
`getBoundingClientRect()` at gesture start rather than per `pointermove`.

## Risks

1. **Hit-test drift** — the highest risk. Geometry is computed in two places
   (`renderBoard` and `findNearest*`); adding the camera to only one puts every placement
   off by the pan offset. Mitigation: camera lives in one object, renderer applies it via
   `ctx`, `clientToBoard` inverts it, `findNearest*` never learn about it.
2. **DPR** — all camera values are CSS pixels, never buffer pixels. Mixing them makes
   zoom-to-cursor drift by a factor of `dpr` on retina only, invisible on a 1× machine.
3. **The `max-width`/`max-height` removal is load-bearing today** — it must land in the
   same commit as viewport sizing, or the canvas overflows its container.
4. **Line widths and fonts scale with the camera** — `lineWidth: 2` at 0.3× is a hairline
   and number tokens become unreadable. If they must stay legible, divide by scale, but
   precompute the font string on camera change rather than per token.
5. Omitting `{ passive: false }` looks like "zoom doesn't work" but is actually "the whole
   page zoomed".

## Order

- **Step 0** (ships alone, no interaction change): viewport-sized canvas, camera at fit
  scale, `renderBoard` wraps the draw, `clientToBoard` gains the inverse, tolerance
  divided by scale. Visually identical to today but crisper, and the whole coordinate
  pipeline becomes camera-aware and verifiable.
- **Step 1**: wheel zoom with zoom-to-cursor and clamping.
- **Step 2**: drag-to-pan integrated with the tap threshold.
- **Step 3**: +/−/fit buttons, keyboard (`+`/`-`/`0`/arrows), zoom level in the `aria-label`.
- **Step 4**: two-finger pinch (needs a touch device to test, so it blocks nothing).
- **Step 5**: culling, once boards actually exceed the viewport.
- **Step 6**: pre-rendered terrain tiles, only if profiling demands it.
