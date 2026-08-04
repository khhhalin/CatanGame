"""Player and bank trading."""

import logging

import state
from extensions import socketio
from game.validation import (
    InvalidPayload,
    clean_resource_counts,
)
from state import (
    bump_and_broadcast,
    rate_limited,
    reject,
    require_actor,
)

from handlers.phases import blocked_by_phase

logger = logging.getLogger(__name__)


@socketio.on('propose_trade')
def handle_propose_trade(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        offered = clean_resource_counts(data.get('offered'), 'offered')
        wanted = clean_resource_counts(data.get('wanted'), 'wanted')
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    # 1 ore for 1 ore is not a trade. Any overlap between the two sides is the
    # same nonsense in a longer form — the shared part cancels out, so what is
    # really being offered is not what the table (or the bank rate) is shown.
    overlap = sorted(set(offered) & set(wanted))
    if overlap:
        reject(
            'INVALID_TRADE',
            f"You cannot trade {' or '.join(overlap)} for itself",
        )
        return

    if blocked_by_phase(name):
        return

    logger.info("trade proposed by=%s offered=%s wanted=%s", name, offered, wanted)

    result = session.game.propose_trade(name, offered, wanted)
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
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    offer_id = data.get('offer_id', 0)

    if name is None or not offer_id:
        return

    result = session.game.accept_trade(offer_id, name)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    logger.info(f"Player {name} accepted trade #{offer_id}")
    socketio.emit('trade_accepted', {'offer_id': offer_id, 'player': name})
    bump_and_broadcast()


@socketio.on('decline_trade')
def handle_decline_trade(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    offer_id = data.get('offer_id', 0)

    if name is None or not offer_id:
        return

    if session.game.decline_trade(offer_id, name):
        logger.info(f"Player {name} declined trade #{offer_id}")
        socketio.emit('trade_declined', {'offer_id': offer_id, 'player': name})


@socketio.on('cancel_trade')
def handle_cancel_trade(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    offer_id = data.get('offer_id', 0)

    if name is None or not offer_id:
        return

    if session.game.cancel_trade(offer_id, name):
        logger.info(f"Player {name} cancelled trade #{offer_id}")
        socketio.emit('trade_cancelled', {'offer_id': offer_id})
        bump_and_broadcast()


@socketio.on('complete_trade')
def handle_complete_trade(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    offer_id = data.get('offer_id', 0)
    selected_responder = data.get('selected_responder', None)

    if name is None or not offer_id:
        return

    result = session.game.complete_trade(offer_id, name, selected_responder)
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
