"""CATAN: New Energies actions: building a power plant, spending energy, and
demolishing a fossil plant.

Each handler is the thin socket wrapper the engine's New Energies methods were
written for — rate-limit, confirm the table agreed to the rule, confirm the
sender holds the seat it claims, take the lock, call the engine method, and
broadcast. The engine decides every rule; nothing here does. Registered by
importing this module in app.py, like every other handler.
"""

import logging

from extensions import socketio
from game.validation import InvalidPayload, require_str
from state import bump_and_broadcast, log_event, reject

from handlers.tb import _actor_for

logger = logging.getLogger(__name__)


@socketio.on('build_power_plant')
def handle_build_power_plant(data):
    got = _actor_for('power_plants', data)
    if got is None:
        return
    session, name = got
    try:
        vertex = require_str(data.get('vertex'), 'vertex')
        hex_key = require_str(data.get('hex'), 'hex')
        kind = require_str(data.get('kind'), 'kind')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.build_power_plant(name, vertex, hex_key, kind)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} built a {kind} power plant", player=name)
        bump_and_broadcast()


@socketio.on('spend_energy')
def handle_spend_energy(data):
    got = _actor_for('power_plants', data)
    if got is None:
        return
    session, name = got
    try:
        card = require_str(data.get('card'), 'card')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.spend_energy_for_card(name, card)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} spent energy for a {card} card", player=name)
        bump_and_broadcast()


@socketio.on('demolish_fossil_plant')
def handle_demolish_fossil_plant(data):
    got = _actor_for('global_footprint', data)
    if got is None:
        return
    session, name = got
    try:
        vertex = require_str(data.get('vertex'), 'vertex')
        hex_key = require_str(data.get('hex'), 'hex')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.demolish_fossil_plant(name, vertex, hex_key)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('build', f"{name} demolished a fossil power plant", player=name)
        bump_and_broadcast()
