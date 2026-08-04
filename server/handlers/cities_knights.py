"""Cities & Knights actions: improvements, knights, city walls, progress cards."""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game import progress_cards
from game import rules as rules_module
from game.cities_knights import COMMODITY_TYPES, IMPROVEMENT_TRACKS
from game.validation import (
    RESOURCE_TYPES,
    InvalidPayload,
    require_choice,
    require_int,
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

from handlers.phases import blocked_by_phase

logger = logging.getLogger(__name__)


def _rule_is_off(game, rule_id: str) -> bool:
    """Reject and report when the table never agreed to this rule."""
    if game.rules[rule_id]:
        return False
    name = rules_module.RULES_BY_ID[rule_id]['name']
    reject('RULE_NOT_IN_PLAY', f'"{name}" is not one of this table\'s rules')
    return True


def _ck_action(data, rule_id, method_name, *extra_keys):
    """Shared plumbing for the Cities & Knights actions.

    They all look the same: validate the payload, check it is that player's
    turn, call one engine method under the lock, then broadcast. Doing it once
    keeps the six handlers below to their actual rules. `rule_id` is the house
    rule this action needs, so a table that did not take it is told which one.
    """
    session = state.session()
    if session.game is None or session.game.game_state != "started":
        return None
    if _rule_is_off(session.game, rule_id):
        return None

    name = require_actor(data)
    if name is None:
        return None

    try:
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
    outcome = _ck_action(data, 'city_improvements', 'buy_improvement', 'track')
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
    outcome = _ck_action(data, 'knights', 'build_knight', 'vertex')
    if outcome:
        log_event('build', f"{outcome[0]} built a knight", player=outcome[0])

@socketio.on('activate_knight')
def handle_activate_knight(data):
    if rate_limited():
        return
    outcome = _ck_action(data, 'knights', 'activate_knight', 'vertex')
    if outcome:
        log_event('build', f"{outcome[0]} activated a knight", player=outcome[0])

@socketio.on('promote_knight')
def handle_promote_knight(data):
    if rate_limited():
        return
    outcome = _ck_action(data, 'knights', 'promote_knight', 'vertex')
    if outcome:
        log_event('build', f"{outcome[0]} promoted a knight", player=outcome[0])

@socketio.on('move_knight')
def handle_move_knight(data):
    if rate_limited():
        return
    outcome = _ck_action(data, 'knights', 'move_knight', 'from_vertex', 'to_vertex')
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
    outcome = _ck_action(data, 'city_walls', 'build_city_wall', 'vertex')
    if outcome:
        log_event('build', f"{outcome[0]} built a city wall", player=outcome[0])

# What each `needs_target` vocabulary word means on the wire. Validated here so
# the engine is handed a value of the right shape and never a raw payload.
_SINGLE_KEY_TARGETS = {'vertex': 'vertex', 'hex': 'hex', 'road': 'road'}
_LIST_TARGETS = {'knight': 'knights', 'two_number_tokens': 'hexes'}

# Road Building names a road target on the card, but the two roads are placed
# through the ordinary place_road flow afterwards, so nothing is chosen with the
# card itself.
_TARGET_CHOSEN_LATER = frozenset({'road_building'})


def _progress_target(card, data):
    """Pull this card's target out of the payload, or raise InvalidPayload.

    Returns None for a card that needs no extra input.
    """
    needs = card['needs_target']
    if needs is None or card['id'] in _TARGET_CHOSEN_LATER:
        return None

    if needs == 'resource':
        return require_choice(data.get('target'), 'target', RESOURCE_TYPES)
    if needs == 'commodity':
        return require_choice(data.get('target'), 'target', COMMODITY_TYPES)
    if needs == 'improvement':
        return require_choice(data.get('target'), 'target', tuple(IMPROVEMENT_TRACKS))
    if needs in _SINGLE_KEY_TARGETS:
        return require_str(data.get('target'), _SINGLE_KEY_TARGETS[needs])

    if needs == 'player':
        # Only that it is a name; whether it is a player at this table, and one
        # this card may be aimed at, is the engine's to decide.
        return require_str(data.get('target'), 'player')

    if needs == 'dice':
        raw = data.get('target')
        if not isinstance(raw, list) or len(raw) != 2:
            raise InvalidPayload('INVALID_PAYLOAD', 'target must be two die values')
        return [require_int(value, 'die', minimum=1, maximum=6) for value in raw]

    if needs in _LIST_TARGETS:
        raw = data.get('target')
        if not isinstance(raw, list) or not 1 <= len(raw) <= 2:
            raise InvalidPayload('INVALID_PAYLOAD', 'target must be a list of one or two keys')
        return [require_str(item, _LIST_TARGETS[needs]) for item in raw]

    # 'resource_or_commodity' belongs to Merchant Fleet, which the engine
    # cannot resolve yet; play_progress_card refuses it by name.
    raise InvalidPayload('NOT_IMPLEMENTED', f"{card['name']} cannot be played yet")


@socketio.on('play_progress_card')
def handle_play_progress_card(data):
    """Play one progress card from the sender's hand."""
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return
    if _rule_is_off(session.game, 'progress_cards'):
        return

    name = require_actor(data)
    if name is None:
        return

    try:
        card_id = require_choice(
            data.get('card'), 'card', tuple(progress_cards.CARDS_BY_ID)
        )
        target = _progress_target(progress_cards.CARDS_BY_ID[card_id], data)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with session.lock:
        current_player = session.game.players[session.game.current_player_index]
        if current_player.name != name:
            reject('NOT_YOUR_TURN', f'Only {current_player.name} can do that')
            return
        if blocked_by_phase(name):
            return

        result = session.game.play_progress_card(name, card_id, target)
        if not result.get('success'):
            reject('ACTION_REJECTED', result.get('error', 'That is not allowed'))
            return

        card_name = progress_cards.CARDS_BY_ID[card_id]['name']
        logger.info("progress card player=%s card=%s result=%s", name, card_id, result)
        log_event('build', f"{name} played {card_name}", player=name)
        socketio.emit('progress_card_played', {'player': name, 'card': card_id})
        # Several cards ask somebody — often an opponent — to decide something
        # before they finish resolving.
        announce_choices()
        bump_and_broadcast()


@socketio.on('request_progress_hand')
def handle_request_progress_hand(data):
    """Send the sender their own progress cards. Never anyone else's."""
    session = state.session()
    if rate_limited():
        return
    if session.game is None or not session.game.rules['progress_cards']:
        return

    # The sender's own hand, and only ever theirs: the cards are the whole
    # point of the secrecy, so the name is the socket's seat, not the payload's.
    name = require_actor(data)
    if name is None:
        return

    emit('progress_hand', {'player': name, 'cards': list(session.game.ck.hand_of(name))})
