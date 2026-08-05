# Map Creator — Design

Design document. No implementation.

**Revised after ships shipped.** The first version of this document was written
when the ocean was scenery: it argued that v1 should let you *author* an island
map and refuse to *start* a game on it, because a second landmass was
unreachable. That compromise is dead. `server/game/seafarers.py`,
`server/handlers/ships.py`, the sea edge graph in `board.py:284`, the `ships` /
`ship_movement` / `pirate` / `longest_trade_route` / `island_victory_points`
rules and a Seafarers UI with browser tests are all in the tree. Islands are
playable today — the engine simply has no way to make one.

That is what this feature is now: **the only missing half of Seafarers is the
board.** Everything downstream of a second island already works and is tested.

The goal, in the owner's words: define regions for landmass, oceans and
islands, and set the pool of tiles for each region.

The rulebook blesses it. From `expansions.md`, Scenario: New World:

> Players may agree to adjust the randomly generated set-up if they are unhappy
> with it, and may freely design and play scenarios of their own.

> The board is created by shuffling all listed hexes face down and placing them
> face up at random within the assembled frame.
> Number tokens are shuffled and placed at random, one on each land hex, and no
> number tokens are placed on sea hexes.

A *region with a shuffled pool* is that paragraph turned into data.

---

## 0. What this buys you, and what it does not

A map creator now gives you: bigger and stranger boards, hand-chosen resource
mixes, **multi-island maps you can actually play**, and a preview button. The
special victory point for a first settlement on a new island scores by itself
(`seafarers.py:332`), because an island is derived from the board as dealt and
nothing about it was ever authored.

It does **not** give you the published Seafarers scenarios verbatim:

| Scenario | Still needs, beyond a map |
|---|---|
| The Four Islands | nothing in the engine — but per-player *home island* setup restrictions ("starting settlements on the main island only") are not expressible |
| Heading for New Shores | as above, plus the robber's start varying by player count |
| The Fog Island | lazy tile reveal on exploration, a hidden server-side stack |
| ~~Any 5–6 player scenario~~ | Lifted: `max_players` is a rule now, and `builtin_maps/six-shores.json` is a four-landmass board for six |
| Gold field scenarios | a `gold` terrain, a production hook, and a client for `pending_choice` — which has no UI at all (`OPEN-THREADS.md` §1) |

So: the geometry and the resource mix are in scope and cheap; **scenario setup
rules are the next expensive thing after this**, and this document does not
plan them. Honest framing, replacing the old "this is 20% of Seafarers": the
map creator is now most of what stands between this engine and a Seafarers
game, and the remainder is per-scenario setup restrictions plus fog.

---

## 1. Data model

### 1.1 The three things a map is

1. **A frame.** How big the board is. One integer radius in the scaled-cube
   metric (`max(|x/3|, |y/3|, |z/3|)`).
   Note what changed: `board.py` no longer has a radius concept at all —
   `_generate_board` derives the sea from *adjacency to land* (`board.py:266`),
   because the 5–6 player island is not a hexagon and no radius describes it.
   That derivation is wrong for a custom map: two islands three hexes apart
   would have no water between them, only a hole where hexes do not exist. So a
   map **authors its own sea**, and `frame.radius` exists to bound the editor
   canvas and to give `"hexes": "remaining"` something to mean.
2. **Regions.** A named set of hex coordinates, plus a kind, plus a pool.
   Regions partition the frame; every hex belongs to exactly one.
3. **Harbours.** In v1, a bag of harbour types the engine spaces around the
   coastlines — the `ports` field of a `LAYOUTS` entry, promoted to data.
   Hand-placing individual harbours is v2 (§6).

### 1.2 Region kind is about *rules*, not about *terrain*

The load-bearing decision, unchanged and now confirmed by shipped code:
**`kind` must not decide what tiles a region contains.** The pool decides that.
`kind` decides how setup and scoring treat the region.

The reason is "Heading for New Shores": the off-island area is a pool of
terrain positions of which *some are sea*. If `kind: "island"` forced land, that
scenario would be inexpressible. So a pool may legitimately contain `sea`, and
the shape of the islands is only known after the draw.

Which leads to the second decision: **the island that scores a special VP is
derived at runtime, not authored.** It is already implemented exactly this way:

```python
# server/game/board.py:579
def islands(self) -> dict:
    """Land hex key -> the id of the island it belongs to.

    An island is derived, never authored: a stretch of land the sea cuts
    off from the rest of the board, found by flood fill over neighbouring
    land hexes. A map file can group hexes into regions for its own
    purposes, but which of them a player has landed on has to come from the
    board as it was actually dealt — a region whose pool dealt it some sea
    may end up as two islands, or none.
    """
```

That docstring was written against this design and is the contract. `islands()`
keys off `hex.type != 'ocean'`, the id is `min(component)`, and
`island_of_vertex` (`seafarers.py:318`) sorts before choosing so the answer does
not depend on iteration order. A region is an *authoring* construct; an island
is a *derived* one, and nothing in `maps.py` may compute one.

`kind` values:

| kind | meaning | v1 |
|---|---|---|
| `main` | Land the scenario calls the main island | yes |
| `island` | Land foreign to everyone at setup. Documentation and a colour, until setup restrictions exist | parses, plays, **has no mechanical effect** |
| `sea` | Water. Ships and the pirate live here. Never takes a number token | yes |
| `fog` | Hexes hidden at setup, drawn lazily on exploration | parses, refuses to start |

`island` is deliberately inert in v1 rather than removed. The thing it would
mean — "no starting settlement here" — is a setup restriction, and setup
restrictions are the scenario work this document does not plan. Keeping the
value in the vocabulary costs nothing and stops the format changing later.
**An `island` region is not what makes an island; the flood fill is.**

### 1.3 Pools

```
pool := {
  "mode":    "shuffled"          v1. "fixed" is v2.
  "terrain": {terrain: count}
  "numbers": [int, ...]          a multiset of tokens, shuffled
}
```

Terrain vocabulary: `wood`, `brick`, `sheep`, `wheat`, `ore`, `desert`, `sea`,
and later `gold`. `sea` is the map-file word; the engine's `Hex.type` value
stays `"ocean"`. **Decided** — the alternative, renaming `"ocean"` everywhere,
touches the renderer, `move_pirate` (`seafarers.py:301`), `islands()`,
`land_hexes_of_edge`, the save format and a dozen tests for no gameplay
benefit. The translation is one line in `_apply_map_instance` and one comment in
`maps.py`.

`numbers` is an explicit multiset rather than counts, because its length must
equal the number of *token-requiring* tiles in the terrain pool, and that is
known statically even though the placement is not. This is what makes rule R5
in §3 a static check rather than a runtime surprise.

### 1.4 Worked example

A radius-4 frame: a 7-hex mainland, a 3-tile offshore position group of which
one tile is sea, everything else water. The coordinates below are checked —
this map builds, and yields two islands with a sea lane between them.

```json
{
  "map_version": 1,
  "id": "little-shores",
  "name": "Little Shores",
  "author": "kalin",
  "notes": "Smallest map that exercises regions, a mixed pool and two islands.",
  "frame": { "radius": 4 },
  "suggested_victory_target": 11,
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
  "harbours": { "mode": "bag", "types": { "generic": 3, "wood": 1, "ore": 1 } }
}
```

Each of these is a deliberate feature:

- `"hexes": "remaining"` — exactly one region may claim every hex inside the
  frame not claimed by another. The parser expands it before anything else
  runs, so the rest of the pipeline only ever sees explicit lists. Without it
  the ocean region of a radius-4 map is a 51-entry array nobody will read.
- `far-shore` has three positions and a pool of three tiles, one of which is
  `sea`. After the draw it may be a 2-hex island, or two 1-hex islands, or a
  1-hex island plus water. This is "Heading for New Shores" in miniature and it
  is why islands are derived. It is also the case that trips every hazard in
  §2.2 — a pool containing `sea` is the whole reason those fixes are v1 work
  and not v2 work.
- `numbers` for `far-shore` has 2 entries for 2 token-requiring tiles. `sea`
  takes none. `mainland` has 6 entries for 7 hexes because one is desert.
- Land sits at ring ≤ 3 inside a radius-4 frame, so every land hex has all six
  neighbours (R8). Land on the rim has coastal edges with only one hex, which
  `is_sea_edge` (`seafarers.py:26`) rejects — no ship could ever reach it and
  `_assign_ports` would still hang a harbour there.
- `suggested_victory_target`, not `victory_target`. `victory_target` is already
  a rule (`rules.py`, INT 5–20) and the lobby owns it. A map that silently
  overrode a rule the table set would be the one thing the rules registry was
  built to prevent — see `rules.py`'s own note that "no rule below ever changes
  it behind your back, though several suggest a different one", and the
  `suggests_victory_target=11` extra already on `harbormaster`. The map uses the
  same convention: it suggests, the editor shows the rulebook heuristic
  (*"terrain hexes minus the deserts, divided by two"*), the lobby decides.
- No `pirate_start`. `pirate_hex` is `None` until somebody first moves it
  (`persistence.py:123`), and that is a real state, not a missing field.

### 1.5 Where the types live

New module `server/game/maps.py`, importing nothing from Flask or Socket.IO.

```python
class MapDefinition:      # parsed, normalised, validated-shape
class Region:             # id, kind, hexes (sorted tuple), pool
class Pool:               # mode, terrain multiset, numbers multiset
class MapProblem:         # code, message, region_id, hex_key  (structured, not prose)
class MapUnplayable(Exception)

def parse_map(data: dict) -> MapDefinition          # shape only; raises InvalidPayload
def validate_map(defn) -> tuple[list, list]         # (errors, warnings)
def instantiate(defn, rng) -> MapInstance           # the deterministic draw
def builtin(name: str) -> MapDefinition             # "standard", "beginner", "large"
def sort_hex_keys(keys) -> list[str]                # by parsed (x, y, z), never string order
```

`MapInstance` is deliberately dumb: `{hex_key: (terrain, number)}`, the harbour
bag, `robber_hex`, and (later) the server-only `fog_stack`. It carries no graph
— the graph is still derived by `_generate_vertices_and_edges` and
`_build_neighbor_relationships`, which do not change.

---

## 2. Instantiating a map into a game

### 2.1 Three prerequisite fixes in `board.py`

These are not part of the map format; they are bugs the map format is the first
thing to reach. **Each is small, independently testable, and should land before
`maps.py` exists.** All three were reproduced against the real engine by
patching a two-island layout into `LAYOUTS` with one `ocean` entry in its
resource pool.

**(a) Land is what was dealt, not what the layout set aside.** `place_settlement`
tests `vertex.neighbors['hexes']` (`game.py:460`), and that list is built from
`land_hex_keys` — the *slots* — in `_build_neighbor_relationships`
(`board.py:485`). Today slots and land terrain are identical for every built-in
layout, so no test can tell them apart; `OPEN-THREADS.md` §3 records this as "a
latent hole for the map creator". It is no longer latent: with one `sea` tile in
a land region's pool, **2 vertices ringed entirely by ocean accepted a
settlement on open water** in the reproduction. Fix, in `_generate_board`
between `_create_hexes` and `_generate_vertices_and_edges`:

```python
self._create_hexes(land_hex_keys, ocean_hex_keys)
# Land is what was dealt, not what the layout set aside for it. Identical for
# every built-in layout; a map pool that contains sea is what makes them differ.
land_hex_keys = {key for key in land_hex_keys if self.hexes[key].type != 'ocean'}
ocean_hex_keys = set(self.hexes) - land_hex_keys
```

Two lines, and they fix `place_settlement`, `is_coastal_edge`,
`land_hexes_of_edge` and the harbour ring at once, because all of them read
terrain except this one list that did not.

**(b) A sea tile must not take a number token.** `_create_hexes:332` exempts
`desert` only:

```python
(hex_type, None if hex_type == 'desert' else number_tokens.pop())
```

In the reproduction, the ocean tile dealt into a land slot came out carrying a
**9**. The renderer would draw a number on open water and `distribute_resources`
would pay nobody. Exempt every type that is not a resource, and let R5 in §3
guarantee the counts.

**(c) A board can have more than one coastline.** `_coastal_edges_in_order`
(`board.py:635`) walks *one* ring from the lowest coastal edge and returns it
even when it is incomplete — it logs `coastline is not a single ring` and
carries on. On the two-island board it walked **18 of 32** coastal edges; on a
sunk-middle board, **18 of 54**, and *none* of the small island's edges were in
the walk. `_assign_ports` then crowds every harbour onto whichever coast the
walk happened to find, sometimes an interior lagoon.

Fix: `_coastline_rings() -> list[list[str]]`, repeating the existing walk from
the lowest unvisited coastal edge until every coastal edge is claimed, rings
returned sorted by length descending then by lowest edge key. `_assign_ports`
allocates harbours across rings in proportion to ring length, capped at
`len(ring) // 2` (the existing "harbours never touch" spacing), remainder to the
longest ring first, then runs today's spacing loop within each ring.

> **Hard constraint on (c):** when there is exactly one ring, the sequence of
> `self.rng` calls must be byte-for-byte what it is today. Otherwise every
> existing seeded board moves its harbours, and `test_map_layouts.py` and the
> browser suites are all pinned to current output. One ring is the only case
> the built-in layouts produce, so this is achievable and must be asserted.

### 2.2 The one branch in `_generate_board`

```python
def _generate_board(self):
    if self.map_definition is None:
        self.board_layout = LAYOUTS.get(...)          # today, unchanged
        land_hex_keys, ocean_hex_keys = self._layout_hex_keys()
        self._create_hexes(land_hex_keys, ocean_hex_keys)
    else:
        instance = maps.instantiate(self.map_definition, self.rng)
        land_hex_keys, ocean_hex_keys = self._apply_map_instance(instance)

    # fix (a) from §2.1 goes here, on both paths
    ...
    graph_hex_keys = land | ocean if self.rules['ships'] else land   # unchanged
    self._generate_vertices_and_edges(graph_hex_keys)                # unchanged
    self._build_neighbor_relationships(land, graph_hex_keys)         # unchanged
    if self.rules['no_adjacent_red_numbers']:
        self._separate_red_numbers()                                 # unchanged
    self._assign_ports()                                             # unchanged
```

Note how much of the old plan this deletes:

- The old draft had `instantiate` implement the rulebook's red-number swap
  itself. **It must not.** `_separate_red_numbers` (`board.py:368`) exists, is
  gated on the `no_adjacent_red_numbers` rule, runs after the graph is built
  because it needs adjacency, is bounded by `MAX_RED_SEPARATION_PASSES`, and
  degrades with a warning instead of raising. A second implementation inside
  `maps.py` would be a second answer waiting to disagree. Drop `MapUnplayable`
  for this cause; keep the class for pool-arithmetic failures.
- The old draft's `_is_ocean` risk is gone — the function no longer exists.
- The old draft's "`_create_hexes` and `_assign_ports` are being rewritten right
  now, do not touch their bodies" caveat is gone. That work landed. Both bodies
  are now fair game, and fixes (b) and (c) are inside them.
- The old draft's harbour section waited on `Edge.port`. `Edge` has `port` and
  `ship`, harbours live on edges, and `canonical_edge_key` (`board.py:234`)
  guarantees one Edge per hex side since `111f714`. Anything in the map file
  naming an edge must be run through `canonical_edge_key`; that is v2's problem,
  since v1 harbours are a bag, not positions.

`_apply_map_instance` fills `self.hexes` from the instance (translating `sea` →
`"ocean"`), sets `self.robber_hex`, and returns the land/ocean split by terrain.
It also sets `self.board_layout` to a synthetic dict carrying `ports` and
`fixed: False`, so `_assign_ports` needs no branch of its own.

### 2.3 The draw, and determinism

Determinism is a hard requirement.
`tests/game/test_map_layouts.py:157::test_every_map_is_reproducible_across_processes`
already runs every layout, with ships off and on, in two subprocesses under
`PYTHONHASHSEED=0` and `=1`, and compares hexes, vertices, edges, **islands**,
ports and the robber. A custom map goes into that test's loop; it does not need
a new test of its own shape.

Rules the map pipeline must obey:

1. **Regions are a JSON array, never an object.** File order is iteration order.
2. **Never iterate a set or a dict from the map file.** `pool.terrain` expands
   through `sorted(counts.items())`; `region.hexes` is normalised at parse time
   through `sort_hex_keys`, which sorts by the parsed `(x, y, z)` tuple. (The
   existing code sorts key *strings*, which is stable but orders `"-3,0,3"`
   before `"0,0,0"` before `"3,-3,0"`. Use `sort_hex_keys` in new code; do not
   churn the existing calls, they are correct as-is.)
3. **The rng is `self.rng`**, threaded into `instantiate` as a parameter. No
   module-level `random.*` anywhere in `maps.py`.
4. **The number of rng calls is a pure function of the definition.** No retries
   whose count depends on what was drawn.

```python
def instantiate(defn, rng):
    placed = {}                                  # hex_key -> (terrain, number)
    for region in defn.regions:                  # file order
        keys   = region.hexes                    # sort_hex_keys'd at parse
        tiles  = expand_terrain(region.pool)     # sorted(items()) then repeat
        tokens = list(region.pool.numbers)       # file order
        rng.shuffle(tiles)
        rng.shuffle(tokens)
        for key, terrain in zip(keys, tiles, strict=True):
            placed[key] = (terrain, tokens.pop() if takes_a_token(terrain) else None)
    return MapInstance(placed, defn.harbours, robber_start(defn, placed))
```

`takes_a_token` is the same predicate as fix (b) — one function, imported by
`board.py`, so the two cannot drift.

`robber_start: "auto"` picks the first desert in `sort_hex_keys` order, matching
`_create_hexes:365`. An explicit hex key is validated to be a land *slot*, and
re-checked after the draw: a pool that can deal sea into the robber's hex is an
authoring error worth a warning, not a crash — fall back to the first desert,
then to no robber if the map has no desert at all.

### 2.4 Persistence

`persistence.py` regenerates board *structure* from geometry on load and
overlays the saved decisions. With a custom map the structure comes from the
definition, so:

- `serialize()` gains `'map': defn.to_json()` — **the whole definition, inlined,
  not an id.** A map file can be edited or deleted between save and load, and a
  saved game that regenerated against a changed map would put buildings on hexes
  that no longer exist. A few KB, and it keeps the "one human-readable file"
  property.
- `deserialize()` passes it as `Game(..., map_definition=parse_map(data['map']))`
  after re-running `validate_map`. `load()`'s contract already treats a save as
  untrusted, and a hand-edited `map` block is exactly that.
- **`SAVE_VERSION` does not change.** The old draft said 1 → 2; that was wrong.
  The key is additive and absent means "not a custom map", which is precisely
  the reasoning the module already records for not bumping when hex sides
  gained a single key: "Refusing them would have thrown away games in progress
  to fix a bug the players did not cause."
- The `rules` block already carries `board_layout` and will carry `board_map`,
  and they must agree with the inlined `map`. On disagreement the **inlined
  definition wins** and the load logs it, for the same reason it is inlined.
- Fog (v3) additionally saves `revealed_hexes` and the remaining `fog_stack`.
  The stack is server-only and must never reach `get_board_data`.

---

## 3. Validation

A map arriving over a socket is untrusted input, identical in status to a
`place_settlement` payload. Two layers.

**Layer 1 — `parse_map`, shape only.** Raises `InvalidPayload` from
`server/game/validation.py` so handlers report it the existing way. Allowlists:

- `map_version` is a known integer.
- `id` matches `^[a-z0-9][a-z0-9-]{0,47}$`. This is also the filename, so it is
  the path-traversal guard; nothing else may build a path from client input.
- `name` ≤ 64 chars, `notes` ≤ 512, `author` ≤ 64.
- `frame.radius` ∈ [1, 6]. Radius 6 is 127 hexes.
- ≤ 64 regions, ≤ 200 hexes total, ≤ 32 harbours, bounded before anything
  quadratic runs.
- Every hex key parses to three ints with `x + y + z == 0`, all divisible by 3.
- `kind` ∈ the enum, terrain ∈ the enum, tokens ∈ {2,3,4,5,6,8,9,10,11,12}.
- Counts are non-negative ints, `bool` rejected explicitly.

**A size note the old draft got backwards.** It proposed *tighter* payload caps
for map events. The cap is `MAX_PAYLOAD_BYTES = 8192`, applied globally in
`rate_limited()` (`state.py:212`) before any handler sees the payload, and there
is no per-event override table. A 200-hex map with `"remaining"` for the ocean
lands around 4–5 KB and fits; a 200-hex map with every hex listed explicitly, or
v2's fixed pools, will not. So either the format stays inside 8 KB — which is
the reason `"remaining"` is not merely a convenience — or `rate_limit.py` grows
`EVENT_PAYLOAD_LIMITS` and `save_map` / `preview_map` get a *larger* one. **A
test must assert that the largest map the validator accepts survives
`payload_too_large`**, or the editor will refuse to save exactly the maps people
work hardest on.

**Layer 2 — `validate_map`, meaning.** Returns `(errors, warnings)` as
structured `MapProblem`s. Errors block saving and starting; warnings are shown
and do not block.

| # | Rule | Level |
|---|---|---|
| R1 | Region ids unique; at most one region uses `"remaining"` | error |
| R2 | No hex claimed twice; every frame hex claimed exactly once | error |
| R3 | Every hex is inside the frame radius | error |
| R4 | **Pool size == region size**: `sum(terrain.values()) == len(hexes)` | error |
| R5 | **Token count == token-requiring tile count** in the pool | error |
| R6 | No token value of 7 | error |
| R7 | At least one land hex on the whole map | error |
| R8 | Every land *slot* has all six neighbours inside the frame — no land on the rim. A rim edge has one hex, so `is_sea_edge` refuses it and no ship can ever arrive | error |
| R9 | Every land slot is adjacent to at least one hex that can be sea, or the map has one component only. A landlocked second island is unreachable however many ships you build | error |
| R10 | Harbour bag size ≤ half the shortest coastline it could land on — checked against the *possible* coastlines, so a warning, since the draw decides | warning |
| R11 | Two red numbers may be dealt adjacent. Not an error: `no_adjacent_red_numbers` fixes it at generation if the table asked, and does not if they did not | warning, only when the rule is off |
| R12 | **More than one land component and `ships` off** — the second island is unreachable | warning at save, **error at game start** |
| R13 | Any region of kind `fog` | warning at save, **error at game start** in v1 and v2 |
| R14 | `robber_start` is a land slot, or `"auto"` with at least one desert in some pool | error |
| R15 | Land hex count vs `max_roads` / `max_ships`: warn if the supply looks too small to cross the map | warning |
| R16 | `suggested_victory_target` differs from the `(land − deserts) / 2` heuristic by more than 3 | warning |

R4 deserves its own note: `_create_hexes` carries three asserts and a comment
about a 20-entry resource list silently dropping a tile so no two boards had the
same mix. R4 and R5 are that bug promoted to a validation rule, which is the
whole argument for pools being explicit multisets rather than "fill the rest
with wheat". They are also what let fix (b) be a one-liner instead of a policy.

R12 is the honest inverse of the old R12. It used to say "multiple islands are
unplayable, full stop". Now it says "multiple islands need the `ships` rule",
which is a coherence check of exactly the kind `rules.dependency_problems`
(`rules.py:418`) already performs and reports through `INCOHERENT_RULES` in
`_start_game_locked`. **Put it there**, not in a new mechanism: the message
should read like the existing ones — *"Little Shores has two islands and needs
Ships"*. This is the one place where a map constrains the rules rather than the
other way round, and it is worth being loud about.

Where validation runs:

- `save_map` — before writing to disk. Errors reject the save.
- `preview_map` — before instantiating.
- `_start_game_locked` — re-read from disk and re-validate. Never trust that the
  file on disk is the file that was validated.
- `persistence.deserialize` — re-validate the inlined definition.

---

## 4. Editor UX

### 4.1 Constraints it has to live inside

- Vanilla ES modules, no build step, one entry point (`main.js`), views are
  sibling `<div>`s in `index.html` toggled with `.hidden`. No router.
- No-scroll layout at 1920×1080; detail lives behind popovers. Nothing may grow
  the page.
- `board-renderer.js` is a classic script exposing `window.BoardRenderer`; the
  camera is module-private. The editor reuses it rather than drawing its own
  canvas.
- Every element handle goes in `dom.js` as a named export.
- Reference `tokens.css` custom properties only, never literals.

### 4.2 What the renderer needs — most of it already exists

Re-checked against `board-renderer.js`. The old draft's asks have largely
landed:

- `clientToBoard`, `boardToClient`, `findNearestVertex`, `findNearestEdge`,
  `findNearestHex`, `attachCameraControls`, `wasPanning`, `computeLayout` are
  **all exported** on `window.BoardRenderer` (`:1985`). Nothing to negotiate.
- The palette is **no longer hardcoded**: `readPalette()` (`:70`) reads
  `--terrain-*` custom properties with `PALETTE_TOKENS` / `PALETTE_FALLBACKS`
  and caches on the theme signature. A new terrain (`gold`, v2) needs one entry
  in each plus one token in `tokens.css`. Note the deliberate exception: the
  ocean is *not* a token (`:87`) — "a light sea around it reads as a rendering
  fault" — so an editor that wants a lighter sea must override the fill itself,
  not add a token.
- **Still needed:** `BoardRenderer.invalidateLayout()`. `getLayout` (`:1068`)
  memoises on board *object identity*. An editor mutating `boardData.hexes` in
  place keeps drawing the stale layout, which is harmless for terrain and a real
  bug the moment a hex is added or removed. Verified unchanged; still in
  `OPEN-THREADS.md` §3. Either expose it, or have the editor replace the board
  object wholesale on every edit. **Replace the object** — it is cheaper to
  reason about, and a 127-hex layout recompute is nothing. Measure before
  optimising.
- **Still needed:** one optional argument on `renderBoard(boardData, canvasId,
  highlight, preview, overlay)` where
  `overlay = { regionOf: {hexKey: regionId}, colors: {regionId: cssColor} }`.
  Region tinting and nothing else. Backward compatible; existing calls pass four.

### 4.3 The screen

A fourth sibling of `#join-screen` / `#user-screen` / `#game-screen`:
`#map-editor-screen`, reached from a **Maps** button in the lobby and left by
**Done**. Lobby-only: editing is refused server-side while a game runs, so the
button carries the same disabled condition as the rules picker.

One full-height flex column, `min-height: 0` on the canvas so it never scrolls:

```
┌─ toolbar ───────────────────────────────────────────────────────┐
│ [Paint][Erase][Inspect] │ Region: [mainland ▾] [＋]              │
│                         │ [Pool ▾] │ [Preview] [Save ▾]         │
├─ canvas (flex: 1, min-height: 0) ───────────────────────────────┤
│            existing pan/zoom canvas, region-tinted              │
├─ status strip ──────────────────────────────────────────────────┤
│ 61 hexes · 3 regions · pool 6/7 ▲ · 2 islands · 2 problems ▸    │
└─────────────────────────────────────────────────────────────────┘
```

Everything with `▾` or `▸` opens a popover through the existing `popovers.js`
(`openPopover` / `togglePopover` / `repositionPopover`), which is already the
no-scroll mechanism the rest of the frontend uses. Nothing else is on screen.

No Harbour tool in v1 — harbours are a bag, edited in the Save popover as five
counters. That removes a whole interaction mode from v1 and costs nothing that
the auto-placement in fix (c) does not already give.

### 4.4 Painting

The tool is a mode, and the mode changes what a drag means. This is the one real
interaction collision: **drag currently pans**, and drag is the natural paint
gesture.

Resolution — paint on drag, pan on modifier:

- **Paint / Erase:** primary-button drag paints continuously. Panning needs
  space-held drag, middle button, two-finger scroll or the arrow keys, all
  already bound by `attachCameraControls`. Wheel zoom unchanged.
- **Inspect:** drag pans as it does in game.
- The editor's pointer handlers register *before* `attachCameraControls`, and
  consult `wasPanning()` the way `board.js:88` does.

Painting assigns the hex to the selected region and removes it from whichever
held it. Erase returns it to the `"remaining"` region if one exists, otherwise
leaves it unassigned and R2 flags it. Region colours come from a fixed palette
of eight, cycling, overridable per region.

Keyboard: `1`–`9` select region, `P`/`E`/`I` select tool, `Ctrl+Z` one level of
undo (a snapshot stack of the map document, capped at 30 — real undo history is
v2).

### 4.5 The pool popover

```
 mainland                    kind [ main ▾ ]
 ────────────────────────────────────────────────────────────
 wood  [−] 2 [+]    brick [−] 1 [+]    desert [−] 1 [+]
 wheat [−] 2 [+]    sheep [−] 1 [+]    sea    [−] 0 [+]
 ────────────────────────────────────────────────────────────
 tokens  2·[0] 3·[1] 4·[1] 5·[1] 6·[1] 8·[0] 9·[1] 10·[1] 11·[0] 12·[0]
 ────────────────────────────────────────────────────────────
 tiles 7/7 ✓        tokens 6/6 ✓        [Auto-fill]  [Done]
```

Anchored with `boardToClient()` inside the board container, the way
`placement.js` anchors its confirm control — proven not to resize the canvas,
which is what matters in a no-scroll layout.

The two badges are the whole authoring-time validation story: they mirror R4 and
R5 exactly, turn red when they disagree, and mean the user never sees a server
rejection for the most common mistake. **Auto-fill** proposes a pool scaled from
the standard 19-hex mix to the region's size — the fastest path from "I painted
an island" to "it is playable".

### 4.6 Preview

**Preview** emits `preview_map { map, seed? }`; the server validates,
instantiates with a fresh seed, and returns a payload of the shape
`get_board_data` produces. The existing renderer draws it unchanged.

Do the preview **server-side**: same code path the real game uses, so what you
preview is what you play, and no second implementation of pool drawing in
JavaScript to drift. One round trip per press, which is nothing.

Preview shows the drawn board, **the island count and their sizes from
`islands()`**, and any warnings. Pressing it repeatedly is how you learn a
pool's variance, which is the thing you actually want to know about a randomised
map — and with a `sea` tile in an island pool, the island count is what varies.

### 4.7 Save, load, share

**Save ▾** opens a popover: name, harbour counters, Save, Save as copy, and a
list of existing maps with Load / Duplicate / Delete. Errors render through the
existing `showNotice(message, 'error')`.

**Delete requires confirmation and is refused while a game uses the map.**
Decided; §5.3 has the wire form. Deleting the map a running game was built on
would not corrupt the game — the definition is inlined in the save — but it
would make the lobby's `board_map` selection dangle, and irreversible deletion
behind a single click is a misclick waiting to happen.

Sharing between players at one table needs no new machinery: **maps live on the
server**, there is one server per table, and selecting a map is a rule, so it
rides the existing `rules_changed` broadcast with the same freeze-on-start
semantics as every other rule.

---

## 5. Storage and sharing

### 5.1 On disk

One JSON file per map in `${CATAN_DATA_DIR}/maps/<id>.json`. `DATA_DIR`
(`config.py:31`) is already the "runtime state lives outside the repo tree"
directory and tests already redirect it to a temp dir, so map tests get
isolation for free.

New module `server/game/map_store.py`:

```python
MAPS_DIR = os.path.join(config.DATA_DIR, "maps")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

def list_maps() -> list[dict]      # [{id, name, author, hexes, regions, islands_min_max, problems}]
def read_map(map_id) -> dict       # raises UnknownMap
def write_map(map_id, data)        # atomic, temp + fsync + os.replace
def delete_map(map_id)
```

`write_map` reuses the atomic-write pattern from `persistence.save` verbatim —
temp file, flush, fsync, `os.replace` — for the reason stated there.

Every path is built as `os.path.join(MAPS_DIR, f"{map_id}.json")` after `SLUG`
matches, and never any other way. That single rule is the whole path-traversal
defence, which is why `id` is validated in layer 1 rather than later.

Built-in maps ship read-only in `server/game/builtin_maps/*.json`, list with
`"builtin": true`, and refuse writes and deletes. Duplicating one is how you
start from it.

`list_maps` runs over a directory a human may have dropped files into. It
validates each; a file that fails becomes a listing entry with `problems` set
rather than an exception that breaks the whole list.

### 5.2 Selecting a map

**Decided: `board_map` lives in `rules`.** It inherits sharing, locking and
persistence, and the cost the old draft worried about is already paid:

- `rules.py` already has `CHOICE` (`:22`), used by `board_layout` and
  `turn_order`. `coerce` (`:600`) already falls back to the default on an
  unknown value, matching the "clamp and continue, never reject a lobby
  setting" policy.
- `lobby.js` already renders a `<select>` for `type === 'choice'` (`:232`),
  with a comment recording that the beginner and large maps were unselectable
  until it did. Nothing to coordinate.

So: `board_layout` gains a fourth option `custom`, and a new `CHOICE` rule
`board_map` names which. `catalogue()` computes `board_map`'s options from
`map_store.list_maps()` at call time, so a newly saved map appears in every
client's picker on the next `rules_changed` with no frontend change. That is the
property the registry was designed for and the main argument against a
standalone `selected_map` on `GameSession`.

Two consequences to handle:

- `board_map`'s options are dynamic, and `coerce` falls back to the default when
  a value is not in `options`. A map deleted between selection and start
  silently reverts the table to some other map. **`_start_game_locked` must
  re-read the selection and refuse with a named error** rather than start a
  game on a board nobody chose.
- `rules.py` currently imports nothing from the rest of `game`. `catalogue()`
  calling `map_store` introduces an import. Keep it lazy and inside the
  function, or inject the list — a rules registry that cannot be imported
  without touching the filesystem will be felt by every test in the suite.

### 5.3 Socket events

Following the existing convention — imperative client→server, past-tense
server→client, snake_case, errors as `{code, message}`, all through
`rate_limited()`:

| Direction | Event | Payload |
|---|---|---|
| c→s | `request_maps` | — |
| s→c | `map_list` | `{maps: [{id, name, author, hexes, regions, builtin, problems}]}` |
| c→s | `save_map` | `{map: {...}}` |
| s→c | `map_saved` | `{id}` — plus a fresh `map_list` and `rules_changed` broadcast |
| c→s | `delete_map` | `{id, confirm: true}` |
| s→c | `map_deleted` | `{id}` — plus a fresh `map_list` |
| c→s | `preview_map` | `{map: {...}, seed?: int}` |
| s→c | `map_preview` | `{board: {...}, warnings: [...], islands: [size, ...]}` |

`delete_map` refuses without `confirm`, refuses a builtin, refuses while
`session.game.game_state == "started"`, and refuses when `board_map` names it —
`MAP_IN_USE`. The confirmation is client-side too (the popover asks), but the
flag is on the wire so the server is not relying on the client having asked.

Authorisation follows `set_rules`: anyone in the lobby may save, select or
delete, refused once a game is running. The old draft's "only the author may
delete" is dropped — identity here is payload-based by design
(`OPEN-THREADS.md` §6), so author-matching is theatre. The threat model is a
misclick, and confirmation is the honest answer to a misclick.

### 5.4 Import and export

v2. A textarea in the Save popover that dumps and accepts JSON — the map *is*
the text file, and copy-paste is the transport. No upload endpoint, no new
dependency. Pasted JSON goes through the same `parse_map` + `validate_map` as
everything else, and hits the same 8 KB question as §3.

---

## 6. Modifiers, and how the map format should ride on them

Another agent is turning `Game.get_cost` (`game.py:954`), production (the inline
`self.rules['city_production'] if building_type == 'city' else 1` at
`game.py:843`, becoming `production_for(vertex, hex)`) and `Game.next_dice`
(`game.py:1044`) into hooks, so a rule can *apply* rather than only be read
(`OPEN-THREADS.md` §2, which asks for this to land **before** the map creator
precisely so the map creator does not add read sites 56–70).

The map format must not invent a parallel mechanism. The rule:

- **v1 contributes no modifiers at all.** A map decides what terrain is where
  and nothing else. Every gameplay knob the map might want — cost changes, a
  bonus on a number, a per-region yield — already has, or will have, a home in
  `rules`.
- **When per-region production arrives (v2+), it is a modifier registered
  against `production_for(vertex, hex)`.** `instantiate` returns
  `MapInstance.modifiers` as inert data; `Game.__init__` hands it to whatever
  registry the funnel work creates, alongside the modifiers the rules
  contribute. `maps.py` never computes a yield and never imports the engine.
- **Order is the funnel's problem, not the map's.** Two modifiers touching
  production have no defined order today; that is the whole reason for the
  funnel. A map that shipped its own resolution order would have to be
  rewritten when the funnel picks one.
- **Gold fields are the test case.** A gold hex is a terrain name, a production
  modifier that yields "choose a resource", and a `pending_choice`. Two of the
  three exist. The third — the pending-choice *client* — does not exist at all
  (`OPEN-THREADS.md` §1: the protocol is implemented and tested and **nothing
  renders it**, and a card that opens a choice today freezes the table until a
  30s timeout). So gold is blocked on the choice UI, not on the map format, and
  the map format should reserve the word `gold` and do nothing else with it.

If the funnel has not landed when v1 starts, nothing in v1 blocks: v1 adds no
`self.rules[...]` reads beyond `board_layout` and `board_map`.

---

## 7. Staging

### v0 — groundwork

1. Fixes (a), (b) and (c) from §2.1, in `board.py`, each with a test that fails
   before it. (a) and (b) need a two-island fixture, which today means the
   `split_the_board` helper in `tests/game/test_islands.py`; (c) can use it
   directly — it already produces the 18-of-54 walk.
2. `sort_hex_keys` and `takes_a_token` in `maps.py`.
3. `map_store.py` with the slug guard and atomic write, plus tests.

Nothing user-visible. Fix (c) is worth landing on its own regardless of whether
the map creator is ever built: it is a latent wrong answer in the base game the
moment any board grows a second coastline.

### v1 — custom maps that play

The smallest genuinely useful version, and it is genuinely useful because ships
exist: **a map you paint, save, preview, select in the lobby, and play — with
more than one island, reachable by ship, scoring island points.**

- `maps.py`: `parse_map`, `validate_map`, `instantiate`, and the builtin
  `standard` / `beginner` / `large` maps expressed in the format. **Do the
  builtins first** — proving the format can express today's three boards, hex
  for hex and token for token against `test_map_layouts.py`'s existing
  assertions, is the best possible test of the format and the cheapest place to
  find out it is wrong.
- The branch in `_generate_board`, plus `_apply_map_instance`.
- `map_definition` inlined into the save; no `SAVE_VERSION` bump.
- `board_layout: custom` + `board_map` in `rules.py`; the multi-island/`ships`
  coherence check in `dependency_problems`.
- Socket events from §5.3.
- The editor: paint, erase, region create/rename/recolour, pool popover, harbour
  bag, preview, save, load, duplicate, delete-with-confirmation, one-level undo.
- Tests: the custom map added to the existing cross-process determinism loop; a
  seed sweep asserting the pool multiset is exactly reproduced on the board and
  no token sits on sea or desert; `parse(to_json(defn)) == defn`; one refusal
  test per validation rule; the payload-size test from §3; and **one browser
  test that plays a settlement onto a second island of a hand-made map**, since
  `OPEN-THREADS.md` §5 records that no seafaring game is played to a winner
  anywhere.

**v1 explicitly does NOT:**

- **Hand-place harbours.** A bag of types, spaced automatically. No Harbour
  tool, no `harbours.places[]`, no edge keys in the map file at all — which also
  means v1 never has to reason about `canonical_edge_key` in a map file.
- **Fixed pools.** Shuffled only. You cannot reproduce a printed scenario
  diagram tile for tile. Deferred, decided, and cheap to add later: `mode` is
  already in the format. (~30 lines in `maps.py`, but it doubles the editor's
  per-hex interaction surface, because you must then be able to set one hex's
  terrain *and* its number directly.)
- **Fog.** `kind: "fog"` parses and previews; starting refuses.
- **Gold fields.** Blocked on the pending-choice client, not on this.
- **Scenario setup rules.** `kind: "island"` is inert: nothing stops a starting
  settlement going on a far island, and nothing tracks a home island beyond what
  `record_island_settlement(award=False)` already does at setup. This is the
  biggest single thing separating "a custom map" from "The Four Islands".
- **Per-map victory target.** A suggestion the editor and lobby display; the
  `victory_target` rule still decides.
- **Any map-level modifier**, per §6.
- ~~**5–6 player frames.**~~ `max_players` became a catalogue rule (0 = the server's default), `PLAYER_COLORS` carries six, and `six-shores.json` proves the format can express a board for them.
- **Import/export, undo history, thumbnails.**
- **Concurrent editing.** One game per process, one table, last write wins. The
  players are in the same room and can talk.
- **Any migration path for v1 maps.** `map_version` exists so v2 can refuse them
  loudly; nobody has a library yet.

### v2 — depth

Fixed pools and per-hex editing, hand-placed harbours on edges, import/export
textarea, larger frames, gold once the pending-choice client exists, per-region
production modifiers riding the funnel.

### v3 — scenarios

Setup restrictions (`kind: "island"` becoming mechanical), the fog stack and
lazy reveal, per-player home islands, 5–6 player frames. This is where the
published scenarios become reproducible, and it is a separate project.

---

## 8. Risks

**Fix (c) moves harbours if it is done carelessly.** Every seeded board in the
suite, and both browser suites, are pinned to where harbours currently land. The
one-ring path must make the identical sequence of `rng` calls. Assert it: build
the `random` layout at a fixed seed before and after and compare
`harbour_edges(game)`.

**Fix (a) is invisible until it is not.** Slots and land are identical for all
three built-in layouts, so the fix changes no existing behaviour and no existing
test can prove it works. Its test must use a layout whose pool contains `ocean`
— which is the reproduction in §2.1, and which is the only way to reach the bug.

**`getLayout` memoises on board object identity.** Unchanged and verified. An
editor mutating hexes in place draws a stale layout the moment a hex is added or
removed. Mitigation in §4.2: replace the board object per edit.

**Paint-drag versus pan-drag.** The modifier-to-pan proposal in §4.4 is the
standard resolution but it is a learned gesture. If it tests badly the fallback
is click-per-hex, tedious on a 127-hex frame but unambiguous.

**Board size versus piece supply.** A 127-hex board with 15 roads and 15 ships
per player is a different game, not a bigger one. R15 warns; it cannot decide.

**Untrusted maps are a bigger attack surface than any existing event.** A map
payload is nested, variable-length, and turns into a filesystem path. The
mitigations in §3 and §5.1 are not optional: bounded sizes before any traversal,
slug regex before any path join, re-validate on every read including from disk.

**A big map is slow in places nobody has measured.** `islands()` is a flood fill
over every land hex and is called *per vertex* by `island_of_vertex`
(`seafarers.py:328`), which `record_island_settlement` calls on every
settlement. Fine for 19 hexes; a 127-hex board with ships doubles the graph and
this becomes O(board) per placement. Not a v1 blocker — measure before caching,
and if you cache, the invalidation point is "terrain changed", which after
generation is never.

**The map format can express boards the harbour spacing cannot serve.** A map
of nine 1-hex islands has nine 6-edge coastlines and a bag of nine harbours;
`len(ring) // 2` gives each ring three, the allocation gives each one, and the
result is defensible but arbitrary. `_assign_ports` already logs and truncates
in this situation rather than failing. Keep that behaviour and let R10 warn.

---

## 9. Still needs the owner to decide

Everything the old §7 listed as open is now settled — `sea` vs `ocean`
(translate at the boundary), islands preview-only (obsolete, ships exist), who
may delete (anyone, with confirmation, refused while in use), fixed pools
(deferred past v1), `board_map` in `rules` (yes). What remains:

1. **Is `kind: "island"` being inert in v1 acceptable?** It means the editor
   offers a label that changes nothing: you can paint a "far island" and a
   player may put a *starting* settlement on it. The alternative is one setup
   restriction in v1 — "starting settlements only on regions of kind `main`" —
   which is maybe 20 lines in `place_settlement` and one line in the map format,
   and is the single cheapest step toward a real scenario. I lean toward
   including it and would rather be told now. **If you want it, say so before
   §7's v1 is scoped**, because it is the one exclusion above that is cheap
   enough to argue about.

2. **Does the payload cap move, or does the format stay under 8 KB?** §3. It
   decides whether `rate_limit.py` grows a per-event table. My recommendation:
   stay under 8 KB in v1 and let `"remaining"` do the work; revisit when fixed
   pools land in v2, which is when it will actually break.

3. **Frame radius cap of 6 (127 hexes).** (`MAX_PLAYERS = 4` is no longer part of this: it is a rule, and a six-player board ships.) A Seafarers 5–6
   player scenario needs both raised. Is that ever in scope, or is this a
   four-player table forever? It changes nothing in v1 either way, but it
   changes whether the editor should warn about board sizes no table here can
   fill.
