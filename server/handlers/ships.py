"""Seafarers actions: building and moving ships, and moving the pirate."""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game import rules as rules_module
from game.validation import (
    InvalidPayload,
    require_str,
)
from state import (
    announce_choices,
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
)

from handlers.building import announce_victory
from handlers.phases import blocked_by_phase

logger = logging.getLogger(__name__)


def _rule_is_off(game, rule_id: str) -> bool:
    """Reject and report when the table never agreed to this rule.

    The engine refuses these actions too; this is here so the player is told
    which rule is missing rather than being handed a bare refusal.
    """
    if game.rules[rule_id]:
        return False
    name = rules_module.RULES_BY_ID[rule_id]['name']
    reject('RULE_NOT_IN_PLAY', f'"{name}" is not one of this table\'s rules')
    return True


def _started_game(rule_id: str):
    """The live game if this action is possible at all, else None."""
    session = state.session()
    if session.game is None or session.game.game_state != "started":
        return None
    if _rule_is_off(session.game, rule_id):
        return None
    return session


@socketio.on('build_ship')
def handle_build_ship(data):
    if rate_limited():
        return
    session = _started_game('ships')
    if session is None:
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        edge_key = require_str(data.get('edge'), 'edge')
    except InvalidPayload:
        return

    if blocked_by_phase(name):
        return

    with session.lock:
        result = session.game.build_ship(name, edge_key)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("ship player=%s edge=%s", name, edge_key)
        log_event('build', f"{name} built a ship", player=name)
        _log_gift(name, result.get('gift'))
        # A gift harbour opens a placement choice; tell the player who owes it
        # before the board goes out.
        announce_choices()
        bump_and_broadcast()
        # A ship can complete the Longest Trade Route, and that card is worth
        # two points, so building one can end the game.
        announce_victory(name)


@socketio.on('move_ship')
def handle_move_ship(data):
    if rate_limited():
        return
    session = _started_game('ship_movement')
    if session is None:
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        from_edge = require_str(data.get('from_edge'), 'from_edge')
        to_edge = require_str(data.get('to_edge'), 'to_edge')
    except InvalidPayload:
        return

    if blocked_by_phase(name):
        return

    with session.lock:
        result = session.game.move_ship(name, from_edge, to_edge)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("ship moved player=%s from=%s to=%s", name, from_edge, to_edge)
        log_event('build', f"{name} moved a ship", player=name)
        _log_gift(name, result.get('gift'))
        announce_choices()
        bump_and_broadcast()
        # Moving a ship can hand over the Longest Trade Route, and that card is
        # worth two points, so it can end the game.
        announce_victory(name)


def _log_gift(name: str, gift):
    """Tell the table a Forgotten Tribe coast gift was claimed.

    What the gift *is* stays public for a chit and a harbour, which the board
    shows anyway; a drawn development card is announced only as "a gift", since
    which card it is stays secret exactly as a bought one does.
    """
    if not gift:
        return
    kind = gift['gift']
    if kind == 'victory_point':
        log_event('game', f"{name} claimed a victory point from the Forgotten Tribe", player=name)
    elif kind == 'dev_card':
        log_event('game', f"{name} received a development card from the Forgotten Tribe",
                  player=name)
    else:
        log_event('game', f"{name} received a harbor from the Forgotten Tribe", player=name)


@socketio.on('move_pirate')
def handle_move_pirate(data):
    if rate_limited():
        return
    session = _started_game('pirate')
    if session is None:
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        hex_key = require_str(data.get('hex'), 'hex')
    except InvalidPayload:
        return

    with session.lock:
        result = session.game.move_pirate(name, hex_key)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("pirate player=%s hex=%s", name, hex_key)
        log_event('robber', f"{name} moved the pirate", player=name)

        # The same choice the robber offers, resolved by the same handler.
        if result['victims']:
            emit('choose_victim', {'victims': result['victims']})

        bump_and_broadcast()
