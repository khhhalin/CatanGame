"""Save and reload a game from a plain JSON file.

Deliberately simple: one human-readable file, no database. A restart should
not lose a game in progress, which until now it always did.

Only the parts of the board that were *decided* are saved — hex types and
numbers, ports, buildings, roads — not the derived graph of vertices, edges and
neighbours. That structure is regenerated deterministically from the board
geometry on load, which keeps the file small (tens of KB) and readable, and
means a change to the neighbour algorithm does not invalidate old saves.

The file is written atomically, so a crash or an overlapping write cannot leave
a half-written save that fails to parse on the next start.
"""

import json
import logging
import os

from game import cities_knights as ck_module
from game import maps
from game.game import Game

logger = logging.getLogger(__name__)

# Bumped when the shape below changes incompatibly. A save from an older
# version is ignored rather than half-loaded into a mismatched Game.
#
# Not bumped when hex sides became one Edge each: the shape is unchanged and
# every old edge key still names a real side, so those saves are translated on
# load instead. Refusing them would have thrown away games in progress to fix a
# bug the players did not cause.
SAVE_VERSION = 1


class NotASaveFile(Exception):
    """The file exists but was never written by us."""


def _edges_on_board(game: Game, keys) -> list:
    """Saved edge keys mapped onto the sides this board actually holds.

    A save written while an inland side had two names carries whichever name
    the writer happened to use, and half of those are no longer keys of the
    board. Unknown keys are dropped, and two names for one side collapse to a
    single entry.
    """
    mapped = []
    for key in keys:
        edge_key = game.canonical_edge_key(key)
        if edge_key is None:
            logger.warning("saved edge %s is not on this board; dropping it", key)
        elif edge_key not in mapped:
            mapped.append(edge_key)
    return mapped


def _walls_by_city(game: Game, saved: dict) -> dict:
    """Saved city walls as {player: [city vertex, ...]}.

    Walls used to be a bare per-player count attached to no city at all. Such a
    save cannot say which cities were walled, so the count is laid onto that
    player's own cities in key order: the hand limit they paid for survives the
    restart, and every wall still lands on a city they really own, which is more
    than dropping them would leave. A wall on the wrong city of one's own is a
    smaller lie than a hand limit that quietly drops by two mid-game.
    """
    walls = {}
    for name, saved_walls in saved.items():
        if isinstance(saved_walls, list):
            walls[name] = list(saved_walls)
            continue
        player = game.get_player(name)
        cities = sorted(player.cities) if player else []
        walls[name] = cities[:saved_walls]
        logger.warning(
            "save holds %s city walls for %s with no cities named; assigning them to %s",
            saved_walls, name, walls[name],
        )
    return walls


def _player_state(player) -> dict:
    return {
        'name': player.name,
        'color': player.color,
        'resources': player.resources,
        'commodities': player.commodities,
        'dev_cards': player.dev_cards,
        'settlements': player.settlements,
        'cities': player.cities,
        'roads': player.roads,
        'ships': player.ships,
        'victory_points': player.victory_points,
        'knights_played': player.knights_played,
        # Explorers & Pirates: the harbour settlements (2 VP each, so a save that
        # dropped them undercounted the score), gold currency, and the reserves.
        'harbor_settlements': player.harbor_settlements,
        'gold': player.gold,
        # Oil Springs: oil is a public currency worth nothing dropped, so a save
        # that lost it would hand a player back a smaller stockpile.
        'oil': player.oil,
        'settlers': player.settlers,
        'crews': player.crews,
    }


def _ck_state(ck) -> dict | None:
    if ck is None:
        return None
    return {
        'improvements': ck.improvements,
        'knights': {
            name: [
                {
                    'vertex': k.vertex, 'rank': k.rank, 'active': k.active,
                    'acted_this_turn': k.acted_this_turn,
                    'activated_this_turn': k.activated_this_turn,
                }
                for k in knights
            ]
            for name, knights in ck.knights.items()
        },
        'city_walls': ck.city_walls,
        'metropolis': ck.metropolis,
        'metropolis_vertex': ck.metropolis_vertex,
        'barbarian_position': ck.barbarian_position,
        'barbarians_have_attacked': ck.barbarians_have_attacked,
        'defender_cards': ck.defender_cards,
        'last_event': ck.last_event,
        'last_red_die': ck.last_red_die,
        # Without these a restart mid-game silently voids every progress card
        # in every hand, and reshuffles decks players have already drawn from.
        'progress_decks': ck.progress_decks,
        'progress_hands': ck.progress_hands,
    }


def _saved_map(data: dict):
    """The custom map a save was played on, re-validated, or None.

    `load` already treats a save as untrusted input, and a hand-edited `map`
    block is exactly that, so it goes through the same parse and validation a
    map arriving over a socket does. The inlined definition wins over the
    `board_map` rule beside it if they disagree — that is the whole reason it is
    inlined — and the disagreement is logged rather than silently resolved.
    """
    raw = data.get('map')
    if raw is None:
        return None

    defn = maps.parse_map(raw)
    errors, _ = maps.validate_map(defn)
    if errors:
        raise ValueError(f"the map saved with this game is not playable: {errors[0].message}")

    chosen = (data.get('rules') or {}).get('board_map')
    if chosen and chosen != defn.id:
        logger.warning("save names map %r but carries %r; playing what it carries",
                       chosen, defn.id)
    return defn


def serialize(game: Game) -> dict:
    """Everything needed to rebuild this game."""
    saved = {
        'save_version': SAVE_VERSION,
        'rules': game.rules,
        'players': [_player_state(p) for p in game.players],
        'observers': game.observers,
        'current_player_index': game.current_player_index,
        'game_state': game.game_state,
        'game_phase': game.game_phase,
        'setup_turn': game.setup_turn,
        'setup_action': game.setup_action,
        'last_setup_settlement': game.last_setup_settlement,
        'player_settlements': game.player_settlements,
        'turn_count': game.turn_count,
        'has_rolled_dice': game.has_rolled_dice,
        'robber_hex': game.robber_hex,
        # Seafarers. The pirate is None until somebody first moves it, which is
        # a real state and not a missing field.
        'pirate_hex': game.pirate_hex,
        'ship_moved_this_turn': game.ship_moved_this_turn,
        'fortress_attacked_this_turn': game.fortress_attacked_this_turn,
        'player_islands': game.player_islands,
        'island_points': game.island_points,
        # The Forgotten Tribe: the claimed 1-VP chits, which marked edges are
        # spent, and any harbour a player is holding to place. The gift edges and
        # the barren islands are re-derived from the map when the board is
        # regenerated, so only what the players decided is saved.
        'gift_points': game.gift_points,
        'claimed_gift_edges': sorted(game.claimed_gift_edges),
        'held_gift_harbors': game.held_gift_harbors,
        # Cloth for Catan: the bolts each player has banked, each village's
        # remaining supply, which players have already established trade
        # relations with each village, and the general supply. The village
        # numbers and positions are re-derived from the map when the board is
        # regenerated, so only what the game has spent and earned is saved.
        'cloth_tokens': game.cloth_tokens,
        'village_cloth': game.village_cloth,
        'village_traders': {vertex: sorted(players)
                            for vertex, players in game.village_traders.items()},
        'cloth_general_supply': game.cloth_general_supply,
        # Catan: Oil Springs. The general oil supply, the shared disaster track,
        # how many number tokens pollution has removed, the sequestered-oil
        # totals, who holds the Champion of the Environment token, and which
        # cities are metropolises. The oil-spring hexes are re-derived from the
        # map when the board regenerates, so only what play changed is saved.
        'oil_supply': game.oil_supply,
        'disaster_track': game.disaster_track,
        'oil_numbers_removed': game.oil_numbers_removed,
        'oil_sequestered': game.oil_sequestered,
        'oil_champion': game.oil_champion,
        'oil_metropolises': game.oil_metropolises,
        # Catan: Frenemies. The favour-token bag is dealt from the RNG and then
        # mutated by play (draws and, later, exchanges), so like the Helpers pile
        # it must be saved outright rather than re-derived. Usable and locked
        # holdings, the VP markers taken and their supply, and the network
        # connections already rewarded are all play state. The per-turn gift flag
        # is rebuilt by start_turn, so it is not saved.
        'favour_bag': game.favour_bag,
        'favour_usable': game.favour_usable,
        'favour_locked': game.favour_locked,
        'favour_vp_markers': game.favour_vp_markers,
        'favour_vp_supply': game.favour_vp_supply,
        'favour_connections': [sorted(pair) for pair in game.favour_connections],
        # The Wonders of Catan: which Wonder each player started and how many of
        # its levels they finished. The marked intersections are re-derived from
        # the map when the board regenerates, so only the players' progress is
        # saved.
        'wonder_choice': game.wonder_choice,
        'wonder_level': game.wonder_level,
        # The Pirate Islands: where the fleet sits on its track, the fortresses'
        # chits and capture, and each player's warships. The track itself and the
        # fortress intersections are re-derived from the map when the board
        # regenerates, so only what play has changed is saved.
        'pirate_fleet_index': game.pirate_fleet_index,
        'pirate_fortresses': game.pirate_fortresses,
        'player_warships': game.player_warships,
        # CATAN - The Helpers: the display pile and every player's held tile are
        # dealt from the RNG and then mutated by play (exchanges), so unlike the
        # map-derived scenarios they must be saved outright. The used-this-turn
        # record is per-turn state that start_turn rebuilds, so it is not saved.
        'helper_pile': game.helper_pile,
        'helper_held': game.helper_held,
        'must_move_robber': game.must_move_robber,
        # Main scenario: a barbarian move owed after a 7 survives a save.
        'must_move_barbarian': game.must_move_barbarian,
        'must_choose_victim': game.must_choose_victim,
        'robber_victims': game.robber_victims,
        'players_needing_discard': game.players_needing_discard,
        'free_roads_remaining': game.free_roads_remaining,
        'pending_invention': game.pending_invention,
        'pending_monopoly': game.pending_monopoly,
        # A restart in the middle of a decision must not deadlock the game, so
        # who owes what is saved along with the options they were offered. The
        # deadline is deliberately left out: it is wall-clock time, and a save
        # reloaded an hour later would expire every choice before the players
        # had a chance to answer it.
        'pending_choices': [
            {key: choice[key] for key in ('kind', 'player', 'options', 'context')}
            for choice in game.pending_choices
        ],
        'pending_dice': list(game.pending_dice) if game.pending_dice else None,
        'merchant_hex': game.merchant_hex,
        'merchant_holder': game.merchant_holder,
        # Additive like `map` below: a save without it restores an empty
        # mapping, which is a game where nobody has played a Merchant Fleet
        # this turn — so old saves load and no rate is invented for them.
        'merchant_fleet_types': game.merchant_fleet_types,
        'state_version': game.state_version,
        'longest_road_holder': game.longest_road_holder,
        'largest_army_holder': game.largest_army_holder,
        'longest_road_length': game.longest_road_length,
        'harbormaster_holder': game.harbormaster_holder,
        'harbor_points': game.harbor_points,
        # What is left of the dice deck: reshuffling it on every restart would
        # hand the table a fresh 36 and undo the evening-out they chose.
        'dice_deck': [list(pair) for pair in game.dice_deck],
        'bank': game.bank.resources,
        'dev_cards_deck': game.bank.dev_cards_deck,
        # Board: only what was decided, not the derived graph. `hidden` is the
        # Explorers & Pirates reveal state — which face-down tiles a ship has
        # turned up — so a reloaded game does not re-hide what was explored.
        'hexes': {k: {'type': h.type, 'number': h.number, 'hidden': h.hidden}
                  for k, h in game.hexes.items()},
        # Harbours twice over: `edge_ports` is the geometry, `ports` the two
        # intersections each one serves. Both are written so a save from before
        # harbours moved onto edges still restores the ports it recorded.
        'edge_ports': {k: e.port for k, e in game.edges.items() if e.port},
        'ports': {k: v.port for k, v in game.vertices.items() if v.port},
        'buildings': {k: v.building for k, v in game.vertices.items() if v.building},
        'roads_on_edges': {k: e.road for k, e in game.edges.items() if e.road},
        'ships_on_edges': {k: e.ship for k, e in game.edges.items() if e.ship},
        # The per-game id the next transport ship will take. Without it a reload
        # resets the counter to zero and the next ship built reuses an id already
        # on the board, so the two become one ship for the one-move-per-turn rule.
        'transport_ship_counter': game.transport_ship_counter,
        'cities_knights': _ck_state(game.ck),
        # Explorers & Pirates: the whole state container — pirate ships, mission
        # markers and destinations, token supplies, the undiscovered pool and its
        # number stacks. Absent (None) on a table without the expansion.
        'ep': game.ep.snapshot() if game.ep is not None else None,
        # Traders & Barbarians (Fishermen): the fish-token supply and discard,
        # each player's private fish hand, the old-boot holder, and the board's
        # fishing grounds and lake. Absent (None) on a table without the scenario.
        'tb': game.tb.snapshot() if game.tb is not None else None,
    }

    # The whole map definition, inlined, never its id. The file on disk can be
    # edited or deleted between the save and the load, and a game that
    # regenerated against a changed map would put its buildings on hexes that
    # no longer exist. A few KB, and the save stays one readable file.
    #
    # SAVE_VERSION does not move for this: the key is additive and absent means
    # "not a custom map", which is the same reasoning recorded above for edge
    # keys. Refusing old saves would throw away games in progress to add a
    # feature their players are not using.
    if game.map_definition is not None:
        saved['map'] = game.map_definition.to_json()
    return saved


def save(game: Game, path: str):
    """Write the game atomically.

    Temp file then rename: an interrupted in-place write leaves a truncated
    file that fails to parse, which would turn "the server restarted" into
    "the game is gone" — exactly what this module exists to prevent.
    """
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, 'w') as handle:
        json.dump(serialize(game), handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def deserialize(data: dict, config=None) -> Game:
    """Rebuild a Game from a save.

    The board is regenerated for its structure, then the saved decisions are
    laid back over it.
    """
    if 'save_version' not in data:
        # Not one of our saves at all — an unrelated file that happens to sit at
        # this path. Distinct from a version mismatch, which is a real save we
        # cannot read and is worth complaining about.
        raise NotASaveFile("file has no save_version; not a Catan save")
    if data['save_version'] != SAVE_VERSION:
        raise ValueError(
            f"save version {data['save_version']} is not {SAVE_VERSION}"
        )

    names = [p['name'] for p in data['players']]
    colors = {p['name']: p['color'] for p in data['players']}
    game = Game(names, list(data.get('observers', [])), colors,
                config=config, rules=data.get('rules'),
                map_definition=_saved_map(data))

    # Board decisions
    for key, saved in data.get('hexes', {}).items():
        hex_obj = game.hexes.get(key)
        if hex_obj:
            hex_obj.type = saved['type']
            hex_obj.number = saved['number']
            # Absent on pre-E&P saves, where nothing was ever hidden.
            hex_obj.hidden = saved.get('hidden', False)
    for vertex in game.vertices.values():
        vertex.port = None
        vertex.building = None
    for key, port in data.get('ports', {}).items():
        if key in game.vertices:
            game.vertices[key].port = port
    for edge in game.edges.values():
        edge.port = None
    # Older saves predate harbours on edges and carry vertex ports only. They
    # still load: the vertices above are what the trade rules read, so such a
    # game keeps the harbours it was played with.
    for key, port in data.get('edge_ports', {}).items():
        edge_key = game.canonical_edge_key(key)
        if edge_key is not None:
            game.edges[edge_key].port = port
    for key, building in data.get('buildings', {}).items():
        if key in game.vertices:
            game.vertices[key].building = building
    for edge in game.edges.values():
        edge.road = None
        edge.ship = None
    for key, ship in sorted(data.get('ships_on_edges', {}).items()):
        edge_key = game.canonical_edge_key(key)
        # A game played with ships and reloaded by a table that has since
        # turned the rule off has nowhere to put them: the open-water sides are
        # not generated at all, and a coastal side without the rule is a place
        # for a road. Dropping them beats restoring a ship nobody can move.
        if edge_key is None or not game.is_sea_edge(edge_key):
            logger.warning("saved ship on %s has no sea side on this board; dropping it", key)
            continue
        game.edges[edge_key].ship = ship

    # The next transport ship's id. A pre-counter save predates the field, so
    # derive a floor from the ids already on the board rather than risk a reused
    # one; a newer save carries the exact value.
    existing_ship_ids = [
        edge.ship['id'] for edge in game.edges.values()
        if edge.ship and isinstance(edge.ship.get('id'), int)
    ]
    game.transport_ship_counter = data.get(
        'transport_ship_counter', max(existing_ship_ids, default=0))
    for key, road in sorted(data.get('roads_on_edges', {}).items()):
        edge_key = game.canonical_edge_key(key)
        if edge_key is None:
            logger.warning("saved road on %s is not a side of this board; dropping it", key)
            continue
        # A save written while a side had two names can hold a road under each
        # of them — a position the physical game cannot represent. One of the
        # two has to go, and which one is arbitrary, so say so loudly.
        if game.edges[edge_key].road is not None:
            logger.warning(
                "saved road on %s is the hex side %s already holds; dropping it", key, edge_key
            )
            continue
        game.edges[edge_key].road = road

    # Players
    for saved in data['players']:
        player = game.get_player(saved['name'])
        if player is None:
            continue
        player.resources = dict(saved.get('resources', {}))
        player.commodities = dict(saved.get('commodities', {}))
        player.dev_cards = saved.get('dev_cards', player.dev_cards)
        player.settlements = list(saved.get('settlements', []))
        player.cities = list(saved.get('cities', []))
        player.roads = _edges_on_board(game, saved.get('roads', []))
        # Only the sides that actually took the ship back. A save reloaded by a
        # table that has since turned ships off drops them from the board, and
        # an owner still listing them would count them against the piece limit
        # and hand the browser pieces there is nothing to draw.
        player.ships = [
            edge_key
            for edge_key in _edges_on_board(game, saved.get('ships', []))
            if game.edges[edge_key].ship
            and game.edges[edge_key].ship.get('player') == player.name
        ]
        player.victory_points = saved.get('victory_points', 0)
        player.knights_played = saved.get('knights_played', 0)
        # Explorers & Pirates; absent ([]/0) on a pre-E&P save.
        player.harbor_settlements = list(saved.get('harbor_settlements', []))
        player.gold = saved.get('gold', 0)
        player.oil = saved.get('oil', 0)
        player.settlers = saved.get('settlers', 0)
        player.crews = saved.get('crews', 0)

    # Turn and phase
    for field in ('current_player_index', 'game_state', 'game_phase', 'setup_turn',
                  'setup_action', 'last_setup_settlement', 'turn_count',
                  'has_rolled_dice', 'robber_hex', 'must_move_robber',
                  'must_move_barbarian',
                  'must_choose_victim', 'robber_victims', 'players_needing_discard',
                  'free_roads_remaining', 'pending_invention', 'pending_monopoly',
                  'state_version', 'longest_road_holder', 'largest_army_holder',
                  'longest_road_length', 'harbormaster_holder', 'harbor_points',
                  'player_settlements', 'pirate_hex', 'ship_moved_this_turn',
                  'fortress_attacked_this_turn',
                  'player_islands', 'island_points', 'merchant_hex', 'merchant_holder',
                  'merchant_fleet_types', 'gift_points', 'held_gift_harbors',
                  'cloth_tokens', 'village_cloth', 'cloth_general_supply',
                  'oil_supply', 'disaster_track', 'oil_numbers_removed',
                  'oil_sequestered', 'oil_champion', 'oil_metropolises',
                  'favour_bag', 'favour_usable', 'favour_locked',
                  'favour_vp_markers', 'favour_vp_supply',
                  'wonder_choice', 'wonder_level',
                  'pirate_fleet_index', 'pirate_fortresses', 'player_warships',
                  'helper_pile', 'helper_held'):
        if field in data:
            setattr(game, field, data[field])

    # A set on the game, a list in the save: spent gift edges must not be
    # reclaimable after a reload.
    if 'claimed_gift_edges' in data:
        game.claimed_gift_edges = set(data['claimed_gift_edges'])

    # A set of {builder, opponent} pairs on the game, a list of lists in the
    # save: a network connection already rewarded must not pay again on reload.
    if 'favour_connections' in data:
        game.favour_connections = {frozenset(pair) for pair in data['favour_connections']}

    # Sets on the game, lists in the save: an established trade relation must
    # not pay its opening bolt again after a reload.
    if 'village_traders' in data:
        game.village_traders = {vertex: set(players)
                                for vertex, players in data['village_traders'].items()}

    game.dice_deck = [tuple(pair) for pair in data.get('dice_deck', [])]
    saved_dice = data.get('pending_dice')
    game.pending_dice = tuple(saved_dice) if saved_dice else None

    # Reopened rather than restored verbatim, so each choice starts its clock
    # again from the moment the game came back up. An older save carries none
    # of these and simply resumes with nothing pending.
    for saved_choice in data.get('pending_choices', []):
        game.open_choice(
            saved_choice['kind'], saved_choice['player'], saved_choice['options'],
            **saved_choice.get('context', {}),
        )

    game.bank.resources = dict(data.get('bank', game.bank.resources))
    game.bank.dev_cards_deck = dict(data.get('dev_cards_deck', game.bank.dev_cards_deck))

    # Cities & Knights
    saved_ck = data.get('cities_knights')
    if saved_ck and game.ck:
        game.ck.improvements = saved_ck.get('improvements', {})
        game.ck.city_walls = _walls_by_city(game, saved_ck.get('city_walls', {}))
        game.ck.metropolis = saved_ck.get('metropolis', game.ck.metropolis)
        game.ck.metropolis_vertex = saved_ck.get('metropolis_vertex',
                                                 game.ck.metropolis_vertex)
        game.ck.barbarian_position = saved_ck.get('barbarian_position', 0)
        game.ck.barbarians_have_attacked = saved_ck.get('barbarians_have_attacked', False)
        game.ck.defender_cards = saved_ck.get('defender_cards', {})
        game.ck.progress_decks = saved_ck.get('progress_decks', {})
        game.ck.progress_hands = saved_ck.get('progress_hands', {})
        game.ck.last_event = saved_ck.get('last_event')
        game.ck.last_red_die = saved_ck.get('last_red_die')
        game.ck.knights = {}
        for name, knights in saved_ck.get('knights', {}).items():
            rebuilt = []
            for saved_knight in knights:
                knight = ck_module.Knight(saved_knight['vertex'], saved_knight['rank'])
                knight.active = saved_knight.get('active', False)
                knight.acted_this_turn = saved_knight.get('acted_this_turn', False)
                knight.activated_this_turn = saved_knight.get('activated_this_turn', False)
                rebuilt.append(knight)
            game.ck.knights[name] = rebuilt

    # Explorers & Pirates: lay the saved state over the fresh container the
    # constructor and mission setups seeded. Absent on a pre-E&P save.
    saved_ep = data.get('ep')
    if saved_ep and game.ep is not None:
        game.ep.load(saved_ep)

    # Traders & Barbarians: lay the saved fish supply, hands and old boot back
    # over the fresh container the constructor seeded. Absent on a pre-T&B save.
    saved_tb = data.get('tb')
    if saved_tb and game.tb is not None:
        game.tb.load(saved_tb)

    return game


def load(path: str, config=None) -> Game | None:
    """Read a saved game, or None if there is nothing usable.

    A corrupt or outdated save is treated as untrusted input: report it and
    start fresh rather than resume a game whose invariants may not hold.
    """
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        data = json.load(handle)

    game = deserialize(data, config=config)

    problems = game.check_invariants()
    if problems:
        raise ValueError(f"saved game fails its own invariants: {problems}")
    return game
