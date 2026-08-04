"""The map file format: parse it, validate it, deal a board from it.

A map is the rulebook's own setup paragraph turned into data — "the board is
created by shuffling all listed hexes face down and placing them face up at
random within the assembled frame", one shuffled pool per region.

This module knows nothing about the engine. It reads a dict that came off the
wire or off disk and returns plain data; `board.py` is what turns that data into
hexes, and the graph, the red-number separation and the harbour spacing all stay
where they are. Nothing here computes an island either: an island is derived
from the board as dealt (`board.islands`), never authored.

The map file says `sea` where the engine's `Hex.type` says `ocean`. The
translation happens once, in `board._apply_map_instance`. Renaming the engine's
value instead would touch the renderer, the pirate, the save format and a dozen
tests for no gameplay benefit.
"""

# What a map file may put in a pool. `sea` is the file's word for water; `gold`
# is reserved so v2 can add it without a format change, and is refused today.
TERRAIN_TYPES = ('wood', 'brick', 'sheep', 'wheat', 'ore', 'desert', 'sea')

# The terrain that pays out when its number is rolled, and therefore the only
# terrain a number token may sit on. Imported by `board._create_hexes` so the
# board and the map file cannot drift into two answers.
RESOURCE_TERRAINS = ('wood', 'brick', 'sheep', 'wheat', 'ore')

# The tokens in the box. A 7 is the robber's roll and never sits on a hex.
TOKEN_VALUES = (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)


def takes_a_token(terrain: str) -> bool:
    """Whether a hex of this terrain carries a number token.

    An allowlist rather than "everything but the desert", so a pool holding sea
    — or, later, any other terrain that produces nothing — cannot quietly pop a
    token out of the box and leave a number floating on open water. Answers for
    the map file's `sea` and the engine's `ocean` alike, since neither is a
    resource.
    """
    return terrain in RESOURCE_TERRAINS


def parse_hex_key(key: str) -> tuple:
    """A hex key as (x, y, z), or None if it does not name a hex.

    A hex centre has all three coordinates divisible by 3 and summing to zero —
    the same lattice `board.py` builds on.
    """
    if not isinstance(key, str) or key.count(',') != 2:
        return None
    try:
        coords = tuple(int(part) for part in key.split(','))
    except ValueError:
        return None
    if sum(coords) != 0 or any(value % 3 for value in coords):
        return None
    return coords


def sort_hex_keys(keys) -> list:
    """Hex keys in a stable order, sorted by coordinate rather than by string.

    `"-3,0,3"` sorts before `"0,0,0"` before `"3,-3,0"` as strings, which is
    stable but is not the order anyone reading a map would expect. What matters
    is only that it never depends on set or dict iteration order: the same map
    and the same seed must deal the same board in every process.
    """
    return sorted(keys, key=lambda key: (parse_hex_key(key) or (0, 0, 0), key))
