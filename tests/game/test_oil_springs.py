"""Catan: Oil Springs — oil production off the oil-spring hexes.

Chunk 1: the sixth commodity. The board carries three Oil Spring tiles; a
building on one produces oil on the hex's number, capped at four held, drawn
from a supply of fifteen. Later chunks add the disaster track, sequestering and
metropolises.

Source: coilspringsgb_2015_web.pdf, 3-4 player rules p. 1.
"""

import random

from conftest import ScriptedRandom
from game import map_store, maps, persistence
from game import rules as rules_module
from game.game import Game


def oil_game(players=('Alice', 'Bob'), seed=12345, rng=None, **overrides):
    """A playing game on the Oil Springs board with the oil rule on.

    Pass `rng` a `ScriptedRandom` to force the disaster dice; board generation
    still shuffles off its seeded base.
    """
    defn = maps.parse_map(map_store.read_map('oil-springs'))
    chosen = dict(rules_module.preset_rules('oil_springs'))
    chosen['turn_order'] = 'lobby'
    chosen.update(overrides)
    game = Game(list(players), [], rng=rng or random.Random(seed), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.start_turn()
    return game


def _a_coastal_vertex(game, exclude=()):
    """A buildable intersection that borders open sea, not in `exclude`."""
    for vertex_key in sorted(game.vertices):
        if vertex_key in exclude:
            continue
        if game._borders_sea(vertex_key):
            return vertex_key
    raise AssertionError('no coastal vertex on the board')


class TestBoardDeal:
    def test_the_board_carries_exactly_three_oil_springs(self):
        """The scenario prints three Oil Spring tiles: the desert, a forest hex
        and a pasture hex (p. 1 set-up). Asserted against the generated board,
        not the map literal."""
        game = oil_game()
        springs = {key for key, hex_obj in game.hexes.items()
                   if getattr(hex_obj.meta, 'oil_spring', False)}
        assert springs == game.oil_spring_hexes
        assert len(springs) == 3
        kinds = sorted(game.hexes[key].type for key in springs)
        assert kinds == ['desert', 'sheep', 'wood']

    def test_the_forest_and_pasture_springs_carry_a_nine_and_a_ten(self):
        """The two producing springs sit on a 9 forest and a 10 pasture (p. 1)."""
        game = oil_game()
        by_type = {game.hexes[key].type: game.hexes[key].number
                   for key in game.oil_spring_hexes}
        assert by_type['wood'] == 9
        assert by_type['sheep'] == 10
        assert by_type['desert'] is None

    def test_the_producing_hexes_carry_the_eighteen_base_tokens(self):
        """A base-game board underneath: the 18 number tokens are unchanged."""
        game = oil_game()
        tokens = sorted(hex_obj.number for hex_obj in game.hexes.values()
                        if hex_obj.type not in ('ocean', 'desert'))
        assert tokens == [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]


class TestProduction:
    def _settle(self, game, spring_key, player_name, btype='settlement'):
        """Put a building of `player_name` on a corner of the given spring."""
        vertex_key = game._oil_spring_vertices(spring_key)[0]
        game.vertices[vertex_key].building = {'type': btype, 'player': player_name}
        return vertex_key

    def _wood_spring(self, game):
        return next(k for k in game.oil_spring_hexes if game.hexes[k].type == 'wood')

    def test_a_settlement_on_an_oil_spring_produces_one_oil_on_its_number(self):
        game = oil_game()
        spring = self._wood_spring(game)  # a 9
        self._settle(game, spring, 'Alice')
        produced = game.distribute_oil(9, 'Alice')
        assert produced == {'Alice': 1}
        assert game.get_player('Alice').oil == 1
        assert game.oil_supply == 15 - 1

    def test_a_city_on_an_oil_spring_produces_two_oil(self):
        game = oil_game()
        spring = self._wood_spring(game)
        self._settle(game, spring, 'Alice', btype='city')
        produced = game.distribute_oil(9, 'Alice')
        assert produced == {'Alice': 2}
        assert game.get_player('Alice').oil == 2

    def test_no_oil_is_produced_when_the_number_is_not_rolled(self):
        game = oil_game()
        spring = self._wood_spring(game)  # a 9
        self._settle(game, spring, 'Alice')
        assert game.distribute_oil(6, 'Alice') == {}
        assert game.get_player('Alice').oil == 0

    def test_no_oil_is_produced_on_a_seven(self):
        game = oil_game()
        spring = self._wood_spring(game)
        self._settle(game, spring, 'Alice')
        assert game.distribute_oil(7, 'Alice') == {}

    def test_a_player_never_holds_more_than_four_oil(self):
        """The hold cap is 4; oil produced beyond it is not taken (p. 1)."""
        game = oil_game()
        spring = self._wood_spring(game)
        self._settle(game, spring, 'Alice', btype='city')  # 2 per roll
        game.get_player('Alice').oil = 3
        produced = game.distribute_oil(9, 'Alice')
        assert produced == {'Alice': 1}
        assert game.get_player('Alice').oil == 4

    def test_the_rule_off_produces_no_oil(self):
        game = oil_game(oil_tokens=False)
        # With the rule off the springs are never read, so nothing produces.
        assert game.oil_spring_hexes == set()
        assert game.distribute_oil(9, 'Alice') == {}


class TestConsumption:
    def test_converting_oil_spends_it_pays_two_and_advances_the_track(self):
        game = oil_game()
        alice = game.get_player('Alice')
        alice.oil = 2
        before = game.bank.resources.get('wheat', 0)
        result = game.convert_oil_to_resource('Alice', 'wheat')
        assert result['success'] is True
        assert alice.oil == 1
        assert alice.resources['wheat'] == 2
        assert game.bank.resources['wheat'] == before - 2
        assert game.disaster_track == 1
        assert game.oil_supply == 15 + 1  # the oil went back to the supply

    def test_no_oil_can_be_used_once_the_track_is_full(self):
        game = oil_game()
        game.get_player('Alice').oil = 1
        game.disaster_track = 5
        result = game.convert_oil_to_resource('Alice', 'wheat')
        assert result['success'] is False
        assert result['code'] == 'DISASTER_IMMINENT'
        assert game.get_player('Alice').oil == 1

    def test_converting_without_oil_is_refused(self):
        game = oil_game()
        result = game.convert_oil_to_resource('Alice', 'wheat')
        assert result['code'] == 'NO_OIL'


class TestDisaster:
    def test_the_fifth_oil_used_triggers_a_flood_on_a_seven(self):
        """A 7 in the disaster phase floods the coasts: a coastal settlement is
        removed and a coastal city reduced to a settlement (p. 2)."""
        game = oil_game(rng=ScriptedRandom(rolls=[3, 4]))  # 3 + 4 = 7
        settle_v = _a_coastal_vertex(game)
        city_v = _a_coastal_vertex(game, exclude={settle_v})
        alice = game.get_player('Alice')
        game.vertices[settle_v].building = {'type': 'settlement', 'player': 'Alice'}
        alice.settlements.append(settle_v)
        game.vertices[city_v].building = {'type': 'city', 'player': 'Alice'}
        alice.cities.append(city_v)

        game.disaster_track = 4
        alice.oil = 1
        game.convert_oil_to_resource('Alice', 'wheat')  # track -> 5
        assert game.oil_disaster_owed() is True

        result = game.advance_turn('Alice')
        disaster = result['oil_disaster']
        assert disaster['kind'] == 'flood'
        # The coastal settlement is gone; the coastal city is now a settlement.
        assert game.vertices[settle_v].building is None
        assert settle_v not in alice.settlements
        assert game.vertices[city_v].building['type'] == 'settlement'
        assert city_v not in alice.cities
        assert game.disaster_track == 0

    def test_the_fifth_oil_used_pollutes_a_hex_on_a_non_seven(self):
        """Any non-7 pollutes a hex carrying the rolled number, removing its
        token for good (asserted against the generated board)."""
        game = oil_game(rng=ScriptedRandom(rolls=[6, 6]))  # 6 + 6 = 12
        # The only 12 on this board is the wood hex at -6,0,6, not a spring.
        twelve = [k for k, h in game.hexes.items() if h.number == 12]
        assert twelve == ['-6,0,6']
        assert twelve[0] not in game.oil_spring_hexes

        game.disaster_track = 4
        game.get_player('Alice').oil = 1
        game.convert_oil_to_resource('Alice', 'wheat')  # track -> 5
        result = game.advance_turn('Alice')

        disaster = result['oil_disaster']
        assert disaster['kind'] == 'pollution'
        assert disaster['hex'] == '-6,0,6'
        assert game.hexes['-6,0,6'].number is None
        assert game.oil_numbers_removed == 1

    def test_polluting_an_oil_spring_burns_three_oil_and_keeps_the_number(self):
        """An oil spring struck by pollution loses 3 oil from the supply and
        keeps its number; it can be hit again (p. 2)."""
        game = oil_game(rng=ScriptedRandom(rolls=[4, 5]))  # 4 + 5 = 9
        # Two hexes carry 9: the wood spring and a brick hex. Retire the brick's
        # token first so the spring is the sole candidate — deterministic.
        for key, hex_obj in game.hexes.items():
            if hex_obj.number == 9 and key not in game.oil_spring_hexes:
                hex_obj.number = None
        spring9 = next(k for k in game.oil_spring_hexes if game.hexes[k].number == 9)

        game.disaster_track = 5
        supply_before = game.oil_supply
        result = game.advance_turn('Alice')

        disaster = result['oil_disaster']
        assert disaster['hex'] == spring9
        assert disaster['oil_spring'] is True
        assert game.hexes[spring9].number == 9      # the spring keeps its token
        assert game.oil_supply == supply_before - 3
        assert game.oil_numbers_removed == 0

    def test_the_board_dies_when_the_fifth_token_is_removed(self):
        """Five destroyed tokens end the game with no true winner (p. 3)."""
        game = oil_game(rng=ScriptedRandom(rolls=[6, 6]))  # 6 + 6 = 12
        game.oil_numbers_removed = 4
        game.disaster_track = 5

        result = game.advance_turn('Alice')
        disaster = result['oil_disaster']
        assert game.oil_numbers_removed == 5
        assert game.game_state == 'finished'
        assert disaster['game_over']['reason'] == 'board_dead'


class TestSequester:
    def test_sequestering_three_oil_scores_two_points_and_the_champion(self):
        """1 VP per 3 sequestered, plus the 1-VP Champion of the Environment
        token for reaching three first (p. 2)."""
        game = oil_game()
        alice = game.get_player('Alice')
        alice.oil = 3
        for _ in range(3):
            result = game.sequester_oil('Alice')
            assert result['success'] is True
            game.start_turn()  # a fresh turn re-opens the one-per-turn allowance
        assert game.oil_sequestered['Alice'] == 3
        assert alice.oil == 0
        assert game.oil_champion == 'Alice'
        # 3 // 3 == 1 point, plus 1 for the Champion token.
        assert game.oil_sequester_victory_points('Alice') == 2
        assert game.victory_points_for('Alice') == 2

    def test_the_sequestered_oil_leaves_the_game_not_the_supply(self):
        game = oil_game()
        game.get_player('Alice').oil = 1
        supply_before = game.oil_supply
        game.sequester_oil('Alice')
        assert game.oil_supply == supply_before  # gone for good, not returned

    def test_only_one_oil_may_be_sequestered_per_turn(self):
        game = oil_game()
        game.get_player('Alice').oil = 2
        assert game.sequester_oil('Alice')['success'] is True
        second = game.sequester_oil('Alice')
        assert second['code'] == 'ALREADY_SEQUESTERED'

    def test_you_cannot_sequester_after_using_oil_this_turn(self):
        game = oil_game()
        alice = game.get_player('Alice')
        alice.oil = 2
        game.convert_oil_to_resource('Alice', 'wheat')  # a use
        blocked = game.sequester_oil('Alice')
        assert blocked['code'] == 'OIL_ALREADY_USED'

    def test_the_champion_passes_to_whoever_sequesters_more(self):
        game = oil_game()
        game.get_player('Alice').oil = 3
        game.get_player('Bob').oil = 4
        for _ in range(3):
            game.sequester_oil('Alice')
            game.start_turn()
        assert game.oil_champion == 'Alice'
        game.current_player_index = 1  # Bob's turn
        game.start_turn()
        for _ in range(4):
            game.sequester_oil('Bob')
            game.start_turn()
        assert game.oil_champion == 'Bob'


class TestMetropolis:
    def _city(self, game, vertex_key, player_name):
        game.vertices[vertex_key].building = {'type': 'city', 'player': player_name}
        game.get_player(player_name).cities.append(vertex_key)

    def test_a_metropolis_costs_resources_and_two_oil_and_advances_the_track(self):
        game = oil_game()
        alice = game.get_player('Alice')
        city_v = _a_coastal_vertex(game)
        self._city(game, city_v, 'Alice')
        alice.resources = {'brick': 1, 'wheat': 1, 'ore': 1}
        alice.oil = 2
        result = game.build_oil_metropolis('Alice', city_v)
        assert result['success'] is True
        assert game.oil_metropolises[city_v] == 'Alice'
        assert alice.oil == 0
        assert alice.resources == {'brick': 0, 'wheat': 0, 'ore': 0}
        assert game.disaster_track == 2

    def test_a_metropolis_is_worth_three_points(self):
        game = oil_game()
        alice = game.get_player('Alice')
        city_v = _a_coastal_vertex(game)
        self._city(game, city_v, 'Alice')
        base = game.victory_points_for('Alice')  # the city scores 2
        alice.resources = {'brick': 1, 'wheat': 1, 'ore': 1}
        alice.oil = 2
        game.build_oil_metropolis('Alice', city_v)
        assert game.victory_points_for('Alice') == base + 1  # 2 -> 3

    def test_a_metropolis_is_immune_to_coastal_flooding(self):
        game = oil_game(rng=ScriptedRandom(rolls=[3, 4]))  # a 7
        alice = game.get_player('Alice')
        city_v = _a_coastal_vertex(game)
        plain_v = _a_coastal_vertex(game, exclude={city_v})
        self._city(game, city_v, 'Alice')
        game.vertices[plain_v].building = {'type': 'settlement', 'player': 'Alice'}
        alice.settlements.append(plain_v)
        alice.resources = {'brick': 1, 'wheat': 1, 'ore': 1}
        alice.oil = 2
        game.build_oil_metropolis('Alice', city_v)

        game.disaster_track = 5
        game.advance_turn('Alice')
        # The flood removed the plain coastal settlement but spared the metropolis.
        assert game.vertices[plain_v].building is None
        assert game.vertices[city_v].building == {'type': 'city', 'player': 'Alice'}
        assert city_v in game.oil_metropolises

    def test_a_metropolis_on_a_spring_produces_three_oil(self):
        game = oil_game()
        spring = next(k for k in game.oil_spring_hexes if game.hexes[k].type == 'wood')
        vertex_key = game._oil_spring_vertices(spring)[0]
        game.vertices[vertex_key].building = {'type': 'city', 'player': 'Alice'}
        game.oil_metropolises[vertex_key] = 'Alice'
        produced = game.distribute_oil(9, 'Alice')
        assert produced == {'Alice': 3}


class TestPersistence:
    def test_oil_and_the_supply_survive_a_save_and_reload(self):
        game = oil_game()
        game.get_player('Alice').oil = 3
        game.oil_supply = 9
        game.disaster_track = 3
        game.oil_numbers_removed = 2
        game.oil_sequestered = {'Alice': 4}
        game.oil_champion = 'Alice'
        city_v = _a_coastal_vertex(game)
        game.vertices[city_v].building = {'type': 'city', 'player': 'Alice'}
        game.get_player('Alice').cities.append(city_v)
        game.oil_metropolises = {city_v: 'Alice'}
        blob = persistence.serialize(game)
        restored = persistence.deserialize(blob)
        assert restored.get_player('Alice').oil == 3
        assert restored.oil_supply == 9
        assert restored.disaster_track == 3
        assert restored.oil_numbers_removed == 2
        assert restored.oil_sequestered == {'Alice': 4}
        assert restored.oil_champion == 'Alice'
        assert restored.oil_metropolises == {city_v: 'Alice'}
        # The springs are re-derived from the map, not the save.
        assert len(restored.oil_spring_hexes) == 3
