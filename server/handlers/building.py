"""Placing settlements, roads and cities."""

import logging

import state
from extensions import socketio
from state import (
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
)

logger = logging.getLogger(__name__)


@socketio.on('place_settlement')
def handle_place_settlement(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    # Check if player must move robber first
    if state.current_game.must_move_robber:
        reject('MUST_MOVE_ROBBER', 'You must move the robber first')
        return
    
    name = data.get('name', '')
    vertex_key = data.get('vertex', '')
    
    if not name or not vertex_key:
        return
    
    # Get current player based on phase
    if state.current_game.game_phase == "setup":
        current_player = state.current_game.players[state.current_game._get_setup_player_index()]
    else:
        current_player = state.current_game.players[state.current_game.current_player_index]

    if current_player.name != name:
        reject('NOT_YOUR_TURN', f'Only {current_player.name} can place buildings')
        return

    # Setup alternates settlement then road. Without this check a player can
    # keep placing free settlements for the whole of their setup turn.
    if state.current_game.game_phase == "setup" and state.current_game.setup_action != "settlement":
        reject('WRONG_PHASE', 'You must place a road next')
        return

    # In C&K setup the second placement is a city, so check that supply instead.
    wanted_piece = (state.current_game.setup_building_type()
                    if state.current_game.game_phase == "setup" else 'settlement')
    if not state.current_game.has_piece_available(name, wanted_piece):
        limit = (state.current_game.MAX_CITIES if wanted_piece == 'city'
                 else state.current_game.MAX_SETTLEMENTS)
        reject('NO_PIECES_LEFT', f'You have used all {limit} {wanted_piece}s')
        return

    # Check if vertex exists
    if vertex_key not in state.current_game.vertices:
        reject('INVALID_TARGET', 'Invalid vertex')
        return

    vertex = state.current_game.vertices[vertex_key]
    
    # Check if vertex already has a building
    if vertex.building is not None:
        reject('OCCUPIED', 'This location already has a building')
        return
    
    # Check if adjacent vertices have buildings (standard Catan rule)
    for adjacent_vertex_key in vertex.neighbors.get('vertices', []):
        if adjacent_vertex_key in state.current_game.vertices:
            adjacent_vertex = state.current_game.vertices[adjacent_vertex_key]
            if adjacent_vertex.building is not None:
                reject('INVALID_PLACEMENT', 'Cannot place settlement next to another settlement')
                return
    
    # Playing phase: check settlement is adjacent to player's own road
    if state.current_game.game_phase == "playing":
        has_adjacent_road = False
        vertex_edges = vertex.neighbors.get('edges', [])
        for edge_key_check in vertex_edges:
            edge_obj = state.current_game.edges.get(edge_key_check)
            if edge_obj and edge_obj.road is not None:
                if edge_obj.road.get('player') == name:
                    has_adjacent_road = True
                    break
        
        if not has_adjacent_road:
            reject('INVALID_PLACEMENT', 'Settlement must be connected to your own road')
            return
    
    # Playing phase: check and deduct cost
    if state.current_game.game_phase == "playing":
        if not state.current_game.can_afford(name, 'settlement'):
            cost = state.current_game.get_cost('settlement')
            cost_str = ', '.join(f"{v} {k}" for k, v in cost.items())
            reject('INSUFFICIENT_RESOURCES', f'Not enough resources. Need: {cost_str}')
            return
        state.current_game.deduct_cost(name, 'settlement')
    
    # Cities & Knights starts each player with a settlement *and a city*, so
    # the second setup placement builds a city rather than a settlement.
    building_type = 'settlement'
    if state.current_game.game_phase == "setup":
        building_type = state.current_game.setup_building_type()

    vertex.building = {
        'type': building_type,
        'player': name
    }

    # Track the piece on the player object for victory points
    player = state.current_game.get_player(name)
    if player:
        if building_type == 'city':
            player.cities.append(vertex_key)
        else:
            player.settlements.append(vertex_key)

    # Track for starter resources
    state.current_game.track_settlement(name, vertex_key)
    state.current_game.update_harbormaster()

    logger.info(f"Player {name} placed {building_type} at {vertex_key}")
    log_event('build', f"{name} built a {building_type}", player=name)
    
    # Setup phase logic
    if state.current_game.game_phase == "setup":
        state.current_game.last_setup_settlement = vertex_key
        
        # Check if we need to place road next (during setup, settlement always followed by road)
        if state.current_game.setup_action == "settlement":
            state.current_game.setup_action = "road"
        else:
            # Already placing road, this shouldn't happen but handle it
            state.current_game.setup_action = "settlement"
    else:
        # Normal playing phase
        state.current_game.setup_action = "settlement"
    
    # Broadcast updated board
    bump_and_broadcast()
    
    # Check for victory condition
    player = state.current_game.get_player(name)
    if player:
        vp = state.current_game.victory_points_for(name)
        if vp >= state.current_game.victory_points_to_win:
            socketio.emit('game_won', {'player': name, 'victory_points': vp})
            logger.info(f"GAME OVER! {name} wins with {vp} victory points!")
            state.current_game.game_state = "finished"

@socketio.on('place_road')
def handle_place_road(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    # Check if player must move robber first
    if state.current_game.must_move_robber:
        reject('MUST_MOVE_ROBBER', 'You must move the robber first')
        return
    
    name = data.get('name', '')
    edge_key = data.get('edge', '')
    
    if not name or not edge_key:
        return
    
    # Get current player based on phase
    if state.current_game.game_phase == "setup":
        current_player = state.current_game.players[state.current_game._get_setup_player_index()]
    else:
        current_player = state.current_game.players[state.current_game.current_player_index]
    
    if current_player.name != name:
        reject('NOT_YOUR_TURN', f'Only {current_player.name} can place buildings')
        return

    if state.current_game.game_phase == "setup" and state.current_game.setup_action != "road":
        reject('WRONG_PHASE', 'You must place a settlement first')
        return

    if not state.current_game.has_piece_available(name, 'road'):
        reject('NO_PIECES_LEFT', f'You have used all {state.current_game.MAX_ROADS} roads')
        return

    # Check if edge exists
    if edge_key not in state.current_game.edges:
        reject('INVALID_TARGET', 'Invalid edge')
        return

    edge = state.current_game.edges[edge_key]

    # Check if edge already has a road
    if edge.road is not None:
        reject('OCCUPIED', 'This location already has a road')
        return

    # Setup phase: the road must touch the settlement just placed. This is
    # unconditional — guarding it on last_setup_settlement being set meant a
    # road emitted before any settlement could land anywhere on the board.
    if state.current_game.game_phase == "setup":
        if not state.current_game.last_setup_settlement:
            reject('WRONG_PHASE', 'You must place a settlement first')
            return
        edge_vertices = edge.neighbors.get('vertices', [])
        if state.current_game.last_setup_settlement not in edge_vertices:
            reject('INVALID_PLACEMENT', 'Road must be connected to your settlement')
            return

    # Playing phase: check road is adjacent to player's own road
    if state.current_game.game_phase == "playing":
        has_adjacent_road = False
        edge_vertices = edge.neighbors.get('vertices', [])
        for vertex_key in edge_vertices:
            vertex = state.current_game.vertices.get(vertex_key)
            if vertex:
                for connected_edge_key in vertex.neighbors.get('edges', []):
                    if connected_edge_key != edge_key:
                        connected_edge = state.current_game.edges.get(connected_edge_key)
                        if connected_edge and connected_edge.road is not None:
                            # Check if it's the same player's road
                            if connected_edge.road.get('player') == name:
                                has_adjacent_road = True
                                break
            if has_adjacent_road:
                break
        
        if not has_adjacent_road:
            reject('INVALID_PLACEMENT', 'Road must be connected to your own road')
            return
    
    # Playing phase: check and deduct cost
    if state.current_game.game_phase == "playing":
        # Check if player has free roads from Two Roads card
        if state.current_game.free_roads_remaining > 0:
            state.current_game.free_roads_remaining -= 1
            logger.info(f"Free road placed! Remaining: {state.current_game.free_roads_remaining}")
        else:
            if not state.current_game.can_afford(name, 'road'):
                cost = state.current_game.get_cost('road')
                cost_str = ', '.join(f"{v} {k}" for k, v in cost.items())
                reject('INSUFFICIENT_RESOURCES', f'Not enough resources. Need: {cost_str}')
                return
            state.current_game.deduct_cost(name, 'road')
    
    # Place road (store with player name)
    edge.road = {'player': name}

    # Track the road on the player too, so the piece limit and any
    # piece-count invariant have something to count.
    road_owner = state.current_game.get_player(name)
    if road_owner is not None and edge_key not in road_owner.roads:
        road_owner.roads.append(edge_key)

    logger.info("road player=%s edge=%s", name, edge_key)
    log_event('build', f"{name} built a road", player=name)

    # Update longest road
    if state.current_game.game_phase == "playing":
        state.current_game.update_longest_road()
    
    # Setup phase: advance to next player after road
    if state.current_game.game_phase == "setup":
        state.current_game._advance_setup_turn()
    
    # Broadcast updated board
    bump_and_broadcast()

@socketio.on('upgrade_city')
def handle_upgrade_city(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return
    
    # Check if player must move robber first
    if state.current_game.must_move_robber:
        reject('MUST_MOVE_ROBBER', 'You must move the robber first')
        return
    
    name = data.get('name', '')
    vertex_key = data.get('vertex', '')
    
    if not name or not vertex_key:
        return
    
    # Get current player based on phase
    if state.current_game.game_phase == "setup":
        reject('WRONG_PHASE', 'Cannot upgrade to city during setup phase')
        return
    else:
        current_player = state.current_game.players[state.current_game.current_player_index]
    
    if current_player.name != name:
        reject('NOT_YOUR_TURN', f'Only {current_player.name} can upgrade buildings')
        return

    if not state.current_game.has_piece_available(name, 'city'):
        reject('NO_PIECES_LEFT', f'You have used all {state.current_game.MAX_CITIES} cities')
        return

    # Check if vertex exists
    if vertex_key not in state.current_game.vertices:
        reject('INVALID_TARGET', 'Invalid vertex')
        return

    vertex = state.current_game.vertices[vertex_key]

    # Check if there's a building
    if vertex.building is None:
        reject('INVALID_TARGET', 'No building at this location')
        return
    
    # Check if it's a settlement (not already a city)
    if vertex.building.get('type') != 'settlement':
        reject('INVALID_TARGET', 'Can only upgrade settlements to cities')
        return
    
    # Check if it's the player's own settlement
    if vertex.building.get('player') != name:
        reject('NOT_YOUR_PIECE', 'Can only upgrade your own settlements')
        return
    
    # Check and deduct city cost
    if not state.current_game.can_afford(name, 'city'):
        cost = state.current_game.get_cost('city')
        cost_str = ', '.join(f"{v} {k}" for k, v in cost.items())
        reject('INSUFFICIENT_RESOURCES', f'Not enough resources. Need: {cost_str}')
        return
    state.current_game.deduct_cost(name, 'city')
    
    # Upgrade to city
    vertex.building = {
        'type': 'city',
        'player': name
    }
    
    # Track city on player object for victory points
    player = state.current_game.get_player(name)
    if player and vertex_key in player.settlements:
        player.settlements.remove(vertex_key)
        player.cities.append(vertex_key)
    
    state.current_game.update_harbormaster()

    logger.info(f"Player {name} upgraded settlement to city at {vertex_key}")
    log_event('build', f"{name} upgraded a settlement to a city", player=name)
    
    # Broadcast updated board
    bump_and_broadcast()
    
    # Check for victory condition
    if player:
        vp = state.current_game.victory_points_for(name)
        if vp >= state.current_game.victory_points_to_win:
            socketio.emit('game_won', {'player': name, 'victory_points': vp})
            logger.info(f"GAME OVER! {name} wins with {vp} victory points!")
            state.current_game.game_state = "finished"
