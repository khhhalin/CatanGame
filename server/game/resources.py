"""The resource registry: name, colour, symbol and pattern for each resource.

What the engine's *mechanics* read off a resource is only its id — production,
build costs and trade all key on ``'wood'``. Everything a player *sees* — the
display name, the board colour, the icon and the hex pattern — is metadata, and
until now it was scattered: a colour in the CSS, an icon in the sprite sheet, a
pattern in the renderer and a name duplicated across two more files, each free to
drift from the others. It lives here instead, one definition per resource, so
adding a resource (gold, say) is a single entry and the client draws it with no
new code.

The defaults below convert the base game's resources to this system *without
changing how they look*: the colour is each terrain's own canonical (dark-theme,
which is the tuned one) fill, the pattern is the style the renderer already draws
for it, and the symbol is its existing sprite id.

Server-global: the same definitions serve every game — which resources a given
board actually uses is the board's own business, told per hex by ``type``. A
``data/resources.json`` file, when present, overrides or extends the defaults
key by key; that file is what the Download button exports and an import writes.
Keyed by ``hex_type`` (``'ocean'``, not the map word ``'sea'``), which is what a
hex carries as its ``type`` and what the client looks a definition up by.
"""

import json
import os

# name: shown to players. color: the hex fill (and card/badge tint). symbol: an
# icon id from the sprite sheet (empty for a terrain with no card). pattern: a
# named hex-fill style the renderer draws in the resource's own colour.
DEFAULT_RESOURCES = {
    "wood":   {"name": "Wood",   "color": "#3f8f5a", "symbol": "wood",   "pattern": "pines"},
    "brick":  {"name": "Brick",  "color": "#c9663a", "symbol": "brick",  "pattern": "brick"},
    "sheep":  {"name": "Sheep",  "color": "#8fbf4a", "symbol": "sheep",  "pattern": "dots"},
    "wheat":  {"name": "Wheat",  "color": "#e0b64a", "symbol": "wheat",  "pattern": "stripes"},
    "ore":    {"name": "Ore",    "color": "#8a9bb0", "symbol": "ore",    "pattern": "chevron"},
    "desert": {"name": "Desert", "color": "#e6d9bb", "symbol": "",       "pattern": "stipple"},
    "ocean":  {"name": "Sea",    "color": "#2f6288", "symbol": "",       "pattern": "solid"},
}

# The pattern styles the renderer knows how to draw; a definition's `pattern`
# must be one of these. Kept here as the shared contract between the file the
# player edits and the renderer that consumes it.
PATTERN_STYLES = ("pines", "brick", "dots", "stripes", "chevron", "stipple", "solid")

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "resources.json")


def _load() -> dict:
    """The defaults, with `data/resources.json` merged over them key by key.

    A missing or unreadable file just means "use the defaults" — the resource
    system is never the reason the server will not start. Each override is
    shallow-merged onto its default, so a file may retint one resource, rename
    another, or add a brand-new one, without restating the fields it leaves
    alone.
    """
    registry = {rid: dict(definition) for rid, definition in DEFAULT_RESOURCES.items()}
    try:
        with open(_PATH) as handle:
            overrides = json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return registry
    if isinstance(overrides, dict):
        for rid, definition in overrides.items():
            if isinstance(definition, dict):
                registry[rid] = {**registry.get(rid, {}), **definition}
    return registry


_registry = _load()


def registry() -> dict:
    """The resource definitions, as a fresh dict the caller may not mutate."""
    return {rid: dict(definition) for rid, definition in _registry.items()}


def reload() -> dict:
    """Re-read the file after it has been written (an import). Returns the new
    registry so the caller need not ask again."""
    global _registry
    _registry = _load()
    return registry()
