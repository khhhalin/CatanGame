# Coding Rules — CatanPro

Grand rules for writing any code in this project: a Python/Flask/Flask-SocketIO
game server with a vanilla JavaScript frontend. Read this before writing code;
consult the relevant section before touching that layer.

`AGENTS.md` covers naming, formatting, and style. This file covers architecture,
correctness, and security — the decisions that are expensive to reverse later.

## The five rules that matter most

1. **The server is the only real game.** Every browser is a renderer plus an
   input device, and everything it says is a request the server may refuse.
2. **The client sends intent, never outcome.** "I want to build at vertex 14",
   never "I built at vertex 14 and now have 3 brick".
3. **Identity comes from the connection, never from the payload.** Derive the
   acting player server-side; a `name` field in an event is forgeable.
4. **Game logic imports nothing from Flask or Socket.IO.** Rules live in plain
   Python that can be tested without starting a server.
5. **Never send a player data they should not see.** Anything that reaches the
   browser is visible in DevTools, whatever the UI chooses to render.

## Known violations in the current code

These are live in the repository today and each one is a worked example of a rule
below. Fixing them is the first backlog.

- `server/app.py` derives the acting player from `data.get('name')` in the event
  payload (see `handle_roll_dice`, `handle_place_settlement`, and most other
  handlers), so any client can act as any player. Violates *Player Identity*.
- `server/app.py` hardcodes `app.config['SECRET_KEY'] = 'catan-secret-key'`.
  Violates *Configuration and Secrets*.
- `server/app.py` runs `socketio.run(app, debug=True, allow_unsafe_werkzeug=True)`.
  Violates *Development Server versus Production*.
- Game state is a module-level global (`current_game`) plus `data/users.json`
  rewritten on every mutation, which breaks with more than one worker and can
  corrupt the file on concurrent writes. Violates *Scaling Beyond One Process*
  and *Persistence and Crash Recovery*.
- `get_board_data()` is broadcast to every player, so hidden information
  (other players' hands, the development card deck) is on the wire for everyone.
  Violates *Hidden Information*.
- `server/game/game.py` calls module-level `random` directly, so dice-dependent
  bugs cannot be reproduced in a test. Violates *Fixtures and Determinism*.
- `server/__pycache__/` is committed. Violates *Version Control Hygiene*.

---

# Part I — Server Architecture (Flask + Flask-SocketIO)

### Application factory and extension initialization

- Create the `SocketIO` object at module scope with no arguments (`socketio = SocketIO()`) and bind it to the app inside the factory with `socketio.init_app(app)`, because an unbound extension object stores no application-specific state and can therefore serve several app instances (production, tests, fixtures) created from the same process.
- Use the application-factory pattern as soon as you need more than one configuration of the app — the moment you write your first test that needs a different `SECRET_KEY`, a different Redis URL, or an isolated game-state store — because a module-level `app = Flask(__name__)` freezes configuration at import time and makes per-test configuration impossible.
- Keep a single-module server only while the whole thing fits in one file you can read in one sitting and has no test suite; the factory costs you one indirection and buys testability, so migrate before the module crosses a few hundred lines rather than after.
- Load configuration as the very first thing inside the factory, before any `init_app()` call, because extensions read `app.config` during `init_app()` and silently pick up defaults if the values are not there yet.
- Never touch `current_app`, `app.config`, or the game-state singleton at import time in any module; read them inside handlers via `current_app`, because import-time access reintroduces the exact global-app coupling the factory exists to remove.
- Return the app from the factory and keep the runner in a separate entry point (`wsgi.py` / `run.py`) that calls `create_app()`, because this keeps the WSGI callable importable by Gunicorn without executing any server-start side effects.

```python
# extensions.py
socketio = SocketIO()

# app/__init__.py
def create_app(config_object="config.ProductionConfig"):
    app = Flask(__name__)
    app.config.from_object(config_object)
    socketio.init_app(app, message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"))
    from . import events           # noqa: F401 — registers handlers by import
    app.register_blueprint(http_bp)
    return app
```

### Splitting handlers across files without circular imports

- Put the `SocketIO()` instance in its own leaf module (e.g. `extensions.py`) that imports nothing from your application, because every handler module will import it and any application import inside it creates a cycle.
- Register socket handlers by importing the handler modules from inside the factory (or from the package `__init__` after `socketio` is defined), not by having the handler modules import the app — the decorator only runs as a side effect of import, so a handler module that is never imported is a handler that silently does not exist.
- Mark those side-effect imports with a `# noqa: F401` comment and a note that the import is the registration mechanism, because a linter or a well-meaning cleanup will otherwise delete them and break events with no error message.
- Do not expect Blueprints to carry Socket.IO handlers: Blueprints organize HTTP routes only, and `@socketio.on()` registers against the single `SocketIO` object regardless of which module the decorated function lives in. Use Blueprints for the REST/HTML surface (lobby pages, health checks, auth) and one of the two handler-organization patterns below for sockets.
- Prefer class-based namespaces (`class GameNamespace(Namespace)` with `on_<event>` methods, registered via `socketio.on_namespace(GameNamespace("/game"))`) when you want handlers grouped as a unit that can be registered explicitly from the factory, because explicit registration removes the import-for-side-effect fragility entirely and makes the handler set visible in one place.
- Remember that a `Namespace` instance is a singleton shared by every connected client, so never store per-player state on `self`; keep per-connection data in the Socket.IO session or a keyed store, or two players will overwrite each other's state.
- Keep game rules out of handler modules: a handler should validate input, resolve the player and game, call a pure function in a `game/` package, and emit the result — this is what lets you unit-test Catan's turn logic without a socket server at all.

### Namespaces versus rooms

- Use rooms, not namespaces, to model a lobby and a game instance: a room is a server-side label for a set of connections within one namespace, created implicitly on first `join_room()` and destroyed when empty, which is exactly the lifecycle of a game.
- Give every game a room named after its game id and every lobby a room named after the lobby (e.g. `join_room(f"game:{game_id}")`), then broadcast state updates with `emit("state", payload, to=f"game:{game_id}")`, because this sends the update only to the players in that game and costs nothing per idle game.
- Rely on the fact that each connection is automatically in a room named after its own `request.sid`, so a private message to one player is `emit("your_hand", data, to=sid)` with no extra bookkeeping.
- Use a namespace only to separate protocols that are logically different connections — for example `/game` for gameplay and `/admin` for a moderation console — because a namespace is a separate multiplexed connection with its own handlers, its own session, and its own room space, and it does not scale to one-per-game.
- Never create a namespace per game or per lobby; namespaces are registered up front and are not dynamic, and per-game namespaces would require registering handlers at runtime and leak them forever.
- Remember rooms are scoped per namespace, so a room name in `/game` and the same name in `/admin` are different rooms; be explicit with the `namespace=` argument whenever you emit from outside a handler.
- Have a player join both a per-game room and a per-player room (`user:{user_id}`), because the per-player room survives across the player's multiple tabs or reconnects and gives you a stable address for "notify this human".

### The async model: eventlet, gevent, threading, and ASGI

- Do not choose eventlet for a new project: the eventlet project is winding down, is in bugfix-only maintenance, its own documentation now ships a "Migrating off of Eventlet" guide, and Miguel Grinberg states plainly that he "would not recommend its use on new projects."
- Default to threading mode (`async_mode="threading"`) for a new Flask + Flask-SocketIO game, because it uses only the standard library, has no monkey-patching, is the most compatible with debuggers, profilers, native extensions, and blocking database drivers, and is the option Grinberg calls "the safest" going forward.
- Install the `simple-websocket` package when using threading mode, because without it the server falls back to HTTP long-polling and you lose the low-latency WebSocket transport that a real-time game needs — long-polling will appear to work in development and quietly add latency and load in production.
- Choose gevent only if you have a measured need for very high connection counts on one process or you are migrating an existing eventlet app with minimal churn, and accept that gevent requires `monkey.patch_all()` as the literal first statement of your entry point, above all other imports, because patching after a module has already grabbed a reference to blocking `socket`/`threading` primitives produces deadlocks that are extremely hard to diagnose.
- Under any greenlet mode (gevent or eventlet), never call blocking C code or CPU-heavy game logic inline in a handler, because a greenlet that does not yield blocks every other connection in that process; move heavy work to a thread pool or a task queue.
- Treat ASGI/asyncio as a real target but understand it means leaving Flask: python-socketio ships `AsyncServer` and `socketio.ASGIApp` for uvicorn/hypercorn, but Flask's own async support is incomplete for this purpose and Flask-SocketIO does not have an asyncio mode, so migrating means porting the HTTP side to Quart or FastAPI and rewriting every handler as `async def`.
- Do not begin an ASGI migration for a project of this size unless you are already hitting a concrete limit that threading and gevent cannot meet; the migration touches every handler and every blocking call, and the win for a turn-based board game with tens of concurrent connections is negligible.
- Pin `async_mode` explicitly in the `SocketIO()` constructor rather than letting the library auto-detect, because auto-detection picks whichever greenlet library happens to be installed in the environment and a transitively-installed gevent will silently change your concurrency model between dev and prod.
- Keep eventlet and gevent out of the virtualenv entirely if you intend to run threading mode, since their mere presence changes the auto-detected default and can produce a mode you never chose.

### Development server versus production

- Never run the Werkzeug development server in production and never set `debug=True` there, because debug mode exposes the Werkzeug interactive debugger, which is a remote code execution console for anyone who can reach it, and the dev server is single-purpose code with no hardening, no request limits, and no process supervision.
- Understand that `allow_unsafe_werkzeug=True` fixes nothing: `socketio.run()` raises a `RuntimeError` when it would have to fall back to Werkzeug, and this flag only suppresses that guard. Passing it is you acknowledging the risk, not the server becoming production-ready — if you find it in a deployment config, that is a bug to fix, not a setting to keep.
- Use `socketio.run(app, debug=True)` for local development only, and make the production entry point a separate command that never calls `socketio.run()` at all.
- Run threading mode in production with Gunicorn's threaded worker plus `simple-websocket`: `gunicorn -w 1 --threads 100 wsgi:app`.
- Run gevent mode in production with `gunicorn -k gevent -w 1 wsgi:app`, or `gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 wsgi:app` when you need gevent's native WebSocket support, or uWSGI in gevent mode with `--http-websockets`.
- Always pass `-w 1` to Gunicorn for a Socket.IO app, because Gunicorn's load-balancing algorithm does not implement sticky sessions and a client whose polling requests land on different workers will fail to establish a session; scale by running multiple single-worker Gunicorn instances behind a sticky load balancer instead.
- Put nginx (1.4+) in front and configure it to pass `Upgrade` and `Connection` headers and to disable proxy buffering for the Socket.IO endpoint, because without the upgrade headers the WebSocket handshake fails and the client silently degrades to polling.
- Use `ip_hash` (or a cookie-based sticky policy) in the nginx `upstream` block when balancing across several server processes, because Socket.IO's HTTP long-polling handshake requires every request of a session to reach the process that owns it.

### Configuration and secrets

- Read `SECRET_KEY` from the environment and raise at startup if it is absent in any non-development configuration, because a hardcoded or defaulted key lets anyone who has read your repository forge session cookies and impersonate any player.
- Generate the key with `python -c 'import secrets; print(secrets.token_hex())'` and never commit it, never log it, and never paste it into an issue — a leaked signing key is a full authentication bypass and rotating it logs out every player.
- Use `SECRET_KEY_FALLBACKS` (Flask 3.1+) when rotating the key so existing sessions stay valid through the rollout, and remove old keys after the rotation window since each extra key adds verification overhead.
- Define configuration as classes (`Config`, `DevelopmentConfig`, `ProductionConfig`, `TestingConfig`) loaded via `app.config.from_object()`, selected by a single environment variable, because this keeps environment differences in one readable place and lets a test construct an app with `create_app(TestingConfig)` without touching the filesystem.
- Keep committed defaults safe-by-default — `DEBUG = False`, `SESSION_COOKIE_SECURE = True`, `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"` in the production config — so that a forgotten override fails closed rather than open.
- Set `DEBUG` via the `FLASK_DEBUG` environment variable or the `--debug` CLI flag rather than in a config file, because Flask itself warns that setting `DEBUG` in code may not behave as expected once extensions have already read it.
- Put non-secret knobs (tick intervals, max players per game, turn timeout) in config rather than as literals in handlers, because the same code then runs in a test with a one-second turn timer and in production with a real one.

### Sessions and identifying a player across reconnects

- Do not treat `request.sid` as a player identity: the `sid` is the identity of one *connection*, it changes on every reconnect and on every transport upgrade cycle, and a mobile client backgrounding the tab will produce a new one within seconds.
- Assign every player a stable identifier that lives in the signed Flask session (or a token the client presents in the Socket.IO `auth` payload on connect) and map `sid -> player_id` at connect time and back again, because reconnect recovery — rejoining the game room and resending state — depends on recognizing the returning human, not the returning socket.
- Know that Flask-SocketIO takes a *copy* of the Flask session when the connection is established, so writes to `session` inside a socket handler fork the session and are not visible to later HTTP requests, since there is no HTTP response on which to set a cookie.
- Use a server-side session backend (Flask-Session with Redis) together with `manage_session=False` when you need HTTP routes and socket handlers to share one mutable session, because that is the only configuration where a change made in an HTTP route is visible to socket handlers.
- Alternatively, keep per-connection data out of the Flask session entirely and use python-socketio's own server-side session (`save_session`/`get_session`, or the `socketio.session()` context manager), which is destroyed on disconnect and never persists across reconnects — which is precisely why the durable `player_id` must live elsewhere.
- Authenticate in the `connect` handler and reject unauthenticated connections by returning `False` or raising `ConnectionRefusedError` with a reason, because a handler that only checks authorization on gameplay events leaves an authenticated-connection-shaped hole and duplicates the check in every event.
- On disconnect, do not immediately destroy the player's seat in the game; mark the player disconnected and start a grace timer, because a real-time game must survive a tunnel, a Wi-Fi handoff, or a page refresh without ending the match.
- Store the authoritative `player_id -> game_id -> seat` mapping outside the connection so that a reconnecting client can be re-joined to its rooms and sent a full state snapshot in the `connect` handler; the client should never need to reconstruct game state from the event stream it missed.
- Remember `before_request` and `after_request` hooks do not run for Socket.IO event handlers, so any cross-cutting concern you implemented as a Flask hook (auth, request logging, tracing) must be re-implemented as a decorator or a base `Namespace` for the socket side.

### CORS

- Leave `cors_allowed_origins` at its default same-origin behavior whenever the game client is served from the same host as the server, because the default rejects mismatched `Origin` headers with a 400 and that is the protection you want.
- Set `cors_allowed_origins` to an explicit list of your real front-end origins when the client is served from a different host, and drive that list from configuration so staging and production differ without a code change.
- Never ship `cors_allowed_origins="*"`, because it lets any web page a player visits open a Socket.IO connection to your server carrying their cookies, which is a cross-site request forgery against the game — the attacker's page can join rooms and send moves as the victim.
- If you must accept many origins, prefer token-based auth in the Socket.IO `auth` payload over cookie-based sessions, because a bearer token is not attached automatically by the browser and therefore does not carry CSRF exposure.
- Keep the HTTP CORS configuration (Flask-CORS or manual headers) and the Socket.IO CORS configuration in sync from the same config value, because they are enforced independently and a mismatch produces failures that look like transport bugs.

### Scaling beyond one process

- Accept the hard constraint first: any game state held in a Python dict at module scope exists only inside one process, so the second worker will have its own empty copy and players will land in different universes depending on which worker their connection hit. Single-worker deployment is a *design decision*, not a default to drift past.
- Decide explicitly whether your target is one process forever (perfectly reasonable for a Catan server, and vastly simpler) or multi-process, and if it is multi-process, move game state to Redis or a database *before* you add the second worker, not after you observe the bug.
- Configure `message_queue="redis://..."` on the `SocketIO` object when running more than one server process, because without it a broadcast issued on worker A never reaches the clients connected to worker B — the message queue is what makes `emit(..., to=room)` span processes.
- Give each independent deployment (staging, production, a second game cluster) a distinct `channel` name on the message queue, because clusters sharing a channel will deliver each other's events to each other's clients.
- Emit from background workers (Celery tasks, cron jobs, an admin script) by constructing a client-only instance — `SocketIO(message_queue="redis://...")` with no app — and calling `emit()` on it; that process needs no Flask app, no eventlet, and no gevent.
- Do not treat the message queue as your state store: it fans out events, it does not synchronize game state, and two workers mutating the same game still need a real store with atomic updates or a per-game lock.
- Serialize mutations to a single game (a Redis lock, a per-game actor, or routing all connections of a game to one process) even in a single-process threading deployment, because two handler threads applying moves to the same board concurrently will corrupt it.
- Instrument the assumption: log the worker/process id on connect and on every state mutation, so that a multi-worker misconfiguration shows up as an obvious log pattern rather than as intermittent "my move disappeared" reports.

### Logging and error handling in socket handlers

- Register `@socketio.on_error_default` and treat it as mandatory, because an exception raised inside an event handler is caught by the server and does not propagate to the client — from the player's point of view the move simply vanishes with no error, no acknowledgement, and no disconnect.
- Make every game-affecting event use an acknowledgement callback and have the handler *return* a result object, because the return value of a handler is delivered to the client's callback and is the only reliable channel for "your move was rejected because it is not your turn."
- Wrap handler bodies so that expected, user-caused failures (illegal move, wrong phase, insufficient resources) are returned as structured error results, while unexpected failures propagate to the default error handler which logs with a traceback and emits a generic `error` event to that client — distinguish the two, because leaking internal exception text to clients discloses implementation detail and confuses players.
- Log the `request.sid`, the resolved `player_id`, the `game_id`, and `request.event` (which carries the event name and arguments) in the error handler, because a traceback without the game context is nearly useless for reproducing a board-state bug.
- Set `logger=True` and `engineio_logger=True` only in development, and keep them off in production, because Engine.IO logging is extremely verbose per packet and will dominate your logs and your I/O budget.
- Configure logging through Python's `logging` module with a handler attached before the app is created, and pass real logger objects to `SocketIO(logger=..., engineio_logger=...)` in production if you want that output, so socket logs land in the same structured stream as everything else.
- Validate and type-check every payload at the handler boundary before it reaches game logic, because Socket.IO payloads are arbitrary attacker-controlled JSON and a `KeyError` deep in the rules engine becomes a silently dropped event.
- Never trust client-supplied `game_id`, `player_id`, or seat numbers from the payload; derive them from the server-side session or the connection mapping, because otherwise any player can act as any other by editing one field.
- Emit an explicit, versioned error event or acknowledgement shape (e.g. `{"ok": false, "code": "NOT_YOUR_TURN"}`) rather than free-form strings, so the client can react programmatically and you can change wording without breaking it.
- Add a heartbeat/`ping_timeout` policy you have actually chosen rather than the default, and log disconnects with their reason, because in a game the difference between "player quit" and "player's network dropped" drives completely different server behavior.

---

# Part II — Authoritative Server Design

### Server authority

- Treat the server's in-memory game state as the only real game, and treat every browser as a renderer plus input device, because a browser tab runs on hardware the player fully controls and any state held there can be edited, replayed, or fabricated at will.
- Implement every game rule (placement legality, resource costs, road connectivity, longest road, victory point totals, turn order) in server-side code, and let the client implement rules only as a UX affordance such as graying out illegal buttons, because a client-side rule check is a hint to honest players and an obstacle of exactly zero value against a dishonest one.
- Make the server the sole producer of state changes: a client action must be applied by mutating server state first, and the client's view must update only from the state or event the server broadcasts back, because any path where the client updates itself optimistically and the server merely agrees creates a divergence a cheater can steer.
- Accept that a turn-based game has no latency excuse for client authority: unlike a shooter, a settlement placement can wait one round trip, so never trade correctness for prediction in a game where the player is not moving continuously.
- Structure the socket API so that every inbound message is a request that the server may reject, and every outbound message is a fact, because collapsing these two categories into a single shared "state update" event invites the client to send facts.

### Intent, not outcome

- Define every client-to-server event as an intent naming an action and its parameters ("build settlement at vertex 42"), and never as an outcome ("I built a settlement; my new brick count is 3"), because an outcome payload asks the server to copy the client's arithmetic instead of doing its own.
- Strip all derived and computed fields from inbound payloads and recompute them server-side, including resource counts, victory points, army size, road length, and building inventories, because any number the client is allowed to assert is a number the client can inflate.
- Reject inbound events that carry state the server already owns rather than silently ignoring those fields, because an event schema that tolerates extra fields today becomes an event schema that reads them after a careless refactor tomorrow.
- Deduct costs, grant resources, and advance turn state from server-side tables and server-side state exclusively, so that a "build road" intent never carries a price and a "trade" intent never carries the resulting balances.
- Keep intent payloads minimal and identifier-based (vertex ID, edge ID, tile ID, card type), because the smaller the surface the client can describe, the smaller the surface you must validate.

### Inbound event validation

- Validate every inbound event against the full checklist before mutating anything: the sender is authenticated, the sender is a player in this specific game, it is the sender's turn, the game is in a phase where this action is legal, the referenced target exists, the action's game-rule preconditions hold, and the player can afford it — because skipping any single one of these is a complete exploit on its own.
- Run all of these checks server-side even when the UI already prevents the action, because the attacker does not use your UI; they open a socket and emit the event directly, and the only code that will ever run for them is your handler.
- Validate the shape and type of every payload field before using it (integers are integers, IDs are within known ranges, strings match a known enum) using allowlists rather than blocklists, because an unvalidated index or key can crash the handler or reach state the action was never meant to touch.
- Resolve every client-supplied identifier by looking it up in server-side state and confirming the requesting player is authorized to act on that specific object, because accepting a raw ID without an ownership check is the game equivalent of an insecure direct object reference — the classic form being a client that sends another player's ID to move that player's piece or spend their cards.
- Deny by default: write handlers so that the action is applied only on an explicit successful path, and every other path — unknown event, unknown phase, unrecognized ID, failed precondition — falls through to rejection, because a validation function that returns "true unless a specific check fails" will silently permit every case you forgot to enumerate.
- Return a structured rejection to the offending client and leave game state untouched, without ever partially applying an action, because half-applied actions (cost deducted, building not placed) corrupt state in ways no later validation can detect.
- Log every rejected action with the player identity, event name, and reason, because a legitimate player's client rarely sends illegal actions, so a burst of rejections is a high-signal indicator of someone probing your protocol.

### Player identity

- Derive the acting player from the server-side socket session rather than from a name or player ID field in the event payload, because any client can put another player's name in that field and act as them.
- Bind identity to the connection once at connect or join time — mapping socket ID (or an authenticated session or token) to a player slot in a specific game, stored server-side — and look that mapping up on every subsequent event, so that identity is established once by the server and never re-asserted by the client.
- Remove player-identifying fields from event payloads entirely rather than validating that they match the session, because a field that exists will eventually be trusted by some handler, and a field that does not exist cannot be spoofed.
- Verify on every event that the socket's bound player is a member of the game room the event targets, because a client can emit an event naming any room ID and otherwise reach into games it never joined.
- Re-establish the identity binding on reconnect through a server-issued, unguessable token rather than by letting the returning client claim a seat by name, because a name-based reclaim lets anyone who knows a player's name steal their seat and their hand.
- Scope authorization per action rather than per connection: being a player in the game authorizes chat, but only being the current player in the correct phase authorizes rolling dice or building, because a single "is authenticated" gate is not an authorization model.

### Hidden information

- Send each client only the information that player is entitled to see, and compute those per-player views server-side before emitting, because anything sent to the browser is fully visible in DevTools regardless of whether the UI displays it — hiding data with CSS, a flag, or an unrendered field hides nothing.
- Never broadcast the full authoritative game state object to all players when it contains hidden information such as other players' resource hands, development cards, the undrawn deck, or face-down tiles, because a single convenient "here is everything" broadcast leaks the entire game to anyone who opens the network tab.
- Send only aggregate or public projections of hidden data — a card count rather than the card list, "played a knight" rather than the player's remaining hand — because opponents legitimately need to know how many cards you hold but never which.
- Never send the deck order or the shuffled sequence of remaining cards to any client, because knowing the next development card converts a probabilistic decision into a certain one and is undetectable in play.
- Prefer drawing hidden items lazily on the server at the moment of the draw over pre-shuffling and transmitting, and if you must pre-shuffle, keep the order exclusively in server memory or storage.
- Audit outbound payloads specifically for over-fetching, treating "the client only renders what it should" as no defense at all, because the leak happens at the network boundary, not the render boundary.

### Randomness

- Generate every random outcome — dice rolls, deck shuffles, robber-driven random card steals, initial turn order — on the server, and send only the resolved result to clients, because a client-generated roll can simply be rerolled until it is a seven.
- Never let the client supply a seed, a roll value, or an index into a shuffled collection, even as a "suggestion" the server checks, because any client-influenced input to randomness is client-controlled randomness.
- Use a cryptographically strong random source (such as Python's `secrets` module or `random.SystemRandom`) for shuffles and steals rather than a default Mersenne Twister, because a predictable PRNG sequence can be reconstructed from observed outcomes and used to plan around future draws.
- Implement shuffles with a correct Fisher-Yates over the server-side array (`random.shuffle` on a real RNG) rather than a comparator-based sort, because a sort with a random comparator is measurably biased and yields exploitable distributions.
- Resolve a random steal by having the server pick the victim's card itself and tell each affected player only what they are entitled to know, because letting the thief's client choose an index leaks the victim's hand composition.

### Rate limiting and flood protection

- Apply a per-socket rate limit to every inbound event, not just to expensive ones, because a client can emit thousands of trivially cheap events per second and starve the event loop that serves every other game on the process.
- Enforce limits per authenticated player and per IP as well as per socket, because a single attacker can open many sockets and defeat a limit that is only scoped to one connection.
- Cap payload size and reject oversized or deeply nested messages before parsing or validating them, because deserialization of attacker-sized input is itself the denial of service.
- Set tighter limits on connection and room-join attempts than on in-game actions, because connection churn is more expensive than a game action and is the cheapest way to exhaust server resources.
- Disconnect or temporarily block a client that persistently exceeds limits or repeatedly sends invalid events, rather than merely dropping the excess messages, because a client behaving that way is not a player having a bad network day.
- Log rate-limit trips with player identity so that abuse is visible in operations, because silent throttling makes an attack indistinguishable from a slow server.

### Disconnects and reconnects

- Keep the game and its server-side state alive when a player disconnects, marking the seat as disconnected rather than destroying the game, because in a turn-based game a dropped connection is usually a thirty-second network blip and destroying the game punishes the other players for it.
- Restore the full, correctly filtered state to a returning player on reconnect in a single snapshot — board, buildings, their own hand, public counts, current turn and phase, pending prompts — because an incremental event replay assumes the client retained prior state, which a page reload does not.
- Rebind the returning socket to the existing player slot via a server-issued reconnect token and invalidate the old socket's binding, because leaving the stale socket bound lets two connections act as one player and lets a stale client mutate the game.
- Enforce a server-side turn timer as a liveness mechanism so that a disconnected or simply idle player cannot stall the game indefinitely, because without one, a single player closing their laptop freezes everyone else forever.
- Define the timeout action explicitly and conservatively (auto-pass, auto-roll, skip the build phase, or forfeit after repeated timeouts) and apply it through the same validated action path as a normal move, because a timeout handler that bypasses validation is a rule-breaking backdoor.
- Run turn timers on the server and treat any client-reported timing as advisory display only, because a client that owns the clock owns unlimited thinking time or can time other players out early.
- Clear a player's timer on reconnect and resume normal play, and only remove a player from the game after a defined grace period, because aggressive eviction turns a transient disconnect into a lost game.

### Concurrency and atomicity

- Serialize action handling per game so that only one action for a given game is being validated and applied at a time, using a per-game queue or lock, because two nearly simultaneous events (two players clicking "buy development card" for the last card, or a player double-clicking "build") can otherwise both pass validation against the same pre-action state and both apply.
- Never yield control between reading state for validation and writing the resulting mutation, because in greenlet-based async modes every blocking call is a yield point where another handler can run and invalidate the state you just checked, and in threading mode the GIL provides no protection across bytecode boundaries.
- Make each action's state transition atomic in effect — validate fully, then apply all mutations as one uninterrupted unit, so no other handler observes a half-applied action, because a partially applied build (cost paid, piece unplaced) is unrecoverable without manual repair.
- Treat validation results as valid only for the exact state they were computed against, and re-validate rather than reuse a decision made before yielding, because a stale "can afford it" check is how duplication bugs are born.
- Ignore or reject duplicate and stale actions explicitly, for example by carrying a monotonically increasing turn or action sequence number in server state and rejecting intents that reference a superseded one, because retries and double-clicks are normal client behavior and must be idempotent, not doubly applied.
- Keep the per-game lock scoped to the game rather than to the whole process, because a global lock makes every concurrent match wait on every other one and turns a correctness fix into a scalability problem.

### Persistence and crash recovery

- Persist authoritative game state so an in-progress game survives a process restart, because a crash that loses a two-hour board game is a worse outcome for players than most cheats you are defending against.
- Do not rewrite an entire JSON file on every state mutation, because the write cost grows with game size, the frequency grows with player activity, and the pattern becomes both a throughput bottleneck and the dominant source of latency in an otherwise cheap turn-based server.
- If you persist to a file at all, write atomically — serialize to a temporary file in the same directory, flush and `fsync` it, then `os.replace` over the target — because a plain in-place write that is interrupted by a crash or overlapping write leaves a truncated file that fails to parse on startup and loses the game entirely.
- Never allow two writers to touch the same state file concurrently: funnel all writes for a given game through the same serialized path used for state mutation, because interleaved writes to one file produce corrupted, unparseable output with no error at write time.
- Prefer a real datastore (SQLite for a single node, Redis or Postgres beyond that) over hand-rolled JSON files once games are anything other than throwaway, because durability, atomic transactions, concurrent access, and crash recovery are exactly the problems those systems already solve correctly and you will otherwise reimplement them badly.
- Debounce or batch persistence (write on meaningful checkpoints such as turn end, or coalesce rapid mutations) rather than persisting on every field change, because the recovery requirement is "resume the game," not "reproduce every intermediate microstate."
- Validate persisted state when loading it, and refuse to resume a game whose invariants do not hold, because a corrupted or hand-edited save file is untrusted input exactly like a client payload.
- Keep the previous good snapshot until the new one is durably written, because an atomic write protects you from a torn file but not from having faithfully persisted already-corrupt state.

### Invariants and failing closed

- Assert the game's global invariants after every applied action — no negative resource counts, per-player piece limits (roads, settlements, cities) not exceeded, total resources of each type not exceeding the bank supply, each vertex and edge occupied by at most one piece, distance rule respected, victory points equal to their recomputed components — because these catch rule bugs that individual precondition checks miss.
- Fail closed on any invariant violation by rejecting the action and rolling back to the pre-action state rather than accepting it and attempting to patch the discrepancy, because a corrupt game state cannot be reasoned about and every subsequent validation built on it is meaningless.
- Treat an invariant violation as a server bug and log it loudly with the full action context, because unlike a rejected illegal move, it means validation and application disagree and the game rules are not actually being enforced where you think they are.
- Apply an action against a copy or transactionally so that rollback on failed post-conditions is genuinely possible, because rollback you cannot perform is not a policy, it is a comment.
- Recompute derived values such as victory points, longest road, and largest army from primary state rather than incrementally maintaining counters, or verify the incremental value against a recomputation, because incremental counters drift silently and a drifted victory point count ends the game wrongly.
- Choose rejection over guessing whenever an event is ambiguous, malformed, or references something that no longer exists, because the cost of making an honest player click again is trivial next to the cost of an unfair or unrecoverable game.

---

# Part III — Event Protocol Design

### Event catalogue and naming

- Maintain a single canonical protocol document (one file, checked into the repo alongside the server code) that lists every event name, its direction (client→server or server→client), its exact payload shape field by field with types, and which events it can trigger in response, because the protocol is the contract between two independently written programs and a contract that lives only in scattered `emit` calls cannot be reviewed, diffed, or reasoned about.
- Treat any event emitted or handled in code but absent from the catalogue as a bug and fix it before merging, because an undocumented event is invisible to everyone who did not write it and will silently diverge between the two sides until it breaks in production.
- Name client→server events as imperative commands (`place_settlement`, `roll_dice`, `end_turn`) and server→client events as past-tense facts (`settlement_placed`, `dice_rolled`, `turn_ended`), because it makes it immediately obvious from a single log line whether something was requested or has already happened.
- Never mix the two naming styles across directions — do not send a server→client event called `update_board` or accept a client→server event called `settlement_placed` — because an imperative name arriving from the server reads as an order the client must obey, which invites the client to duplicate authority the server already holds, and a past-tense name arriving from the client falsely implies the fact is already settled.
- Pick one lexical convention for the whole protocol (`snake_case` with a `noun_verb` or `domain.noun_verb` shape) and apply it to every event without exception, because inconsistent casing turns event names into a memorization problem and makes grepping logs unreliable.
- Never use the names `connect`, `connect_error`, `disconnect`, `disconnecting`, `newListener`, or `removeListener` for application events, because Socket.IO reserves them and registering your own handler on them will either be ignored or collide with transport-level behavior.

### Commands, notifications, and authority

- Require every client→server command to carry only the player's *intent* (which action, which coordinates, which trade) and never the resulting state, because the server is the sole authority on what the game state becomes and accepting computed state from a client makes cheating a matter of editing one JSON field.
- Emit a server→client notification for every accepted command, even when the acting client already knows what it asked for, because all clients must learn about the fact through exactly one code path and special-casing the actor produces divergent client states.
- Do not let a command name and its resulting notification name be identical, because identical names in both directions make it impossible to tell from a log or a network trace which side originated a frame.

### Full snapshots versus deltas

- Broadcast the full game state on every state change for this turn-based game, because the state is small (a fixed board, a handful of players, a bounded resource count), changes only a few times per turn rather than 60 times per second, and one code path that always sends everything cannot produce the class of bug where a client's state drifts because a delta was dropped, reordered, or applied twice.
- Do not introduce incremental deltas until you have measured an actual problem — payload size in bytes and observed latency on a real connection — because delta protocols require the server to track per-client baselines, require the client to handle out-of-order and missed updates, and multiply the number of reachable client states by an amount that is not worth paying for a board game.
- If deltas eventually become necessary, keep a full-snapshot event permanently in the protocol as the baseline and resync mechanism rather than replacing it, because every delta scheme needs a way to establish or repair the baseline and reusing the snapshot path means that code is exercised constantly instead of only during rare failures.

### Self-sufficiency and resync

- Make every server→client state message self-sufficient — it must contain everything the recipient needs to render the current situation without reference to any earlier message — because a client that reconnected, was backgrounded by the browser, or dropped a frame must still render correctly rather than render a state that is silently half-old.
- Provide an explicit client→server `request_state` (or equivalent) event that causes the server to send the full current snapshot to that one socket, because reconnection is normal in browsers (tab sleep, network switch, laptop lid) and without an explicit resync the client's only recovery is a full page reload.
- Have the client call the resync event unconditionally after every successful reconnect rather than only when it detects a problem, because Socket.IO's connection state recovery explicitly is not guaranteed to succeed and a client cannot reliably know what it missed while disconnected.
- Never rely on a client having received an earlier event as a precondition for interpreting a later one, because message ordering guarantees end where the connection ends, and a protocol with such preconditions can only be debugged by replaying the entire session.

### Per-player filtered state

- Build a separate payload for each recipient whenever the game state contains hidden information (other players' hands, the development card deck order, unrevealed cards), because a single broadcast sends identical bytes to everyone and any hidden data present in those bytes is readable in the browser's network tab regardless of what the UI chooses to display.
- Implement per-player filtering as an explicit serialization function that takes the authoritative state and the viewing player and returns only what that player is entitled to see, then loop over the players emitting to each one's socket individually, because "hide it in the UI" is not hiding and there is no way to express per-recipient redaction through one broadcast call.
- Include in each player's payload the *shape* of what is hidden (opponent hand counts, deck remaining count) rather than omitting hidden information entirely, because clients must render "opponent holds 5 cards" without being able to derive which five.
- Write a test that asserts a given player's serialized payload contains no other player's private fields, because this is the one protocol bug that produces no visible symptom and no error, only a quietly cheatable game.

### Targeting messages

- Choose the target of every emit deliberately from three options — broadcast to the game's room, emit to one specific socket, or reply to the sender — and state the intended target in the event catalogue, because a message sent to the wrong audience either leaks information or leaves a player's screen stale.
- Remember that in Flask-SocketIO the module-level `emit()` inside an event handler sends *only to the client that triggered the handler* by default, so a state update written as a bare `emit('state_updated', payload)` will reach exactly one player and no one else — this is the single most common cause of "it works on my screen but not theirs".
- Use `to=<room>` (or the equivalent `room=` alias) to address a game room and put every player of a game into a room named after the game ID on join, because room membership is the only scalable way to isolate concurrent games on one server, and `join_room`/`leave_room` handle cleanup automatically when a client disconnects.
- Prefer `to=<game_room>` over `broadcast=True` for anything game-related, because `broadcast=True` sends to every client connected to the namespace — that is every player of every concurrent game on the server, not just this one.
- Know that `broadcast=True` and room-addressed emits *include the sender by default*, and pass `include_self=False` only when you have a specific reason for the actor not to receive the message, because relying on the actor's local optimistic update instead of the broadcast creates two divergent paths to the same state.
- Use `skip_sid` rather than manual per-socket loops when you need "everyone in the room except these", because hand-rolled exclusion loops drift out of sync with room membership.
- Emit to a specific session ID (`to=<sid>`) for anything personal — a private hand, a validation error, a resync snapshot — because these must never reach the room, and a per-recipient emit is the only construct that guarantees it.

### Acknowledgements

- Use acknowledgement callbacks for request/response interactions where exactly one client needs exactly one answer to a question it just asked (was my move legal, what is the current state, did my trade offer register), because the ack ties the response to the request automatically and the client does not have to correlate a later broadcast back to what it sent.
- Return the response value directly from the Flask-SocketIO handler function to invoke the client's callback, since any value returned from the handler is passed to the client as the callback's arguments — this is simpler and less error-prone than emitting a bespoke response event and having the client match it up.
- Use a separate server→client notification event, not an ack, whenever more than one client needs to learn the outcome, because acks reach only the requester and are explicitly **not invoked for broadcast messages** in Flask-SocketIO.
- When an action both needs a private answer and changes shared state, do both — ack the actor with the accept/reject result and broadcast the resulting fact to the room — because collapsing these into one mechanism forces you to either leak the private part or drop the public part.
- Set a client-side timeout on every ack-based call and surface the failure in the UI, because an ack that never arrives (server crash, dropped connection mid-handler) otherwise leaves a button spinning forever with no error anywhere.

### Error reporting

- Define exactly one server→client error event with a fixed shape — a machine-readable `code` (a stable string like `NOT_YOUR_TURN`, `INSUFFICIENT_RESOURCES`, `INVALID_PLACEMENT`), a human-readable `message`, and an optional `details` object — because the client must branch on the code programmatically while showing the message to a human, and free-form error strings force clients to pattern-match on prose that changes.
- Enumerate every error code in the protocol catalogue alongside the events that can produce it, because an unlisted error code reaching the client is indistinguishable from a bug in the client's error handling.
- Guarantee that the server sends *something* back to the originating client for every rejected command — an ack with a failure result or a targeted error event — because a client that optimistically disabled a button and then hears nothing is stuck permanently, and "silence means rejection" is a rule no client can distinguish from a lost connection.
- Send errors only to the client whose action failed, never to the room, because one player's illegal move is not the other players' business and broadcasting rejections leaks intent (what a player tried to do reveals what they hold).
- Log every rejected command server-side with the player, the command, the payload, and the rejection code, because a rejection is either a client bug or an attempted exploit and both need to be visible.

### Idempotency, ordering, and staleness

- Include a monotonically increasing `state_version` (or sequence number) in every server→client state message and increment it on every accepted state change, because it is the only way for a client to tell "this is new information" from "this is a message I already applied" or "this arrived out of order".
- Have clients ignore any state message whose version is not greater than the version they already hold, because duplicates and late arrivals are inevitable across reconnects and applying an older snapshot silently rewinds the UI.
- Have clients that detect a version gap (or any inconsistency) request a full resync rather than attempting local repair, because the server's snapshot is authoritative and cheap and client-side reconciliation logic is a permanent source of subtle divergence.
- Attach a client-generated `request_id` to every command and make the server's response echo it, because a player double-clicking a button or a client retrying after a flaky connection must not produce two settlements, and the server can reject or replay-answer a repeated `request_id` instead.
- Make server command handling idempotent with respect to the game state where possible — re-processing the same action for the same turn and the same player should not double-apply it — because at-least-once delivery is the practical reality of a browser client with automatic reconnection.

### Validation, schema, and protocol versioning

- Validate every incoming payload on the server before touching game state: check that required fields are present, that types are correct, that values are within legal bounds, and that the acting player is who they claim to be and it is their turn, because a browser client is fully under the user's control and any field the server trusts unchecked is an attack surface.
- Never trust a client-supplied player identity in the payload — derive the acting player from the server-side session/socket mapping — because otherwise any player can act as any other by editing one field.
- Validate incoming payloads on the client as well (at minimum, guard on shape before rendering), because a malformed or unexpected server message should surface as a logged protocol error rather than a stack trace deep inside a render function.
- Define payload shapes in one place per side (a schema, dataclass, or TypedDict on the server; a matching type definition on the client) and derive the serialization from it rather than constructing dicts inline at each emit site, because inline dict literals drift field by field until the two sides disagree.
- Include a protocol version in the connection handshake and have the server reject or explicitly tell any client whose version does not match to reload, because a browser tab left open across a deploy will otherwise keep speaking the old protocol and can corrupt a live game with payloads the new server misinterprets.
- Bump the protocol version whenever you rename an event, add a required field, change a field's type, or change the meaning of an existing value, because these are exactly the changes an old client cannot detect on its own.
- Treat adding a new optional field or a new event as backward compatible and do not bump for it, provided clients ignore unknown fields and unknown events without crashing, because gratuitous version bumps force unnecessary reload prompts and train users to ignore them.

### Payload size and serialization

- Send only what the event's recipients actually need — do not attach the full board and every player's full state to trivial notifications like a chat message, a dice roll, or a turn timer tick — because payload weight compounds with player count and message frequency and turns a cheap event into a bandwidth problem.
- Keep the full-snapshot event as the one place that carries the complete state, and let all other events be small facts, because that draws a clear line between "here is everything" and "here is one thing that happened" instead of every event drifting toward carrying everything.
- Write explicit serialization functions that convert internal game objects to wire dicts, and never emit internal objects or their `__dict__` directly, because doing so leaks private attributes and hidden information onto the wire, and it welds the wire format to your class layout so that any server-side refactor silently breaks every client.
- Use short, stable field names in the wire format and keep them decoupled from internal attribute names, because the wire format is a published contract with a versioning cost while internal names should stay free to change.
- Serialize enums and domain objects to plain primitives (strings for resource types, integers for coordinates and counts) rather than relying on any framework's object encoding, because the client is JavaScript and every non-primitive representation becomes a decoding rule that must be documented, implemented twice, and kept in sync.

---

# Part IV — Vanilla JavaScript Frontend

### Module structure and file organization

- Load your client code with a single `<script type="module" src="/js/main.js"></script>` entry point and pull everything else in with `import`, because module scripts are deferred by default, run in strict mode, and evaluate exactly once no matter how many files import them, so shared modules become natural singletons instead of race-prone global assignments.
- Export every symbol another file needs with a named `export` and import it explicitly, because an explicit import graph lets you (and your editor) answer "who uses this function?" by searching for the name, while `window.drawBoard = …` gives you no way to tell a caller from a typo.
- Never attach game objects to `window` (no `window.gameState`, `window.socket`, `window.board`), because globals can be reassigned from anywhere, load-order bugs surface only in production, two modules can silently claim the same name, and nothing tells you which of the twenty files that read `window.gameState` is the one corrupting it.
- Use relative specifiers with explicit extensions (`import { store } from "./state/store.js"`), because browsers do not resolve extensionless or bare specifiers without an import map, and a missing `.js` fails at runtime rather than at build time.
- Serve the client over HTTP (the same Flask server is fine) rather than opening `index.html` from `file://`, because ES modules are fetched under CORS rules and `file://` origins are opaque, so every `import` fails.
- Give each module one responsibility and name the file after it (`socket.js`, `store.js`, `render/board.js`, `input/pointer.js`), because a reader who needs to change how roads are drawn should be able to find the file without grepping.
- Use dynamic `import()` only for genuinely optional screens (a replay viewer, a stats panel) and never inside the render loop, because dynamic import returns a promise and awaiting it mid-frame introduces a visible stall.

### Layer separation

- Split the client into exactly four layers — transport (Socket.IO), state store, renderer, and input/UI — and allow dependencies only in the direction transport → store → renderer and input → transport, because a cycle between any two of them means you can no longer test or reason about either one in isolation.
- Forbid rendering code from mutating state: render functions must take the state as a read-only input and produce only pixels and DOM, because if drawing a tooltip also sets `state.hoveredTile`, then the picture you see depends on the order the draw calls ran, and a skipped frame changes game behavior.
- Forbid socket callbacks from drawing anything directly: a socket handler's only job is to validate the payload, hand it to the store, and return, because a handler that calls `drawBoard()` will draw once per event, so three server events in one tick cause three full redraws, and a burst during reconnect can stall the tab.
- Forbid input handlers from mutating game state directly: a click handler should translate the pointer position into a game intent and emit it to the server, because the server is the only thing that knows whether the move is legal, and locally applying it produces a board that disagrees with every other player.
- Keep pure geometry (hex-to-pixel conversion, vertex and edge coordinates, neighbor lookup) in its own dependency-free module that imports neither the store nor the canvas, because that math is the part most worth unit-testing and the part most likely to be shared with the server.
- Route every layer-to-layer message through an explicit function call or a small event emitter rather than reaching into another module's internals, because `store.js` exporting `getState()` and `applyServerState()` lets you add logging or validation in one place, whereas exporting a mutable object lets any file write to it unobserved.

### Client state store

- Keep exactly one client state object as the single source of truth for what is on screen, because two parallel copies (one in the store, one cached in the renderer) will diverge the first time an update path forgets to touch both, and the resulting bug looks like a rendering glitch rather than a state bug.
- Update the state object only from server events and from purely local UI concerns (which panel is open, what the pointer is hovering), and keep those two categories in separate fields such as `state.game` and `state.ui`, because a full server snapshot must be able to replace `state.game` wholesale without wiping the menu the user has open.
- Replace the server-authoritative slice wholesale from each snapshot rather than deep-merging fields, because a merge silently keeps stale entries the server has deleted (a settlement that was undone, a player who left) while a replacement cannot.
- Route every state change through a single `setState`/`applyServerState` function that assigns the new value and then marks the frame dirty, because scattered direct assignments mean some mutation somewhere will forget to trigger a redraw and the board will freeze in a way that looks random.
- Have the store notify subscribers (`store.subscribe(fn)`) instead of calling the renderer by name, because the day you add a second view — a chat panel, a resource counter, a dev overlay — the store should not need editing.
- Re-render the whole view from state after every change rather than patching the canvas or DOM in place from inside an event handler, because "draw a road at this edge" handlers must be individually correct for every ordering of events, while "draw the state" is correct by construction.
- Treat state as immutable-by-convention in the render path: never let a render or hit-test helper push onto an array or set a field on the state, because such writes are invisible in the code that reads like drawing and they resurrect after every redraw.
- Log or debug-dump the whole state object on demand (e.g. a `?debug` flag exposing `getState()` to the console), because reproducing a client bug from a single serialized snapshot is far cheaper than reproducing it from a sequence of clicks.

### Canvas rendering

- Drive all drawing from a single `requestAnimationFrame` loop and never call your draw function directly from an event handler, because rAF runs at most once per display refresh and pauses in background tabs, whereas synchronous redraws on every event can run dozens of times between two frames, all but the last of which are thrown away.
- Set a `dirty` flag when state changes and have the rAF callback return immediately when it is not set, because a static Catan board needs zero redraws per second, and burning a full board render 60 times a second heats laptops and drains phone batteries for no visible benefit.

  ```js
  let dirty = true;
  export function markDirty() { dirty = true; }
  function frame() {
    if (dirty) { dirty = false; render(store.getState()); }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  ```
- Keep exactly one rAF loop alive for the lifetime of the page and never start a new one per screen, because each `requestAnimationFrame(frame)` chain you start keeps running forever, so re-entering the game screen three times gives you three loops drawing the same board three times per frame.
- Distinguish the canvas CSS size (`canvas.style.width`, what the user sees, in CSS pixels) from the drawing-buffer size (`canvas.width`/`canvas.height`, the actual pixel grid), because setting only the CSS size makes the browser stretch a 300×150 default buffer across your whole board, which is the usual cause of a soft, blurry hex grid.
- Size the buffer to the CSS size multiplied by `window.devicePixelRatio` and then apply that scale once, because this makes one unit of your drawing coordinates equal one CSS pixel while the buffer still has one sample per physical pixel, so lines and text stay crisp on retina and high-DPI phone screens.

  ```js
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width  = Math.round(rect.width  * dpr);
  canvas.height = Math.round(rect.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);   // resets any previous scale
  ```
- Use `ctx.setTransform(dpr, 0, 0, dpr, 0, 0)` rather than a bare `ctx.scale(dpr, dpr)` when re-sizing, because `scale` multiplies onto the existing transform, so resizing the window twice would leave the board scaled by `dpr²`.
- Re-run the sizing routine on `resize` and on `devicePixelRatio` changes (via a `matchMedia("(resolution: Xdppx)")` listener), because assigning `canvas.width` clears the buffer and resets the transform, and a user dragging the tab from a retina laptop to an external monitor changes `devicePixelRatio` with no resize event on some setups.
- Debounce resize handling to one sizing pass per animation frame and mark the canvas dirty instead of drawing inside the resize handler, because resize fires continuously during a window drag and each re-allocation of the drawing buffer is expensive.
- Clear with `ctx.clearRect(0, 0, cssWidth, cssHeight)` in the same coordinate space your transform establishes, because clearing with `canvas.width`/`canvas.height` after scaling by `dpr` clears an area `dpr` times too large and only accidentally works.
- Draw in layers with the static board on a background canvas and the changing pieces on a canvas stacked over it, because the terrain hexes, numbers and ports never change during a game and re-rasterizing them on every dirty frame is pure waste.
- Wrap any temporary state change in `ctx.save()`/`ctx.restore()` or explicitly reset what you set, because a `ctx.globalAlpha = 0.5` left behind by the "valid placement" highlight will fade everything drawn after it, in a way that only shows up when placements are legal.
- Round positions of images and sprites to integers with `Math.round` before `drawImage`, because sub-pixel placement forces the browser into an interpolation path that both costs time and softens sprite edges.
- Create the context with `{ alpha: false }` when the board fully covers the canvas, because an opaque context lets the compositor skip blending the canvas with the page behind it.
- Pre-render expensive repeated artwork (a hex tile with its texture, number token and border) once into an offscreen canvas and `drawImage` it nineteen times, because re-running the same path, gradient and text calls per tile per frame is the most common reason a simple board renders slowly.

### Hit detection on a hex/vertex/edge board

- Convert client coordinates to canvas coordinates by subtracting the live `getBoundingClientRect()` origin, never by using `offsetLeft`, `clientX` alone, or `event.offsetX` across nested transforms, because the bounding rect is the only value that already accounts for scrolling, page zoom and CSS transforms applied to ancestors.
- Account for the ratio between the drawing-buffer size and the CSS box size explicitly, because when they differ, a click at the visual centre maps to the wrong buffer pixel and every placement lands one tile off near the board edges.

  ```js
  const rect = canvas.getBoundingClientRect();
  // With ctx.setTransform(dpr,...) the drawing space IS CSS pixels:
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  // Without that transform, scale into buffer space instead:
  // const x = (event.clientX - rect.left) * (canvas.width  / rect.width);
  ```
- Pick one convention — "drawing coordinates are CSS pixels" — and apply the identical transform in both the renderer and the hit-tester, because two places computing scale independently will drift the moment one of them is updated for high-DPI and the other is not.
- Do hit testing against the same geometry model the renderer draws from (shared `hexToPixel`, `vertexPosition`, `edgeMidpoint` functions), because duplicating the layout math means a change to hex radius or board offset fixes the picture and breaks the clicks.
- Detect hexes by converting pixel coordinates back to axial/cube hex coordinates with the inverse of your layout matrix and rounding in cube space, rather than looping over tiles and testing polygon containment, because the inverse-and-round approach is constant time, has no gaps or overlaps at tile borders, and cannot disagree with the forward transform.
- Detect vertices and edges by finding the nearest candidate within a radius threshold rather than testing exact geometric containment, because a settlement corner is a mathematical point and an edge is a line with zero width, so exact tests are unclickable — use a tolerance of roughly one third of the hex radius for vertices and pick the closest one.
- Restrict candidates to the legal placements the server told you about before running nearest-neighbor selection, because snapping to a nearby illegal corner produces a click the server rejects and the user experiences as the board ignoring them.
- Cache the bounding rect and scale factors and recompute them on resize, scroll and layout changes rather than on every `pointermove`, because `getBoundingClientRect()` forces a synchronous layout and calling it at pointer-move frequency during a drag is a classic source of jank.
- Never trust hit-test output as a move: translate it into an intent (`{ type: "buildSettlement", vertexId }`) and emit it, because hit detection answers "what did they point at", not "may they do it".

### Pointer, touch and keyboard input

- Handle input with pointer events (`pointerdown`, `pointermove`, `pointerup`, `pointercancel`) as a single code path instead of parallel mouse and touch handlers, because the browser also synthesizes compatibility mouse events after touch, so dual handlers fire your placement logic twice for one finger tap.
- Read `event.pointerType` when behavior genuinely must differ (larger hit tolerance for `"touch"`, hover highlights only for `"mouse"`), because a finger contact patch is far larger than a cursor hotspot and a touch device has no hover state to preview into.
- Call `element.setPointerCapture(event.pointerId)` when starting a drag (panning the board, dragging a card) and release it on `pointerup`, because capture guarantees you receive the `pointerup` even if the pointer leaves the canvas, without which a drag gets stuck in progress.
- Always handle `pointercancel` alongside `pointerup` and treat it as an abort, because the browser fires it when it takes over the gesture for scrolling or when a phone call interrupts, and code that only resets state on `pointerup` leaves a phantom drag active.
- Set `touch-action: none` in CSS on the game canvas, because without it a drag on the board scrolls or pinch-zooms the page and the browser delays or cancels your pointer events while it decides.
- Distinguish a tap from a drag by movement threshold and time rather than by binding `click`, because on touch devices `click` arrives roughly 300 ms late on some configurations and after a `pointerup` that already ended your gesture.
- Give every game action a real focusable control in the DOM (buttons for "end turn", "roll dice", "accept trade") rather than canvas-only affordances, because a `<canvas>` is opaque to screen readers and keyboard users, and native `<button>` elements get focus, Enter/Space activation and accessible names for free.
- Make the canvas itself focusable with `tabindex="0"` and give it `role="img"` plus an `aria-label` summarizing the board state, because a keyboard user needs a way to reach the board region and a non-visual user needs some textual account of what is drawn.
- Provide keyboard navigation for board selection (arrow keys to move a highlighted vertex, Enter to confirm, Escape to cancel) and render a visible focus indicator for the current selection, because "click precisely on a small corner" is not an input method available to everyone.
- Never remove focus outlines globally or rely on color alone to convey whose turn it is or which placement is legal, because color-blind users and keyboard users lose the only signal available to them.
- Announce turn changes and errors through an `aria-live="polite"` region, because a screen reader user gets no notification when a canvas repaints.

### Event listener hygiene

- Register DOM listeners for a screen exactly once, and if a screen can be entered repeatedly, remove the previous listeners before adding new ones, because `addEventListener` with a fresh function reference adds a second listener rather than replacing the first, so the third time a player enters the trade screen one click sends three trade offers.
- Keep a named function reference for anything you will remove, because `removeEventListener("click", () => handle())` removes nothing — the arrow function you pass is a different object from the one you registered.
- Prefer an `AbortController` and pass its signal to every listener for a screen, then call `abort()` on teardown, because one call detaches every listener registered with that signal and you cannot forget one.

  ```js
  let screenAbort;
  export function enterGameScreen() {
    screenAbort?.abort();                 // idempotent re-entry
    screenAbort = new AbortController();
    const { signal } = screenAbort;
    canvas.addEventListener("pointerdown", onPointerDown, { signal });
    window.addEventListener("resize", onResize, { signal });
  }
  ```
- Attach one delegated listener to a stable container and dispatch on `event.target.closest("[data-action]")` instead of binding a listener per button, because rebuilding a player list or a card hand replaces the DOM nodes and orphans every listener bound to the old ones.
- Encode the intent in `data-*` attributes rather than in the listener (`data-action="buildRoad" data-edge="12"`), because delegation then needs no re-registration when the list re-renders and the markup documents what each element does.
- Mark high-frequency listeners you never call `preventDefault` on as `{ passive: true }`, because the browser can then scroll without waiting for your handler to finish.
- Never register a listener inside a render function, because render runs on every dirty frame and would accumulate thousands of duplicates within seconds.
- Do only bookkeeping in `pointermove` — store the position and mark dirty — and never draw or run expensive layout there, because pointer move can fire far more often than the display refreshes and the extra work is discarded.

### Socket.IO client

- Create the socket in exactly one module, export that instance, and import it everywhere else, because a second `io()` call opens a second connection with its own session, so the server sees two players where there is one.
- Register every `socket.on(...)` handler once at module load, at the top level of your socket module, because registering inside a function that runs on each screen change or on each `connect` stacks duplicate handlers and makes a single server event run your callback N times.
- Never register handlers inside the `connect` handler, because `connect` fires again on every reconnection, so a player who briefly loses Wi-Fi ends up applying every subsequent state update twice, then three times.
- Handle `connect`, `disconnect` and `connect_error` explicitly with user-visible feedback, because silence during a dropped connection is indistinguishable from the game hanging, and players will reload and lose their place.
- Rely on Socket.IO's built-in reconnection rather than writing your own retry loop, and tune it through the `reconnectionDelay`, `reconnectionDelayMax` and `reconnectionAttempts` options, because the built-in logic already applies randomized exponential backoff and manual loops tend to hammer a server that is already struggling.
- Distinguish the two `disconnect` cases: when the server called `socket.disconnect()` or the client did (`reason === "io server disconnect"` / `"io client disconnect"`), reconnection will not happen automatically and you must call `socket.connect()` yourself, because otherwise the client sits silently disconnected forever.
- Treat `connect_error` as either recoverable (network) or fatal (auth rejected) by inspecting the error, and stop retrying and show a login prompt in the fatal case, because retrying a rejected token indefinitely just spins.
- On every `connect`, re-emit a rejoin/resync request identifying the room and the player, and apply the full snapshot the server sends back, because incremental events that occurred while the socket was down are gone and any state derived from them is wrong.

  ```js
  socket.on("connect", () => {
    ui.setConnectionStatus("connected");
    socket.emit("rejoin_game", { gameId });   // server replies with full state
  });
  ```
- Design the server protocol so a full-state snapshot exists as a first-class message and the client can always recover by requesting it, because "apply this delta" protocols with no snapshot path have no way back after any missed message.
- Assume every incoming payload may arrive out of order or duplicated and make state application idempotent, because reconnection and buffering can replay events and a handler that does `resources += 1` will drift while one that does `resources = payload.resources` cannot.
- Validate the shape of incoming payloads before writing them into the store, because a malformed or hostile message that lands in state will surface later as an exception inside the render loop, which is the worst place to debug it.
- Never emit from inside the render loop or from a `pointermove` handler without throttling, because Socket.IO will happily queue hundreds of messages per second and saturate the connection.
- Remove per-screen socket handlers with `socket.off(event, handler)` if you genuinely must register them dynamically, because the alternative is unbounded growth in the listener list and a "MaxListeners" style memory leak.
- Guard against emitting while disconnected by checking `socket.connected` and queueing or disabling the UI, because messages emitted while offline are dropped silently by default and the player sees their action vanish.

### Client authority and validation

- Treat the server as the sole authority on game state and never let the client's own computation of a move's outcome reach the board, because anyone can open devtools and call your functions, so a client that decides whether a settlement is legal is a client that can build anywhere.
- Duplicate every client-side rule check on the server, and consider the server copy the real one, because the client copy exists only to grey out an illegal button before the round trip.
- Only render a move after the server confirms it, and if you show optimistic feedback, mark it visually as pending and reconcile it against the next authoritative snapshot, because an optimistic placement that the server rejects leaves a ghost building nobody else can see.
- Never send the outcome of an action to the server ("I gained 3 wood"); send the intent ("I want to build a settlement at vertex 14") and let the server compute the outcome, because outcome messages are directly forgeable into unlimited resources.
- Never let the client hold information the player should not see (other players' hands, the shuffled development card deck, unrevealed tiles), because anything in the client's memory is visible in devtools no matter how the UI hides it, so the server must send each client only its own view.
- Never trust client-supplied identity fields such as `playerId` on incoming actions; derive the actor from the authenticated socket on the server, because a spoofed `playerId` otherwise lets one player act as another.
- Keep any shared rule module free of DOM and socket references if you share code between client and server, because the value of a shared rulebook disappears the moment it can only run in one environment.

### Asset loading

- Preload every image and sound the game needs before showing the board, and display a determinate loading indicator while doing so, because a texture that arrives mid-game causes a first frame where hexes render as blank shapes.
- Wrap image loading in promises and await them all with `Promise.all`, resolving on `load` and rejecting on `error`, because `drawImage` with a partially loaded image draws nothing at all and fails silently.

  ```js
  const loadImage = (src) => new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load ${src}`));
    img.src = src;
  });
  ```
- Handle asset load failures with a visible retry rather than an unhandled rejection, because a single 404 on a texture otherwise leaves the player at a loading screen that never finishes and no message explaining why.
- Store loaded assets in one module that exports them by name and import that module in the renderer, because re-creating `new Image()` per draw call re-triggers decoding and defeats the browser cache benefit you were relying on.
- Combine small sprites into a single atlas and draw with the source-rect form of `drawImage`, because dozens of separate requests cost more in connection overhead than the pixels are worth.
- Assume audio will not play until the user has interacted with the page, and create or `resume()` your `AudioContext` inside the first click or key handler, because browsers start an `AudioContext` created before any gesture in the `suspended` state and it will never produce sound until resumed from a gesture.
- Always handle the promise returned by `audio.play()` with a `.catch`, because a blocked autoplay rejects that promise and an uncaught rejection is both a console error and a silent failure of your sound effects.
- Give the user a mute control and persist the preference, defaulting to muted or to no ambient audio, because unexpected sound is the most common reason a player closes a browser game tab.
- Decode audio into buffers during preload rather than at trigger time, because decoding a dice-roll sound at the moment the dice are rolled adds an audible delay.

### Performance

- Never allocate objects, arrays, closures or strings inside the render loop; hoist reusable vectors and buffers to module scope and mutate them, because per-frame allocation feeds the garbage collector and GC pauses appear as periodic stutters exactly during animation.
- Avoid building strings per frame (template literals for `fillText`, `hsl(...)` color strings, `JSON.stringify` for comparisons), because string construction allocates, and colors and labels can be computed once when state changes instead of once per frame.
- Batch all DOM reads before all DOM writes within a single frame, because interleaving a geometry read like `offsetWidth` after a style write forces the browser to run layout synchronously, and doing that in a loop over players or cards multiplies one layout into dozens.
- Compute layout-dependent values (canvas rect, panel sizes) once per frame or on resize and cache them, rather than querying them inside handlers, because `getBoundingClientRect`, `offsetTop` and `getComputedStyle` all flush pending layout.
- Build DOM updates in a `DocumentFragment` or set one `innerHTML` per list rather than appending nodes one at a time in a loop, because each append into the live tree can trigger style and layout work.
- Update the DOM only for the parts of the state that actually changed by comparing against the previously rendered values, because rewriting the entire player panel on every server event destroys focus, resets scroll position and discards text selection.
- Animate with `transform` and `opacity` rather than `top`, `left`, `width` or `height`, because the former can be handled by the compositor without layout or paint while the latter force both.
- Never use `setInterval` for animation or polling of state, because intervals continue firing in background tabs, drift relative to the display, and can queue up callbacks faster than they complete.
- Measure before optimizing with the browser's performance profiler and treat any rendering rule here as a hypothesis until a flame chart confirms where the time goes, because the actual bottleneck in a board game client is usually one accidental full-page reflow rather than the canvas at all.

### Error handling and user-visible errors

- Attach a `.catch` to every promise chain and wrap every `await` in `try`/`catch` at the point where you can actually do something about the failure, because an unhandled rejection in a module produces only a console message the player will never see.
- Install `window.addEventListener("error", …)` and `window.addEventListener("unhandledrejection", …)` as a last-resort net that shows a "something went wrong" notice and offers a reload, because an exception thrown inside a rAF callback kills that frame's work and the game silently stops updating otherwise.
- Never let an exception escape the render loop: wrap the body of the frame callback in `try`/`catch`, log, and either recover or stop cleanly with a visible message, because a throw inside `requestAnimationFrame` leaves the loop scheduled but the screen frozen with no indication of why.
- Define a single server-side error event (`socket.on("game_error", …)`) carrying a machine-readable `code` and a human-readable `message`, and surface it through one shared toast/banner component, because scattering `alert()` calls blocks the whole page and stops the game loop until the player dismisses it.
- Show errors in a non-blocking, auto-dismissing region that never covers the board or the action buttons, and make it `aria-live="assertive"` for genuine failures, because a modal error during another player's turn hides the very state the message is about.
- Distinguish recoverable errors ("you cannot build there", "not your turn") from fatal ones ("game no longer exists") in the UI and only force a screen change for the latter, because treating a rejected move as fatal throws the player out of a game they are still in.
- Never surface raw exception text or stack traces to players; log the detail to the console and show a plain-language summary, because internal messages both confuse users and leak implementation detail.
- Clear stale error banners on the next successful action or state update, because a "not your turn" message still on screen three turns later reads as the current state of the game.

---

# Part V — Testing, Tooling, and Project Structure

### Separating game logic from transport

- Keep every game rule, state transition, and validation in plain Python classes and functions under `server/game/` that import nothing from `flask`, `flask_socketio`, or `socketio`, because logic that reaches for `emit`, `request.sid`, or `session` cannot be exercised without booting a server and therefore never gets unit-tested.
- Make each socket handler a thin adapter that does exactly three things — parse and validate the incoming payload, call one method on the game engine, emit the result — because a handler containing branching rules logic forces every rule test to go through the Socket.IO layer.
- Have game-logic methods return values or raise domain-specific exceptions (for example `IllegalPlacementError`) instead of emitting error events, because returning a result lets a unit test assert on it directly while the handler decides how to translate it onto the wire.
- Never let game logic read the current player from `session` or a global connection registry; pass the acting player's identity in as an argument, because implicit request-scoped state makes the function untestable outside a request context.
- Define the set of emitted event names and their payload shapes in one place (a constants module or serialization functions) rather than inline in each handler, because scattered literal event names silently drift out of sync with the JavaScript client.
- Give the engine a `to_dict()`/serialization method separate from the rules methods, because the wire format changes for UI reasons far more often than the rules do and the two should not be edited together.

### Testing socket handlers

- Create the Socket.IO test client with `client = socketio.test_client(app, flask_test_client=app.test_client())` rather than `socketio.test_client(app)` alone whenever handlers depend on the Flask session or cookies, because without the Flask test client the session set by an HTTP login route is not visible to the event handlers.
- Assert on events using the documented shape of `get_received()` — a list of dicts with `name` and `args` keys, as in `received = client.get_received(); assert received[0]["name"] == "game_state"` — because indexing blindly into the payload without checking the event name produces tests that pass on the wrong event.
- Remember that `get_received()` drains the queue, so capture it once into a variable and assert against that variable, because a second call returns an empty list and yields confusing "no events" failures.
- Simulate a multiplayer game by constructing several independent test clients against the same app, emitting from one and calling `get_received()` on the others, because broadcast, room membership, and turn-notification bugs only appear with more than one connected client.
- Test that events are correctly scoped: assert that a private payload (a player's own hand of resource cards) appears in that player's `get_received()` and does **not** appear in the other clients', because leaking hidden information to all clients is a real Catan-server bug class that a single-client test cannot detect.
- Do not configure a message queue (Redis and similar) in the testing config, because `SocketIOTestClient` does not work with an external message queue and the tests will hang or silently drop events.
- Build the app through an application factory (`create_app(config)`) so tests get a fresh app and a fresh game registry per test, because module-level global game state carried between tests makes failures depend on test execution order.
- Test connection lifecycle explicitly — `client.connect()`, `client.disconnect()`, `client.is_connected()` — including what happens when a player disconnects mid-turn, because reconnect and drop handling is where server state and client state diverge in practice.
- Cover the malformed-input path for at least the handlers that accept coordinates or indices, asserting the server emits an error and does not mutate state, because a browser client is not a trusted input source.

### What to test first

- Write tests for the rules engine invariants before any transport tests: legal settlement/road placement including the distance rule, resource costs being deducted exactly, turn order and phase transitions, robber movement and stealing, and win-condition detection at the correct victory-point threshold, because these are cheap to test in-process and are where the genuine bugs live.
- Test that an illegal action leaves the game state completely unchanged, not merely that it returns an error, because half-applied moves (resources spent but no building placed) are the most damaging and least visible class of bug.
- Test each cost table entry against a player who has exactly enough and a player who is one resource short, because off-by-one resource checks pass the happy-path test and fail in real games.
- Test the initial-placement phase separately from the main loop, including its reversed second round and the initial resource grant, because setup phases have their own rules and are usually the least covered code.
- Assert conservation invariants after every state-changing operation — total resource cards in players' hands plus the bank equals the starting supply, and no player holds a negative count — because these single assertions catch a wide class of trade, steal, and discard bugs.
- Do not chase line-coverage percentage on the transport layer; prioritize rules coverage, because a handler that merely forwards a call is adequately covered by one test while a placement rule needs many.

### Fixtures and determinism

- Inject a `random.Random` instance (or a roll function) into the game engine's constructor instead of calling module-level `random.shuffle`, `random.choice`, or `random.randint` inside game logic, because a bug in dice- or shuffle-dependent code cannot be reproduced in a test unless the randomness is deterministic and controllable.
- Have production code construct the engine with a real RNG and tests construct it with `Random(12345)` or a fake whose rolls are a scripted list, because seeding at the boundary keeps the game genuinely random in production while making every test replay identically.
- Never seed the global `random` module in tests as a substitute for injection, because the global seed is process-wide, leaks between tests, and breaks the moment tests run in parallel or in a different order.
- Provide a fake dice source that yields a fixed sequence (for example `[7, 7, 6]`) so robber and discard rules can be tested without looping until the roll happens by chance, because probabilistic test setup produces flaky tests.
- Build named pytest fixtures for the game states you assert against repeatedly — `two_player_game_after_setup`, `player_with_exact_city_cost`, `game_one_point_from_victory` — because inlining twenty lines of state construction into each test hides what the test is actually about.
- Compose fixtures rather than duplicating them: derive `game_in_main_phase` from `fresh_game` by applying real engine calls, because a hand-constructed state object can encode a configuration the engine could never actually reach and the test then proves nothing.
- Put shared fixtures in `tests/conftest.py` and keep fixture scope at the default `function` for anything mutable, because a session-scoped mutable game object silently couples tests together.

### Property-based and exhaustive testing

- Use exhaustive testing where the domain is small enough to enumerate — every vertex and edge on the board, every resource-cost combination — because a Catan board has on the order of 54 vertices and 72 edges and a loop over all of them is both faster to write and stronger than sampled cases.
- Use Hypothesis for board-generation invariants that must hold for every seed, generating the seed and asserting structural properties: exactly the expected count of each terrain type, exactly one desert with no number token, every number token in 2–12 excluding 7, and the correct multiset of tokens.
- Assert the Catan-specific adjacency invariant under Hypothesis — no two adjacent hexes both carry 6 or 8 — if the generator claims to enforce it, because this constraint holds for most random seeds by chance and example-based tests will not find the seeds where it fails.
- Use property-based tests for round-trip properties such as `deserialize(serialize(state)) == state`, because save/load corruption is otherwise found only when a real game breaks.
- Do not reach for property-based testing where a specific example is clearer; a rule like "a city costs 3 ore and 2 grain" deserves a plain assertion, because an over-general property test obscures the requirement it encodes.

### Test organization and speed

- Keep tests in a top-level `tests/` directory that mirrors the source layout — `tests/game/test_placement.py`, `tests/game/test_trade.py`, `tests/test_socket_handlers.py` — because a test file that mirrors a module tells you immediately where to add a test for new behavior.
- Name test functions as a behavioral sentence, `test_settlement_rejected_within_two_edges_of_existing_settlement`, not `test_placement_2`, because the function name is what you read in the failure output and it should state the broken requirement without opening the file.
- Follow pytest's discovery conventions (`test_*.py` files, `test_` functions, `Test` classes without `__init__`) and set `--import-mode=importlib` in `pyproject.toml`, because the default `prepend` mode requires globally unique test filenames and breaks once two directories both contain `test_board.py`.
- Keep the whole unit suite under a few seconds by never sleeping, never opening network sockets, and never touching real files (use `tmp_path` for persistence tests), because a suite slower than the edit-run loop stops being run on every change.
- Assert one behavior per test with a clear arrange/act/assert shape, because a test with eight assertions stops at the first failure and hides the rest.
- Mark the slower end-to-end socket tests (`@pytest.mark.slow`) so the default run is the fast rules suite, because the rules suite is the one you want to run on every save.
- Run tests with a fixed `PYTHONHASHSEED` or avoid depending on set/dict iteration order in assertions, because ordering-dependent assertions produce intermittent CI failures that are expensive to diagnose.

### Python tooling

- Adopt Ruff as the single linter and formatter (`ruff check .` and `ruff format .`), because it has largely superseded the flake8 + isort + black stack in current practice, is 10–100× faster, and its formatter is a documented drop-in for black with >99.9% identical output.
- Configure Ruff in `pyproject.toml` under `[tool.ruff]` with an explicit `select` list (at minimum `E`, `F`, `I`, `UP`, `B`) and a pinned `target-version`, because leaving the rule set implicit means a Ruff upgrade silently changes what CI enforces.
- Do not expect Ruff to replace type checking; run mypy or pyright alongside it, because Ruff is a linter and formatter and by design performs no type inference across modules.
- Add type hints to the public signatures of the game engine first (`def place_settlement(self, player_id: str, vertex: VertexId) -> PlacementResult:`), because a rules engine passing dicts of untyped coordinates is exactly where a type checker earns its keep, and hint-free handler bodies are lower value.
- Turn on mypy's `disallow_untyped_defs` for the `game/` package only at first, leaving the transport layer looser, because an all-at-once strict rollout on a large existing `app.py` produces hundreds of errors and gets abandoned.
- Run `ruff check`, `ruff format --check`, mypy, and pytest as separate CI steps so a failure names the tool that failed, and run the same commands locally via a pre-commit hook or a Makefile target, because checks that only exist in CI are discovered after the push.
- Pin the versions of Ruff and mypy themselves, because an unpinned linter upgrade turns a green branch red without any code change.

### Dependencies and environment

- Declare dependencies with their constraints in `pyproject.toml` and treat that as the source of truth, because it is the standard Python project configuration file and it also holds the Ruff, mypy, and pytest configuration, avoiding four scattered config files.
- Ship a fully pinned lock artifact (`uv.lock`, or a `requirements.txt` generated by `uv pip compile`/`pip-tools`) for deployment, because a server is a deployable application and open ranges like `flask>=3.0.0` mean the Docker image built today and the one built next month are different programs.
- Pin transitive dependencies, not just direct ones, because reproducibility fails on an unpinned sub-dependency exactly as easily as on a direct one.
- Always install into a virtual environment (or the project's Nix shell) and never into the system Python, because global installs make the machine's state undeclared and unreproducible on any other machine.
- Keep test and lint tools in a separate dependency group (`[dependency-groups] dev` or an optional-dependencies extra) rather than in the runtime requirements, because pytest and Ruff have no business in the production image.
- Record the Python version the project targets in `pyproject.toml` (`requires-python`) and match it in CI and the Dockerfile, because a version mismatch between dev and CI surfaces as a failure nobody can reproduce locally.

### JavaScript frontend tooling

- Lint the browser code with ESLint 9+ using a flat `eslint.config.js`, because the legacy `.eslintrc` format is superseded and new plugin releases target flat config.
- Write the client as ES modules with explicit `import`/`export` and load it with `<script type="module">`, because a file that assigns to globals cannot be statically analyzed for unused or undefined symbols, and cannot be imported by a test runner at all.
- Enable at minimum `no-undef`, `no-unused-vars`, and `eqeqeq` with the `browser` global environment declared, because typos in a Socket.IO event name or a variable are otherwise found only by a user clicking the wrong thing.
- Extract pure client logic — coordinate math, board geometry, state reducers — into modules that import nothing from the DOM or the Socket.IO client, because those functions can then be unit-tested in Node with no browser at all.
- Use Vitest with jsdom for the small amount of DOM-touching code worth testing, and keep the runner optional rather than mandatory, because a heavyweight browser-test harness on a vanilla-JS project usually costs more than the bugs it catches.
- Assert the client's socket event names against the server's constant list in at least one test, because the client and server drift apart on event names and payload keys and nothing else catches it before runtime.
- Split any frontend file that has grown past a few hundred lines into rendering, networking, and state modules, because a single file mixing canvas drawing, socket wiring, and UI state cannot be reviewed or tested in pieces.

### Repository structure

- Keep four clearly separated top-level areas — pure game logic (`server/game/`), transport and app wiring (`server/app.py` or `server/transport/`), presentation assets (`server/static/`, `server/templates/`), and tests (`tests/`) — because the separation on disk is what makes the "no Flask imports in game logic" rule visible and enforceable.
- Split any module that has grown past a few hundred lines of unrelated concerns into modules named for those concerns, because a 1200-line `game.py` holding board generation, placement rules, trading, and the robber forces every contributor to read all of it to change any of it.
- Split a large `app.py` of socket handlers by feature area (lobby, setup phase, turn actions, trading) using namespaced handler modules registered from the factory, because a single file with 100 `emit` calls makes conflicts and accidental duplicate handler registrations inevitable.
- Put a `create_app()` factory in its own module and keep the `if __name__ == "__main__"` server launch out of it, because a module that starts a server at import time cannot be imported by a test.
- Keep static assets served from `static/` and never inline more than trivial JavaScript in Jinja templates, because script inside a template is invisible to ESLint and to any test runner.

### Logging

- Use `logger = logging.getLogger(__name__)` at module level and call `logger.info(...)`/`logger.debug(...)` instead of `print()`, because print writes unconditionally to stdout with no level, no timestamp, and no way to quiet it in production without editing code.
- Choose levels by consequence: DEBUG for per-move state dumps, INFO for game lifecycle events (created, player joined, game ended), WARNING for rejected client actions, ERROR with `exc_info=True` or `logger.exception()` inside `except` blocks — because a log where everything is the same level cannot be filtered when something breaks.
- Log with context identifiers (game id, player id, event name) in every message, because a multiplayer server interleaves several games in one stream and a bare "invalid placement" line is unusable.
- Configure logging once at application startup via `dictConfig` and let handlers inherit it, rather than calling `basicConfig` from library modules, because per-module configuration produces duplicated or missing output depending on import order.
- Never log secrets, session tokens, cookies, passwords, or full request payloads that may contain them, and never log a player's hidden hand at INFO, because logs are copied into tickets, shipped to third-party aggregators, and retained far longer than the data warrants.
- Log to stdout in containerized deployment rather than to a file inside the container, because the container filesystem is ephemeral and the platform already collects stdout.

### Version control hygiene

- Add a `.gitignore` covering `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, and `node_modules/`, because compiled bytecode and virtualenvs are machine-specific artifacts that create conflicts on every pull.
- Remove already-committed generated files with `git rm -r --cached server/__pycache__` and commit that removal, because adding a `.gitignore` rule does not untrack files that git is already following.
- Keep runtime game state (`data/game.json`, `data/users.json`, save files) out of version control and write it to a path configured by an environment variable, because committed live state means every deploy overwrites production data and every developer's local play session shows up as a diff.
- Do commit genuinely static configuration data such as `data/costs.json` and treat it as source, because it is a game rule expressed as data, not runtime state — but keep it in a directory separate from the mutable saves so the distinction is structural rather than remembered.
- Keep secrets (`SECRET_KEY`, any credentials) out of the repository entirely by reading them from environment variables with no hardcoded fallback in production config, because a default secret key committed to git is a session-forgery vulnerability.
- Commit the lock file and the tool configuration, because reproducibility depends on every checkout resolving to the same dependency versions and the same lint rules.
