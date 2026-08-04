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


def pips(hex_obj):
    """The dots on a number token: how often that hex pays."""
    if hex_obj.number is None:
        return 0
    return 6 - abs(7 - hex_obj.number)


class TestWhereTheRobberGoesWhenNobodyMovedIt:
    """A hex picked at random was as likely to be the timed-out player's own
    best hex as anyone's, which turned a missed click into a self-inflicted
    blockade. It goes to the busiest hex that costs them nothing."""

    @pytest.fixture
    def timed_out(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        game.game_state = 'started'
        game.game_phase = 'playing'
        game.start_turn()
        game.must_move_robber = True
        return game

    def _candidates(self, game, acting):
        """Land hexes the robber could legally be moved to."""
        mine = {
            hex_key
            for key, vertex in game.vertices.items()
            if vertex.building and vertex.building.get('player') == acting
            for hex_key in vertex.neighbors.get('hexes', [])
        }
        return {
            key: hex_obj
            for key, hex_obj in game.hexes.items()
            if hex_obj.type != 'ocean' and key != game.robber_hex and key not in mine
        }

    def test_it_takes_the_busiest_hex_on_the_board(self, timed_out):
        acting = timed_out.players[timed_out.current_player_index].name
        best = max(pips(h) for h in self._candidates(timed_out, acting).values())

        outcome = timed_out.auto_resolve_robber()

        assert pips(timed_out.hexes[outcome['hex']]) == best

    def test_it_does_not_blockade_the_player_it_is_resolving_for(self, timed_out):
        acting = timed_out.players[timed_out.current_player_index].name
        # Put the absent player on the best hex there is, so a robber that
        # only counted pips would sit on their own production.
        richest = max(
            (key for key, h in timed_out.hexes.items() if h.type not in ('ocean', 'desert')),
            key=lambda key: pips(timed_out.hexes[key]),
        )
        vertex_key = next(
            key for key, vertex in timed_out.vertices.items()
            if richest in vertex.neighbors.get('hexes', [])
        )
        timed_out.vertices[vertex_key].building = {'type': 'settlement', 'player': acting}
        timed_out.get_player(acting).settlements.append(vertex_key)

        # Worked out before the move, because moving it changes which hexes
        # are still legal targets.
        candidates = self._candidates(timed_out, acting)

        outcome = timed_out.auto_resolve_robber()

        assert outcome['hex'] != richest
        assert outcome['hex'] in candidates
        assert pips(timed_out.hexes[outcome['hex']]) == max(
            pips(h) for h in candidates.values()
        )

    def test_the_same_seed_resolves_the_same_way(self, timed_out):
        """Timeouts must not be where a replayed game diverges."""
        again = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        again.game_state = 'started'
        again.game_phase = 'playing'
        again.start_turn()
        again.must_move_robber = True

        assert timed_out.auto_resolve_robber() == again.auto_resolve_robber()


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

    def test_it_takes_from_across_the_hand(self, rolled_seven):
        """Not a fixed order: taking the first pile first lets a player game
        the timeout by holding what they want kept behind what the server
        always takes."""
        discarded = rolled_seven.auto_discard('Bob')

        assert sum(discarded.values()) == 5
        assert sorted(discarded) == ['ore', 'wood']

    def test_the_same_hand_and_seed_always_discards_the_same_cards(self):
        """Which cards go must not depend on the order they were collected in
        — that is a seeded game where the same 7 costs different cards
        depending on how the hand was filled."""
        def game_with(hand):
            game = Game(['Alice', 'Bob'], [], rng=random.Random(12345))
            game.game_state = 'started'
            game.game_phase = 'playing'
            game.start_turn()
            game.get_player('Bob').resources = dict(hand)
            game.check_discard_required()
            return game

        collected_one_way = game_with([('wood', 5), ('ore', 5)])
        collected_the_other = game_with([('ore', 5), ('wood', 5)])

        assert (collected_one_way.auto_discard('Bob')
                == collected_the_other.auto_discard('Bob'))
