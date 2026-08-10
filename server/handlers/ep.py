"""Explorers & Pirates actions: transport ships, the pirate ship, the three
missions, and gold trades.

Each handler is the thin socket wrapper the engine's E&P methods were written
for: rate-limit, confirm the table agreed to the rule, confirm the sender holds
the seat it claims, validate the payload, take the lock, call the engine method,
and broadcast. The engine decides every rule; nothing here does. Registered by
importing this module in app.py, like every other handler.
"""

import logging

from extensions import socketio
from flask_socketio import emit
from game.validation import InvalidPayload, require_int, require_str
from state import (
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
)

from handlers.building import announce_victory
from handlers.phases import blocked_by_phase
from handlers.ships import _started_game

logger = logging.getLogger(__name__)


def _actor_for(rule_id, data, *, phase_gated=True):
    """Shared preamble: rate-limit, rule gate, seat, and — for a turn action —
    the phase. Returns (session, name), or None once any of them has refused."""
    if rate_limited():
        return None
    session = _started_game(rule_id)
    if session is None:
        return None
    name = require_actor(data)
    if name is None:
        return None
    if phase_gated and blocked_by_phase(name):
        return None
    return session, name


def _apply(name, result, kind, log_msg, *, victory=False):
    """Common tail: refuse on failure, else log, broadcast, and — when the action
    can move a marker and so end the game — announce a win."""
    if not result['success']:
        reject(result['code'], result['error'])
        return
    log_event(kind, f"{name} {log_msg}", player=name)
    bump_and_broadcast()
    if victory:
        announce_victory(name)


# --- Transport ships ---------------------------------------------------------

@socketio.on('build_transport_ship')
def handle_build_transport_ship(data):
    got = _actor_for('transport_ships', data)
    if got is None:
        return
    session, name = got
    try:
        edge = require_str(data.get('edge'), 'edge')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.build_transport_ship(name, edge),
               'build', 'built a transport ship')


@socketio.on('move_transport_ship')
def handle_move_transport_ship(data):
    got = _actor_for('transport_ships', data)
    if got is None:
        return
    session, name = got
    try:
        from_edge = require_str(data.get('from_edge'), 'from_edge')
        to_edge = require_str(data.get('to_edge'), 'to_edge')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.move_transport_ship(name, from_edge, to_edge),
               'build', 'moved a transport ship')


@socketio.on('load_transport_ship')
def handle_load_transport_ship(data):
    got = _actor_for('transport_ships', data)
    if got is None:
        return
    session, name = got
    try:
        edge = require_str(data.get('edge'), 'edge')
        basin = require_int(data.get('basin_index'), 'basin_index')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.load_transport_ship(name, edge, basin),
               'build', 'loaded a transport ship')


@socketio.on('unload_transport_ship')
def handle_unload_transport_ship(data):
    got = _actor_for('transport_ships', data)
    if got is None:
        return
    session, name = got
    try:
        edge = require_str(data.get('edge'), 'edge')
        cargo = require_int(data.get('cargo_index'), 'cargo_index')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.unload_transport_ship(name, edge, cargo),
               'build', 'unloaded a transport ship')


# --- The pirate ship (on a roll of seven) ------------------------------------

@socketio.on('place_pirate_ship')
def handle_place_pirate_ship(data):
    # Not phase-gated: this resolves a roll of seven, where the robber would
    # otherwise move, so the engine does the turn and discard checks itself.
    got = _actor_for('pirate_ship_instead_of_robber', data, phase_gated=False)
    if got is None:
        return
    session, name = got
    try:
        hex_key = require_str(data.get('hex'), 'hex')
    except InvalidPayload:
        return
    with session.lock:
        result = session.game.place_pirate_ship(name, hex_key)
        if not result['success']:
            reject(result['code'], result['error'])
            return
        log_event('robber', f"{name} placed the pirate ship", player=name)
        # The same victim choice the robber offers, resolved by the same handler.
        if result['victims']:
            emit('choose_victim', {'victims': result['victims']})
        bump_and_broadcast()


# --- Pirate Lairs mission ----------------------------------------------------

@socketio.on('land_crews_on_lair')
def handle_land_crews_on_lair(data):
    got = _actor_for('mission_pirate_lairs', data)
    if got is None:
        return
    session, name = got
    try:
        ship_edge = require_str(data.get('ship_edge'), 'ship_edge')
        lair_hex = require_str(data.get('lair_hex'), 'lair_hex')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.land_crews_on_lair(name, ship_edge, lair_hex),
               'build', 'landed crews on a pirate lair', victory=True)


@socketio.on('pickup_crews_from_lair')
def handle_pickup_crews_from_lair(data):
    got = _actor_for('mission_pirate_lairs', data)
    if got is None:
        return
    session, name = got
    try:
        ship_edge = require_str(data.get('ship_edge'), 'ship_edge')
        lair_hex = require_str(data.get('lair_hex'), 'lair_hex')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.pickup_crews_from_lair(name, ship_edge, lair_hex),
               'build', 'picked crews up from a lair')


# --- Fish for Catan mission --------------------------------------------------

@socketio.on('roll_fish_haul')
def handle_roll_fish_haul(data):
    got = _actor_for('mission_fish', data)
    if got is None:
        return
    session, name = got
    with session.lock:
        _apply(name, session.game.roll_fish_haul(name),
               'build', 'rolled for a fish haul')


@socketio.on('catch_fish')
def handle_catch_fish(data):
    got = _actor_for('mission_fish', data)
    if got is None:
        return
    session, name = got
    try:
        ship_edge = require_str(data.get('ship_edge'), 'ship_edge')
        shoal_hex = require_str(data.get('shoal_hex'), 'shoal_hex')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.catch_fish(name, ship_edge, shoal_hex),
               'build', 'caught a fish haul')


@socketio.on('deliver_fish')
def handle_deliver_fish(data):
    got = _actor_for('mission_fish', data)
    if got is None:
        return
    session, name = got
    try:
        ship_edge = require_str(data.get('ship_edge'), 'ship_edge')
        council_hex = require_str(data.get('council_hex'), 'council_hex')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.deliver_fish(name, ship_edge, council_hex),
               'build', 'delivered a fish haul', victory=True)


# --- Spices for Catan mission ------------------------------------------------

@socketio.on('befriend_spice_village')
def handle_befriend_spice_village(data):
    got = _actor_for('mission_spices', data)
    if got is None:
        return
    session, name = got
    try:
        ship_edge = require_str(data.get('ship_edge'), 'ship_edge')
        spice_hex = require_str(data.get('spice_hex'), 'spice_hex')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.befriend_spice_village(name, ship_edge, spice_hex),
               'build', 'befriended a spice village')


@socketio.on('deliver_spices')
def handle_deliver_spices(data):
    got = _actor_for('mission_spices', data)
    if got is None:
        return
    session, name = got
    try:
        ship_edge = require_str(data.get('ship_edge'), 'ship_edge')
        council_hex = require_str(data.get('council_hex'), 'council_hex')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.deliver_spices(name, ship_edge, council_hex),
               'build', 'delivered spice sacks', victory=True)


# --- Gold trades -------------------------------------------------------------

@socketio.on('sell_resources_for_gold')
def handle_sell_resources_for_gold(data):
    got = _actor_for('gold', data)
    if got is None:
        return
    session, name = got
    try:
        resource = require_str(data.get('resource'), 'resource')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.sell_resources_for_gold(name, resource),
               'build', 'sold a resource for gold')


@socketio.on('buy_resource_with_gold')
def handle_buy_resource_with_gold(data):
    got = _actor_for('gold', data)
    if got is None:
        return
    session, name = got
    try:
        resource = require_str(data.get('resource'), 'resource')
    except InvalidPayload:
        return
    with session.lock:
        _apply(name, session.game.buy_resource_with_gold(name, resource),
               'build', 'bought a resource with gold')
