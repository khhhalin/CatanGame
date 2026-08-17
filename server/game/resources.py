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
    # A sixth resource no printed box holds, defined so a custom map can deal it
    # (game/tiles.py). Soft cream fill, the cloth glyph, a stipple weave — a look
    # of its own that no base terrain owns, so a cotton hex and a cotton card read
    # as cotton wherever a map places them.
    "cotton": {"name": "Cotton", "color": "#e8e2d0", "symbol": "cloth",  "pattern": "stipple"},
    # Explorers & Pirates map-format-v2 terrains (see game/tiles.py). They carry
    # no resource card, so no harbour glyph (symbol empty, like the desert); the
    # colours match the renderer's own --terrain-gold/fish/spice fallbacks so a
    # board looks the same whether it draws from here or the CSS tokens.
    "gold":   {"name": "Gold",   "color": "#d9a441", "symbol": "",       "pattern": "stipple"},
    "fish":   {"name": "Fish",   "color": "#3f9fb8", "symbol": "",       "pattern": "dots"},
    "spice":  {"name": "Spice",  "color": "#b5643c", "symbol": "",       "pattern": "stripes"},
    # Rise of the Inkas goods (game/tiles.py), each dealt on the die like any
    # resource — 1:1, so one entry serves both the hex fill and the card. The
    # jungle pays feathers (a warm plumage gold), the plantation coca (a deep leaf
    # green, apart from the forest), and the fishing-ground `fishery` a Fish card
    # (a colder sea-teal than the ocean frame so the shoals stand out on the coast).
    "feathers": {"name": "Feathers", "color": "#d9a441", "symbol": "", "pattern": "dots"},
    "coca":     {"name": "Coca",     "color": "#2f7d4f", "symbol": "", "pattern": "pines"},
    "fishery":  {"name": "Fish",     "color": "#2f8fb0", "symbol": "", "pattern": "dots"},
    # Traders & Barbarians (Fishermen): the lake that replaces the desert. It
    # deals no resource card (symbol empty, like the desert), and takes a watery
    # blue so it reads as open water inside the island rather than a resource hex.
    "lake":   {"name": "Lake",   "color": "#2f6288", "symbol": "",       "pattern": "solid"},
    # Traders & Barbarians (Rivers): the river hex you build beside for coins,
    # and the swampland that replaces the desert and starts the robber. Neither
    # deals a card (symbol empty, like the desert). The river takes a watery
    # blue; the swampland a dull green-brown bog.
    "river":     {"name": "River",     "color": "#3f7fa8", "symbol": "", "pattern": "solid"},
    "swampland": {"name": "Swampland", "color": "#6b6f45", "symbol": "", "pattern": "stipple"},
    # Traders & Barbarians (Caravans): the oasis that replaces the desert at the
    # centre, from which the caravans grow. It deals no card (symbol empty, like
    # the desert), and takes a warm sand colour with a stippled dune texture.
    "oasis":     {"name": "Oasis",     "color": "#d8b877", "symbol": "", "pattern": "stipple"},
    # Traders & Barbarians (Barbarian Attack): the castle in the outer ring where
    # knights are trained. It deals no card (symbol empty, like the desert) and
    # can never be conquered; a cool stone grey with a solid fill sets it apart
    # from the sandy coasts.
    "castle":    {"name": "Castle",    "color": "#8a8f99", "symbol": "", "pattern": "solid"},
    # Traders & Barbarians (main scenario): the quarry and the glassworks join the
    # castle as the three trade hexes a wagon delivers to. Neither deals a card
    # (symbol empty); the quarry a warm marble-tan, the glassworks a cool teal, so
    # the three trade hexes read apart at a glance.
    "quarry":     {"name": "Quarry",     "color": "#b89b74", "symbol": "", "pattern": "solid"},
    "glassworks": {"name": "Glassworks", "color": "#5f9ea0", "symbol": "", "pattern": "solid"},
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


def save(overrides: dict) -> dict:
    """Write `overrides` to `data/resources.json` and reload the registry.

    The write half of the import that `reload()` completes: the module that owns
    the path and the file's format is the one that writes it, so the shape here
    matches what the Download route exports and `_load` reads back. The caller
    validates the payload's shape; this only persists it (pretty-printed, utf-8,
    non-ASCII kept) and returns the freshly reloaded registry.
    """
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as handle:
        json.dump(overrides, handle, indent=2, ensure_ascii=False)
    return reload()
