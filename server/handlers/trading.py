"""Player and bank trading."""

import logging

import state
from extensions import socketio
from game.validation import (
    InvalidPayload,
    clean_resource_counts,
    require_str,
)
from state import (
    bump_and_broadcast,
    rate_limited,
    reject,
)

logger = logging.getLogger(__name__)


@socketio.on('propose_trade')
def handle_propose_trade(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return

    # Check if player must move robber first
    if state.current_game.must_move_robber:
        reject('MUST_MOVE_ROBBER', 'You must move the robber first')
        return

    try:
        name = require_str(data.get('name'), 'name')
        offered = clean_resource_counts(data.get('offered'), 'offered')
        wanted = clean_resource_counts(data.get('wanted'), 'wanted')
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    if not offered or not wanted:
        reject('INVALID_PAYLOAD', 'A trade needs resources on both sides')
        return

    logger.info("trade proposed by=%s offered=%s wanted=%s", name, offered, wanted)

    # Check if it's this player's turn
    current_player = state.current_game.players[state.current_game.current_player_index]
    if current_player.name != name:
        reject('NOT_YOUR_TURN', f'Only {current_player.name} can propose trades on their turn')
        return

    # Check player has the offered resources
    player = state.current_game.get_player(name)
    if not player:
        reject('INVALID_TARGET', 'Unknown player')
        return

    for resource, count in offered.items():
        available = player.resources.get(resource, 0)
        if available < count:
            reject(
                'INSUFFICIENT_RESOURCES',
                f'Not enough {resource}: have {available}, offering {count}',
            )
            return

    # Check if this is a bank trade (check player's port-based ratio)
    offered_total = sum(offered.values())
    wanted_total = sum(wanted.values())
    ratio = offered_total / wanted_total if wanted_total > 0 else 0

    # Get player's ports to determine their trade rate
    player_ports = state.current_game.get_player_ports(name)
    generic_port = "generic" in player_ports
    resource_ports = {r for r in ["wood", "brick", "sheep", "wheat", "ore"] if r in player_ports}

    # Determine best trade rate for player
    # Check if player has 2:1 port for ANY resource they're offering
    # If yes, they can trade 2 of that resource for ANY resource
    best_rate = 4
    if generic_port:
        best_rate = 3

    # Check if player has a 2:1 port for any of the offered resources
    if offered_total > 0:
        for resource in offered.keys():
            if resource in resource_ports:
                best_rate = min(best_rate, 2)
                break

    if ratio >= best_rate:
        # Execute bank trade immediately
        logger.info(
            f"Auto-completing bank trade for {name}! Ratio: {ratio}:1 (best rate: {best_rate}:1)"
        )

        # Check the bank can cover the whole request before touching anything.
        # Mutating first and unwinding on failure previously left the player
        # holding whatever was granted before the shortfall.
        for resource, count in wanted.items():
            if state.current_game.bank.resources.get(resource, 0) < count:
                reject('BANK_EMPTY', f'Bank does not have {count} {resource}')
                return

        # Transfer resources from player to bank
        for resource, count in offered.items():
            player.resources[resource] = player.resources.get(resource, 0) - count
            state.current_game.bank.return_resources(resource, count)

        # Transfer resources from bank to player. take() removes one card per
        # call, so it must be called once per unit granted.
        for resource, count in wanted.items():
            state.current_game.bank.take(resource, count)
            player.resources[resource] = player.resources.get(resource, 0) + count

        logger.info(
            "bank trade player=%s offered=%s wanted=%s rate=%s", name, offered, wanted, best_rate
        )
        socketio.emit(
            'bank_trade_completed', {'offered': offered, 'wanted': wanted, 'rate_used': best_rate}
        )
        bump_and_broadcast()
    else:
        # Not a bank trade - create regular offer
        offer = state.current_game.propose_trade(name, offered, wanted)
        if offer:
            logger.info("trade offer created id=%s by=%s", offer['id'], name)
            socketio.emit('trade_proposed', {'offer': offer})
            # Also emit board_updated to refresh everyone's trade lists
            bump_and_broadcast()
        else:
            reject('TRADE_LIMIT', 'Maximum number of trade offers reached')


@socketio.on('accept_trade')
def handle_accept_trade(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return

    name = data.get('name', '')
    offer_id = data.get('offer_id', 0)

    if not name or not offer_id:
        return

    # Get offer first
    offer = state.current_game.trade_manager.offers.get(offer_id)
    if not offer:
        reject('TRADE_NOT_FOUND', 'Trade offer not found')
        return

    # Check player has the wanted resources (what the proposer wants)
    player = state.current_game.get_player(name)
    if not player:
        return

    for resource, count in offer['wanted_resources'].items():
        if player.resources.get(resource, 0) < count:
            reject('INSUFFICIENT_RESOURCES', f'Not enough {resource} to accept this trade')
            return

    if state.current_game.accept_trade(offer_id, name):
        logger.info(f"Player {name} accepted trade #{offer_id}")
        socketio.emit('trade_accepted', {'offer_id': offer_id, 'player': name})
        bump_and_broadcast()
    else:
        reject('TRADE_FAILED', 'Could not accept trade')


@socketio.on('decline_trade')
def handle_decline_trade(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return

    name = data.get('name', '')
    offer_id = data.get('offer_id', 0)

    if not name or not offer_id:
        return

    if state.current_game.decline_trade(offer_id, name):
        logger.info(f"Player {name} declined trade #{offer_id}")
        socketio.emit('trade_declined', {'offer_id': offer_id, 'player': name})


@socketio.on('cancel_trade')
def handle_cancel_trade(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return

    name = data.get('name', '')
    offer_id = data.get('offer_id', 0)

    if not name or not offer_id:
        return

    if state.current_game.cancel_trade(offer_id, name):
        logger.info(f"Player {name} cancelled trade #{offer_id}")
        socketio.emit('trade_cancelled', {'offer_id': offer_id})
        bump_and_broadcast()


@socketio.on('complete_trade')
def handle_complete_trade(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return

    name = data.get('name', '')
    offer_id = data.get('offer_id', 0)
    selected_responder = data.get('selected_responder', None)

    if not name or not offer_id:
        return

    result = state.current_game.complete_trade(offer_id, name, selected_responder)
    if not result:
        reject('TRADE_FAILED', 'Could not complete trade')
        return

    # Execute the trade
    if result['type'] == 'bank':
        state.current_game.execute_bank_trade(offer_id, name)
        logger.info(f"Player {name} completed bank trade #{offer_id}")
        socketio.emit('trade_completed', {'offer_id': offer_id, 'type': 'bank'})
    else:
        state.current_game.execute_trade_with_player(offer_id, name, result['responder'])
        logger.info(f"Player {name} completed trade #{offer_id} with {result['responder']}")
        socketio.emit(
            'trade_completed', {'offer_id': offer_id, 'type': 'player', 'with': result['responder']}
        )

    bump_and_broadcast()
