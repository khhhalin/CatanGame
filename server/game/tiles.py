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
    # An Explorers & Pirates map-format-v2 terrain, refused in a v1 map file.
    v2: bool = False
    # Whether a number token sits on it, when that is not simply "does it
    # produce": gold pays out on its roll (so takes a token) but its yield is a
    # player's *choice*, so `produces` is None. Left None to derive from produces.
    token: bool | None = None

    @property
    def takes_token(self) -> bool:
        """A number token sits on a tile that pays out when it is rolled."""
        if self.token is not None:
            return self.token
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
    """Every base (non-v2) terrain's map-file name, in registration order.

    This is the v1 vocabulary; a v1 map naming a v2 terrain is refused. See
    `all_names` for the full set an Explorers & Pirates (v2) map may use.
    """
    return tuple(name for name, terrain in REGISTRY.items() if not terrain.v2)


def all_names() -> tuple:
    """Every terrain, base and Explorers & Pirates v2, in registration order."""
    return tuple(REGISTRY)


def resource_terrains() -> tuple:
    """The base resources — the terrains that pay out a fixed resource."""
    return tuple(name for name, terrain in REGISTRY.items() if terrain.produces)


def token_terrains() -> tuple:
    """Every terrain a number token may sit on — the producers plus gold."""
    return tuple(name for name, terrain in REGISTRY.items() if terrain.takes_token)


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

# A sixth resource that is not in any printed box: it exists so a custom map can
# deal it, and only there. Registering it here is what makes it a real terrain —
# paintable, tokenable, and a valid v1 map word — while the built-in layouts,
# which list their own tiles, never include it. It pays a `cotton` card like any
# producer; it carries no Cities & Knights commodity, since no city was ever
# printed to yield one.
register(Terrain("cotton", "cotton", produces="cotton"))

# Explorers & Pirates map-format-v2 terrains, refused in a v1 map. Gold pays out
# on its roll (a token sits on it) but its yield is a player's choice, so
# `produces` stays None and `token` is set explicitly. Fish shoals and spice
# hexes produce through the mission mechanics, not a dice roll, so they carry no
# token — like a desert or the sea.
register(Terrain("gold", "gold", produces=None, v2=True, token=True))
register(Terrain("fish", "fish", produces=None, v2=True))
register(Terrain("spice", "spice", produces=None, v2=True))

# Traders & Barbarians, The Fishermen of Catan: the lake replaces the desert.
# It pays no resource card, so `produces` is None, and it carries no single
# number token — it draws fish on any of 2/3/11/12 — so `token` is False and its
# four trigger numbers live on the game's fishing state, not on the hex. Like
# the desert it hosts no production walk; unlike the desert the robber never
# starts on it (it is never coastal, and this scenario starts the robber off the
# board anyway).
register(Terrain("lake", "lake", produces=None, v2=True, token=False))

# Traders & Barbarians, The Rivers of Catan. A river hex pays no resource card
# and carries no token — its role is adjacency: settlements and roads built
# beside it earn gold coins, and the paths that cross it are bridge sites. A
# swampland hex likewise pays nothing and takes no token; it is the desert's
# replacement, and the robber starts on one at set-up. Both are land, not sea, so
# the buildable graph forms around them (a sea corner has no buildable vertex).
register(Terrain("river", "river", produces=None, v2=True, token=False))
register(Terrain("swampland", "swampland", produces=None, v2=True, token=False))

# Traders & Barbarians, The Caravans. The oasis replaces the desert at the very
# centre of the island and pays no resource card and carries no token — like the
# desert, but the caravans of camels grow out from the three arrows printed on
# it. It is land, so the buildable graph forms around it and camels can be placed
# on the paths that radiate from its corners.
register(Terrain("oasis", "oasis", produces=None, v2=True, token=False))

# Traders & Barbarians, Barbarian Attack. The castle sits in the outer ring and
# is where knights are trained: it pays no resource card and carries no token,
# and it can never be conquered. It is land, so the buildable graph forms around
# it and its six adjacent paths are where knights stand to guard the coast.
register(Terrain("castle", "castle", produces=None, v2=True, token=False))

# Traders & Barbarians, the main scenario. The quarry and the glassworks join the
# castle as the three trade hexes: a wagon delivers commodity tokens to them for
# gold and victory points (game/wagons.py). Like the castle they pay no resource
# card and carry no number token; they are land, so the buildable graph forms
# around their four land corners while their three sea-border paths carry no road.
register(Terrain("quarry", "quarry", produces=None, v2=True, token=False))
register(Terrain("glassworks", "glassworks", produces=None, v2=True, token=False))
