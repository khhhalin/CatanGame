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
        'victory_points': player.victory_points,
        'knights_played': player.knights_played,
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
    }


def serialize(game: Game) -> dict:
    """Everything needed to rebuild this game."""
    return {
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
        'must_move_robber': game.must_move_robber,
        'must_choose_victim': game.must_choose_victim,
        'robber_victims': game.robber_victims,
        'players_needing_discard': game.players_needing_discard,
        'free_roads_remaining': game.free_roads_remaining,
        'pending_invention': game.pending_invention,
        'pending_monopoly': game.pending_monopoly,
        'state_version': game.state_version,
        'longest_road_holder': game.longest_road_holder,
        'largest_army_holder': game.largest_army_holder,
        'longest_road_length': game.longest_road_length,
        'harbormaster_holder': game.harbormaster_holder,
        'harbor_points': game.harbor_points,
        'bank': game.bank.resources,
        'dev_cards_deck': game.bank.dev_cards_deck,
        # Board: only what was decided, not the derived graph.
        'hexes': {k: {'type': h.type, 'number': h.number} for k, h in game.hexes.items()},
        # Harbours twice over: `edge_ports` is the geometry, `ports` the two
        # intersections each one serves. Both are written so a save from before
        # harbours moved onto edges still restores the ports it recorded.
        'edge_ports': {k: e.port for k, e in game.edges.items() if e.port},
        'ports': {k: v.port for k, v in game.vertices.items() if v.port},
        'buildings': {k: v.building for k, v in game.vertices.items() if v.building},
        'roads_on_edges': {k: e.road for k, e in game.edges.items() if e.road},
        'cities_knights': _ck_state(game.ck),
    }


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
                config=config, rules=data.get('rules'))

    # Board decisions
    for key, saved in data.get('hexes', {}).items():
        hex_obj = game.hexes.get(key)
        if hex_obj:
            hex_obj.type = saved['type']
            hex_obj.number = saved['number']
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
        player.victory_points = saved.get('victory_points', 0)
        player.knights_played = saved.get('knights_played', 0)

    # Turn and phase
    for field in ('current_player_index', 'game_state', 'game_phase', 'setup_turn',
                  'setup_action', 'last_setup_settlement', 'turn_count',
                  'has_rolled_dice', 'robber_hex', 'must_move_robber',
                  'must_choose_victim', 'robber_victims', 'players_needing_discard',
                  'free_roads_remaining', 'pending_invention', 'pending_monopoly',
                  'state_version', 'longest_road_holder', 'largest_army_holder',
                  'longest_road_length', 'harbormaster_holder', 'harbor_points',
                  'player_settlements'):
        if field in data:
            setattr(game, field, data[field])

    game.bank.resources = dict(data.get('bank', game.bank.resources))
    game.bank.dev_cards_deck = dict(data.get('dev_cards_deck', game.bank.dev_cards_deck))

    # Cities & Knights
    saved_ck = data.get('cities_knights')
    if saved_ck and game.ck:
        game.ck.improvements = saved_ck.get('improvements', {})
        game.ck.city_walls = saved_ck.get('city_walls', {})
        game.ck.metropolis = saved_ck.get('metropolis', game.ck.metropolis)
        game.ck.metropolis_vertex = saved_ck.get('metropolis_vertex',
                                                 game.ck.metropolis_vertex)
        game.ck.barbarian_position = saved_ck.get('barbarian_position', 0)
        game.ck.barbarians_have_attacked = saved_ck.get('barbarians_have_attacked', False)
        game.ck.defender_cards = saved_ck.get('defender_cards', {})
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
