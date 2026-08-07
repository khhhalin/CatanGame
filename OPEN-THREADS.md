# Open threads

Work that is started, known-broken, or deliberately deferred. The point of this
file is to resume things rather than start new ones.

Deployed: `ff7564d` = **v2.1.0**. Suites: ~1118 fast, ~358 browser (~10 min), ruff
clean (one known `#start-game-btn` a11y flake under load, passes in isolation).
New owner: read `HANDOFF.md` first.

---

## 1. Next up

**The map editor.** The engine half is done and shipped: `server/game/maps.py`
(parse, validate, instantiate), `map_store.py`, four built-in maps expressed in
the format, a `board_map` rule, and `preview_map` over the wire so what the
editor previews is the code path that gets played. **There is no editor.**
`map-creator.md` is the specification and has been revised for a world where
ships exist; read its §5 handoff for the events and what the editor must not
assume.

This also unblocks the item below.

**`island_victory_points` cannot score on the built-in boards.** Three of the
five are one landmass, so `record_island_settlement` never finds a second
island. `six-shores.json` now has four landmasses, so the rule is reachable —
but nothing else built-in is, and the rule is advertised on every table.

---

## 2. Client-side copies of server truth

The pattern that has produced three separate bugs: a number the engine owns,
written a second time in JS, free to disagree. "needs 5" in the award panel
while the table played to 2; per-development-card prices in `costs.json` that
nothing read and that were wrong; `BUILD_COSTS` duplicating every price.

Prices are fixed — the payload carries `costs`, modifier-adjusted, and the
client's literal is gone. These remain, found in the same sweep:

- **Priced by the payload, still hardcoded**: `cities-knights.js:174-177`
  (knight build/activate/promote, city wall), `seafarers.js` `SHIP_COST`, and
  three static `build-cost` spans in `index.html`. The template ones want their
  own commit: the only place to rewrite them is `updateAffordability`, and
  `test_browser_layout.py::test_arming_or_disabling_a_build_button_never_resizes_it`
  exists because rewrapping the console once moved the camera.
- **Already in `board.rules`, still hardcoded**: `hand.js` `RESOURCE_LIMIT = 19`
  (bank bars read over 100% if a table raises `bank_resource_limit`), plus
  `?? 4 / ?? 3 / ?? 2 / ?? 15` fallbacks in `trade.js` and `seafarers.js`.
- **No field exists yet**: `trade.js` `MERCHANT_TRADE_RATE` and `scoreboard.js`
  Harbormaster "needs 3". (The trade countdown is now the `trade_offer_seconds`
  rule, carried in `board.rules`; the server refuses an accept or a completion
  past the deadline rather than only pruning the list.)
- **Engine constants mirrored in JS**: `MAX_CITY_WALLS`, `MAX_KNIGHTS_PER_RANK`,
  `MAX_IMPROVEMENT_LEVEL`, `ABILITY_LEVEL`, the improvement price formula, knight
  rank names (in `cities-knights.js` *and* `choices.js`), and a client-side
  re-implementation of the barbarian attack outcome. All currently agree.
- `board-renderer.js` `isHot = number === 6 || number === 8` duplicates
  `board.RED_NUMBERS`.

---

## 3. Magic numbers that could be rules

The catalogue is 60+ rules and the invariant is that a number a table might want
to change belongs in it. These are still literals:

- **Harbormaster threshold.** `trade_rules.py` `if best < 3` and
  `scoreboard.js` "needs 3". They agree, so nothing drifts *today* — but there is
  no `harbormaster_minimum` rule, which is why the client's copy is not the same
  bug as "needs 5" was.
- `MAX_KNIGHTS_PER_RANK`, `MAX_IMPROVEMENT_LEVEL`, `ABILITY_LEVEL`,
  `METROPOLIS_LEVEL`, `METROPOLIS_STEAL_LEVEL` in `cities_knights.py`.

---

## 4. Known-unfixed

- **`/skip` does not check whose turn it is.** Any seated player can end the
  current player's turn (logged as "Bob skipped Alice's turn"). Likewise
  `/add_resource` targets any player. Both look intentional for an opt-in,
  fully-logged house rule, but a table switching `chat_commands` on hands every
  seat those powers.
- **~22 `console.log` calls in `net.js`** — deliberate-looking event tracing,
  not litter. A judgement call, not a fix.
- Dead import `activeRulesChipValue` in `panels.js`; the `INVALID_TARGET` branch
  in `robber_refusal` is unreachable from `move_robber`; five literal
  "cd the repo root" strings left in `split-briefs/` by a path scrub.

---

## 5. Untested — real risk

- **No screen-reader run.** Live regions and combobox patterns are asserted
  through the DOM only.
- **Touch input** was reasoned about, never tested on a device.
- **Docker deploys `python:3.13-slim`; everything is tested on 3.14.6.** If the
  deploy is the Docker path, that gap is unexercised. The image build itself was
  verified once with buildah, not docker.
- **`gunicorn>=21.2,<27` is a range, not a lock** — a rebuild months from now
  silently picks up a newer 26.x.
- **No long game on the seafaring board.** The 141-turn playthrough was replaced
  by per-rule scenarios (which reach three things it never did) plus a 24-turn
  seeded soak. The base-board long game is untouched.
- **A dark-theme contrast flake**: `test_every_visible_label_meets_wcag_aa[dark]`
  measured 2.01:1 on a disabled Start button once under full-suite load, and
  passes in isolation on both the old and new commits. Diagnosed as an in-flight
  CSS transition colour — *not proven*.
- `test_the_build_id_is_this_checkout` fails outside a git checkout (a tarball
  deploy, some CI images). The test is non-hermetic; the product is not.

---

## 6. Waiting on a decision

- **`audit-report.md` is in the public git history.** Removed from the tree and
  gitignored, but `git log -p` still shows 426 lines naming the identity and
  hidden-information holes with file and line numbers. The holes it describes
  are the ones since fixed. Purging needs a history rewrite and a force-push.
- **Four split briefs are unapplied**: `index.html` + `dom.js` (they move
  together — 15 of `dom.js`'s 15 commits also touched the template), `style.css`,
  `test_socket_handlers.py`, and `game.py` (which the audit rates weakest and
  advises against splitting `__init__`). `panels.js` is done: seven modules, and
  three import cycles gone.

---

## 7. Decisions not to re-litigate

- `board-renderer.js` and `cities-knights.js` are **deliberately not split** —
  biggest files, near-zero contention, and splitting the renderer would spread
  its ~60 top-level globals across more script tags.
- The two browser suites are **deliberately not merged**: four things live only
  in `test_browser_playthrough.py`, and the confirm/YOLO split is structural.
- `test_every_listed_map_can_be_built` was on a kill-list and **kept**: it is the
  only test checking the *advertised* layouts against what actually builds.
- Verification runs the browser suite **once**, not three times.
- See `CLAUDE.md` for the testing contract, the rules invariant, and the
  shared-worktree rule these came out of.
