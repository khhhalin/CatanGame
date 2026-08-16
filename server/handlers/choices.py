"""Answering a pending choice — the one way out of the choice phase.

The engine records who owes a decision, of what kind, and exactly which options
it offered (`game/pending_choice.py`). This handler is the thin adapter: it
derives nothing from the payload that the server already knows, and hands the
engine three strings it re-checks against what it recorded.
"""

import logging

import state
from extensions import socketio
from game.pending_choice import KINDS
from game.validation import (
    InvalidPayload,
    require_choice,
    require_str,
)
from state import (
    announce_choices,
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
)

logger = logging.getLogger(__name__)


@socketio.on('make_choice')
def handle_make_choice(data):
    """Apply one player's answer to the decision the game is waiting on."""
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        kind = require_choice(data.get('kind'), 'kind', tuple(KINDS))
        option = require_str(data.get('option'), 'option', max_length=128)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with session.lock:
        result = session.game.resolve_choice(name, kind, option)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("choice player=%s kind=%s result=%s", name, kind, result)
        # What was chosen is public for the kinds where the board shows it
        # anyway; the option itself is not logged for the kinds where it is a
        # card out of somebody's hand.
        log_event('game', _story(name, result), player=name)
        socketio.emit('choice_resolved', {'player': name, 'kind': kind})

        # A resolver can open the next decision — a Master Merchant's second
        # card, the knight a Deserter's replacement stands on — so whoever owes
        # one now is told before the board goes out.
        announce_choices()
        bump_and_broadcast()


def _story(name: str, result: dict) -> str:
    """What the table is told about an answered choice.

    Deliberately not the option for the kinds where it is hidden information:
    that Alice took a card from Bob is public, which card it was is not.
    """
    kind = result['kind']
    if kind == 'barbarian_city':
        return f"{name} gave up a city to the barbarians"
    if kind == 'progress_deck':
        return f"{name} drew a {result['option']} progress card for the joint defence"
    if kind == 'commercial_harbor':
        return f"{name} traded a commodity at the commercial harbor"
    if kind == 'merchant_fleet':
        return (
            f"{name}'s merchant fleet trades {result['option']} "
            'with the bank at 2:1 for the rest of the turn'
        )
    if kind == 'master_merchant':
        return f"{name} took a card as Master Merchant"
    if kind == 'wedding':
        return f"{name} gave a card as a wedding gift"
    if kind == 'spy':
        return f"{name} took a progress card as Spy"
    if kind == 'deserter':
        return f"one of {name}'s knights deserted"
    if kind == 'camel_placement':
        return f"{name} placed the caravan's camel"
    if kind == 'intrigue_coast':
        return f"{name} spirited a barbarian off the coast as a prisoner"
    if kind == 'gift_harbor':
        return f"{name} placed a gift harbor from the Forgotten Tribe"
    if kind == 'gold_field_choice':
        return f"{name} took {result['option']} from a gold field"
    return f"{name} placed the deserting knight"
