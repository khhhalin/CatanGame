"""Where maps live: one JSON file per map, plus the ones that ship with us.

A map is a small human-readable file, exactly like a save, and for the same
reason: there is one server per table and no database anywhere in this project.
Custom maps are written under `DATA_DIR/maps/`, which is already the "runtime
state lives outside the repo tree" directory tests redirect to a temp dir.

Every path is `os.path.join(MAPS_DIR, f"{map_id}.json")` and is built only after
`maps.SLUG` has matched, never any other way. That single rule is the whole
path-traversal defence, which is why the id is checked before anything else
looks at a map.
"""

import json
import logging
import os

from config import get_config

from game import maps

logger = logging.getLogger(__name__)

# Read at import for the same reason `state.py` reads it there: one process,
# one data directory, fixed for its lifetime.
MAPS_DIR = os.path.join(get_config().DATA_DIR, 'maps')

# Shipped with the server and read-only. Duplicating one is how you start from
# it, which is also why they are not merely constants in Python: the format has
# to be able to express them, and a file nobody can round-trip is not a format.
BUILTIN_DIR = os.path.join(os.path.dirname(__file__), 'builtin_maps')


class UnknownMap(Exception):
    """No map of that id, here or in the box."""


class ReadOnlyMap(Exception):
    """A built-in map. Duplicate it instead."""


def _safe_path(directory: str, map_id: str) -> str:
    if not isinstance(map_id, str) or not maps.SLUG.match(map_id):
        raise UnknownMap(f'{map_id!r} is not a map id')
    return os.path.join(directory, f'{map_id}.json')


def builtin_ids() -> list:
    if not os.path.isdir(BUILTIN_DIR):
        return []
    return sorted(
        name[: -len('.json')] for name in os.listdir(BUILTIN_DIR) if name.endswith('.json')
    )


def is_builtin(map_id: str) -> bool:
    return map_id in builtin_ids()


def read_map(map_id: str) -> dict:
    """One map file as it sits on disk. Raises UnknownMap.

    Returns the raw document rather than a MapDefinition: every caller has to
    re-validate anyway — a file on disk is a file a human may have edited — and
    handing back a parsed object would hide that from them.
    """
    for directory in (MAPS_DIR, BUILTIN_DIR):
        path = _safe_path(directory, map_id)
        if os.path.exists(path):
            with open(path) as handle:
                return json.load(handle)
    raise UnknownMap(f'there is no map called {map_id!r}')


def write_map(map_id: str, data: dict):
    """Write a map atomically, the way `persistence.save` writes a game.

    Temp file, flush, fsync, rename: an interrupted in-place write leaves a
    truncated file that fails to parse, which turns "the editor crashed" into
    "the map is gone".
    """
    if is_builtin(map_id):
        raise ReadOnlyMap(f'{map_id} ships with the server and cannot be overwritten')
    path = _safe_path(MAPS_DIR, map_id)
    os.makedirs(MAPS_DIR, exist_ok=True)
    temp_path = f'{path}.tmp'
    with open(temp_path, 'w') as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def delete_map(map_id: str):
    if is_builtin(map_id):
        raise ReadOnlyMap(f'{map_id} ships with the server and cannot be deleted')
    path = _safe_path(MAPS_DIR, map_id)
    if not os.path.exists(path):
        raise UnknownMap(f'there is no map called {map_id!r}')
    os.remove(path)


def _summary(map_id: str, data: dict, builtin: bool) -> dict:
    """One row of the map list, whether or not the file is any good."""
    row = {'id': map_id, 'name': map_id, 'author': '', 'hexes': 0, 'regions': 0,
           'islands': 0, 'builtin': builtin, 'problems': []}
    try:
        defn = maps.parse_map(data)
    except maps.InvalidPayload as exc:
        row['problems'] = [{'code': exc.code, 'message': exc.message,
                            'region_id': None, 'hex_key': None}]
        return row

    errors, _ = maps.validate_map(defn)
    row.update({
        'name': defn.name,
        'author': defn.author,
        'hexes': sum(len(region.hexes) for region in defn.regions),
        'regions': len(defn.regions),
        'islands': len(maps.land_components(defn)),
        'problems': [problem.to_json() for problem in errors],
    })
    return row


def list_maps() -> list:
    """Every map on this server, built-ins first, each with its problems.

    A directory a human can drop files into is a directory with a broken file
    in it sooner or later. One bad map becomes a row carrying its problems, not
    an exception that costs the editor the whole list.
    """
    rows = []
    for builtin, directory in ((True, BUILTIN_DIR), (False, MAPS_DIR)):
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.endswith('.json'):
                continue
            map_id = name[: -len('.json')]
            if not maps.SLUG.match(map_id):
                logger.warning('ignoring %s: not a map id', os.path.join(directory, name))
                continue
            try:
                with open(os.path.join(directory, name)) as handle:
                    data = json.load(handle)
            except (OSError, ValueError) as exc:
                logger.warning('could not read map %s: %s', name, exc)
                rows.append({'id': map_id, 'name': map_id, 'author': '', 'hexes': 0,
                             'regions': 0, 'islands': 0, 'builtin': builtin,
                             'problems': [{'code': 'UNREADABLE', 'message': str(exc),
                                           'region_id': None, 'hex_key': None}]})
                continue
            rows.append(_summary(map_id, data, builtin))
    return rows


def load_definition(map_id: str) -> maps.MapDefinition:
    """A map from disk, parsed and validated. The one way to start a game on one.

    Re-read and re-validated every time rather than cached: the file may have
    changed since it was listed, and a map arriving from disk is exactly as
    untrusted as one arriving over a socket.
    """
    defn = maps.parse_map(read_map(map_id))
    errors, _ = maps.validate_map(defn)
    if errors:
        raise maps.InvalidPayload(
            'INVALID_MAP', f'{map_id} cannot be played: {errors[0].message}'
        )
    return defn
