# `server/game/game.py` — SPLIT, but narrowly. Three extractions, not a rewrite.

1431 lines. Highest *interleaving* score in the repository, and the most
dangerous file here to split.

## 1. Why this file is contended

Window: `--since='2026-08-03 00:00'`, 135 commits.

- **10 distinct work-scopes**: `board`, `engine`, `maps`, `progress cards`,
  `rules`, `seafarers`, `timers`, `ui-bank`, `fix`, plus a knight-placement fix.
- **25 commits** — the most of any file in the window.
- **10 adjacent cross-scope pairs under 45 minutes — the highest in the
  repository, twice `panels.js`'s five.** Ten times in three days, a commit from
  one piece of work on this file was followed inside the hour by a commit from a
  different piece of work.
- Co-changes: 9 with `rules.py`, 6 each with `turn_clock.py`,
  `cities_knights_rules.py` and `persistence.py`, 5 each with `handlers/turns.py`,
  `trade_rules.py`, `board.py`.

But the contention is **diffuse**, and that changes the recommendation. Bucketing
every diff hunk's start line into 50-line bands:

```
lines    0- 49: 4 scopes   board, engine, rules, ui-bank
lines  450-499: 5 scopes   engine, maps, rules, seafarers, ui-bank
lines  600-649: 4 scopes   board, engine, rules, seafarers
lines 1150-1199: 4 scopes  engine, fix, rules, ui-bank
lines  100-149: 4 scopes   board, engine, rules, timers
...and every other band 1-3 scopes, with no band empty below line 1300
```

There is no single hot region to lift out. The file is contended along its whole
length because it genuinely hosts the whole base game. **That is an argument for
a small, principled split and against an ambitious one.**

## 2. The seams that already exist

This project has already done this split once, successfully, and wrote down the
pattern. `Game` is:

```python
class Game(BoardBuilder, TradeRules, RobberRules, SeafarersRules, DevCardRules,
           CitiesKnightsRules, PendingChoiceRules, TurnClock):
```

and `robber_rules.py` opens with a docstring that states the rule:

> Split out of `game.py` alongside the other rules mixins; see `board.py` for
> the pattern. It stays a mixin because every method reads Game state.

So the seam vocabulary already exists: a mixin per concern, no state of its own,
`self.*` throughout, added to the bases tuple. Follow it exactly. What remains
in `game.py` after the previous rounds falls into five clusters:

| Lines | Size | Cluster |
|-------|------|---------|
| 24–65 | 42 | class header, `PLAYER_COLORS`, `MAX_*` |
| 66–267 | 202 | `__init__` — one attribute wall |
| 268–401 | 134 | small accessors: `has_piece_available`, `check_invariants`, observers, `get_player`, `set_player_color`, `track_settlement`, setup-turn helpers |
| 402–718 | 317 | **building actions**: `current_player_name`, `claim_victory`, `_cost_message`, `_respects_distance_rule`, `_road_connects`, `place_settlement`, `build_road`, `upgrade_city`, `_touches_own_road`, `_touches_own_route` |
| 719–778 | 60 | **scoring**: `victory_points_for`, `public_victory_points` |
| 779–897 | 119 | **the board payload**: `get_board_data` |
| 898–1101 | 204 | **production and costs**: `production_for`, `distribute_resources`, `distribute_from_settlement`, `give_resource`, `get_cost`, `can_afford`, `deduct_cost` |
| 1102–1217 | 116 | dice: `roll_dice`, `next_dice`, `dice_combinations`, `in_robber_free_opening` |
| 1218–1431 | 214 | **awards**: `route_pieces`, `calculate_longest_road`, `update_longest_road`, `update_largest_army` |

## 3. The proposed split

Three extractions. Nothing else.

| New file | Takes | ≈ lines | Mirrors |
|----------|-------|---------|---------|
| `game/board_payload.py` → `class BoardPayload` | `get_board_data` (779–897) | 125 | — |
| `game/building_rules.py` → `class BuildingRules` | 402–718 minus `current_player_name` | 300 | `handlers/building.py` |
| `game/awards.py` → `class Awards` | 719–778 + 1218–1431 (`victory_points_for`, `public_victory_points`, `claim_victory`, `route_pieces`, `calculate_longest_road`, `update_longest_road`, `update_largest_army`) | 285 | — |

`game.py` lands at roughly **720 lines**: the class header, `__init__`, the
small accessors, production and costs, and dice.

### Why these three and not others

- **`get_board_data` is the highest-value extraction in the file.** It is the
  single place every UI feature adds a field, and the band containing it was
  touched by `engine`, `rules`, `progress cards` and `timers`. It is a pure
  read — it mutates nothing — so a mixin holding it cannot introduce an ordering
  bug. It is also the file that frontend work reaches into the engine to touch,
  which is exactly the cross-lane contention worth removing.
- **The building actions are the biggest single block** (317 lines, 21% of the
  file) and they already have a handler-layer counterpart (`handlers/building.py`,
  6 commits, 5 scopes). Making the engine boundary match the handler boundary is
  the same move that made `robber_rules.py` work.
- **Awards** (longest road, largest army, victory points) is 285 lines that
  nothing else in the file calls except through three named entry points, and
  it was its own scope in the log (`feat(scoreboard)`,
  `fix(rules): road wins are announced`).

### Why production, dice and `__init__` stay

- **Production and dice are the same subject as `distribute_resources`, and the
  `rules`/`engine` scopes that touch them are the same ones.** Splitting them
  buys no lane.
- **`__init__` cannot be safely split, and this brief does not try.** It is 202
  lines touched by five scopes — `maps`, `rules`, `engine`, `progress cards`,
  `timers` — and it is the second-worst contention point in the file. But
  construction order matters (`self.rules` before `self.bank` before
  `self.players` before `self.ck` before `_generate_board()`), and
  `persistence.py` reconstructs a `Game` and then writes attributes over it by
  name. Giving each mixin an `_init_x()` hook would move that ordering
  constraint out of sight for no measured gain: a rule addition is one or two
  attribute lines, i.e. the cheapest possible conflict. **Leave it. Say out loud
  that it stays contended.**

## 4. What must not move

- **Save-file compatibility.** `persistence.py` pins `SAVE_VERSION = 1`,
  refuses a file without `save_version`, and enumerates attribute names it
  copies back onto a reconstructed `Game` (`state_version`,
  `longest_road_holder`, `largest_army_holder`, …). **No attribute may be
  renamed, and none may move from `Game` onto a mixin instance.** The mixins
  hold no state — that is what the `robber_rules.py` docstring means by "it
  stays a mixin because every method reads Game state". Every extracted method
  keeps reading `self.*` exactly as it does today.
- **`from game.game import Game` must keep working unchanged.** Ten modules do
  it: `persistence.py`, `handlers/lobby.py`, `handlers/maps.py`,
  `tests/conftest.py`, and six test modules. `Game` stays in `game/game.py`,
  with the same name and the same constructor signature.
- **`rules.catalogue()` must stay importable without touching the filesystem.**
  `rules.py` has no `open()` today and the split must not give it one. Note that
  `game.py`'s `__init__` *does* read `server/data/costs.json` from disk — that
  read stays in `__init__`, in `game.py`, and must not migrate into any mixin
  that a catalogue import might pull in.
- **No engine code may branch on the name of an expansion.**
  `grep -rn "rules\['cities_and_knights'\]" server/` must stay empty. Moving
  code is a tempting moment to "simplify" a chain of rule checks into one; don't.
- **`check_invariants` stays in `game.py`.** It reads across every subsystem and
  is the cross-mixin sanity net; it belongs to the host, not to a part.
- **The comment on `victory_points_to_win`.** "Adding to it here instead rewrote
  an explicit choice — a table that asked for 10 got 11, or 13, with no clue
  why." That is a live invariant in `AGENTS.md` and `CLAUDE.md`; it stays
  attached to its line in `__init__`.
- **The `MAX_*` comment.** "The lobby can override them per game, so read
  `self.MAX_*` (the instance attribute), never the class constant." Extracted
  building code reads `self.MAX_SETTLEMENTS`; if a move turns it into
  `Game.MAX_SETTLEMENTS` the piece limits silently ignore the lobby.

## 5. Known hazards

- **Method Resolution Order.** Adding three bases to a tuple that already has
  eight means any name collision resolves silently by position. Before
  committing, prove there is none:
  ```bash
  .venv/bin/python - <<'EOF'
  import sys; sys.path.insert(0, 'server')
  from game.game import Game
  import collections
  seen = collections.Counter()
  for base in Game.__mro__[1:]:
      for name, value in vars(base).items():
          if callable(value) and not name.startswith('__'):
              seen[name] += 1
  print([n for n, c in seen.items() if c > 1])   # must be []
  EOF
  ```
- **`self.` attribute ownership.** No extracted method may *create* an attribute
  that `__init__` does not already set. Anything it creates lazily will be
  missing from a save file and will fail only on load, hours later.
- **This is the file another agent is most likely to be holding right now.**
  Twenty-five commits in three days. Coordinate before starting, do it in one
  sitting, and stage by explicit path — `git add server/game/game.py
  server/game/board_payload.py …`, never `git add -A`.
- **A split here is much harder to prove neutral than the CSS one**, because
  the code is executable and the diff is a move plus three new class headers plus
  three new import lines. Lean on the invariant checker and the persistence
  round trip, not on reading the diff.
- **Do not add a fourth extraction "while you are in there."** The measured
  case for these three is thin already; the case for a fourth is not there.

## 6. How to verify the split changed nothing

```bash
cd the repo root

# 1. The public surface of Game is identical.
.venv/bin/python -c "
import sys; sys.path.insert(0,'server')
from game.game import Game
print('\n'.join(sorted(n for n in dir(Game) if not n.startswith('__'))))" > /tmp/api-after
# and the same from the parent, in a scratch copy — NEVER git stash here:
TMP=$(mktemp -d); git archive HEAD~1 | tar -x -C "$TMP"
(cd "$TMP" && .venv/bin/python -c "
import sys; sys.path.insert(0,'server')
from game.game import Game
print('\n'.join(sorted(n for n in dir(Game) if not n.startswith('__'))))") > /tmp/api-before
diff /tmp/api-before /tmp/api-after        # MUST be empty

# 2. No MRO collision (script above). MUST print [].

# 3. The catalogue still imports with no filesystem access.
.venv/bin/python -c "
import sys, builtins; sys.path.insert(0,'server')
_open = builtins.open
def guard(*a, **k): raise AssertionError('rules touched the filesystem: %r' % (a,))
builtins.open = guard
from game import rules
print(len(rules.catalogue()), 'rules')
builtins.open = _open"

# 4. Save-file compatibility, both directions.
.venv/bin/python -m pytest -q tests/game/test_persistence.py \
    tests/game/test_seafarers_persistence.py \
    tests/game/test_progress_card_persistence.py -v

# 5. Everything.
.venv/bin/python -m pytest -q          # 998 fast tests
.venv/bin/ruff check server tests
.venv/bin/python -m pytest -q tests/test_browser_full_game.py \
    tests/test_browser_playthrough.py tests/test_browser_awards.py
# then the full browser suite before calling it done.
```

### What would prove a regression rather than merely passing

Unlike the frontend splits, the fast suite is the right gate here — it is where
the engine's rulebook pins live.

- `tests/game/test_persistence.py` failing means an attribute moved or a lazily
  created one appeared. This is the failure that would ship a game that cannot
  be loaded, and it is the one to watch hardest.
- `tests/game/test_rules_options.py` failing means an extracted method stopped
  reading `self.rules[...]` where it used to — the "a rule the engine ignores"
  failure `CLAUDE.md` treats as worse than no rule.
- `tests/game/test_board.py` and `test_two_island_boards.py` failing means the
  building extraction lost a distance-rule or connectivity check.
- `test_browser_full_game.py` with `CATAN_SEED` set: a game that reaches a
  winner before and stalls a point short after means the awards extraction broke
  `update_longest_road` / `update_largest_army`. Run it seeded, twice; the
  project's own note is that "a gate that passes two runs in three is not a
  gate".
- `Game.check_invariants()` returning a non-empty list at the end of any
  playthrough test is a direct hit.

## 7. How much parallelism this actually buys

Less than the frontend splits, and it is worth being blunt about that.

What it does buy:

- **`board_payload.py` decouples frontend-driven engine work from rules work.**
  Today, "add a field the client needs" and "change how a rule scores" both open
  `game.py`. After, the first opens `board_payload.py` and the second does not.
  That is one real lane, and it is the lane that crosses teams.
- **`building_rules.py` lets building work and production/dice work run at
  once**, and it aligns the engine boundary with `handlers/building.py` so a
  building change is two files that nobody else wants.
- **`awards.py`** takes the scoreboard/longest-road lane out of the engine
  host — the same lane `scoreboard.js` takes out of `panels.js`, so a scoreboard
  task ends up owning `awards.py` + `scoreboard.js` and colliding with nobody.

What it does not buy: `__init__` stays a five-scope contention point, and
`rules.py` (9 co-changes with this file) is deliberately not split. Realistically
this takes `game.py` from "most engine work must open it" to "about half of
engine work must open it" — call it **two concurrent engine agents where today
there is one**, against a materially higher risk than any other brief here.

That is why it is fifth in the order and not first, despite having the worst
interleaving score.
</content>
