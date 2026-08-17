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

from handlers.building import announce_victory
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


# The optional resource choices a redemption carries: the traders' give/receive
# pair and the merchants' single resource. Read only when the guild needs them;
# the engine validates every one, so a missing or bad value is simply refused.
_FAVOUR_LABEL = {
    'trader': 'traded at the traders',
    'merchant': 'took a resource from the merchants',
    'road_builder': 'took a free road from the road builders',
    'scholar': 'drew a card from the scholars',
    'master_builder': 'took a Victory-Point marker from the master builders',
}


@socketio.on('redeem_favour')
def handle_redeem_favour(data):
    if rate_limited():
        return
    session = _started_game('guild_hall')
    if session is None:
        return
    name = require_actor(data)
    if name is None:
        return
    try:
        guild = require_str(data.get('guild'), 'guild')
    except InvalidPayload:
        return
    # The trader and merchant favours carry a resource choice; the rest ignore
    # these, and the engine refuses a bad one, so they are passed straight
    # through without a handler-side gate.
    kwargs = {}
    for key in ('give', 'receive', 'resource'):
        if isinstance(data, dict) and isinstance(data.get(key), str):
            kwargs[key] = data[key]
    with session.lock:
        result = session.game.redeem_favour(name, guild, **kwargs)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} {_FAVOUR_LABEL.get(guild, 'redeemed a favour')}", player=name)
        bump_and_broadcast()
        # A Victory-Point marker can win outright, so it is announced now rather
        # than held to the next roll (p. 2, the win comes on your own turn).
        announce_victory(name)


@socketio.on('exchange_favour')
def handle_exchange_favour(data):
    if rate_limited():
        return
    session = _started_game('guild_hall')
    if session is None:
        return
    name = require_actor(data)
    if name is None:
        return
    try:
        return_guild = require_str(data.get('return'), 'return')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.exchange_favour(name, return_guild)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} exchanged a favour token", player=name)
        bump_and_broadcast()
