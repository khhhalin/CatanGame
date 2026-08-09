"""The terrain registry: one place each tile type is defined.

A `Terrain` is the map file's word for a hex plus everything the engine needs to
run it — what it produces on its number, whether a number token sits on it, the
Cities & Knights commodity a city on it yields, and whether it is water. The map
validator, the board builder, production, and the robber all read their answer
from here rather than from a literal each keeps its own copy of.

This is the tile half of the "engine as an API" seam: adding a terrain — a
Traders & Barbarians river, an Explorers & Pirates gold or fish tile — is one
`register(Terrain(...))` call, and the scattered terrain logic picks it up with
no edit.

Two names for water: a map file writes ``sea``; the running board calls the same
hex ``ocean``. A `Terrain` carries both, and `get` resolves either — so a check
written against the map word and one written against the engine word reach the
same tile.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Terrain:
    """One terrain type and the facts the engine reads off it.

    `name` is the map file's word; `hex_type` is what the running board calls the
    hex (the same word for land, ``ocean`` for the file's ``sea``). `produces` is
    the resource its number pays out, or None for a tile that pays nobody.
    """

    name: str
    hex_type: str
    produces: str | None
    commodity: str | None = None
    is_sea: bool = False

    @property
    def takes_token(self) -> bool:
        """A number token sits only on a tile that pays out when it is rolled."""
        return self.produces is not None


REGISTRY: dict[str, Terrain] = {}
_BY_HEX_TYPE: dict[str, Terrain] = {}


def register(terrain: Terrain) -> Terrain:
    """Add a terrain. Refuses a duplicate name or a duplicate hex_type.

    The extension point: a new terrain is one call, and every consumer that goes
    through this module gains it without a change.
    """
    if terrain.name in REGISTRY:
        raise ValueError(f"duplicate terrain name: {terrain.name!r}")
    if terrain.hex_type in _BY_HEX_TYPE:
        raise ValueError(f"duplicate terrain hex_type: {terrain.hex_type!r}")
    REGISTRY[terrain.name] = terrain
    _BY_HEX_TYPE[terrain.hex_type] = terrain
    return terrain


def get(name_or_hex_type: str) -> Terrain | None:
    """The terrain for a map word (``sea``) or an engine word (``ocean``)."""
    terrain = REGISTRY.get(name_or_hex_type)
    if terrain is not None:
        return terrain
    return _BY_HEX_TYPE.get(name_or_hex_type)


def names() -> tuple:
    """Every terrain's map-file name, in registration order."""
    return tuple(REGISTRY)


def resource_terrains() -> tuple:
    """The names that pay out — the only terrains a number token may sit on."""
    return tuple(name for name, terrain in REGISTRY.items() if terrain.produces)


def hex_type_of(name: str) -> str:
    """The running board's word for a map terrain (``sea`` -> ``ocean``)."""
    terrain = get(name)
    return terrain.hex_type if terrain is not None else name


def produces(name_or_hex_type: str) -> str | None:
    """The resource this terrain pays out, or None."""
    terrain = get(name_or_hex_type)
    return terrain.produces if terrain is not None else None


def takes_token(name_or_hex_type: str) -> bool:
    """Whether a hex of this terrain carries a number token."""
    terrain = get(name_or_hex_type)
    return terrain is not None and terrain.takes_token


def is_sea(name_or_hex_type: str) -> bool:
    """Whether this terrain is water — where the pirate sails and the robber cannot go."""
    terrain = get(name_or_hex_type)
    return terrain is not None and terrain.is_sea


def commodities_by_terrain() -> dict:
    """{terrain name: commodity} for the terrains a city draws a commodity from."""
    return {
        name: terrain.commodity
        for name, terrain in REGISTRY.items()
        if terrain.commodity is not None
    }


# The base board's terrains. `sea` is the file's water, `ocean` the board's.
# Commodities are the Cities & Knights pairing (expansions.md): a city on wood
# also gives paper, on wool cloth, on ore coin; hills and fields give none.
register(Terrain("wood", "wood", produces="wood", commodity="paper"))
register(Terrain("brick", "brick", produces="brick"))
register(Terrain("sheep", "sheep", produces="sheep", commodity="cloth"))
register(Terrain("wheat", "wheat", produces="wheat"))
register(Terrain("ore", "ore", produces="ore", commodity="coin"))
register(Terrain("desert", "desert", produces=None))
register(Terrain("sea", "ocean", produces=None, is_sea=True))
