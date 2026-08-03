"""Shared server state and the helpers every handler needs.

Handlers live in `handlers/` and import from here. Two names — `current_game`
and `lobby_rules` — are *rebound* rather than mutated, so they must always be
reached through this module (`state.current_game`), never imported by value, or
a handler would keep looking at the game that was running when it was imported.
"""

import json
import logging
import os
import random
import threading

from config import get_config
from extensions import socketio
from flask import request
from flask_socketio import disconnect, emit
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
current_game = None

# Serializes validate-then-apply for the single game. Two events arriving in the
# same tick would otherwise both validate against the pre-action state and both
# apply — the last development card bought twice, a double-clicked road placed
# twice.
game_lock = threading.RLock()

# Socket id -> the player name this connection joined as. This drives *which
# private hand a socket is shown*, not authorization: acting as another player
# is deliberately allowed here so the group can cover for someone mid-game.
# Taking over means joining as them, which also switches the private view.
socket_viewers = {}

# Serializes writes to users.json.
users_file_lock = threading.Lock()

# Flood protection. One limiter covers every event, keyed by socket and event,
# so a client cannot burn the server down with cheap-to-send, expensive-to-serve
# messages like refresh_board.
rate_limiter = RateLimiter()
abuse_tracker = AbuseTracker()

# Chat and game history. Survives games so the table can look back at what
# happened; bounded internally so a long session cannot grow without limit.
event_log = EventLog()

# Rules the lobby has selected for the next game. Anyone in the lobby can change
# these; they are frozen into the Game when it starts, because a rule that
# changed mid-game would invalidate decisions players had already made.
lobby_rules = rules_module.defaults()


def restore_saved_game():
    """Bring back an interrupted game on startup.

    A corrupt or outdated save is reported and skipped rather than half-loaded:
    resuming a game whose invariants do not hold is worse than starting fresh.
    """
    global current_game
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
    current_game = restored
    logger.info(
        "restored game: players=%s phase=%s turn=%s",
        restored.get_player_names(),
        restored.game_phase,
        restored.turn_count,
    )


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
    logger.warning(
        "rejected %s from sid=%s: %s (%s)", request.event.get('message'), request.sid, message, code
    )
    # Sender only. One player's illegal move is not the table's business, and
    # what they tried to do leaks what they hold.
    emit('error', {'code': code, 'message': message})


def rate_limited() -> bool:
    """Whether this event should be dropped. Call at the top of a handler.

    Checks payload size first: deserialising hostile input is itself the denial
    of service, so an oversized message is refused before it is looked at.
    Persistent offenders are disconnected rather than merely throttled — a
    client behaving that way is not a player having a bad network day.
    """
    event = request.event.get('message') if request else '?'
    args = request.event.get('args') if request else None
    sid = getattr(request, 'sid', '?')
    key = f"{sid}:{event}"

    if args and payload_too_large(args[0] if args else None):
        logger.warning("oversized payload for %s from sid=%s", event, sid)
        emit('error', {'code': 'PAYLOAD_TOO_LARGE', 'message': 'That message was too large.'})
        return True

    if rate_limiter.allow(key, limit=limit_for(event)):
        return False

    wait = rate_limiter.retry_after(key, limit=limit_for(event))
    strikes = abuse_tracker.record_violation(sid)
    logger.warning(
        "rate limited %s from sid=%s viewer=%s (strike %s, retry in %.1fs)",
        event,
        sid,
        socket_viewers.get(sid),
        strikes,
        wait,
    )

    if abuse_tracker.should_disconnect(sid):
        logger.warning("disconnecting sid=%s for sustained flooding", sid)
        emit('error', {'code': 'RATE_LIMITED', 'message': 'Too many requests - disconnecting.'})
        disconnect()
        return True

    emit(
        'error',
        {
            'code': 'RATE_LIMITED',
            'message': f'Slow down - try again in {wait:.1f}s.',
            'details': {'retry_after': wait},
        },
    )
    return True


def log_event(kind, text, player=None, **details):
    """Record something that happened and push it to everyone.

    Timestamps come from the log (server clock) — a client that owns the clock
    could otherwise forge history.
    """
    entry = event_log.log(kind, text, player=player, **details)
    socketio.emit('event_logged', {'entry': entry})
    return entry


def viewer_for(sid=None):
    """The player name a socket is currently viewing as, if any."""
    return socket_viewers.get(sid or request.sid)


def broadcast_board(extra=None):
    """Send the board to every connected socket, filtered per recipient.

    Each socket gets its own payload because hands are hidden information: a
    single broadcast sends identical bytes to everyone, and anything in those
    bytes is readable in DevTools no matter what the UI draws.
    """
    if current_game is None:
        return
    for sid, name in list(socket_viewers.items()):
        payload = {
            'board': current_game.get_board_data(viewer=name),
            'log_last_id': event_log.last_id,
        }
        if extra:
            payload.update(extra)
        emit('board_updated', payload, to=sid)


def save_game():
    """Write the game to disk so a restart does not lose it.

    Saved on every accepted change rather than on a timer: the file is small
    (only decided board state, not the derived graph) and this way there is no
    window in which the last move is missing.
    """
    if current_game is None:
        return
    try:
        persistence.save(current_game, SAVE_FILE)
    except Exception:
        # A failed save must never take the live game down with it.
        logger.exception("could not save the game to %s", SAVE_FILE)


def bump_and_broadcast(extra=None):
    """Record that state changed, then push it to everyone."""
    if current_game is not None:
        current_game.state_version += 1
        problems = current_game.check_invariants()
        if problems:
            # Validation and application disagree — the rules are not actually
            # being enforced where we think they are. Loud, with context.
            logger.error(
                "INVARIANT VIOLATION after %s: %s",
                request.event.get('message') if request else '?',
                problems,
            )
        save_game()
    broadcast_board(extra)


def end_game_locked(by):
    """Abandon the current game and return everyone to the lobby.

    Shared by the `end_game` event and the in-game `/restart` command: both
    must tear the running game down exactly the same way, or one path leaves
    a half-reset server behind.
    """
    global current_game
    with game_lock:
        if current_game is None or current_game.game_state != "started":
            reject('NO_GAME', 'There is no game to end')
            return

        logger.info("game ended by %s (was: %s)", by, current_game.get_player_names())
        log_event('game', f"{by} ended the game", player=by)
        current_game = None
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)

    socketio.emit('game_ended', {'by': by})
    emit_user_list()
    emit_rules()


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
    present = set(socket_viewers.values())
    return [u for u in load_users() if u.get('name') in present]


def emit_rules(to_sender_only=False):
    """Publish the rule catalogue and the current selection.

    The catalogue travels with the selection so the lobby can render itself
    from the server's registry — adding a rule server-side makes it appear in
    every client with no front-end change.
    """
    payload = {
        'catalogue': rules_module.catalogue(),
        'selected': lobby_rules,
        'locked': current_game is not None and current_game.game_state == "started",
    }
    if to_sender_only:
        emit('rules_changed', payload)
    else:
        socketio.emit('rules_changed', payload)


def send_state_snapshot():
    """Send the full current state to the requesting socket only."""
    if current_game is None or current_game.game_state != "started":
        emit('game_state', {'in_game': False})
        return

    current_player = current_game.players[current_game.current_player_index]
    emit(
        'game_state',
        {
            'in_game': True,
            'players': current_game.get_player_names(),
            'observers': current_game.observers,
            'current_player': current_player.name if current_player else None,
            'board': current_game.get_board_data(viewer=viewer_for()),
        },
    )


def emit_user_list():
    users = lobby_users()
    players = [u for u in users if u.get('role') == 'player']
    observers = [u for u in users if u.get('role') == 'observer']
    socketio.emit(
        'user_list',
        {
            'players': players,
            'observers': observers,
            'min_players': lobby_rules['min_players'],
            'max_players': MAX_PLAYERS,
        },
    )
