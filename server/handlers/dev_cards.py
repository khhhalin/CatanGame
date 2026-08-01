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
    game_lock,
    rate_limited,
    reject,
)

logger = logging.getLogger(__name__)


@socketio.on('buy_dev_card')
def handle_buy_dev_card(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    if state.current_game.game_phase == "setup":
        reject('WRONG_PHASE', 'Cannot buy development cards during setup')
        return
    
    if state.current_game.must_move_robber:
        reject('MUST_MOVE_ROBBER', 'You must move the robber first')
        return
    
    name = data.get('name', '')
    
    if not name:
        return
    
    current_player = state.current_game.players[state.current_game.current_player_index]
    if current_player.name != name:
        reject('NOT_YOUR_TURN', f'Only {current_player.name} can buy development cards')
        return
    
    result = state.current_game.buy_dev_card(name)
    
    if result.get('success'):
        # Which card was drawn goes to the buyer alone; everyone else learns
        # only that the deck shrank, via the board update.
        emit('dev_card_bought', {
            'card_type': result.get('card_type'),
            'player': name
        })
        bump_and_broadcast()
    else:
        reject('ACTION_FAILED', result.get('error', 'Failed to buy development card'))

@socketio.on('play_dev_card')
def handle_play_dev_card(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    if state.current_game.game_phase == "setup":
        reject('WRONG_PHASE', 'Cannot play development cards during setup')
        return
    
    try:
        name = require_str(data.get('name'), 'name')
        card_type = require_choice(data.get('card_type'), 'card_type', DEV_CARD_TYPES)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    current_player = state.current_game.players[state.current_game.current_player_index]
    if current_player.name != name:
        reject('NOT_YOUR_TURN', f'Only {current_player.name} can play development cards')
        return
    
    # Check if card can be played (dice rolled + one turn delay)
    # Exception: Knight can be played even if must_move_robber is already true (to reassign robber)
    if card_type != 'knight':
        if state.current_game.must_move_robber:
            reject('MUST_MOVE_ROBBER', 'You must move the robber first')
            return
    
    can_play, error_msg = state.current_game.can_play_dev_card(name, card_type)
    if not can_play:
        reject('ACTION_REJECTED', error_msg)
        return
    
    player = state.current_game.get_player(name)
    player.dev_cards[card_type]['count'] -= 1
    
    # Handle Knight card effect - move robber
    if card_type == 'knight':
        state.current_game.must_move_robber = True
        player.knights_played += 1
        state.current_game.update_largest_army()
        logger.info(f"Player {name} played Knight - must move robber")
    
    # Handle Victory Point card effect - add to player's VP
    elif card_type == 'victory_point':
        player.victory_points += 1
        logger.info(f"Player {name} played Victory Point - now has {player.victory_points} VP")
        
        # Check for victory condition
        vp = state.current_game.victory_points_for(name)
        if vp >= state.current_game.victory_points_to_win:
            socketio.emit('game_won', {'player': name, 'victory_points': vp})
            logger.info(f"GAME OVER! {name} wins with {vp} victory points!")
            state.current_game.game_state = "finished"
            return
    
    # Handle Invention card effect - prompt for resources
    elif card_type == 'invention':
        # Record who is owed the follow-up. Without this, use_invention is a
        # free action any client can call without ever holding the card.
        state.current_game.pending_invention = name
        logger.info(f"Player {name} played Invention - waiting for resource selection")
        socketio.emit('dev_card_played', {
            'card_type': card_type,
            'player': name,
            'needs_resources': True
        })
        bump_and_broadcast()
        return
    
    # Handle Two Roads card effect - free roads
    elif card_type == 'two_roads':
        state.current_game.free_roads_remaining = 2
        logger.info(f"Player {name} played Two Roads - 2 free roads")
    
    # Handle Monopoly card effect - prompt for resource
    elif card_type == 'monopoly':
        state.current_game.pending_monopoly = name
        logger.info(f"Player {name} played Monopoly - waiting for resource selection")
        socketio.emit('dev_card_played', {
            'card_type': card_type,
            'player': name,
            'needs_resource': True
        })
        bump_and_broadcast()
        return

    logger.info(f"Player {name} played {card_type}")

    socketio.emit('dev_card_played', {
        'card_type': card_type,
        'player': name,
        'must_move_robber': state.current_game.must_move_robber if card_type == 'knight' else False
    })
    
    bump_and_broadcast()

@socketio.on('use_invention')
def handle_use_invention(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    try:
        name = require_str(data.get('name'), 'name')
        # Invention grants exactly two cards, so the whole request is bounded
        # here rather than trusting the client to ask for a sane amount.
        resources = clean_resource_counts(data.get('resources'), total_max=2)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with game_lock:
        # The card grants the right to this follow-up; without the pending flag
        # anyone could call it at any time and drain the bank.
        if state.current_game.pending_invention != name:
            reject('NO_PENDING_INVENTION', 'You have not played an Invention card')
            return

        if sum(resources.values()) != 2:
            reject('INVALID_PAYLOAD', 'Invention gives exactly 2 resources')
            return

        player = state.current_game.get_player(name)
        if not player:
            reject('INVALID_TARGET', 'Unknown player')
            return

        taken = {}
        for resource_type, count in resources.items():
            for _ in range(count):
                if state.current_game.bank.take(resource_type):
                    player.resources[resource_type] = player.resources.get(resource_type, 0) + 1
                    taken[resource_type] = taken.get(resource_type, 0) + 1

        state.current_game.pending_invention = None
        logger.info("invention player=%s received=%s", name, taken)
        bump_and_broadcast()

@socketio.on('use_monopoly')
def handle_use_monopoly(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    try:
        name = require_str(data.get('name'), 'name')
        resource_type = require_choice(data.get('resource_type'), 'resource_type', RESOURCE_TYPES)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with game_lock:
        if state.current_game.pending_monopoly != name:
            reject('NO_PENDING_MONOPOLY', 'You have not played a Monopoly card')
            return

        result = state.current_game.use_monopoly(name, resource_type)
        state.current_game.pending_monopoly = None

        if result.get('success'):
            logger.info("monopoly player=%s took %s %s from %s", name,
                        result['stolen_count'], resource_type, result['stolen_from'])

        bump_and_broadcast()
