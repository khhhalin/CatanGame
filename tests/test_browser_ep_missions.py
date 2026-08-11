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
    """A started Pirate Cove game with Alice mid-turn and a mission set-up on each
    of the three cove-adjacent special hexes: a fish shoal carrying a haul, a
    pirate lair one crew short of capture, and a spice village. Each has one of
    Alice's transport ships on the cove edge beside it, so a single gesture drives
    each mission. Returns the game and the keys the taps need."""
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

    gold_edge = _edge_between(game, cove, specials['gold'])
    game.edges[gold_edge].ship = {'player': 'Alice', 'kind': 'transport', 'id': 2,
                                  'built_turn': -1,
                                  'cargo': [{'type': 'crew', 'size': 'small'},
                                            {'type': 'crew', 'size': 'small'}]}
    # One crew already on the lair, so Alice's two land to 3 and capture it.
    game.ep.lairs[specials['gold']] = {'captured': False, 'crews': {'Alice': 1}}

    spice_edge = _edge_between(game, cove, specials['spice'])
    game.edges[spice_edge].ship = {'player': 'Alice', 'kind': 'transport', 'id': 3,
                                   'built_turn': -1,
                                   'cargo': [{'type': 'crew', 'size': 'small'}]}
    game.ep.spice_hexes[specials['spice']] = {'sacks': 2, 'advantage': 'swift_voyage',
                                              'crews': []}
    return game, {
        'cove': cove, 'fish': specials['fish'], 'gold': specials['gold'],
        'spice': specials['spice'], 'fish_edge': fish_edge, 'gold_edge': gold_edge,
        'spice_edge': spice_edge,
    }


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


def test_the_gesture_lands_crews_and_captures_a_lair(browser, tmp_path):
    """land_crews_on_lair: two crews land on a lair that already held one, the
    third captures it, and Alice's Pirate Lairs marker ticks up in the panel."""
    game, ref = _scenario_game()
    alice, proc = _open(browser, tmp_path, game)
    try:
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.pirate_lairs") == 0
        alice.page.click("#ep-mission")
        _click_key(alice, 'edge', ref['gold_edge'])
        _click_key(alice, 'hex', ref['gold'])
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.pirate_lairs > 0",
            timeout=8000,
        )
        # The lair is captured and the panel shows Alice's advance on the track.
        assert alice.page.evaluate(
            "g => window.__catanDebug.getBoard().ep.lairs[g].captured", ref['gold']) is True
        assert "Pirate Lairs" in alice.page.inner_text("#ep-missions")
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)


def test_the_gesture_befriends_a_village_then_delivers_spices(browser, tmp_path):
    """befriend_spice_village grants a visible advantage in the players list, and
    deliver_spices then advances the Spices marker — both through the gesture."""
    game, ref = _scenario_game()
    alice, proc = _open(browser, tmp_path, game)
    try:
        alice.page.click("#ep-mission")
        # Befriend: a crew steps ashore, the village's advantage is earned.
        _click_key(alice, 'edge', ref['spice_edge'])
        _click_key(alice, 'hex', ref['spice'])
        alice.page.wait_for_function(
            "() => (window.__catanDebug.getBoard().ep.village_advantages.Alice || [])"
            ".includes('swift_voyage')",
            timeout=8000,
        )
        # The players list, what a player reads, now names the advantage.
        assert "swift voyage" in alice.page.inner_text("#ep-players").lower(), \
            alice.page.inner_text("#ep-players")
        # Deliver: the sack that came aboard advances the Spices track.
        _click_key(alice, 'edge', ref['spice_edge'])
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
