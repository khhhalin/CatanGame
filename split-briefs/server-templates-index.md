# `server/templates/index.html` + `server/static/js/dom.js` — SPLIT, and split them together

694 lines / 43 KB, and 178 lines / 11 KB. One brief, because splitting either
one alone buys nothing.

## 1. Why these files are contended

Window: `--since='2026-08-03 00:00'`, 135 commits.

**`index.html`**
- **10 distinct work-scopes**: `a11y`, `client`, `dialogs`, `discard`,
  `knights`, `sound`, `trade`, `ui`, `feat`, plus the Firefox/socket.io vendoring
  commit.
- **18 commits**, **5 adjacent cross-scope pairs under 45 minutes**.

**`dom.js`**
- **9 distinct work-scopes**: `a11y`, `client`, `dialogs`, `discard`, `knights`,
  `sound`, `trade`, `ui`, `feat` — the same nine, minus one.
- **15 commits**, **4 adjacent cross-scope pairs under 45 minutes**.

**The number that decides the shape of this brief:**

```
15  server/static/js/dom.js  +  server/templates/index.html
```

Fifteen of `dom.js`'s fifteen commits — **100%** — also touched `index.html`.
`dom.js` is not an independent module; it is a mirror of the template, one
`getElementById` per id the template declares. Adding a control means adding it
in both files, always, in the same commit.

Therefore:

- Splitting `index.html` alone leaves every frontend task queueing on `dom.js`.
- Splitting `dom.js` alone leaves every frontend task queueing on `index.html`.
- Splitting both **along the same seams** is the only version that pays.

`dom.js` is also the counterexample that justifies this whole audit's method:
at 178 lines it is one of the smallest files in the client, and it is the
third-most-contended file in the repository. Ranking by size would have missed
it entirely.

## 2. The seams that already exist

**`index.html`** — the top-level structure is already five regions, each a
single element, each with its own comment block:

| Lines | Region |
|-------|--------|
| 1–33 | `<head>`, `#notice-region`, `#placement-announce`, `#cdn-error` |
| 34–39 | `.container` open, `#connection-status` |
| 40–61 | `#join-screen` — role selection, colour selection |
| 70–99 | `#user-screen` — the lobby: user lists, `#rules-panel`, lobby actions |
| 113–470 | `#game-screen` — `.game-rail` (114–312) and `.game-main` (314–468) |
| 472–556 | `<aside class="table-aside">` — `#info-panel`, `#side-tabs` (log, chat, trade) |
| 560–697 | five modals: trade, discard, victim, invention, monopoly |
| 698–709 | the three `<script>` tags |

Inside `.game-rail`, `#folds-panel` (123–312) is itself grouped by comment:
Cities & Knights folds (126–255), Seafarers (204–255), the development-card /
progress-card pair (256–312).

**`dom.js`** — already sectioned by the same subjects, in comment blocks:
lobby and screens, the trade panel and its modal, timers, dev cards, the
invention/monopoly modals, notices and connection, the board overlays
(`#placement-confirm`, `#yolo-mode-toggle`, `#mute-toggle`), Cities & Knights,
Seafarers, the fold chips, the pending-choice panel, the discard and victim
modals.

Only three of its 124 `getElementById` lookups are not exported (`rolePlayer`,
`roleObserver`, `tradePanel`) — 123 `export const` lines in all — and it imports
nothing at all, the only module in the client that is a pure leaf of the graph.

## 3. The proposed split

**`index.html` → Jinja includes.** Flask already renders this template; `{%
include %}` needs no build step and no configuration.

| New partial | Takes | ≈ lines |
|-------------|-------|---------|
| `templates/partials/lobby.html` | `#join-screen` + `#user-screen` | 55 |
| `templates/partials/rail.html` | `.game-rail` | 200 |
| `templates/partials/board.html` | `.game-main` | 155 |
| `templates/partials/aside.html` | `<aside class="table-aside">` | 85 |
| `templates/partials/dialogs.html` | the five modals | 140 |
| `index.html` (remains) | `<head>`, `.container`, `.table`/`.table-main` shell, the `<script>` tags, five `{% include %}` lines | 60 |

`rail.html` is the largest and, being the Cities & Knights and Seafarers folds,
the one most work lands in. A second cut inside it — `partials/folds-ck.html`
and `partials/folds-seafarers.html` — is defensible, but do it as a follow-up
once the first split has proved out.

**`dom.js` → a directory plus a barrel.**

| New file | Takes | ≈ lines |
|----------|-------|---------|
| `dom/lobby.js` | screens, join, user lists, rules picker, presets | 25 |
| `dom/rail.js` | scoreboard, console buttons, dice, C&K, Seafarers, fold chips | 60 |
| `dom/board.js` | canvas, board overlays, placement confirm, yolo/mute, choice panel | 25 |
| `dom/aside.js` | hand panel, side tabs, chat, event log, trade panel, timers | 30 |
| `dom/dialogs.js` | trade, discard, victim, invention, monopoly modal elements | 40 |
| `dom.js` (remains) | `export * from './dom/lobby.js';` × 5, plus the file's header comment | 12 |

**Keep `dom.js` as a re-export barrel.** That makes the `dom.js` half of this
split a pure move with **zero consumer edits** — twenty modules import
`from './dom.js'` and none of them change. And because the barrel is
`export *`, adding a new lookup later means editing only the sub-file: the
barrel does not grow, so it does not become the new contention point.

Retargeting consumers at the sub-modules (`import { knightList } from
'./dom/rail.js'`) is optional and, on the evidence, unnecessary. Do not do it in
the split commit.

## 4. What must not move

- **Every one of the 188 element ids in the template** (188 occurrences, 188
  distinct — no id is declared twice). 74 distinct `#id` selectors are driven
  from 24 test modules under `tests/`; the most-used are `#start-game-btn`
  (19 references), `#username` (12), `#join-btn` (10), `#trade-verdict` (9),
  `#role-player` (9), `#propose-trade-btn` (9). Moving an element into a partial
  must not change its id, its classes, its ARIA attributes or its position in
  the DOM order.
- **DOM order, exactly.** The includes must render in the same sequence as the
  markup they replace. CSS sibling selectors, tab order and the `role="tablist"`
  keyboard order all depend on it, and `test_browser_a11y.py` asserts on the
  latter.
- **`dom.js` must stay a leaf that imports nothing but its own sub-files.** It
  is currently the only module with zero imports. That property is why it can be
  imported from everywhere without a cycle.
- **`document.getElementById` must still run at the same moment.** The lookups
  are module-level side effects that depend on `main.js` being loaded as a
  module (deferred, so the DOM is parsed). Do not make them lazy, do not wrap
  them in a function, do not "fix" the three unexported ones.
- **The three `<script>` tags stay in `index.html`, in order, at the foot.**
  `board-renderer.js` is a classic script that must define `window.BoardRenderer`
  before `main.js`'s module graph evaluates; `socket.io.min.js` is vendored
  locally on purpose (`#cdn-error` and its comment record why). None of this
  goes into a partial.
- **The no-scroll layout at 1920×1080.** `#game-screen`'s box model is a
  property of the whole tree. `test_the_board_gets_most_of_the_screen` and
  `test_the_console_stays_one_row` will catch a stray wrapper div; do not add
  one to "make the include tidy".
- **Arming a build mode must not change the canvas box or the camera.** The
  comment at `index.html:315` — "position: relative + overflow: hidden so the
  planned viewport-sized canvas can be laid over this box without the layout
  changing again" — travels into `board.html` attached to its element.

## 5. Known hazards

- **Jinja whitespace.** `{% include %}` inserts the file's content verbatim,
  including its trailing newline, and the partial's own leading indentation.
  The rendered output will differ from today's by whitespace unless you are
  careful. That is harmless for CSS and tests, but it means the verification
  diff below must normalise whitespace — and that in turn means the diff is
  weaker evidence than the `style.css` one. Compensate with the id count check.
- **A missing `{% include %}` renders a page with a whole region silently
  absent.** No exception, no 500 — just a lobby with no Start button. This is
  exactly the class of bug `CLAUDE.md` says only the browser suite has ever
  caught ("the Start button vanishing, chat having no input at all").
- **No import cycle risk on the `dom.js` side**, because `dom.js` and its
  sub-files import nothing. This is the safest half of the split; if you only
  have time for one half, do this one.
- **`dom/rail.js` is doing two jobs** — base-game console and the expansion
  folds. If knight work and console work collide there later, cut it again into
  `dom/console.js` and `dom/expansions.js`. Do not pre-empt that now; measure
  first, as this audit did.
- **Do not move markup between regions while splitting.** If a modal's markup
  "belongs" in the aside, that is a separate change on a separate day.

## 6. How to verify the split changed nothing

```bash
cd the repo root

# --- The template: render before and after, compare the DOM, not the bytes ---
TMP=$(mktemp -d)
git archive HEAD~1 | tar -x -C "$TMP"      # never `git stash` in this worktree

# Every id must survive, and there must be exactly as many as before.
git archive HEAD~1 server/templates/index.html | tar -xO \
  | grep -oE 'id="[a-z0-9-]+"' | sort > /tmp/ids-before
cat server/templates/index.html server/templates/partials/*.html \
  | grep -oE 'id="[a-z0-9-]+"' | sort > /tmp/ids-after
diff /tmp/ids-before /tmp/ids-after         # MUST be empty (188 ids)

# Same for classes and ARIA attributes.
for attr in class role aria-label aria-controls aria-expanded aria-selected; do
  git archive HEAD~1 server/templates/index.html | tar -xO \
    | grep -oE "$attr=\"[^\"]*\"" | sort > /tmp/a-before
  cat server/templates/index.html server/templates/partials/*.html \
    | grep -oE "$attr=\"[^\"]*\"" | sort > /tmp/a-after
  echo "== $attr"; diff /tmp/a-before /tmp/a-after
done

# --- dom.js: the exported surface must be identical ---
git archive HEAD~1 server/static/js/dom.js | tar -xO \
  | grep -oE 'export const [a-zA-Z]+' | sort > /tmp/dom-before
cat server/static/js/dom.js server/static/js/dom/*.js \
  | grep -oE 'export const [a-zA-Z]+' | sort > /tmp/dom-after
diff /tmp/dom-before /tmp/dom-after         # MUST be empty (123 exports)

# No consumer should have changed at all.
git show --stat HEAD | grep -c 'static/js/' # expect: only dom.js and dom/*

# --- The suites ---
.venv/bin/python -m pytest -q
.venv/bin/ruff check server tests
.venv/bin/python -m pytest -q tests/test_browser_layout.py \
    tests/test_browser_a11y.py tests/test_browser_firefox.py \
    tests/test_browser_playthrough.py tests/test_browser_knights.py \
    tests/test_browser_trade_rate.py
# then the full 237-test browser suite (~16 min) before calling it done.
```

### What would prove a regression rather than merely passing

The three `diff`s must be empty. If they are, no id, class, ARIA attribute or
export was lost, and the remaining risk is ordering — which only the browser
suite can see.

- `test_browser_a11y.py` failing on tab order or `aria-controls` means an
  include landed in the wrong sequence.
- `test_browser_layout.py::test_nothing_scrolls_and_nothing_is_clipped` naming
  an element means a wrapper or an indentation-induced text node changed the box
  model.
- `test_browser_playthrough.py` failing at all means a whole region did not
  render — the "Start button vanishing" failure mode.
- A green *fast* suite means nothing here. It never loads the template.

If the browser suite was not run, say so; this is the split where skipping it is
most likely to ship a blank region.

## 7. How much parallelism this actually buys

The same nine scopes that opened `dom.js` map onto the new files:

- `knights` → `partials/rail.html` + `dom/rail.js`
- `trade` → `partials/dialogs.html` + `partials/aside.html` + `dom/dialogs.js`
- `dialogs`, `discard` → `partials/dialogs.html` + `dom/dialogs.js`
- `lobby`-adjacent work → `partials/lobby.html` + `dom/lobby.js`
- `sound`, board overlays → `partials/board.html` + `dom/board.js`

Combined with the `panels.js` and `style.css` splits, a knight-panel task, a
trade-dialog task and a lobby task each touch three files, and **none of the
three files is shared with either of the others**. Today all three tasks
contend for the same three files (`index.html`, `dom.js`, `style.css`) plus
`panels.js` — which is precisely the four-way jam the session reported.

That is the end state worth aiming at: **three concurrent frontend agents with
no shared file between them.** This brief is the third of the three splits that
gets there, and none of the three delivers it alone.
</content>
