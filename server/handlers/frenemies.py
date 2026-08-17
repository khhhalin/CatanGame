"""Catan: Frenemies actions — gifting a resource and declining a steal.

Each handler is the thin socket wrapper the engine's Frenemies methods were
written for: rate-limit, confirm the table agreed to the rule, confirm the
sender holds the seat it claims, take the lock, call the engine method, and
broadcast. The engine decides every rule; nothing here does. The two
earn-triggers that ride on existing actions — a harmless robber move and a
first-time network connection — are awarded inside `move_robber` and
`build_road`, so they need no handler of their own. Registered by importing this
module in app.py, like every other handler.
"""

import logging

from extensions import socketio
from game.validation import InvalidPayload, require_str
from state import bump_and_broadcast, log_event, rate_limited, reject, require_actor

from handlers.ships import _started_game

logger = logging.getLogger(__name__)


@socketio.on('gift_resource')
def handle_gift_resource(data):
    if rate_limited():
        return
    session = _started_game('favour_tokens')
    if session is None:
        return
    name = require_actor(data)
    if name is None:
        return
    try:
        recipient = require_str(data.get('recipient'), 'recipient')
        resource = require_str(data.get('resource'), 'resource')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.gift_resource(name, recipient, resource)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('trade', f"{name} gifted a {resource} to {recipient}", player=name)
        # Which card moved is the giver's and recipient's to know; the table is
        # told a gift happened and that it earned a favour, not what it was.
        for sid, viewer in list(session.viewers.items()):
            payload = {'player': name, 'recipient': recipient, 'favours': result['favours']}
            if viewer in (name, recipient):
                payload['resource'] = resource
            socketio.emit('resource_gifted', payload, to=sid)
        bump_and_broadcast()


@socketio.on('decline_steal')
def handle_decline_steal(data):
    if rate_limited():
        return
    session = _started_game('favour_tokens')
    if session is None:
        return
    name = require_actor(data)
    if name is None:
        return
    with session.lock:
        result = session.game.decline_steal(name)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('robber', f"{name} declined to steal on the desert", player=name)
        bump_and_broadcast()
