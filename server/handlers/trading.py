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

    try:
        name = require_str(data.get('name'), 'name')
        offered = clean_resource_counts(data.get('offered'), 'offered')
        wanted = clean_resource_counts(data.get('wanted'), 'wanted')
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    logger.info("trade proposed by=%s offered=%s wanted=%s", name, offered, wanted)

    result = state.current_game.propose_trade(name, offered, wanted)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    if result['kind'] == 'bank':
        rate = result['rate_used']
        logger.info(
            "bank trade player=%s offered=%s wanted=%s rate=%s", name, offered, wanted, rate
        )
        socketio.emit(
            'bank_trade_completed', {'offered': offered, 'wanted': wanted, 'rate_used': rate}
        )
    else:
        offer = result['offer']
        logger.info("trade offer created id=%s by=%s", offer['id'], name)
        socketio.emit('trade_proposed', {'offer': offer})

    # Everyone's trade list changes either way, so the board goes out in both
    # branches.
    bump_and_broadcast()


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

    result = state.current_game.accept_trade(offer_id, name)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    logger.info(f"Player {name} accepted trade #{offer_id}")
    socketio.emit('trade_accepted', {'offer_id': offer_id, 'player': name})
    bump_and_broadcast()


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
    if not result['success']:
        reject(result['code'], result['error'])
        return

    if result['type'] == 'bank':
        logger.info(f"Player {name} completed bank trade #{offer_id}")
        socketio.emit('trade_completed', {'offer_id': offer_id, 'type': 'bank'})
    else:
        responder = result['responder']
        logger.info(f"Player {name} completed trade #{offer_id} with {responder}")
        socketio.emit(
            'trade_completed', {'offer_id': offer_id, 'type': 'player', 'with': responder}
        )

    bump_and_broadcast()
