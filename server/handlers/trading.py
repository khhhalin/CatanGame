"""Player and bank trading."""

import logging

import state
from extensions import socketio
from game.validation import (
    InvalidPayload,
    clean_card_counts,
    require_int,
)
from state import (
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
)

from handlers.phases import blocked_by_phase

logger = logging.getLogger(__name__)


def _cards_phrase(cards: dict) -> str:
    """"2 wheat and 1 ore" - what a player would say out loud."""
    parts = [f"{count} {card}" for card, count in sorted(cards.items()) if count]
    if not parts:
        return 'nothing'
    if len(parts) == 1:
        return parts[0]
    return ', '.join(parts[:-1]) + ' and ' + parts[-1]


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
        # Cards, not resources: commodities trade exactly as resources do
        # (`expansions.md` 329), so a payload naming cloth, coin or paper is
        # legal input. Anything outside those eight names still bounces.
        offered = clean_card_counts(data.get('offered'), 'offered')
        wanted = clean_card_counts(data.get('wanted'), 'wanted')
        # Gold rides its own scalars, not the resource dicts (a gold key inside
        # `offered` is still rejected by `clean_card_counts`). Absent on a
        # base-game payload, defaulting to 0; the engine gates any non-zero gold
        # on a gold rule being in play.
        offered_gold = require_int(data.get('offered_gold', 0), 'offered_gold')
        wanted_gold = require_int(data.get('wanted_gold', 0), 'wanted_gold')
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

    result = session.game.propose_trade(name, offered, wanted, offered_gold, wanted_gold)
    if not result['success']:
        reject(result['code'], result['error'])
        return

    if result['kind'] == 'bank':
        rate = result['rate_used']
        logger.info(
            "bank trade player=%s offered=%s wanted=%s rate=%s", name, offered, wanted, rate
        )
        # The shared log, not only the server's: cards left a hand, and until
        # now the history said nothing happened. The player-to-player branch
        # has always been visible; this one was not.
        log_event(
            'trade',
            f"{name} traded {_cards_phrase(offered)} to the bank "
            f"for {_cards_phrase(wanted)} at {rate}:1",
            player=name,
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
        # The refusal changes what every screen should show — the denier marked,
        # the offer gone once all responders decline — so the board goes out to
        # everyone, the same as an accept does. Without this the decline was
        # recorded but invisible ("deny nie jest responsywne").
        bump_and_broadcast()


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
