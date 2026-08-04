# `server/static/js/cities-knights.js` — LEAVE ALONE (but take `findMyPlayer` out of the cycle)

1007 lines, 37 KB. Second-largest client module.

## 1. Why it is not contended

Window: `--since='2026-08-03 00:00'`, 135 commits.

- **4 distinct work-scopes**: `client`, `feat`, `knights`, `ui`.
- **5 commits.**
- **0 adjacent cross-scope pairs under 45 minutes.** Not one collision in three
  days of parallel work.

Compare `panels.js` — 1339 lines, eleven scopes, five collisions — and
`dom.js`, at 178 lines and nine scopes. This file is large because Cities &
Knights is large: a barbarian track, three improvement tracks, knights with
rank and activation, city walls, and three progress-card decks. It is one
expansion, worked on by one agent at a time, which is exactly the pattern that
does *not* need splitting.

The same finding holds for its engine counterpart,
`server/game/cities_knights_rules.py` — 1104 lines, six scopes, **zero**
cross-scope adjacencies, eight commits, all of them variations on the same
expansion.

## 2. The seams do exist — that is not the question

For the record, so nobody has to look again: the file is cleanly sectioned into
placement (`handleCkVertexTap`, `expectPlacement`, `clearSettledPlacement`,
`myKnightAt`, `myWallCount`), the barbarian (`noteBarbarianAttack`,
`describeLastAttack`, `renderBarbarianTrack`), rule and cost helpers (`ckRule`,
`ckEnabled`, `isCkMode`, `formatCost`, `canAfford`, `shortfallReason`,
`ckTurnBlockReason`, `knightActionReasons`), mode arming (`toggleCkMode`,
`startKnightMove`, `syncCkModeButtons`, `ckModeHint`), and four renderers
(`renderCitiesKnights`, `renderImprovements`, `renderKnights`,
`renderProgressHand`, `buildProgressCardRow`, `buildKnightActionButton`) with
three delegated listeners at the foot.

A `ck-barbarian.js` / `ck-knights.js` / `ck-progress.js` split is perfectly
feasible. It is simply not paid for: it would move code nobody is queueing on,
churn a file with an active import cycle, and produce a diff that hides
behaviour changes — the three costs a split has to earn back.

## 3. The one change worth making, and it is not a split

`cities-knights.js` sits in a live import cycle:

```
panels.js ──ckEnabled, isCkMode, shortfallReason, syncCkModeButtons──▶ cities-knights.js
panels.js ◀──────────────── findMyPlayer ─────────────────────────────  cities-knights.js
```

and in a three-hop one:

```
cities-knights.js ──syncSeaModeButtons──▶ seafarers.js ──findMyPlayer──▶ panels.js
                  ◀────────── ckEnabled, isCkMode, … ──────────────────
```

`constants.js` exists because a `const` reached across a cycle is a load-order
bug — that is written into this repository's history, not theory.
`findMyPlayer` is the only thing this file wants from `panels.js`, and it is
seventeen lines. Lifting it into a new `player-view.js` (see
`server-static-js-panels.md`, §5) removes **both** cycles and touches three
lines of this file.

Do that. Do not split this file.

## 4. What must not move, if someone overrules this

- **`shortfallReason` and `ckEnabled` are consumed by `panels.js`.** They are
  the C&K side of the build-gating chain
  (`updateAffordability` → `buildBlockReason` → `shortfallReason`). Moving them
  into a sub-module means `panels.js` imports two C&K files instead of one and
  the cycle risk doubles.
- **`syncCkModeButtons` and `toggleCkMode` arm build modes.** `AGENTS.md` and
  `test_browser_layout.py::test_arming_or_disabling_a_build_button_never_resizes_it`
  make this a hard invariant: arming must not change the canvas box or move the
  camera. Whatever those functions write to the DOM today, they must write
  byte-identically tomorrow.
- **The fold chips must summarise themselves unopened.**
  `test_each_fold_summarises_itself_without_being_opened`,
  `test_the_improvements_chip_reads_as_the_owner_asked` and
  `test_the_barbarian_chip_states_the_clock_without_being_opened` all drive
  `#knights-chip`, `#progress-cards-chip`, `#barbarian-chip-value` and friends —
  ids that this file's renderers fill.
- **No client code may branch on the name of an expansion.** `ckRule(ruleId)`
  reads one rule at a time, on purpose. `CLAUDE.md`: "Branch on the specific
  rule that governs the behaviour — `rules['knights']`, not 'are we playing
  C&K'." A split that introduces a `ck-*.js` module gated on "is C&K on" would
  reintroduce the mode this project spent 41 individual rules removing.

## 5. How much parallelism a split would buy

Zero measured. Four scopes, five commits, no collisions. There is currently no
second agent waiting on this file, and the `findMyPlayer` extraction unblocks
the agents who were waiting on it *through* `panels.js` — which is where the
actual queue was.

**Recommendation: leave it alone. Revisit only if a future measurement shows
barbarian, knight and progress-card work colliding, which it has not yet.**
</content>
