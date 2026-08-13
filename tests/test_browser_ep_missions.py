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


def _edge_between(game, cove, hex_key):
    """The sea edge shared by the cove and an adjacent hex — an end of a ship
    there points at both, which is what lets one ship catch/befriend then
    deliver at the dock next door."""
    corners = set(game._hex_corner_vertices(cove)) & set(game._hex_corner_vertices(hex_key))
    return next(
        edge_key for edge_key in sorted(game.edges)
        if game.is_sea_edge(edge_key)
        and set(game.edges[edge_key].neighbors['vertices']) <= corners
        and len(corners.intersection(game.edges[edge_key].neighbors['vertices'])) == 2
    )


def _scenario_game():
    """A started Pirate Cove game with Alice mid-turn and a fish shoal carrying a
    haul on a cove-adjacent hex, with one of Alice's empty transport ships on the
    cove edge beside it — so a single gesture catches, and the next delivers at
    the dock next door. Returns the game and the keys the taps need. The Fish
    mission needs no crew, so this whole cycle is real UI, no injected cargo."""
    document = map_store.read_map('pirate-cove')
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish', 'mission_spices', 'mission_pirate_lairs'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    cove = next(key for key, hex_obj in game.hexes.items()
                if hex_obj.meta is not None and hex_obj.meta.docks)
    specials = {}
    for key, hex_obj in game.hexes.items():
        if getattr(hex_obj, 'hidden', False):
            hex_obj.hidden = False
            specials[hex_obj.type] = key

    fish_edge = _edge_between(game, cove, specials['fish'])
    game.edges[fish_edge].ship = {'player': 'Alice', 'kind': 'transport', 'id': 1,
                                  'built_turn': -1, 'cargo': []}
    game.ep.fish_shoals[specials['fish']] = {'number': 4, 'haul': True}
    return game, {'cove': cove, 'fish': specials['fish'], 'fish_edge': fish_edge}


def _harbor_and_ship_edge(game, cove, special):
    """A coastal corner shared by the cove and `special`, plus an empty sea edge
    at it. A ship built there points at both the special hex and the cove dock,
    so one ship works the mission and then delivers next door without sailing —
    and, sitting beside the harbour settlement, is where a crew is built into the
    hold. Returns (harbor_vertex, ship_edge)."""
    shared = set(game._hex_corner_vertices(cove)) & set(game._hex_corner_vertices(special))
    for vertex in sorted(shared):
        if not game.is_coastal_settlement_site(vertex):
            continue
        edge = next((e for e in game.vertices[vertex].neighbors['edges']
                     if game.is_sea_edge(e) and game.edges[e].ship is None), None)
        if edge is not None:
            return vertex, edge
    raise AssertionError('no shared coastal corner with a sea edge')


def _crew_mission_game(special_type):
    """A started Pirate Cove game staged so a crew mission can be played end to
    end through the real UI with NO injected cargo: Alice has a harbour settlement
    on a corner shared by the Council cove and the mission hex, funded to build a
    transport ship there and the crews the mission needs. The ship she builds
    points at both the mission hex and the dock, so the whole crew→ship→mission
    chain runs from one spot. Returns the game and the keys the taps need."""
    document = map_store.read_map('pirate-cove')
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'crews', 'cargo_settlers',
                 'mission_pirate_lairs', 'mission_spices'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    cove = next(key for key, hex_obj in game.hexes.items()
                if hex_obj.meta is not None and hex_obj.meta.docks)
    specials = {}
    for key, hex_obj in game.hexes.items():
        if getattr(hex_obj, 'hidden', False):
            hex_obj.hidden = False
            specials[hex_obj.type] = key
    special = specials[special_type]

    harbor, edge = _harbor_and_ship_edge(game, cove, special)
    game.vertices[harbor].building = {'type': 'harbor_settlement', 'player': 'Alice',
                                      'basin': []}
    game.get_player('Alice').harbor_settlements.append(harbor)
    # Enough to build the ship (1 wood, 1 sheep) and three crews (1 ore, 1 sheep
    # each) — every crew reaches the hold through the UI, none is injected.
    game.get_player('Alice').resources = {'wood': 1, 'sheep': 5, 'ore': 3}

    # The mission destination itself (a lair token, a stocked village) is board
    # state, not cargo — set up as the fish shoal is in the sibling fixtures.
    if special_type == 'gold':
        game.ep.lairs[special] = {'captured': False, 'crews': {}}
    elif special_type == 'spice':
        game.ep.spice_hexes[special] = {'sacks': 3, 'advantage': 'swift_voyage',
                                        'crews': []}
    return game, {'cove': cove, 'special': special, 'harbor': harbor, 'edge': edge}


def _build_ship_through_ui(alice, edge):
    """Arm the strip's Build ship, tap the sea side, confirm, and wait for it."""
    alice.page.click("#ep-build-ship")
    _click_key(alice, 'edge', edge)
    alice.page.click("#placement-confirm-yes")
    alice.page.wait_for_function(
        "e => { const s = window.__catanDebug.getBoard().edges[e]?.ship;"
        " return s && s.player === 'Alice' && s.kind === 'transport'; }",
        arg=edge, timeout=8000,
    )


def _build_crew_through_ui(alice, edge, expected_in_hold):
    """Arm the strip's Build crew, tap the ship, and wait for the hold to hold
    `expected_in_hold` crews."""
    alice.page.click("#ep-build-crew")
    _click_key(alice, 'edge', edge)
    alice.page.wait_for_function(
        "([e, n]) => ((window.__catanDebug.getBoard().edges[e].ship.cargo || [])"
        ".filter(p => p.type === 'crew').length) === n",
        arg=[edge, expected_in_hold], timeout=8000,
    )


def _pirate_seven_game():
    """A started Pirate Cove game with the E&P pirate rule on and a seven
    outstanding: Alice must place the pirate ship, the robber having been
    replaced. No ships, so a sea placement steals from nobody."""
    document = map_store.read_map('pirate-cove')
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish', 'pirate_ship_instead_of_robber'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.must_move_robber = True
    cove = next(key for key, hex_obj in game.hexes.items()
                if hex_obj.meta is not None and hex_obj.meta.docks)
    # The most central land hex, so its tap lands on-canvas clear of the panels.
    land_hex = min(
        (key for key, hex_obj in game.hexes.items()
         if hex_obj.type != 'ocean' and not getattr(hex_obj, 'hidden', False)),
        key=lambda key: sum(abs(int(part)) for part in key.split(',')),
    )
    return game, cove, land_hex


def _fish_roll_game():
    """A started Pirate Cove game with the Fish mission on and six discovered
    shoals, one for each die face 1-6, none yet carrying a haul. Whatever the
    server rolls therefore matches exactly one shoal, so a single roll always
    lands a haul from the supply — the once-per-movement gate the surface leaves
    to the client is not exercised here, only the roll's placement. Returns the
    game and the six shoal hex keys, nearest the middle first so their taps and
    pixel reads land on-canvas."""
    document = map_store.read_map('pirate-cove')
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    cove = next(key for key, hex_obj in game.hexes.items()
                if hex_obj.meta is not None and hex_obj.meta.docks)
    central = sorted(
        (key for key in game.hexes if key != cove),
        key=lambda key: sum(abs(int(part)) for part in key.split(',')),
    )
    shoals = central[:6]
    for number, key in enumerate(shoals, start=1):
        game.hexes[key].hidden = False
        game.ep.fish_shoals[key] = {'number': number, 'haul': False}
    return game, shoals


def _hex_ink(player, hex_key):
    """A signature of the canvas pixels around a hex — the sum of every channel in
    a box at its centre. A pirate ship drawing onto a flat ocean hex changes it,
    which is how a pixel-counting assertion sees the piece a player sees."""
    board_x, board_y = _board_point(player, 'hex', hex_key)
    layout = player.page.evaluate(_LAYOUT)
    return player.page.evaluate(
        """([bx, by, ox, oy]) => {
            const canvas = document.getElementById('board-canvas');
            const rect = canvas.getBoundingClientRect();
            const origin = window.BoardRenderer.clientToBoard(canvas, rect.left, rect.top);
            const far = window.BoardRenderer.clientToBoard(
                canvas, rect.left + 100, rect.top + 100);
            const sx = 100 / (far.x - origin.x), sy = 100 / (far.y - origin.y);
            const cx = (bx + ox - origin.x) * sx, cy = (by + oy - origin.y) * sy;
            const half = 34;
            const ctx = canvas.getContext('2d');
            const data = ctx.getImageData(
                Math.max(0, cx - half), Math.max(0, cy - half), half * 2, half * 2).data;
            let sum = 0;
            for (let i = 0; i < data.length; i++) sum += data[i];
            return sum;
        }""",
        [board_x, board_y, layout["offsetX"], layout["offsetY"]],
    )


def _open(browser, tmp_path, game):
    """Save the game, serve it, and bring Alice to a painted board."""
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    alice = Player(browser, url, "Alice", viewport=VIEWPORT)
    alice.page.check("#role-player")
    alice.page.fill("#username", "Alice")
    alice.page.click("#join-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    wait_for_board_painted(alice)
    next_frame(alice.page)
    return alice, proc


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


def test_the_gesture_catches_a_haul_then_delivers_it(browser, tmp_path):
    """catch_fish, then deliver_fish, both through the mission gesture. The
    delivery is only possible because the catch filled the hold, so the Fish
    marker advancing is proof of both."""
    game, ref = _scenario_game()
    alice, proc = _open(browser, tmp_path, game)
    try:
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.fish") == 0
        alice.page.click("#ep-mission")
        # Catch: the laden shoal into the empty ship.
        _click_key(alice, 'edge', ref['fish_edge'])
        _click_key(alice, 'hex', ref['fish'])
        alice.page.wait_for_function(
            "e => (window.__catanDebug.getBoard().edges[e].ship.cargo || [])"
            ".some(p => p.type === 'fish_haul')",
            arg=ref['fish_edge'], timeout=8000,
        )
        # Deliver: the same ship at the dock next door.
        _click_key(alice, 'edge', ref['fish_edge'])
        _click_key(alice, 'hex', ref['cove'])
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.fish === 1",
            timeout=8000,
        )
        assert "1/6" in alice.page.inner_text("#ep-missions"), \
            alice.page.inner_text("#ep-missions")
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)


def test_a_player_builds_crews_and_captures_a_lair_end_to_end(browser, tmp_path):
    """Pirate Lairs, from scratch through the real UI with no injected cargo: the
    player builds a transport ship at her harbour, builds a crew into its hold and
    another beside it, lands both on the lair, builds a third crew and lands it —
    the capturing crew — and her Pirate Lairs marker ticks up in the panel while
    the lair flips captured. Every crew reaches the ship through the strip's Build
    crew button; the lair starts empty."""
    game, ref = _crew_mission_game('gold')
    alice, proc = _open(browser, tmp_path, game)
    try:
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.pirate_lairs") == 0

        _build_ship_through_ui(alice, ref['edge'])
        # Two crews fill the hold; land them on the lair.
        _build_crew_through_ui(alice, ref['edge'], 1)
        _build_crew_through_ui(alice, ref['edge'], 2)
        alice.page.click("#ep-mission")
        _click_key(alice, 'edge', ref['edge'])
        _click_key(alice, 'hex', ref['special'])
        alice.page.wait_for_function(
            "g => window.__catanDebug.getBoard().ep.lairs[g].crews.Alice === 2",
            arg=ref['special'], timeout=8000,
        )
        # A third crew, built and landed, is the capture.
        _build_crew_through_ui(alice, ref['edge'], 1)
        alice.page.click("#ep-mission")
        _click_key(alice, 'edge', ref['edge'])
        _click_key(alice, 'hex', ref['special'])
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.pirate_lairs > 0",
            timeout=8000,
        )
        assert alice.page.evaluate(
            "g => window.__catanDebug.getBoard().ep.lairs[g].captured", ref['special']) is True
        assert "Pirate Lairs" in alice.page.inner_text("#ep-missions")
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)


def test_a_player_builds_a_crew_and_plays_spices_end_to_end(browser, tmp_path):
    """Spices, from scratch through the real UI with no injected cargo: the player
    builds a transport ship at her harbour, builds a crew into its hold, befriends
    the spice village next door (the crew steps ashore, a sack comes aboard and
    the advantage is earned), and delivers the sack at the Council dock to advance
    her Spices marker. The crew reaches the ship through the strip's Build crew
    button."""
    game, ref = _crew_mission_game('spice')
    alice, proc = _open(browser, tmp_path, game)
    try:
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.spices") == 0

        _build_ship_through_ui(alice, ref['edge'])
        _build_crew_through_ui(alice, ref['edge'], 1)

        # Befriend: the crew steps ashore, the village's advantage is earned.
        alice.page.click("#ep-mission")
        _click_key(alice, 'edge', ref['edge'])
        _click_key(alice, 'hex', ref['special'])
        alice.page.wait_for_function(
            "() => (window.__catanDebug.getBoard().ep.village_advantages.Alice || [])"
            ".includes('swift_voyage')",
            timeout=8000,
        )
        # The players list, what a player reads, now names the advantage.
        assert "swift voyage" in alice.page.inner_text("#ep-players").lower(), \
            alice.page.inner_text("#ep-players")
        # Deliver: the sack that came aboard advances the Spices track.
        _click_key(alice, 'edge', ref['edge'])
        _click_key(alice, 'hex', ref['cove'])
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.spices === 1",
            timeout=8000,
        )
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)


def test_a_seven_places_the_pirate_on_the_sea_and_refuses_the_land(browser, tmp_path):
    """The E&P pirate resolves a 7: a land-hex tap is refused with a cue (the
    robber is gone, there is no land move), and a sea-hex tap places the pirate
    ship — which draws onto that hex, a change the pixels show."""
    game, cove, land_hex = _pirate_seven_game()
    alice, proc = _open(browser, tmp_path, game)
    try:
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.pirate_hex.Alice") is None

        # A land tap owes nothing — no ✓ is pinned, and the player is told why.
        _click_key(alice, 'hex', land_hex)
        assert not alice.page.is_visible("#placement-confirm:not(.hidden)"), \
            "a land tap on an E&P 7 pinned a placement it cannot make"
        assert any("sea hex" in notice.lower() for notice in alice.notices()), \
            f"no cue to aim at the sea: {alice.notices()}"
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.pirate_hex.Alice") is None

        # A sea tap places the pirate. Capture the hex before and after so the
        # assertion is that the piece actually drew, not just that state changed.
        ink_before = _hex_ink(alice, cove)
        _click_key(alice, 'hex', cove)
        alice.page.click("#placement-confirm-yes")
        alice.page.wait_for_function(
            "c => window.__catanDebug.getBoard().ep.pirate_hex.Alice === c",
            arg=cove, timeout=8000,
        )
        next_frame(alice.page)
        assert _hex_ink(alice, cove) != ink_before, \
            "the pirate ship left no mark on the sea hex it was placed on"
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)


def test_the_fish_roll_lands_a_haul_on_a_matching_shoal(browser, tmp_path):
    """roll_fish_haul through the strip's Roll button: a die is rolled server-side
    and a haul comes off the supply onto the shoal whose number it matches. The
    handler is fine on its own; what the unit suite cannot see is the button
    firing it at all. The player-visible proof is twofold — the 'Fish hauls'
    supply count in the panel ticks down from six to five, and a fish-haul token
    draws onto the shoal that took it, a change the pixels show."""
    game, shoals = _fish_roll_game()
    alice, proc = _open(browser, tmp_path, game)
    try:
        # Six hauls in the supply, none on the board yet.
        assert "6 Fish hauls" in alice.page.inner_text("#ep-supply"), \
            alice.page.inner_text("#ep-supply")
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.token_supply.fish_haul") == 6
        ink_before = {key: _hex_ink(alice, key) for key in shoals}

        alice.page.click("#ep-roll-fish")

        # The supply drops by one: exactly one shoal took a haul.
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().ep.token_supply.fish_haul === 5",
            timeout=8000,
        )
        assert "5 Fish hauls" in alice.page.inner_text("#ep-supply"), \
            alice.page.inner_text("#ep-supply")

        # The haul token drew onto whichever shoal matched the roll.
        hauled = alice.page.evaluate(
            "() => Object.entries(window.__catanDebug.getBoard().ep.fish_shoals)"
            ".filter(([, s]) => s.haul).map(([k]) => k)"
        )
        assert len(hauled) == 1, hauled
        next_frame(alice.page)
        assert _hex_ink(alice, hauled[0]) != ink_before[hauled[0]], \
            "the fish haul left no mark on the shoal it landed on"
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
