"""Saving and reloading a game.

Until this existed, every server restart destroyed the game in progress.
"""

import json
import random

import pytest
from game import cities_knights as ck
from game import persistence
from game import rules as rules_module
from game.game import Game


def a_game(rules=None, players=('Alice', 'Bob')):
    return Game(list(players), [], rng=random.Random(11), rules=rules)


def round_trip(game, tmp_path):
    path = str(tmp_path / "game.json")
    persistence.save(game, path)
    return persistence.load(path)


class TestBoardSurvives:
    def test_hex_types_and_numbers_come_back(self, tmp_path):
        game = a_game()
        before = {k: (h.type, h.number) for k, h in game.hexes.items()}
        after = round_trip(game, tmp_path)
        assert {k: (h.type, h.number) for k, h in after.hexes.items()} == before

    def test_ports_come_back(self, tmp_path):
        game = a_game()
        before = {k: v.port for k, v in game.vertices.items() if v.port}
        after = round_trip(game, tmp_path)
        assert {k: v.port for k, v in after.vertices.items() if v.port} == before
        assert before, "the board should have ports at all"

    def test_harbours_come_back_on_their_edges(self, tmp_path):
        game = a_game()
        before = {k: e.port for k, e in game.edges.items() if e.port}
        after = round_trip(game, tmp_path)
        assert {k: e.port for k, e in after.edges.items() if e.port} == before
        assert len(before) == 9

    def test_a_save_from_before_harbours_moved_to_edges_still_loads(self, tmp_path):
        """Such a save carries vertex ports only, and those are what the trade
        rules read, so the game resumes with the harbours it was played with."""
        game = a_game()
        data = persistence.serialize(game)
        vertex_ports = data.pop('edge_ports') and data['ports']

        restored = persistence.deserialize(data)
        assert {k: v.port for k, v in restored.vertices.items() if v.port} == vertex_ports
        assert not any(e.port for e in restored.edges.values())

    def test_a_bigger_map_comes_back_whole(self, tmp_path):
        game = a_game(rules={'board_layout': 'large'})
        before = {k: (h.type, h.number) for k, h in game.hexes.items()}
        after = round_trip(game, tmp_path)
        assert {k: (h.type, h.number) for k, h in after.hexes.items()} == before
        assert after.rules['board_layout'] == 'large'
        assert sum(1 for e in after.edges.values() if e.port) == 11

    def test_buildings_and_roads_come_back(self, tmp_path):
        game = a_game()
        vertex_key = next(iter(game.vertices))
        edge_key = next(iter(game.edges))
        game.vertices[vertex_key].building = {'type': 'city', 'player': 'Alice'}
        game.edges[edge_key].road = {'player': 'Bob'}
        game.get_player('Alice').cities.append(vertex_key)
        game.get_player('Bob').roads.append(edge_key)

        after = round_trip(game, tmp_path)

        assert after.vertices[vertex_key].building == {'type': 'city', 'player': 'Alice'}
        assert after.edges[edge_key].road == {'player': 'Bob'}
        assert after.get_player('Alice').cities == [vertex_key]

    def test_the_derived_graph_is_rebuilt_not_stored(self, tmp_path):
        """Neighbours are regenerated, which is what keeps the file small."""
        game = a_game()
        path = str(tmp_path / "game.json")
        persistence.save(game, path)
        raw = json.loads(open(path).read())
        assert 'neighbors' not in json.dumps(raw), "the graph must not be in the file"

        after = persistence.load(path)
        for edge in after.edges.values():
            for vertex_key in edge.neighbors.get('vertices', []):
                assert vertex_key in after.vertices


class TestGameStateSurvives:
    def test_hands_come_back(self, tmp_path):
        game = a_game()
        game.get_player('Alice').resources = {'wood': 3, 'ore': 1}
        after = round_trip(game, tmp_path)
        assert after.get_player('Alice').resources == {'wood': 3, 'ore': 1}

    def test_the_bank_comes_back(self, tmp_path):
        game = a_game()
        game.bank.take('wood', 4)
        after = round_trip(game, tmp_path)
        assert after.bank.resources['wood'] == game.bank.resources['wood']

    def test_the_dev_card_deck_comes_back(self, tmp_path):
        game = a_game()
        game.bank.draw_dev_card()
        after = round_trip(game, tmp_path)
        assert after.bank.dev_cards_deck == game.bank.dev_cards_deck

    def test_turn_and_phase_come_back(self, tmp_path):
        game = a_game()
        game.start()
        game.game_phase = "playing"
        game.current_player_index = 1
        game.turn_count = 7
        game.has_rolled_dice = True

        after = round_trip(game, tmp_path)

        assert after.game_phase == "playing"
        assert after.current_player_index == 1
        assert after.turn_count == 7
        assert after.has_rolled_dice is True

    def test_robber_state_comes_back(self, tmp_path):
        game = a_game()
        hex_key = next(k for k, h in game.hexes.items() if h.type != 'ocean')
        game.robber_hex = hex_key
        game.must_move_robber = True
        after = round_trip(game, tmp_path)
        assert after.robber_hex == hex_key
        assert after.must_move_robber is True

    def test_special_cards_come_back(self, tmp_path):
        game = a_game()
        game.longest_road_holder = 'Alice'
        game.largest_army_holder = 'Bob'
        after = round_trip(game, tmp_path)
        assert after.longest_road_holder == 'Alice'
        assert after.largest_army_holder == 'Bob'

    def test_a_pending_dev_card_effect_comes_back(self, tmp_path):
        """Otherwise a restart mid-Invention silently eats the card."""
        game = a_game()
        game.pending_invention = 'Alice'
        assert round_trip(game, tmp_path).pending_invention == 'Alice'

    def test_a_decision_the_game_is_waiting_on_comes_back(self, tmp_path):
        """A restart mid-decision must not deadlock the table.

        Losing the choice leaves the rule that opened it half applied — a
        barbarian attack that sacked nothing — and every action is refused
        while one is outstanding, so a lost choice with a live flag would stop
        the game for good.
        """
        game = a_game()
        game.open_choice('barbarian_city', 'Alice', ['v1', 'v2'], reason='attack')

        after = round_trip(game, tmp_path)

        restored = after.pending_choice_for('Alice')
        assert restored['kind'] == 'barbarian_city'
        assert restored['options'] == ['v1', 'v2']
        assert restored['context'] == {'reason': 'attack'}
        # The clock starts again rather than being restored: a save reloaded an
        # hour later would otherwise expire before anyone could answer it.
        assert not after.choices_expired()

    def test_a_chosen_alchemist_roll_comes_back(self, tmp_path):
        game = a_game()
        game.pending_dice = (3, 4)
        assert round_trip(game, tmp_path).pending_dice == (3, 4)

    def test_the_merchant_keeps_its_hex_and_its_owner(self, tmp_path):
        game = a_game()
        game.merchant_hex = next(k for k, h in game.hexes.items() if h.type != 'ocean')
        game.merchant_holder = 'Bob'

        after = round_trip(game, tmp_path)

        assert (after.merchant_hex, after.merchant_holder) == (game.merchant_hex, 'Bob')
        assert after.victory_points_for('Bob') == 1, 'the point travels with the piece'

    def test_a_save_written_before_any_of_this_still_loads(self, tmp_path):
        """Old saves predate every field above and must not be refused."""
        game = a_game()
        data = persistence.serialize(game)
        for field in ('pending_choices', 'pending_dice', 'merchant_hex', 'merchant_holder'):
            data.pop(field)

        restored = persistence.deserialize(data)

        assert restored.pending_choices == []
        assert restored.pending_dice is None
        assert restored.merchant_holder is None


class TestRulesSurvive:
    def test_the_chosen_rules_come_back(self, tmp_path):
        game = a_game({'friendly_robber': True, 'victory_target': 12})
        after = round_trip(game, tmp_path)
        assert after.rules['friendly_robber'] is True
        assert after.victory_points_to_win == 12

    def test_custom_piece_supplies_come_back(self, tmp_path):
        game = a_game({'max_settlements': 8})
        assert round_trip(game, tmp_path).MAX_SETTLEMENTS == 8

    def test_the_dice_deck_is_not_reshuffled_by_a_restart(self, tmp_path):
        """A restart that dealt a fresh 36 would undo the evening-out."""
        game = a_game({'dice_deck': True})
        game.game_phase = "playing"
        game.start_turn()
        game.roll_dice(game.players[game.current_player_index].name)
        assert len(game.dice_deck) == 35

        assert round_trip(game, tmp_path).dice_deck == game.dice_deck

    def test_a_custom_dice_set_comes_back_with_what_is_left_of_it(self, tmp_path):
        """A restart must not hand the table the two numbers they took out."""
        game = a_game({'dice_set': 'no_two_or_twelve', 'dice_deck': True})
        game.game_phase = "playing"
        game.start_turn()
        game.roll_dice(game.players[game.current_player_index].name)

        after = round_trip(game, tmp_path)
        assert after.rules['dice_set'] == 'no_two_or_twelve'
        assert after.dice_deck == game.dice_deck
        assert all(sum(pair) not in (2, 12) for pair in after.dice_combinations())

    def test_a_save_written_before_these_rules_existed_still_loads(self, tmp_path):
        """Old saves carry no `dice_set` and no `epidemic`; both fall back to
        the base game rather than refusing the file."""
        path = str(tmp_path / "game.json")
        persistence.save(a_game(), path)
        with open(path) as handle:
            data = json.load(handle)
        for rule_id in ('dice_set', 'epidemic'):
            del data['rules'][rule_id]
        with open(path, 'w') as handle:
            json.dump(data, handle)

        after = persistence.load(path)
        assert after.rules['dice_set'] == 'standard'
        assert after.rules['epidemic'] is False


class TestCitiesKnightsSurvives:
    def test_improvements_come_back(self, tmp_path):
        game = a_game(rules_module.preset_rules('cities_and_knights'))
        game.ck.improvements['Alice'][ck.TRADE] = 3
        after = round_trip(game, tmp_path)
        assert after.ck.level('Alice', ck.TRADE) == 3

    def test_knights_come_back_with_their_state(self, tmp_path):
        game = a_game(rules_module.preset_rules('cities_and_knights'))
        knight = ck.Knight('v1', ck.STRONG)
        knight.active = True
        knight.acted_this_turn = True
        game.ck.knights['Alice'] = [knight]

        after = round_trip(game, tmp_path)

        restored = after.ck.knights['Alice'][0]
        assert restored.vertex == 'v1'
        assert restored.rank == ck.STRONG
        assert restored.active is True
        assert restored.acted_this_turn is True

    def test_the_barbarian_track_comes_back(self, tmp_path):
        game = a_game(rules_module.preset_rules('cities_and_knights'))
        game.ck.barbarian_position = 5
        game.ck.barbarians_have_attacked = True
        after = round_trip(game, tmp_path)
        assert after.ck.barbarian_position == 5
        assert after.ck.barbarians_have_attacked is True

    def test_a_metropolis_comes_back(self, tmp_path):
        game = a_game(rules_module.preset_rules('cities_and_knights'))
        game.ck.metropolis[ck.TRADE] = 'Alice'
        game.ck.metropolis_vertex[ck.TRADE] = 'v9'
        after = round_trip(game, tmp_path)
        assert after.ck.metropolis[ck.TRADE] == 'Alice'
        assert after.victory_points_for('Alice') >= 2

    def test_commodities_come_back(self, tmp_path):
        game = a_game(rules_module.preset_rules('cities_and_knights'))
        game.get_player('Alice').commodities = {'cloth': 2, 'coin': 1}
        after = round_trip(game, tmp_path)
        assert after.get_player('Alice').commodities == {'cloth': 2, 'coin': 1}

    def test_the_base_game_stores_no_expansion_state(self, tmp_path):
        game = a_game()
        path = str(tmp_path / "game.json")
        persistence.save(game, path)
        assert json.loads(open(path).read())['cities_knights'] is None


class TestASaveFromBeforeTheDecomposition:
    """A game saved while Cities & Knights was one boolean.

    Dropping the unknown key would have taken the commodities, knights and
    barbarians off a table part-way through a match, so the flag is translated
    into the rules it stood for — including the 13-point target the old engine
    forced on them, because that is the game they are playing.
    """

    def _legacy_save(self, tmp_path):
        game = a_game(rules_module.preset_rules('cities_and_knights'))
        game.ck.barbarian_position = 4
        game.get_player('Alice').commodities = {'cloth': 3}
        path = str(tmp_path / "game.json")
        persistence.save(game, path)

        data = json.loads(open(path).read())
        data['rules'] = {'cities_and_knights': True, 'victory_target': 13}
        open(path, 'w').write(json.dumps(data))
        return path

    def test_the_expansion_is_still_being_played(self, tmp_path):
        after = persistence.load(self._legacy_save(tmp_path))
        assert after.rules['knights'] is True
        assert after.rules['commodities'] is True
        assert after.rules['city_improvements'] is True

    def test_the_barbarians_are_still_where_they_were(self, tmp_path):
        after = persistence.load(self._legacy_save(tmp_path))
        assert after.ck is not None
        assert after.ck.barbarian_position == 4

    def test_the_game_is_still_played_to_thirteen(self, tmp_path):
        after = persistence.load(self._legacy_save(tmp_path))
        assert after.victory_points_to_win == 13

    def test_the_dead_flag_is_not_carried_forward(self, tmp_path):
        after = persistence.load(self._legacy_save(tmp_path))
        assert 'cities_and_knights' not in after.rules


class TestFileHandling:
    def test_loading_a_missing_file_is_not_an_error(self, tmp_path):
        assert persistence.load(str(tmp_path / "nope.json")) is None

    def test_an_outdated_save_is_refused(self, tmp_path):
        path = tmp_path / "game.json"
        path.write_text(json.dumps({'save_version': 999}))
        with pytest.raises(ValueError, match="save version"):
            persistence.load(str(path))

    def test_a_corrupt_save_is_refused(self, tmp_path):
        path = tmp_path / "game.json"
        path.write_text("{not json")
        with pytest.raises(json.JSONDecodeError):
            persistence.load(str(path))

    def test_a_save_failing_its_invariants_is_refused(self, tmp_path):
        """A hand-edited or corrupt save is untrusted input like any other."""
        game = a_game()
        path = str(tmp_path / "game.json")
        persistence.save(game, path)

        data = json.loads(open(path).read())
        data['players'][0]['resources'] = {'wood': -5}
        open(path, 'w').write(json.dumps(data))

        with pytest.raises(ValueError, match="invariants"):
            persistence.load(path)

    def test_saving_twice_leaves_no_temp_file(self, tmp_path):
        game = a_game()
        path = str(tmp_path / "game.json")
        persistence.save(game, path)
        persistence.save(game, path)
        assert not (tmp_path / "game.json.tmp").exists()
