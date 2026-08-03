"""A restart must not void the progress cards players are holding."""

import random

from game import persistence
from game import rules as rules_module
from game.game import Game


def _ck_game():
    game = Game(['Alice', 'Bob'], [], {}, rules=rules_module.preset_rules('cities_and_knights'),
                rng=random.Random(11))
    game.start()
    return game


class TestProgressCardsSurviveARestart:
    def test_a_hand_is_still_there_after_a_round_trip(self, tmp_path):
        game = _ck_game()
        game.ck.progress_hands['Alice'] = ['crane', 'medicine']

        path = str(tmp_path / 'game.json')
        persistence.save(game, path)
        restored = persistence.load(path)

        assert restored.ck.progress_hands['Alice'] == ['crane', 'medicine']

    def test_a_partly_drawn_deck_is_not_reshuffled(self, tmp_path):
        """Reshuffling on restart would deal cards players already drew."""
        game = _ck_game()
        game.ck.progress_decks['trade'] = ['crane', 'merchant']

        path = str(tmp_path / 'game.json')
        persistence.save(game, path)
        restored = persistence.load(path)

        assert restored.ck.progress_decks['trade'] == ['crane', 'merchant']

    def test_a_save_written_before_progress_cards_existed_still_loads(self, tmp_path):
        """Old saves have no such key; they must load, not crash."""
        game = _ck_game()
        path = str(tmp_path / 'game.json')
        persistence.save(game, path)

        import json
        with open(path) as handle:
            data = json.load(handle)
        del data['cities_knights']['progress_decks']
        del data['cities_knights']['progress_hands']
        with open(path, 'w') as handle:
            json.dump(data, handle)

        restored = persistence.load(path)
        assert restored.ck.progress_hands == {}
        assert restored.ck.progress_decks == {}
