# Map Creator — Design

Design document. No implementation. Written while `server/game/board.py`,
`server/game/rules.py` and the frontend are being changed by other agents, so
every plug point below is described as *one branch* or *one new module* rather
than a rewrite of code someone else is holding.

The goal, in the owner's words: define regions for landmass, oceans and
islands, and set the pool of tiles for each region.

The rulebook already blesses this. From `expansions.md`, Scenario: New World:

> Players may agree to adjust the randomly generated set-up if they are unhappy
> with it, and may freely design and play scenarios of their own.

And the same scenario describes exactly the mechanism this document builds:

> The board is created by shuffling all listed hexes face down and placing them
> face up at random within the assembled frame.
> Number tokens are shuffled and placed at random, one on each land hex, and no
> number tokens are placed on sea hexes.

A *region with a shuffled pool* is that paragraph turned into data.

---

## 0. What this buys you, and what it does not

Read this before the rest, because it changes what "done" means.

A map creator gives you: bigger and stranger boards, hand-chosen resource
mixes, hand-placed harbours, multi-island *geometry*, and a preview button. All
of that is a few hundred lines and is genuinely useful on its own — a 37-hex
board with a custom mix is playable today.

A map creator does **not** give you the Seafarers scenarios. "The Four
Islands", "Heading for New Shores" and "The Fog Island" each need machinery the
engine does not have:

| Scenario | Also needs |
|---|---|
| The Four Islands | ships, pirate, special VP chits, per-player home-island tracking |
| Heading for New Shores | ships, pirate, special VP, robber start depending on player count |
| The Fog Island | ships, pirate, lazy tile reveal on exploration, hidden server-side stack |

Ships are the big one. `_generate_vertices_and_edges` is called with land hexes
only (`board.py:161`), deliberately — "the ocean ring is scenery". Without
vertices and edges over water there is nowhere to put a ship, so **a
second island is unreachable**. The map format below is designed so those
scenarios drop in later without a format change, but v1 will let you *author*
a four-island map and refuse to *start* a game on it. Saying otherwise would be
dishonest about the cost: the map creator is maybe 20% of "we can play
Seafarers".

---

## 1. Data model

### 1.1 The three things a map is

1. **A frame.** How big the board is. One integer radius, in the existing
   scaled-cube metric (`max(|x/3|, |y/3|, |z/3|)`), matching `_is_valid_hex`.
2. **Regions.** A named set of hex coordinates, plus a kind, plus a pool.
   Regions partition the frame; every hex belongs to exactly one.
3. **Harbours.** Edge keys with types, or a set of edge keys plus a bag of
   types to shuffle over them.

### 1.2 Region kind is about *rules*, not about *terrain*

This is the design decision most likely to be got wrong, so it is stated up
front: **`kind` must not decide what tiles a region contains.** The pool decides
that. `kind` decides how the setup and scoring rules treat the region.

The reason is "Heading for New Shores", from `expansions.md`:

> Each time a player builds their first settlement on one of the small islands,
> that player receives two special victory points.

and the scenario's off-island area is a pool of terrain positions of which
*some are sea*. If `kind: "island"` forced land, that scenario would be
inexpressible. So a pool may legitimately contain `sea` entries, and the shape
of the islands is only known after the draw.

Which leads to the second decision: **the "island" that scores a special VP is
derived at runtime, not authored.** It is a connected component of land hexes,
found by flood fill after instantiation. A region is an *authoring* construct;
an island is a *derived* one. Authoring them as the same thing works for The
Four Islands and breaks immediately on New Shores.

`kind` values:

| kind | meaning |
|---|---|
| `main` | Land the scenario calls the main island. Starting settlements allowed. |
| `island` | Land that is foreign to everyone at setup. Starting settlements refused. Source of special VP later. |
| `sea` | Water. Ships and the pirate live here. Never takes a number token. |
| `fog` | Hexes hidden at setup, drawn lazily on exploration. v3. |

For v1 only `main` and `sea` are *playable*; `island` and `fog` parse,
validate and preview, but a game refuses to start on a map that uses them
(see §3, rule R12).

### 1.3 Pools

```
pool := {
  "mode":    "shuffled" | "fixed",
  "terrain": {terrain: count}   when shuffled
           | [terrain, ...]     when fixed, parallel to "hexes"
  "numbers": [int, ...]         a multiset of tokens, shuffled when mode=shuffled
}
```

Terrain vocabulary: `wood`, `brick`, `sheep`, `wheat`, `ore`, `desert`, `sea`,
and later `gold`. `sea` is the map-file word; the engine's `Hex.type` value
stays `"ocean"` (see §7, open question 1).

`numbers` is an explicit multiset rather than counts, because it reads better
and because a fixed pool needs positional order anyway. Its length must equal
the number of *token-requiring* tiles in the terrain pool — which is known
statically even for a shuffled pool, because the multiset is known even though
the placement is not. That is what makes rule R4 in §3 a static check rather
than a runtime surprise.

`mode: "fixed"` places tiles in the region's `hexes` order with no shuffling.
This is how you reproduce a printed scenario diagram exactly. Recommended for
v2, not v1 (§6).

### 1.4 Worked example

A small map: a 7-hex mainland, a 3-tile offshore position group of which one
tile is sea, one hand-placed harbour, everything else water. Frame radius 4.

```json
{
  "map_version": 1,
  "id": "little-shores",
  "name": "Little Shores",
  "author": "kalin",
  "notes": "Smallest map that exercises regions, a mixed pool and a harbour.",
  "frame": { "radius": 4 },
  "victory_target": 8,
  "robber_start": "auto",
  "regions": [
    {
      "id": "mainland",
      "kind": "main",
      "color": "#8bb26a",
      "hexes": [
        "0,0,0",
        "3,-3,0", "3,0,-3", "0,3,-3",
        "-3,3,0", "-3,0,3", "0,-3,3"
      ],
      "pool": {
        "mode": "shuffled",
        "terrain": { "wood": 2, "wheat": 2, "sheep": 1, "brick": 1, "desert": 1 },
        "numbers": [3, 4, 5, 6, 9, 10]
      }
    },
    {
      "id": "far-shore",
      "kind": "island",
      "color": "#c9a227",
      "hexes": ["9,-9,0", "9,-6,-3", "9,-3,-6"],
      "pool": {
        "mode": "shuffled",
        "terrain": { "ore": 1, "sheep": 1, "sea": 1 },
        "numbers": [8, 11]
      }
    },
    {
      "id": "ocean",
      "kind": "sea",
      "color": "#3b6ea5",
      "hexes": "remaining",
      "pool": { "mode": "shuffled", "terrain": { "sea": 51 }, "numbers": [] }
    }
  ],
  "harbours": {
    "mode": "fixed",
    "places": [
      { "edge": "4,-4,0", "type": "generic" }
    ]
  }
}
```

Notes on the example, each of which is a deliberate feature:

- `"hexes": "remaining"` — exactly one region per map may claim every hex
  inside the frame not claimed by another region. The ocean is always
  "everything else", and without this the ocean region in a radius-4 map is a
  51-entry array nobody will ever read. The parser expands it before anything
  else runs, so the rest of the pipeline only ever sees explicit lists.
- `far-shore` has three positions and a pool of three tiles, one of which is
  `sea`. After the draw the region may be a 2-hex island, or two 1-hex islands,
  or a 2-hex island plus water — decided by the shuffle. This is
  "Heading for New Shores" in miniature, and it is why islands are derived.
- `numbers` for `far-shore` has 2 entries for 2 token-requiring tiles (`ore`,
  `sheep`). `sea` takes none. `mainland` has 6 entries for 7 hexes because one
  is desert.
- The harbour edge `"4,-4,0"` is hex `3,-3,0` plus edge direction `(1,-1,0)`,
  which is the boundary between land hex `3,-3,0` and sea hex `6,-6,0`. Exactly
  one coordinate is divisible by 3, so it is a well-formed edge key per
  `hex.md`.
- `victory_target` per map, because `expansions.md` says every scenario sets its
  own, and offers a heuristic the editor should suggest: *"the victory point
  target equals the number of terrain hexes minus the deserts, divided by two."*

Shuffled harbours, per `expansions.md` — *"Harbour tokens listed in a scenario
are shuffled face down and placed one at a time at the positions shown in the
scenario diagram"* — use the other form:

```json
"harbours": {
  "mode": "shuffled",
  "edges": ["4,-4,0", "-1,4,-3", "-4,1,3"],
  "types": { "generic": 2, "ore": 1 }
}
```

### 1.5 Where the types live

New module `server/game/maps.py`, importing nothing from Flask or Socket.IO
(coding rule 4). Suggested surface:

```python
class MapDefinition:      # parsed, normalised, validated-shape
class Region:             # id, kind, hexes (sorted tuple), pool
class Pool:               # mode, terrain multiset, numbers multiset
class MapProblem:         # code, message, region_id, hex_key  (structured, not prose)
class MapUnplayable(Exception)

def parse_map(data: dict) -> MapDefinition          # shape only; raises InvalidPayload
def validate_map(defn) -> tuple[list, list]         # (errors, warnings)
def instantiate(defn, rng) -> MapInstance           # the deterministic draw
def builtin(name: str) -> MapDefinition             # "standard", "beginner", ...
def sort_hex_keys(keys) -> list[str]                # by parsed (x, y, z), never string order
```

`MapInstance` is deliberately dumb: `{hex_key: (terrain, number)}`,
`{edge_key: port}`, `robber_hex`, and (later) the server-only `fog_stack`.
It carries no graph — the graph is still derived by the existing
`_generate_vertices_and_edges` / `_build_neighbor_relationships`, which do not
change at all.

---

## 2. Instantiating a map into a game

### 2.1 The one branch in BoardBuilder

`_generate_board` currently does five steps. The map path replaces step 1, 2
and 5 and leaves 3 and 4 untouched:

```python
def _generate_board(self):
    if self.map_definition is None:
        land, ocean = self._radius_hex_keys()      # today's steps 1
        self._create_hexes(land | ocean)           # today's step 2
    else:
        instance = maps.instantiate(self.map_definition, self.rng)
        land, ocean = self._apply_map_instance(instance)   # fills self.hexes, self.robber_hex

    self._generate_vertices_and_edges(land)        # unchanged
    self._build_neighbor_relationships(land)       # unchanged

    if self.map_definition is None:
        self._assign_ports()                       # unchanged
    else:
        self._place_harbours_from_map(instance)
```

That is the whole collision surface with the in-flight `board.py` work: one
`if` in `_generate_board`, plus two new methods. `_create_hexes` and
`_assign_ports` are the two functions being rewritten right now, so the map
path must not touch their bodies.

`_apply_map_instance` also sets `self.hex_radius = defn.frame.radius` and
`self.edge_radius = defn.frame.radius`, so every existing consumer of those
attributes keeps working; on a custom map the land/sea split is per-hex data,
not a radius comparison. Anything that calls `self._is_ocean(x, y, z)` to ask
"is this water" must be changed to consult `self.hexes[key].type == "ocean"`.
Grep for `_is_ocean` before starting; it is currently used inside
`_create_hexes` only, but the in-flight work may add callers.

### 2.2 Harbours

The other agent is moving harbours onto coastal **edges**. That is exactly what
this format assumes — `harbours.places[].edge` is an edge key. `Edge` in
`server/game/hex_models.py` has no `port` field yet; when it gains one,
`_place_harbours_from_map` is a loop over `instance.ports`.

If that work has not landed when v1 starts, v1 ships with the map's `harbours`
block **parsed and validated but ignored**, falling back to the existing
`_assign_ports`, and the editor hides the Harbour tool. That keeps the two
efforts from blocking each other.

### 2.3 The draw, and determinism

Determinism is a hard requirement:
`tests/game/test_board.py::test_the_whole_board_is_reproducible_across_processes`
runs board generation in two subprocesses with different `PYTHONHASHSEED` and
demands identical output. Everything below exists to satisfy it.

Rules the map pipeline must obey, each mirroring a bug the existing code
already paid for (see the comments in `_create_hexes` and
`_generate_vertices_and_edges`):

1. **Regions are a JSON array, never an object.** File order is the iteration
   order. An object would give dict order, which is insertion order in CPython
   but is not something a wire format should lean on.
2. **Never iterate a set or a dict from the map file.** `pool.terrain` is
   expanded through `sorted(counts.items())`; `region.hexes` is normalised at
   parse time through `sort_hex_keys`, which sorts by the parsed `(x, y, z)`
   tuple, not lexicographically. (The existing code sorts key *strings*, which
   is stable but puts `"-3,0,3"` before `"0,0,0"` before `"3,-3,0"` in an order
   nobody would predict. New code should use `sort_hex_keys`; do not churn the
   existing calls, they are correct as-is.)
3. **The rng is the injected one**, `self.rng`, threaded in as a parameter to
   `instantiate`. No module-level `random.*` anywhere in `maps.py`.
4. **The number of rng calls is a pure function of (definition, rng).** Retries
   are allowed as long as they are driven by the same rng and bounded.

The algorithm:

```
def instantiate(defn, rng):
    placed = {}                                  # hex_key -> (terrain, number)
    for region in defn.regions:                  # file order
        keys   = region.hexes                    # already sort_hex_keys'd at parse
        tiles  = expand_terrain(region.pool)     # sorted(items()) then repeat
        tokens = list(region.pool.numbers)       # file order

        if region.pool.mode == "shuffled":
            rng.shuffle(tiles)
            rng.shuffle(tokens)

        for key, terrain in zip(keys, tiles):
            placed[key] = (terrain, None)

        assign_tokens(placed, keys, tokens, defn, rng)

    return MapInstance(placed, harbours(defn, rng), robber_start(defn, placed))
```

`assign_tokens` walks `keys` in order, and for each hex whose terrain requires
a token pops the next token off the stack. Sea, desert and (later) fog take
none. When the popped token is a 6 or an 8 and a 6 or 8 already sits on an
adjacent hex, apply the official rule from `expansions.md` (New World):

> The red number tokens showing six and eight may not be placed on adjacent
> hexes, and a second red token drawn next to a first must be replaced by
> another token drawn at random.

Concretely: scan forward through the remaining stack for the first non-red
token, swap it into this position, and push the red back where it came from.
This is O(n), always terminates, and matches the rulebook more closely than
reshuffling the whole region. If no non-red token remains — a map whose pool is
mostly reds on a tight island — raise `MapUnplayable`. Fail closed: refuse to
start the game with a named error rather than quietly placing adjacent reds.
This is why R11 in §3 is a *warning* at authoring time and a hard failure at
instantiation time.

Adjacency is checked against `placed` globally, so a later region cannot put a
red next to an earlier region's red.

`robber_start: "auto"` picks the first desert in `sort_hex_keys` order,
matching today's behaviour in `_create_hexes`. An explicit hex key is
validated to be land.

### 2.4 Testing determinism

Add `tests/game/test_maps.py` with a subprocess test modelled directly on
`test_the_whole_board_is_reproducible_across_processes`: instantiate the same
custom map with `random.Random(99)` under `PYTHONHASHSEED=0` and `=1`, dump
sorted hexes + ports + robber, assert equality. Without this the map path will
regress the moment someone iterates a dict.

Add property-style tests over seeds 0..25, as `test_board.py` already does for
the standard board: pool multiset is exactly reproduced on the board, no 7,
no token on sea or desert, no two reds adjacent.

### 2.5 Persistence

`server/game/persistence.py` regenerates board *structure* from geometry on
load and overlays the saved decisions. With a custom map the structure comes
from the map definition, so:

- `serialize()` gains `'map': defn.to_json()` — **the whole definition,
  inlined, not an id.** A map file can be edited or deleted between save and
  load; a saved game that silently regenerates against a different map would
  put buildings on hexes that no longer exist. Inlining is a few KB and keeps
  the "one human-readable file" property the module was written for.
- `deserialize()` passes it to `Game(..., map_definition=parse_map(data['map']))`.
  It re-runs `validate_map` first: `load()`'s docstring already treats a save as
  untrusted input, and a hand-edited `map` block is exactly that.
- `SAVE_VERSION` goes 1 → 2. An old save has no `'map'` key and means "standard
  board", so a compatibility shim is possible — but the module's stated policy
  is to ignore old saves rather than half-load them, and a single in-progress
  game is not worth the shim. Bump and move on.
- Fog (v3) additionally saves `revealed_hexes` and the remaining `fog_stack`.
  The stack is server-only state and must never appear in `get_board_data`
  (coding-rules, *Hidden information*: never send the deck order).

---

## 3. Validation

A map arriving over a socket is untrusted input, identical in status to a
`place_settlement` payload. Two layers:

**Layer 1 — `parse_map`, shape only.** Raises `InvalidPayload` from
`server/game/validation.py` so handlers report it the existing way
(`reject(code, message)`). Allowlists, per coding-rules *Inbound event
validation*:

- `map_version` is a known integer.
- `id` matches `^[a-z0-9][a-z0-9-]{0,47}$`. This is also the filename, so it is
  the path-traversal guard; nothing else may build a path from client input.
- `name` ≤ 64 chars, `notes` ≤ 512, `author` ≤ 64.
- `frame.radius` ∈ [1, 6]. Radius 6 is 127 hexes.
- ≤ 64 regions, ≤ 200 hexes total, ≤ 32 harbours. Bounded before anything
  quadratic runs.
- Every hex key parses to three ints with `x + y + z == 0`, all divisible by 3.
- `kind` ∈ the enum. Terrain names ∈ the enum. Token values ∈
  {2,3,4,5,6,8,9,10,11,12}.
- Counts are non-negative ints, `bool` rejected explicitly (`require_int`
  already does this and explains why).

**Layer 2 — `validate_map`, meaning.** Returns `(errors, warnings)` as
structured `MapProblem`s. Errors block saving *and* starting. Warnings are
shown in the editor and the lobby and do not block.

| # | Rule | Level |
|---|---|---|
| R1 | Region ids unique; at most one region uses `"remaining"` | error |
| R2 | No hex claimed by two regions; every frame hex claimed by exactly one | error |
| R3 | Every hex is inside the frame radius | error |
| R4 | **Pool size == region size.** `sum(terrain.values()) == len(hexes)` | error |
| R5 | **Token count == token-requiring tile count** in the pool | error |
| R6 | No token value of 7; no token on a `sea`/`desert`/`fog` tile (structural at instantiation, asserted post-hoc) | error |
| R7 | **At least one land hex on the whole map** | error |
| R8 | Every land hex has all six neighbours present in the frame — no land on the outer boundary. Seafarers frame pieces are all-sea; land at the rim has no coastline and breaks harbour and ship placement | error |
| R9 | **A region declared `island` is a land component entirely surrounded by sea** — an `island` region adjacent to `main` land is a naming lie | error |
| R10 | **Harbours sit on a coastal edge**: the edge's two adjacent hexes are one land, one sea; both its vertices are corners of the land hex. No two harbours on the same or adjacent edges (`expansions.md`, Forgotten Tribe: *"A harbour may never be placed on an edge adjacent to, or the same as, an edge already occupied by another harbour"*) | error |
| R11 | Two red numbers (6/8) adjacent. Statically checkable for `mode: "fixed"` | error (fixed) / warning (shuffled — enforced at instantiation, §2.3) |
| R12 | **More than one land component** — unreachable without ships | warning at save, **error at game start** until ships exist |
| R13 | Any region of kind `island` or `fog` | warning at save, **error at game start** in v1 |
| R14 | `robber_start` is a land hex (or `"auto"` with at least one desert); `pirate_start` is a sea hex | error |
| R15 | Land hex count vs piece supply: warn if `max_roads` per player looks too small to cross the map | warning |
| R16 | `victory_target` differs from the `(land − deserts) / 2` heuristic by more than 3 | warning |

R4 deserves its own note: the existing `_create_hexes` carries a comment about
a 20-entry resource list silently dropping one tile so no two boards had the
same mix. R4 is that bug promoted to a validation rule, which is the whole
argument for pools being explicit multisets rather than "fill the rest with
wheat".

Where validation runs:

- `save_map` handler — before writing to disk. Errors reject the save.
- `preview_map` handler — before instantiating.
- Game start (`_start_game_locked`) — re-read from disk and re-validate.
  Never trust that the file on disk is the file that was validated.
- `persistence.deserialize` — re-validate the inlined definition.

---

## 4. Editor UX

### 4.1 Constraints it has to live inside

- Vanilla ES modules, no build step, one entry point (`main.js`), views are
  sibling `<div>`s toggled with `.hidden`. No router.
- The frontend is being reworked for a no-scroll layout with detail behind
  buttons. So: compact controls, detail in popovers, nothing that grows the
  page.
- `board-renderer.js` is a classic script exposing `window.BoardRenderer`; the
  camera is module-private. The editor reuses it rather than drawing its own
  canvas.
- Every element handle goes in `dom.js` as a named export; nothing calls
  `document.getElementById` inline.
- Reference `tokens.css` custom properties only, never literals — the palette
  is redeclared under `prefers-color-scheme: dark`.

### 4.2 What the renderer needs to expose

Small, additive, and worth agreeing with the frontend agent before they land
their rework:

- `BoardRenderer.clientToBoard`, `findNearestHex`, `findNearestEdge`,
  `boardToClient`, `attachCameraControls` — already exist, need to be on the
  exported object.
- `BoardRenderer.invalidateLayout()` — `getLayout` memoises on board *object
  identity*, so an editor mutating hexes in place will keep drawing the stale
  layout. Adding or removing a hex is exactly the case that breaks. Either
  expose this or have the editor replace the board object wholesale on every
  edit (cheaper to reason about; measure before optimising).
- One optional argument on `renderBoard(boardData, canvasId, highlight,
  preview, overlay)` where `overlay = { regionOf: {hexKey: regionId}, colors:
  {regionId: cssColor} }`. The editor needs region tinting and nothing else.
  Backward compatible; existing calls pass four arguments.
- `BOARD_CONFIG.colors` needs entries for `sea` (distinct from the current
  `ocean`, if the naming question in §7 goes that way) and later `gold`, plus
  matching `--terrain-*` tokens. The renderer hardcodes its palette today,
  which is a pre-existing gap the editor will make visible.

### 4.3 The screen

A fourth sibling of `#join-screen` / `#user-screen` / `#game-screen`:
`#map-editor-screen`, reached from a **Maps** button in the lobby, left by a
**Done** button. Lobby-only: editing during a game is refused server-side, so
the button is disabled while a game runs (same condition as `set_rules`
locking).

One full-height flex column, `min-height: 0` on the canvas so it never scrolls:

```
┌─ toolbar ───────────────────────────────────────────────────────┐
│ [Paint][Erase][Harbour][Inspect] │ Region: [mainland ▾] [＋]     │
│                                  │ [Pool ▾] │ [Preview] [Save ▾] │
├─ canvas (flex: 1, min-height: 0) ───────────────────────────────┤
│                                                                 │
│            existing pan/zoom canvas, region-tinted              │
│                                                                 │
├─ status strip ──────────────────────────────────────────────────┤
│ 61 hexes · 3 regions · pool 6/7 ▲ · 2 problems ▸                │
└─────────────────────────────────────────────────────────────────┘
```

Everything with a `▾` or `▸` opens a popover. Nothing else is on screen.

### 4.4 Painting

The tool is a mode, and the mode changes what a drag means. This is the one
real interaction collision: **drag currently pans**, and drag is also the
natural paint gesture.

Resolution — paint on drag, pan on modifier:

- **Paint / Erase mode:** primary-button drag paints or erases continuously.
  Panning requires space-held-drag, middle button, two-finger scroll, or the
  arrow keys — all already bound by `attachCameraControls`. Wheel zoom is
  unchanged.
- **Harbour / Inspect mode:** drag pans as it does in game, since there is no
  drag gesture to conflict with.
- The existing `wasPanning()` guard in `board.js`'s tap handler is the model:
  the editor's pointer handlers must be registered *before*
  `attachCameraControls` for the same reason.

Painting assigns the hex to the currently selected region and removes it from
whichever region held it. Erase returns it to the `"remaining"` region if one
exists, otherwise leaves it unassigned and R2 flags it. Region colours come
from a fixed palette of eight, cycling; the owner can override per region.

Keyboard: `1`–`9` select region, `P`/`E`/`H`/`I` select tool, `Ctrl+Z` one
level of undo (a snapshot stack of the map document, capped at 30 — a real
undo history is v2).

### 4.5 The pool popover

Click **Pool ▾**, or click the region chip on a painted hex, and a popover
opens anchored to the board using the same mechanism `placement.js` already
uses for the placement confirm control — `anchorFor()` → `boardToClient()` →
absolutely positioned inside `#game-board` at `--z-dropdown`. This is proven
not to resize the canvas, which matters in a no-scroll layout.

Contents, compact:

```
 mainland                    kind [ main ▾ ]   [shuffled ▾]
 ────────────────────────────────────────────────────────────
 wood  [−] 2 [+]    brick [−] 1 [+]    desert [−] 1 [+]
 wheat [−] 2 [+]    sheep [−] 1 [+]    sea    [−] 0 [+]
 ────────────────────────────────────────────────────────────
 tokens  2·[0] 3·[1] 4·[1] 5·[1] 6·[1] 8·[0] 9·[1] 10·[1] 11·[0] 12·[0]
 ────────────────────────────────────────────────────────────
 tiles 7/7 ✓        tokens 6/6 ✓        [Auto-fill]  [Done]
```

The two badges are the whole validation story at authoring time: they mirror
R4 and R5 exactly, turn red when they disagree, and mean the user never sees a
server rejection for the most common mistake. **Auto-fill** proposes a pool
scaled from the standard 19-hex mix to the region's size — the fastest path
from "I painted an island" to "it is playable".

Harbour tool: click a coastal edge and it cycles
`generic → wood → brick → sheep → wheat → ore → none`. Non-coastal edges do not
respond, and the status strip explains why (R10, phrased as
"harbours sit between land and sea").

### 4.6 Preview

**Preview** emits `preview_map { map }` to the server, which validates and
calls `instantiate(defn, Random(seed))` with a fresh seed each press, and
returns a board payload of the same shape `get_board_data` produces. The
existing renderer draws it with no changes.

Do the preview **server-side**. It is the same code path the real game uses, so
what you preview is what you play, and it avoids a second implementation of
pool drawing in JavaScript that would drift. The cost is one round trip per
press, which is nothing.

Preview shows the drawn board, the derived island count, and any warnings.
Pressing it repeatedly is how you sanity-check a pool's variance, which is the
thing you actually want to know about a randomised map.

### 4.7 Save, load, share

**Save ▾** opens a popover: name field, Save, Save as copy, and a list of
existing maps with Load / Duplicate / Delete. Server events in §5. Errors
render through the existing `showNotice(message, 'error')`.

Sharing between players at one table is solved by the architecture and needs no
new machinery: **maps live on the server**, and there is one server per table.
Selecting a map is a lobby rule, so it rides the existing `rules_changed`
broadcast and every seat sees the same selection, with the same
"frozen when the game starts" semantics as every other rule.

---

## 5. Storage and sharing

### 5.1 On disk

One JSON file per map, in `${CATAN_DATA_DIR}/maps/<id>.json`. `DATA_DIR` is
already the "runtime state lives outside the repo tree" directory
(`server/config.py`), and the tests already redirect it to a temp dir, so map
tests get isolation for free.

New module `server/game/map_store.py`:

```python
MAPS_DIR = os.path.join(config.DATA_DIR, "maps")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

def list_maps() -> list[dict]      # [{id, name, author, hexes, regions, problems}]
def read_map(map_id) -> dict       # raises UnknownMap
def write_map(map_id, data)        # atomic, temp + fsync + os.replace
def delete_map(map_id)
```

`write_map` reuses the atomic-write pattern from `persistence.save` verbatim —
temp file, flush, fsync, `os.replace` — for the reason stated there: an
interrupted write must not turn "the server restarted" into "the map is gone".

Every path is built as `os.path.join(MAPS_DIR, f"{map_id}.json")` after `SLUG`
matches, and never any other way. That single rule is the entire path-traversal
defence, which is why `id` is validated in layer 1 of §3 rather than later.

Built-in maps (`standard`, `beginner`, and whatever `board_layout` grows) ship
read-only in `server/game/builtin_maps/*.json`, are listed alongside user maps
with `"builtin": true`, and refuse writes and deletes. Duplicating a built-in
into `DATA_DIR` is how you start from one.

`list_maps` is called on a directory that a human may have dropped files into.
It parses and validates each one; a file that fails becomes a listing entry
with `problems` set rather than an exception that breaks the whole list.

### 5.2 Selecting a map

The in-flight work adds a `board_layout` rule with `random` / `beginner` /
`large`. Build on it: add a fourth option `custom`, plus a companion rule
`board_map` naming which custom map.

That needs a third type in `server/game/rules.py`, which today has only `BOOL`
and `INT`:

```python
CHOICE = "choice"   # {"options": [{"value": ..., "label": ...}], "default": ...}
```

`coerce` gains one branch: value must be a string present in `options`,
otherwise fall back to the default — matching the existing "clamp and continue,
never reject a lobby setting" policy. `catalogue()` computes `board_map`'s
options from `map_store.list_maps()` at call time, so a newly saved map appears
in every client's picker on the next `rules_changed` with no frontend change.
That is the same property the rules registry was designed for, and it is the
main argument for putting map selection in `rules` rather than inventing a
parallel `selected_map` field on `GameSession`.

The cost is honest: `lobby.js` needs a `CHOICE` row renderer (a `<select>`
alongside the existing `.rule-toggle` and `.rule-number`), and `lobby.js` is
being reworked. Coordinate or wait.

### 5.3 Socket events

Following the existing convention — imperative client→server, past-tense
server→client, snake_case, errors as `{code, message}`:

| Direction | Event | Payload |
|---|---|---|
| c→s | `request_maps` | — |
| s→c | `map_list` | `{maps: [{id, name, author, hexes, regions, builtin, problems}]}` |
| c→s | `save_map` | `{map: {...}}` |
| s→c | `map_saved` | `{id}` — plus a fresh `map_list` and `rules_changed` broadcast |
| c→s | `delete_map` | `{id}` |
| c→s | `preview_map` | `{map: {...}, seed?: int}` |
| s→c | `map_preview` | `{board: {...}, warnings: [...], islands: int}` |

All of them go through `rate_limited()` like every other handler. `save_map`
and `preview_map` carry the largest payloads on the wire, so they need an
explicit size cap ahead of parsing — `payload_too_large` in
`server/game/rate_limit.py` already exists for this; give map events a tighter
limit than the default (a 200-hex map serialises to well under 32 KB).

Authorisation follows the existing `set_rules` policy: anyone in the lobby may
save or select a map, refused once a game is running. Delete is the one that
should probably be narrower — see §7.

### 5.4 Import and export

v2. A textarea in the Save popover that dumps and accepts the JSON, which is
the "real simple system, save to a text file" the owner asked for taken to its
conclusion: the map *is* the text file, and copy-paste is the transport. No
upload endpoint, no new dependency. Pasted JSON goes through exactly the same
`parse_map` + `validate_map` as everything else.

---

## 6. Staging

### v0 — groundwork (small, unblocks everything)

1. `sort_hex_keys` in `maps.py`.
2. `map_store.py` with the slug guard and atomic write, plus tests.
3. Agree the renderer surface in §4.2 with whoever owns the frontend.

Ship nothing user-visible. This is deliberately a separate step so the
renderer conversation happens before anything depends on its outcome.

### v1 — custom single-landmass maps

Smallest thing that is actually useful.

- `maps.py`: `parse_map`, `validate_map`, `instantiate`, the builtin
  `standard` map expressed in the format (which proves the format can express
  today's board — do this first, it is the best possible test).
- The one branch in `_generate_board`, plus `_apply_map_instance`.
- `SAVE_VERSION` → 2, map inlined in the save.
- `board_layout: custom` + `board_map` + `CHOICE` in `rules.py`.
- Socket events from §5.3.
- The editor: paint, erase, region create/rename/recolour, pool popover,
  preview, save, load, delete, one-level undo.
- Tests: subprocess determinism, seed sweep, round-trip
  `parse(to_json(defn)) == defn`, every validation rule gets a test that a bad
  map is refused.

**v1 explicitly does NOT:**

- Ships, the pirate, gold fields, special victory points, Catan chits.
- Fog reveal. `kind: "fog"` parses and previews; starting a game refuses.
- Multi-landmass *play*. You may author and preview a four-island map; the
  game refuses to start on it (R12). This is the honest consequence of having
  no ships and should be stated in the editor UI, not discovered.
- Fixed pools / hand-placed individual tiles. Shuffled pools only.
- Import/export, undo history, map thumbnails, per-scenario setup rules
  ("starting settlements on the main island only"), 5–6 player frames.
- Concurrent editing. One game per process, one table, last write wins. The
  players are in the same room and can talk.
- Any migration path for v1 maps. `map_version` exists so v2 can refuse them
  loudly; nobody has a library of maps yet.

### v2 — depth without ships

Gold fields (one terrain, one "choose a resource" prompt — genuinely cheap and
does not need ships), fixed pools, import/export textarea, larger frames,
per-map `victory_target` wired into `Game`.

### v3 — ships

Vertices and edges over sea hexes, ship pieces, the Longest Trade Route, the
pirate. This is the expensive one and it is a separate project. Only after it
lands do `island` and `fog` become playable, and only then do the special-VP
rules from The Four Islands and Heading for New Shores mean anything.

---

## 7. Risks and open questions

### Risks

**The two functions this touches are the two being rewritten.** `_create_hexes`
and `_assign_ports` are in flight right now. Mitigation is structural: all new
logic lives in `maps.py`, and `board.py` gains one `if` plus two small methods
that call into it. If the merge still conflicts, the conflict is in
`_generate_board`, which is 15 lines.

**`getLayout` memoises on board object identity.** An editor that mutates
`hexes[key].type` in place will silently draw the old layout. Harmless for
terrain changes, a real bug the moment a hex is added or removed. Either
`invalidateLayout()` or replace the board object per edit.

**Paint-drag versus pan-drag.** The proposal in §4.4 (modifier to pan while
painting) is the standard resolution but it is a learned gesture. If it tests
badly the fallback is click-per-hex with no drag, which is tedious on a 127-hex
frame but unambiguous.

**Board size versus piece supply.** A 127-hex board with 15 roads per player is
a different game, not a bigger one. R15 warns; it cannot decide for you.

**`_is_ocean` as a water predicate.** It answers "is this hex in the ring
between hex_radius and edge_radius", which on a custom map is meaningless. Any
caller using it as "is this water" must move to `hexes[key].type`. Currently
there is one caller; the in-flight work may add more.

**Renderer palette is hardcoded** in `BOARD_CONFIG.colors` and does not read
`--terrain-*`. The editor makes this visible immediately because it introduces
new terrain names. Pre-existing, but it lands on this feature's plate.

**Untrusted maps are a bigger attack surface than any existing event.** A map
payload is nested, variable-length, and turns into filesystem paths. The
mitigations are all in §3 and §5.1 and none of them are optional: bounded sizes
before any traversal, slug regex before any path join, re-validate on every
read including from disk.

### Open questions — need the owner's decision

1. **`sea` or `ocean`?** The engine says `"ocean"`, the Seafarers rulebook says
   "sea". Map files could use either. My recommendation: `"sea"` in map files
   (it is the published vocabulary and it is what the editor's UI will say),
   translated to `"ocean"` at the engine boundary in `_apply_map_instance`, with
   a note in `maps.py` explaining the one-word translation. The alternative —
   renaming `"ocean"` everywhere — touches the renderer, the tests and the save
   format for no gameplay benefit.

2. **Is it acceptable that v1 authors multi-island maps but refuses to start
   them?** I think yes, and I think the alternative (waiting for ships) delays
   everything useful by weeks. But it means the headline feature you asked for —
   islands — is a preview-only feature in v1. If that is not acceptable, the
   staging in §6 needs to move ships into v1 and the whole thing becomes a much
   bigger project.

3. **Who may delete a map?** `set_rules` policy is "anyone in the lobby, the
   table can talk". That is right for *selecting* a map and probably wrong for
   *deleting* someone's work, which is irreversible. Options: nobody (delete by
   hand on the server), only the recorded `author`, or everyone with a
   confirmation. I lean toward "only the author, matched against the joined
   name" — weak, but the threat model here is a misclick, not an adversary.

4. **Fixed pools in v1?** They are what you need to reproduce a printed
   scenario diagram exactly, and they are maybe 30 extra lines. But they double
   the editor's per-hex interaction surface (you must be able to set one hex's
   terrain and number directly). I recommend deferring to v2 and would rather
   be told I am wrong now than build it twice.

5. **Frame radius cap of 6 (127 hexes) and `MAX_PLAYERS = 4`.** A Seafarers
   5–6 player scenario needs both raised. Is that in scope at all, or is this a
   four-player table forever?

6. **Should `board_map` live in `rules`?** It gets sharing, locking and
   persistence for free, at the cost of a third type in `rules.py` and a new
   row renderer in a `lobby.js` that someone else is currently rewriting. The
   alternative is a standalone `selected_map` on `GameSession` with its own
   broadcast, which is more code but zero collision. I recommend `rules`, but
   the timing is a coordination question, not a technical one.
