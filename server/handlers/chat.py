"""Chat and the event log."""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game.event_log import sanitize_chat
from game.validation import RESOURCE_TYPES
from state import (
    bump_and_broadcast,
    end_game_locked,
    event_log,
    log_event,
    rate_limited,
    reject,
    viewer_for,
)

logger = logging.getLogger(__name__)


def _run_command(command, name):
    parts = command.split()
    if not parts:
        return
    cmd = parts[0].lower().lstrip('/')
    if cmd == 'help':
        log_event('chat', 'Commands: /restart  /add <resource> [count]  /help', player=name)
    elif cmd == 'restart':
        end_game_locked(name)
    elif cmd == 'add':
        game = state.current_game
        if game is None or game.game_state != "started":
            reject('NO_GAME', 'There is no game to add resources to')
            return
        if len(parts) < 2:
            reject('INVALID_PAYLOAD', 'Usage: /add <resource> [count]')
            return
        resource = parts[1].lower()
        if resource not in RESOURCE_TYPES:
            reject('INVALID_PAYLOAD', f'Unknown resource: {resource}')
            return
        count = 1
        if len(parts) >= 3:
            try:
                count = int(parts[2])
            except ValueError:
                reject('INVALID_PAYLOAD', f'Count must be an integer, got "{parts[2]}"')
                return
        if count <= 0:
            reject('INVALID_PAYLOAD', 'Count must be positive')
            return
        player = game.get_player(name)
        if player is None:
            reject('INVALID_TARGET', 'You are not a player in this game')
            return
        player.resources[resource] = player.resources.get(resource, 0) + count
        bump_and_broadcast()
        log_event('chat', f'/add {count} {resource}', player=name)
        emit('command_result', {'message': f'Added {count} {resource}'})
    else:
        reject('UNKNOWN_COMMAND', f'Unknown command /{cmd}. Try /help')


@socketio.on('chat_message')
def handle_chat_message(data):
    if rate_limited():
        return
    """Say something to the table."""
    name = viewer_for()
    if name is None:
        reject('NOT_IN_LOBBY', 'Join before chatting')
        return

    try:
        text = sanitize_chat(data.get('text'))
    except ValueError as exc:
        reject('INVALID_PAYLOAD', str(exc))
        return

    if text.strip().startswith('/'):
        _run_command(text.strip(), name)
        return

    log_event('chat', text, player=name)


@socketio.on('request_log')
def handle_request_log(data=None):
    if rate_limited():
        return
    """Catch up after a reconnect. Replies to the asking socket only."""
    after_id = (data or {}).get('after_id', 0)
    if isinstance(after_id, bool) or not isinstance(after_id, int) or after_id < 0:
        after_id = 0
    emit('log_history', {'entries': event_log.since(after_id)})
