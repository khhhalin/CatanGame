"""Placing settlements, roads and cities."""

import logging

import state
from extensions import socketio
from game.validation import (
    InvalidPayload,
    require_str,
)
from game.wonders import WONDERS
from state import (
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
)

from handlers.phases import blocked_by_phase

logger = logging.getLogger(__name__)


def announce_victory(name):
    """Tell the table if that action just won the game."""
    session = state.session()
    points = session.game.claim_victory(name)
    if points is None:
        return
    socketio.emit('game_won', {'player': name, 'victory_points': points})
    logger.info(f"GAME OVER! {name} wins with {points} victory points!")

@socketio.on('place_settlement')
def handle_place_settlement(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        vertex_key = require_str(data.get('vertex'), 'vertex')
    except InvalidPayload:
        return

    if blocked_by_phase(name):
        return

    result = session.game.place_settlement(name, vertex_key)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    building_type = result['building_type']
    logger.info(f"Player {name} placed {building_type} at {vertex_key}")
    log_event('build', f"{name} built a {building_type}", player=name)

    bump_and_broadcast()
    announce_victory(name)

@socketio.on('place_road')
def handle_place_road(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
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

    result = session.game.build_road(name, edge_key)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    if result['used_free_road']:
        logger.info(f"Free road placed! Remaining: {session.game.free_roads_remaining}")

    logger.info("road player=%s edge=%s", name, edge_key)
    log_event('build', f"{name} built a road", player=name)

    bump_and_broadcast()
    # A road wins through Longest Road, which is worth 2 points. Every other
    # placement announced its win; this one left the table to notice.
    announce_victory(name)

@socketio.on('build_wonder_level')
def handle_build_wonder_level(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    # The Wonder to start, on the first level; ignored once one is under way.
    wonder = data.get('wonder')
    if wonder is not None and not isinstance(wonder, str):
        return

    if blocked_by_phase(name):
        return

    result = session.game.build_wonder_level(name, wonder)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    wonder_name = WONDERS[result['wonder']]['name']
    logger.info("wonder player=%s wonder=%s level=%s", name, result['wonder'], result['level'])
    log_event('build', f"{name} built the {wonder_name} to level {result['level']}", player=name)

    bump_and_broadcast()
    announce_victory(name)

@socketio.on('upgrade_city')
def handle_upgrade_city(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        vertex_key = require_str(data.get('vertex'), 'vertex')
    except InvalidPayload:
        return

    if blocked_by_phase(name):
        return

    result = session.game.upgrade_city(name, vertex_key)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    logger.info(f"Player {name} upgraded settlement to city at {vertex_key}")
    log_event('build', f"{name} upgraded a settlement to a city", player=name)

    bump_and_broadcast()
    announce_victory(name)
