"""Bug C: an unresolved robber must not be able to outlive the round timer.

`must_move_robber` gates every build, trade and turn advance, so leaving it set
does not delay the table, it stops it — and the flag surviving into the next
player's turn is what let a late move end somebody else's turn.
"""

import random

import pytest
from game.game import Game


@pytest.fixture
def rolled_seven(playing_game):
    """A game sitting on a rolled 7, robber unmoved, Bob owing a discard."""
    playing_game.must_move_robber = True
    bob = playing_game.get_player('Bob')
    bob.resources = {'wood': 5, 'ore': 5}
    playing_game.check_discard_required()
    return playing_game


class TestAutoResolveRobber:
    def test_the_robber_ends_up_somewhere_legal(self, rolled_seven):
        outcome = rolled_seven.auto_resolve_robber()

        assert outcome['hex'] == rolled_seven.robber_hex
        assert rolled_seven.hexes[rolled_seven.robber_hex].type != 'ocean'

    def test_nothing_is_left_pending(self, rolled_seven):
        rolled_seven.auto_resolve_robber()

        assert not rolled_seven.must_move_robber
        assert not rolled_seven.must_choose_victim
        assert rolled_seven.robber_victims == []

    def test_a_late_move_is_refused_rather_than_ending_a_turn(self, rolled_seven):
        rolled_seven.auto_resolve_robber()

        current = rolled_seven.players[rolled_seven.current_player_index].name
        result = rolled_seven.move_robber(current, next(iter(rolled_seven.hexes)))
        assert not result['success']
        assert result['code'] == 'WRONG_PHASE'

    def test_the_turn_can_be_advanced_afterwards(self, rolled_seven):
        rolled_seven.auto_resolve_robber()
        rolled_seven.players_needing_discard = {}

        current = rolled_seven.players[rolled_seven.current_player_index].name
        assert rolled_seven.advance_turn(current)['success']

    def test_it_steals_when_the_new_hex_has_a_victim(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(11))
        game.game_phase = 'playing'
        game.start_turn()
        game.must_move_robber = True

        # Put every one of Bob's buildings around one hex, then aim there by
        # leaving it the only legal target.
        target = next(k for k, h in game.hexes.items() if h.type not in ('ocean', 'desert'))
        vertex_key = next(
            key for key, vertex in game.vertices.items()
            if target in vertex.neighbors.get('hexes', [])
        )
        game.vertices[vertex_key].building = {'type': 'settlement', 'player': 'Bob'}
        game.get_player('Bob').settlements.append(vertex_key)
        game.get_player('Bob').resources = {'ore': 1}
        # Somewhere else to start from: the robber may not be moved onto the
        # hex it already stands on.
        game.robber_hex = next(
            key for key, hex_obj in game.hexes.items()
            if hex_obj.type != 'ocean' and key != target
        )

        # The robber never stays put, so aim it by hand and resolve the steal.
        game.move_robber(game.players[game.current_player_index].name, target)
        acting = game.players[game.current_player_index].name
        if acting == 'Bob':
            pytest.skip('shuffled order put Bob on the robber; nobody to rob')

        outcome = game.auto_resolve_robber()
        assert outcome['victim'] == 'Bob'
        assert outcome['stolen'] == 'ore'
        assert game.get_player('Alice').resources.get('ore') == 1


class TestAutoDiscard:
    def test_it_takes_exactly_what_was_owed(self, rolled_seven):
        owed = rolled_seven.players_needing_discard['Bob']
        discarded = rolled_seven.auto_discard('Bob')

        assert sum(discarded.values()) == owed
        assert rolled_seven.get_player('Bob').total_cards() == 10 - owed

    def test_it_clears_the_obligation(self, rolled_seven):
        rolled_seven.auto_discard('Bob')
        assert 'Bob' not in rolled_seven.players_needing_discard

    def test_a_player_who_owes_nothing_is_untouched(self, rolled_seven):
        assert rolled_seven.auto_discard('Alice') == {}
