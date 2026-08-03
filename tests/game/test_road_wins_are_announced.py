"""A road that wins the game must say so.

Settlements, cities and ships all announce a win the moment they cause one.
A road did not: completing the Longest Road is worth 2 points and can end the
game, and the table was told nothing — the winner surfaced on some later state
push, or not at all.
"""

import pytest
import state
from extensions import socketio


@pytest.fixture
def clients(socket_app):
    alice = socketio.test_client(socket_app)
    bob = socketio.test_client(socket_app)
    alice.emit('join', {'name': 'Alice', 'role': 'player'})
    bob.emit('join', {'name': 'Bob', 'role': 'player'})
    alice.emit('start_game')
    alice.get_received()
    bob.get_received()
    return alice, bob


def events(client, name):
    return [msg['args'][0] for msg in client.get_received() if msg['name'] == name]


class TestARoadThatWinsIsAnnounced:
    def test_the_table_is_told_when_a_road_ends_the_game(self, clients):
        alice, _ = clients
        game = state.session().game

        # A road is only ever worth points through Longest Road, so put the
        # target within reach of the card alone.
        game.victory_points_to_win = 2
        game.rules['longest_road_minimum'] = 2
        game.game_phase = 'playing'
        game.has_rolled_dice = True
        game.current_player_index = [p.name for p in game.players].index('Alice')

        player = game.get_player('Alice')
        player.resources.update({'wood': 9, 'brick': 9})

        # Lay a connected run directly, stopping one short of the card.
        laid = [key for key, edge in sorted(game.edges.items()) if not edge.road][:1]
        game.edges[laid[0]].road = {'player': 'Alice'}
        player.roads.append(laid[0])

        neighbours = game.edges[laid[0]].neighbors['vertices']
        next_edge = next(
            key for key, edge in sorted(game.edges.items())
            if not edge.road and set(edge.neighbors['vertices']) & set(neighbours)
        )

        alice.get_received()
        alice.emit('place_road', {'name': 'Alice', 'edge': next_edge})

        won = events(alice, 'game_won')
        assert won, "a road that ends the game must emit game_won"
        assert won[0]['player'] == 'Alice'
