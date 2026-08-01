# Compliance Audit — CatanPro vs `coding-rules.md`

> **STATUS — remediated.** Every finding below has been addressed except the
> identity model, which the team keeps deliberately (see "Accepted by design").
> 67 tests pass, ruff is clean, and the fixes were verified end-to-end against
> the real gunicorn server. See "Remediation summary" at the bottom.


Three independent audits covering all five Parts of `coding-rules.md`, run against
`server/app.py` (1174 lines), `server/game/*.py`, `server/static/js/*` (2182 lines),
`server/templates/index.html`, and the infra files.

Every finding below was confirmed by reading the actual code. Findings the auditors
could not substantiate were dropped.

## Verdict

The game logic is well separated from transport and the rules engine is sound — that
is the project's real asset and it makes most of the fixes cheap. Everything around
it is not yet a server: there is no identity, no authorization, no persistence of the
game, no tests, and the container ships a remote code execution console.

**Nothing here is a design dead end.** The board, the rules engine, and the renderer
are all reusable as-is.

| Severity | Count | Theme |
|---|---|---|
| Critical | 7 | identity spoofing, hidden-information leak, resource duplication, RCE |
| High | 12 | no production runner, no tests, no config, canvas/DPI, listener and error paths |
| Medium | 17 | protocol shape, rooms, logging, module size, determinism |
| Low | 2 | logging of rejections, missing global error net |

---

## Critical

### C1. Any client can act as any player
`server/app.py` — 18 handlers, including `:174`, `:251`, `:314`, `:430`, `:622`, `:761`, `:819`

Every handler derives the actor from the payload:
```python
name = data.get('name', '')
current_player = current_game.players[current_game.current_player_index]
if current_player.name != name:
    emit('error', {'message': f'Only {current_player.name} can roll dice'})
```
There is no `request.sid`, no `session`, and no socket→player map anywhere in the file.
Player names are broadcast publicly in `user_list` and `turn_changed`, so no guessing
is needed.

**Impact:** any connected socket — including a spectator or a tab that never joined —
can take the current player's entire turn: roll, build, buy and play dev cards, move
the robber, and discard *another player's* cards.

**Fix:** bind `request.sid → (game, player)` at join, look it up at the top of every
handler, delete the `name` field from all inbound payloads.

### C2. Every player's hand and the dev-card deck are broadcast to everyone
`server/game/player.py:41-53`, `server/game/game.py:726-728`, broadcast from 25 sites

`to_dict()` returns `'resources': self.resources, 'dev_cards': self.dev_cards` in full,
`get_board_data()` includes `'dev_card_deck'`, and every state change sends it with
`broadcast=True`. `get_board_data()` takes no viewer argument — no per-player
projection exists anywhere.

**Impact:** open DevTools → Network → WS and read every opponent's exact hand,
including unplayed victory-point cards, plus the remaining deck composition. Perfect
information. Undetectable in play.

**Fix:** `get_board_data(viewer)` returning own hand in full and opponents as counts;
emit per-socket instead of broadcasting.

### C3. `use_invention` grants unlimited free resources to anyone
`server/app.py:845-871`

No turn check, no phase check, and no check that an Invention card was ever played —
`handle_play_dev_card` sets no pending state that this handler consults. `count` is
unvalidated.

**Impact:** any client, at any time, without owning a card, drains the bank into any
player's hand — repeatedly. `{"wood": 1000000000}` also spins `range(count)` in the
greenlet and stalls every game on the process.

**Fix:** require a server-set `pending_invention` owned by the current player, cap at
exactly 2, validate each count as an int in range.

### C4. `use_monopoly` has no turn check and no card check
`server/app.py:916-934`, `server/game/game.py:1013-1037`

`use_monopoly` validates only that the resource type is known.

**Impact:** any client at any time transfers every card of a chosen resource from all
players into a hand of their choosing, with no card ever bought.

**Fix:** gate on a server-set `pending_monopoly` owned by the current player.

### C5. Negative counts in `discard_resources` mint resources
`server/game/game.py:860-875`

```python
if current < count:      # 0 < -50 is False, so this passes
    return False
player.resources[resource_type] -= count      # -= -50 ADDS 50
self.bank.return_resources(resource_type, count)   # negative amount drains the bank
```
Resource keys are unvalidated too, so `{"gold": -50}` creates a `gold` entry in both
the hand and the bank.

**Fix:** reject any key outside the five-resource allowlist and any value that is not
an int in `0..holdings`.

### C6. Negative counts in the bank trade mint resources
`server/app.py:971-1014`

`wanted` values are never validated, and `bank.take(resource)` removes exactly 1 while
`+ count` adds arbitrarily. `wanted = {"ore": 100, "wheat": -99}` sums to 1, so the 4:1
ratio gate passes and the player receives 100 ore for 4 wood.

**Fix:** validate keys and positive-int values; call `bank.take` once per unit granted.

### C7. The container ships a remote code execution console
`server/app.py:1173-1174`, `Dockerfile:12`

```python
socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
```
`Dockerfile:12` is `CMD ["python", "app.py"]`, so this is the deployed line. Flask-SocketIO
wraps the app in `DebuggedApplication(..., evalex=True)` when `debug` is true and the
async mode is not `threading` — and the resolved mode is `eventlet` (confirmed by
importing from the project's own venv). `docker-compose.yml:12`'s `FLASK_DEBUG=0` does
**not** stop this: `run()` assigns `app.debug` from the explicit keyword argument.

**Impact:** arbitrary Python execution for anyone who can reach port 5000 and trigger a
traceback.

**Fix:** remove the `debug`/`allow_unsafe_werkzeug` call from the deployed path; add
`wsgi.py` and a real server command.

---

## High

### H1. Hardcoded `SECRET_KEY`
`server/app.py:10` — `app.config['SECRET_KEY'] = 'catan-secret-key'`. No `os.environ`
call exists anywhere in `server/`. The key is in git history. Blast radius is limited
today only because sessions are unused (H5) — fixing H5 without this converts it into
a full authentication bypass.

### H2. No production runner exists
No `gunicorn` in `requirements.txt`, no `wsgi.py`, no `run.py`. The only entry point is
the dev server from C7.

### H3. Async mode unpinned, resolves to deprecated eventlet
`server/app.py:11` is `SocketIO(app)` with no `async_mode`; `requirements.txt:4` pins
`eventlet>=0.34.0`; `AGENTS.md:190` recommends eventlet, contradicting the new rules.
**The migration is small**: `simple_websocket` is already installed, and there is no
`monkey_patch()` call anywhere in the codebase. It is: drop eventlet, add
`simple-websocket`, set `async_mode="threading"`, uninstall eventlet from the venv,
update `AGENTS.md`. It must land together with H2, because under threading mode
`socketio.run()` hits the Werkzeug guard that `allow_unsafe_werkzeug=True` suppresses.

### H4. No configuration layer
No config module. `MAX_PLAYERS`, the data path, and the victory threshold (`vp >= 10`
at `:415`, `:604`, `:696`) are literals. No `SESSION_COOKIE_*` flags anywhere.

### H5. Reconnect reclaims a seat by name
`server/app.py:77-84`, `:109-116`. Names are public. Anyone sending `{"name": "Alice"}`
gets Alice's seat and a full board snapshot. `handle_disconnect` (`:1168`) is `pass` —
no disconnect marking, no grace timer, and stale entries accumulate in `users.json`
against `MAX_PLAYERS`.

### H6. No `on_error_default`; exceptions vanish silently
`grep "on_error"` → no matches. `grep -c "try:"` → **0**. No handler returns an ack
object either, so a crashed handler leaves the player with no error, no acknowledgement,
and no disconnect. Reachable crashes exist at `:680` and `:861-862`.

### H7. No tests at all
No `tests/`, no `conftest.py`, no `test_*.py`, no pytest dependency. `.dockerignore:7`
excludes a `**/tests` that does not exist; `AGENTS.md` instructs "ensure all tests pass".
**This is the cheapest gap to close** — `server/game/` imports no transport (verified),
so the rules engine is testable today with no refactor.

### H8. No `.gitignore`; bytecode and live game state are committed
`git ls-files` shows 7 committed `.pyc` files (plus untracked `cpython-314` copies from
a second interpreter), `server/data/game.json`, and `server/data/users.json` containing
real play-session players. `docker-compose.yml:9` bind-mounts `./server/data`, so every
deploy stamps committed player data over live state. (`costs.json` is correctly
committed — it is static rule data.)

### H9. No tooling configuration
No `pyproject.toml`, `ruff.toml`, `mypy.ini`, `pytest.ini`, `Makefile`, or `.github/`.

### H10. Unpinned dependencies; three environments disagree
All four requirement lines are open ranges — including the rules' own example,
`flask>=3.0.0`. `Dockerfile:1` targets python 3.13, `.venv` is 3.14 (and carries
`simple_websocket`, declared in no requirements file), and `shell.nix:6-11` omits
`python-socketio` and `eventlet` entirely, so the Nix shell alone cannot run the server.
The dual-version `.pyc` files are the fingerprint of this split.

### H11. `displayError` is called 7 times and never defined
`client.js:225, 230, 235, 566, 571, 576, 583`. `grep` finds zero definitions. Every one
of these paths throws `ReferenceError` inside a click handler, which aborts the handler —
so clicking "Buy Card" out of turn silently does nothing.

### H12. Canvas has no devicePixelRatio handling, and CSS scaling breaks clicks
`board-renderer.js:337-338` sets `canvas.width/height` from board extents with no DPR
anywhere in the file, while `style.css:196-199` applies `max-width: 100%`. The hit-tester
(`client.js:274-277`) assumes buffer space equals CSS space. Two confirmed defects: the
board renders soft on any high-DPI screen, and the moment `max-width` engages the click
mapping skews progressively worse away from the origin — with a 15px `clickRadius`,
edge-of-board clicks land on the wrong vertex or on nothing.

### H13. Socket callbacks draw directly; no rAF loop
`grep requestAnimationFrame` → **no matches**. Five socket handlers call the renderer
synchronously (`client.js:1249, 1306, 1372, 1390, 1404`). A single `roll_dice` produces
up to three server events in one tick, each triggering a full redraw that reallocates the
canvas buffer.

### H14. No `disconnect` / `connect_error` handling
`grep "connect_error|disconnect|reconnect"` in `client.js` → **zero matches**. On Wi-Fi
loss the board freezes silently and every click is dropped; there is no `socket.connected`
guard before any of the 22 emits.

### H15. `alert()` for all errors, including inside the render path
Nine calls. The worst is `client.js:645` inside `updateGameUI`, which runs on every
`board_updated` — and `must_move_robber` stays true across many updates, so the player
gets a **modal re-fired on every board update** until they move the robber, each one
freezing the tab.

### H16. `resource_stolen` broadcasts which resource was stolen
`server/app.py:905-909` uses `broadcast=True`. The client at `client.js:1515` guards the
message on the recipient being the victim — but the payload already reached everyone.

### H17. No protocol document
The 41-event contract exists only as grep output.

### H18. `refresh_board` is client-timer-driven and broadcasts
`server/app.py:1119-1126` broadcasts a full board; `client.js:867` calls it from a
1-second `setInterval` on *every* client. One expiring trade offer produces N² full
snapshots.

### H19. Reconnect resync is incidental
`app.py:104-117` only replies with `game_state` when the game has already started, so a
client reconnecting during the lobby gets nothing and must reload.

### H20. Error events carry no machine-readable code
All 40+ error emits are prose-only; `client.js:1564` is `alert(data.message)`. The client
can never distinguish recoverable from fatal.

### H21. No ES modules; everything on `window`
`index.html:194-197` loads two classic scripts sharing one global scope;
`board-renderer.js:605` assigns `window.BoardRenderer`. Load-order dependent, no strict
mode, all internals writable from the console.

---

## Medium

**Server:** no rooms — all 40 state emits use `broadcast=True` on the default namespace,
so only one game is possible (`current_game` is a module global at `:16`); no application
factory and a 1174-line handler module; `allow_unsafe_werkzeug` present (currently inert
under eventlet, load-bearing after H3); single-process assumption undocumented and
unenforced; `save_users` (`:44-46`) rewrites `users.json` in place with no lock or atomic
rename, so a greenlet switch mid-write truncates it; no per-game lock, so two
`buy_dev_card` events in one tick both draw the last card; no invariant checks and **no
piece limits at all** — a player can build unlimited settlements, cities, and roads, and
victory points scale directly with those lists; setup phase permits unlimited free
settlements and a road with no settlement (`:366-372`, `:459-466`); bank trade partially
applies on failure (`:1011-1022`); trade completion reuses a stale affordability check;
turn timers are client-driven and, once expired, `next_turn` accepts *any* requester;
weak RNG (Mersenne Twister) plus a **biased dev-card draw** — `bank.py:45` uses
`random.choice` over *distinct remaining types*, so a knight (14 in deck) is as likely as
a monopoly (2 in deck); no type or shape validation on any payload field; `start_game`,
`set_color`, and `refresh_board` require no identity at all; 58 `print()` calls (35 in
`app.py`, 23 in `game.py`) with zero `logging` usage — including `app.py:969` printing a
player's full private hand; `game.py` is 1251 lines; module-level `random` throughout the
engine blocks deterministic tests; handlers are fat (the settlement distance rule lives in
`app.py:304-417`, not the engine); the engine reads `costs.json` from disk in its
constructor.

**Protocol:** no `state_version`, no `request_id`, no idempotency; no acknowledgement
callbacks anywhere; no protocol version in the handshake; naming violations —
`choose_victim` and `discard_required` are imperative server→client events,
`game_state`/`user_list` are bare nouns, `next_turn` and `refresh_board` are misnamed
commands; ten handlers `return` silently on rejection, leaving the client hanging.

**Frontend:** no single state object — eleven module-level `let`s mixing server state and
UI state; the renderer mutates shared geometry as a side effect of drawing
(`board-renderer.js:429-435`), so hit detection is undefined until a render has happened;
`click` only, no pointer events, no `touch-action` (so a finger drag scrolls the container
instead of registering); listeners re-registered inside `renderDevCards()` on every server
event (not a duplicate-fire bug — `innerHTML` orphans the old nodes — but the markup
already carries `data-card-type`, so delegation is a one-line change); `setInterval` emits
game commands (`client.js:1197`, `:1206`) and will auto-roll and auto-end a turn from a
backgrounded tab; `client.js` is 1572 lines mixing all four layers; no `aria-` attributes
anywhere and the canvas has no `tabindex`/`role`/`aria-label`.

## Low

Rejected actions are not logged with identity and reason, so protocol probing produces
zero server-side signal. No global `error`/`unhandledrejection` net, no `resize` handler,
no `onerror` fallback on the CDN-loaded Socket.IO script (`index.html:194` — a blocked CDN
yields a blank game), and no `.catch()` on the audio `play()` promise.

---

## Confirmed compliant

Worth stating plainly, because these are the parts you do not need to touch:

- **`server/game/` imports no transport.** Verified by grep — the only match for
  `flask|socketio|emit\(|request\.|session` across all five modules is the word "session"
  inside a docstring. This is the single most valuable structural property in the repo.
- **Clients send intent, not outcome.** Every command carries identifiers
  (`vertex`, `edge`, `hex`, `card_type`, `offer_id`), never computed state.
- **Costs are server-side.** Read from `data/costs.json`, never from the payload.
- **Victory points are recomputed from primary state** (`player.py:65`), not maintained
  as a drifting counter.
- **Full snapshots over deltas** — the right call for a turn-based game, and already done.
- **Socket handler registration hygiene is clean.** All 21 `socket.on` calls are at the
  top level; the `connect` handler registers nothing. The classic
  duplicate-handlers-on-reconnect bug is not present.
- **Errors are correctly sender-targeted.** All ~40 `emit('error', ...)` calls omit
  `broadcast=True`. No state update is missing `broadcast=True` either — the "works on my
  screen but not theirs" bug is not present.
- **CORS is compliant** — default same-origin, no `"*"` anywhere.
- **Geometry math is shared** between renderer and hit-tester rather than duplicated.
- **Built-in Socket.IO reconnection is relied upon**; no hand-rolled retry loop.
- **Canvas context state is reset** after the highlight path (`board-renderer.js:100-102`).
- **Action buttons are real `<button>` elements**, so they are keyboard-reachable.

---

## Suggested order

1. **Identity** (C1, H5) — one `sid → player` map fixes the single largest class of
   exploit and unblocks C3/C4 and per-player filtering.
2. **Deployment** (C7, H2, H3, H1) — one change: `wsgi.py` + gunicorn + threading mode +
   `SECRET_KEY` from env. Removes the RCE.
3. **Input validation** (C5, C6, C3, C4) — an allowlist + positive-int check on every
   resource dict closes the duplication exploits.
4. **Hidden information** (C2, H16) — `get_board_data(viewer)` plus per-socket emit.
5. **Tests** (H7) — start on the rules engine; it needs no refactor. Inject the RNG first
   so dice and shuffles are reproducible.
6. **Hygiene** (H8, H9, H10) — `.gitignore`, `git rm --cached`, `pyproject.toml`, pinned lock.
7. Frontend correctness (H11, H12, H13, H14, H15) — the four live user-facing bugs.


---

# Remediation summary

## Accepted by design, not fixed

**C1 — any client can act as any player.** Kept deliberately. This is a private
game between people who trust each other, and being able to take a turn for
someone who stepped away is a feature they want. Handlers still take the acting
player from the payload.

The one thing that changed around it: each socket now has a *private view*
bound to the name it joined as, so hidden information is filtered per
connection. Taking over a seat is done by joining as that player, which also
switches the view. Verified live — rejoining as Bob flips `is_you` to Bob and
hides Alice's hand.

If this game is ever exposed beyond the group, C1 becomes a real hole and the
`socket_viewers` map already has the binding needed to close it.

## Fixed

| Finding | Fix |
|---|---|
| C2 hands broadcast to everyone | `get_board_data(viewer)` builds a per-recipient payload; opponents reduced to `resource_count`/`dev_card_count`. Deck composition replaced with a single `dev_cards_remaining`. Every board push is now per-socket. |
| C3 `use_invention` unauthorized | Requires a server-set `pending_invention` naming the player, capped at exactly 2 resources, cleared on use and at turn end. |
| C4 `use_monopoly` unauthorized | Requires `pending_monopoly`; resource type validated against an allowlist. |
| C5 negative-count discard | `clean_resource_counts` rejects non-int, negative, and unknown keys at the boundary; the engine re-checks so it is safe to call directly. |
| C6 negative-count bank trade | Same validation, plus the bank is checked for the *whole* trade before anything mutates, and `take()` is called once per unit granted. |
| C7 RCE console in the container | `Dockerfile` runs gunicorn against a new `wsgi.py`. `debug`/`allow_unsafe_werkzeug` gone from the deployed path. Threading mode also means Flask-SocketIO never wraps the app in `DebuggedApplication`. |
| H1 hardcoded `SECRET_KEY` | Read from the environment; production raises at startup if missing. |
| H2 no production runner | `server/wsgi.py` + gunicorn, with the `-w 1` constraint documented where someone would change it. |
| H3 eventlet | Removed. `async_mode='threading'` pinned explicitly, `simple-websocket` added — websocket transport confirmed live. |
| H4 no config layer | `server/config.py` with Development/Testing/Production, safe-by-default cookie flags, and the game knobs. |
| H5 disconnect no-op | Drops the view binding and logs; the seat survives, as it should. |
| H6 no `on_error_default` | Added: logs with event/sid context and returns a coded error instead of the action vanishing. |
| H7 no tests | 67 tests: board invariants, costs, discards, piece limits, victory points, hidden information, plus socket-level tests that drive the actual exploits. |
| H8 committed junk | `.gitignore` added; `__pycache__` and runtime state untracked (files kept on disk). |
| H9 no tooling | `pyproject.toml` with ruff, mypy (strict on `game/` only), and pytest config. |
| H10 unpinned deps | Upper bounds on every dependency; `shell.nix` brought in line and given the dev tools. |
| H11–H15, frontend | `displayError` defined; all 9 `alert()` calls replaced with a non-blocking `aria-live` region; DPR handling and hit-test scaling unified; single rAF loop with a dirty flag; `disconnect`/`connect_error` handling with a status indicator; pointer events; delegated listeners; the backgrounded-tab auto-play removed. |
| H16 `resource_stolen` broadcast | The resource is sent only to thief and victim; the table sees that a steal happened. |
| H18 `refresh_board` broadcast | Replies to the asker only. |
| H19 reconnect resync | A join always gets a snapshot, in game or in lobby; `request_state` added. |
| H20 no error codes | One shape everywhere: `{code, message}`, sender-targeted, every rejection logged. |
| Medium | Per-game lock around validate-then-apply; piece limits (5/4/15) enforced and roads finally tracked on the player; `check_invariants()` run after every mutation; atomic `users.json` writes; RNG injected throughout and dev-card draws weighted by remaining count; 58 `print()` calls replaced with `logging`; server-side turn watchdog; `state_version` on every payload. |

## Bugs found while fixing, not in the original audit

1. **Board generation dropped a tile type.** The resource list had 20 entries
   for 19 land hexes, so one tile's type was discarded at random and the mix
   differed every game. It was also the wrong distribution. Now the correct
   4 wood / 4 wheat / 4 sheep / 3 brick / 3 ore / 1 desert, asserted to total 19.
2. **Board generation was not reproducible even with a fixed seed**, because it
   used module-level `random` and iterated a `set`. Both fixed; a test pins it.
3. **Concurrent joins lost players.** `handle_join` did read-modify-write on
   `users.json` without holding the lock across both halves, so two players
   joining at once left only one in the file — caught by driving two real
   clients at the production server. `update_users()` now holds the lock across
   the whole cycle, with a threaded regression test.
4. **`handlePlayDevCard` compared a dict to a number** (`dev_cards[type] <= 0`),
   so its "you do not have this card" branch could never fire.
5. **`logToGameConsole` was called but never defined** — the same class of bug
   as `displayError`.

## Deferred

- **ES-module migration of the frontend (H21).** Large mechanical churn; the
  client still uses `window.BoardRenderer`. Worth doing before the file grows.
- **Splitting `app.py` (1400 lines) and `game.py` (1250 lines).** The `E501`
  line-length check is disabled until these are split; see `pyproject.toml`.
- **Rate limiting (H7 in Part II).** Genuinely useful only once the game is
  reachable beyond the group; noted rather than built.
- **Protocol document and event renames.** The naming inconsistencies
  (`choose_victim`, `next_turn`, `refresh_board`) are unchanged so the client
  and server stay in step; renaming is a coordinated change.
- **Persisting game state.** Still in memory only, so a restart loses the game.
  The single-worker constraint is now documented rather than accidental.
