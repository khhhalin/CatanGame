"""Chat and the event log."""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game.event_log import sanitize_chat
from state import (
    log_event,
    rate_limited,
    reject,
    viewer_for,
)

logger = logging.getLogger(__name__)


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

    log_event('chat', text, player=name)

@socketio.on('request_log')
def handle_request_log(data=None):
    session = state.session()
    if rate_limited():
        return
    """Catch up after a reconnect. Replies to the asking socket only."""
    after_id = (data or {}).get('after_id', 0)
    if isinstance(after_id, bool) or not isinstance(after_id, int) or after_id < 0:
        after_id = 0
    emit('log_history', {'entries': session.event_log.since(after_id)})
