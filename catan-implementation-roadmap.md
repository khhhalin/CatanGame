# Catan — implementation roadmap (remaining work)

The whole backlog, prioritised, decomposed enough to hand each item to one agent
as a vertical slice (rules/handlers + client + tests, engine core first,
failing-test-first, no engine branch on an expansion name). Method is the proven
one: **sequential on the shared tree**, one item at a time, verify green, batch
into releases; pushes are live deploys and wait for the owner.

Sizes: **S** ≈ one focused session, **M** ≈ a scenario-sized slice, **L** ≈ a
multi-part feature.

---

## Tier 0 — in the current unpushed patch (DONE)
- `bbdbc7f` scenario presets deal their scenario board (was: random board).
- `a67b534` board no longer collapses to a strip on a narrow/tiled window.
- `063c396` scenario side-panels no longer leak across T&B scenarios.

Ready to ship as **v3.6.1** whenever the owner says push (plus whatever else
below lands first).

---

## Tier 1 — playability-blocking (make every scenario fully playable)

### 1. E&P cargo/crew economy → unlock Pirate Lairs + Spices  **(L — biggest gap)**
Today only the **Fish** mission is UI-playable; Lairs and Spices need a crew
aboard a ship and there is no client path to put one there. Engine methods exist
in `cargo.py`/`transport.py`; the wiring is missing.
- **Handlers (add):** `build_crew`, `build_settler`, `found_settlement_from_ship`
  (engine methods exist, no socket handler). `load_transport_ship`,
  `unload_transport_ship`, `pickup_crews_from_lair` (handlers exist, no client).
- **Client (`ep.js`/`seafarers.js`):** build a crew/settler onto a ship at a
  harbour settlement; load/unload cargo; found a new settlement from a settler
  ship; pick up crews from a captured lair. Gestures mirror the existing
  ship-move/mission gestures.
- **`transshipping`:** a declared rule with NO engine implementation (CLAUDE.md
  forbids a rule the engine ignores). **Decision:** implement cargo-transfer
  between adjacent ships, OR remove the dead rule + its dependency/preset refs.
- **Tests:** browser — Pirate Lairs and Spices missions played end-to-end from
  scratch (build crew → load → sail → land/befriend → deliver → score), with NO
  hand-injected cargo. A natural or one-action-short win on each.

### 2. Barbarian Attack — knight **movement** gesture  **(M)**
Placement works; movement has engine (`move_barbarian_knight`) + handler but no
board gesture. Add a two-tap gesture (select a knight on a castle-adjacent path →
tap a destination path, BFS-legal ≤3 free / ≤5 for 1 grain). Client + browser
test (a knight visibly moves).

### 3. T&B main — drive-off-barbarian gesture  **(S/M)**
Engine + handler exist; no picker gesture. Add an "adjacent barbarian → drive
off" gesture (baggage-gated), plus surface the 7-forced barbarian move clearly
(the `#tb-move-barbarian` gesture exists; confirm the prompt reads well). Client
+ browser test.

---

## Tier 2 — completeness gestures / shared gaps

### 4. Fishermen — old-boot pass button  **(S)**
`pass_old_boot` has engine + handler + test; add a panel button. Client.

### 5. Fishermen — starting-settlement fish (rulebook 497)  **(S)**
A second setup settlement adjacent to a fishing ground draws 1 fish at setup.
Engine + test.

### 6. Opponent-to-opponent gold trading  **(M, shared by E&P + T&B)**
Both `gold` (E&P) and `gold_coins` (T&B) are tradeable per the rules but there is
no gold-in-trade payload path. Add gold to the trade offer/accept payload +
validation + trade UI. Engine + client + tests. Closes the one documented gap in
Rivers and E&P at once.

---

## Tier 3 — fidelity (low; documented simplifications, none block play)
7. **Caravans:** multiplayer bid *negotiation* depth (today: largest-single-bidder
   fallback) and caravan **merging** (chains meeting at an intersection).  (M)
8. **T&B main trade-hex plaza:** model the printed central-plaza vertex + four
   interior paths + three un-buildable sea-border paths (today: one land corner,
   2 sea-paths/hex not 3). A board-format enhancement.  (M)
9. **T&B main Swift Journey:** a distinct second movement phase (today: fresh
   points).  (S)
10. **Barbarian Attack:** prompt for Treason/Intrigue targets (today: auto-target);
    disable a conquered building's harbour for trade (today: only VP + production
    lost).  (S each)

---

## Tier 4 — known layout bugs (pre-existing, not from the expansion work)
11. **C&K 4-player floating tray off-screen at 1920×1080** — the
    `test_browser_layout.py::TestCitiesAndKnightsFits` failures (confirmed
    pre-existing via `git archive HEAD`). Same class as #12.  (M)
12. **`#side-tabs` clipping** on a 4-player / every-expansion table — from the
    v3.2.1 TEST 6 left-rail relayout (`test_browser_tester_round.py::…
    test_nothing_scrolls_and_nothing_is_clipped`).  (S/M)

Both are overlay-layout fixes in `style.css`; good to batch together, each with a
bbox non-overlap / no-clip browser guard at 1920×1080 and 1600×1000.

---

## Tier 5 — future expansions (roadmap pending)
A research agent is cataloguing official + unofficial Catan expansions/variants
into `catan-expansions-research.md` (rules, state, board, scoring, how each
decomposes into individual rules). The ranked "next targets" from that document
become this tier — new expansions built the same way (a batch of individual
switchable rules + presets + built-in maps), one scenario/mechanic per slice.

---

## Suggested sequencing
1. **Ship v3.6.1** (Tier 0 — the three fixes already done) whenever the owner
   pushes; it makes every scenario reachable + interactive, the highest value per
   effort. Fold in Tier 4 (layout bugs) if a slightly bigger patch is wanted.
2. **Tier 1** next, in order 1→2→3 — E&P cargo economy first (it unlocks the most
   gameplay), then the two barbarian gestures. One release when Tier 1 lands.
3. **Tier 2** (completeness) as a following batch.
4. **Tier 3** fidelity only if a scenario feels thin in real play.
5. **Tier 5** new expansions once the research lands and the owner picks targets.
