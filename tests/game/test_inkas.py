"""Catan Histories: Rise of the Inkas — the rise-and-decline of three tribes.

Source: Catan Histories: Rise of the Inkas rulebook (Klaus & Benjamin Teuber,
2018), 5f-catan-rise-of-the-inkas-rulebook.pdf. The 4/4/3 cultural goals are
stated verbatim on p. 7 ("either 2 settlements and 1 city or 4 settlements";
"either 1 settlement and 1 city or 3 settlements"), 11 markers in all (p. 8) —
OFFICIAL, not fan-sourced.

Every test names the breakage a player would notice: a tribe that never declines,
a declined network that keeps expanding, an overbuild that steals nothing, a game
that ends on the wrong condition, a board dealt the wrong hexes.
"""

import random

from game import map_store, maps
from game import rules as rules_module
from game.game import Game
from game.inkas import TRIBE_GOALS


def inkas_game(players=('Alice', 'Bob'), seed=7, **overrides):
    """A playing game on the Rise of the Inkas board with the tribe rules on."""
    defn = maps.parse_map(map_store.read_map('rise-of-the-inkas'))
    chosen = dict(rules_module.preset_rules('rise_of_the_inkas'))
    chosen['turn_order'] = 'lobby'
    chosen.update(overrides)
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.start_turn()
    return game


def _land_vertices(game):
    """Buildable intersections (bordering at least one land hex), sorted."""
    return [key for key in sorted(game.vertices)
            if game.vertices[key].neighbors['hexes']]


def _seed_building(game, name, vertex_key, tribe=1, kind='settlement', ruined=False):
    """Put a building straight on the board, bypassing placement rules."""
    building = {'type': kind, 'player': name, 'tribe': tribe}
    if ruined:
        building['ruined'] = True
    game.vertices[vertex_key].building = building
    player = game.get_player(name)
    (player.cities if kind == 'city' else player.settlements).append(vertex_key)
    return vertex_key


def _seed_road(game, name, edge_key):
    game.edges[edge_key].road = {'player': name}
    game.get_player(name).roads.append(edge_key)


def _spread_vertices(game, count, exclude=()):
    """`count` empty buildable vertices, each at least 2 apart from the others."""
    chosen = []
    taken = set(exclude)
    for key in _land_vertices(game):
        if key in taken or game.vertices[key].building is not None:
            continue
        neighbours = set(game.vertices[key].neighbors.get('vertices', []))
        if neighbours & set(chosen):
            continue
        chosen.append(key)
        taken.update(neighbours)
        taken.add(key)
        if len(chosen) == count:
            return chosen
    raise AssertionError(f'board had fewer than {count} spread-out vertices')


class TestBoardDeal:
    """The 27-hex jungle-and-ocean board, asserted against what generation dealt."""

    def test_the_board_deals_27_producing_hexes(self):
        game = inkas_game()
        producing = [h for h in game.hexes.values() if h.type != 'ocean']
        assert len(producing) == 27

    def test_the_board_carries_the_new_goods_and_the_five_resources(self):
        """The jungle (feathers), plantation (coca) and fishing ground (fishery)
        join the five resources, all dealt on the die — asserted against the
        generated board, not the map literal."""
        game = inkas_game()
        producible = game.producible_resources()
        assert {'feathers', 'coca', 'fishery'} <= producible
        assert {'wood', 'brick', 'sheep', 'wheat', 'ore'} <= producible
        # And the new goods appear in the order the client renders hands from.
        in_play = game.in_play_resource_types()
        assert in_play[:5] == ['wood', 'brick', 'sheep', 'wheat', 'ore']
        assert set(in_play[5:]) == {'feathers', 'coca', 'fishery'}


class TestApexThreshold:
    """The cultural goal that triggers decline is 4, not 3 (rulebook p. 7)."""

    def test_a_first_tribe_does_not_decline_at_three_points(self):
        game = inkas_game()
        alice = game.get_player('Alice')
        spots = _spread_vertices(game, 3)
        for spot in spots:
            _seed_building(game, 'Alice', spot, tribe=1)
        assert game.active_tribe_culture('Alice') == 3
        assert game.check_tribe_transition('Alice') is None
        assert alice.tribe == 1

    def test_a_first_tribe_declines_the_moment_it_reaches_four(self):
        game = inkas_game()
        alice = game.get_player('Alice')
        spots = _spread_vertices(game, 4)
        for spot in spots:
            _seed_building(game, 'Alice', spot, tribe=1)
        assert game.active_tribe_culture('Alice') == TRIBE_GOALS[1] == 4
        summary = game.check_tribe_transition('Alice')
        assert summary is not None
        assert alice.tribe == 2


class TestDecline:
    """What happens on decline: roads gone, buildings covered, next tribe owed."""

    def test_decline_removes_every_road_and_covers_every_building(self):
        game = inkas_game()
        alice = game.get_player('Alice')
        spots = _spread_vertices(game, 4)
        for spot in spots:
            _seed_building(game, 'Alice', spot, tribe=1)
        # A couple of Alice's roads, on real edges touching her settlements.
        for spot in spots[:2]:
            edge = game.vertices[spot].neighbors['edges'][0]
            _seed_road(game, 'Alice', edge)
        assert alice.roads

        game.check_tribe_transition('Alice')

        assert alice.roads == []
        assert all(game.edges[e].road is None for e in game.edges
                   if game.edges[e].road and game.edges[e].road.get('player') == 'Alice')
        for spot in spots:
            assert game.vertices[spot].building['ruined'] is True
        assert game.founding_player == 'Alice'

    def test_declined_buildings_still_produce_on_their_number(self):
        """A thicket-covered settlement still pays its owner (rulebook p. 7)."""
        game = inkas_game()
        # Find a settlement site beside a producing hex, ruin it, then roll that
        # hex's number and confirm the owner is still paid.
        for vertex_key in _land_vertices(game):
            hexes = [game.hexes[h] for h in game.vertices[vertex_key].neighbors['hexes']]
            producers = [h for h in hexes if h.type != 'ocean' and h.number
                         and h.number != 7 and h.type != game.robber_hex]
            if producers:
                break
        hex_obj = producers[0]
        _seed_building(game, 'Alice', vertex_key, tribe=1, ruined=True)
        before = game.get_player('Alice').resources.get(hex_obj.type, 0)
        game.distribute_resources(hex_obj.number)
        after = game.get_player('Alice').resources.get(hex_obj.type, 0)
        assert after > before

    def test_second_decline_clears_the_first_tribes_ruins(self):
        """On the second decline the leftover first-tribe pieces come off the
        board first (rulebook p. 7)."""
        game = inkas_game()
        alice = game.get_player('Alice')
        alice.tribe = 2
        # A leftover first-tribe ruin, plus a full second tribe about to peak.
        first_ruin = _spread_vertices(game, 1)[0]
        _seed_building(game, 'Alice', first_ruin, tribe=1, ruined=True)
        second = _spread_vertices(game, 4, exclude={first_ruin})
        for spot in second:
            _seed_building(game, 'Alice', spot, tribe=2)

        game.check_tribe_transition('Alice')

        assert game.vertices[first_ruin].building is None
        assert first_ruin not in alice.settlements
        assert alice.tribe == 3


class TestFounding:
    """Founding the next tribe: one free settlement, its own siting (p. 8)."""

    def test_founding_places_a_free_settlement_tagged_the_new_tribe(self):
        game = inkas_game()
        alice = game.get_player('Alice')
        alice.tribe = 2
        game.founding_player = 'Alice'
        alice.resources = {}  # no cards: the placement must be free
        culture_before = alice.culture_points
        spot = _spread_vertices(game, 1)[0]

        result = game.place_settlement('Alice', spot)

        assert result['success'] and result.get('founding')
        assert game.vertices[spot].building == {
            'type': 'settlement', 'player': 'Alice', 'tribe': 2}
        assert alice.resources == {}
        assert alice.culture_points == culture_before + 1
        assert game.founding_player is None

    def test_founding_refused_on_an_active_tribes_road_network(self):
        """A founding settlement may not be a settlement site of an active tribe —
        an intersection beside a road (rulebook p. 8, condition B)."""
        game = inkas_game()
        alice = game.get_player('Alice')
        alice.tribe = 2
        game.founding_player = 'Alice'
        # Put an opponent's road on an edge, then try to found beside it.
        edge_key = sorted(game.edges)[0]
        _seed_road(game, 'Bob', edge_key)
        beside = game.edges[edge_key].neighbors['vertices'][0]
        if not game.vertices[beside].neighbors['hexes']:
            beside = game.edges[edge_key].neighbors['vertices'][1]

        result = game.place_settlement('Alice', beside)
        assert not result['success']
        assert result['code'] == 'INVALID_PLACEMENT'
        assert game.founding_player == 'Alice'

    def test_a_declined_player_must_found_before_building_a_road(self):
        game = inkas_game()
        game.get_player('Alice').tribe = 2
        game.founding_player = 'Alice'
        edge_key = sorted(game.edges)[0]
        result = game.build_road('Alice', edge_key)
        assert result['code'] == 'MUST_FOUND_TRIBE'


class TestLockdown:
    """A tribe in decline cannot expand or upgrade (rulebook p. 7)."""

    def test_a_road_cannot_extend_from_a_ruin(self):
        game = inkas_game()
        ruin = _spread_vertices(game, 1)[0]
        _seed_building(game, 'Alice', ruin, tribe=1, ruined=True)
        # An edge that touches only the ruin — no active road or building.
        edge_key = game.vertices[ruin].neighbors['edges'][0]
        result = game.build_road('Alice', edge_key)
        assert result['code'] == 'DECLINED_NO_EXPANSION'

    def test_a_ruined_settlement_cannot_be_upgraded(self):
        game = inkas_game()
        ruin = _spread_vertices(game, 1)[0]
        _seed_building(game, 'Alice', ruin, tribe=1, ruined=True)
        game.get_player('Alice').resources = {'wheat': 5, 'ore': 5}
        result = game.upgrade_city('Alice', ruin)
        assert result['code'] == 'DECLINED_NO_EXPANSION'

    def test_a_tribe_may_build_only_one_city(self):
        """Rulebook p. 6: a player may build only 1 city per tribe."""
        game = inkas_game()
        alice = game.get_player('Alice')
        spots = _spread_vertices(game, 2)
        _seed_building(game, 'Alice', spots[0], tribe=1, kind='city')
        _seed_building(game, 'Alice', spots[1], tribe=1, kind='settlement')
        alice.resources = {'wheat': 5, 'ore': 5}
        result = game.upgrade_city('Alice', spots[1])
        assert result['code'] == 'ONE_CITY_PER_TRIBE'


class TestOverbuild:
    """An active tribe builds over a declining building (rulebook p. 7)."""

    def test_overbuilding_a_ruin_takes_the_site_from_its_owner(self):
        game = inkas_game()
        alice, bob = game.get_player('Alice'), game.get_player('Bob')
        ruin = _spread_vertices(game, 1)[0]
        _seed_building(game, 'Bob', ruin, tribe=1, ruined=True)
        # Alice reaches the ruin with an active road and can pay for a settlement.
        edge_key = game.vertices[ruin].neighbors['edges'][0]
        _seed_road(game, 'Alice', edge_key)
        alice.resources = {'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1}

        result = game.place_settlement('Alice', ruin)

        assert result['success'] and result.get('overbuilt')
        assert game.vertices[ruin].building == {
            'type': 'settlement', 'player': 'Alice', 'tribe': 1}
        assert ruin in alice.settlements
        assert ruin not in bob.settlements
        assert alice.resources == {'wood': 0, 'brick': 0, 'wheat': 0, 'sheep': 0}

    def test_overbuild_refused_without_a_road_reaching_the_ruin(self):
        game = inkas_game()
        bob = game.get_player('Bob')
        ruin = _spread_vertices(game, 1)[0]
        _seed_building(game, 'Bob', ruin, tribe=1, ruined=True)
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1}
        result = game.place_settlement('Alice', ruin)
        assert not result['success']
        assert ruin in bob.settlements  # nothing was stolen


class TestEndgame:
    """The race ends on the third tribe's apex, not a point threshold (p. 8)."""

    def test_reaching_the_third_tribes_apex_wins(self):
        game = inkas_game()
        alice = game.get_player('Alice')
        alice.tribe = 3
        for spot in _spread_vertices(game, 3):
            _seed_building(game, 'Alice', spot, tribe=3)
        assert game.tribe_culture_points('Alice', 3) == TRIBE_GOALS[3] == 3
        assert game.inka_victory('Alice') is True
        assert game.claim_victory('Alice') is not None
        assert game.game_state == 'finished'

    def test_a_third_tribe_short_of_its_apex_has_not_won(self):
        game = inkas_game()
        alice = game.get_player('Alice')
        alice.tribe = 3
        for spot in _spread_vertices(game, 2):
            _seed_building(game, 'Alice', spot, tribe=3)
        assert game.claim_victory('Alice') is None

    def test_the_plain_point_threshold_cannot_win_here(self):
        """A first-tribe player heaped with points still has not won — the
        threshold path is gated out while third-tribe victory is on."""
        game = inkas_game()
        alice = game.get_player('Alice')
        # Pile on buildings worth well over the target, all first tribe.
        for spot in _spread_vertices(game, 6):
            _seed_building(game, 'Alice', spot, tribe=1, kind='city')
        assert game.victory_points_for('Alice') >= game.victory_points_to_win
        assert alice.tribe == 1
        assert game.claim_victory('Alice') is None


class TestPreset:
    def test_the_preset_ticks_the_three_tribe_rules_and_the_map(self):
        chosen = rules_module.preset_rules('rise_of_the_inkas')
        assert chosen['tribe_decline'] is True
        assert chosen['overbuild_ruins'] is True
        assert chosen['third_tribe_victory'] is True
        assert chosen['board_map'] == 'rise-of-the-inkas'
        # The Longest Road / Largest Army points are dropped (rulebook p. 5).
        assert chosen['longest_road_card'] is False
        assert chosen['largest_army_card'] is False
