# HANDOFF — start here

You are taking over a multiplayer Catan web game: **Flask-SocketIO + vanilla JS**,
in-memory game state, one server process. It is live at
**https://catangame.onrender.com**. This file orients you; the deep contracts
live in the docs listed at the bottom and are **not** repeated here — read them.

---

## 1. The deploy model — read before you `git push`

- **A push to `fork/main` is a live deploy.** Render auto-builds and serves
  `fork` = `git@github.com:khhhalin/CatanGame.git`, branch `main`, on every push.
  There is no staging step. Commit locally freely; push to `main` only when you
  mean to ship.
- **`origin` = `rub6y/CatanGame` is a stale upstream.** Don't push there expecting
  a deploy; it isn't the one Render watches.
- The container is built from the `Dockerfile` (`python:3.13-slim`) and copies
  `server/` + `CHANGELOG.md` — **no `.git`**. So a deployed server can't run
  `git`: the build id shown in the on-screen panel is **the newest heading in
  `CHANGELOG.md`**. Cutting a release therefore means editing files, not tagging.
- Run in production exactly as Render does: `gunicorn -w 1 --threads 100 wsgi:app`.
  **One worker on purpose** — all state is in process memory. Two workers = two
  divergent games. Never `pkill -f gunicorn` on a shared box; kill by PID.

**Cutting a release** (the panel/CHANGELOG contract, enforced by
`tests/test_changelog.py`): bump `VERSION` at the repo root (patch / minor / major)
and rename the top `## unreleased` heading — or add a new top heading —
`## v<the new VERSION> — <YYYY-MM-DD HH:MM>`. `VERSION` and that heading must
agree. Entry lines are `- **Fixed|New|Known issue** <one line>`.

---

## 2. Branches — what is live, what is not

| Branch | Remote | HEAD | State |
|---|---|---|---|
| `main` | `fork/main` | `ff7564d` = **v2.1.0** | **LIVE.** Base + Cities&Knights + Seafarers + the icon UI + rule mutual-exclusions + the versioning system + the full v2.0 UI overhaul + the v2.1 floating-board relayout. |
| `ep` | `fork/ep` | `47507b1` | **Explorers & Pirates integration. NOT deployed, NOT playable yet.** Pushed to `fork/ep` as a backup only; Render does not build it. |

**Do NOT merge `ep` into `main` until E&P is actually playable** (owner decision).
Its presets already appear in the lobby, so shipping it half-built would let a
table select a broken, unplayable expansion. Everything on `ep` is additive and
every E&P rule defaults OFF, but the client UI/handlers are incomplete — see §6.

---

## 3. Run & test locally

```bash
# deps into a venv (never system Python); repo ships a .venv
./.venv/bin/python -m pytest -q            # fast suite (~1118 tests)
./.venv/bin/python -m pytest -q -m slow    # browser suite (~358, ~10 min) — the release gate
./.venv/bin/ruff check server tests        # lint, must be clean
python -m flask --app wsgi run             # dev server (never in prod)
```

The **browser suite (`-m slow`) is the real gate** — it is the only layer that has
ever caught a regression a player would hit (the unit suite asserts server state,
and every player-facing bug so far left server state correct). Run it **once**, not
three times; a genuine flake is confirmed by re-running the one test in isolation,
not by re-running the whole suite. See `CLAUDE.md`.

---

## 4. The conventions that are not optional

All of these are in `CLAUDE.md` / `coding-rules.md` and every one exists because
something broke without it. The load-bearing ones:

- **Rules are individual; there are no expansions in the engine.** ~60 individually
  switchable rules. **No engine code may branch on an expansion name** — branch on
  the specific rule (`rules['knights']`, never "are we playing C&K").
  `grep -rn "rules\['cities_and_knights'\]" server/` must stay empty, and the same
  for any expansion you add. A preset just ticks rule ids; the engine never learns
  a preset existed. A rule may *suggest* a victory target, never overwrite one.
- **A test earns its place only if it can fail for a reason a player would notice.**
  A bug fix starts with a test that fails *for the bug's reason*. Hardcoded lists
  are asserted against the **generated board**, never against another copy of the
  literal.
- **Shared checkout discipline.** Historically several agents committed into one
  tree. **Never `git stash/checkout/restore/reset`** here — they act on the whole
  tree and eat others' uncommitted work. **Stage and commit by explicit path**
  (`git commit -- <paths>`), never `git add -A` / `commit -a` / a bare `commit`.
  To diff against a parent commit, `git archive <sha> | tar -x -C "$(mktemp -d)"`.
- **`.claude/settings.json`** shows as modified — that is the owner's local
  `worktree.baseRef` edit. Leave it uncommitted.

---

## 5. Architecture map

- `server/game/` — the engine. `game.py` (state + `to_dict` serialization the
  client renders from), `rules.py` (the catalogue + `EXCLUSIONS` + dependency
  refusals), `seafarers.py`, `cities_knights.py`, `trade_rules.py`, `maps.py`
  (map format v2), `persistence.py`. `ep.py` and the `ep_*`/`gold`/`harbor_*`/
  `transport`/`exploration`/`cargo`/`missions` modules live on the `ep` branch.
- `server/handlers/` — socket.io handlers; untrusted payloads land here.
  `state.py` holds `reject(code, message)` (emits `error` to the offending client
  only; it surfaces as `console.warn('Server rejected action:', …)` + a notice).
- `server/static/js/` — vanilla ES modules. `board-renderer.js` (canvas; exposes
  `window.BoardRenderer`), `placement.js` (the ✓/✗ placement flow), `net.js`
  (socket wiring), `hand.js`, `trade.js`, `panels.js`, `scoreboard.js`,
  `seafarers.js`, `overlays.js` (sizes the floating layer), `seam.js`.
- `tests/` mirrors `server/`. `tests/browser_harness.py` drives real browsers via
  Playwright; `tests/test_browser_*.py` are the end-to-end gate.

---

## 6. v2.1 UI architecture — the thing that will bite you

The v2.1 relayout floats the standing info over a **full-width board**: players
top-left, the physical hand of cards bottom-centre, the dice tray bottom-right,
and a unified build+trade tray bottom-left. **All of these live in
`#board-overlays`** — a `position: fixed; z-index: sticky` element that
`overlays.js` sizes to the board's bounding rect on every layout.

The consequence, and the trap:

- `#board-overlays` is a **separate stacking context that paints above everything
  in `#game-screen`.** A board popover (the placement ✓/✗ `#placement-confirm`,
  the knight actions `#knight-actions`) that lives inside `.game-board` will be
  drawn **behind** the floats, and at a bottom/corner hex the hand or a tray
  covers it — unclickable, for a real player too. Raising its `z-index` does
  **nothing** (different stacking context). The fix, already applied, is to
  **move the popover node into `#board-overlays`** so it shares the floats'
  context, then give it a higher z-index there. If you add another board-anchored
  popover, put it in `#board-overlays`, not `.game-board`.
- **The floats overlap the interactive board.** A vertex/edge/hex sitting under
  the hand or a tray cannot be clicked where it is drawn — a player pans it into
  the clear (the board zooms/drags). The browser harness simulates this with
  `_reveal_target` (zoom + pan + restore) in `click_edge/click_hex/click_vertex`.
  When a seafaring/placement test "can't reach" a target, this is why.
- The board↔right-panel **seam is drag-resizable** (`#board-resizer`, `seam.js`).

Approved mockups (durable): v2.0 overhaul
`https://claude.ai/code/artifact/74c29177-9ff0-4ece-8a02-aec1dee6a2ec`;
v2.1 relayout (rev.5 is the target)
`https://claude.ai/code/artifact/9ffd320b-c48b-41ae-8633-617cc2f13b90`.

---

## 7. In flight / planned

**Explorers & Pirates → v1.1 (branch `ep`).** Plan: `explorers-and-pirates-plan.md`.
- **Done:** Waves 0–3 and the Wave 4 missions *container* — 21 E&P rules, the
  `ep` state container, gold currency, harbour settlements, transport ships, the
  E&P pirate (ship-instead-of-robber + steal + gold tribute), exploration,
  cargo (settlers + crews), a movement phase, and the missions tracks/markers/
  lead-card VP.
- **Next:** Wave 4 mission *modules* (lairs, fish, spices); **Wave 5** = the
  renderer, `server/handlers/ep_*.py`, and the five scenario maps; a dedicated
  **E&P persistence pass** (gold/harbour/settlers/crews/missions are not
  serialized yet). Then E&P is playable → cut v1.1. Only *then* consider `ep`→`main`.

**Map editor (main).** The engine half is shipped (`maps.py`, `map_store.py`,
four built-in maps, `board_map` rule, `preview_map` over the wire). **There is no
editor UI.** Spec + handoff in `map-creator.md` §5. This also unblocks
`island_victory_points`, which can only score on a multi-landmass board.

**Everything else deferred / known-broken:** `OPEN-THREADS.md` is the live ledger —
client-side copies of server truth, magic numbers that could be rules, `/skip`
not checking whose turn it is, untested touch input and screen-reader paths, the
`python:3.13` deploy vs `3.14` test gap, and the `audit-report.md`-in-git-history
decision. Read it before starting anything new.

---

## 8. Known flakes (not bugs)

- `test_browser_a11y.py::test_every_visible_label_meets_wcag_aa` intermittently
  fails on the **`#start-game-btn`** in the lobby under full-suite load — it
  measures the button mid-CSS-transition (white text on a background still
  fading in) and reads a low contrast for one frame. **Passes in isolation** on
  both themes. Confirm-in-isolation before treating it as real.

---

## 9. Doc index

- `CLAUDE.md` — which tests are worth writing; the rules-are-individual invariant;
  the shared-worktree rule. **The testing contract.**
- `AGENTS.md` — commands, project structure, style.
- `coding-rules.md` — Part I (no dev server in prod), Part V (socket handlers,
  fixtures, determinism).
- `OPEN-THREADS.md` — everything started, deferred, or known-broken.
- `expansions.md` — the rulebook the rules are cited against.
- `explorers-and-pirates-plan.md` — the E&P build plan.
- `map-creator.md` — the map editor spec + §5 handoff.
- `extending-cards-and-tiles.md` — how to add a card or a terrain through the
  `cards.py` / `tiles.py` registries, and the whole path a new one still needs.
- `CHANGELOG.md` — player-facing release notes; also the deployed build id.
