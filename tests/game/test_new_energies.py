"""CATAN: New Energies — power plants, the science commodity, and energy.

Chunk 1 of the scenario. A city produces a `science` card as well as its
resource; players build cheap fossil and costlier renewable power plants on the
numbered land hexes beside their towns and cities; a plant pays 1 energy when
its hex produces, and energy buys cards. The global-footprint track, the event
discs and the dual end condition are the later chunks.

Source: CATAN: New Energies rulebook (CN3207 New Energies rules 240409), the
3-4 player rules — 'Production Phase' p. 11 and 'Build/buy' pp. 14-15.
"""

import random

import pytest
from game import rules as rules_module
from game.game import Game


def ne_game(extra=None, players=('Alice', 'Bob'), seed=7):
    """A playing game with the New Energies rule set on the standard board."""
    rules = rules_module.preset_rules('new_energies')
    rules['turn_order'] = 'lobby'
    rules.update(extra or {})
    game = Game(list(players), [], rng=random.Random(seed), rules=rules)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.start_turn()
    return game


def building_on(game, player_name, btype, terrain=None):
    """Put a `btype` building next to a numbered hex and return (vertex, hex).

    Placed straight onto the board (not built through setup) so a production or
    energy test can name the exact hex it stands on; the placement itself is
    exercised by the setup and build tests.
    """
    for vertex_key, vertex in game.vertices.items():
        if vertex.building:
            continue
        for hex_key in vertex.neighbors.get('hexes', []):
            hex_obj = game.hexes.get(hex_key)
            if hex_obj is None or hex_obj.number is None:
                continue
            if terrain is not None and hex_obj.type != terrain:
                continue
            vertex.building = {'type': btype, 'player': player_name}
            (game.get_player(player_name).cities if btype == 'city'
             else game.get_player(player_name).settlements).append(vertex_key)
            return vertex_key, hex_key
    pytest.skip(f"no numbered {terrain or 'land'} hex free on this board")


class TestPreset:
    def test_the_preset_ticks_power_plants_and_starts_with_a_city(self):
        game = ne_game()
        assert game.rules['power_plants'] is True
        assert game.rules['setup_second_city'] is True
        # A New Energies city takes one resource a hex, not the base game's two.
        assert game.rules['city_production'] == 1
        assert game.victory_points_to_win == 10

    def test_off_by_default_no_new_energies_state(self):
        base = Game(['A', 'B'], [], rng=random.Random(1))
        assert base.new_energies_client_state() is None
        assert base.rules['power_plants'] is False


class TestSetup:
    def test_the_opening_is_a_town_then_a_city(self):
        rules = rules_module.preset_rules('new_energies')
        game = Game(['Alice', 'Bob'], [], rng=random.Random(7), rules=rules)
        game.start()
        assert game.setup_building_type() == 'settlement'
        game.setup_turn = len(game.players)
        assert game.setup_building_type() == 'city'

    def test_the_starting_city_pays_one_flat_science_not_one_per_hex(self):
        """"Each player also takes 1 science card for their city" — a single
        science however many hexes the city touches, unlike the per-hex
        resources beside it (rulebook, 'Collect your starting hand', p. 7)."""
        game = ne_game()
        vertex_key, _ = building_on(game, 'Alice', 'city')
        hex_count = sum(
            1 for h in game.vertices[vertex_key].neighbors['hexes']
            if game.hexes.get(h) and game.hexes[h].number
        )
        game.distribute_from_settlement(vertex_key, 'Alice')
        player = game.get_player('Alice')
        assert player.commodities.get('science') == 1
        assert sum(player.resources.values()) == hex_count


class TestScienceProduction:
    def test_a_city_produces_a_resource_and_a_science(self):
        game = ne_game()
        vertex_key, hex_key = building_on(game, 'Alice', 'city')
        number = game.hexes[hex_key].number
        expected = sum(
            1 for h in game.vertices[vertex_key].neighbors['hexes']
            if game.hexes.get(h) and game.hexes[h].number == number
        )
        game.robber_hex = None
        gained = game.distribute_resources(number)
        alice = gained.get('Alice', {})
        assert alice.get('science') == expected
        assert game.get_player('Alice').commodities.get('science') == expected

    def test_a_town_produces_no_science(self):
        game = ne_game()
        vertex_key, hex_key = building_on(game, 'Alice', 'settlement')
        number = game.hexes[hex_key].number
        game.robber_hex = None
        game.distribute_resources(number)
        assert game.get_player('Alice').commodities.get('science', 0) == 0


class TestPowerPlantBuild:
    def test_a_fossil_plant_costs_one_science(self):
        game = ne_game()
        vertex_key, hex_key = building_on(game, 'Alice', 'settlement')
        game.get_player('Alice').commodities['science'] = 1
        result = game.build_power_plant('Alice', vertex_key, hex_key, 'fossil')
        assert result['success']
        assert game.get_player('Alice').commodities['science'] == 0
        assert game.power_plants[(vertex_key, hex_key)] == {'player': 'Alice', 'kind': 'fossil'}

    def test_a_renewable_plant_costs_three_science(self):
        game = ne_game()
        vertex_key, hex_key = building_on(game, 'Alice', 'city')
        game.get_player('Alice').commodities['science'] = 2
        short = game.build_power_plant('Alice', vertex_key, hex_key, 'renewable')
        assert not short['success']
        assert short['code'] == 'INSUFFICIENT_RESOURCES'
        game.get_player('Alice').commodities['science'] = 3
        assert game.build_power_plant('Alice', vertex_key, hex_key, 'renewable')['success']
        assert game.get_player('Alice').commodities['science'] == 0

    def test_a_town_hosts_one_plant_a_city_three(self):
        game = ne_game()
        vertex_key, _ = building_on(game, 'Alice', 'settlement')
        hexes = [h for h in game.vertices[vertex_key].neighbors['hexes']
                 if game.hexes.get(h) and game.hexes[h].number]
        if len(hexes) < 2:
            pytest.skip("need a town on two numbered hexes")
        game.get_player('Alice').commodities['science'] = 5
        assert game.build_power_plant('Alice', vertex_key, hexes[0], 'fossil')['success']
        game.power_plant_built_this_turn = False  # the once-a-turn cap is a separate test
        second = game.build_power_plant('Alice', vertex_key, hexes[1], 'fossil')
        assert not second['success']
        assert second['code'] == 'NO_CUTOUT_LEFT'

    def test_a_plant_must_stand_on_a_numbered_land_hex_beside_your_building(self):
        game = ne_game()
        vertex_key, hex_key = building_on(game, 'Alice', 'city')
        game.get_player('Alice').commodities['science'] = 5
        # A hex the building does not touch is refused.
        stranger = next(h for h in game.hexes
                        if h not in game.vertices[vertex_key].neighbors['hexes'])
        off = game.build_power_plant('Alice', vertex_key, stranger, 'fossil')
        assert not off['success'] and off['code'] == 'INVALID_PLACEMENT'

    def test_only_one_plant_a_turn(self):
        game = ne_game()
        v1, h1 = building_on(game, 'Alice', 'city')
        v2, h2 = building_on(game, 'Alice', 'settlement')
        game.get_player('Alice').commodities['science'] = 5
        assert game.build_power_plant('Alice', v1, h1, 'fossil')['success']
        again = game.build_power_plant('Alice', v2, h2, 'fossil')
        assert not again['success'] and again['code'] == 'PLANT_ALREADY_BUILT'
        game.start_turn()
        assert game.build_power_plant('Alice', v2, h2, 'fossil')['success']


def _city_with_two_numbered_hexes(game, player_name):
    """A city and two of its adjacent numbered hexes, for two-plant tests."""
    for vertex_key, vertex in game.vertices.items():
        if vertex.building:
            continue
        numbered = [h for h in vertex.neighbors.get('hexes', [])
                    if game.hexes.get(h) and game.hexes[h].number]
        if len(numbered) >= 2:
            vertex.building = {'type': 'city', 'player': player_name}
            game.get_player(player_name).cities.append(vertex_key)
            return vertex_key, numbered[0], numbered[1]
    pytest.skip("no city site touching two numbered hexes")


class TestGlobalFootprint:
    def test_local_footprint_weighs_town_city_and_plants(self):
        game = ne_game()
        town_v, town_h = building_on(game, 'Alice', 'settlement')
        city_v, _ = building_on(game, 'Alice', 'city')
        assert game.local_footprint('Alice') == 1 + 2  # a town and a city
        game.power_plants[(town_v, town_h)] = {'player': 'Alice', 'kind': 'fossil'}
        assert game.local_footprint('Alice') == 3 + 1  # a fossil plant adds one
        game.power_plants[(city_v, next(
            h for h in game.vertices[city_v].neighbors['hexes']
            if game.hexes.get(h) and game.hexes[h].number))] = {
            'player': 'Alice', 'kind': 'renewable'}
        assert game.local_footprint('Alice') == 4 - 1  # a renewable subtracts one

    def test_the_global_footprint_is_the_sum_of_local_footprints(self):
        game = ne_game()
        building_on(game, 'Alice', 'city')
        building_on(game, 'Bob', 'settlement')
        assert game.global_footprint_level() == (
            game.local_footprint('Alice') + game.local_footprint('Bob')
        )

    def test_a_fossil_plant_raises_and_a_renewable_lowers_the_footprint(self):
        game = ne_game()
        city_v, h1, h2 = _city_with_two_numbered_hexes(game, 'Alice')
        game.get_player('Alice').commodities['science'] = 4
        before = game.global_footprint_level()
        assert game.build_power_plant('Alice', city_v, h1, 'fossil')['success']
        assert game.global_footprint_level() == before + 1
        game.power_plant_built_this_turn = False
        assert game.build_power_plant('Alice', city_v, h2, 'renewable')['success']
        assert game.global_footprint_level() == before  # back down one

    def test_the_footprint_never_drops_below_zero(self):
        game = ne_game()
        city_v, _ = building_on(game, 'Alice', 'city')  # LF 2
        # Six renewables would take the sum to 2 - 6 = -4; the track stops at 0.
        for i, hex_key in enumerate(sorted(game.hexes)[:6]):
            game.power_plants[(f'{city_v}#{i}', hex_key)] = {
                'player': 'Alice', 'kind': 'renewable'}
        assert game.local_footprint('Alice') < 0
        assert game.global_footprint_level() == 0

    def test_start_is_three_per_player(self):
        game = ne_game()
        building_on(game, 'Alice', 'settlement')
        building_on(game, 'Alice', 'city')
        building_on(game, 'Bob', 'settlement')
        building_on(game, 'Bob', 'city')
        assert game.global_footprint_level() == 3 * len(game.players)

    def test_demolishing_a_fossil_lowers_the_footprint_for_one_energy(self):
        game = ne_game()
        city_v, hex_key = building_on(game, 'Alice', 'city')
        game.power_plants[(city_v, hex_key)] = {'player': 'Alice', 'kind': 'fossil'}
        alice = game.get_player('Alice')
        alice.energy = 1
        before = game.global_footprint_level()
        result = game.demolish_fossil_plant('Alice', city_v, hex_key)
        assert result['success']
        assert (city_v, hex_key) not in game.power_plants
        assert alice.energy == 0
        assert game.global_footprint_level() == before - 1

    def test_only_one_fossil_demolished_a_turn(self):
        game = ne_game()
        c1, h1 = building_on(game, 'Alice', 'city')
        c2, h2 = building_on(game, 'Alice', 'settlement')
        game.power_plants[(c1, h1)] = {'player': 'Alice', 'kind': 'fossil'}
        game.power_plants[(c2, h2)] = {'player': 'Alice', 'kind': 'fossil'}
        game.get_player('Alice').energy = 5
        assert game.demolish_fossil_plant('Alice', c1, h1)['success']
        again = game.demolish_fossil_plant('Alice', c2, h2)
        assert not again['success'] and again['code'] == 'ALREADY_DEMOLISHED'

    def test_only_a_fossil_may_be_demolished(self):
        game = ne_game()
        city_v, hex_key = building_on(game, 'Alice', 'city')
        game.power_plants[(city_v, hex_key)] = {'player': 'Alice', 'kind': 'renewable'}
        game.get_player('Alice').energy = 5
        result = game.demolish_fossil_plant('Alice', city_v, hex_key)
        assert not result['success'] and result['code'] == 'INVALID_TARGET'


class TestEnergyProduction:
    def test_a_plant_pays_one_energy_when_its_hex_produces(self):
        game = ne_game()
        vertex_key, hex_key = building_on(game, 'Alice', 'settlement')
        game.power_plants[(vertex_key, hex_key)] = {'player': 'Alice', 'kind': 'fossil'}
        game.robber_hex = None
        gained = game.distribute_energy(game.hexes[hex_key].number)
        assert gained == {'Alice': 1}
        assert game.get_player('Alice').energy == 1

    def test_energy_is_capped_at_five(self):
        game = ne_game()
        vertex_key, hex_key = building_on(game, 'Alice', 'settlement')
        game.power_plants[(vertex_key, hex_key)] = {'player': 'Alice', 'kind': 'fossil'}
        game.robber_hex = None
        game.get_player('Alice').energy = 5
        assert game.distribute_energy(game.hexes[hex_key].number) == {}
        assert game.get_player('Alice').energy == 5

    def test_the_robber_blocks_a_plants_energy(self):
        game = ne_game()
        vertex_key, hex_key = building_on(game, 'Alice', 'settlement')
        game.power_plants[(vertex_key, hex_key)] = {'player': 'Alice', 'kind': 'fossil'}
        game.robber_hex = hex_key
        assert game.distribute_energy(game.hexes[hex_key].number) == {}
        assert game.get_player('Alice').energy == 0


class TestEnergyUses:
    def test_two_energy_buys_one_resource_of_choice(self):
        game = ne_game()
        alice = game.get_player('Alice')
        alice.energy = 2
        bank_wood = game.bank.resources['wood']
        result = game.spend_energy_for_card('Alice', 'wood')
        assert result['success']
        assert alice.energy == 0
        assert alice.resources.get('wood') == 1
        assert game.bank.resources['wood'] == bank_wood - 1

    def test_two_energy_buys_one_science(self):
        game = ne_game()
        alice = game.get_player('Alice')
        alice.energy = 2
        assert game.spend_energy_for_card('Alice', 'science')['success']
        assert alice.commodities.get('science') == 1
        assert alice.energy == 0

    def test_too_little_energy_is_refused(self):
        game = ne_game()
        game.get_player('Alice').energy = 1
        result = game.spend_energy_for_card('Alice', 'wood')
        assert not result['success'] and result['code'] == 'NOT_ENOUGH_ENERGY'
