"""Buying and playing development cards."""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game.validation import (
    DEV_CARD_TYPES,
    RESOURCE_TYPES,
    InvalidPayload,
    clean_resource_counts,
    require_choice,
    require_str,
)
from state import (
    bump_and_broadcast,
    rate_limited,
    reject,
)

from handlers.phases import blocked_by_phase

logger = logging.getLogger(__name__)


@socketio.on('buy_dev_card')
def handle_buy_dev_card(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    try:
        name = require_str(data.get('name'), 'name')
    except InvalidPayload:
        return

    if blocked_by_phase(name):
        return

    result = session.game.buy_dev_card(name)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    # Which card was drawn goes to the buyer alone; everyone else learns
    # only that the deck shrank, via the board update.
    emit('dev_card_bought', {'card_type': result['card_type'], 'player': name})
    bump_and_broadcast()

@socketio.on('play_dev_card')
def handle_play_dev_card(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    try:
        name = require_str(data.get('name'), 'name')
        card_type = require_choice(data.get('card_type'), 'card_type', DEV_CARD_TYPES)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    if blocked_by_phase(name):
        return

    result = session.game.play_dev_card(name, card_type)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    logger.info(f"Player {name} played {card_type}")

    if result['won']:
        points = result['victory_points']
        socketio.emit('game_won', {'player': name, 'victory_points': points})
        logger.info(f"GAME OVER! {name} wins with {points} victory points!")
        return

    # Invention and Monopoly leave the player owing a declaration, and the
    # client opens a picker on these flags rather than on the card name.
    if result['needs_resources']:
        payload = {'card_type': card_type, 'player': name, 'needs_resources': True}
    elif result['needs_resource']:
        payload = {'card_type': card_type, 'player': name, 'needs_resource': True}
    else:
        payload = {
            'card_type': card_type,
            'player': name,
            'must_move_robber': result['must_move_robber'],
        }
    socketio.emit('dev_card_played', payload)

    bump_and_broadcast()

@socketio.on('use_invention')
def handle_use_invention(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    try:
        name = require_str(data.get('name'), 'name')
        # Invention grants exactly two cards, so the whole request is bounded
        # here rather than trusting the client to ask for a sane amount.
        resources = clean_resource_counts(data.get('resources'), total_max=2)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with session.lock:
        result = session.game.use_invention(name, resources)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("invention player=%s received=%s", name, result['taken'])
        bump_and_broadcast()

@socketio.on('use_monopoly')
def handle_use_monopoly(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    try:
        name = require_str(data.get('name'), 'name')
        resource_type = require_choice(data.get('resource_type'), 'resource_type', RESOURCE_TYPES)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with session.lock:
        result = session.game.use_monopoly(name, resource_type)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("monopoly player=%s took %s %s from %s", name,
                    result['stolen_count'], resource_type, result['stolen_from'])
        bump_and_broadcast()
