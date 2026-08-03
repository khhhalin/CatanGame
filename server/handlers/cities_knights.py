"""Cities & Knights actions: improvements, knights and city walls."""

import logging

import state
from extensions import socketio
from game.validation import (
    InvalidPayload,
    require_str,
)
from state import (
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
)

from handlers.phases import blocked_by_phase

logger = logging.getLogger(__name__)


def _ck_action(data, method_name, *extra_keys):
    """Shared plumbing for the Cities & Knights actions.

    They all look the same: validate the payload, check it is that player's
    turn, call one engine method under the lock, then broadcast. Doing it once
    keeps the six handlers below to their actual rules.
    """
    session = state.session()
    if session.game is None or session.game.game_state != "started":
        return None
    if session.game.ck is None:
        reject('WRONG_MODE', 'Cities & Knights is not enabled for this game')
        return None

    try:
        name = require_str(data.get('name'), 'name')
        args = [require_str(data.get(key), key) for key in extra_keys]
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return None

    with session.lock:
        current_player = session.game.players[session.game.current_player_index]
        if current_player.name != name:
            reject('NOT_YOUR_TURN', f'Only {current_player.name} can do that')
            return None

        # None of these are legal while the robber or a discard is outstanding,
        # and the engine methods below carry no phase check of their own.
        if blocked_by_phase(name):
            return None

        result = getattr(session.game, method_name)(name, *args)
        if not result.get('success'):
            reject('ACTION_REJECTED', result.get('error', 'That is not allowed'))
            return None

        bump_and_broadcast()
        return name, result

@socketio.on('buy_improvement')
def handle_buy_improvement(data):
    if rate_limited():
        return
    """Advance one city improvement track by a level."""
    outcome = _ck_action(data, 'buy_improvement', 'track')
    if not outcome:
        return
    name, result = outcome

    track = data.get('track')
    log_event('build', f"{name} improved {track} to level {result['level']}", player=name)
    if result.get('metropolis'):
        taken = result.get('took_from')
        text = (f"{name} took the {track} metropolis from {taken}" if taken
                else f"{name} built the {track} metropolis")
        log_event('build', text, player=name)

@socketio.on('build_knight')
def handle_build_knight(data):
    if rate_limited():
        return
    outcome = _ck_action(data, 'build_knight', 'vertex')
    if outcome:
        log_event('build', f"{outcome[0]} built a knight", player=outcome[0])

@socketio.on('activate_knight')
def handle_activate_knight(data):
    if rate_limited():
        return
    outcome = _ck_action(data, 'activate_knight', 'vertex')
    if outcome:
        log_event('build', f"{outcome[0]} activated a knight", player=outcome[0])

@socketio.on('promote_knight')
def handle_promote_knight(data):
    if rate_limited():
        return
    outcome = _ck_action(data, 'promote_knight', 'vertex')
    if outcome:
        log_event('build', f"{outcome[0]} promoted a knight", player=outcome[0])

@socketio.on('move_knight')
def handle_move_knight(data):
    if rate_limited():
        return
    outcome = _ck_action(data, 'move_knight', 'from_vertex', 'to_vertex')
    if not outcome:
        return
    name, result = outcome
    if result.get('displaced'):
        log_event('build', f"{name} displaced {result['displaced']}'s knight", player=name)
    else:
        log_event('build', f"{name} moved a knight", player=name)

@socketio.on('build_city_wall')
def handle_build_city_wall(data):
    if rate_limited():
        return
    outcome = _ck_action(data, 'build_city_wall', 'vertex')
    if outcome:
        log_event('build', f"{outcome[0]} built a city wall", player=outcome[0])
