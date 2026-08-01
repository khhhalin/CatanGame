"""The robber: moving it, discarding on a 7, and stealing."""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game.validation import (
    InvalidPayload,
    clean_resource_counts,
    require_str,
)
from state import (
    bump_and_broadcast,
    game_lock,
    log_event,
    rate_limited,
    reject,
    socket_viewers,
)

logger = logging.getLogger(__name__)


@socketio.on('move_robber')
def handle_move_robber(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    # Can't move robber during setup
    if state.current_game.game_phase == "setup":
        reject('WRONG_PHASE', 'Cannot move robber during setup')
        return
    
    # Check if player must move robber
    if not state.current_game.must_move_robber:
        reject('WRONG_PHASE', 'You do not need to move the robber')
        return
    
    name = data.get('name', '')
    hex_key = data.get('hex', '')
    
    if not name or not hex_key:
        return
    
    # Check if it's this player's turn
    current_player = state.current_game.players[state.current_game.current_player_index]
    if current_player.name != name:
        reject('NOT_YOUR_TURN', f'Only {current_player.name} can move the robber')
        return
    
    # Check if hex exists and is not ocean
    if hex_key not in state.current_game.hexes:
        reject('INVALID_TARGET', 'Invalid hex')
        return
    
    hex_obj = state.current_game.hexes[hex_key]
    if hex_obj.type == 'ocean':
        reject('INVALID_TARGET', 'Cannot place robber on ocean')
        return

    # Friendly Robber, when enabled, protects anyone still on 2 victory points.
    if not state.current_game.robber_is_allowed(hex_key):
        reject('FRIENDLY_ROBBER',
               'Friendly Robber: that hex touches a settlement of a player on '
               '2 victory points. Pick another hex.')
        return

    # Move robber
    state.current_game.robber_hex = hex_key
    state.current_game.must_move_robber = False
    
    logger.info(f"Player {name} moved robber to {hex_key}")
    
    # Check for victims adjacent to new robber position
    victims = state.current_game.get_robber_victims()
    logger.info(f"Victims found near robber hex {hex_key}: {victims}")
    
    # Exclude current player from victims (can't rob yourself)
    if name in victims:
        victims.remove(name)
    
    logger.info(f"Victims after removing self: {victims}")
    
    current_player = state.current_game.players[state.current_game.current_player_index]
    
    if victims:
        state.current_game.must_choose_victim = True
        state.current_game.robber_victims = victims
        emit('choose_victim', {
            'victims': victims
        })
    
    # Broadcast updated board
    bump_and_broadcast()

@socketio.on('discard_resources')
def handle_discard_resources(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    try:
        name = require_str(data.get('name'), 'name')
        resources = clean_resource_counts(data.get('resources'))
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with game_lock:
        if name not in state.current_game.players_needing_discard:
            reject('WRONG_PHASE', 'You do not need to discard')
            return

        if not state.current_game.discard_resources(name, resources):
            reject('INVALID_PAYLOAD', 'Invalid discard amount or resources')
            return

        logger.info("discard player=%s resources=%s", name, resources)
        log_event('trade', f"{name} discarded {sum(resources.values())} cards", player=name)
        socketio.emit('discard_completed', {'player': name})
        bump_and_broadcast()

@socketio.on('choose_robber_victim')
def handle_choose_robber_victim(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    if not state.current_game.must_choose_victim:
        reject('WRONG_PHASE', 'No victim selection required')
        return
    
    name = data.get('name', '')
    victim_name = data.get('victim', '')
    
    if not name or not victim_name:
        return
    
    current_player = state.current_game.players[state.current_game.current_player_index]
    if current_player.name != name:
        reject('NOT_YOUR_TURN', f'Only {current_player.name} can choose victim')
        return
    
    if victim_name not in state.current_game.robber_victims:
        reject('INVALID_TARGET', 'Invalid victim selection')
        return
    
    stolen = state.current_game.steal_resource(victim_name, name)
    
    state.current_game.must_choose_victim = False
    state.current_game.robber_victims = []
    
    if stolen:
        logger.info("steal thief=%s victim=%s", name, victim_name)
        log_event('robber', f"{name} stole a card from {victim_name}", player=name)
        # Which resource moved is known only to the thief and the victim. The
        # table sees that a steal happened, not what it was.
        for sid, viewer in list(socket_viewers.items()):
            payload = {'player': name, 'victim': victim_name}
            if viewer in (name, victim_name):
                payload['resource'] = stolen
            emit('resource_stolen', payload, to=sid)

    bump_and_broadcast()
