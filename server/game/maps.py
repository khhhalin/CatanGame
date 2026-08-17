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

Determinism is a hard requirement and shapes every collection below: regions are
an array so file order is iteration order, a pool expands through
`sorted(items())`, and hex keys are ordered by their parsed coordinates rather
than by the string. Nothing here reads a set or a dict in its own order.
"""

import logging
import re
from dataclasses import dataclass, replace

from game import tiles
from game.validation import InvalidPayload, require_int, require_str

logger = logging.getLogger(__name__)

# The highest format version this build understands. A file still declares its
# own version and keeps it: a v1 file is parsed with v1 rules and stays v1, so
# the new v2 features below are additive and every map already on disk builds
# unchanged. A version beyond this is refused loudly rather than guessed at.
MAP_VERSION = 2

# What a v1 map file may put in a pool, read from the terrain registry so the
# map file, the board builder and production cannot drift into three answers.
# `sea` is the file's word for water.
TERRAIN_TYPES = tiles.names()

# v2 adds three Explorers & Pirates terrains — gold, fish and spice — which the
# registry carries flagged v2. A v1 file naming one is still refused.
TERRAIN_TYPES_V2 = tiles.all_names()

# The base-game resources: what a settlement collects and what the bank stocks,
# from the registry so the board and the map file cannot drift.
RESOURCE_TERRAINS = tiles.resource_terrains()

# Every terrain that carries a number token. A token means "pays out on this
# roll", which is why gold joins the list and fish/spice do not: their yield is
# not a die roll on the hex. From the registry (gold sets its token flag), kept
# separate from RESOURCE_TERRAINS so a gold tile can take a token without the
# bank stocking a "gold" resource.
TOKEN_TERRAINS = tiles.token_terrains()

# The tokens in the box. A 7 is the robber's roll and never sits on a hex.
TOKEN_VALUES = (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)

# What a region can be. See `Region` for what each one means; only `main` has a
# mechanical effect, and only through the "start on the main land" rule.
KINDS = ('main', 'island', 'sea', 'fog')

# v1 shuffles every pool. v2 adds `hidden` — an exploration pool dealt
# icon-side-up and revealed on discovery, its number tokens drawn per icon at
# reveal time (a later wave) rather than at the deal — and `fixed`, a printed
# map laid out tile by tile at declared positions (which is what lets the format
# express the beginner layout). Both are gated to v2.
POOL_MODES = ('shuffled',)
POOL_MODES_V2 = ('shuffled', 'hidden', 'fixed')

# How many docks one Council-of-Catan-style sea hex may carry, one per side.
MAX_DOCKS = 6

HARBOUR_TYPES = ('generic',) + RESOURCE_TERRAINS

# The six steps from a hex centre to its neighbours, the same six as
# `BoardBuilder.HEX_DIRECTIONS`. Repeated rather than imported because
# `board.py` imports this module and not the other way round; a test asserts the
# two lists agree.
HEX_NEIGHBOURS = (
    (3, -3, 0), (3, 0, -3), (0, 3, -3), (-3, 3, 0), (-3, 0, 3), (0, -3, 3),
)

# The six steps from a hex centre to its corners, the same six as
# `BoardBuilder.VERTEX_DIRECTIONS`. Repeated for the same reason as
# `HEX_NEIGHBOURS`; a test asserts the two lists agree. Used to tell whether a
# vertex a plaza names is genuinely a corner of the plaza's hex.
VERTEX_OFFSETS = (
    (1, -2, 1), (2, -1, -1), (1, 1, -2), (-1, 2, -1), (-2, 1, 1), (-1, -1, 2),
)

# A map id is also its filename, so this regex is the path-traversal guard.
# Nothing else may ever build a path out of client input.
SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{0,47}$')
REGION_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')

# Bounds, applied before anything walks the map twice. Radius 8 is 217 hexes.
MAX_FRAME_RADIUS = 8
MAX_REGIONS = 64
MAX_HEXES = 250
MAX_HARBOURS = 32
# Bridge-crossing sites a Rivers map may print. The printed scenario has 7; the
# cap is generous room for a custom river map, and bounds the payload.
MAX_BRIDGE_SITES = 32
# Caravan-start arrows a Caravans map may print. The printed scenario has 3 (one
# per caravan); the cap is generous room for a variant and bounds the payload.
MAX_OASIS_ARROWS = 12
# Roaming barbarians a main-scenario map may print. The printed scenario has 3;
# the cap is generous room for a variant and bounds the payload.
MAX_BARBARIAN_PATHS = 12
# Marked gift coast edges a Forgotten Tribe map may print. The printed scenario
# has 18 (8 Catan chits, 4 development cards, 6 harbours); the cap is generous
# room for a variant and bounds the payload.
MAX_GIFT_EDGES = 32
# Cloth-for-Catan villages a map may print (Seafarers 2021, Scenario 6, p. 22).
# The printed scenario has 8 (two per small island); the cap is generous room
# for a variant and bounds the payload.
MAX_CLOTH_VILLAGES = 16
# The three gift kinds a marked coast edge can carry (Seafarers 2021, Scenario 5,
# p. 20). A harbour gift also names the harbour it hands over.
GIFT_KINDS = ('victory_point', 'dev_card', 'harbor')
# The Wonders of Catan marked intersections (Seafarers 2021, Scenario 8, p. 27):
# the printed board marks the strait (purple squares) and the wasteland (brown
# squares), and a settlement standing on one gates a wonder. The printed board
# marks two of the first and five of the second; the cap is generous room for a
# variant and bounds the payload.
WONDER_MARKER_KINDS = ('strait', 'wasteland')
MAX_WONDER_MARKERS = 24
# The Pirate Islands (Seafarers 2021, Scenario 7, pp. 20-22). The printed board
# carries four pirate fortresses (a settlement corner on each western island) and
# a track of sea hexes the pirate fleet circumnavigates clockwise. The caps are
# the rulebook's four fortresses (generous room for a variant) and a loop no
# longer than the ring of sea around the board.
MAX_PIRATE_FORTRESSES = 8
MAX_PIRATE_TRACK = 64
MAX_NAME = 64
MAX_NOTES = 512

# Non-standard "explicit-adjacency" pieces a map injects onto the lattice: a
# plaza vertex sitting at a hex centre, or a spoke edge bordering one hex from
# inside — pieces the %3 lattice cannot predict, so they carry their own
# neighbour lists. The caps bound the payload; a Traders & Barbarians trade hex
# needs one plaza and up to six spokes, so a handful of trade hexes fits well
# inside these.
MAX_EXPLICIT_PIECES = 128
MAX_EXPLICIT_NEIGHBOURS = 12

# The syntactic prefixes that mark a non-standard piece's key. A lattice key is
# only digits, commas and minus signs, so a colon can never appear in one: a
# tagged key is therefore unmistakable, never collides with the lattice
# namespace, and never reaches the %3 classifiers the numeric path uses.
PLAZA_PREFIX = 'plaza:'
SPOKE_PREFIX = 'spoke:'

# Exactly one region may say this instead of listing hexes.
REMAINING = 'remaining'
AUTO = 'auto'


def takes_a_token(terrain: str) -> bool:
    """Whether a hex of this terrain carries a number token.

    An allowlist rather than "everything but the desert", so a pool holding sea
    — or a fish-shoal, a spice hex, or any other terrain that produces nothing
    on a roll — cannot quietly pop a token out of the box and leave a number
    floating where production would pay nobody. Read live from the registry, where
    a producer (and gold, by its token flag) carries a token and sea, desert,
    fish and spice do not. Answers for the map file's `sea` and the engine's
    `ocean` alike, since neither is a resource.
    """
    return tiles.takes_token(terrain)


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


def parse_edge_key(key: str) -> tuple:
    """An edge key as (x, y, z), or None if it does not name a hex side.

    A hex side sits one step out from a centre along an edge direction, so its
    coordinates sum to zero and exactly one of the three is divisible by 3 — the
    same lattice `board.py` builds edges on. Either of the side's two names
    qualifies; the board canonicalises them to one when it reads the map.
    """
    if not isinstance(key, str) or key.count(',') != 2:
        return None
    try:
        coords = tuple(int(part) for part in key.split(','))
    except ValueError:
        return None
    if sum(coords) != 0 or sum(1 for value in coords if value % 3 == 0) != 1:
        return None
    return coords


def parse_vertex_key(key: str) -> tuple:
    """A vertex key as (x, y, z), or None if it does not name an intersection.

    An intersection sits one step out from a centre along a vertex direction, so
    its coordinates sum to zero and none of the three is divisible by 3 — the
    same lattice `board.py` builds vertices on, and what tells a corner apart
    from a hex centre (all three divisible by 3) and a hex side (exactly one).
    """
    if not isinstance(key, str) or key.count(',') != 2:
        return None
    try:
        coords = tuple(int(part) for part in key.split(','))
    except ValueError:
        return None
    if sum(coords) != 0 or any(value % 3 == 0 for value in coords):
        return None
    return coords


def parse_plaza_key(key: str) -> tuple:
    """A plaza vertex key 'plaza:<hex>' as the hex's (x, y, z), or None.

    A plaza sits at a hex centre — a position the lattice reserves for the hex
    itself, never a corner — so it cannot be a standard vertex key and carries
    the tagged form instead. The embedded key must name a real hex centre; the
    coordinates are returned so a caller can reuse them for a frame-bounds check.
    """
    if not isinstance(key, str) or not key.startswith(PLAZA_PREFIX):
        return None
    return parse_hex_key(key[len(PLAZA_PREFIX):])


def parse_spoke_key(key: str) -> tuple:
    """A spoke edge key 'spoke:<hex>|<vertex>' as the hex's (x, y, z), or None.

    A spoke runs from a hex centre out to one of its corners — an interior side
    the lattice cannot name, since every lattice edge sits between two centres.
    The key embeds the hex it is interior to and the corner it reaches, so it is
    unique and legible; the hex coordinates are returned for the bounds check.
    The explicit neighbour lists, not this key, are what the board wires up.
    """
    if not isinstance(key, str) or not key.startswith(SPOKE_PREFIX):
        return None
    hex_part, sep, vertex_part = key[len(SPOKE_PREFIX):].partition('|')
    if not sep:
        return None
    hex_coords = parse_hex_key(hex_part)
    if hex_coords is None or parse_vertex_key(vertex_part) is None:
        return None
    return hex_coords


def _valid_hex_ref(key) -> bool:
    return parse_hex_key(key) is not None


def _valid_vertex_ref(key) -> bool:
    """A neighbour that names an intersection: a lattice corner or a plaza."""
    return parse_vertex_key(key) is not None or parse_plaza_key(key) is not None


def _valid_edge_ref(key) -> bool:
    """A neighbour that names a hex side: a lattice edge or a spoke."""
    return parse_edge_key(key) is not None or parse_spoke_key(key) is not None


def sort_hex_keys(keys) -> list:
    """Hex keys in a stable order, sorted by coordinate rather than by string.

    `"-3,0,3"` sorts before `"0,0,0"` before `"3,-3,0"` as strings, which is
    stable but is not the order anyone reading a map would expect. What matters
    is only that it never depends on set or dict iteration order: the same map
    and the same seed must deal the same board in every process.
    """
    return sorted(keys, key=lambda key: (parse_hex_key(key) or (0, 0, 0), key))


def ring_of(key: str) -> int:
    """How many hexes out from the centre this hex sits — the frame metric."""
    x, y, z = parse_hex_key(key)
    return max(abs(x), abs(y), abs(z)) // 3


def frame_hex_keys(radius: int) -> list:
    """Every hex inside a frame of this radius, rows first.

    The same lattice `board._hexagon` walks. Duplicated rather than imported
    because `board.py` imports this module and not the other way round; the
    test suite asserts the two agree.
    """
    keys = []
    for row in range(-radius, radius + 1):
        first = max(-radius, -radius - row)
        last = min(radius, radius - row)
        for column in range(first, last + 1):
            keys.append(f"{3 * column},{-3 * (column + row)},{3 * row}")
    return keys


def neighbour_keys(key: str) -> list:
    """The six hexes around this one, whether or not the map holds them."""
    x, y, z = parse_hex_key(key)
    return [f"{x + dx},{y + dy},{z + dz}" for dx, dy, dz in HEX_NEIGHBOURS]


class MapUnplayable(Exception):
    """A definition that got past validation still could not be dealt.

    Pool arithmetic only: everything else a map can get wrong is a
    `MapProblem` from `validate_map`, which the caller shows rather than
    raises.
    """


@dataclass(frozen=True)
class MapProblem:
    """One thing wrong with a map, structured rather than prose.

    The editor points at the region or the hex; the wire carries the code.
    """

    code: str
    message: str
    region_id: str = None
    hex_key: str = None

    def to_json(self) -> dict:
        return {
            'code': self.code,
            'message': self.message,
            'region_id': self.region_id,
            'hex_key': self.hex_key,
        }


@dataclass(frozen=True)
class Pool:
    """What a region's hexes are drawn from.

    `terrain` is a multiset as sorted (terrain, count) pairs and `numbers` an
    explicit multiset of tokens rather than counts, because its length has to
    equal the number of token-taking tiles — which is knowable before anything
    is shuffled, and is what makes that a validation rule instead of a runtime
    surprise.

    `mode` decides how the tiles reach the board:

    - `shuffled` (v1) — dealt face-up in a random order, tokens shuffled onto
      the producing tiles as they land.
    - `hidden` (v2) — the same shuffle, but each tile is placed face-down and
      carries no number: exploration reveals it later and draws its token then.
    - `fixed` (v2) — a printed layout. `placements` names the tile and token for
      each hex by key, so the deal is deterministic and ignores the generator.
      `terrain`/`numbers` are derived from `placements`, so the size and token
      rules validate the same way they do for a shuffled pool.
    """

    mode: str
    terrain: tuple
    numbers: tuple
    placements: tuple = ()

    @property
    def size(self) -> int:
        return sum(count for _, count in self.terrain)

    @property
    def tokens_needed(self) -> int:
        return sum(count for terrain, count in self.terrain if takes_a_token(terrain))

    @property
    def is_hidden(self) -> bool:
        return self.mode == 'hidden'

    def has(self, terrain: str) -> bool:
        return any(name == terrain and count for name, count in self.terrain)

    def tiles(self) -> list:
        """The pool as one tile per hex, in a fixed order for the shuffle."""
        return [name for name, count in self.terrain for _ in range(count)]

    def to_json(self) -> dict:
        if self.mode == 'fixed':
            return {
                'mode': 'fixed',
                'placements': {
                    key: ({'terrain': terrain, 'number': number}
                          if number is not None else {'terrain': terrain})
                    for key, terrain, number in self.placements
                },
            }
        return {
            'mode': self.mode,
            'terrain': {name: count for name, count in self.terrain},
            'numbers': list(self.numbers),
        }


@dataclass(frozen=True)
class HexMeta:
    """Per-hex metadata a scenario prints onto one tile.

    Schema only for now — parsed, validated and serialized so a v2 map can
    carry it, but read by no mechanic yet:

    - `docks` — the sides (0..5) of a Council-of-Catan sea hex that a settlement
      may build a dock against; the hex itself takes no settlement.
    - `village` — this hex holds a village (a spice-scenario advantage).
    - `lair` — this hex holds a pirate lair token.
    - `fishing_ground` — a Fishermen-scenario fishing-ground tile on this frame
      (sea) hex, carrying the production number that pays out fish to buildings
      on the coastal intersections it touches. None when the hex carries none.
    - `oil_spring` — an Oil Springs tile printed on this hex; buildings on it
      produce oil rather than the terrain's resource, and pollution hits it
      differently (coilspringsgb_2015_web.pdf p. 1-2). False when the hex has
      no tile.
    """

    docks: tuple = ()
    village: bool = False
    lair: bool = False
    fishing_ground: int | None = None
    oil_spring: bool = False

    def to_json(self) -> dict:
        data = {}
        if self.docks:
            data['docks'] = list(self.docks)
        if self.village:
            data['village'] = True
        if self.lair:
            data['lair'] = True
        if self.fishing_ground is not None:
            data['fishing_ground'] = self.fishing_ground
        if self.oil_spring:
            data['oil_spring'] = True
        return data


@dataclass(frozen=True)
class Region:
    """A named set of hexes, a kind, and the pool its tiles come from.

    `kind` is about rules, never about terrain: the pool decides what a region
    contains, and a pool may legitimately contain sea. `main` is the land a
    scenario calls the mainland — the only kind with a mechanical effect in v1,
    through the "start on the main land" rule. `island` is documentation and a
    colour. `sea` is water. `fog` parses and refuses to start.

    `meta` is v2 per-hex metadata as sorted (hex_key, HexMeta) pairs, empty on
    an ordinary region.
    """

    id: str
    kind: str
    color: str
    hexes: tuple
    pool: Pool
    meta: tuple = ()

    def to_json(self) -> dict:
        data = {
            'id': self.id,
            'kind': self.kind,
            'color': self.color,
            'hexes': list(self.hexes),
            'pool': self.pool.to_json(),
        }
        if self.meta:
            data['meta'] = {key: hex_meta.to_json() for key, hex_meta in self.meta}
        return data


@dataclass(frozen=True)
class MapDefinition:
    """A parsed, normalised map. Says nothing about any game it is played in."""

    map_version: int
    id: str
    name: str
    author: str
    notes: str
    radius: int
    regions: tuple
    harbours: tuple
    robber_start: str
    suggested_victory_target: int = None
    excluded_hexes: tuple = ()
    # The Rivers of Catan river-crossing bridge sites: hex-side (edge) keys a
    # bridge may span and a normal road may never sit on. A map-level field
    # because a path is not owned by any one hex — `HexMeta` is per-hex. Empty on
    # every map that prints none.
    bridge_sites: tuple = ()
    # The Caravans oasis arrows: the hex-side (edge) keys each of the three
    # caravans starts from. Edge-direction data — the first camel of a caravan
    # sits on this path with its head pointing away from the oasis — but the
    # direction is derived from the oasis geometry rather than stored, so an arrow
    # is just the starting edge. A map-level field like `bridge_sites`, because a
    # path is not owned by a hex. Empty on every map that prints none.
    oasis_arrows: tuple = ()
    # The Traders & Barbarians main-scenario barbarian paths: the hex-side (edge)
    # keys the three roaming barbarians start on (expansions.md 690). A map-level
    # field like `bridge_sites`, because a path is not owned by a hex. Empty on
    # every map that prints none. The trade hexes themselves are read off the
    # dealt board by terrain (castle/quarry/glassworks), so they need no field.
    barbarian_paths: tuple = ()
    # The Forgotten Tribe marked gift coast edges: sorted (edge_key, kind, port)
    # triples, where kind is one of GIFT_KINDS and port names the harbour a
    # 'harbor' gift hands over (None for the other kinds). A map-level field like
    # `bridge_sites`, because a gift edge is not owned by a hex. Empty on every
    # map that prints none.
    gift_edges: tuple = ()
    # The Cloth for Catan villages: sorted (vertex_key, number) pairs. A village
    # is a number token that sits on an intersection of a small island and starts
    # with a supply of cloth; a shipping route reaching it earns its owner cloth.
    # A map-level field like `bridge_sites`, because a village is owned by an
    # intersection, not a hex. Empty on every map that prints none.
    cloth_villages: tuple = ()
    # The Wonders of Catan marked intersections: sorted (vertex_key, kind) pairs,
    # kind one of WONDER_MARKER_KINDS. A settlement on a 'strait' marker gates the
    # Great Bridge, one on a 'wasteland' marker the Great Wall. A map-level field
    # like `bridge_sites`, because a marker is owned by an intersection, not a
    # hex. Empty on every map that prints none.
    wonder_markers: tuple = ()
    # The Pirate Islands fleet track: an ordered tuple of sea-hex keys forming the
    # clockwise loop the pirate fleet circumnavigates (Seafarers 2021, Scenario 7,
    # p. 22). Consecutive entries name adjacent hexes, so a move of N steps is N
    # hops along the ring. A map-level field like `bridge_sites`, because the ring
    # is not owned by any one hex. Empty on every map that prints none.
    pirate_fleet_track: tuple = ()
    # The hex the fleet starts on — the field marked with a pirate ship in the
    # scenario diagram (p. 22). One of the track's own keys; None on a map that
    # prints no fleet.
    pirate_fleet_start: str = None
    # The Pirate Islands fortresses: sorted (vertex_key, index) pairs, where index
    # names which fortress (0..3) the intersection carries. A settlement of a
    # player's colour standing on three Catan chits (p. 20). A map-level field like
    # `cloth_villages`, because a fortress is owned by an intersection, not a hex.
    # Empty on every map that prints none.
    pirate_fortresses: tuple = ()
    # Non-standard "explicit-adjacency" pieces the map injects onto the lattice,
    # each as a (key, hexes, vertices, edges) 4-tuple where key is a tagged
    # (non-lattice) key and the three lists name the lattice-or-tagged pieces it
    # connects to, in the order the map declares them. `plaza_vertices` are
    # intersections at a hex centre; `spoke_edges` are interior sides bordering
    # one hex from inside — the Traders & Barbarians trade-hex plaza is the
    # motivating case. The %3 lattice cannot predict either, so they carry their
    # own neighbours and the board splices them into the standard graph after it
    # is built. Empty on every map that declares none, which is every board that
    # existed before this channel — so those boards are byte-for-byte unchanged.
    plaza_vertices: tuple = ()
    spoke_edges: tuple = ()

    def to_json(self) -> dict:
        """The definition as a map file. `parse_map(defn.to_json()) == defn`."""
        frame: dict = {'radius': self.radius}
        if self.excluded_hexes:
            frame['excluded'] = list(self.excluded_hexes)
        data = {
            'map_version': self.map_version,
            'id': self.id,
            'name': self.name,
            'author': self.author,
            'notes': self.notes,
            'frame': frame,
            'robber_start': self.robber_start,
            'suggested_victory_target': self.suggested_victory_target,
            'regions': [region.to_json() for region in self.regions],
            'harbours': {
                'mode': 'bag',
                'types': {name: count for name, count in self.harbours},
            },
        }
        if self.bridge_sites:
            data['bridge_sites'] = list(self.bridge_sites)
        if self.oasis_arrows:
            data['oasis_arrows'] = list(self.oasis_arrows)
        if self.barbarian_paths:
            data['barbarian_paths'] = list(self.barbarian_paths)
        if self.gift_edges:
            data['gift_edges'] = {
                edge_key: ({'gift': kind, 'port': port} if port else {'gift': kind})
                for edge_key, kind, port in self.gift_edges
            }
        if self.cloth_villages:
            data['cloth_villages'] = {
                vertex_key: number for vertex_key, number in self.cloth_villages
            }
        if self.wonder_markers:
            data['wonder_markers'] = {
                vertex_key: kind for vertex_key, kind in self.wonder_markers
            }
        if self.pirate_fleet_track:
            data['pirate_fleet_track'] = list(self.pirate_fleet_track)
        if self.pirate_fleet_start is not None:
            data['pirate_fleet_start'] = self.pirate_fleet_start
        if self.pirate_fortresses:
            data['pirate_fortresses'] = {
                vertex_key: index for vertex_key, index in self.pirate_fortresses
            }
        if self.plaza_vertices:
            data['plaza_vertices'] = _explicit_pieces_to_json(self.plaza_vertices)
        if self.spoke_edges:
            data['spoke_edges'] = _explicit_pieces_to_json(self.spoke_edges)
        return data

    def region_of(self) -> dict:
        """Hex key -> the id of the region that claims it."""
        return {
            hex_key: region.id for region in self.regions for hex_key in region.hexes
        }

    def hexes_of_kind(self, kind: str) -> set:
        return {
            hex_key
            for region in self.regions if region.kind == kind
            for hex_key in region.hexes
        }

    def land_capable(self) -> set:
        """Hexes whose region could deal them something other than sea.

        The strongest thing that can be said about a map before the draw. A
        region holding one sea tile among three land ones may come out as two
        islands, one island, or a single hex in the water — which is why an
        island is derived from the board rather than read off the file.
        """
        return {
            hex_key
            for region in self.regions
            if region.pool.size > sum(
                count for name, count in region.pool.terrain if name == 'sea'
            )
            for hex_key in region.hexes
        }


@dataclass(frozen=True)
class MapInstance:
    """One dealt board: terrain and tokens per hex, the harbour bag, the robber.

    Deliberately dumb. It carries no graph — `board.py` derives that, exactly as
    it does for a built-in layout.

    `hidden` is the set of hex keys dealt face-down by an exploration pool: the
    terrain in `placed` is real on the server but secret to clients until a
    later wave reveals it, and its number is still `None` because the token is
    drawn at reveal. `meta` maps a hex key to its `HexMeta`, empty when the map
    prints none. Both default empty, so a v1 draw is exactly what it was.
    """

    placed: dict
    harbours: tuple
    robber_hex: str
    hidden: frozenset = frozenset()
    meta: dict = None


# --- Parsing: shape only ------------------------------------------------

def _require_slug(value, field: str, pattern) -> str:
    text = require_str(value, field, max_length=48)
    if not pattern.match(text):
        raise InvalidPayload('INVALID_MAP', f'{field} must be lowercase letters, digits and dashes')
    return text


def _require_counts(raw, field: str, allowed) -> tuple:
    """A {name: count} multiset from a map file, as sorted pairs.

    Sorted here and nowhere else: this is what the shuffle sees, so its order
    must not depend on the order the file happened to list the keys in.
    """
    if not isinstance(raw, dict):
        raise InvalidPayload('INVALID_MAP', f'{field} must be an object')
    counts = {}
    for name, count in raw.items():
        if name not in allowed:
            raise InvalidPayload('INVALID_MAP', f'{field} does not have a "{name}"')
        count = require_int(count, f'{field}[{name}]', minimum=0, maximum=MAX_HEXES)
        if count:
            counts[name] = count
    return tuple(sorted(counts.items()))


def _require_token(value, field: str) -> int:
    if isinstance(value, bool) or value not in TOKEN_VALUES:
        raise InvalidPayload('INVALID_MAP', f'{value!r} is not a number token')
    return value


def _parse_fixed_pool(raw, allowed_terrain) -> Pool:
    """A printed pool: a tile, and its token, named for each hex by key.

    Every producing tile must print its number here — there is no shuffle to
    draw one from — so a fixed pool's tokens are settled at parse time, and its
    derived `terrain`/`numbers` let the size and token-count rules validate it
    exactly as they would a shuffled pool.
    """
    placements_raw = raw.get('placements')
    if not isinstance(placements_raw, dict) or not placements_raw \
            or len(placements_raw) > MAX_HEXES:
        raise InvalidPayload('INVALID_MAP', 'a fixed pool places a tile on each of its hexes')

    placements, counts, numbers = [], {}, []
    for key in sort_hex_keys(placements_raw):
        if parse_hex_key(key) is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex')
        spec = placements_raw[key]
        if not isinstance(spec, dict):
            raise InvalidPayload('INVALID_MAP', f'{key} names a terrain and, if it pays, a token')
        terrain = spec.get('terrain')
        if terrain not in allowed_terrain:
            raise InvalidPayload('INVALID_MAP', f'a fixed pool has no "{terrain}" tile')
        number = spec.get('number')
        if takes_a_token(terrain):
            if number is None:
                raise InvalidPayload('INVALID_MAP', f'{key} is {terrain} and must print a number')
            number = _require_token(number, f'{key} number')
            numbers.append(number)
        elif number is not None:
            raise InvalidPayload('INVALID_MAP', f'{key} is {terrain} and takes no number')
        placements.append((key, terrain, number))
        counts[terrain] = counts.get(terrain, 0) + 1

    return Pool('fixed', tuple(sorted(counts.items())), tuple(numbers), tuple(placements))


def _parse_pool(raw, version: int) -> Pool:
    if not isinstance(raw, dict):
        raise InvalidPayload('INVALID_MAP', 'pool must be an object')
    modes = POOL_MODES_V2 if version >= 2 else POOL_MODES
    mode = raw.get('mode', 'shuffled')
    if mode not in modes:
        raise InvalidPayload(
            'INVALID_MAP', 'a pool is shuffled; a hidden or fixed pool needs map_version 2')
    terrains = TERRAIN_TYPES_V2 if version >= 2 else TERRAIN_TYPES

    if mode == 'fixed':
        return _parse_fixed_pool(raw, terrains)

    numbers = raw.get('numbers', [])
    if not isinstance(numbers, list) or len(numbers) > MAX_HEXES:
        raise InvalidPayload('INVALID_MAP', 'pool numbers must be a list of tokens')
    numbers = tuple(_require_token(token, 'pool numbers') for token in numbers)

    return Pool(mode, _require_counts(raw.get('terrain'), 'pool terrain', terrains), numbers)


def _parse_meta(raw, version: int) -> tuple:
    """A region's per-hex metadata as sorted (hex_key, HexMeta) pairs.

    Refused before v2 so a v1 file means exactly what it always did. Which hex
    each entry belongs to is checked here; that the hex is one the region owns
    is `validate_map`'s job, once `remaining` has been expanded.
    """
    if raw is None:
        return ()
    if version < 2:
        raise InvalidPayload('INVALID_MAP', 'per-hex metadata needs map_version 2')
    if not isinstance(raw, dict) or len(raw) > MAX_HEXES:
        raise InvalidPayload('INVALID_MAP', 'meta maps a hex key to its metadata')

    meta = []
    for key in sort_hex_keys(raw):
        if parse_hex_key(key) is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex')
        meta.append((key, _parse_hex_meta(raw[key])))
    return tuple(meta)


def _parse_hex_meta(spec) -> HexMeta:
    if not isinstance(spec, dict):
        raise InvalidPayload('INVALID_MAP', 'hex metadata must be an object')

    docks_raw = spec.get('docks', [])
    if not isinstance(docks_raw, list) or len(docks_raw) > MAX_DOCKS:
        raise InvalidPayload('INVALID_MAP', f'docks are up to {MAX_DOCKS} hex sides')
    docks = []
    for side in docks_raw:
        if isinstance(side, bool) or not isinstance(side, int) or not 0 <= side < 6:
            raise InvalidPayload('INVALID_MAP', 'a dock sits on a hex side 0..5')
        docks.append(side)
    docks = tuple(sorted(dict.fromkeys(docks)))

    village = spec.get('village', False)
    lair = spec.get('lair', False)
    if not isinstance(village, bool) or not isinstance(lair, bool):
        raise InvalidPayload('INVALID_MAP', 'village and lair are true or false')

    fishing_ground = spec.get('fishing_ground')
    if fishing_ground is not None:
        if isinstance(fishing_ground, bool) or not isinstance(fishing_ground, int) \
                or fishing_ground not in TOKEN_VALUES:
            raise InvalidPayload(
                'INVALID_MAP', 'a fishing ground carries a production number (2..12, not 7)'
            )

    oil_spring = spec.get('oil_spring', False)
    if not isinstance(oil_spring, bool):
        raise InvalidPayload('INVALID_MAP', 'oil_spring is true or false')

    return HexMeta(docks, village, lair, fishing_ground, oil_spring)


def _parse_region(raw, version: int) -> tuple:
    """One region, and its hexes or the marker that it claims what is left."""
    if not isinstance(raw, dict):
        raise InvalidPayload('INVALID_MAP', 'a region must be an object')

    region_id = _require_slug(raw.get('id'), 'region id', REGION_ID)
    kind = raw.get('kind')
    if kind not in KINDS:
        raise InvalidPayload('INVALID_MAP', f'a region is one of: {", ".join(KINDS)}')

    color = raw.get('color', '')
    if not isinstance(color, str) or len(color) > 32:
        color = ''

    hexes = raw.get('hexes')
    if hexes != REMAINING:
        if not isinstance(hexes, list) or len(hexes) > MAX_HEXES:
            raise InvalidPayload('INVALID_MAP', f'region {region_id} must list its hexes')
        for key in hexes:
            if parse_hex_key(key) is None:
                raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex')
        hexes = tuple(sort_hex_keys(dict.fromkeys(hexes)))

    region = Region(region_id, kind, color, (), _parse_pool(raw.get('pool'), version),
                    _parse_meta(raw.get('meta'), version))
    return region, hexes


def parse_map(data: dict) -> MapDefinition:
    """A map file as a MapDefinition, or InvalidPayload if it is not one.

    Shape only — sizes, allowlists and the coordinate lattice. Whether the map
    makes sense is `validate_map`'s job. Everything a client can send is bounded
    here, before anything quadratic runs, because a map is the most nested
    payload this protocol has and it turns into a filename.
    """
    if not isinstance(data, dict):
        raise InvalidPayload('INVALID_MAP', 'a map must be an object')

    version = require_int(data.get('map_version'), 'map_version', minimum=1, maximum=MAP_VERSION)
    map_id = _require_slug(data.get('id'), 'map id', SLUG)
    name = require_str(data.get('name'), 'map name', max_length=MAX_NAME)
    author = data.get('author') or ''
    if author:
        author = require_str(author, 'map author', max_length=MAX_NAME)
    notes = data.get('notes') or ''
    if notes:
        notes = require_str(notes, 'map notes', max_length=MAX_NOTES)

    frame = data.get('frame')
    if not isinstance(frame, dict):
        raise InvalidPayload('INVALID_MAP', 'a map needs a frame')
    radius = require_int(frame.get('radius'), 'frame radius', minimum=1,
                         maximum=MAX_FRAME_RADIUS)

    excluded_raw = frame.get('excluded') or []
    if not isinstance(excluded_raw, list) or len(excluded_raw) > MAX_HEXES:
        raise InvalidPayload('INVALID_MAP', 'frame excluded must be a list of hex keys')
    excluded_hexes: set[str] = set()
    for key in excluded_raw:
        if parse_hex_key(key) is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex')
        if ring_of(key) > radius:
            raise InvalidPayload('INVALID_MAP', f'excluded hex {key!r} is outside the frame')
        excluded_hexes.add(key)
    excluded_tuple = tuple(sort_hex_keys(excluded_hexes))

    raw_regions = data.get('regions')
    if not isinstance(raw_regions, list) or not raw_regions or len(raw_regions) > MAX_REGIONS:
        raise InvalidPayload('INVALID_MAP', f'a map has 1 to {MAX_REGIONS} regions')

    parsed = [_parse_region(raw, version) for raw in raw_regions]
    if len({region.id for region, _ in parsed}) != len(parsed):
        raise InvalidPayload('INVALID_MAP', 'two regions share an id')
    if sum(1 for _, hexes in parsed if hexes == REMAINING) > 1:
        raise InvalidPayload('INVALID_MAP', 'only one region may claim what is left')
    listed = sum(len(hexes) for _, hexes in parsed if hexes != REMAINING)
    if listed > MAX_HEXES:
        raise InvalidPayload('INVALID_MAP', f'a map has at most {MAX_HEXES} hexes')

    # `remaining` is expanded here and nowhere later, so nothing downstream ever
    # sees anything but an explicit list. Without it the sea of a radius-4 map
    # is a 51-entry array nobody will read, and the file stops fitting in a
    # socket payload.
    claimed = {key for _, hexes in parsed if hexes != REMAINING for key in hexes}
    regions = []
    for region, hexes in parsed:
        if hexes == REMAINING:
            hexes = tuple(sort_hex_keys(
                key for key in frame_hex_keys(radius)
                if key not in claimed and key not in excluded_hexes
            ))
        else:
            # Strip excluded hexes from explicit lists so erasing a hex in any
            # region removes it cleanly regardless of which region held it.
            hexes = tuple(k for k in hexes if k not in excluded_hexes)
        regions.append(replace(region, hexes=hexes))

    robber_start = data.get('robber_start', AUTO)
    if robber_start != AUTO and parse_hex_key(robber_start) is None:
        raise InvalidPayload('INVALID_MAP', 'robber_start is "auto" or a hex key')

    target = data.get('suggested_victory_target')
    if target is not None:
        target = require_int(target, 'suggested_victory_target', minimum=5, maximum=20)

    harbours = data.get('harbours') or {}
    if not isinstance(harbours, dict) or harbours.get('mode', 'bag') != 'bag':
        raise InvalidPayload('INVALID_MAP', 'harbours are a bag of types')
    bag = _require_counts(harbours.get('types') or {}, 'harbour types', HARBOUR_TYPES)
    if sum(count for _, count in bag) > MAX_HARBOURS:
        raise InvalidPayload('INVALID_MAP', f'a map has at most {MAX_HARBOURS} harbours')

    bridge_sites_raw = data.get('bridge_sites') or []
    if not isinstance(bridge_sites_raw, list) or len(bridge_sites_raw) > MAX_BRIDGE_SITES:
        raise InvalidPayload('INVALID_MAP',
                             f'bridge_sites is a list of at most {MAX_BRIDGE_SITES} hex sides')
    bridge_sites: set[str] = set()
    for key in bridge_sites_raw:
        coords = parse_edge_key(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex side')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP', f'bridge site {key!r} is outside the frame')
        bridge_sites.add(key)
    bridge_tuple = tuple(sort_hex_keys(bridge_sites))

    oasis_arrows_raw = data.get('oasis_arrows') or []
    if not isinstance(oasis_arrows_raw, list) or len(oasis_arrows_raw) > MAX_OASIS_ARROWS:
        raise InvalidPayload('INVALID_MAP',
                             f'oasis_arrows is a list of at most {MAX_OASIS_ARROWS} hex sides')
    oasis_arrows: set[str] = set()
    for key in oasis_arrows_raw:
        coords = parse_edge_key(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex side')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP', f'oasis arrow {key!r} is outside the frame')
        oasis_arrows.add(key)
    oasis_tuple = tuple(sort_hex_keys(oasis_arrows))

    barbarian_paths_raw = data.get('barbarian_paths') or []
    if not isinstance(barbarian_paths_raw, list) \
            or len(barbarian_paths_raw) > MAX_BARBARIAN_PATHS:
        raise InvalidPayload(
            'INVALID_MAP',
            f'barbarian_paths is a list of at most {MAX_BARBARIAN_PATHS} hex sides')
    barbarian_paths: set[str] = set()
    for key in barbarian_paths_raw:
        coords = parse_edge_key(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex side')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP',
                                 f'barbarian path {key!r} is outside the frame')
        barbarian_paths.add(key)
    barbarian_tuple = tuple(sort_hex_keys(barbarian_paths))

    gift_tuple = _parse_gift_edges(data.get('gift_edges'), radius, bag)

    cloth_tuple = _parse_cloth_villages(data.get('cloth_villages'), radius)

    wonder_tuple = _parse_wonder_markers(data.get('wonder_markers'), radius)

    track_tuple, track_start = _parse_pirate_track(
        data.get('pirate_fleet_track'), data.get('pirate_fleet_start'), radius)
    fortress_tuple = _parse_pirate_fortresses(data.get('pirate_fortresses'), radius)

    plaza_tuple = _parse_explicit_pieces(
        data.get('plaza_vertices'), radius, parse_plaza_key, 'plaza_vertices')
    spoke_tuple = _parse_explicit_pieces(
        data.get('spoke_edges'), radius, parse_spoke_key, 'spoke_edges')

    return MapDefinition(
        map_version=version, id=map_id, name=name, author=author, notes=notes,
        radius=radius, regions=tuple(regions), harbours=bag,
        robber_start=robber_start, suggested_victory_target=target,
        excluded_hexes=excluded_tuple, bridge_sites=bridge_tuple,
        oasis_arrows=oasis_tuple, barbarian_paths=barbarian_tuple,
        gift_edges=gift_tuple, cloth_villages=cloth_tuple,
        wonder_markers=wonder_tuple,
        pirate_fleet_track=track_tuple, pirate_fleet_start=track_start,
        pirate_fortresses=fortress_tuple,
        plaza_vertices=plaza_tuple, spoke_edges=spoke_tuple,
    )


def _parse_cloth_villages(raw, radius: int) -> tuple:
    """The Cloth for Catan villages as sorted (vertex_key, number) pairs.

    Shape only, like the other map-level fields: each key names an intersection
    on the lattice and each value is a number token a die can roll (2-12, never
    7). Which small island the intersection sits on is a board fact, checked no
    more than the gift edges are. Empty when the map prints none.
    """
    if raw is None:
        return ()
    if not isinstance(raw, dict) or len(raw) > MAX_CLOTH_VILLAGES:
        raise InvalidPayload(
            'INVALID_MAP',
            f'cloth_villages maps at most {MAX_CLOTH_VILLAGES} intersections to a number')

    villages = {}
    for key in sort_hex_keys(raw):
        coords = parse_vertex_key(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name an intersection')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP', f'village {key!r} is outside the frame')
        number = raw[key]
        if not isinstance(number, int) or isinstance(number, bool) \
                or number < 2 or number > 12 or number == 7:
            raise InvalidPayload('INVALID_MAP', 'a village number is 2-12 and never 7')
        villages[key] = number

    return tuple((key, villages[key]) for key in sort_hex_keys(villages))


def _parse_wonder_markers(raw, radius: int) -> tuple:
    """The Wonders of Catan marked intersections as sorted (vertex_key, kind) pairs.

    Shape only, like the other map-level fields: each key names an intersection
    on the lattice and each value is one of WONDER_MARKER_KINDS. Which land the
    intersection sits on is a board fact, checked no more than the cloth villages
    or gift edges are. Empty when the map prints none.
    """
    if raw is None:
        return ()
    if not isinstance(raw, dict) or len(raw) > MAX_WONDER_MARKERS:
        raise InvalidPayload(
            'INVALID_MAP',
            f'wonder_markers maps at most {MAX_WONDER_MARKERS} intersections to a kind')

    markers = {}
    for key in sort_hex_keys(raw):
        coords = parse_vertex_key(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name an intersection')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP', f'wonder marker {key!r} is outside the frame')
        kind = raw[key]
        if kind not in WONDER_MARKER_KINDS:
            raise InvalidPayload(
                'INVALID_MAP', f'a wonder marker is one of: {", ".join(WONDER_MARKER_KINDS)}')
        markers[key] = kind

    return tuple((key, markers[key]) for key in sort_hex_keys(markers))


def _parse_pirate_track(raw, start, radius: int) -> tuple:
    """The Pirate Islands fleet track as an ordered tuple of hex keys.

    Shape only, like the other map-level fields: an ordered list of hex keys on
    the lattice, kept in the order given (the loop is directional — clockwise —
    so it is *not* sorted). The start, if named, must be one of the track's own
    keys. Whether the keys are sea and mutually adjacent is a board fact, checked
    against the generated board by the scenario code, not here. Empty when the
    map prints none.
    """
    if raw is None:
        return (), None
    if not isinstance(raw, list) or len(raw) > MAX_PIRATE_TRACK:
        raise InvalidPayload(
            'INVALID_MAP', f'pirate_fleet_track is a list of at most {MAX_PIRATE_TRACK} hexes')
    track = []
    for key in raw:
        coords = parse_hex_key(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP', f'track hex {key!r} is outside the frame')
        track.append(key)
    if start is not None:
        if start not in track:
            raise InvalidPayload(
                'INVALID_MAP', 'pirate_fleet_start must be one of the track hexes')
    return tuple(track), start


def _parse_pirate_fortresses(raw, radius: int) -> tuple:
    """The Pirate Islands fortresses as sorted (vertex_key, index) pairs.

    Shape only, like the other map-level fields: each key names an intersection
    on the lattice and each value is the fortress index (a non-negative integer)
    that intersection carries. Which island the corner sits on is a board fact,
    checked no more than the cloth villages are. Empty when the map prints none.
    """
    if raw is None:
        return ()
    if not isinstance(raw, dict) or len(raw) > MAX_PIRATE_FORTRESSES:
        raise InvalidPayload(
            'INVALID_MAP',
            f'pirate_fortresses maps at most {MAX_PIRATE_FORTRESSES} intersections to an index')
    forts = {}
    for key in sort_hex_keys(raw):
        coords = parse_vertex_key(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name an intersection')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP', f'fortress {key!r} is outside the frame')
        index = raw[key]
        if not isinstance(index, int) or isinstance(index, bool) or index < 0 \
                or index >= MAX_PIRATE_FORTRESSES:
            raise InvalidPayload(
                'INVALID_MAP', f'a fortress index is 0 to {MAX_PIRATE_FORTRESSES - 1}')
        forts[key] = index
    return tuple((key, forts[key]) for key in sort_hex_keys(forts))


def _explicit_pieces_to_json(pieces) -> dict:
    """A channel of non-standard pieces back to its map-file form."""
    return {
        key: {'hexes': list(hexes), 'vertices': list(vertices), 'edges': list(edges)}
        for key, hexes, vertices, edges in pieces
    }


def _require_ref_list(raw, field: str, validator) -> tuple:
    """A non-standard piece's neighbour list: lattice or tagged keys.

    Kept in the order the map gives them rather than sorted, because a piece's
    neighbour order is part of what the author declares — the way an edge's two
    endpoint vertices are ordered.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) > MAX_EXPLICIT_NEIGHBOURS:
        raise InvalidPayload(
            'INVALID_MAP',
            f'{field} must be a list of at most {MAX_EXPLICIT_NEIGHBOURS} keys')
    keys = []
    for key in raw:
        if not validator(key):
            raise InvalidPayload('INVALID_MAP', f'{key!r} is not a valid key in {field}')
        keys.append(key)
    return tuple(keys)


def _parse_explicit_pieces(raw, radius: int, key_parser, kind_label: str) -> tuple:
    """A channel of non-standard pieces: tagged key -> explicit neighbour lists.

    Shape only, exactly like the other map-level fields. The key is a tagged key
    `key_parser` recognises — never a lattice key, so it can never be
    misclassified as a standard piece — and its value names the hexes, vertices
    and edges the piece connects to, each of which is a lattice key or another
    tagged key. The board splices these into the standard graph after it is
    built; whether the referenced pieces exist is a board fact, checked against
    the generated board, not here. Returns sorted (key, hexes, vertices, edges)
    4-tuples. Empty when the map declares none.
    """
    if raw is None:
        return ()
    if not isinstance(raw, dict) or len(raw) > MAX_EXPLICIT_PIECES:
        raise InvalidPayload(
            'INVALID_MAP',
            f'{kind_label} maps at most {MAX_EXPLICIT_PIECES} pieces to their neighbours')

    pieces = {}
    for key in sorted(raw):
        coords = key_parser(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} is not a {kind_label} key')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP', f'{kind_label} {key!r} is outside the frame')
        spec = raw[key]
        if not isinstance(spec, dict):
            raise InvalidPayload('INVALID_MAP', f'{key} names the neighbours it connects to')
        pieces[key] = (
            _require_ref_list(spec.get('hexes'), f'{key} hexes', _valid_hex_ref),
            _require_ref_list(spec.get('vertices'), f'{key} vertices', _valid_vertex_ref),
            _require_ref_list(spec.get('edges'), f'{key} edges', _valid_edge_ref),
        )

    return tuple((key, *pieces[key]) for key in sorted(pieces))


def _parse_gift_edges(raw, radius: int, harbour_bag) -> tuple:
    """The Forgotten Tribe marked gift coast edges as sorted triples.

    Shape only, exactly as the other map-level edge fields: each key names a hex
    side on the lattice, and each value names one of the three gift kinds. A
    'harbor' gift also names the harbour it hands over — a harbour type the bag
    allows — because that harbour is not in the auto-placed bag but delivered to
    a player to place. `None` for the other kinds. Which small island a gift edge
    borders is a board fact, checked no more than the other edge fields are.
    """
    if raw is None:
        return ()
    if not isinstance(raw, dict) or len(raw) > MAX_GIFT_EDGES:
        raise InvalidPayload(
            'INVALID_MAP', f'gift_edges maps at most {MAX_GIFT_EDGES} hex sides to a gift')

    gifts = {}
    for key in sort_hex_keys(raw):
        coords = parse_edge_key(key)
        if coords is None:
            raise InvalidPayload('INVALID_MAP', f'{key!r} does not name a hex side')
        if any(abs(value) > 3 * radius for value in coords):
            raise InvalidPayload('INVALID_MAP', f'gift edge {key!r} is outside the frame')
        spec = raw[key]
        if not isinstance(spec, dict) or spec.get('gift') not in GIFT_KINDS:
            raise InvalidPayload(
                'INVALID_MAP', f'a gift edge is one of: {", ".join(GIFT_KINDS)}')
        kind = spec['gift']
        port = None
        if kind == 'harbor':
            port = spec.get('port')
            if port not in HARBOUR_TYPES:
                raise InvalidPayload('INVALID_MAP', 'a harbour gift names a harbour type')
        elif spec.get('port') is not None:
            raise InvalidPayload('INVALID_MAP', f'a {kind} gift takes no harbour type')
        gifts[key] = (kind, port)

    return tuple((key, gifts[key][0], gifts[key][1]) for key in sort_hex_keys(gifts))


# --- Validation: meaning ------------------------------------------------

def land_components(defn: MapDefinition) -> list:
    """The stretches of land the map could deal, largest first.

    "Could": a pool holding sea may split one of these in two, or sink it. It
    is an upper bound on connectedness and a lower bound on the number of
    islands, which is all a file can honestly say — the board as dealt is what
    `board.islands` reads.
    """
    land = set(defn.land_capable())
    components = []
    for start in sort_hex_keys(land):
        if start not in land:
            continue
        component, frontier = [], [start]
        land.discard(start)
        while frontier:
            key = frontier.pop()
            component.append(key)
            for neighbour in neighbour_keys(key):
                if neighbour in land:
                    land.discard(neighbour)
                    frontier.append(neighbour)
        components.append(sort_hex_keys(component))
    components.sort(key=lambda component: (-len(component), component[0]))
    return components


def _sailing_reaches_every_island(defn: MapDefinition, components: list) -> bool:
    """Whether a ship could get from the first stretch of land to all the rest.

    A flood fill from the largest land mass through every hex that could be
    water. A second island the frame does not join to the first by sea is
    unreachable however many ships you build.
    """
    claimed = defn.region_of()
    land = defn.land_capable()
    reached = set(components[0])
    frontier = list(components[0])
    while frontier:
        for neighbour in neighbour_keys(frontier.pop()):
            if neighbour in reached or neighbour not in claimed:
                continue
            reached.add(neighbour)
            # Land stops the walk unless it is where we are going; water carries
            # it on.
            if neighbour not in land:
                frontier.append(neighbour)
    return all(set(component) & reached for component in components)


def validate_map(defn: MapDefinition) -> tuple:
    """(errors, warnings) as MapProblems. Errors block saving and starting.

    Shape is `parse_map`'s job and is already done; this is about whether the
    map means anything. Two rules from the design are deliberately not here:
    red numbers landing adjacent is what the "Keep 6s and 8s apart" rule fixes
    at generation, and whether the piece supply can cross the board depends on
    rules a definition knows nothing about.
    """
    errors, warnings = [], []
    claimed = {}

    for region in defn.regions:
        for hex_key in region.hexes:
            if hex_key in claimed:
                errors.append(MapProblem(
                    'HEX_CLAIMED_TWICE',
                    f'{hex_key} is in both {claimed[hex_key]} and {region.id}',
                    region.id, hex_key,
                ))
            claimed[hex_key] = region.id
            if ring_of(hex_key) > defn.radius:
                errors.append(MapProblem(
                    'OUTSIDE_FRAME', f'{hex_key} is outside the frame', region.id, hex_key,
                ))

        if region.pool.size != len(region.hexes):
            errors.append(MapProblem(
                'POOL_SIZE',
                f'{region.id} has {region.pool.size} tiles for {len(region.hexes)} hexes',
                region.id,
            ))
        if len(region.pool.numbers) != region.pool.tokens_needed:
            errors.append(MapProblem(
                'TOKEN_COUNT',
                f'{region.id} has {len(region.pool.numbers)} tokens for '
                f'{region.pool.tokens_needed} tiles that take one',
                region.id,
            ))
        if region.pool.mode == 'fixed':
            placed_keys = {key for key, _, _ in region.pool.placements}
            if placed_keys != set(region.hexes):
                errors.append(MapProblem(
                    'FIXED_PLACEMENT',
                    f'{region.id} prints tiles on hexes it does not own, or leaves some blank',
                    region.id,
                ))
        for hex_key, _ in region.meta:
            if hex_key not in set(region.hexes):
                errors.append(MapProblem(
                    'META_OFF_REGION',
                    f'{region.id} has metadata for {hex_key}, which it does not own',
                    region.id, hex_key,
                ))
        if region.kind == 'fog':
            warnings.append(MapProblem(
                'FOG_REGION', f'{region.id} is fog, which cannot be played yet', region.id,
            ))

    components = land_components(defn)
    if not components:
        errors.append(MapProblem('NO_LAND', 'a map needs somewhere to build'))
        return errors, warnings

    for hex_key in sort_hex_keys(defn.land_capable()):
        missing = [key for key in neighbour_keys(hex_key) if key not in claimed]
        if missing:
            # A side with one hex is not a sea edge, so no ship can arrive and no
            # harbour there could ever be used, but `_assign_ports` would still
            # hang one off it.
            errors.append(MapProblem(
                'LAND_ON_THE_RIM',
                f'{hex_key} could be land with nothing beside it; land needs six neighbours',
                claimed[hex_key], hex_key,
            ))

    if not _sailing_reaches_every_island(defn, components):
        errors.append(MapProblem(
            'UNREACHABLE_LAND', 'no shipping route could reach every island on this map',
        ))

    errors.extend(_explicit_pieces_off_board(defn, claimed))

    if defn.robber_start != AUTO:
        if defn.robber_start not in defn.land_capable():
            errors.append(MapProblem(
                'ROBBER_START', 'the robber must start on a hex that can be land',
                None, defn.robber_start,
            ))
    elif not any(region.pool.has('desert') for region in defn.regions):
        warnings.append(MapProblem(
            'NO_ROBBER_START',
            'no desert anywhere, so the robber starts beside the board',
        ))

    if len(components) > 1:
        warnings.append(MapProblem(
            'MANY_ISLANDS',
            f'{len(components)} stretches of land, which needs the Ships rule to play',
        ))

    coast = sum(
        1 for hex_key in defn.land_capable()
        for neighbour in neighbour_keys(hex_key)
        if neighbour not in defn.land_capable()
    )
    harbours = sum(count for _, count in defn.harbours)
    if harbours * 2 > coast:
        warnings.append(MapProblem(
            'HARBOUR_CROWDING',
            f'{harbours} harbours for {coast} coastal edges; some will not be placed',
        ))

    if defn.suggested_victory_target is not None:
        land = sum(
            count for region in defn.regions for name, count in region.pool.terrain
            if takes_a_token(name)
        )
        if abs(defn.suggested_victory_target - land // 2) > 3:
            warnings.append(MapProblem(
                'VICTORY_TARGET',
                f'{defn.suggested_victory_target} points on a board of {land} '
                f'producing hexes; the rulebook heuristic says {land // 2}',
            ))

    return errors, warnings


def _is_corner_of(vertex_key: str, hex_key: str) -> bool:
    """Whether a vertex is genuinely one of a hex's six corners.

    A corner sits one vertex-step out from a hex centre, so the difference of
    their coordinates is one of the six `VERTEX_OFFSETS`. Shape-level: it says a
    plaza's declared corner really touches its hex, never that the corner is land.
    """
    corner = parse_vertex_key(vertex_key)
    centre = parse_hex_key(hex_key)
    if corner is None or centre is None:
        return False
    step = tuple(c - h for c, h in zip(corner, centre, strict=True))
    return step in VERTEX_OFFSETS


def _explicit_pieces_off_board(defn: MapDefinition, claimed: dict) -> list:
    """The plaza/spoke board-fact check the explicit-adjacency channel defers.

    `parse_map` bounds a plaza or spoke to the frame but cannot see the dealt
    board; this checks, once the regions are known, that each piece's hex is one
    the map actually holds and each corner it names is a true corner of that hex.
    Shape-level, like the other map-field validators — it never asks whether a
    corner is land, only whether the geometry the piece claims exists.
    """
    problems = []
    for key, _hexes, vertices, _edges in defn.plaza_vertices:
        hex_key = key[len(PLAZA_PREFIX):]
        if hex_key not in claimed:
            problems.append(MapProblem(
                'PLAZA_OFF_BOARD', f'{key} sits on {hex_key}, which the map does not hold',
                None, hex_key,
            ))
        for corner in vertices:
            if not _is_corner_of(corner, hex_key):
                problems.append(MapProblem(
                    'PLAZA_OFF_BOARD',
                    f'{key} names {corner}, which is not a corner of {hex_key}',
                    None, hex_key,
                ))
    for key, _hexes, vertices, _edges in defn.spoke_edges:
        hex_key = key[len(SPOKE_PREFIX):].partition('|')[0]
        if hex_key not in claimed:
            problems.append(MapProblem(
                'SPOKE_OFF_BOARD', f'{key} sits on {hex_key}, which the map does not hold',
                None, hex_key,
            ))
        for corner in vertices:
            if corner.startswith(PLAZA_PREFIX):
                continue
            if not _is_corner_of(corner, hex_key):
                problems.append(MapProblem(
                    'SPOKE_OFF_BOARD',
                    f'{key} reaches {corner}, which is not a corner of {hex_key}',
                    None, hex_key,
                ))
    return problems


def start_problems(defn: MapDefinition, chosen: dict) -> list:
    """Why this map cannot be played under these rules, as sentences.

    The one place a map constrains the rules rather than the other way round,
    reported the same way `rules.dependency_problems` reports its own: named,
    refused, and never quietly fixed by switching a rule on for the table.
    """
    problems = []
    if any(region.kind == 'fog' for region in defn.regions):
        problems.append(f'{defn.name} has fog, which cannot be played yet')
    if chosen.get('start_on_main_land') and not defn.hexes_of_kind('main'):
        problems.append(f'{defn.name} has no main land to start on')
    components = land_components(defn)
    if len(components) > 1 and not chosen.get('ships'):
        problems.append(f'{defn.name} has {len(components)} islands and needs Ships')
    # The Caravans grow out of a central oasis; with no oasis the camels have
    # nowhere to start, so the rule is refused rather than played to nothing.
    if chosen.get('caravans') and not any(
        region.pool.has('oasis') for region in defn.regions
    ):
        problems.append(f'{defn.name} has no oasis for the caravans to grow from')
    return problems


# --- The draw -----------------------------------------------------------

def instantiate(defn: MapDefinition, rng) -> MapInstance:
    """Deal a board from this map with the game's own generator.

    The number of calls made on `rng` is a pure function of the definition —
    two shuffles per shuffled region, one per hidden region, none for a fixed
    one, in file order, and no retries — so a seed replays a map exactly. The
    red-number separation and the harbour spacing are not here: they belong to
    `board.py`, run after the graph exists, and a second implementation of
    either would be a second answer waiting to disagree.
    """
    placed = {}
    hidden = set()
    meta = {}
    for region in defn.regions:
        for hex_key, hex_meta in region.meta:
            meta[hex_key] = hex_meta

        if region.pool.mode == 'fixed':
            # Printed: no draw, tiles land where the author named them.
            for hex_key, terrain, number in region.pool.placements:
                placed[hex_key] = (terrain, number)
            continue

        tiles = region.pool.tiles()
        rng.shuffle(tiles)
        if len(tiles) != len(region.hexes):
            raise MapUnplayable(
                f'{region.id} has {len(tiles)} tiles for {len(region.hexes)} hexes'
            )

        if region.pool.is_hidden:
            # Face-down: the terrain is real but the number is drawn per icon at
            # reveal (a later wave), so no token is placed and none is shuffled.
            for hex_key, terrain in zip(region.hexes, tiles, strict=True):
                placed[hex_key] = (terrain, None)
                hidden.add(hex_key)
            continue

        tokens = list(region.pool.numbers)
        rng.shuffle(tokens)
        for hex_key, terrain in zip(region.hexes, tiles, strict=True):
            if takes_a_token(terrain) and not tokens:
                raise MapUnplayable(f'{region.id} ran out of number tokens')
            placed[hex_key] = (terrain, tokens.pop() if takes_a_token(terrain) else None)

    return MapInstance(placed, _harbour_bag(defn), _robber_hex(defn, placed),
                       frozenset(hidden), meta)


def _harbour_bag(defn: MapDefinition) -> tuple:
    """The harbours as one entry per piece. `_assign_ports` shuffles them."""
    return tuple(name for name, count in defn.harbours for _ in range(count))


def _robber_hex(defn: MapDefinition, placed: dict) -> str:
    """Where the robber starts on the board as it was actually dealt.

    A pool that can deal sea into the hex the author picked is an authoring
    mistake worth a line in the log, not a crash: fall back to the first desert
    the way `_create_hexes` does, and to nowhere at all if the map has none —
    the robber standing beside the board is a real state.
    """
    if defn.robber_start != AUTO:
        terrain = placed.get(defn.robber_start, (None, None))[0]
        if terrain is not None and terrain != 'sea':
            return defn.robber_start
        logger.warning('map %s wanted the robber on %s, which was dealt %s',
                       defn.id, defn.robber_start, terrain)

    for hex_key in sort_hex_keys(placed):
        if placed[hex_key][0] == 'desert':
            return hex_key
    return None
