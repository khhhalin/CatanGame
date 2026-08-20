# Design brief — Catan web game restyle

A reference kit for finding a new look in **Claude Design** (claude.ai/design).
Feed the design agent this brief + the screenshots in `screens/` + the paste-ready
`snapshot/game-screen.html`, then iterate on a new visual direction. The look you
land on gets translated back into the real app — see **How the restyle lands**.

---

## What this is

A multiplayer Settlers-of-Catan web game. Server-rendered HTML (Flask), vanilla
JS, an HTML5 **canvas** for the board, one CSS token file driving everything.
Three surfaces, all in the kit:

| Surface | Screens | What it is |
|---|---|---|
| **Lobby** | `lobby-light.png`, `lobby-dark.png` | Player/observer roster, house-rules picker (presets + a long expansion rule list), chat panel, Maps + Start buttons. |
| **In-game** | `game-light.png`, `game-dark.png` | The heart of it: a full-width hex board with **floating** UI over it — players top-left, physical hand of cards bottom-centre, build+trade tray bottom-left, dice tray bottom-right — plus a right panel (game log, bank, titles, costs, house rules). |
| **Map editor** | `map-editor-light.png`, `map-editor-dark.png` | Region sidebar, paint/inspect toolbar, an editable ocean grid, Clear/Preview/Save/Done. Newest surface, least polished. |

The **snapshot** (`snapshot/game-screen.html`) is the in-game screen as one
self-contained file: real DOM, real CSS inlined, the board canvas rasterised to an
image. It renders standalone — paste it into Claude Design as the starting point to
restyle, or use it to pull exact spacing/structure.

---

## Current identity — what we're moving away from (or refining)

**"Warm parchment + Catan orange."** Warm off-white neutrals, a darkened Catan
orange accent, resource-coloured accents, full light **and** dark themes. Every
text colour is WCAG-AA-checked on its surface. It's competent but a bit flat and
paper-y; the map editor in particular feels unfinished next to the rest.

The whole system lives in **one file** (`tokens.css`, ~90 semantic tokens). The
new look is primarily *new values for these tokens* — so the vocabulary below is
the palette the redesign should speak in.

### Palette (light theme — dark is the mirror)

**Neutrals / surfaces**
- `--bg #f4f0e9`, `--bg-sunken #e7dfd0`
- `--surface-1 #fdfbf7` (cards), `--surface-2 #f8f4ec`, `--surface-3 #eee8da`
- `--border #ddd2bf`, `--border-strong #b8ab93`
- hairlines: `--hairline #e6ddcd`, `--hairline-soft #efe8db`, `--surface-quiet #f0ebe1` (quiet fills — rail, tray, must not read as a boxed panel)

**Text** — `--text #221d17`, `--text-muted #5c5142` (7.5:1), `--text-faint #6a5d4b` (4.8:1)

**Accent** — `--accent #b5551a` (darkened Catan orange, AA on white), `--accent-hover #91410f`, `--accent-soft #fbeade`, `--on-accent #fff`

**Status** — info `#1a5fb4`, good `#1a6b3c`, warn `#8a5a00`, bad `#a52222` (each with a `-soft` tint + white `--on-status`)

**Focus** — `--focus #0b57d0` + a 3px focus ring. Never removed; keyboard focus is visible by default.

**Resource identity** (used as panel text *and* as canvas harbour-badge fills — both directions must clear 4.5:1): wood `#2f6b3a`, brick `#a4502a`, sheep `#597925`, wheat `#8a6800`, ore `#4d5b6b`.

**Terrain fills** (board canvas, deliberately brighter/separate from resource text so big hexes don't look muddy): wood `#3f8f5a`, brick `#c9663a`, sheep `#8fbf4a`, wheat `#e0b64a`, ore `#8a9bb0`, desert `#e6d9bb`. Board backdrop `--board-backdrop #16110b` (same dark in both themes — the canvas paints its own ocean).

**Commodities** (C&K): cloth `#6d3f8f`, coin `#8a6a12`, paper `#146e73`.
**Player colours** 1–6 (pips + coloured names): `#a04a12 #144e96 #145a32 #75235a #654c0f #12545c`.
**Dice** — fixed ivory face `#f6f1e7` / near-black pips `#2c2318`, both themes.

### Type / spacing / shape
- Fonts: UI = `system-ui` stack; numbers = a monospace stack (`--font-num`).
- Type scale (rem): 2xs .6875 · xs .75 · sm .8125 · **md .9375 (body)** · lg 1.0625 · xl/2xl fluid `clamp()`. Body fixed on purpose; only headings fluid.
- Spacing: 4px base — `--space-1..7` = .25 .5 .75 1 1.5 2 3 rem. No raw px gaps.
- Radii: sm 4 · md 8 · lg 14 · pill 999px.
- Elevation: `--shadow-1/2/3` (subtle → modal).
- Z-index scale (one place, nothing invents a 9999): board-overlay 10 · sticky 20 · dropdown 30 · modal 40 · notice 50.
- Motion: `--dur-fast 90ms · med 180 · slow 320`, one easing curve; all filtered through a reduced-motion block.

---

## Hard constraints — the new look MUST honour these

1. **Two themes.** Every colour token is declared in three places (light `:root`, `prefers-color-scheme: dark`, and `[data-theme=dark]`). A new colour must exist in all three or the theme half-applies. Design *both* light and dark.
2. **WCAG AA on text.** All text/surface pairs clear 4.5:1 (large/UI 3:1). A browser test sweep (`test_every_visible_label_meets_wcag_aa`) fails the build if a label drops below AA. Resource + player colours do double duty (text *and* fills) and are pinned by contrast on **both** ends — don't pick pretty values that fail one side.
3. **The board is a canvas, painted by JS from the `--terrain-*` / resource / player tokens.** You can restyle its palette (change the tokens) but not its layout via CSS — hexes, number discs, harbour badges, roads, ships are drawn in `board-renderer.js`. Treat the board's *colours* as in-scope, its *geometry* as fixed.
4. **The floating in-game layout is load-bearing.** Players/hand/tray/dice float in a fixed overlay sized to the board. You can restyle these floats freely (fills, shadows, card look, spacing); moving them is a bigger structural change (flag it, don't assume it).
5. **Reduced-motion + visible focus** are non-negotiable (accessibility).
6. **No build step.** One CSS file, no preprocessor, no framework. The output is plain CSS custom properties + rules.

## What's flexible (go wild here)
Palette direction and mood; surface treatment (parchment → glass / flat / material / dark-first / high-contrast, anything); card and tile styling; button and chip design; type pairing (a display face for headings is fine); depth/shadow language; the map-editor chrome (most in need of love); iconography feel.

---

## How the restyle lands (so you design the right thing)

The change comes home primarily as **new `tokens.css` values** (recolour / retype /
respace once, everything moves together) **plus targeted component CSS** in
`style.css` where structure — not just colour — needs it (buttons, cards, panels,
the map-editor toolbar). Layout stays put unless we explicitly decide otherwise.

So the most useful thing to get out of Claude Design is: **a coherent token
palette (light + dark) and a component styling direction** — not a from-scratch
React app. Concretely, aim the exploration at producing (a) the new colour values
for the token names above, (b) a treatment for cards / buttons / panels / the
board chrome, in both themes.

---

## Kit contents
```
design-refkit/
  BRIEF.md                    ← this file
  screens/
    lobby-light.png    lobby-dark.png
    game-light.png     game-dark.png      ← the important one
    map-editor-light.png  map-editor-dark.png
  snapshot/
    game-screen.html          ← self-contained, paste-into-Claude-Design ready
```
Captured from live `main` (build `61e13b7`), 1600×1000, Chromium.
