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
