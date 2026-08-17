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
from game import buildings, map_store, maps, resources
from game import rules as rules_module
from game.game import Game
from state import (
    bump_and_broadcast,
    emit_rules,
    rate_limited,
    reject,
    viewer_for,
)

logger = logging.getLogger(__name__)

# The two registries an author may import, keyed by the `kind` the client sends.
# Each module owns its own file path and format; the handler only validates the
# payload's shape and hands it to `save`. Adding a third registry is one entry.
_IMPORTABLE = {
    'resources': resources,
    'buildings': buildings,
}

# A registry override with more keys than this is not a hand-edited file; it is a
# client trying to make the server write a large one. The transport size cap
# (`import_registry` in EVENT_PAYLOAD_LIMITS) refuses oversized bytes first; this
# bounds the key count independently, since many tiny keys can stay under it.
MAX_IMPORT_KEYS = 500


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


@socketio.on('request_map')
def handle_request_map(data=None):
    if rate_limited():
        return
    map_id = (data or {}).get('id')
    try:
        full = map_store.read_map(map_id)
    except (map_store.UnknownMap, map_store.ReadOnlyMap) as exc:
        reject('UNKNOWN_MAP', str(exc))
        return
    builtin = map_store.is_builtin(map_id)
    emit('map_data', {'map': full, 'builtin': builtin})


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


@socketio.on('import_registry')
def handle_import_registry(data=None):
    """Adopt an uploaded resource or building registry file.

    The write-back half of the Download routes: an author edits the exported
    JSON and sends it here, and the server persists it to `data/<kind>.json` and
    re-reads it so every board dealt from then on draws the new colours or
    charges the new prices. Allowed during a live game as well as in the lobby —
    a retint or reprice is a table decision, not a board edit — but only a joined
    viewer may do it, and the payload is validated hard before it reaches disk.

    Tolerant like `_load`: a partial file that overrides a few keys is valid, so
    only the object-of-objects shape and a size bound are enforced; the merge
    over the defaults happens in `reload()`.
    """
    if rate_limited():
        return
    if viewer_for() is None:
        reject('NOT_IN_LOBBY', 'Join before importing a registry')
        return

    data = data or {}
    kind = data.get('kind')
    module = _IMPORTABLE.get(kind)
    if module is None:
        reject('UNKNOWN_REGISTRY', "kind must be 'resources' or 'buildings'")
        return

    payload = data.get('data')
    if not isinstance(payload, dict):
        reject('INVALID_REGISTRY', 'The imported file must be a JSON object')
        return
    if len(payload) > MAX_IMPORT_KEYS:
        reject('INVALID_REGISTRY', f'Too many entries (max {MAX_IMPORT_KEYS})')
        return
    if not all(isinstance(definition, dict) for definition in payload.values()):
        reject('INVALID_REGISTRY', 'Every entry must itself be an object')
        return

    session = state.session()
    with session.lock:
        try:
            module.save(payload)
        except OSError:
            logger.exception("could not write the %s registry", kind)
            reject('IMPORT_FAILED', f'The server could not save the {kind} file')
            return

        logger.info("%s registry imported by %s (%d entries)",
                    kind, viewer_for(), len(payload))
        emit('registry_imported', {'kind': kind, 'count': len(payload)})
        # A running game already carries per-board cost and colour data in its
        # snapshot, so push a fresh board so connected clients redraw at once; a
        # lobby with no board has nothing to broadcast and the next deal picks it
        # up. (The engine's flat prices are read per game at deal time, so a
        # reprice reaches an in-progress game's costs on its next board, not this
        # instant — see game.Game.building_costs.)
        if session.game is not None:
            bump_and_broadcast()


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


@socketio.on('preview_scenario')
def handle_preview_scenario(data=None):
    """Deal one preset's board once and send it back for the lobby's picker.

    The scenario picker previews a whole published rule set, which `preview_map`
    cannot: a preset names its board by id — or names none, meaning the default
    board — not the full map payload `preview_map` parses. This deals the preset
    through the same `Game` the table would play, so the thumbnail is the board
    the scenario deals rather than a second draw in JavaScript to drift from it.

    A preset ticks individual rules and nothing more (see `preset_rules`); this
    handler never learns which preset a running game came from, and refuses once
    a game is running, like the rest of the lobby.
    """
    if rate_limited():
        return
    if not _in_lobby():
        return

    preset_id = (data or {}).get('preset')
    chosen = rules_module.preset_rules(preset_id)
    if chosen is None:
        reject('UNKNOWN_PRESET', f'There is no "{preset_id}" preset')
        return

    # A preset with a custom board names its map by id; the default board (no
    # board_map, or a non-custom layout) deals with no map definition at all.
    map_definition = None
    if chosen['board_layout'] == 'custom' and chosen.get('board_map'):
        try:
            map_definition = map_store.load_definition(chosen['board_map'])
        except (map_store.UnknownMap, maps.InvalidPayload) as exc:
            reject('UNKNOWN_MAP',
                   f'The map "{chosen["board_map"]}" cannot be previewed: {exc}')
            return

    session = state.session()
    try:
        preview = Game(['Preview'], [], config=session.config, rules=chosen,
                       rng=random.Random(), map_definition=map_definition)
    except maps.MapUnplayable as exc:
        reject('INVALID_MAP', str(exc))
        return

    # The preset rides back so the client can match the board to the row still
    # selected, rather than paint a stale reply over a scenario clicked since.
    emit('scenario_preview', {'preset': preset_id, 'board': preview.get_board_data()})
