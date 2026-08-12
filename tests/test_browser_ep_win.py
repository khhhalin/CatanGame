"""An Explorers & Pirates game reaches a declared winner, in a real browser.

The victory path nothing had run end to end: a mission delivery that carries a
player over the line, the win check firing, and the game-over banner. Rather than
bot a whole E&P game to a natural win — the generic playthrough bot does not know
how to score missions, and an unseeded finish is a coin toss the CLAUDE notes
forbid as a gate — this drives to a state *one action short* of the target and
plays the winning action through the UI, which exercises the same
claim_victory → game_won → banner path a natural win would.

The setup is deterministic: Alice holds two harbour settlements (4 points) and a
laden ship at the Council dock, level with Bob on the Fish track. Delivering
takes the sole Fish lead — its 1-point card — to exactly the 5 needed. The
player-visible proof is the GAME OVER banner every tab is shown.

Run: pytest tests/test_browser_ep_win.py -m slow -q
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
    game_is_over,
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

# The rules picker's floor for a legal game; two harbours plus one lead card
# reach it exactly, so the delivery is the winning move and nothing before it is.
VICTORY_TARGET = 5


def _win_game():
    document = map_store.read_map('pirate-cove')
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    rules['victory_target'] = VICTORY_TARGET
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    cove = next(key for key, hex_obj in game.hexes.items()
                if hex_obj.meta is not None and hex_obj.meta.docks)
    corners = set(game._hex_corner_vertices(cove))

    # Four points banked already — one short of the win. Set on the player's own
    # points rather than as placed buildings because that is what the save round
    # trips (harbour settlements are not yet serialized), and the number is all
    # this test needs: the delivery must be the move that crosses the line.
    game.get_player('Alice').victory_points = VICTORY_TARGET - 1

    # A laden ship at the dock, and the Fish track tied so the delivery takes the
    # lead card outright — the fifth point.
    deliver_edge = next(
        edge_key for edge_key in sorted(game.edges)
        if game.is_sea_edge(edge_key) and game.edges[edge_key].ship is None
        and any(vertex in corners for vertex in game.edges[edge_key].neighbors['vertices'])
    )
    game.edges[deliver_edge].ship = {
        'player': 'Alice', 'kind': 'transport', 'id': 7, 'built_turn': -1,
        'cargo': [{'type': 'fish_haul', 'size': 'large'}],
    }
    game.ep.markers['Alice']['fish'] = 1
    game.ep.markers['Bob']['fish'] = 1
    game.ep.recompute_lead_cards()
    return game, deliver_edge, cove


def _click_key(player, kind, key):
    board_x, board_y = _board_point(player, kind, key)
    layout = player.page.evaluate(_LAYOUT)
    _click_board_point(player, board_x, board_y, layout)


# --- The natural Fish-mission playthrough -----------------------------------
#
# The Fish mission is the ONE mission fully playable through the real UI: a catch
# needs only an empty ship at a shoal, and a delivery only a laden ship at a dock
# — no crew, and a crew has no client path to a ship's hold (build_crew /
# load_transport_ship / pickup_crews have no UI; build_settler /
# found_settlement_from_ship have no handler at all). So the Pirate Lairs and
# Spices missions cannot be won end to end by a player, and this natural-win proof
# is deliberately built on Fish alone. `transshipping` is likewise a declared rule
# with no engine implementation. None of those deferred paths is faked here.
#
# How natural this is: every fish MECHANIC is driven for real through the real
# handlers — the player builds a transport ship, sails one to discover a
# face-down tile, catches a haul into an empty ship, and delivers it to the
# Council to take the Fish lead card. That deciding lead card is what crosses the
# victory line. Because the Fish mission caps at its single 1-VP lead card,
# repeated deliveries cannot accrue further points, so the rest of Alice's total
# is banked ahead of time (one harbour settlement plus a point) — the delivery is
# the move that wins, exactly as a real end-game fish run would land it.

NATURAL_WIN_TARGET = 5


def _points_at(game, edge_key, hex_key):
    corners = set(game._hex_corner_vertices(hex_key))
    return any(v in corners for v in game.edges[edge_key].neighbors['vertices'])


def _edge_between(game, hex_a, hex_b):
    """The sea edge whose two ends are both shared corners of the two hexes — a
    ship there points at both, so one ship catches at the shoal then delivers at
    the dock next door."""
    corners = set(game._hex_corner_vertices(hex_a)) & set(game._hex_corner_vertices(hex_b))
    return next(
        edge_key for edge_key in sorted(game.edges)
        if game.is_sea_edge(edge_key)
        and set(game.edges[edge_key].neighbors['vertices']) <= corners
        and len(corners.intersection(game.edges[edge_key].neighbors['vertices'])) == 2
    )


def _natural_fish_win_game():
    """A Pirate Cove game one Fish delivery short of a low, seeded victory target,
    with the whole fish cycle set up to be driven for real: a harbour settlement
    funded for a build, a fog tile to discover by moving, and an empty ship beside
    a hauled shoal-and-dock so a catch then a delivery can score the deciding
    point."""
    document = map_store.read_map('pirate-cove')
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    rules['victory_target'] = NATURAL_WIN_TARGET
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    cove = next(key for key, hex_obj in game.hexes.items()
                if hex_obj.meta is not None and hex_obj.meta.docks)
    cove_corners = set(game._hex_corner_vertices(cove))

    # Reveal one fish shoal beside the cove and lay a haul on it — the catch
    # target. Every other hidden tile stays as fog for the discovering move.
    fish = next(key for key, hex_obj in game.hexes.items()
                if getattr(hex_obj, 'hidden', False) and hex_obj.type == 'fish')
    game.hexes[fish].hidden = False
    game.ep.fish_shoals[fish] = {'number': 4, 'haul': True}
    catch_edge = _edge_between(game, cove, fish)
    game.edges[catch_edge].ship = {
        'player': 'Alice', 'kind': 'transport', 'id': 1, 'built_turn': -1, 'cargo': [],
    }

    # A harbour settlement (2 VP) funded for one build, and one banked point, so
    # Alice sits at 3 — one under the target of 4. The Fish lead card the delivery
    # takes is the fourth and winning point; nothing before it crosses the line.
    harbor = next(
        key for key in sorted(cove_corners)
        if game.vertices[key].neighbors.get('hexes')
        and game.is_coastal_settlement_site(key)
    )
    game.vertices[harbor].building = {'type': 'harbor_settlement', 'player': 'Alice', 'basin': []}
    game.get_player('Alice').harbor_settlements.append(harbor)
    game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}
    game.get_player('Alice').victory_points = NATURAL_WIN_TARGET - 1 - 2
    build_edge = next(edge for edge in game.vertices[harbor].neighbors['edges']
                      if game.is_sea_edge(edge))

    # Alice and Bob are level on the Fish track, so the delivery takes the lead
    # outright — its 1-VP card is the fourth point.
    game.ep.markers['Alice']['fish'] = 0
    game.ep.markers['Bob']['fish'] = 0
    game.ep.recompute_lead_cards()

    # A ship already out by the fog for the discovering move: an empty transport
    # one step from a sea edge that borders a face-down tile. The arrival reveals
    # it, server-side; a hidden tile is land, so a coastal vertex lists it.
    hidden_hexes = {key for key, hex_obj in game.hexes.items()
                    if getattr(hex_obj, 'hidden', False)}

    def _borders_fog(edge_key):
        return any(hex_key in hidden_hexes
                   for vertex in game.edges[edge_key].neighbors['vertices']
                   for hex_key in game.vertices[vertex].neighbors.get('hexes', []))

    spoken_for = {build_edge, catch_edge}

    def _centrality(edge_key):
        return sum(abs(int(part)) for part in edge_key.split(','))

    explore_edge = ship_start_edge = None
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
        game.edges[ship_start_edge].ship = {
            'player': 'Alice', 'kind': 'transport', 'id': 2, 'built_turn': -1, 'cargo': [],
        }
    return game, {
        'cove': cove, 'fish': fish, 'catch_edge': catch_edge, 'build_edge': build_edge,
        'ship_start_edge': ship_start_edge, 'explore_edge': explore_edge,
    }


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def test_a_mission_delivery_wins_the_game_and_banners_it(browser, tmp_path):
    game, deliver_edge, cove = _win_game()
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

        # One point short, and the game still running.
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').victory_points"
        ) == VICTORY_TARGET - 1
        assert not game_is_over(alice), "the game was already over before the winning move"

        # The winning delivery, through the mission gesture.
        alice.page.click("#ep-mission")
        _click_key(alice, 'edge', deliver_edge)
        _click_key(alice, 'hex', cove)

        # The banner every tab is shown is the thing that announces the winner.
        alice.page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#notice-region *'))"
            ".some(n => n.textContent.toUpperCase().includes('GAME OVER'))",
            timeout=8000,
        )
        assert game_is_over(alice), alice.notices()
        assert any("Alice" in notice for notice in alice.notices()), alice.notices()
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)


def test_a_fished_out_game_is_won_by_playing_the_whole_cycle(browser, tmp_path):
    """The Fish mission won by driving its every mechanic through the real UI:
    build a transport ship, sail one to discover a face-down tile, catch a haul
    into an empty ship, and deliver it to the Council for the lead card that wins.
    Unlike the one-action-short fixture above (kept as a fast guard), the ship
    here starts empty and the haul is caught in play, so the victory comes out of
    real fishing rather than a hand-set final move. Seeded via CATAN_SEED for a
    reproducible board; the GAME OVER banner every tab is shown is the proof."""
    game, ref = _natural_fish_win_game()
    assert ref['ship_start_edge'] is not None, "the scenario grew no fog to explore"
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path, seed=5)
    try:
        alice = Player(browser, url, "Alice", viewport=VIEWPORT)
        alice.page.check("#role-player")
        alice.page.fill("#username", "Alice")
        alice.page.click("#join-btn")
        alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        wait_for_board_painted(alice)
        next_frame(alice.page)

        # Three points banked, one under the target, and the game still running.
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').victory_points"
        ) == NATURAL_WIN_TARGET - 1
        assert not game_is_over(alice), "the game was already over before any play"

        # --- Build a transport ship at the harbour settlement, through the strip.
        alice.page.click("#ep-build-ship")
        _click_key(alice, 'edge', ref['build_edge'])
        alice.page.click("#placement-confirm-yes")
        alice.page.wait_for_function(
            "edge => { const s = window.__catanDebug.getBoard().edges[edge]?.ship;"
            " return s && s.player === 'Alice'; }",
            arg=ref['build_edge'], timeout=8000,
        )

        # --- Sail a ship one edge on; the arrival reveals a face-down tile.
        hidden_before = alice.page.evaluate(
            "() => Object.values(window.__catanDebug.getBoard().hexes)"
            ".filter(h => h.hidden).length"
        )
        alice.page.click("#ep-move-ship")
        _click_key(alice, 'edge', ref['ship_start_edge'])
        _click_key(alice, 'edge', ref['explore_edge'])
        alice.page.click("#placement-confirm-yes")
        alice.page.wait_for_function(
            "n => Object.values(window.__catanDebug.getBoard().hexes)"
            ".filter(h => h.hidden).length < n",
            arg=hidden_before, timeout=8000,
        )

        # --- Catch the haul: the mission gesture, the empty ship, then the shoal.
        alice.page.click("#ep-mission")
        _click_key(alice, 'edge', ref['catch_edge'])
        _click_key(alice, 'hex', ref['fish'])
        alice.page.wait_for_function(
            "e => (window.__catanDebug.getBoard().edges[e].ship.cargo || [])"
            ".some(p => p.type === 'fish_haul')",
            arg=ref['catch_edge'], timeout=8000,
        )
        # Still one short: the catch scored nothing, the delivery is the win.
        assert not game_is_over(alice), "the game ended on the catch, before the delivery"

        # --- Deliver: the same ship at the Council dock. The lead card wins.
        _click_key(alice, 'edge', ref['catch_edge'])
        _click_key(alice, 'hex', ref['cove'])

        alice.page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#notice-region *'))"
            ".some(n => n.textContent.toUpperCase().includes('GAME OVER'))",
            timeout=8000,
        )
        assert game_is_over(alice), alice.notices()
        assert any("Alice" in notice for notice in alice.notices()), alice.notices()
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().ep.markers.Alice.fish") == 1
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
