"""Cities & Knights: commodities, improvements, knights, barbarians."""

import random

import pytest
from game import cities_knights as ck
from game import rules as rules_module
from game.game import Game


def ck_game(extra=None, players=('Alice', 'Bob')):
    rules = rules_module.preset_rules('cities_and_knights')
    rules.update(extra or {})
    return Game(list(players), [], rng=random.Random(7), rules=rules)


def city_on(game, player_name, terrain):
    """Put a city next to a hex of `terrain` and return (vertex, hex)."""
    for vertex_key, vertex in game.vertices.items():
        if vertex.building:
            continue
        for hex_key in vertex.neighbors.get('hexes', []):
            hex_obj = game.hexes.get(hex_key)
            if hex_obj and hex_obj.type == terrain and hex_obj.number:
                vertex.building = {'type': 'city', 'player': player_name}
                game.get_player(player_name).cities.append(vertex_key)
                return vertex_key, hex_obj
    pytest.skip(f"no numbered {terrain} hex on this board")


class TestTheExpansionIsJustRules:
    def test_none_of_it_is_on_by_default(self):
        assert Game(['A', 'B'], [], rng=random.Random(1)).ck is None

    def test_the_preset_ticks_all_of_it(self):
        assert ck_game().ck is not None

    def test_the_lobby_number_wins_over_the_preset(self):
        """Reported: "10 vp needed setting got overridden".

        The expansion used to hard-assign 13 whatever the table had agreed on.
        A preset may propose a length; only the table sets one.
        """
        assert ck_game({'victory_target': 10}).victory_points_to_win == 10

    def test_knights_can_be_taken_without_commodities(self):
        """The whole point of decomposing it: half the expansion is a choice."""
        game = Game(['A', 'B'], [], rng=random.Random(1),
                    rules={'knights': True, 'barbarians': True, 'city_walls': True})
        assert game.ck is not None
        assert game.rules['commodities'] is False
        assert game.rules['city_improvements'] is False


class TestCommodities:
    def test_a_city_on_pasture_yields_wool_and_cloth(self):
        game = ck_game()
        _, hex_obj = city_on(game, 'Alice', 'sheep')
        game.distribute_resources(hex_obj.number)
        player = game.get_player('Alice')
        assert player.resources.get('sheep') == 1
        assert player.commodities.get('cloth') == 1

    def test_a_city_on_mountain_yields_ore_and_coin(self):
        game = ck_game()
        _, hex_obj = city_on(game, 'Alice', 'ore')
        game.distribute_resources(hex_obj.number)
        player = game.get_player('Alice')
        assert player.resources.get('ore') == 1
        assert player.commodities.get('coin') == 1

    def test_a_city_on_forest_yields_wood_and_paper(self):
        game = ck_game()
        _, hex_obj = city_on(game, 'Alice', 'wood')
        game.distribute_resources(hex_obj.number)
        player = game.get_player('Alice')
        assert player.resources.get('wood') == 1
        assert player.commodities.get('paper') == 1

    def test_a_city_on_fields_still_yields_two_grain(self):
        """Fields and hills have no commodity, so a city there is unchanged.

        Only wheat is asserted: the same vertex may also touch another hex
        bearing the same number, which legitimately produces its own commodity.
        """
        game = ck_game()
        _, hex_obj = city_on(game, 'Alice', 'wheat')
        game.distribute_resources(hex_obj.number)
        player = game.get_player('Alice')
        assert player.resources.get('wheat') == 2
        assert 'wheat' not in player.commodities, "fields yield no commodity"

    def test_a_settlement_never_produces_a_commodity(self):
        game = ck_game()
        for vertex_key, vertex in game.vertices.items():
            if vertex.building:
                continue
            for hex_key in vertex.neighbors.get('hexes', []):
                hex_obj = game.hexes.get(hex_key)
                if hex_obj and hex_obj.type == 'sheep' and hex_obj.number:
                    vertex.building = {'type': 'settlement', 'player': 'Alice'}
                    game.get_player('Alice').settlements.append(vertex_key)
                    game.distribute_resources(hex_obj.number)
                    assert game.get_player('Alice').resources.get('sheep') == 1
                    assert game.get_player('Alice').commodities == {}
                    return
        pytest.skip("no numbered pasture on this board")

    def test_commodities_count_toward_the_discard_limit(self):
        game = ck_game()
        player = game.get_player('Alice')
        player.resources = {'wood': 4}
        player.commodities = {'cloth': 4}
        game.check_discard_required()
        assert game.players_needing_discard['Alice'] == 4

    def test_the_base_game_has_no_commodities(self):
        game = Game(['A', 'B'], [], rng=random.Random(1))
        for vertex_key, vertex in game.vertices.items():
            if vertex.building:
                continue
            for hex_key in vertex.neighbors.get('hexes', []):
                hex_obj = game.hexes.get(hex_key)
                if hex_obj and hex_obj.type == 'sheep' and hex_obj.number:
                    vertex.building = {'type': 'city', 'player': 'A'}
                    game.get_player('A').cities.append(vertex_key)
                    game.distribute_resources(hex_obj.number)
                    assert game.get_player('A').resources.get('sheep') == 2
                    assert game.get_player('A').commodities == {}
                    return
        pytest.skip("no numbered pasture on this board")


class TestImprovements:
    def _with_city(self, game, name='Alice'):
        game.get_player(name).cities.append('some-city')
        return game.get_player(name)

    def test_a_city_is_required(self):
        game = ck_game()
        game.get_player('Alice').commodities = {'cloth': 5}
        result = game.buy_improvement('Alice', ck.TRADE)
        assert not result['success']
        assert 'city' in result['error']

    def test_level_one_costs_one_commodity(self):
        game = ck_game()
        player = self._with_city(game)
        player.commodities = {'cloth': 1}
        assert game.buy_improvement('Alice', ck.TRADE)['success']
        assert game.ck.level('Alice', ck.TRADE) == 1
        assert player.commodities['cloth'] == 0

    def test_costs_escalate_by_level(self):
        game = ck_game()
        player = self._with_city(game)
        player.commodities = {'cloth': 15}  # 1+2+3+4+5
        for expected in range(1, 6):
            assert game.buy_improvement('Alice', ck.TRADE)['success']
            assert game.ck.level('Alice', ck.TRADE) == expected
        assert player.commodities['cloth'] == 0

    def test_cannot_go_past_level_five(self):
        game = ck_game()
        player = self._with_city(game)
        player.commodities = {'cloth': 30}
        for _ in range(5):
            game.buy_improvement('Alice', ck.TRADE)
        result = game.buy_improvement('Alice', ck.TRADE)
        assert not result['success']
        assert 'level 5' in result['error']

    def test_each_track_uses_its_own_commodity(self):
        game = ck_game()
        self._with_city(game).commodities = {'coin': 1}
        assert not game.buy_improvement('Alice', ck.TRADE)['success'], "trade needs cloth"
        assert game.buy_improvement('Alice', ck.POLITICS)['success']

    def test_level_three_unlocks_the_ability(self):
        game = ck_game()
        self._with_city(game).commodities = {'coin': 6}
        for _ in range(3):
            game.buy_improvement('Alice', ck.POLITICS)
        assert game.ck.has_ability('Alice', ck.POLITICS), "Fortress is up"


class TestMetropolis:
    def _reach(self, game, name, track, level):
        player = game.get_player(name)
        # A distinct city per metropolis: claiming one needs a city that is not
        # already a metropolis.
        player.cities.append(f"{name}-city-{track}")
        commodity = ck.IMPROVEMENT_TRACKS[track]['commodity']
        player.commodities = {commodity: 99}
        for _ in range(level):
            game.buy_improvement(name, track)

    def test_level_four_claims_it(self):
        game = ck_game()
        self._reach(game, 'Alice', ck.TRADE, 4)
        assert game.ck.metropolis[ck.TRADE] == 'Alice'

    def test_it_is_worth_two_extra_points(self):
        game = ck_game()
        self._reach(game, 'Alice', ck.TRADE, 4)
        # 1 city = 2 points, plus 2 for the metropolis.
        assert game.victory_points_for('Alice') == 4

    def test_a_rival_at_four_cannot_take_it(self):
        game = ck_game()
        self._reach(game, 'Alice', ck.TRADE, 4)
        self._reach(game, 'Bob', ck.TRADE, 4)
        assert game.ck.metropolis[ck.TRADE] == 'Alice'

    def test_a_rival_at_five_takes_it(self):
        game = ck_game()
        self._reach(game, 'Alice', ck.TRADE, 4)
        self._reach(game, 'Bob', ck.TRADE, 5)
        assert game.ck.metropolis[ck.TRADE] == 'Bob'

    def test_the_holder_at_five_can_never_lose_it(self):
        game = ck_game()
        self._reach(game, 'Alice', ck.TRADE, 5)
        self._reach(game, 'Bob', ck.TRADE, 5)
        assert game.ck.metropolis[ck.TRADE] == 'Alice'

    def test_one_player_may_hold_several(self):
        game = ck_game()
        self._reach(game, 'Alice', ck.TRADE, 4)
        self._reach(game, 'Alice', ck.SCIENCE, 4)
        assert game.ck.metropolis_count('Alice') == 2


class TestKnights:
    def _road_and_vertex(self, game, name='Alice'):
        """Give the player a road and return a vacant vertex touching it."""
        for edge_key, edge in game.edges.items():
            if edge.road:
                continue
            vertices = edge.neighbors.get('vertices', [])
            if not vertices:
                continue
            edge.road = {'player': name}
            game.get_player(name).roads.append(edge_key)
            for vertex_key in vertices:
                if game.vertices.get(vertex_key) and not game.vertices[vertex_key].building:
                    return vertex_key
        pytest.fail("no usable edge")

    def test_building_costs_sheep_and_ore(self):
        game = ck_game()
        vertex = self._road_and_vertex(game)
        player = game.get_player('Alice')
        player.resources = {'sheep': 1, 'ore': 1}
        assert game.build_knight('Alice', vertex)['success']
        assert player.resources == {'sheep': 0, 'ore': 0}

    def test_a_new_knight_is_inactive(self):
        game = ck_game()
        vertex = self._road_and_vertex(game)
        game.get_player('Alice').resources = {'sheep': 1, 'ore': 1}
        game.build_knight('Alice', vertex)
        assert game.ck.knight_at(vertex)[1].active is False

    def test_a_knight_must_touch_your_own_road(self):
        game = ck_game()
        self._road_and_vertex(game)
        game.get_player('Alice').resources = {'sheep': 1, 'ore': 1}
        stranded = next(
            k
            for k, v in game.vertices.items()
            if not v.building and not game._touches_own_road('Alice', k)
        )
        result = game.build_knight('Alice', stranded)
        assert not result['success']

    def test_activating_costs_wheat(self):
        game = ck_game()
        vertex = self._road_and_vertex(game)
        player = game.get_player('Alice')
        player.resources = {'sheep': 1, 'ore': 1, 'wheat': 1}
        game.build_knight('Alice', vertex)
        assert game.activate_knight('Alice', vertex)['success']
        assert player.resources['wheat'] == 0
        assert game.ck.knight_at(vertex)[1].active is True

    def test_a_knight_cannot_act_the_turn_it_is_activated(self):
        game = ck_game()
        vertex = self._road_and_vertex(game)
        player = game.get_player('Alice')
        player.resources = {'sheep': 1, 'ore': 1, 'wheat': 1}
        game.build_knight('Alice', vertex)
        game.activate_knight('Alice', vertex)
        knight = game.ck.knight_at(vertex)[1]
        assert not knight.can_act()

    def test_a_new_turn_frees_the_knight_to_act(self):
        game = ck_game()
        vertex = self._road_and_vertex(game)
        player = game.get_player('Alice')
        player.resources = {'sheep': 1, 'ore': 1, 'wheat': 1}
        game.build_knight('Alice', vertex)
        game.activate_knight('Alice', vertex)
        game.ck.start_turn()
        assert game.ck.knight_at(vertex)[1].can_act()

    def test_promotion_to_mighty_needs_the_fortress(self):
        game = ck_game()
        vertex = self._road_and_vertex(game)
        player = game.get_player('Alice')
        player.resources = {'sheep': 9, 'ore': 9}
        game.build_knight('Alice', vertex)
        assert game.promote_knight('Alice', vertex)['success'], (
            "basic -> strong is free of prerequisites"
        )

        result = game.promote_knight('Alice', vertex)
        assert not result['success']
        assert 'Fortress' in result['error']

    def test_the_fortress_unlocks_mighty(self):
        game = ck_game()
        vertex = self._road_and_vertex(game)
        player = game.get_player('Alice')
        player.resources = {'sheep': 9, 'ore': 9}
        player.cities.append('a-city')
        player.commodities = {'coin': 6}
        for _ in range(3):
            game.buy_improvement('Alice', ck.POLITICS)

        game.build_knight('Alice', vertex)
        game.promote_knight('Alice', vertex)
        assert game.promote_knight('Alice', vertex)['success']
        assert game.ck.knight_at(vertex)[1].rank == ck.MIGHTY

    def test_only_active_knights_defend(self):
        game = ck_game()
        vertex = self._road_and_vertex(game)
        player = game.get_player('Alice')
        player.resources = {'sheep': 1, 'ore': 1, 'wheat': 1}
        game.build_knight('Alice', vertex)
        assert game.ck.total_knight_strength() == 0, "inactive knights contribute nothing"
        game.activate_knight('Alice', vertex)
        assert game.ck.total_knight_strength() == 1


class TestBarbarians:
    def test_the_ship_arrives_after_seven_steps(self):
        game = ck_game()
        for _ in range(ck.BARBARIAN_TRACK_LENGTH - 1):
            assert not game.ck.advance_barbarians()
        assert game.ck.advance_barbarians(), "the seventh step is the attack"

    def test_defence_wins_on_a_tie(self):
        """The rule is 'greater than or equal', so equal strength holds."""
        game = ck_game()
        game.get_player('Alice').cities = ['c1']
        game.ck.knights['Alice'] = [ck.Knight('v1')]
        game.ck.knights['Alice'][0].active = True
        result = game.resolve_barbarian_attack()
        assert result['attack'] == 1
        assert result['defence'] == 1
        assert result['won']

    def test_the_top_defender_gets_a_victory_point(self):
        game = ck_game()
        game.get_player('Alice').cities = ['c1']
        knight = ck.Knight('v1', ck.STRONG)
        knight.active = True
        game.ck.knights['Alice'] = [knight]
        result = game.resolve_barbarian_attack()
        assert result['defenders'] == ['Alice']
        assert game.ck.defender_cards['Alice'] == 1
        assert game.victory_points_for('Alice') == 3  # city 2 + defender 1

    def test_a_tie_for_top_defender_awards_no_card(self):
        game = ck_game()
        for name in ('Alice', 'Bob'):
            game.get_player(name).cities = []
            knight = ck.Knight(f'{name}-v')
            knight.active = True
            game.ck.knights[name] = [knight]
        result = game.resolve_barbarian_attack()
        assert sorted(result['defenders']) == ['Alice', 'Bob']
        assert game.ck.defender_cards['Alice'] == 0

    def test_losing_turns_a_city_back_into_a_settlement(self):
        game = ck_game()
        alice = game.get_player('Alice')
        alice.cities = ['c1']
        game.vertices[list(game.vertices)[0]].building = {'type': 'city', 'player': 'Alice'}
        alice.cities = [list(game.vertices)[0]]
        result = game.resolve_barbarian_attack()
        assert not result['won'], "no knights means the barbarians win"
        assert result['pillaged'] == ['Alice']
        assert alice.cities == []
        assert len(alice.settlements) == 1

    def test_a_player_with_no_cities_is_untouched(self):
        game = ck_game()
        game.get_player('Alice').cities = [list(game.vertices)[0]]
        game.vertices[list(game.vertices)[0]].building = {'type': 'city', 'player': 'Alice'}
        result = game.resolve_barbarian_attack()
        assert 'Bob' not in result['pillaged']

    def test_every_knight_is_spent_afterwards(self):
        game = ck_game()
        knight = ck.Knight('v1')
        knight.active = True
        game.ck.knights['Alice'] = [knight]
        game.resolve_barbarian_attack()
        assert knight.active is False

    def test_the_track_resets(self):
        game = ck_game()
        game.ck.barbarian_position = 7
        game.resolve_barbarian_attack()
        assert game.ck.barbarian_position == 0
        assert game.ck.barbarians_have_attacked

    def test_the_event_die_has_three_barbarian_faces(self):
        assert ck.EVENT_FACES.count(ck.EVENT_BARBARIAN) == 3
        assert len(ck.EVENT_FACES) == 6


class TestCityWalls:
    def test_a_wall_costs_two_brick(self):
        game = ck_game()
        player = game.get_player('Alice')
        player.cities = ['c1']
        player.resources = {'brick': 2}
        assert game.build_city_wall('Alice', 'c1')['success']
        assert player.resources['brick'] == 0

    def test_a_wall_raises_the_hand_limit_by_two(self):
        game = ck_game()
        player = game.get_player('Alice')
        player.cities = ['c1']
        player.resources = {'brick': 2}
        game.build_city_wall('Alice', 'c1')

        player.resources = {'wood': 9}
        game.check_discard_required()
        assert 'Alice' not in game.players_needing_discard, "limit is now 9"

        player.resources = {'wood': 10}
        game.check_discard_required()
        assert game.players_needing_discard['Alice'] == 5

    def test_at_most_three_walls(self):
        game = ck_game()
        player = game.get_player('Alice')
        player.cities = ['c1']
        player.resources = {'brick': 99}
        for _ in range(ck.MAX_CITY_WALLS):
            assert game.build_city_wall('Alice', 'c1')['success']
        assert not game.build_city_wall('Alice', 'c1')['success']


class TestSerialization:

    def test_a_player_sees_only_their_own_commodities(self):
        game = ck_game()
        game.get_player('Bob').commodities = {'cloth': 3}
        board = game.get_board_data(viewer='Alice')
        bob = next(p for p in board['players'] if p['name'] == 'Bob')
        assert bob['commodities'] is None
        assert bob['commodity_count'] == 3


class TestSetupPhase:
    """C&K starts each player with a settlement AND a city, not two settlements."""

    def test_the_first_placement_is_a_settlement(self):
        game = ck_game()
        game.start()
        assert game.setup_building_type() == 'settlement'

    def test_the_second_placement_is_a_city(self):
        game = ck_game()
        game.start()
        game.setup_turn = len(game.players)  # second round
        assert game.setup_building_type() == 'city'

    def test_the_base_game_places_two_settlements(self):
        game = Game(['A', 'B'], [], rng=random.Random(1))
        game.start()
        game.setup_turn = len(game.players)
        assert game.setup_building_type() == 'settlement'

    def test_the_starting_city_yields_a_commodity(self):
        """'one resource and, where applicable, one commodity' from each hex."""
        game = ck_game()
        vertex_key, _ = city_on(game, 'Alice', 'sheep')
        game.distribute_from_settlement(vertex_key, 'Alice')
        player = game.get_player('Alice')
        assert player.resources.get('sheep') == 1
        assert player.commodities.get('cloth') == 1

    def test_a_starting_settlement_yields_no_commodity(self):
        game = ck_game()
        for vertex_key, vertex in game.vertices.items():
            if vertex.building:
                continue
            hexes = [game.hexes.get(h) for h in vertex.neighbors.get('hexes', [])]
            if any(h and h.type == 'sheep' for h in hexes):
                vertex.building = {'type': 'settlement', 'player': 'Alice'}
                game.distribute_from_settlement(vertex_key, 'Alice')
                assert game.get_player('Alice').commodities == {}
                return
        pytest.skip("no pasture-adjacent vertex")
