"""Seafarers, the Krakatoa/Volcano variant — production then eruption.

Source: the Seafarers Volcano variant and its "Krakatoa" sub-variant, three
volcanoes on tokens 4/5/6 (ultraboardgames.com/catan/the-volcano.php;
catan-expansions-research.md, "The Volcano"). A volcano pays each adjacent
building resources of choice on its number (the gold field), then erupts — a die
picks one of its six corners and the building there is destroyed (a settlement)
or downgraded (a city).
"""

import random

from conftest import ScriptedRandom
from game import map_store, maps
from game import rules as rules_module
from game.game import Game


def krakatoa_game(players=('Alice', 'Bob'), seed=3, rng=None, **overrides):
    """A playing game on the Krakatoa board with the volcano rule on.

    Pass `rng` a `ScriptedRandom` to force the eruption die; board generation
    still deals off its seeded base.
    """
    defn = maps.parse_map(map_store.read_map('krakatoa'))
    chosen = dict(rules_module.preset_rules('krakatoa'))
    chosen['turn_order'] = 'lobby'
    chosen.update(overrides)
    game = Game(list(players), [], rng=rng or random.Random(seed), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.start_turn()
    return game


def _volcano_on(game, number):
    """The volcano hex carrying `number`, and its six corner vertices in the
    board's fixed die order (index i is die i+1)."""
    hex_key = next(k for k in game.volcano_hexes if game.hexes[k].number == number)
    corners = [game._volcano_corner(hex_key, i) for i in range(6)]
    return hex_key, corners


class TestBoardDeal:
    def test_the_board_deals_exactly_three_volcanoes_on_four_five_six(self):
        """The Krakatoa island is three volcano hexes on tokens 4, 5 and 6
        (the variant's set-up). Asserted against the generated board — the hex
        types and numbers generation actually dealt — not the map literal."""
        game = krakatoa_game()
        volcanoes = [h for h in game.hexes.values() if h.type == 'volcano']
        assert len(volcanoes) == 3
        assert sorted(h.number for h in volcanoes) == [4, 5, 6]

    def test_the_rule_off_reads_no_volcanoes(self):
        """With the eruption rule off nothing tracks the volcano hexes, so a roll
        can never erupt one even on a board that prints them."""
        game = krakatoa_game(volcano_hex=False)
        assert game.volcano_hexes == set()
        assert game.erupt_volcanoes(5) == []


class TestEruption:
    def test_a_rolled_volcano_downgrades_a_city_on_the_struck_corner(self):
        """The die picks a corner; a city there is reduced to a settlement and
        the city piece returns to its owner (the variant's eruption rule)."""
        game = krakatoa_game()
        _hex, corners = _volcano_on(game, 5)
        target = corners[0]
        game.vertices[target].building = {'type': 'city', 'player': 'Alice'}
        game.get_player('Alice').cities.append(target)

        game.rng = ScriptedRandom(rolls=[1])  # die 1 -> corner index 0
        eruptions = game.erupt_volcanoes(5)

        assert eruptions == [{'hex': _hex, 'die': 1, 'vertex': target,
                              'player': 'Alice', 'was': 'city', 'now': 'settlement'}]
        assert game.vertices[target].building == {'type': 'settlement', 'player': 'Alice'}
        assert target not in game.get_player('Alice').cities
        assert target in game.get_player('Alice').settlements

    def test_a_rolled_volcano_destroys_a_settlement_on_the_struck_corner(self):
        """A settlement on the struck corner is destroyed and returned to its
        owner's supply — the vertex is left empty."""
        game = krakatoa_game()
        _hex, corners = _volcano_on(game, 5)
        target = corners[2]
        game.vertices[target].building = {'type': 'settlement', 'player': 'Bob'}
        game.get_player('Bob').settlements.append(target)

        game.rng = ScriptedRandom(rolls=[3])  # die 3 -> corner index 2
        eruptions = game.erupt_volcanoes(5)

        assert eruptions[0]['player'] == 'Bob'
        assert eruptions[0]['now'] is None
        assert game.vertices[target].building is None
        assert target not in game.get_player('Bob').settlements

    def test_an_eruption_onto_an_empty_corner_destroys_nothing(self):
        """The lava reaches a corner with no building: the eruption is recorded
        but nobody loses anything."""
        game = krakatoa_game()
        _hex, corners = _volcano_on(game, 5)
        # Every corner empty; whichever the die hits, no victim.
        game.rng = ScriptedRandom(rolls=[4])
        eruptions = game.erupt_volcanoes(5)
        assert eruptions == [{'hex': _hex, 'die': 4, 'vertex': corners[3],
                              'player': None, 'was': None, 'now': None}]

    def test_a_volcano_erupts_only_on_its_own_number(self):
        """A roll that does not match a volcano's token leaves every building
        standing — a 5-volcano is untouched by an 8."""
        game = krakatoa_game()
        _hex, corners = _volcano_on(game, 5)
        game.vertices[corners[0]].building = {'type': 'city', 'player': 'Alice'}
        game.get_player('Alice').cities.append(corners[0])

        assert game.erupt_volcanoes(8) == []
        assert game.vertices[corners[0]].building == {'type': 'city', 'player': 'Alice'}


class TestProductionThenEruption:
    def test_a_volcano_pays_resources_of_choice_before_it_erupts(self):
        """The building produces first (the Seafarers gold field: a city owes two
        resources of choice) and only then is struck — so its owner is still owed
        the pending picks even as the eruption downgrades the city."""
        game = krakatoa_game()
        _hex, corners = _volcano_on(game, 5)
        target = corners[0]
        game.vertices[target].building = {'type': 'city', 'player': 'Alice'}
        game.get_player('Alice').cities.append(target)

        # Two dice summing to 5, then the eruption die (1 -> the city's corner).
        game.rng = ScriptedRandom(rolls=[2, 3, 1])
        result = game.roll_dice('Alice')

        # Produced first: a city owes two resource-of-choice picks.
        pending = [c for c in game.pending_choices
                   if c['kind'] == 'gold_field_choice' and c['player'] == 'Alice']
        assert len(pending) == 2
        # Then erupted: the roll's payload names the downgrade the player sees.
        assert result['eruption'] == [{'hex': _hex, 'die': 1, 'vertex': target,
                                       'player': 'Alice', 'was': 'city',
                                       'now': 'settlement'}]
        assert game.vertices[target].building['type'] == 'settlement'

    def test_the_robber_stops_production_but_not_the_eruption(self):
        """The robber on a volcano blocks its resource-of-choice payout, yet the
        volcano still erupts (the variant: the robber cannot stop an eruption)."""
        game = krakatoa_game()
        hex_key, corners = _volcano_on(game, 5)
        target = corners[0]
        game.vertices[target].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(target)
        game.robber_hex = hex_key

        game.rng = ScriptedRandom(rolls=[2, 3, 1])
        result = game.roll_dice('Alice')

        # Robber blocked the payout: no gold-of-choice picks opened.
        assert not [c for c in game.pending_choices if c['kind'] == 'gold_field_choice']
        # But the eruption fired and destroyed the settlement.
        assert result['eruption'][0]['now'] is None
        assert game.vertices[target].building is None
