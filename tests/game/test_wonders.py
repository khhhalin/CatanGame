"""The Wonders of Catan: one Wonder per player, four levels, two ways to win.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 8 "The Wonders of Catan"
(pp. 26-29, wonder cards on p. 27). The five cards' costs and start requirements
were read off the official cards (verified against the printed wonder cards):

- Cathedral    3 ore, 1 wheat, 1 brick   — a city and at least 6 victory points
- Great Bridge 1 sheep, 1 wheat, 3 wood  — a settlement at the strait
- Great Wall   1 wheat, 3 brick, 1 wood  — settlements at the wasteland
- Monument     2 ore, 3 wheat            — a city on a harbour + a route of 5
- Theater      3 sheep, 1 brick, 1 wood  — two cities

Every assertion here can fail for a reason a player would notice: a requirement
gate that lets a Wonder start too early, a cost that charges the wrong hand, the
one-Wonder-per-player rule, or the two win conditions. The board test reads the
markers off the *generated* board, never a copy of the map file.
"""

import random

from game import map_store, maps, persistence
from game import rules as rules_module
from game.game import Game
from seafarers_board import build_ships_along, give_building, ship_path


def wonders_game(players=('Alice', 'Bob'), seed=12345, actor='Alice', **overrides):
    """A Wonders game past setup, with `actor` sitting on the turn to build."""
    defn = maps.parse_map(map_store.read_map('wonders-of-catan'))
    chosen = dict(rules_module.preset_rules('wonders_of_catan'))
    chosen['turn_order'] = 'lobby'
    chosen['board_layout'] = 'custom'
    chosen['board_map'] = 'wonders-of-catan'
    chosen.update(overrides)
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = next(
        i for i, p in enumerate(game.players) if p.name == actor)
    game.start_turn()
    return game


def _touches_small_island(game, vertex_key):
    vertex = game.vertices[vertex_key]
    for hex_key in vertex.neighbors['hexes']:
        hex_obj = game.hexes.get(hex_key)
        if hex_obj and hex_obj.type != 'ocean' and not game.is_main_land(hex_key):
            return True
    return False


def _plain_vertices(game, count):
    """`count` distinct main-land intersections that carry no special points, so
    the victory-point maths in a test stays exactly the buildings it placed."""
    found = []
    for vertex_key in sorted(game.vertices):
        vertex = game.vertices[vertex_key]
        if not vertex.neighbors['hexes'] or _touches_small_island(game, vertex_key):
            continue
        if game.is_wonder_marker(vertex_key) or vertex.port is not None:
            continue
        found.append(vertex_key)
        if len(found) == count:
            return found
    raise AssertionError(f'only {len(found)} plain intersections on this board')


def _small_island_vertices(game, count):
    found = [key for key in sorted(game.vertices)
             if _touches_small_island(game, key)]
    assert len(found) >= count, f'only {len(found)} small-island intersections'
    return found[:count]


def _harbour_vertex(game):
    for vertex_key in sorted(game.vertices):
        if game.vertices[vertex_key].port is not None:
            return vertex_key
    raise AssertionError('no harbour intersection on this board')


def _plain_coastal_vertex(game):
    """A coastal intersection that is not a harbour — a plain anchor for a ship
    route that leaves the harbour requirement genuinely unmet."""
    for vertex_key in sorted(game.vertices):
        vertex = game.vertices[vertex_key]
        if vertex.port is not None or game.is_wonder_marker(vertex_key):
            continue
        if any(game.is_sea_edge(edge_key) for edge_key in vertex.neighbors['edges']):
            return vertex_key
    raise AssertionError('no plain coastal intersection on this board')


class TestTheBoardAsDealt:
    """The strait and wasteland markers are read off the generated board, so a
    marker literal that drifts from the map file is caught where the engine
    consumes it, not where it is declared."""

    def test_the_markers_deal_where_the_map_prints_them(self):
        game = wonders_game()
        assert sorted(game.wonder_strait) == ['-1,-1,2', '-1,-4,5']
        assert sorted(game.wonder_wasteland) == [
            '-1,2,-1', '-1,5,-4', '-1,8,-7', '-10,5,5', '-10,8,2']
        # Every marker is a real intersection on the dealt board — a Great Bridge
        # or Great Wall is built against geometry that exists.
        for vertex_key in game.wonder_strait | game.wonder_wasteland:
            assert vertex_key in game.vertices

    def test_the_client_state_carries_the_same_markers(self):
        game = wonders_game()
        state = game.wonders_client_state()
        assert state['strait'] == sorted(game.wonder_strait)
        assert state['wasteland'] == sorted(game.wonder_wasteland)
        assert [entry['id'] for entry in state['catalogue']] == [
            'cathedral', 'great_bridge', 'great_wall', 'monument', 'theater']
        assert state['levels'] == 4

    def test_two_gold_small_islands_are_dealt(self):
        game = wonders_game()
        gold = [key for key, hex_obj in game.hexes.items() if hex_obj.type == 'gold']
        assert len(gold) == 2
        assert all(not game.is_main_land(key) for key in gold)


class TestChoosingAWonder:
    def test_starting_a_wonder_records_the_choice_at_level_one(self):
        game = wonders_game()
        give_building(game, 'Alice', _plain_vertices(game, 2)[0], 'city')
        give_building(game, 'Alice', _plain_vertices(game, 2)[1], 'city')
        game.get_player('Alice').resources = {'sheep': 3, 'brick': 1, 'wood': 1}

        result = game.build_wonder_level('Alice', 'theater')

        assert result['success'], result
        assert result['wonder'] == 'theater'
        assert game.wonder_choice['Alice'] == 'theater'
        assert game.wonder_level_of('Alice') == 1

    def test_a_level_costs_the_hand_and_returns_it_to_the_bank(self):
        """The Cathedral level costs 3 ore, 1 wheat, 1 brick — charged from the
        hand and handed to the bank, exactly the five cards on the card."""
        game = wonders_game()
        city = _plain_vertices(game, 5)[0]
        give_building(game, 'Alice', city, 'city')
        for vertex_key in _plain_vertices(game, 5)[1:5]:
            give_building(game, 'Alice', vertex_key)  # four settlements -> 6 VP
        assert game.victory_points_for('Alice') >= 6
        game.get_player('Alice').resources = {'ore': 4, 'wheat': 2, 'brick': 1, 'wood': 9}
        game.bank.resources['ore'] = 0

        result = game.build_wonder_level('Alice', 'cathedral')

        assert result['success'], result
        hand = game.get_player('Alice').resources
        assert hand['ore'] == 1 and hand['wheat'] == 1 and hand['brick'] == 0
        assert hand['wood'] == 9, 'an unrelated resource was touched'
        # The 3 ore came back to the drained bank rather than vanishing.
        assert game.bank.resources['ore'] == 3


class TestRequirements:
    """Each Wonder is refused until its printed requirement is met, then allowed.
    Break the matching gate in wonders.py and exactly one of these turns red."""

    def test_theater_needs_two_cities(self):
        game = wonders_game()
        cities = _plain_vertices(game, 2)
        give_building(game, 'Alice', cities[0], 'city')
        game.get_player('Alice').resources = {'sheep': 3, 'brick': 1, 'wood': 1}

        refused = game.build_wonder_level('Alice', 'theater')
        assert refused['code'] == 'WONDER_REQUIREMENT', refused

        give_building(game, 'Alice', cities[1], 'city')
        assert game.build_wonder_level('Alice', 'theater')['success']

    def test_cathedral_needs_a_city_and_six_victory_points(self):
        game = wonders_game()
        spots = _plain_vertices(game, 5)
        give_building(game, 'Alice', spots[0], 'city')  # 1 city, only 2 VP
        game.get_player('Alice').resources = {'ore': 3, 'wheat': 1, 'brick': 1}

        refused = game.build_wonder_level('Alice', 'cathedral')
        assert refused['code'] == 'WONDER_REQUIREMENT', refused

        for vertex_key in spots[1:5]:
            give_building(game, 'Alice', vertex_key)  # +4 VP -> 6
        assert game.victory_points_for('Alice') >= 6
        assert game.build_wonder_level('Alice', 'cathedral')['success']

    def test_great_bridge_needs_a_settlement_at_the_strait(self):
        game = wonders_game()
        game.get_player('Alice').resources = {'sheep': 1, 'wheat': 1, 'wood': 3}

        refused = game.build_wonder_level('Alice', 'great_bridge')
        assert refused['code'] == 'WONDER_REQUIREMENT', refused

        give_building(game, 'Alice', sorted(game.wonder_strait)[0])
        assert game.build_wonder_level('Alice', 'great_bridge')['success']

    def test_great_wall_needs_two_settlements_at_the_wasteland(self):
        game = wonders_game()
        marks = sorted(game.wonder_wasteland)
        game.get_player('Alice').resources = {'wheat': 1, 'brick': 3, 'wood': 1}

        give_building(game, 'Alice', marks[0])  # one wasteland settlement, plural asks two
        refused = game.build_wonder_level('Alice', 'great_wall')
        assert refused['code'] == 'WONDER_REQUIREMENT', refused

        give_building(game, 'Alice', marks[1])
        assert game.build_wonder_level('Alice', 'great_wall')['success']

    def test_monument_a_five_route_without_a_harbour_city_is_not_enough(self):
        """A trade route of five, but the harbour half of the requirement unmet:
        a settlement on the coast is not the city on a harbour the card asks."""
        game = wonders_game()
        game.get_player('Alice').resources = {'ore': 2, 'wheat': 3}
        anchor = _plain_coastal_vertex(game)
        give_building(game, 'Alice', anchor)  # a settlement, and not on a harbour
        edges, _ = ship_path(game, anchor, 5)
        build_ships_along(game, 'Alice', edges)
        assert game.calculate_longest_road('Alice') >= 5

        refused = game.build_wonder_level('Alice', 'monument')
        assert refused['code'] == 'WONDER_REQUIREMENT', refused

    def test_monument_needs_the_route_a_full_five_long(self):
        """A harbour city with a route of four is refused; the fifth link allows
        it — the exact threshold on the card, not four and not six."""
        game = wonders_game()
        game.get_player('Alice').resources = {'ore': 2, 'wheat': 3}
        harbour = _harbour_vertex(game)
        give_building(game, 'Alice', harbour, 'city')
        edges, _ = ship_path(game, harbour, 5)
        build_ships_along(game, 'Alice', edges[:4])
        assert game.calculate_longest_road('Alice') == 4

        refused = game.build_wonder_level('Alice', 'monument')
        assert refused['code'] == 'WONDER_REQUIREMENT', refused

        build_ships_along(game, 'Alice', edges[4:])  # the fifth link
        assert game.calculate_longest_road('Alice') == 5
        assert game.build_wonder_level('Alice', 'monument')['success']


class TestOneWonderPerPlayerAndPerTable:
    def test_a_player_may_not_switch_to_a_second_wonder(self):
        game = wonders_game()
        cities = _plain_vertices(game, 2)
        for vertex_key in cities:
            give_building(game, 'Alice', vertex_key, 'city')
        give_building(game, 'Alice', _small_island_vertices(game, 1)[0])  # +6 VP room
        game.get_player('Alice').resources = {'sheep': 3, 'brick': 1, 'wood': 1,
                                              'ore': 3, 'wheat': 1}
        assert game.build_wonder_level('Alice', 'theater')['success']

        # Even with a different Wonder's requirement met, Alice is committed.
        refused = game.build_wonder_level('Alice', 'cathedral')
        assert refused['code'] == 'WONDER_CHOSEN', refused

    def test_a_wonder_another_player_started_is_taken(self):
        game = wonders_game(actor='Alice')
        for vertex_key in _plain_vertices(game, 4)[:2]:
            give_building(game, 'Alice', vertex_key, 'city')
        game.get_player('Alice').resources = {'sheep': 3, 'brick': 1, 'wood': 1}
        assert game.build_wonder_level('Alice', 'theater')['success']

        # Bob meets the same requirement but the Theater is already claimed.
        game.current_player_index = next(
            i for i, p in enumerate(game.players) if p.name == 'Bob')
        game.start_turn()
        for vertex_key in _plain_vertices(game, 8)[4:6]:
            give_building(game, 'Bob', vertex_key, 'city')
        game.get_player('Bob').resources = {'sheep': 3, 'brick': 1, 'wood': 1}
        refused = game.build_wonder_level('Bob', 'theater')
        assert refused['code'] == 'WONDER_TAKEN', refused


class TestWinning:
    def test_finishing_the_fourth_level_wins_however_few_the_points(self):
        game = wonders_game()
        for vertex_key in _plain_vertices(game, 2):
            give_building(game, 'Alice', vertex_key, 'city')
        for _ in range(4):
            game.get_player('Alice').resources = {'sheep': 3, 'brick': 1, 'wood': 1}
            result = game.build_wonder_level('Alice', 'theater')
            assert result['success'], result
        assert result['level'] == 4 and result['finished']
        assert game.wonder_level_of('Alice') == 4
        # Far short of the 10-point target, but a finished Wonder wins outright.
        assert game.victory_points_for('Alice') < 10
        assert game.claim_victory('Alice') == game.victory_points_for('Alice')
        assert game.game_state == 'finished'

    def test_ten_points_win_only_with_a_strictly_higher_wonder_level(self):
        game = wonders_game()
        game.wonder_level = {'Alice': 2, 'Bob': 1}
        assert game.wonder_victory('Alice', 10, 10) is True
        # Level equal to an opponent: not strictly higher, no win at the target.
        game.wonder_level = {'Alice': 1, 'Bob': 1}
        assert game.wonder_victory('Alice', 10, 10) is False
        # Ten points with no Wonder ahead of anyone is not a win on its own.
        game.wonder_level = {'Alice': 0, 'Bob': 0}
        assert game.wonder_victory('Alice', 10, 10) is False
        # Below the target, a higher level still does not win by points.
        game.wonder_level = {'Alice': 2, 'Bob': 1}
        assert game.wonder_victory('Alice', 9, 10) is False

    def test_ten_points_alone_do_not_end_a_wonders_game(self):
        """The plain threshold win is gated out under the scenario: a leader at
        the target with no Wonder ahead of the table has not won."""
        game = wonders_game()
        for vertex_key in _plain_vertices(game, 6)[:4]:
            give_building(game, 'Alice', vertex_key, 'city')  # 4 cities -> 8 VP
        for vertex_key in _plain_vertices(game, 6)[4:6]:
            give_building(game, 'Alice', vertex_key)          # +2 -> 10 VP
        assert game.victory_points_for('Alice') >= 10
        assert game.wonder_level_of('Alice') == 0
        assert game.claim_victory('Alice') is None
        assert game.game_state != 'finished'


class TestSmallIslandPoints:
    def test_each_small_island_building_is_a_special_point(self):
        game = wonders_game()
        islands = _small_island_vertices(game, 2)
        base = game.victory_points_for('Alice')
        give_building(game, 'Alice', islands[0])
        assert game.wonder_island_victory_points('Alice') == 1
        assert game.victory_points_for('Alice') == base + 1 + 1  # settlement + island

        give_building(game, 'Alice', islands[1])
        assert game.wonder_island_victory_points('Alice') == 2


class TestPersistence:
    def test_wonder_progress_survives_a_restart(self, tmp_path):
        """Which Wonder each player started and how high they have raised it is
        decided state — losing it on reload loses the race the table ran."""
        game = wonders_game()
        for vertex_key in _plain_vertices(game, 2):
            give_building(game, 'Alice', vertex_key, 'city')
        game.get_player('Alice').resources = {'sheep': 3, 'brick': 1, 'wood': 1}
        assert game.build_wonder_level('Alice', 'theater')['success']

        path = str(tmp_path / 'game.json')
        persistence.save(game, path)
        restored = persistence.load(path)

        assert restored.wonder_choice['Alice'] == 'theater'
        assert restored.wonder_level_of('Alice') == 1
        assert sorted(restored.wonder_strait) == sorted(game.wonder_strait)
        assert sorted(restored.wonder_wasteland) == sorted(game.wonder_wasteland)
