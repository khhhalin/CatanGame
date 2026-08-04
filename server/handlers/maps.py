"""The map editor's half of the wire: list, save, delete and preview a map.

Authorisation follows `set_rules`: anyone in the lobby may save, delete or
preview, and all of it is refused once a game is running. Author-matching was
considered and dropped — identity here is payload-based by design, so "only the
author may delete" would be theatre. The threat model is a misclick, and a
confirmation flag is the honest answer to a misclick.

A map payload is the most nested thing a client can send and it turns into a
filename, so nothing here trusts one: every entry point runs `parse_map` (which
bounds and allowlists everything) and then `validate_map`, in that order, before
the map reaches disk or a board.
"""

import logging
import random

import state
from extensions import socketio
from flask_socketio import emit
from game import map_store, maps
from game.game import Game
from state import (
    emit_rules,
    rate_limited,
    reject,
    viewer_for,
)

logger = logging.getLogger(__name__)


def _in_lobby() -> bool:
    """Whether editing is allowed at all right now.

    Same condition as the rules picker: the board is frozen once a game starts,
    and a map is part of the board.
    """
    game = state.session().game
    if game is not None and game.game_state == "started":
        reject('GAME_IN_PROGRESS', 'Maps cannot be edited once a game has started')
        return False
    if viewer_for() is None:
        reject('NOT_IN_LOBBY', 'Join before editing maps')
        return False
    return True


def _accepted(data) -> maps.MapDefinition:
    """A map from a client, parsed and validated, or None once refused."""
    try:
        defn = maps.parse_map((data or {}).get('map'))
    except maps.InvalidPayload as exc:
        reject(exc.code, exc.message)
        return None

    errors, _ = maps.validate_map(defn)
    if errors:
        # The first problem is the message; the whole list rides along so the
        # editor can point at every region at fault rather than one at a time.
        emit('error', {'code': 'INVALID_MAP', 'message': errors[0].message,
                       'details': {'problems': [problem.to_json() for problem in errors]}})
        return None
    return defn


@socketio.on('request_maps')
def handle_request_maps(data=None):
    if rate_limited():
        return
    emit('map_list', {'maps': map_store.list_maps()})


@socketio.on('save_map')
def handle_save_map(data=None):
    if rate_limited():
        return
    if not _in_lobby():
        return

    defn = _accepted(data)
    if defn is None:
        return

    try:
        map_store.write_map(defn.id, defn.to_json())
    except (map_store.ReadOnlyMap, map_store.UnknownMap) as exc:
        reject('MAP_READ_ONLY', str(exc))
        return

    logger.info("map %s saved by %s", defn.id, viewer_for())
    emit('map_saved', {'id': defn.id})
    socketio.emit('map_list', {'maps': map_store.list_maps()})
    # The picker's options come off disk, so the table only learns a new map
    # exists through the rules broadcast.
    emit_rules()


@socketio.on('delete_map')
def handle_delete_map(data=None):
    if rate_limited():
        return
    if not _in_lobby():
        return

    session = state.session()
    map_id = (data or {}).get('id')
    if not (data or {}).get('confirm'):
        reject('CONFIRM_REQUIRED', 'Deleting a map cannot be undone; confirm it')
        return
    if session.lobby_rules['board_layout'] == 'custom' \
            and session.lobby_rules['board_map'] == map_id:
        reject('MAP_IN_USE', 'This map is the one the table has chosen to play')
        return

    try:
        map_store.delete_map(map_id)
    except map_store.ReadOnlyMap as exc:
        reject('MAP_READ_ONLY', str(exc))
        return
    except map_store.UnknownMap as exc:
        reject('UNKNOWN_MAP', str(exc))
        return

    logger.info("map %s deleted by %s", map_id, viewer_for())
    emit('map_deleted', {'id': map_id})
    socketio.emit('map_list', {'maps': map_store.list_maps()})
    emit_rules()


@socketio.on('preview_map')
def handle_preview_map(data=None):
    """Deal this map once and send back the board it produced.

    Server-side on purpose: the preview goes through the same `Game` the table
    will play, so what you preview is what you play and there is no second
    implementation of the draw in JavaScript to drift from this one. Pressing it
    repeatedly is how you learn a pool's variance, which with a sea tile in an
    island's pool is the thing worth knowing.
    """
    if rate_limited():
        return
    if not _in_lobby():
        return

    defn = _accepted(data)
    if defn is None:
        return

    seed = (data or {}).get('seed')
    rng = random.Random(seed) if isinstance(seed, int) and not isinstance(seed, bool) else None

    session = state.session()
    rules = dict(session.lobby_rules)
    rules['board_layout'] = 'custom'
    rules['board_map'] = defn.id
    try:
        preview = Game(['Preview'], [], config=session.config, rules=rules,
                       rng=rng or random.Random(), map_definition=defn)
    except maps.MapUnplayable as exc:
        reject('INVALID_MAP', str(exc))
        return

    islands = {}
    for island_id in preview.islands().values():
        islands[island_id] = islands.get(island_id, 0) + 1

    _, warnings = maps.validate_map(defn)
    emit('map_preview', {
        'board': preview.get_board_data(),
        'islands': sorted(islands.values(), reverse=True),
        'warnings': [warning.to_json() for warning in warnings],
    })
