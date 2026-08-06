"""Explorers & Pirates mission container (Wave 4, expansions.md 969-978).

The three concrete missions (pirate-lairs, fish, spices) land later; this pins
only the machinery they share, so each test names something a table would notice
break: a marker that ran past the end of its track, a sole leader who did not
score the mission's 1-VP lead card, a tie that awarded the card to somebody, an
overtake that failed to move the point, and a base game that grew a mission it
never switched on.

`missions` has no dependencies, so it is switched on alone here — the container
is built for it and nothing else, which is exactly the scaffold the three
mission modules plug into.
"""

import random

from game import rules as rules_module
from game.game import Game


def _game(missions=True, **overrides):
    rules = dict(rules_module.defaults())
    if missions:
        rules['missions'] = True
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], rules=rules, rng=random.Random(7))
    return game


def test_advancing_a_marker_moves_it_and_caps_at_the_track_end():
    game = _game()
    game.register_mission_track('fish', 5)

    assert game.advance_mission('Alice', 'fish', 3) == 3
    # A delivery that would overshoot seats the marker on the final step.
    assert game.advance_mission('Alice', 'fish', 10) == 5
    assert game.ep.marker('Alice', 'fish') == 5


def test_an_unregistered_track_moves_no_marker():
    """A track no mission has declared yet has length 0, so its marker is inert
    until that mission's module fills it in."""
    game = _game()
    assert game.advance_mission('Alice', 'fish', 4) == 0
    assert game.ep.marker('Alice', 'fish') == 0


def test_a_sole_leader_holds_the_lead_card_and_scores_a_point():
    game = _game()
    game.register_mission_track('spices', 8)

    game.advance_mission('Alice', 'spices', 2)
    game.advance_mission('Bob', 'spices', 1)

    assert game.mission_lead_holder('spices') == 'Alice'
    assert game.victory_points_for('Alice') == 1
    assert game.victory_points_for('Bob') == 0


def test_a_tie_at_the_front_leaves_the_card_unheld_and_unscored():
    game = _game()
    game.register_mission_track('spices', 8)

    game.advance_mission('Alice', 'spices', 2)
    game.advance_mission('Bob', 'spices', 2)

    assert game.mission_lead_holder('spices') is None
    assert game.victory_points_for('Alice') == 0
    assert game.victory_points_for('Bob') == 0


def test_overtaking_flips_the_holder_and_the_point():
    game = _game()
    game.register_mission_track('pirate_lairs', 8)

    game.advance_mission('Alice', 'pirate_lairs', 2)
    assert game.mission_lead_holder('pirate_lairs') == 'Alice'
    assert game.victory_points_for('Alice') == 1

    game.advance_mission('Bob', 'pirate_lairs', 3)
    assert game.mission_lead_holder('pirate_lairs') == 'Bob'
    assert game.victory_points_for('Alice') == 0
    assert game.victory_points_for('Bob') == 1


def test_the_base_game_is_untouched_when_missions_are_off():
    game = _game(missions=False)
    # No container, no track, no score — the rule reaches nothing.
    assert game.ep is None
    assert game.advance_mission('Alice', 'fish', 5) == 0
    assert game.mission_lead_holder('fish') is None
    assert game.victory_points_for('Alice') == 0
