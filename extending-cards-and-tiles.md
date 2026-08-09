# Extending the engine: cards and tiles

Two registries make cards and tiles programmable as self-contained units:

- `server/game/cards.py` — a **card** is a descriptor + a resolver, registered in
  one place; the engine plays any card through one lookup.
- `server/game/tiles.py` — a **terrain** is a descriptor of what a tile produces,
  whether it takes a token, its commodity, and whether it is water; the map
  validator, board builder, production and robber all read from it.

The `Game` object is the API a resolver is written against (`get_player`, `bank`,
the robber and knight operations, …). Adding a card or tile is a `register(...)`
call with its own behaviour — no edit to any dispatch site.

## The one rule that governs all of this

**Never add content the engine or the client ignores.** A card that can be held
but never played, or a tile that appears on a board but renders blank, is worse
than not adding it — and the browser suite fails the build for exactly that
(`tests/test_browser_progress_cards.py::TestEveryCardCanBeReached`). The registry
is the *engine* half. Wire the whole path below, or don't add it.

---

## Adding a card

### An official Cities & Knights progress card

1. **Descriptor** — add an entry to `PROGRESS_CARDS` in `progress_cards.py`
   (`id`, `name`, `deck`, `count`, `timing`, `needs_target`, `victory_points`,
   `summary`). The three decks must stay 18/18/18 — an import-time guard
   (`_check_deck_sizes`) refuses a miscount.
2. **Effect** — add a method `_progress_<id>(self, player_name, target)` on
   `CitiesKnightsRules` returning `{'success': bool, 'error': str, ...}`. The
   registry builds a delegating resolver for every non-immediate progress
   descriptor automatically, so no dispatch edit is needed. (A card worth a
   victory point on sight — `timing: "immediate"` — has *no* method; it is scored
   on draw, not played.)
3. **Client flow** — the card must be playable in the browser: `needs_target`
   drives the client prompt, and `handlers/cities_knights.py` validates the
   target. A progress card with no client flow fails `TestEveryCardCanBeReached`.

### A base-game development card

1. **Register** it in `cards.py`: `register(Card(family=cards.DEV, id=..., name=...,
   deck=cards.DEV, timing="turn", needs_target=None, victory_points=..., resolve=fn))`.
   `play_dev_card` merges the resolver's returned keys into its result.
2. **Deck** — add its count to `dev_cards_deck` in `bank.py`, or it is never drawn.
3. **Follow-ups** — a card that owes a second action (Year of Plenty, Monopoly)
   sets a pending flag on `Game` and redeems it in a separate method; see
   `_dev_invention` / `use_invention` for the pattern.

### A homebrew / self-contained card

`register(Card(id=..., family="homebrew", ..., resolve=your_fn))` with a
free-function resolver — no core dispatch edit. It still needs a way to be played
(a client flow, or a chat command) to be reachable.

---

## Adding a tile

### The registry (engine half)

```python
register(Terrain("river", "river", produces=None))              # land, pays nobody
register(Terrain("fish", "fish", produces=None))                # a shoal, no token
register(Terrain("swamp", "swamp", produces="brick", commodity=None))
```

Registering a terrain gives you, for free: map validation (`maps.TERRAIN_TYPES`),
number-token eligibility (`maps.takes_a_token`), the `sea`→`ocean` rename
(`hex_type_of`), production (`produces`), and the robber/pirate land-vs-sea checks
(`is_sea`).

### What a tile still needs beyond the registry

- **A map that places it.** A registered terrain nobody deals is inert. Add it to
  a map's pool (see `map-creator.md`) or the map editor.
- **A client fill.** Add the terrain to the `TERRAIN_*` map in `board-renderer.js`
  and a `--terrain-<name>` token in `tokens.css` — **both light and dark** — or the
  hex draws blank.
- **Choice-based production.** The plain `produces` field only covers a fixed
  yield. A tile that yields a *choice* (gold → any one resource) needs a
  production modifier / pending-choice; this is why `gold` is not in the base set
  yet.

---

## Where the proof lives

The seam is pinned by `tests/game/test_card_registry.py` and
`tests/game/test_tile_registry.py` — each registers a throwaway card/tile and
asserts it flows through the helpers. Copy those patterns for a new one.

## Files

| Concern | File |
|---|---|
| Card registry + dev resolvers | `server/game/cards.py` |
| Progress card descriptors | `server/game/progress_cards.py` |
| Progress card effects | `server/game/cities_knights_rules.py` |
| Dev card deck composition | `server/game/bank.py` |
| Card client flow / validation | `server/handlers/cities_knights.py`, `server/static/js/` |
| Terrain registry | `server/game/tiles.py` |
| Terrain rendering | `server/static/js/board-renderer.js`, `server/static/css/tokens.css` |
| Map authoring | `map-creator.md` |
