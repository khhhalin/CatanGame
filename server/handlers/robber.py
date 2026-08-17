"""The robber: moving it, discarding on a 7, and stealing."""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game.validation import (
    InvalidPayload,
    clean_card_counts,
    require_str,
)
from state import (
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
)

logger = logging.getLogger(__name__)


@socketio.on('move_robber')
def handle_move_robber(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        hex_key = require_str(data.get('hex'), 'hex')
    except InvalidPayload:
        return

    result = session.game.move_robber(name, hex_key)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    logger.info(f"Player {name} moved robber to {hex_key}")

    if result['victims']:
        emit('choose_victim', {'victims': result['victims']})

    bump_and_broadcast()

@socketio.on('discard_resources')
def handle_discard_resources(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        # Commodities count toward the limit a 7 enforces, so the discard has
        # to be able to name them too — and oil on an Oil Springs table.
        resources = clean_card_counts(
            data.get('resources'), allow_oil=session.game.rules['oil_tokens'])
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with session.lock:
        result = session.game.discard(name, resources)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("discard player=%s resources=%s", name, resources)
        log_event('trade', f"{name} discarded {sum(resources.values())} cards", player=name)
        socketio.emit('discard_completed', {'player': name})
        bump_and_broadcast()

@socketio.on('choose_robber_victim')
def handle_choose_robber_victim(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        victim_name = require_str(data.get('victim'), 'victim')
    except InvalidPayload:
        return

    result = session.game.steal_from_victim(name, victim_name)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    stolen = result['stolen']
    if stolen:
        logger.info("steal thief=%s victim=%s", name, victim_name)
        log_event('robber', f"{name} stole a card from {victim_name}", player=name)
        # Which resource moved is known only to the thief and the victim. The
        # table sees that a steal happened, not what it was.
        for sid, viewer in list(session.viewers.items()):
            payload = {'player': name, 'victim': victim_name}
            if viewer in (name, victim_name):
                payload['resource'] = stolen
            emit('resource_stolen', payload, to=sid)

    bump_and_broadcast()
