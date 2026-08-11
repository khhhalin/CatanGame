"""The building registry: name, cost and icon for every build the engine prices.

What the engine's *mechanics* read off a build is only its id — `deduct_cost`,
`can_afford` and every placement flow key on ``'settlement'``, and the price is
looked up by that id in ``_base_cost``. Two of the three fields here are display:
the ``name`` a player reads on the Costs panel and the ``icon`` the sprite sheet
draws for it. The third, ``cost``, is the price the engine actually charges —
until now it lived in a separate ``data/costs.json`` that no name or glyph sat
beside, so a build's price, its label and its icon were three files free to
drift. They live here instead, one definition per build, so adding a build or
retinting one is a single entry and a data edit rather than a code change.

The defaults below fold in every line of the old ``data/costs.json`` with its
cost dict byte-for-byte unchanged, and add the label the Costs panel already
showed and the sprite concept id ``icons.js`` already understood for each. A
city improvement is *not* here: it is priced per level in the track's own
commodity, which is a question with an argument rather than a line in a table,
so ``game.py`` still asks the track (see ``_base_cost``).

Server-global: the same definitions serve every game — which builds a table can
actually make is its rules' business, not the registry's. A ``data/buildings.json``
file, when present, overrides or extends the defaults key by key; that file is
what the Download button exports and an import writes. Keyed by build id, which
is what the engine prices by and what the client looks a definition up by.
"""

import json
import os

# name: the label shown to players. cost: the price the engine charges, as
# `data/costs.json` carried it. icon: a sprite concept id from icons.js (a
# STATUS_ICON key, e.g. 'settlement' -> i-house), so a renamed glyph is renamed
# in one place. City improvements are priced per level and so are not listed.
DEFAULT_BUILDINGS = {
    "road": {"name": "Road", "cost": {"wood": 1, "brick": 1}, "icon": "road"},
    "ship": {"name": "Ship", "cost": {"wood": 1, "sheep": 1}, "icon": "ship"},
    "settlement": {"name": "Settlement",
                   "cost": {"wood": 1, "brick": 1, "wheat": 1, "sheep": 1},
                   "icon": "settlement"},
    "city": {"name": "City", "cost": {"wheat": 2, "ore": 3}, "icon": "city"},
    "harbor_settlement": {"name": "Harbor Settlement",
                          "cost": {"wheat": 2, "ore": 2}, "icon": "harbormaster"},
    "transport_ship": {"name": "Transport Ship",
                       "cost": {"wood": 1, "sheep": 1}, "icon": "ship"},
    "settler": {"name": "Settler",
                "cost": {"wood": 1, "brick": 1, "wheat": 1, "sheep": 1},
                "icon": "settlement"},
    "crew": {"name": "Crew", "cost": {"ore": 1, "sheep": 1}, "icon": "ship"},
    "build_knight": {"name": "Knight", "cost": {"sheep": 1, "ore": 1}, "icon": "knight"},
    "activate_knight": {"name": "Activate Knight", "cost": {"wheat": 1}, "icon": "knight"},
    "promote_knight": {"name": "Promote Knight", "cost": {"sheep": 1, "ore": 1}, "icon": "knight"},
    "city_wall": {"name": "City Wall", "cost": {"brick": 2}, "icon": "city_wall"},
    "medicine_city": {"name": "City (Medicine)", "cost": {"ore": 2, "wheat": 1}, "icon": "city"},
    "dev_card": {"name": "Dev Card", "cost": {"wheat": 1, "sheep": 1, "ore": 1}, "icon": "dev"},
}

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "buildings.json")


def _load() -> dict:
    """The defaults, with `data/buildings.json` merged over them key by key.

    A missing or unreadable file just means "use the defaults" — the building
    registry is never the reason the server will not start. Each override is
    shallow-merged onto its default, so a file may reprice one build, relabel
    another, or add a brand-new one, without restating the fields it leaves
    alone.
    """
    registry = {bid: dict(definition) for bid, definition in DEFAULT_BUILDINGS.items()}
    try:
        with open(_PATH) as handle:
            overrides = json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return registry
    if isinstance(overrides, dict):
        for bid, definition in overrides.items():
            if isinstance(definition, dict):
                registry[bid] = {**registry.get(bid, {}), **definition}
    return registry


_registry = _load()


def registry() -> dict:
    """The building definitions, as a fresh dict the caller may not mutate."""
    return {bid: dict(definition) for bid, definition in _registry.items()}


def reload() -> dict:
    """Re-read the file after it has been written (an import). Returns the new
    registry so the caller need not ask again."""
    global _registry
    _registry = _load()
    return registry()
