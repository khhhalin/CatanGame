"""The pending-choice phase, and the barbarians it was built for.

A tester reported that a barbarian attack never asked which city was lost. The
missing dialog was the symptom; the cause was that `resolve_barbarian_attack`
ran to completion inside `roll_dice` and picked the weakest defender's first
city itself, because the engine had no way to stop and ask anybody anything.

These tests pin the machinery that fixes it: what the server offers, what it
refuses, that the table cannot play on around an open question, and that a
question nobody answers is settled rather than left to hang — which is the same
failure `_turn_watchdog` already paid for with `must_move_robber`.
"""

import random

import pytest
from game import progress_cards
from game import rules as rules_module
from game.game import Game
from game.pending_choice import KINDS


def ck_game(players=('Alice', 'Bob')):
    game = Game(list(players), [], rng=random.Random(7),
                rules=rules_module.preset_rules('cities_and_knights'))
    game.game_phase = 'playing'
    game.start_turn()
    game.set_dice_rolled()
    return game


def city_keys(game, count):
    """Real vertex keys, so a pillage has a building to turn back over."""
    return sorted(game.vertices)[:count]


def give_cities(game, player_name, *vertex_keys):
    player = game.get_player(player_name)
    for vertex_key in vertex_keys:
        game.vertices[vertex_key].building = {'type': 'city', 'player': player_name}
        player.cities.append(vertex_key)
    return player


@pytest.fixture
def game():
    return ck_game()


class TestTheKindRegistry:
    def test_every_kind_has_a_resolver_on_the_engine(self, game):
        """`KINDS` is a hardcoded table; the resolvers are what consume it.

        A kind with no `_choice_<kind>` method does not fail on the way in — it
        is offered to a player, accepted from them, and then raises inside the
        handler with the choice already removed from the queue.
        """
        missing = [kind for kind in KINDS if not hasattr(game, f'_choice_{kind}')]
        assert missing == []


class TestTheBarbariansAskWhichCity:
    def _lost_attack(self, game, *cities):
        give_cities(game, 'Alice', *cities)
        return game.resolve_barbarian_attack()

    def test_a_player_with_two_cities_is_asked_which_one_goes(self, game):
        first, second = city_keys(game, 2)
        result = self._lost_attack(game, first, second)

        assert not result['won'], 'no knights means the barbarians win'
        assert result['awaiting'] == ['Alice']
        assert result['pillaged'] == [], 'nothing is taken until Alice has answered'
        assert game.pending_choice_for('Alice')['options'] == [first, second]

    def test_the_city_the_player_names_is_the_one_that_is_lost(self, game):
        first, second = city_keys(game, 2)
        self._lost_attack(game, first, second)

        assert game.resolve_choice('Alice', 'barbarian_city', second)['success']

        alice = game.get_player('Alice')
        assert alice.cities == [first], 'the city Alice kept is the one she did not name'
        assert second in alice.settlements
        assert game.vertices[second].building['type'] == 'settlement'

    def test_a_metropolis_is_never_offered(self, game):
        first, second = city_keys(game, 2)
        give_cities(game, 'Alice', first, second)
        game.ck.metropolis['trade'] = 'Alice'
        game.ck.metropolis_vertex['trade'] = first

        result = game.resolve_barbarian_attack()

        # One city left to lose is no decision, so it goes without asking.
        assert result['pillaged'] == ['Alice']
        assert game.pending_choices == []
        assert game.get_player('Alice').cities == [first]

    def test_the_table_cannot_play_on_while_the_question_is_open(self, game):
        first, second = city_keys(game, 2)
        self._lost_attack(game, first, second)

        current = game.players[game.current_player_index].name
        refusal = game.advance_turn(current)

        assert not refusal['success']
        assert refusal['code'] in ('MUST_CHOOSE', 'AWAITING_CHOICE')

    def test_answering_releases_the_table(self, game):
        first, second = city_keys(game, 2)
        self._lost_attack(game, first, second)
        game.resolve_choice('Alice', 'barbarian_city', first)

        current = game.players[game.current_player_index].name
        assert game.advance_turn(current)['success']


class TestAnswersAreUntrusted:
    @pytest.fixture
    def asked(self, game):
        first, second = city_keys(game, 2)
        give_cities(game, 'Alice', first, second)
        game.resolve_barbarian_attack()
        return game, first, second

    def test_a_player_who_was_not_asked_cannot_answer(self, asked):
        game, first, _ = asked
        result = game.resolve_choice('Bob', 'barbarian_city', first)

        assert result['code'] == 'NO_CHOICE_PENDING'
        assert game.get_player('Alice').cities == [first, _]

    def test_answering_the_wrong_kind_is_refused(self, asked):
        game, first, _ = asked
        assert game.resolve_choice('Alice', 'spy', first)['code'] == 'WRONG_CHOICE'

    def test_an_option_that_was_never_offered_is_refused(self, asked):
        game, first, second = asked
        stranger = next(key for key in sorted(game.vertices) if key not in (first, second))

        result = game.resolve_choice('Alice', 'barbarian_city', stranger)

        assert result['code'] == 'INVALID_CHOICE'
        assert game.get_player('Alice').cities == [first, second]
        assert game.pending_choices, 'a refused answer leaves the question open'


class TestTheTimeout:
    def test_a_choice_nobody_answers_is_settled_for_them(self, game):
        first, second = city_keys(game, 2)
        give_cities(game, 'Alice', first, second)
        game.resolve_barbarian_attack()

        game.pending_choices[0]['deadline'] = 0
        assert game.choices_expired()
        settled = game.auto_resolve_choices()

        assert [entry['option'] for entry in settled] == [first]
        assert game.pending_choices == [], 'nothing is left to block the next turn'
        assert game.get_player('Alice').cities == [second]

    def test_it_drains_follow_up_questions_too(self, game):
        """A Master Merchant takes two cards, asked one at a time."""
        game.get_player('Bob').resources = {'ore': 2}
        game.get_player('Bob').victory_points = 5
        game.ck.progress_hands['Alice'] = ['master_merchant']
        assert game.play_progress_card('Alice', 'master_merchant', 'Bob')['success']

        game.auto_resolve_choices()

        assert game.pending_choices == []
        assert game.get_player('Alice').resources['ore'] == 2
        assert game.get_player('Bob').resources['ore'] == 0


class TestWhatTheClientIsTold:
    def test_only_the_chooser_is_shown_the_options(self, game):
        """A Master Merchant's options are the cards in somebody else's hand."""
        game.get_player('Bob').resources = {'ore': 1, 'wheat': 1}
        game.get_player('Bob').victory_points = 5
        game.ck.progress_hands['Alice'] = ['master_merchant']
        game.play_progress_card('Alice', 'master_merchant', 'Bob')

        for_alice = game.get_board_data(viewer='Alice')['pending_choices'][0]
        for_bob = game.get_board_data(viewer='Bob')['pending_choices'][0]

        assert for_alice['options'] == ['ore', 'wheat']
        assert 'options' not in for_bob
        # Bob still learns that the game is waiting, and on whom.
        assert (for_bob['player'], for_bob['option_count']) == ('Alice', 2)
        assert for_bob['prompt'] == KINDS['master_merchant']


class TestJointDefendersChooseTheirDeck:
    def test_each_tied_defender_is_offered_all_three_decks(self, game):
        for name in ('Alice', 'Bob'):
            knight = game.ck.knights.setdefault(name, [])
            knight.append(_active_knight(f'{name}-v'))

        result = game.resolve_barbarian_attack()

        assert sorted(result['awaiting_draws']) == ['Alice', 'Bob']
        assert game.pending_choice_for('Bob')['options'] == list(progress_cards.DECKS)


def _active_knight(vertex):
    from game import cities_knights as ck_module
    knight = ck_module.Knight(vertex)
    knight.active = True
    return knight
