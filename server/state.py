"""The game session and the helpers every handler needs.

Handlers live in `handlers/` and import from here. Everything that changes
during a session — the game, the lobby's rule selection, who is watching, the
history, the flood limiters — belongs to a `GameSession` reached through
`state.session()`. It used to be a set of module globals, two of which were
*rebound* rather than mutated, so every handler had to remember to spell them
`state.current_game` or quietly keep looking at a finished game. Attributes on
one object cannot go stale that way, and a test can build a fresh session
instead of unsetting globals one by one.
"""

import json
import logging
import os
import random
import threading

import build_info
from config import get_config
from extensions import socketio
from flask import request
from flask_socketio import disconnect, emit
from game import commands as commands_module
from game import persistence
from game import rules as rules_module
from game.event_log import EventLog
from game.rate_limit import (
    AbuseTracker,
    RateLimiter,
    limit_for,
    payload_too_large,
)

logger = logging.getLogger(__name__)

config = get_config()

DATA_FILE = os.path.join(config.DATA_DIR, 'users.json')
SAVE_FILE = os.path.join(config.DATA_DIR, 'game.json')
MAX_PLAYERS = config.MAX_PLAYERS
MIN_PLAYERS = config.MIN_PLAYERS

# Serializes writes to users.json. Not part of the session: the file outlives
# every game, and a new session must not hand out a second lock on it.
users_file_lock = threading.Lock()


class GameSession:
    """One server's worth of mutable state.

    There is exactly one game per process — state lives in memory and the
    deployment is a single worker (see wsgi.py) — so there is exactly one of
    these. It exists so that the game and everything that travels with it are
    attributes reached through `session()` rather than module globals that get
    rebound underneath the handlers reading them.
    """

    def __init__(self, config=None):
        self.config = config or get_config()
        self.game = None

        # Rules the lobby has selected for the next game. Anyone in the lobby
        # can change these; they are frozen into the Game when it starts,
        # because a rule that changed mid-game would invalidate decisions
        # players had already made.
        self.lobby_rules = rules_module.defaults()

        # Socket id -> the seat this connection holds. It decides both which
        # private hand the socket is shown and, through `require_actor`, whose
        # actions it may take: identity comes from the connection, never from
        # a `name` in the payload, which anyone can forge. Covering for someone
        # who stepped away still works — it means joining as them with
        # `takeover`, which moves the seat to that socket and is logged.
        self.viewers = {}

        # Chat and game history. Survives games so the table can look back at
        # what happened; bounded internally so a long session cannot grow
        # without limit.
        self.event_log = EventLog()

        # Serializes validate-then-apply for the single game. Two events
        # arriving in the same tick would otherwise both validate against the
        # pre-action state and both apply — the last development card bought
        # twice, a double-clicked road placed twice.
        self.lock = threading.RLock()

        # Flood protection. One limiter covers every event, keyed by socket and
        # event, so a client cannot burn the server down with cheap-to-send,
        # expensive-to-serve messages like refresh_board.
        self.rate_limiter = RateLimiter()
        self.abuse_tracker = AbuseTracker()


_session = GameSession()


def session() -> GameSession:
    """The session this process is serving. The one way in."""
    return _session


def new_session(config=None) -> GameSession:
    """Start again from an empty session.

    Called by the factory, so building an app means serving a fresh server —
    which is what lets a test start from a clean table instead of unsetting
    globals one at a time and hoping it remembered them all.
    """
    global _session
    _session = GameSession(config)
    return _session

def restore_saved_game():
    """Bring back an interrupted game on startup.

    A corrupt or outdated save is reported and skipped rather than half-loaded:
    resuming a game whose invariants do not hold is worse than starting fresh.
    """
    try:
        restored = persistence.load(SAVE_FILE, config=config)
    except persistence.NotASaveFile:
        logger.info("%s is not a saved game; starting fresh", SAVE_FILE)
        return
    except Exception:
        logger.exception("ignoring unusable save at %s", SAVE_FILE)
        return
    if restored is None:
        return
    session().game = restored
    logger.info("restored game: players=%s phase=%s turn=%s",
                restored.get_player_names(), restored.game_phase, restored.turn_count)

COLOR_PALETTE = [
    '#3498db',  # Blue
    '#27ae60',  # Green
    '#f1c40f',  # Yellow
    '#e74c3c',  # Red
    '#9b59b6',  # Purple
    '#e67e22',  # Orange
    '#ff6b9d',  # Pink
    '#ecf0f1',  # White
    '#2c3e50',  # Black
]


def seat_limit() -> int:
    """How many players this table seats.

    The cap is a rule like the clocks are: 0 means "whatever this server is
    configured with", so a table that never opened the setting gets the
    deployment's own number and an old save loads without inventing one. It
    was a bare config constant, which made it the one seating number the
    lobby could not agree on — `min_players` has always been a rule.

    A running game answers from its own frozen rules: the rules a game started
    under are the rules it is played under, and a seat opened mid-game by a
    lobby edit would seat a seventh player into a six-player board.
    """
    game = session().game
    rules = game.rules if game is not None else session().lobby_rules
    return rules['max_players'] or MAX_PLAYERS


def get_random_color():
    """Get a random color from the palette."""
    return random.choice(COLOR_PALETTE)

def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            data = json.load(f)
            return data.get('users', [])
    return []

def save_users(users):
    """Write the user list atomically.

    A plain in-place write that is interrupted, or two writes interleaving,
    leaves a truncated file that fails to parse on the next read and breaks
    joining permanently. Writing to a temp file in the same directory and
    renaming makes the replacement all-or-nothing.
    """
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    temp_path = f"{DATA_FILE}.tmp"
    with open(temp_path, 'w') as f:
        json.dump({'users': users}, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, DATA_FILE)

def update_users(mutate):
    """Read, modify, and write the user list as one atomic unit.

    The read and the write must be under the same lock: two players joining at
    the same moment would otherwise both read the old list, each append
    themselves, and the second write would drop the first player entirely.

    `mutate` takes the current list and returns (new_list, result); result is
    passed back to the caller.
    """
    with users_file_lock:
        users, result = mutate(load_users())
        if users is not None:
            save_users(users)
        return result

def reject(code, message):
    """Send a rejection to the client whose action failed, and log it.

    Every rejected action gets a reply — a client that hears nothing cannot
    tell rejection from a dropped connection, and leaves its button spinning.
    """
    logger.warning("rejected %s from sid=%s: %s (%s)", request.event.get('message'),
                   request.sid, message, code)
    # Sender only. One player's illegal move is not the table's business, and
    # what they tried to do leaks what they hold.
    emit('error', {'code': code, 'message': message})

def rate_limited(budget_event=None) -> bool:
    """Whether this event should be dropped. Call at the top of a handler.

    Checks payload size first: deserialising hostile input is itself the denial
    of service, so an oversized message is refused before it is looked at.
    Persistent offenders are disconnected rather than merely throttled — a
    client behaving that way is not a player having a bad network day.

    `budget_event` spends another event's bucket instead of this one's. It
    exists for the slash commands, which are typed into the chat box: given a
    bucket of their own, a client could take turns between `chat_message` and
    `run_command` and talk to the table at twice the rate chat allows.
    """
    event = request.event.get('message') if request else '?'
    args = request.event.get('args') if request else None
    sid = getattr(request, 'sid', '?')
    key = f"{sid}:{budget_event or event}"

    if args and payload_too_large(args[0] if args else None):
        logger.warning("oversized payload for %s from sid=%s", event, sid)
        emit('error', {'code': 'PAYLOAD_TOO_LARGE',
                       'message': 'That message was too large.'})
        return True

    limiters = session()
    budget = limit_for(budget_event or event)
    if limiters.rate_limiter.allow(key, limit=budget):
        return False

    wait = limiters.rate_limiter.retry_after(key, limit=budget)
    strikes = limiters.abuse_tracker.record_violation(sid)
    logger.warning("rate limited %s from sid=%s viewer=%s (strike %s, retry in %.1fs)",
                   event, sid, limiters.viewers.get(sid), strikes, wait)

    if limiters.abuse_tracker.should_disconnect(sid):
        logger.warning("disconnecting sid=%s for sustained flooding", sid)
        emit('error', {'code': 'RATE_LIMITED',
                       'message': 'Too many requests - disconnecting.'})
        disconnect()
        return True

    emit('error', {
        'code': 'RATE_LIMITED',
        'message': f'Slow down - try again in {wait:.1f}s.',
        'details': {'retry_after': wait},
    })
    return True

def log_event(kind, text, player=None, **details):
    """Record something that happened and push it to everyone.

    Timestamps come from the log (server clock) — a client that owns the clock
    could otherwise forge history.
    """
    entry = session().event_log.log(kind, text, player=player, **details)
    socketio.emit('event_logged', {'entry': entry})
    return entry

def viewer_for(sid=None):
    """The player name a socket is currently viewing as, if any."""
    return session().viewers.get(sid or request.sid)

def require_actor(data=None):
    """The seat this socket holds, or None once the action has been refused.

    Every game handler starts here. The acting player is whoever this
    *connection* is seated as; the `name` a client sends is only its claim
    about itself, and until this existed any connected socket could send
    another player's name and act as them. The field is still read — the
    browser puts it in every payload — but only to notice a disagreement,
    which is either a client bug or somebody trying it on.
    """
    seat = session().viewers.get(request.sid)
    claimed = data.get('name') if isinstance(data, dict) else None
    if isinstance(claimed, str) and claimed.strip() and claimed.strip() != seat:
        logger.warning("payload name %r does not match seat %r for %s from sid=%s",
                       claimed, seat, request.event.get('message'), request.sid)

    if seat is None:
        reject('NOT_SEATED', 'Join the table before taking an action')
        return None

    game = session().game
    if game is not None and game.game_state == "started" and not game.is_player(seat):
        # An observer holds a seat in the lobby but none at the table. Without
        # this they would reach the engine under a name it does not know.
        reject('NOT_A_PLAYER', 'Observers cannot act in the game')
        return None
    return seat

def broadcast_board(extra=None):
    """Send the board to every connected socket, filtered per recipient.

    Each socket gets its own payload because hands are hidden information: a
    single broadcast sends identical bytes to everyone, and anything in those
    bytes is readable in DevTools no matter what the UI draws.

    Sent through `socketio.emit` rather than the request-scoped `emit`: the turn
    watchdog broadcasts from a background task with no request behind it, and
    the request-scoped form raised there — so every board update the server sent
    on its own initiative was lost inside the watchdog's except clause.
    """
    live = session()
    if live.game is None:
        return
    for sid, name in list(live.viewers.items()):
        payload = {
            'board': live.game.get_board_data(viewer=name),
            'log_last_id': live.event_log.last_id,
            # Which build served this. A tab left open across a deploy keeps
            # talking to the new server with the old client, and this is what
            # lets it notice: the panel latches the first id it is told and says
            # so, loudly, the moment a later payload disagrees.
            'build': build_info.summary(),
        }
        if extra:
            payload.update(extra)
        socketio.emit('board_updated', payload, to=sid)

def announce_choices():
    """Tell each player who owes a decision what they are being asked.

    Sent to that player's own sockets only, because the options can be the
    contents of somebody else's hand. The table learns that the game is waiting
    from the board snapshot, which carries every pending choice redacted.
    """
    game = session().game
    if game is None or not game.pending_choices:
        return
    for sid, name in list(session().viewers.items()):
        choice = game.pending_choice_for(name)
        if choice is not None:
            # socketio.emit for the same reason as broadcast_board: an
            # expiring choice is announced from the watchdog, with no request.
            socketio.emit('choice_required', game.choice_to_dict(choice, viewer=name), to=sid)

def save_game():
    """Write the game to disk so a restart does not lose it.

    Saved on every accepted change rather than on a timer: the file is small
    (only decided board state, not the derived graph) and this way there is no
    window in which the last move is missing.
    """
    game = session().game
    if game is None:
        return
    try:
        persistence.save(game, SAVE_FILE)
    except Exception:
        # A failed save must never take the live game down with it.
        logger.exception("could not save the game to %s", SAVE_FILE)

def bump_and_broadcast(extra=None):
    """Record that state changed, then push it to everyone."""
    game = session().game
    if game is not None:
        game.state_version += 1
        problems = game.check_invariants()
        if problems:
            # Validation and application disagree — the rules are not actually
            # being enforced where we think they are. Loud, with context.
            logger.error("INVARIANT VIOLATION after %s: %s",
                         request.event.get('message') if request else '?', problems)
        save_game()
    broadcast_board(extra)

def get_user_by_name(users, name):
    for user in users:
        if user.get('name') == name:
            return user
    return None

def remove_user_by_name(users, name):
    return [u for u in users if u.get('name') != name]

def lobby_users():
    """The users actually present right now.

    users.json is a *memory* of everyone who has ever joined — it is what lets
    a returning player keep their colour. It is not the roster. Nothing removes
    an entry when someone closes their tab, so treating the file as the roster
    let four players from a finished session occupy every seat forever while
    the lobby showed nobody. Presence comes from live sockets instead.

    A player who drops mid-game keeps their seat: that roster is the Game
    object, not this list.
    """
    present = set(session().viewers.values())
    return [u for u in load_users() if u.get('name') in present]

def emit_rules(to_sender_only=False):
    """Publish the rule catalogue and the current selection.

    The catalogue travels with the selection so the lobby can render itself
    from the server's registry — adding a rule server-side makes it appear in
    every client with no front-end change. The presets ride along for the same
    reason: each one is a named set of individual rules the lobby can offer as
    a one-click shortcut.
    """
    live = session()
    payload = {
        'catalogue': rules_module.catalogue(),
        'presets': rules_module.presets(),
        'selected': live.lobby_rules,
        'locked': live.game is not None and live.game.game_state == "started",
    }
    if to_sender_only:
        emit('rules_changed', payload)
    else:
        socketio.emit('rules_changed', payload)

    # The command bar renders from the server's catalogue for the same reason
    # the rules picker does, and which commands this table may run is decided by
    # the rules that just went out — so the two travel together rather than
    # leaving the client to work out availability from a rule id.
    emit_commands(to_sender_only)

def emit_commands(to_sender_only=False):
    """Publish the slash command catalogue, availability already worked out."""
    live = session()
    running = live.game is not None and live.game.game_state == "started"
    payload = {
        'commands': commands_module.catalogue(
            live.game.rules if running else live.lobby_rules, running,
        ),
        'prefix': commands_module.PREFIX,
    }
    if to_sender_only:
        emit('commands_changed', payload)
    else:
        socketio.emit('commands_changed', payload)

def send_state_snapshot():
    """Send the full current state to the requesting socket only."""
    game = session().game
    if game is None or game.game_state != "started":
        emit('game_state', {'in_game': False, 'build': build_info.summary()})
        return

    current_player = game.players[game.current_player_index]
    emit('game_state', {
        'in_game': True,
        'build': build_info.summary(),
        'players': game.get_player_names(),
        'observers': game.observers,
        'current_player': current_player.name if current_player else None,
        'board': game.get_board_data(viewer=viewer_for())
    })

def emit_user_list():
    users = lobby_users()
    players = [u for u in users if u.get('role') == 'player']
    observers = [u for u in users if u.get('role') == 'observer']
    socketio.emit('user_list', {
        'players': players,
        'observers': observers,
        'min_players': session().lobby_rules['min_players'],
        'max_players': seat_limit(),
    })
