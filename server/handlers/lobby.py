"""Joining, the lobby roster, house rules, and starting or ending a game."""

import logging
import os

import state
from extensions import socketio
from flask import request
from flask_socketio import emit
from game import rules as rules_module
from game.game import Game
from game.validation import (
    InvalidPayload,
    require_str,
)
from state import (
    MAX_PLAYERS,
    SAVE_FILE,
    abuse_tracker,
    config,
    emit_rules,
    emit_user_list,
    game_lock,
    get_random_color,
    get_user_by_name,
    lobby_users,
    log_event,
    rate_limited,
    rate_limiter,
    reject,
    remove_user_by_name,
    save_game,
    send_state_snapshot,
    socket_viewers,
    update_users,
    viewer_for,
)

logger = logging.getLogger(__name__)


@socketio.on('join')
def handle_join(data):
    if rate_limited():
        return
    try:
        name = require_str(data.get('name'), 'name')
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    # Taking over someone's seat is a supported move, but it has to be asked
    # for. Browsers pre-fill the name field, so without this a second window
    # silently joins as whoever joined first and both end up viewing that
    # player — which reads as "every browser became A".
    if not data.get('takeover'):
        holder = next(
            (sid for sid, viewer in socket_viewers.items()
             if viewer == name and sid != request.sid),
            None,
        )
        if holder is not None:
            reject('NAME_TAKEN',
                   f'"{name}" is already connected. Pick a different name, '
                   f'or confirm to take over their seat.')
            return

    role = data.get('role', 'observer')
    if role not in ('player', 'observer'):
        role = 'observer'

    color = data.get('color', '')
    if not isinstance(color, str) or len(color) > 32:
        color = ''

    if state.current_game is not None and state.current_game.game_state == "started":
        if state.current_game.is_player(name):
            role = "player"
        else:
            role = "observer"

    def add_or_replace(users):
        chosen_color = color

        existing_user = get_user_by_name(users, name)
        if existing_user:
            users = remove_user_by_name(users, name)
            # Use provided color, or existing saved color, or random
            if not chosen_color:
                chosen_color = existing_user.get('color')

        if not chosen_color:
            chosen_color = get_random_color()

        if role == 'player':
            # Count seats held by people who are actually connected, excluding
            # this socket's own name so rejoining or taking over a seat never
            # counts twice.
            present = set(socket_viewers.values()) - {name}
            player_count = sum(
                1 for u in users
                if u.get('role') == 'player' and u.get('name') in present
            )
            if player_count >= MAX_PLAYERS:
                return None, 'full'

        users.append({'name': name, 'role': role, 'color': chosen_color})
        return users, 'ok'

    if update_users(add_or_replace) == 'full':
        reject('GAME_FULL', f'Cannot join as player. Max {MAX_PLAYERS} players allowed.')
        return

    # Bind the socket's private view only now that the join has been accepted.
    # Binding before the seat check left a rejected socket registered as
    # present, which then made its own name look taken on the retry.
    socket_viewers[request.sid] = name

    if state.current_game is not None and state.current_game.game_state == "started" \
            and not state.current_game.is_player(name):
        state.current_game.add_observer(name)

    logger.info("join name=%s role=%s sid=%s", name, role, request.sid)
    log_event('game', f"{name} joined as {role}", player=name)
    emit_user_list()

    # Always answer a join with the current state, whether or not a game is
    # running. A client that reconnects during the lobby otherwise gets nothing
    # back and has no recovery but a page reload.
    send_state_snapshot()

    # Push the rules unasked, so a client that arrives late sees the table's
    # selection without having to know to request it.
    emit_rules(to_sender_only=True)

@socketio.on('request_users')
def handle_request_users(data=None):
    if rate_limited():
        return
    emit_user_list()

@socketio.on('request_rules')
def handle_request_rules(data=None):
    if rate_limited():
        return
    emit_rules(to_sender_only=True)

@socketio.on('set_rules')
def handle_set_rules(data):
    if rate_limited():
        return
    """Change the rules for the next game.

    Anyone in the lobby may do this — it is a shared decision, and the table
    can talk. It is refused once a game is running.
    """

    if state.current_game is not None and state.current_game.game_state == "started":
        reject('GAME_IN_PROGRESS', 'Rules cannot change once a game has started')
        return

    if viewer_for() is None:
        reject('NOT_IN_LOBBY', 'Join before changing the rules')
        return

    state.lobby_rules = rules_module.coerce(data.get('rules'))
    logger.info("rules set by %s: %s", viewer_for(), state.lobby_rules)
    log_event('rules', f"{viewer_for()} changed the house rules", player=viewer_for())
    emit_rules()

@socketio.on('request_state')
def handle_request_state(data=None):
    if rate_limited():
        return
    """Explicit resync. Replies to the asking socket, never the room."""
    send_state_snapshot()

@socketio.on('end_game')
def handle_end_game(data=None):
    if rate_limited():
        return
    """Abandon the current game and return everyone to the lobby.

    Without this there is no way out of a game at all: a game that is
    abandoned, or left half-finished because everyone closed their tab, keeps
    `state.current_game` alive forever, so `start_game` refuses and every new arrival
    is dropped into a match nobody is playing.

    Any player at the table may call it — this is a friendly game, and the
    alternative is restarting the server.
    """

    with game_lock:
        if state.current_game is None or state.current_game.game_state != "started":
            reject('NO_GAME', 'There is no game to end')
            return

        if viewer_for() is None:
            reject('NOT_IN_LOBBY', 'Join before ending the game')
            return

        logger.info("game ended by %s (was: %s)", viewer_for(),
                    state.current_game.get_player_names())
        log_event('game', f"{viewer_for()} ended the game", player=viewer_for())
        state.current_game = None
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)

    socketio.emit('game_ended', {'by': viewer_for()})
    emit_user_list()
    emit_rules()

@socketio.on('start_game')
def handle_start_game(data=None):
    if rate_limited():
        return

    with game_lock:
        if state.current_game is not None and state.current_game.game_state == "started":
            reject('GAME_IN_PROGRESS', 'A game is already in progress')
            return

        _start_game_locked()

def _start_game_locked():

    # Seat only people who are actually here — the remembered list in
    # users.json includes everyone who has ever played.
    users = lobby_users()
    players = [u.get('name') for u in users if u.get('role') == 'player']
    observers = [u.get('name') for u in users if u.get('role') == 'observer']

    # Build player colors dict from users
    player_colors = {}
    for u in users:
        if u.get('role') == 'player' and u.get('color'):
            player_colors[u.get('name')] = u.get('color')

    minimum = state.lobby_rules['min_players']
    if len(players) < minimum:
        reject('NOT_ENOUGH_PLAYERS',
               f'Need at least {minimum} player{"s" if minimum != 1 else ""} to start '
               f'({len(players)} in the lobby)')
        return

    state.current_game = Game(players, observers, player_colors, config=config,
                        rules=state.lobby_rules)
    state.current_game.start()
    state.current_game.update_harbormaster()
    logger.info("game started players=%s observers=%s rules=%s",
                players, observers, state.current_game.rules)
    log_event('game', f"Game started with {', '.join(players)}")
    save_game()
    emit_rules()

    current_player = state.current_game.players[state.current_game.current_player_index]
    for sid, name in list(socket_viewers.items()):
        emit('game_started', {
            'players': state.current_game.get_player_names(),
            'observers': state.current_game.observers,
            'current_player': current_player.name if current_player else None,
            'board': state.current_game.get_board_data(viewer=name)
        }, to=sid)

@socketio.on('disconnect')
def handle_disconnect(reason=None):
    """Drop the socket's view binding and free its lobby seat.

    The seat in a *running game* survives — a dropped connection is usually a
    brief blip, and ending the game would punish everyone else for it. But the
    lobby roster is presence-based, so leaving must free the slot; otherwise
    yesterday's players still fill the lobby today.

    Current python-socketio passes a disconnect reason; the parameter is
    optional so the handler also works on versions that pass nothing.
    """
    name = socket_viewers.pop(request.sid, None)
    abuse_tracker.forget(request.sid)
    rate_limiter.prune()
    logger.info("disconnect name=%s sid=%s reason=%s", name, request.sid, reason)
    if name is not None:
        emit_user_list()
