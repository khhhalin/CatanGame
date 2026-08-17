"""Catan: Oil Springs actions: converting oil to resources, sequestering oil,
and upgrading a city into a metropolis.

Each handler is the thin socket wrapper the engine's Oil Springs methods were
written for — rate-limit, confirm the table agreed to the rule, confirm the
sender holds the seat it claims, take the lock, call the engine method, and
broadcast. The engine decides every rule; nothing here does. Registered by
importing this module in app.py, like every other handler.
"""

import logging

from extensions import socketio
from game.validation import InvalidPayload, require_str
from state import bump_and_broadcast, log_event, reject

from handlers.building import announce_victory
from handlers.tb import _actor_for

logger = logging.getLogger(__name__)


@socketio.on('convert_oil')
def handle_convert_oil(data):
    got = _actor_for('disaster_track', data)
    if got is None:
        return
    session, name = got
    try:
        resource = require_str(data.get('resource'), 'resource')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.convert_oil_to_resource(name, resource)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} converted oil into 2 {resource}", player=name)
        bump_and_broadcast()


@socketio.on('sequester_oil')
def handle_sequester_oil(data):
    got = _actor_for('oil_sequester_vp', data)
    if got is None:
        return
    session, name = got
    with session.lock:
        result = session.game.sequester_oil(name)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} sequestered an oil", player=name)
        bump_and_broadcast()
        # Sequestering scores victory points, so it can win outright — announced
        # on this action, not held to the next roll (rules p. 3: the win "which
        # includes resolving the Disaster Phase").
        announce_victory(name)


@socketio.on('build_oil_metropolis')
def handle_build_oil_metropolis(data):
    got = _actor_for('oil_metropolis', data)
    if got is None:
        return
    session, name = got
    try:
        vertex = require_str(data.get('vertex'), 'vertex')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.build_oil_metropolis(name, vertex)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} built a metropolis", player=name)
        bump_and_broadcast()
        # A metropolis is worth 3 VP, so it can win outright — announced now.
        announce_victory(name)
