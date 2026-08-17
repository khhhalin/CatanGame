"""Activating a helper tile.

The thin adapter over the engine's helper subsystem (game/helpers.py). It
bounds the untrusted payload - a tile id and a small, fixed set of optional
parameters - and hands them to the engine, which re-checks everything against
the tile the player actually holds and the state of the board. The mandatory
exchange-or-flip that follows a use is a pending choice, so it travels the
existing `make_choice` handler, not this one.
"""

import logging

import state
from extensions import socketio
from game.helper_tiles import HELPER_TILES_BY_ID
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

# The parameter keys any advantage may carry, each a bounded scalar. The engine
# re-validates every one against real state; this only keeps a payload sane.
_STR_PARAMS = ('resource', 'resource_out', 'target', 'from_edge', 'to_edge',
               'edge', 'dev_card', 'build', 'vertex',
               'substitute_from', 'substitute_with')
# List-valued parameters (e.g. Stina's several 2:1 receipts, Asla's two
# requests), each a short list of short strings.
_LIST_PARAMS = ('resources', 'targets', 'returns')


def _clean_params(raw: dict) -> dict:
    """A bounded copy of the activation parameters, or raise InvalidPayload."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise InvalidPayload('INVALID_PAYLOAD', 'params must be an object')
    cleaned: dict = {}
    for key in _STR_PARAMS:
        if raw.get(key) is not None:
            cleaned[key] = require_str(raw.get(key), key, max_length=64)
    for key in _LIST_PARAMS:
        value = raw.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or len(value) > 20 \
                or any(not isinstance(item, str) or len(item) > 64 for item in value):
            raise InvalidPayload('INVALID_PAYLOAD', f'{key} must be a short list of strings')
        cleaned[key] = value
    return cleaned


@socketio.on('activate_helper')
def handle_activate_helper(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        tile = require_choice(data.get('tile'), 'tile', tuple(HELPER_TILES_BY_ID))
        params = _clean_params(data.get('params'))
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with session.lock:
        result = session.game.activate_helper(name, tile, params)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("helper player=%s tile=%s result=%s", name, tile, result)
        log_event('game', f"{name} played the {HELPER_TILES_BY_ID[tile]['title']} helper",
                  player=name)
        socketio.emit('helper_activated', {'player': name, 'tile': tile})

        # Activation always opens the exchange-or-flip choice; tell whoever owes
        # a decision before the board goes out.
        announce_choices()
        bump_and_broadcast()
