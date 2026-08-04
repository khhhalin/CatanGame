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

from game.validation import InvalidPayload, require_int, require_str

logger = logging.getLogger(__name__)

# The one format version. v2 will refuse a v1 file loudly rather than migrate
# it: `map_version` exists for that, and nobody has a library of maps yet.
MAP_VERSION = 1

# What a map file may put in a pool. `sea` is the file's word for water; `gold`
# is reserved for v2 — it needs a production modifier and a pending-choice
# client, neither of which exists — and is refused today.
TERRAIN_TYPES = ('wood', 'brick', 'sheep', 'wheat', 'ore', 'desert', 'sea')

# The terrain that pays out when its number is rolled, and therefore the only
# terrain a number token may sit on. Imported by `board._create_hexes` so the
# board and the map file cannot drift into two answers.
RESOURCE_TERRAINS = ('wood', 'brick', 'sheep', 'wheat', 'ore')

# The tokens in the box. A 7 is the robber's roll and never sits on a hex.
TOKEN_VALUES = (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)

# What a region can be. See `Region` for what each one means; only `main` has a
# mechanical effect, and only through the "start on the main land" rule.
KINDS = ('main', 'island', 'sea', 'fog')

# v1 shuffles every pool. `fixed` — a printed map, tile by tile — is v2, which
# is why the beginner layout is the one built-in board this format cannot yet
# express.
POOL_MODES = ('shuffled',)

HARBOUR_TYPES = ('generic',) + RESOURCE_TERRAINS

# The six steps from a hex centre to its neighbours, the same six as
# `BoardBuilder.HEX_DIRECTIONS`. Repeated rather than imported because
# `board.py` imports this module and not the other way round; a test asserts the
# two lists agree.
HEX_NEIGHBOURS = (
    (3, -3, 0), (3, 0, -3), (0, 3, -3), (-3, 3, 0), (-3, 0, 3), (0, -3, 3),
)

# A map id is also its filename, so this regex is the path-traversal guard.
# Nothing else may ever build a path out of client input.
SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{0,47}$')
REGION_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')

# Bounds, applied before anything walks the map twice. Radius 6 is 127 hexes.
MAX_FRAME_RADIUS = 6
MAX_REGIONS = 64
MAX_HEXES = 200
MAX_HARBOURS = 32
MAX_NAME = 64
MAX_NOTES = 512

# Exactly one region may say this instead of listing hexes.
REMAINING = 'remaining'
AUTO = 'auto'


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
    """

    mode: str
    terrain: tuple
    numbers: tuple

    @property
    def size(self) -> int:
        return sum(count for _, count in self.terrain)

    @property
    def tokens_needed(self) -> int:
        return sum(count for terrain, count in self.terrain if takes_a_token(terrain))

    def has(self, terrain: str) -> bool:
        return any(name == terrain and count for name, count in self.terrain)

    def tiles(self) -> list:
        """The pool as one tile per hex, in a fixed order for the shuffle."""
        return [name for name, count in self.terrain for _ in range(count)]

    def to_json(self) -> dict:
        return {
            'mode': self.mode,
            'terrain': {name: count for name, count in self.terrain},
            'numbers': list(self.numbers),
        }


@dataclass(frozen=True)
class Region:
    """A named set of hexes, a kind, and the pool its tiles come from.

    `kind` is about rules, never about terrain: the pool decides what a region
    contains, and a pool may legitimately contain sea. `main` is the land a
    scenario calls the mainland — the only kind with a mechanical effect in v1,
    through the "start on the main land" rule. `island` is documentation and a
    colour. `sea` is water. `fog` parses and refuses to start.
    """

    id: str
    kind: str
    color: str
    hexes: tuple
    pool: Pool

    def to_json(self) -> dict:
        return {
            'id': self.id,
            'kind': self.kind,
            'color': self.color,
            'hexes': list(self.hexes),
            'pool': self.pool.to_json(),
        }


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

    def to_json(self) -> dict:
        """The definition as a map file. `parse_map(defn.to_json()) == defn`."""
        return {
            'map_version': self.map_version,
            'id': self.id,
            'name': self.name,
            'author': self.author,
            'notes': self.notes,
            'frame': {'radius': self.radius},
            'robber_start': self.robber_start,
            'suggested_victory_target': self.suggested_victory_target,
            'regions': [region.to_json() for region in self.regions],
            'harbours': {
                'mode': 'bag',
                'types': {name: count for name, count in self.harbours},
            },
        }

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
    """

    placed: dict
    harbours: tuple
    robber_hex: str


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


def _parse_pool(raw) -> Pool:
    if not isinstance(raw, dict):
        raise InvalidPayload('INVALID_MAP', 'pool must be an object')
    mode = raw.get('mode', 'shuffled')
    if mode not in POOL_MODES:
        raise InvalidPayload('INVALID_MAP', 'a pool is shuffled; fixed pools are not in yet')

    numbers = raw.get('numbers', [])
    if not isinstance(numbers, list) or len(numbers) > MAX_HEXES:
        raise InvalidPayload('INVALID_MAP', 'pool numbers must be a list of tokens')
    for token in numbers:
        if isinstance(token, bool) or token not in TOKEN_VALUES:
            raise InvalidPayload('INVALID_MAP', f'{token!r} is not a number token')

    return Pool(mode, _require_counts(raw.get('terrain'), 'pool terrain', TERRAIN_TYPES),
                tuple(numbers))


def _parse_region(raw) -> tuple:
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

    return Region(region_id, kind, color, (), _parse_pool(raw.get('pool'))), hexes


def parse_map(data: dict) -> MapDefinition:
    """A map file as a MapDefinition, or InvalidPayload if it is not one.

    Shape only — sizes, allowlists and the coordinate lattice. Whether the map
    makes sense is `validate_map`'s job. Everything a client can send is bounded
    here, before anything quadratic runs, because a map is the most nested
    payload this protocol has and it turns into a filename.
    """
    if not isinstance(data, dict):
        raise InvalidPayload('INVALID_MAP', 'a map must be an object')

    require_int(data.get('map_version'), 'map_version', minimum=1, maximum=MAP_VERSION)
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

    raw_regions = data.get('regions')
    if not isinstance(raw_regions, list) or not raw_regions or len(raw_regions) > MAX_REGIONS:
        raise InvalidPayload('INVALID_MAP', f'a map has 1 to {MAX_REGIONS} regions')

    parsed = [_parse_region(raw) for raw in raw_regions]
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
                key for key in frame_hex_keys(radius) if key not in claimed
            ))
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

    return MapDefinition(
        map_version=MAP_VERSION, id=map_id, name=name, author=author, notes=notes,
        radius=radius, regions=tuple(regions), harbours=bag,
        robber_start=robber_start, suggested_victory_target=target,
    )


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
    return problems


# --- The draw -----------------------------------------------------------

def instantiate(defn: MapDefinition, rng) -> MapInstance:
    """Deal a board from this map with the game's own generator.

    The number of calls made on `rng` is a pure function of the definition —
    two shuffles per region, in file order, and no retries — so a seed replays
    a map exactly. The red-number separation and the harbour spacing are not
    here: they belong to `board.py`, run after the graph exists, and a second
    implementation of either would be a second answer waiting to disagree.
    """
    placed = {}
    for region in defn.regions:
        tiles = region.pool.tiles()
        tokens = list(region.pool.numbers)
        rng.shuffle(tiles)
        rng.shuffle(tokens)
        if len(tiles) != len(region.hexes):
            raise MapUnplayable(
                f'{region.id} has {len(tiles)} tiles for {len(region.hexes)} hexes'
            )
        for hex_key, terrain in zip(region.hexes, tiles, strict=True):
            if takes_a_token(terrain) and not tokens:
                raise MapUnplayable(f'{region.id} ran out of number tokens')
            placed[hex_key] = (terrain, tokens.pop() if takes_a_token(terrain) else None)

    return MapInstance(placed, _harbour_bag(defn), _robber_hex(defn, placed))


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
