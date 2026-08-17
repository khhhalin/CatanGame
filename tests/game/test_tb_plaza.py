"""The real Traders & Barbarians trade-hex plaza (expansions.md 697-701).

The main scenario once modelled each trade hex's central plaza as a documented
simplification: one designated land corner where the wagon delivered, two
sea-border paths, and no interior spokes. This replaces that with the printed
topology, injected through the explicit-adjacency channel (game/board.py
`_apply_explicit_pieces`): a central plaza intersection at the hex centre
carrying the trade building, four interior spoke paths from the plaza to the
hex's four land corners, and three sea-border paths that take no road.

Every fact is read off the *generated* board, never a copied literal, exactly
as the board bugs in CLAUDE.md demand: the plaza and spokes are what the dealt
board actually holds.
"""

import random

from game import map_store, maps, tb_decks
from game import rules as rules_module
from game.game import Game

TRADE_HEX_TYPES = ('castle', 'quarry', 'glassworks')


def board_game(seed=7, **overrides):
    defn = maps.parse_map(map_store.read_map('traders-barbarians'))
    chosen = dict(rules_module.TB_MAIN_RULES)
    chosen.update(overrides)
    return Game(['Alice', 'Bob'], [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)


def playing(game):
    game.game_phase = 'playing'
    game.has_rolled_dice = True
    return game


def trade_hex_keys(game):
    return sorted(k for k, h in game.hexes.items() if h.type in TRADE_HEX_TYPES)


def spokes_of(game, hex_key):
    return sorted(k for k, e in game.edges.items()
                  if e.kind == 'spoke' and hex_key in e.neighbors['hexes'])


def sea_paths_of(game, hex_key):
    return sorted(k for k, e in game.edges.items()
                  if e.kind == 'standard' and hex_key in e.neighbors['hexes']
                  and game.is_coastal_edge(k))


# --- The printed topology, read off the generated board -----------------

class TestTheTradeHexTopology:
    def test_each_trade_hex_has_a_central_plaza_and_four_spokes_and_three_sea_paths(self):
        game = board_game()
        assert len(trade_hex_keys(game)) == 3
        for hex_key in trade_hex_keys(game):
            plaza_key = maps.PLAZA_PREFIX + hex_key
            assert game.vertices[plaza_key].kind == 'plaza'
            assert game.vertices[plaza_key].neighbors['hexes'] == [hex_key]
            assert len(spokes_of(game, hex_key)) == 4
            assert len(sea_paths_of(game, hex_key)) == 3

    def test_each_spoke_runs_from_the_plaza_to_a_land_corner(self):
        """A spoke joins the plaza to a corner that stands on land, never to one
        of the two sea corners — the four buildable land corners of the hex."""
        game = board_game()
        for hex_key in trade_hex_keys(game):
            plaza_key = maps.PLAZA_PREFIX + hex_key
            for spoke in spokes_of(game, hex_key):
                ends = game.edges[spoke].neighbors['vertices']
                assert plaza_key in ends
                corner = next(v for v in ends if v != plaza_key)
                land = [h for h in game.vertices[corner].neighbors['hexes']
                        if game.hexes[h].type not in ('ocean', 'sea')]
                assert len(land) >= 2
                # The spoke is spliced back onto the standard corner's edges.
                assert spoke in game.vertices[corner].neighbors['edges']

    def test_the_scenario_registers_the_plaza_and_sea_paths_off_the_pieces(self):
        game = board_game()
        for hex_key, meta in game.tb.trade_hexes.items():
            assert meta['plaza'] == maps.PLAZA_PREFIX + hex_key
            assert meta['plaza'] in game.trade_plazas
            assert len(meta['sea_paths']) == 3
            assert all(p in game.trade_sea_paths for p in meta['sea_paths'])
            # A spoke is interior, never registered as a sea path.
            assert not any(game.edges[p].kind == 'spoke' for p in meta['sea_paths'])


# --- Delivery, roads, and the building rule -----------------------------

class TestDeliveryAndBuildingOnThePlaza:
    def test_a_wagon_delivers_when_it_stops_on_the_plaza_vertex(self):
        game = playing(board_game())
        hex_key = game._trade_hex_of_type('castle')
        plaza = maps.PLAZA_PREFIX + hex_key
        corner = game.vertices[plaza].neighbors['vertices'][0]
        game.tb.wagons['Alice'] = corner
        game.wagon_points_left = 4
        game.tb.carried_commodity['Alice'] = None
        result = game.move_wagon('Alice', plaza)
        assert result['success'], result
        assert game.tb.wagons['Alice'] == plaza
        drew = result['delivery']['picked_up']
        assert drew in tb_decks.TRADE_HEX_EXPORTS['castle']

    def test_a_road_builds_on_a_spoke_but_not_on_a_sea_border_path(self):
        game = playing(board_game())
        hex_key = game._trade_hex_of_type('quarry')
        spoke = spokes_of(game, hex_key)[0]
        corner = next(v for v in game.edges[spoke].neighbors['vertices']
                      if not v.startswith(maps.PLAZA_PREFIX))
        # Anchor a settlement on the spoke's land corner so the road connects.
        game.vertices[corner].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(corner)
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1}
        assert game.build_road('Alice', spoke)['success']
        assert game.edges[spoke].road == {'player': 'Alice'}
        # A sea-border path refuses a road (expansions.md 700).
        sea_path = sea_paths_of(game, hex_key)[0]
        assert game.build_road('Alice', sea_path)['code'] == 'TRADE_SEA_PATH'

    def test_the_plaza_carries_the_trade_building_and_refuses_a_settlement(self):
        """The plaza carries the trade building for delivery but never a player's
        settlement or city (expansions.md 699, 701) — honoured by the rule, not a
        scenario-name check."""
        game = playing(board_game())
        hex_key = game._trade_hex_of_type('glassworks')
        plaza = maps.PLAZA_PREFIX + hex_key
        assert game.trade_hex_settlement_refusal(plaza)['code'] == 'TRADE_PLAZA'
        assert game.place_settlement('Alice', plaza)['code'] == 'TRADE_PLAZA'
        assert game.vertices[plaza].building is None
