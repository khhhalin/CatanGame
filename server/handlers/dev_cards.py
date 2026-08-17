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
)
from state import (
    bump_and_broadcast,
    rate_limited,
    reject,
    require_actor,
)

from handlers.building import announce_victory
from handlers.phases import blocked_by_phase

logger = logging.getLogger(__name__)


def _dev_cards_disabled(game) -> bool:
    """Whether this game uses development cards at all.

    Which system a table plays is the `card_system` rule's to say: progress
    cards replace development cards by default (expansions.md 303, 427), and
    only the house rule that runs both leaves the deck buyable alongside them.
    The engine refuses either way; this is here to answer the client before a
    turn's worth of other checks decide it was the wrong turn anyway.
    """
    if game.dev_deck_in_play():
        return False
    reject('DEV_CARDS_NOT_IN_PLAY', 'This table uses progress cards, not development cards')
    return True


@socketio.on('buy_dev_card')
def handle_buy_dev_card(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    if _dev_cards_disabled(session.game) or blocked_by_phase(name):
        return

    result = session.game.buy_dev_card(name)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    # Which card was drawn goes to the buyer alone; everyone else learns
    # only that the deck shrank, via the board update.
    emit('dev_card_bought', {'card_type': result['card_type'], 'player': name})
    # With "Victory Point cards count in hand" on, the card that was just drawn
    # can be the winning point, and there is no later action to notice it.
    announce_victory(name)
    bump_and_broadcast()

@socketio.on('play_dev_card')
def handle_play_dev_card(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        card_type = require_choice(data.get('card_type'), 'card_type', DEV_CARD_TYPES)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    # A card is the one thing that may be played before the dice, and which
    # cards those are is `can_play_dev_card`'s to say — the knight, and nothing
    # else. Gating the roll here would take that decision away from it.
    if _dev_cards_disabled(session.game) or blocked_by_phase(name, needs_roll=False):
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

    name = require_actor(data)
    if name is None:
        return

    try:
        # Invention grants exactly two cards, so the whole request is bounded
        # here rather than trusting the client to ask for a sane amount. Oil is a
        # legal choice on an Oil Springs table.
        resources = clean_resource_counts(
            data.get('resources'), total_max=2,
            allow_oil=session.game.rules['oil_tokens'])
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

    name = require_actor(data)
    if name is None:
        return

    try:
        # Oil is a legal monopoly target on an Oil Springs table.
        allowed = (RESOURCE_TYPES + ('oil',)
                   if session.game.rules['oil_tokens'] else RESOURCE_TYPES)
        resource_type = require_choice(data.get('resource_type'), 'resource_type', allowed)
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
