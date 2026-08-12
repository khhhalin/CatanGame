"""Traders & Barbarians (The Fishermen of Catan) actions: spending fish tokens
for a benefit, and passing the old boot.

Each handler is the thin socket wrapper the engine's Fishermen methods were
written for — rate-limit, confirm the table agreed to the rule, confirm the
sender holds the seat it claims, validate the payload, take the lock, call the
engine method, and broadcast. The engine decides every rule; nothing here does.
Registered by importing this module in app.py, like every other handler.
"""

import logging

from extensions import socketio
from game.fishing import FISH_BENEFITS
from game.validation import InvalidPayload, require_str
from state import (
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
)

from handlers.phases import blocked_by_phase
from handlers.ships import _started_game

logger = logging.getLogger(__name__)


def _actor_for(rule_id, data):
    """Shared preamble: rate-limit, rule gate, seat, and the turn phase. Returns
    (session, name), or None once any of them has refused."""
    if rate_limited():
        return None
    session = _started_game(rule_id)
    if session is None:
        return None
    name = require_actor(data)
    if name is None:
        return None
    if blocked_by_phase(name):
        return None
    return session, name


@socketio.on('spend_fish')
def handle_spend_fish(data):
    got = _actor_for('fish_tokens', data)
    if got is None:
        return
    session, name = got
    try:
        benefit = require_str(data.get('benefit'), 'benefit')
    except InvalidPayload:
        return
    if benefit not in FISH_BENEFITS:
        reject('INVALID_PAYLOAD', f'No such fish benefit: {benefit!r}')
        return

    tokens = data.get('tokens')
    if not isinstance(tokens, list) or not tokens \
            or any(not isinstance(t, int) or isinstance(t, bool) for t in tokens):
        reject('INVALID_PAYLOAD', 'Spend a list of fish tokens')
        return

    # The two benefits that name another party. Left as None otherwise, which the
    # engine ignores for the benefits that take no target.
    target = data.get('target') if isinstance(data.get('target'), str) else None
    resource = data.get('resource') if isinstance(data.get('resource'), str) else None

    with session.lock:
        result = session.game.spend_fish(name, benefit, tokens,
                                         target=target, resource=resource)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} spent fish for {benefit}", player=name)
        bump_and_broadcast()


@socketio.on('pass_old_boot')
def handle_pass_old_boot(data):
    got = _actor_for('old_boot', data)
    if got is None:
        return
    session, name = got
    try:
        target = require_str(data.get('target'), 'target')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.pass_old_boot(name, target)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} passed the old boot to {target}", player=name)
        bump_and_broadcast()


# --- The Rivers of Catan: bridges and the gold-coin economy ------------------

@socketio.on('build_bridge')
def handle_build_bridge(data):
    got = _actor_for('bridges', data)
    if got is None:
        return
    session, name = got
    try:
        edge_key = require_str(data.get('edge'), 'edge')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.build_bridge(name, edge_key)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} built a bridge", player=name)
        bump_and_broadcast()


# --- The Caravans: bidding in the camel voting round -------------------------

@socketio.on('bid_camel')
def handle_bid_camel(data):
    got = _actor_for('caravans', data)
    if got is None:
        return
    session, name = got
    cards = data.get('cards')
    if not isinstance(cards, list) \
            or any(not isinstance(card, str) for card in cards):
        reject('INVALID_PAYLOAD', 'A bid is a list of wool and grain cards')
        return
    with session.lock:
        result = session.game.bid_camel(name, cards)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} bid {len(cards)} card(s) for the camel", player=name)
        bump_and_broadcast()


@socketio.on('buy_resource_with_coins')
def handle_buy_resource_with_coins(data):
    got = _actor_for('gold_coins', data)
    if got is None:
        return
    session, name = got
    try:
        resource = require_str(data.get('resource'), 'resource')
    except InvalidPayload:
        return
    with session.lock:
        # The 2-gold-buys-1-resource action is shared with Explorers & Pirates
        # gold; the engine method serves either economy.
        result = session.game.buy_resource_with_gold(name, resource)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} bought {resource} with gold coins", player=name)
        bump_and_broadcast()


@socketio.on('sell_resources_for_coins')
def handle_sell_resources_for_coins(data):
    got = _actor_for('gold_coins', data)
    if got is None:
        return
    session, name = got
    try:
        resource = require_str(data.get('resource'), 'resource')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.sell_resources_for_gold_coins(name, resource)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} bought a gold coin with {resource}", player=name)
        bump_and_broadcast()


# --- Barbarian Attack: the scenario deck and the castle knights --------------

@socketio.on('buy_barbarian_card')
def handle_buy_barbarian_card(data):
    got = _actor_for('barbarian_attack_deck', data)
    if got is None:
        return
    session, name = got
    with session.lock:
        result = session.game.buy_barbarian_card(name)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} revealed a {result['card']} card", player=name)
        bump_and_broadcast()


@socketio.on('place_barbarian_knight')
def handle_place_barbarian_knight(data):
    got = _actor_for('barbarian_attack', data)
    if got is None:
        return
    session, name = got
    try:
        edge_key = require_str(data.get('edge'), 'edge')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.place_barbarian_knight(name, edge_key)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} placed a knight", player=name)
        bump_and_broadcast()


@socketio.on('move_barbarian_knight')
def handle_move_barbarian_knight(data):
    got = _actor_for('barbarian_attack', data)
    if got is None:
        return
    session, name = got
    try:
        from_edge = require_str(data.get('from'), 'from')
        to_edge = require_str(data.get('to'), 'to')
    except InvalidPayload:
        return
    pay_grain = bool(data.get('pay_grain'))
    with session.lock:
        result = session.game.move_barbarian_knight(name, from_edge, to_edge,
                                                     pay_grain=pay_grain)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} moved a knight", player=name)
        bump_and_broadcast()
