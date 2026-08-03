"""A Seafarers game survives a restart.

Ships, the pirate and the special points are decided state, so losing any of
them on reload is losing the game the table played. The old-save test is the
other half: a game saved before this expansion existed must still open.
"""

import pytest
from game import persistence
from seafarers_board import (
    build_ships_along,
    coastal_vertex,
    give_building,
    seafarers_game,
    ship_path,
)


@pytest.fixture
def sailed_game():
    """A game with ships on the board, a pirate at sea and a point scored."""
    game = seafarers_game()
    start = coastal_vertex(game)
    give_building(game, 'Alice', start)
    edges, _vertices = ship_path(game, start, 3)
    build_ships_along(game, 'Alice', edges)
    game.pirate_hex = next(
        key for key, hex_obj in sorted(game.hexes.items()) if hex_obj.type == 'ocean'
    )
    game.island_points = {'Alice': 2}
    game.player_islands = {'Alice': ['0,0,0']}
    game.ship_moved_this_turn = True
    return game


def round_trip(game, tmp_path):
    path = str(tmp_path / 'game.json')
    persistence.save(game, path)
    return persistence.load(path)


def test_the_ships_come_back_on_their_sides(sailed_game, tmp_path):
    before = {key: edge.ship for key, edge in sailed_game.edges.items() if edge.ship}
    restored = round_trip(sailed_game, tmp_path)

    assert {key: edge.ship for key, edge in restored.edges.items() if edge.ship} == before
    assert before, 'the fixture should have put ships on the board'


def test_the_owner_still_owns_them(sailed_game, tmp_path):
    restored = round_trip(sailed_game, tmp_path)
    assert restored.get_player('Alice').ships == sailed_game.get_player('Alice').ships


def test_the_pirate_stays_where_it_was_left(sailed_game, tmp_path):
    restored = round_trip(sailed_game, tmp_path)
    assert restored.pirate_hex == sailed_game.pirate_hex


def test_the_special_points_come_back(sailed_game, tmp_path):
    restored = round_trip(sailed_game, tmp_path)
    assert restored.island_points == {'Alice': 2}
    assert restored.player_islands == {'Alice': ['0,0,0']}
    assert restored.victory_points_for('Alice') == sailed_game.victory_points_for('Alice')


def test_the_ship_already_moved_this_turn_is_still_spent(sailed_game, tmp_path):
    """Otherwise a restart hands the current player a second free move."""
    restored = round_trip(sailed_game, tmp_path)
    assert restored.ship_moved_this_turn is True


def test_a_save_from_before_the_expansion_still_loads(sailed_game):
    """Every Seafarers field is absent from such a file, and none of them may
    be required to rebuild the game."""
    data = persistence.serialize(sailed_game)
    for field in ('ships_on_edges', 'pirate_hex', 'ship_moved_this_turn',
                  'player_islands', 'island_points'):
        del data[field]
    for player in data['players']:
        del player['ships']

    restored = persistence.deserialize(data)
    assert restored.pirate_hex is None
    assert restored.island_points == {}
    assert not any(edge.ship for edge in restored.edges.values())
    assert restored.get_player('Alice').ships == []


def test_a_ship_saved_onto_a_side_this_board_lacks_is_dropped(sailed_game):
    """A table that turns ships off has no sea sides to put them back on. The
    game still opens rather than refusing to start."""
    data = persistence.serialize(sailed_game)
    data['rules'] = dict(data['rules'])
    data['rules'].update({
        'ships': False, 'ship_movement': False, 'pirate': False,
        'longest_trade_route': False, 'island_victory_points': False,
    })

    restored = persistence.deserialize(data)
    assert not any(edge.ship for edge in restored.edges.values())
