"""The Explorers & Pirates mission gesture, end to end in a real browser.

The write-side this proves is the new client gesture: a player arms the strip's
Mission button, taps one of their transport ships, then taps a target hex, and
the client infers which mission action that is (here a delivery to the Council of
Catan) and fires the matching handler. The regression it guards against is the
gesture emitting nothing, emitting the wrong action, or the delivery never
reaching the engine — none of which the unit suite can see, because the handlers
are correct on their own and it is the *client* that must call them.

It also drives the two gestures the delivery depends on through the same UI: a
transport ship is built at a harbour settlement (the strip's Build button), and
an empty ship is sailed one edge on so its arrival reveals a face-down tile
(discovery is automatic on the server side of a move). The player-visible proof
is the Fish-for-Catan marker in the panel ticking up when the haul lands.

Run: pytest tests/test_browser_ep_missions.py -m slow -q
"""

import os
import random

import pytest
from browser_harness import (
    _LAYOUT,
    Player,
    _board_point,
    _click_board_point,
    browser_session,
    next_frame,
    start_server,
    stop_server,
    wait_for_board_painted,
)
from game import map_store, maps, persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}


def _points_at(game, edge_key, hex_key):
    """Whether an end of this edge is a corner of that hex — the same reach the
    mission actions require, taken from the engine's own geometry so the fixture
    picks a position the server will accept."""
    corners = set(game._hex_corner_vertices(hex_key))
    return any(v in corners for v in game.edges[edge_key].neighbors['vertices'])


def _mission_game():
    """A started Pirate Cove game with Alice mid-turn: a harbour settlement funded
    for one ship, and a second transport ship already laden with a fish haul and
    pointing at the Council dock, so a single delivery gesture can score."""
    document = map_store.read_map('pirate-cove')
    definition = maps.parse_map(document)
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish', 'mission_spices', 'mission_pirate_lairs'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=definition)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0  # Alice to act
    game.set_dice_rolled()

    # Everything the gestures touch is kept around the central cove, so the board
    # clicks land on-canvas and clear of the side panels rather than off the rim.
    council = next(key for key, hex_obj in game.hexes.items()
                   if hex_obj.meta is not None and hex_obj.meta.docks)
    cove_corners = set(game._hex_corner_vertices(council))

    # A harbour settlement on a cove corner, funded for one ship: the Build
    # gesture's target, and central because the cove is.
    harbor = next(
        key for key in sorted(cove_corners)
        if game.vertices[key].neighbors.get('hexes')
        and game.is_coastal_settlement_site(key)
    )
    game.vertices[harbor].building = {'type': 'harbor_settlement', 'player': 'Alice', 'basin': []}
    game.get_player('Alice').harbor_settlements.append(harbor)
    game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}
    build_edge = next(edge for edge in game.vertices[harbor].neighbors['edges']
                      if game.is_sea_edge(edge))

    # Another cove side holds a laden ship pointing at the dock: the delivery.
    deliver_edge = next(
        edge_key for edge_key in sorted(game.edges)
        if game.is_sea_edge(edge_key) and edge_key != build_edge
        and _points_at(game, edge_key, council)
        and game.edges[edge_key].ship is None
    )
    game.edges[deliver_edge].ship = {
        'player': 'Alice', 'kind': 'transport', 'id': 7, 'built_turn': 0,
        'cargo': [{'type': 'fish_haul', 'size': 'large'}],
    }

    # A discovering move needs a ship already out by the fog: an empty transport
    # on a sea edge one step from another sea edge that borders a face-down hex.
    # The arrival — not the placement — is what reveals it, server-side. A hidden
    # tile is land, so a coastal vertex lists it in its hex-neighbours.
    hidden_hexes = {key for key, hex_obj in game.hexes.items() if getattr(hex_obj, 'hidden', False)}

    def _borders_fog(edge_key):
        return any(hex_key in hidden_hexes
                   for vertex in game.edges[edge_key].neighbors['vertices']
                   for hex_key in game.vertices[vertex].neighbors.get('hexes', []))

    spoken_for = {build_edge, deliver_edge}

    def _centrality(edge_key):
        return sum(abs(int(part)) for part in edge_key.split(','))

    explore_edge = ship_start_edge = None
    # Nearest the middle first, so the two taps of the move land on-canvas.
    for edge_key in sorted(game.edges, key=_centrality):
        if not game.is_sea_edge(edge_key) or game.edges[edge_key].ship is not None \
                or edge_key in spoken_for or not _borders_fog(edge_key):
            continue
        start = min(
            (other for vertex in game.edges[edge_key].neighbors['vertices']
             for other in game.vertices[vertex].neighbors['edges']
             if other != edge_key and other not in spoken_for
             and game.is_sea_edge(other) and game.edges[other].ship is None),
            key=_centrality, default=None,
        )
        if start is not None:
            explore_edge, ship_start_edge = edge_key, start
            break
    if ship_start_edge is not None:
        # Built on an earlier turn, so the client lets it move now (a ship cannot
        # move on the turn it was built, and this game's turn counter is at 0).
        game.edges[ship_start_edge].ship = {
            'player': 'Alice', 'kind': 'transport', 'id': 8, 'built_turn': -1, 'cargo': [],
        }

    # Alice already leads the Fish track by a step, so the delivery's advance from
    # 1/6 to 2/6 is an unmistakable, isolated change in the panel.
    game.ep.markers['Alice']['fish'] = 1
    game.ep.recompute_lead_cards()
    return game, build_edge, deliver_edge, council, ship_start_edge, explore_edge


def _click_key(player, kind, key):
    board_x, board_y = _board_point(player, kind, key)
    layout = player.page.evaluate(_LAYOUT)
    _click_board_point(player, board_x, board_y, layout)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def test_the_mission_gesture_delivers_a_haul_and_advances_the_track(browser, tmp_path):
    game, build_edge, deliver_edge, council, ship_start_edge, explore_edge = _mission_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = Player(browser, url, "Alice", viewport=VIEWPORT)
        alice.page.check("#role-player")
        alice.page.fill("#username", "Alice")
        alice.page.click("#join-btn")
        alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        wait_for_board_painted(alice)
        next_frame(alice.page)

        # The strip is up with the mission controls.
        assert alice.page.query_selector("#ep-mission:not(.hidden)") is not None, \
            "the E&P strip has no Mission control"
        assert "Fish for Catan" in alice.page.inner_text("#ep-missions")

        # --- Build a transport ship at the harbour settlement, through the strip.
        alice.page.click("#ep-build-ship")
        _click_key(alice, 'edge', build_edge)
        alice.page.click("#placement-confirm-yes")
        alice.page.wait_for_function(
            "edge => { const s = window.__catanDebug.getBoard().edges[edge]?.ship;"
            " return s && s.player === 'Alice'; }",
            arg=build_edge, timeout=8000,
        )

        # --- Sail a ship one edge on; the arrival reveals a face-down tile.
        assert ship_start_edge is not None, "the scenario grew no fog to explore"
        hidden_before = alice.page.evaluate(
            "() => Object.values(window.__catanDebug.getBoard().hexes)"
            ".filter(h => h.hidden).length"
        )
        alice.page.click("#ep-move-ship")
        _click_key(alice, 'edge', ship_start_edge)   # pick the explorer up
        _click_key(alice, 'edge', explore_edge)      # set it down by the fog
        alice.page.click("#placement-confirm-yes")
        alice.page.wait_for_function(
            "n => Object.values(window.__catanDebug.getBoard().hexes)"
            ".filter(h => h.hidden).length < n",
            arg=hidden_before, timeout=8000,
        )

        # --- The mission gesture: arm, tap the laden ship, tap the Council dock.
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.fish"
        ) == 1
        alice.page.click("#ep-mission")
        _click_key(alice, 'edge', deliver_edge)
        _click_key(alice, 'hex', council)

        # The haul lands: the server advances the Fish marker, and the panel — what
        # the player is looking at — now reads the higher number.
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.fish === 2",
            timeout=8000,
        )
        assert "2/6" in alice.page.inner_text("#ep-missions"), \
            alice.page.inner_text("#ep-missions")
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
