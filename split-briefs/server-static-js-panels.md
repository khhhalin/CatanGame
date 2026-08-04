# `server/static/js/panels.js` — SPLIT. Do this one first.

1339 lines, 49 KB. The most contended file in the repository by the metric that
matters.

## 1. Why this file is contended

Measured over `--since='2026-08-03 00:00'` (135 commits, the window since the
`client.js` split created the current layout):

- **11 distinct work-scopes** touched it — the highest of any file in the repo:
  `a11y`, `client`, `dev cards`, `dialogs`, `discard`, `panels`, `scoreboard`,
  `ui`, `feat`, plus two commits whose subject lines are about award thresholds
  and route-award naming.
- **14 commits**, of which **5 were adjacent cross-scope pairs less than 45
  minutes apart** — that is, five times in three days a commit from one piece of
  work was followed within the hour by a commit from a *different* piece of work
  on the same file. That is the queue, visible in the log.
- Co-changes: 8 with `style.css`, 8 with `index.html`, 7 with `dom.js`, 5 with
  `net.js`.

The reason is structural, not accidental. `panels.js` is the only home for six
unrelated player-facing surfaces: the scoreboard, the hand, the bank, the
development-card fold, the two dialogs a 7 opens, and the build console. Those
are six independent feature areas that happen to share a filename.

The decisive fact for a split, though, is this: **only 9 of its ~30 functions
are visible outside the file.**

```
net.js       offerVictimChoice, openDiscardModal, renderBank, renderDevCards,
             renderGameSidebar, renderResourcePanel, updateButtonColors,
             updateConsoleVisibility, updateGameUI
seafarers.js findMyPlayer
cities-knights.js findMyPlayer
trade.js     findMyPlayer, renderDialogHands
```

`scoreChip`, `awardsHeldBy`, `scoreChipsFor`, `handChips`, `getContrastColor`,
`parseHexColor`, `BUILD_COSTS`, `DISCARDABLE_CARDS`, `buildBlockReason`,
`updateAffordability`, `formatBuildCost`, `renderTurnIndicator` and
`renderAwardSummary` have **zero** references outside the file. A split has a
tiny blast radius.

## 2. The seams that already exist

The file is already ordered by concern. Line ranges as of the commit this brief
was written against (`23eaa85`):

| Lines | Size | Concern |
|-------|------|---------|
| 1–29 | 29 | Header, `DISCARDABLE_CARDS`, `BUILD_COSTS` |
| 30–177 | 148 | The eight console button listeners (next turn, end game, roll, colour, settlement, road, city, buy card) |
| 178–343 | 166 | `scoreChip`, `awardsHeldBy`, `scoreChipsFor` |
| 345–418 | 74 | `renderGameSidebar` |
| 419–526 | 108 | `renderAwardSummary` |
| 527–553 | 27 | `renderTurnIndicator` |
| 554–628 | 75 | `parseHexColor`, `relativeLuminance`, `contrastRatio`, `getContrastColor` |
| 629–645 | 17 | `findMyPlayer` |
| 646–712 | 67 | `handChips`, `renderResourcePanel`, `renderDialogHands` |
| 713–759 | 47 | `renderBank` |
| 760–899 | 140 | `renderDevCards`, `renderDevCardsChip`, `renderDevDeckRemaining`, delegated listener, `handlePlayDevCard` |
| 901–919 | 19 | `openDiscardModal` |
| 920–1073 | 154 | `updateGameUI` |
| 1074–1168 | 95 | `buildBlockReason`, `missingFromThisTableReason`, `updateAffordability`, `formatBuildCost` |
| 1169–1229 | 61 | `updateConsoleVisibility` |
| 1230–1260 | 31 | `updateButtonColors` |
| 1261–1339 | 79 | `offerVictimChoice`, `renderVictimList`, victim listener, discard submit listener |

These are clean seams. Measured symbol usage per region (grep of every imported
name against each range) shows the regions barely reach across each other:

```
scoreboard (178–527)  needs: getBoard, getCurrentPlayer, seaRule, getContrastColor
hand + bank (646–760) needs: ckEnabled, COMMODITY_ICONS, COMMODITY_TYPES,
                             RESOURCE_ICONS, findMyPlayer, getBoard
dev cards (760–900)   needs: displayError, emitGame, findMyPlayer, getBoard,
                             getGamePhase, hasRolledDice, isMyTurn,
                             mustMoveRobber, viewState
the seven (1261–1339) needs: displayError, emitGame, getBoard,
                             getDiscardAmount, getRobberVictims, viewState
```

## 3. The proposed split

Six new files; `panels.js` keeps the console and the orchestrator.

| New file | Owns | Moved from | ≈ lines |
|----------|------|------------|---------|
| `player-view.js` | `findMyPlayer` **only** | 629–645 | 20 |
| `contrast.js` | `parseHexColor`, `relativeLuminance`, `contrastRatio`, `getContrastColor` | 554–628 | 80 |
| `scoreboard.js` | `scoreChip`, `awardsHeldBy`, `scoreChipsFor`, `renderGameSidebar`, `renderAwardSummary` | 178–526 | 355 |
| `hand.js` | `handChips`, `renderResourcePanel`, `renderDialogHands`, `renderBank` | 646–759 | 120 |
| `dev-cards.js` | `renderDevCards`, `renderDevCardsChip`, `renderDevDeckRemaining`, `handlePlayDevCard`, the delegated `myDevCardsDiv` listener | 760–899 | 145 |
| `seven.js` | `DISCARDABLE_CARDS`, `openDiscardModal`, the discard-submit listener, `offerVictimChoice`, `renderVictimList`, the victim listener | 18, 901–919, 1261–1339 | 120 |
| `panels.js` (remains) | the eight button listeners, `BUILD_COSTS`, `buildBlockReason`, `missingFromThisTableReason`, `updateAffordability`, `formatBuildCost`, `updateConsoleVisibility`, `updateButtonColors`, `renderTurnIndicator`, `updateGameUI`, plus re-exports | — | 480 |

`main.js` gains no new entries — the new modules are pulled in by `panels.js`
and `net.js`, which are already in the entry list. The listener-bearing files
(`dev-cards.js`, `seven.js`) must be imported for side effect by `panels.js` so
their listeners still register at the same point in load order.

### Why `panels.js` keeps the console cluster

`updateConsoleVisibility` calls `updateAffordability` → `buildBlockReason` →
`shortfallReason` (from `cities-knights.js`), then `updateButtonColors` →
`getContrastColor`, then `renderTurnIndicator`. There is a comment in the file
recording *why* the order is what it is ("Affordability first: updateButtonColors
only paints a button it finds enabled"). Splitting inside that chain moves an
ordering constraint across a file boundary where nobody will see it. Leave it
whole.

### Why `contrast.js` is worth its own 80 lines

It is pure — no imports at all, four functions, WCAG luminance maths — and it is
the only thing the scoreboard and `updateButtonColors` share. Putting it in
`scoreboard.js` would make `panels.js` import the scoreboard to paint a button.

## 4. What must not move

- **Every element id.** 74 distinct `#id` selectors are driven from 24 test
  modules under `tests/`; `#award-summary`, `#next-turn-btn`, `#roll-dice-btn`,
  `#submit-discard-btn`, `#victim-list`, `#dice-set` and `#resource-display` are
  all reached from this file. The split moves code between files; it must not
  rename, add or remove a single id or class the DOM carries.
- **`window.BoardRenderer` and `window.__catanDebug`.** `__catanDebug` is
  assembled in `main.js` and read by nine browser test modules. `panels.js`
  contributes nothing to it and must continue to contribute nothing. Do not take
  the opportunity to "expose the new modules for testing".
- **Arming a build mode must not change the canvas box or the camera.**
  `tests/test_browser_layout.py::test_arming_or_disabling_a_build_button_never_resizes_it`
  exists because rewrapping the console resized the board box and moved the
  camera under a click already in flight. `updateAffordability` sets
  `button.disabled` and `button.title` and nothing else; `updateButtonColors`
  sets `style.color`/fill and nothing else. **A split must not change one
  character of what those two functions write to the DOM** — in particular do
  not "tidy" a `title` into a text node or a class toggle.
- **The no-scroll layout at 1920×1080.** Asserted in
  `test_browser_layout.py`, `test_browser_firefox.py` and `test_browser_a11y.py`.
  `renderGameSidebar` and `renderAwardSummary` write markup that is sized against
  it. Move the functions; do not reflow their HTML.
- **The `BUILD_COSTS` comment.** It records that the table mirrors
  `server/data/costs.json` and exists only to grey a button out, and that the
  server re-checks everything. `d255200 docs(panels): put the build-cost comment
  back on the build costs` is a commit whose entire content is restoring this
  comment after it drifted off its subject. It travels with `BUILD_COSTS` into
  `panels.js`, attached to it.
- **`renderResourcePanel` calling `renderDialogHands`.** `79d680c fix(dialogs):
  show the hand the discard and trade dialogs are asking about` made the rail
  panel and the two dialogs paint from one `handChips` call so a chip cannot say
  one thing in the panel and another in the dialog. Both stay in `hand.js`,
  together, with that call intact.

## 5. Known hazards

**The live import cycle.** Today:

```
panels.js  ──imports ckEnabled, isCkMode, shortfallReason, syncCkModeButtons──▶ cities-knights.js
panels.js  ◀────────────────── imports findMyPlayer ──────────────────────────  cities-knights.js

panels.js  ──imports isSeaMode, seaRule, syncSeaModeButtons──▶ seafarers.js
panels.js  ◀───────────── imports findMyPlayer ───────────────  seafarers.js

and the three-hop: cities-knights.js → seafarers.js → panels.js → cities-knights.js
```

`constants.js` exists precisely because a `const` reached across a cycle is a
load-order bug. **Extracting the 17-line `findMyPlayer` into `player-view.js`
removes all three cycles**, because `findMyPlayer` is the only thing either
expansion module wants from `panels.js`. That is the highest-leverage single
change in this entire audit and it is 17 lines.

Do it as its own commit, first, before anything else in this brief. It is
independently valuable and independently reviewable.

After the split the graph must be checked, not assumed. There is no bundler to
warn you: a cycle in ES modules is silent until a `const` is read before its
module body ran, and then it is a `ReferenceError` in one browser and not the
other. See the verification step.

**Other hazards:**

- `hand.js` will import `ckEnabled` from `cities-knights.js`. That is a new
  edge. It does not close a cycle *provided* `findMyPlayer` has already moved
  out of `panels.js` — `cities-knights.js` must not import `hand.js`.
- `tests/test_browser_tester_round.py:528` does
  `const panels = await import('/static/js/panels.js'); panels.renderGameSidebar(...)`.
  If `renderGameSidebar` moves to `scoreboard.js` that test breaks. **Re-export
  it from `panels.js`** so the split commit stays provably behaviour-neutral;
  changing the test in the same commit would mean the suite is no longer
  checking the same thing across the split.
- The same argument applies to `net.js`'s nine-name import. Re-export all nine
  from `panels.js` in the split commit, so `net.js` is untouched and the diff is
  pure movement. Retargeting `net.js`'s imports at the real modules is a good
  follow-up commit — but a *separate* one, when nobody is mid-edit in `net.js`.
- Two module-level delegated listeners (`myDevCardsDiv`, `victimList`) and the
  discard-submit listener register at import time. If their new files are only
  imported lazily, the listeners never attach and the failure looks like "the
  button does nothing" — which no unit test catches. `panels.js` must import
  them for side effect at the top.

## 6. How to verify the split changed nothing

```bash
# 1. Cycle check — the thing most likely to go wrong, and silent if it does.
#    Build the module graph from the import lines and look for a back edge.
cd the repo root
grep -Hn "^import .* from '\./" server/static/js/*.js
#    Expect: no path from cities-knights.js or seafarers.js back to panels.js.

# 2. The moved code really is the same code.
git show --stat HEAD          # should be ~= as many deletions as insertions
git show HEAD -- server/static/js/panels.js | grep '^+' | grep -v '^+++' \
  | grep -vE '^\+(import|export \{|//|$)'
#    Expect: empty. Any surviving line is new behaviour hiding in a move.

# 3. The public surface is unchanged.
grep -o "export function [a-zA-Z]*" server/static/js/panels.js | sort > /tmp/after
#    Compare against the same list from the parent commit, extracted WITHOUT
#    touching the worktree:
git archive HEAD~1 server/static/js/panels.js | tar -xO \
  | grep -o "export function [a-zA-Z]*" | sort > /tmp/before
diff /tmp/before /tmp/after   # expect: no removals

# 4. The suites.
.venv/bin/python -m pytest -q                    # 998 fast tests
.venv/bin/ruff check server tests
.venv/bin/python -m pytest -q tests/test_browser_layout.py \
    tests/test_browser_tester_round.py tests/test_browser_a11y.py \
    tests/test_browser_visuals.py tests/test_browser_firefox.py
#    then the full 237-test browser run before calling it done (~16 min).
```

**Never `git stash` or `git checkout` to get the parent version** — another
agent is committing into this worktree. `git archive HEAD~1 | tar -x -C
"$(mktemp -d)"` as `CLAUDE.md` instructs.

### What would prove a regression rather than merely passing

The fast suite passing proves almost nothing here — it asserts on server state
and every bug this split could introduce leaves server state perfectly correct.
The specific failures to look for:

- `test_browser_layout.py::test_arming_or_disabling_a_build_button_never_resizes_it`
  — a regression here means the console rewrapped, which means
  `updateAffordability` or `updateButtonColors` now writes something different.
- `test_browser_layout.py::test_no_console_errors_were_logged` (three
  fixtures) — this is the cycle detector. A load-order `ReferenceError` shows up
  here and nowhere else.
- `test_browser_tester_round.py` scoreboard test — proves the dynamic
  `import('/static/js/panels.js')` still resolves `renderGameSidebar`.
- `test_browser_a11y.py` — the chips and folds the no-scroll layout hid whole
  panels behind.

A green run that *skipped* the browser suite is not evidence. Say so if you did.

## 7. How much parallelism this actually buys

Concretely, after the split these can run at the same time, each in its own
file, where today they queue on one:

- **scoreboard work** (`scoreboard.js`) — award badges, per-player state,
  thresholds. Four of the 14 commits in the window were this.
- **dev-card / progress-card gating** (`dev-cards.js`) — three commits.
- **the 7 dialogs: discard and victim** (`seven.js`) — three commits, and this
  is the area that collided with the trade dialog work.
- **hand and bank rendering** (`hand.js`) — the commodity work.
- **build-console gating and the turn indicator** (`panels.js`) — the a11y and
  affordability work.

Five of the eleven scopes that touched this file in three days get their own
file. On the observed pattern that is roughly **three concurrent frontend
agents where today there is one** — and the trade UI (`trade.js`) and knight
actions (`cities-knights.js`, `knight-overlay.js`) stop being blocked behind
whoever holds `panels.js` for `findMyPlayer` and `renderDialogHands`.
</content>
