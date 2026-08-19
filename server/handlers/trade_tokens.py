"""Catan for Two: spending and earning trade tokens.

The token economy lives in `game/trade_tokens.py`; these handlers are the thin
socket layer over it — validate the payload, call the engine method, broadcast.
"""

import logging

import state
from extensions import socketio
from game.validation import InvalidPayload, clean_card_counts, require_str
from state import (
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
)

logger = logging.getLogger(__name__)


@socketio.on("spend_trade_token")
def handle_spend_trade_token(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        action = require_str(data.get("action"), "action")
    except InvalidPayload:
        return

    with session.lock:
        if action == "move_robber":
            result = session.game.spend_trade_tokens_move_robber(name)
        elif action == "forced_trade":
            try:
                give = clean_card_counts(data.get("give"))
            except InvalidPayload as exc:
                reject(exc.code, exc.message)
                return
            result = session.game.spend_trade_tokens_forced_trade(name, give)
        else:
            reject("INVALID_TARGET", "Unknown trade-token action")
            return

        if not result["success"]:
            reject(result["code"], result["error"])
            return

    log_event("build", f"{name} spent trade tokens ({action})", player=name)
    bump_and_broadcast()


@socketio.on("discard_knight_for_tokens")
def handle_discard_knight_for_tokens(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    with session.lock:
        result = session.game.discard_knight_for_trade_tokens(name)
        if not result["success"]:
            reject(result["code"], result["error"])
            return

    log_event("build", f"{name} traded a knight for 2 trade tokens", player=name)
    bump_and_broadcast()
