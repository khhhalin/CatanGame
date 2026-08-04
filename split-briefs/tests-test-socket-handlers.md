# `tests/test_socket_handlers.py` — SPLIT. Nearly free; slot it into any gap.

1845 lines, 26 test classes.

## 1. Why this file is contended

Window: `--since='2026-08-03 00:00'`, 135 commits.

- **8 distinct work-scopes**: `engine`, `feat`, `fix`, `handlers`, `rules`,
  `seafarers`, `server`, `test`.
- **15 commits** — fourth-highest in the repository.
- Co-changes: 5 with `handlers/dev_cards.py`, 4 with `server/app.py`, and one
  each with most of the handler layer.

The cause is written into `CLAUDE.md`:

> Layer boundaries — `tests/test_socket_handlers.py` drives real clients through
> real handlers. Untrusted payloads belong here.

That instruction is correct and should not change. Its consequence is that
**every feature that adds a socket event adds a class to this one file** — and
the handler layer it tests is already split across eleven modules
(`handlers/lobby.py`, `handlers/trading.py`, `handlers/cities_knights.py`, …),
none of which is above 8 commits. The tests are the last unsplit layer.

This one is ranked fifth only because it does not block *feature* work the way
the frontend files do — but it blocks the test-writing half of every feature,
which under this project's "a bug fix requires a failing test first" rule is the
half that comes **first**.

## 2. The seams that already exist

Twenty-six classes, already grouped by subject, already named after what they
check:

```
  16–50  fixtures/helpers: clients, events, last_error, seated
  51     TestConnectionAndState
  73     TestHiddenInformationOverTheWire
 106     TestDevCardFollowUpsRequireTheCard
 169     TestDiscardOverTheWire
 195     TestErrorsAreTargetedAndCoded
 219     TestPieceLimitsOverTheWire
 240     TestIdentityComesFromTheConnection
 394     TestConcurrentJoins
 417     TestLobbyPresence
 500     TestNameCollision
 551     TestLobbyRules
 766     TestEndGame
 823     TestStartingAGame
 889     TestChatAndEventLog
 977     TestSlashCommands
1140     TestHandlersToleratePayloads
1183     TestServerErrorReporting
1208     TestCitiesKnightsOverTheWire
1348     TestBarbarianClock
1443     TestSeafarersOverTheWire
1597     TestAnsweringAPendingChoice
1700     TestCommoditiesReachTheTradeHandler
1762     TestTheLogSaysWhoTheRollPaid
```

The four module-level helpers at lines 16–50 (`clients`, `events`,
`last_error`, `seated`) are the only shared surface. Nothing outside this file
imports anything from it.

## 3. The proposed split

A package, `tests/handlers/`, mirroring `server/handlers/` the way `tests/game/`
already mirrors `server/game/` — the local precedent is right there.

| New file | Classes | ≈ lines |
|----------|---------|---------|
| `tests/handlers/conftest.py` | `clients`, `events`, `last_error`, `seated` | 45 |
| `tests/handlers/test_identity_and_presence.py` | ConnectionAndState, IdentityComesFromTheConnection, ConcurrentJoins, LobbyPresence, NameCollision | 400 |
| `tests/handlers/test_lobby_and_rules.py` | LobbyRules, StartingAGame, EndGame | 340 |
| `tests/handlers/test_turn_actions.py` | DevCardFollowUpsRequireTheCard, DiscardOverTheWire, PieceLimitsOverTheWire, AnsweringAPendingChoice | 260 |
| `tests/handlers/test_trading.py` | CommoditiesReachTheTradeHandler | 65 |
| `tests/handlers/test_cities_knights.py` | CitiesKnightsOverTheWire, BarbarianClock | 235 |
| `tests/handlers/test_seafarers.py` | SeafarersOverTheWire | 155 |
| `tests/handlers/test_chat_and_log.py` | ChatAndEventLog, SlashCommands, TheLogSaysWhoTheRollPaid | 250 |
| `tests/handlers/test_untrusted_payloads.py` | HiddenInformationOverTheWire, ErrorsAreTargetedAndCoded, HandlersToleratePayloads, ServerErrorReporting | 140 |

`tests/test_socket_handlers.py` ceases to exist.

Put the shared helpers in `tests/handlers/conftest.py` rather than a helper
module, so pytest injects the fixtures and no new import lines are needed. Check
first whether `socket_app` comes from the root `tests/conftest.py` (100 lines) —
if so it is already inherited and nothing needs to move for it.

**`test_untrusted_payloads.py` is the one to name carefully.** `CLAUDE.md`
singles out untrusted payloads as belonging to this layer; that instruction
should point at an obviously-named file afterwards. Consider updating that one
line of `CLAUDE.md` in the same commit — it is the only doc reference to the old
filename.

## 4. What must not move

- **Not one test may be deleted, renamed, merged or weakened.** `CLAUDE.md`:
  "Never delete a test because it fails" and "Deleting a good test is worse than
  keeping a mediocre one." A split is the classic opportunity to quietly drop a
  slow or awkward test. Don't.
- **Docstrings travel with their tests.** Several are regression tests named
  after real failures, and the project's rule is that such a test says so in its
  docstring. That naming is the test's value.
- **The four helpers keep their exact semantics.** `seated(name, **clients)`
  and `events(client, name)` encode assumptions about the socket test client's
  buffering; re-implementing them as fixtures with different scope will produce
  flakiness that looks like a handler bug.
- **Determinism.** `CLAUDE.md`: inject `random.Random`, never seed the global
  module; never assert on set or dict iteration order. If any test currently
  depends on class-ordering within the module (it should not, but check), the
  split will expose it — that is a real bug found, not a split to undo.

## 5. Known hazards

- **The lowest-risk brief in this set.** No production code, no imports to
  rewire, no cycles possible: nothing in the repository imports this module.
- **Test ids change** — `tests/test_socket_handlers.py::TestLobbyRules::…`
  becomes `tests/handlers/test_lobby_and_rules.py::TestLobbyRules::…`. Anything
  pinning a full node id (a CI config, a `-k` recipe in a doc) needs the update.
  Grep for the old path before committing.
- **Fixture scope.** If any fixture in the file is module-scoped, splitting the
  module changes how often it is built. That can be a real speed-up or a real
  slow-down; measure the wall clock before and after.
- **A `tests/handlers/__init__.py` may or may not be wanted** — match whatever
  `tests/game/` does, don't invent a new convention.

## 6. How to verify the split changed nothing

```bash
cd the repo root

# The set of tests must be identical, ignoring only the module path.
.venv/bin/python -m pytest --collect-only -q 2>/dev/null \
  | grep '::' | sed 's|^.*::||' | sort > /tmp/tests-after

TMP=$(mktemp -d); git archive HEAD~1 | tar -x -C "$TMP"   # never git stash here
(cd "$TMP" && .venv/bin/python -m pytest \
   --collect-only -q 2>/dev/null) | grep '::' | sed 's|^.*::||' | sort > /tmp/tests-before

diff /tmp/tests-before /tmp/tests-after      # MUST be empty

# Counts, as a second check: 998 collected fast, 237 browser deselected.
.venv/bin/python -m pytest --collect-only -q 2>&1 | tail -1

# Nothing references the old path.
grep -rn "test_socket_handlers" --include='*.py' --include='*.md' \
     --include='*.toml' --include='*.json' . | grep -v '^./.git'

.venv/bin/python -m pytest -q tests/handlers/ -v
.venv/bin/python -m pytest -q
.venv/bin/ruff check server tests
```

### What would prove a regression rather than merely passing

- **The collect-only diff being empty is the gate.** A non-empty diff means a
  test was lost, which is the only outcome that actually matters here.
- A test that now *passes* where it used to fail, or vice versa, means a
  fixture's scope or ordering changed — investigate before accepting either.
  `CLAUDE.md`: "Check your test fails before you believe it."
- Run the new package twice with `-p no:randomly` off and on if the project uses
  random ordering; a test that only passes in the old module order was relying
  on leaked state and needs fixing, not reverting.
- The browser suite is unaffected by this change and does not need re-running
  for it — the one brief here where that is true.

## 7. How much parallelism this actually buys

The eight scopes that opened this file map cleanly:

- `seafarers` → `test_seafarers.py`
- Cities & Knights work → `test_cities_knights.py`
- `handlers` / lobby work → `test_lobby_and_rules.py`
- `server` / security work → `test_untrusted_payloads.py`
- the chat/slash-command feature (`23eaa85`, the most recent commit at time of
  writing) → `test_chat_and_log.py`

Under this project's rules a feature is not done until its handler test exists,
and a bug fix must start with a failing test. So this file sits on the **front**
of every engine and handler task, not the back. Splitting it means the seafarers
agent and the knights agent can each write their layer-boundary test at the same
moment they write the handler — which today they cannot.

Call it **the removal of a shared front-of-queue for every server-side task**.
It costs almost nothing and it can be verified exactly. If there is a lull, do
this one.
</content>
