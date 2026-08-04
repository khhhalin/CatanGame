# Splitting for parallelism — ranked by measured contention

The goal is not smaller files. The goal is that two agents can hold two files
and work at the same time. Everything below is ranked by **how many distinct
pieces of work had to open the same file**, measured from this repository's own
history, not by size.

## How contention was measured

All numbers are over the window `--since='2026-08-03 00:00'` — 135 commits, the
period after `14f92dd refactor(client): split client.js into ES modules`, which
is when the current file layout came into being. Measuring before that point
would just re-measure the old `client.js`.

Three metrics, in decreasing order of how much I trust them:

1. **Distinct work-scopes** — the `feat(<scope>)` / `fix(<scope>)` tag on each
   commit that touched the file. This is the closest proxy the repo has for
   "separate pieces of work", and it is exactly the thing that queues.
   Command:
   `git log --since=… --format='MARK|%s' --name-only` then group filenames by scope.
2. **Adjacent cross-scope pairs under 45 minutes** — consecutive commits to the
   same file, from *different* scopes, landing close together. This is the
   signal that two agents were actually contending for the file at the same
   time rather than visiting it on different days.
3. **Commit count** — noisy, and dominated by whichever feature happened to be
   in flight. Reported for completeness only.

## The ranking

| # | File | Lines | Scopes | Cross-scope pairs <45min | Commits | Verdict |
|---|------|-------|--------|--------------------------|---------|---------|
| 1 | `server/static/js/panels.js` | 1339 | **11** | 5 | 14 | **Split** |
| 2 | `server/templates/index.html` + `server/static/js/dom.js` | 694 + 178 | **10 / 9** | 5 / 4 | 18 / 15 | **Split, together** |
| 3 | `server/static/css/style.css` | 2491 | 9 | 3 | 17 | **Split** (cheapest of all) |
| 4 | `server/game/game.py` | 1431 | 10 | **10** | 25 | **Split, narrowly** |
| 5 | `tests/test_socket_handlers.py` | 1845 | 8 | — | 15 | **Split** (free) |
| — | `server/static/js/board-renderer.js` | 2252 | 5 | 1 | 7 | **Leave alone** |
| — | `server/static/js/cities-knights.js` | 1007 | 4 | **0** | 5 | **Leave alone** |
| — | `server/game/cities_knights_rules.py` | 1104 | 6 | **0** | 8 | Leave alone (see below) |
| — | `server/game/board.py` | 850 | — | 1 | 9 | Leave alone (see below) |
| — | `server/game/rules.py` | 878 | 5 | 1 | 10 | Leave alone (see below) |

The headline result is that **size and contention are nearly uncorrelated
here**. The two biggest files in the repo, `board-renderer.js` (2252 lines) and
`cities_knights_rules.py` (1104 lines), are among the *least* contended:
board-renderer had one cross-scope adjacency in three days, cities_knights_rules
had zero. Meanwhile `dom.js` — 178 lines — was opened by nine different pieces
of work.

Raw scope lists, which are worth reading because they name the work that queued:

```
panels.js       11  a11y, client, dev cards, dialogs, discard, panels, scoreboard, ui,
                    "route award", "award thresholds", feat
index.html      10  a11y, client, dialogs, discard, knights, sound, trade, ui, feat, "vendor socket.io"
game.py         10  board, engine, maps, progress cards, rules, seafarers, timers, ui-bank,
                    fix, "refuse a settlement on an intersection a knight holds"
style.css        9  a11y, dialogs, discard, knights, lobby, scoreboard, trade, ui, feat
dom.js           9  a11y, client, dialogs, discard, knights, sound, trade, ui, feat
socket_handlers  8  engine, feat, fix, handlers, rules, seafarers, server, test
```

## Co-change coupling — why some of these must move together

```
15  dom.js       + index.html      (dom.js changed 15 times; ALL 15 also touched index.html)
14  style.css    + index.html
12  style.css    + dom.js
 9  game.py      + rules.py
 8  style.css    + panels.js
 8  panels.js    + index.html
```

`dom.js` is a mirror of `index.html`: 100% of its commits also touch the
template, because it exists to look up ids the template declares. Splitting one
without the other buys nothing — the queue simply moves to the other file.
Hence one brief for the pair.

`game.py + rules.py` at 9 co-changes is the reason **`rules.py` is not on the
split list**: it is a single registry that every rule addition appends to, by
design and by written policy (`AGENTS.md`, "Adding an optional rule"). The
contention there is a one-line append per rule, and splitting the registry would
break the "one place to look" property that `CLAUDE.md` protects.

## The order to do them in

1. **`panels.js`** — brief in `server-static-js-panels.md`. Highest scope count,
   smallest blast radius (only 9 of its ~30 functions are imported anywhere
   else), and it is the file the session actually reported queueing on. **This
   is the one I would do first.**
2. **`style.css`** — brief in `server-static-css-style.md`. Do it second not
   because it is more contended than the template, but because it is the only
   split in this set that can be *proved* a no-op by `cat`-and-`diff`, and it
   unblocks the same frontend agents.
3. **`index.html` + `dom.js`** — brief in `server-templates-index.md`. More
   delicate (188 element ids, Jinja whitespace), so it goes after the two
   frontend splits that make its consumers smaller.
4. **`tests/test_socket_handlers.py`** — brief in `tests-test-socket-handlers.md`.
   Can be done at any time by anyone; nothing imports it. Slot it into a gap.
5. **`game.py`** — brief in `server-game-game.md`. Highest *interleaving* score
   of any file (10 cross-scope adjacencies) but the most dangerous to split,
   because construction order and save-file compatibility both run through it.
   Narrow extraction only.

## Leave-alone briefs

- `server-static-js-board-renderer.md` — the biggest file in the repo and the
  obvious wrong target. It is a classic script, not a module; splitting it means
  either more ordered `<script>` tags leaking ~60 top-level `const`s into the
  global scope, or a conversion that breaks the `window.BoardRenderer` timing
  the browser suite depends on. Measured contention does not justify either.
- `server-static-js-cities-knights.md` — 1007 lines, zero cross-scope
  adjacencies. Big because Cities & Knights is big.

Not written up as separate briefs, but on the record as deliberate leave-alones:

- **`server/game/cities_knights_rules.py`** (1104 lines, 6 scopes, **0**
  cross-scope adjacencies). Every scope that touched it was a variation on the
  same expansion; no two pieces of work contended for it in the same window. It
  is already a mixin, i.e. already the product of the split that worked.
- **`server/game/rules.py`** (878 lines). The catalogue is deliberately one
  registry. `AGENTS.md` says a new rule is an entry there and nothing else, and
  a test asserts every catalogue id is read by engine code. Contention is one
  appended dict per rule — the cheapest possible conflict. Splitting it would
  also put `rules.catalogue()`'s "importable without touching the filesystem"
  invariant at risk for no measured gain.
- **`server/game/board.py`** (850 lines, 1 cross-scope adjacency). Board
  generation is one algorithm; the co-changes are with `game.py`, not with other
  board work.
- **`server/handlers/*.py`** — already split, and the split is working: the
  handler layer's contention is spread across eleven files, none above 8
  commits. This is the local proof that the approach pays.

## Standing rules for whoever executes these

- **Never `git stash`, `git checkout`, `git restore` or `git reset` in this
  worktree.** `CLAUDE.md` says so, and it has already cost work twice in one
  day. Stage by explicit path. A split touches many files at once, which makes
  this the highest-risk kind of commit for exactly that mistake.
- **One split per commit, and the commit must be provably behaviour-neutral.**
  A split commit that also changes behaviour is the worst possible diff to
  review — the reviewer cannot tell moved code from new code.
- **A split that adds an import cycle is worse than no split.** `constants.js`
  exists because a `const` reached across a cycle is a load-order bug; the
  `panels.js ↔ cities-knights.js` cycle is still live today. Every brief below
  states what it does to the cycle graph.
</content>
