"""A refusal must name the rule that actually refused.

Two rules can close a hex to the robber, and both came back as Friendly
Robber — so a table with Friendly Robber switched off was told about it
anyway, and went looking for a rule that was not in play.

The bank trade had the opposite problem: it refused nothing and said
nothing. Cards left a hand and the shared history recorded no reason for
it, while a player-to-player trade had always been visible.
"""

import random

import state
from extensions import socketio
from game import rules as rules_module
from game.game import Game


def _game(**overrides):
    rules = dict(rules_module.defaults())
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(4))
    game.start()
    game.game_phase = 'playing'
    game.has_rolled_dice = True
    game.must_move_robber = True
    return game


def _desert(game):
    """The desert, with the robber moved off it first.

    The robber starts on the desert, so without this every test below trips
    the "it must actually move" refusal before reaching the rule it is about.
    """
    desert = next(key for key, hex_obj in game.hexes.items() if hex_obj.type == 'desert')
    game.robber_hex = next(
        key for key, hex_obj in sorted(game.hexes.items())
        if hex_obj.type not in ('desert', 'ocean')
    )
    return desert


class TestTheRobberSaysWhichRuleClosedTheHex:
    def test_the_desert_rule_is_not_reported_as_friendly_robber(self):
        """The bug: one message stood in for every refusal."""
        game = _game(robber_may_return_to_desert=False, friendly_robber=False)
        result = game.move_robber('Alice', _desert(game))

        assert not result['success']
        assert result['code'] == 'ROBBER_NOT_ON_DESERT'
        assert 'friendly' not in result['error'].lower(), (
            f"a table not playing Friendly Robber was told about it: {result['error']!r}"
        )

    def test_the_desert_is_open_when_the_rule_allows_it(self):
        game = _game(robber_may_return_to_desert=True, friendly_robber=False)
        assert game.move_robber('Alice', _desert(game))['success']

    def test_an_unknown_hex_is_its_own_refusal(self):
        game = _game()
        result = game.move_robber('Alice', 'not,a,hex')
        assert not result['success']
        assert result['code'] == 'INVALID_TARGET'


class TestABankTradeReachesTheSharedLog:
    def test_the_table_is_told_what_left_the_hand(self, socket_app):
        alice = socketio.test_client(socket_app)
        bob = socketio.test_client(socket_app)
        alice.emit('join', {'name': 'Alice', 'role': 'player'})
        bob.emit('join', {'name': 'Bob', 'role': 'player'})
        alice.emit('start_game')

        game = state.session().game
        game.game_phase = 'playing'
        game.set_dice_rolled()
        game.current_player_index = [p.name for p in game.players].index('Alice')
        game.get_player('Alice').resources['wood'] = 4

        alice.get_received()
        bob.get_received()
        alice.emit('propose_trade', {'name': 'Alice',
                                     'offered': {'wood': 4},
                                     'wanted': {'ore': 1}})

        # Bob's queue, because the point is that the *table* can see it.
        logged = [
            message['args'][0]['entry']
            for message in bob.get_received()
            if message['name'] == 'event_logged'
        ]
        trades = [entry for entry in logged if entry['kind'] == 'trade']
        assert trades, "a bank trade left no trace in the shared log"
        assert 'Alice' in trades[-1]['text']
        assert 'bank' in trades[-1]['text'].lower()
