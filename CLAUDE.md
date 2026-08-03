# CLAUDE.md

Read `AGENTS.md` for commands and style, `coding-rules.md` Part V for how to test
socket handlers, fixtures and determinism. This file is about **which tests are
worth writing**. Every rule below is here because something in this repo went
wrong without it.

## The bar

The suite once held 513 tests. A human played the game and filed 27 bugs. The
suite caught none of them. Among them: the board dealt 30 number tokens into 18
slots, with dice-weighted frequencies, so every board ever generated was wrong —
and 447 tests passed over it.

**A test earns its place only if it can fail for a reason a player would notice.**
Before writing one, say out loud what breakage it catches. If the answer is "the
code was edited", delete it.

Write:
- Rulebook pins — costs, the 18 tokens, 19 hexes, 9 harbours, discard at 8, harbour rates, victory targets.
- Regression tests for bugs that really happened. These are the best tests here. Name them after the failure and say so in the docstring.
- Layer boundaries — `tests/test_socket_handlers.py` drives real clients through real handlers. Untrusted payloads belong here.
- End-to-end browser tests. See below.

Never write:
- A test that asserts a constant equals the same constant, or that a setter set.
  Deleted: `TestStateVersion` asserted that incrementing `state_version` reported
  the incremented value — no client JS reads the field at all.
- A test of Python or the stdlib. Deleted: a test that a timestamp `isinstance`
  float when the fixture clock returns a float; a test that two
  `random.Random(7)` instances roll the same face.
- A second test that restates the first in different words. One test that pins
  the exact list beats three that pin its length, its order, and its type.
- A test whose setup cannot reach the state it claims to check.
  `test_only_two_knights_of_each_rank` builds knights for a player with no roads,
  places nothing, then asserts `1 <= 2`. It cannot fail. Check your test fails
  before you believe it.

## A bug fix requires a failing test first

Write the test, watch it fail *for the reason the bug describes*, then fix.
`test_the_card_is_surrendered_when_the_road_is_broken` was written this way — it
failed with `assert 'Bob' is None` before the fix, which proved it was pointed at
the real defect. A test written after the fix only proves the code does what it
now does.

## Hardcoded lists must be asserted against what they have to match

Both board bugs were a literal drifting away from the thing it filled: a 30-entry
token pool for 18 slots, and a 20-entry resource list for 19 hexes. **A test that
copied either literal would have passed.**

So: assert the literal against the *generated board*, never against another copy
of the literal.

```python
# Right — the literal is checked against what generation actually dealt.
numbers = sorted(h.number for h in game.hexes.values() if h.type not in ('ocean', 'desert'))
assert numbers == [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]

# Wrong — passes forever, whatever the board does.
assert len(board.NUMBER_TOKENS) == len(board.NUMBER_TOKENS)
```

The same applies to any table the engine consumes: check it where it is used, not
where it is declared.

## Browser tests are the ones that catch real breakage

`tests/test_browser_*.py` are the only tests that have ever caught a regression a
player would have hit: the Start button vanishing, chat having no input at all,
`start_game` crashing on a payload, a board that rendered blank. They catch these
because the unit suite asserts on server state, and every one of those bugs left
server state perfectly correct.

- Do not delete a browser test to make the suite faster. Argue it in a PR first.
- A canvas assertion must count pixels. A blank canvas satisfies every DOM assertion.
- Assert what a player sees — a visible button, a rendered message, a winner's
  banner — not that a handler was called.
- When a UI bug is reported, the regression test goes here, not in the unit suite.

## Determinism

- Inject `random.Random`; never seed the global module. (`coding-rules.md` Part V.)
- Seed anything that plays a whole game. `test_browser_full_game.py` passes
  `CATAN_SEED`; unseeded it reached a winner, then stalled a point short on
  identical code. **A gate that passes two runs in three is not a gate.**
- Never assert on set or dict iteration order. Board generation once varied per
  process because it iterated a set of string keys — the same seed built
  different boards, and a test passed four times in five.

## Before you call it done

- `./.venv/bin/python -m pytest -q` passes, and `./.venv/bin/ruff check server tests` is clean.
- A test that fails is a bug report. Fix the code or file it. **Never delete a test because it fails.**
- Deleting a good test is worse than keeping a mediocre one. When unsure, keep it and write down why.
