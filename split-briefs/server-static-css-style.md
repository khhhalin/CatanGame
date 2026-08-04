# `server/static/css/style.css` — SPLIT. The cheapest one, and the only provable one.

2491 lines, 62 KB.

## 1. Why this file is contended

Window: `--since='2026-08-03 00:00'`, 135 commits.

- **9 distinct work-scopes**: `a11y`, `dialogs`, `discard`, `knights`, `lobby`,
  `scoreboard`, `trade`, `ui`, `feat`.
- **17 commits**, **3 adjacent cross-scope pairs under 45 minutes**.
- Co-changes: 14 with `index.html`, 12 with `dom.js`, 8 with `panels.js`, 6 with
  `net.js`.

Note the honest reading: the cross-scope adjacency count (3) is *lower* than
`panels.js` (5) and `index.html` (5). Nine scopes with only three tight
collisions means the file is opened by almost every frontend task, but the
visits are short — a rule block here, a rule block there. That is still a
serialisation point, because a short hold on a file is still an exclusive hold.

The reason it is ranked second is not its contention score. It is that this is
the **only split in the set that can be proved a no-op by `diff`**, so it costs
almost nothing to get wrong-proof, and it unblocks the same set of agents as the
`panels.js` split.

## 2. The seams that already exist

Twenty-three banner comments, already written, already in domain order. Measured
sizes:

```
  74  /* -------- table shell */
  48  /* -------- panels */
 103  /* -------- form basics */
 297  /* -------- lobby screen */
 232  /* -------- game screen */
 274  /* -------- console pieces */
 127  /* -------- folds and popovers */
  34  /* -------- the scoreboard */
  91  /* -------- rail panel bodies */
  51  /* -------- resources and bank */
  62  /* -------- tabbed side panel */
 137  /* -------- trade */
 230  /* -------- chat and event log */
  77  /* -------- notices and connection */
 242  /* -------- modals */
  31  /* -------- cities & knights panels */
  48  /* -------- barbarian track */
  72  /* -------- city improvements */
  97  /* -------- knights */
  47  /* -------- progress cards */
  12  /* -------- commodities */
  10  /* -------- utilities */
 109  /* -------- responsive */
```

`tokens.css` (345 lines) is already separate and already loaded first, with a
comment in `index.html` saying why. That is the local precedent: this project
already knows how to serve CSS from more than one file.

## 3. The proposed split

Eight files, grouped so that each maps to a scope seen in the log, linked from
`index.html` **in exactly this order**:

| New file | Sections it takes | ≈ lines |
|----------|-------------------|---------|
| `shell.css` | table shell, panels, form basics, folds and popovers | 352 |
| `lobby.css` | lobby screen | 297 |
| `table.css` | game screen, console pieces, the scoreboard, rail panel bodies, resources and bank, tabbed side panel | 654 |
| `trade.css` | trade | 137 |
| `log.css` | chat and event log, notices and connection | 307 |
| `modals.css` | modals | 242 |
| `cities-knights.css` | cities & knights panels, barbarian track, city improvements, knights, progress cards, commodities | 307 |
| `responsive.css` | responsive, utilities | 119 |

`style.css` ceases to exist as a file.

`index.html` gains seven `<link>` lines after the existing `tokens.css` line —
one contiguous edit in the `<head>`, which is the least contended part of the
template.

### Why `<link>` tags and not `@import`

CSS `@import` inside a stylesheet is fetched only after the importing sheet
parses, serialising eight round trips and blocking first paint. There is no
build step to inline them. Eight parallel `<link>` requests over the same HTTP
connection is the correct answer here, and it keeps the cascade order explicit
and readable in the template where a reviewer will look for it.

## 4. What must not move

- **The cascade order.** This is the whole risk. CSS resolves specificity ties
  by document order, and this stylesheet has 2491 lines of accumulated ties.
  `responsive.css` **must be last** — its media queries override the base rules
  and nothing else. `shell.css` **must be first** after `tokens.css`. The
  concatenation of the eight files in link order must be byte-identical to the
  current `style.css`, modulo the banner comments. Do not reorder sections to
  make a file "cleaner".
- **`tokens.css` stays first and stays whole.** `index.html` carries the comment
  "Tokens first: style.css reads colour, spacing, radii and motion from" —
  every one of the eight new files reads those custom properties.
- **The no-scroll layout at 1920×1080.** This is the invariant this file most
  directly owns.
  `test_browser_firefox.py::test_the_layout_does_not_scroll_at_1920x1080`,
  `test_browser_layout.py::test_nothing_scrolls_and_nothing_is_clipped` (three
  fixtures), `test_the_console_stays_one_row`, `test_the_board_gets_most_of_the_screen`
  and `test_the_lobby_does_not_scroll_at_1920x1080` all assert it. It is a
  property of the *composed* cascade, not of any one section, which is exactly
  why the concatenation must be identical.
- **Arming a build mode must not change the canvas box.** The console's sizing
  rules live in the "console pieces" section. `test_browser_layout.py:414`
  records the failure: the console rewrapped, which resized the board box, which
  moved the camera. Those rules go into `table.css` unchanged and un-reindented.
- **No selector may be edited.** Not renamed, not merged, not de-duplicated. If
  a rule looks redundant, it is not this commit's business — a duplicate
  selector later in the file may be the one that wins.

## 5. Known hazards

- **This is not a JS module split; there are no import cycles to add.** CSS has
  no dependency graph. The hazard is entirely order.
- **Silent failure mode.** If a `<link>` is misordered or omitted, most of the
  page still looks right; a handful of overrides quietly lose. The browser
  layout suite catches it, the fast suite does not, and eyeballing a screenshot
  might not.
- **A missing file 404s and the page still renders.** Check the browser console
  assertion (`test_no_console_errors_were_logged`) actually covers network
  errors; if it does not, verify the seven requests by hand once.
- **Do not take the chance to convert anything to `tokens.css`.** Moving a
  hardcoded colour into a custom property in the same commit makes the diff
  unreviewable and defeats the `diff`-proof below.

## 6. How to verify the split changed nothing

The strong check, which no other brief in this set can offer:

```bash
cd the repo root
# The parent version, WITHOUT touching the shared worktree:
TMP=$(mktemp -d)
git archive HEAD~1 server/static/css/style.css | tar -x -C "$TMP"

# Concatenate the new files in exactly the <link> order from index.html:
cat server/static/css/shell.css server/static/css/lobby.css \
    server/static/css/table.css server/static/css/trade.css \
    server/static/css/log.css server/static/css/modals.css \
    server/static/css/cities-knights.css server/static/css/responsive.css \
  > /tmp/after.css

# Ignore only the banner comments and blank lines the split adds:
diff <(grep -vE '^\s*(/\*|$)' "$TMP/server/static/css/style.css") \
     <(grep -vE '^\s*(/\*|$)' /tmp/after.css)
```

**That diff must be empty.** If it is empty, the cascade is provably unchanged
and the split is a no-op by construction. If it is not empty, the split changed
CSS and must be redone.

Then:

```bash
grep -c 'rel="stylesheet"' server/templates/index.html    # expect 9
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/test_browser_layout.py \
    tests/test_browser_firefox.py tests/test_browser_a11y.py \
    tests/test_browser_visuals.py
```

### What would prove a regression rather than merely passing

The `diff` above passing is the real gate; the suites are the backstop. If the
diff is empty and a browser test still fails, the cause is link order or a
missing `<link>`, not the CSS.

Specifically:
- `test_the_layout_does_not_scroll_at_1920x1080` (Firefox) failing means an
  override lost — almost certainly `responsive.css` is not last.
- `test_nothing_scrolls_and_nothing_is_clipped` naming a specific element tells
  you which section landed in the wrong file; the assertion message names it.
- `test_browser_visuals.py` screenshot diffs are the sensitive detector for a
  rule that lost by one position.

A run that skipped the browser suite proves nothing about this change.

## 7. How much parallelism this actually buys

The nine scopes that opened this file map almost one-to-one onto the proposed
files:

- `lobby` → `lobby.css`
- `trade` → `trade.css`
- `dialogs`, `discard` → `modals.css`
- `knights` → `cities-knights.css`
- `scoreboard` → `table.css`
- `a11y` → spread, but mostly `shell.css` and `responsive.css`

So: **lobby work, trade-dialog work, knight-panel work and scoreboard work can
run concurrently** where today all four contend for one file. On the observed
distribution that is four independent lanes.

The secondary benefit is review: a `trade.css` diff is obviously a trade change.
Today a `style.css` diff is 62 KB of context around six lines.
</content>
