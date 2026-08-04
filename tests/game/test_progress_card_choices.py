"""The progress cards that were refused by name until the engine could ask.

Nine of the 54 cards had no resolver, so `play_progress_card` answered "not
implemented yet" for a card the player was holding. Eight of them are here.
Merchant Fleet is not: it lets a player trade a chosen resource *or commodity*
at 2:1 with the bank, and the trade engine has no bank trade for commodities at
all, so it is still refused rather than half implemented.

Each test asserts the effect a player would notice — a card leaving somebody
else's hand, a road coming off the board, a die coming up on demand.
"""

import random

import pytest
from game import cities_knights as ck_module
from game import rules as rules_module
from game.game import Game


def ck_game(players=('Alice', 'Bob')):
    game = Game(list(players), [], rng=random.Random(7),
                rules=rules_module.preset_rules('cities_and_knights'))
    game.game_phase = 'playing'
    game.start_turn()
    game.set_dice_rolled()
    return game


@pytest.fixture
def game():
    return ck_game()


def hold(game, player_name, *card_ids):
    game.ck.progress_hands[player_name] = list(card_ids)


class TestMerchantFleetIsStillRefused:
    def test_it_names_itself_rather_than_pretending(self, game):
        hold(game, 'Alice', 'merchant_fleet')

        result = game.play_progress_card('Alice', 'merchant_fleet', 'cloth')

        assert not result['success']
        assert 'not implemented' in result['error']
        assert game.ck.hand_of('Alice') == ['merchant_fleet'], 'a refused card is not burned'


class TestAlchemist:
    def test_the_chosen_faces_are_the_ones_that_come_up(self, game):
        hold(game, 'Alice', 'alchemist')
        game.has_rolled_dice = False

        assert game.play_progress_card('Alice', 'alchemist', [3, 4])['success']
        roll = game.roll_dice(game.players[game.current_player_index].name)

        assert (roll['dice1'], roll['dice2'], roll['total']) == (3, 4, 7)

    def test_it_only_lasts_one_roll(self, game):
        hold(game, 'Alice', 'alchemist')
        game.has_rolled_dice = False
        game.play_progress_card('Alice', 'alchemist', [3, 4])
        game.roll_dice(game.players[game.current_player_index].name)

        assert game.pending_dice is None

    def test_a_face_off_the_die_is_refused(self, game):
        hold(game, 'Alice', 'alchemist')
        game.has_rolled_dice = False

        assert not game.play_progress_card('Alice', 'alchemist', [0, 7])['success']


class TestMerchant:
    def _hex_beside_a_building(self, game, player_name):
        vertex_key = next(
            key for key, vertex in game.vertices.items()
            if any(
                game.hexes.get(hex_key) is not None
                and game.hexes[hex_key].type not in ('ocean', 'desert')
                for hex_key in vertex.neighbors.get('hexes', [])
            )
        )
        game.get_player(player_name).settlements.append(vertex_key)
        return next(
            hex_key for hex_key in game.vertices[vertex_key].neighbors['hexes']
            if game.hexes.get(hex_key) is not None
            and game.hexes[hex_key].type not in ('ocean', 'desert')
        )

    def test_it_is_worth_a_point_while_you_hold_it(self, game):
        hex_key = self._hex_beside_a_building(game, 'Alice')
        hold(game, 'Alice', 'merchant')
        before = game.victory_points_for('Alice')

        assert game.play_progress_card('Alice', 'merchant', hex_key)['success']

        assert game.victory_points_for('Alice') == before + 1
        assert game.merchant_holder == 'Alice'

    def test_it_buys_that_hex_resource_from_the_bank_at_two_to_one(self, game):
        hex_key = self._hex_beside_a_building(game, 'Alice')
        resource = game.hexes[hex_key].type
        hold(game, 'Alice', 'merchant')
        game.play_progress_card('Alice', 'merchant', hex_key)

        assert game.get_player_ports('Alice') == {}, 'no harbour is doing the work here'
        assert game.best_trade_rate('Alice', {resource: 2}) == 2
        # Everything else is still the table's ordinary bank rate.
        other = next(r for r in ('wood', 'brick', 'sheep', 'wheat', 'ore') if r != resource)
        assert game.best_trade_rate('Alice', {other: 4}) == game.rules['bank_trade_rate']

    def test_it_must_stand_beside_one_of_your_own_buildings(self, game):
        hold(game, 'Alice', 'merchant')
        lonely = next(
            key for key, hex_obj in game.hexes.items() if hex_obj.type not in ('ocean',)
        )

        assert not game.play_progress_card('Alice', 'merchant', lonely)['success']


class TestDiplomat:
    def _open_road(self, game, player_name):
        """A road with nothing at one end — the only kind that can be removed."""
        edge_key = next(
            key for key in sorted(game.edges) if game.land_hexes_of_edge(key)
        )
        game.edges[edge_key].road = {'player': player_name}
        game.get_player(player_name).roads.append(edge_key)
        return edge_key

    def test_an_open_road_comes_off_the_board(self, game):
        edge_key = self._open_road(game, 'Bob')
        hold(game, 'Alice', 'diplomat')

        assert game.play_progress_card('Alice', 'diplomat', edge_key)['success']

        assert game.edges[edge_key].road is None
        assert game.get_player('Bob').roads == []

    def test_your_own_road_can_be_rebuilt_for_free(self, game):
        edge_key = self._open_road(game, 'Alice')
        hold(game, 'Alice', 'diplomat')

        game.play_progress_card('Alice', 'diplomat', edge_key)

        assert game.free_roads_remaining == 1

    def test_a_road_built_up_at_both_ends_is_safe(self, game):
        edge_key = self._open_road(game, 'Bob')
        # Close both ends: a building at one, a neighbouring road at the other.
        first, second = game.edges[edge_key].neighbors['vertices']
        game.vertices[first].building = {'type': 'settlement', 'player': 'Bob'}
        neighbour = next(
            key for key in game.vertices[second].neighbors['edges'] if key != edge_key
        )
        game.edges[neighbour].road = {'player': 'Bob'}
        hold(game, 'Alice', 'diplomat')

        assert not game.play_progress_card('Alice', 'diplomat', edge_key)['success']
        assert game.edges[edge_key].road is not None


class TestCommercialHarbor:
    def test_each_opponent_chooses_which_commodity_they_part_with(self, game):
        game.get_player('Alice').resources = {'ore': 1}
        game.get_player('Bob').commodities = {'cloth': 1, 'paper': 1}
        hold(game, 'Alice', 'commercial_harbor')

        assert game.play_progress_card('Alice', 'commercial_harbor', 'ore')['success']
        assert game.pending_choice_for('Bob')['options'] == ['cloth', 'paper']

        game.resolve_choice('Bob', 'commercial_harbor', 'paper')

        assert game.get_player('Alice').commodities['paper'] == 1
        assert game.get_player('Bob').commodities == {'cloth': 1, 'paper': 0}
        assert game.get_player('Bob').resources['ore'] == 1, 'they get the resource in exchange'
        assert game.get_player('Alice').resources['ore'] == 0

    def test_a_resource_you_do_not_hold_cannot_be_offered(self, game):
        game.get_player('Bob').commodities = {'cloth': 1}
        hold(game, 'Alice', 'commercial_harbor')

        assert not game.play_progress_card('Alice', 'commercial_harbor', 'ore')['success']


class TestMasterMerchant:
    def test_two_cards_are_taken_one_named_at_a_time(self, game):
        bob = game.get_player('Bob')
        bob.resources = {'ore': 1}
        bob.commodities = {'coin': 1}
        bob.victory_points = 5
        hold(game, 'Alice', 'master_merchant')

        assert game.play_progress_card('Alice', 'master_merchant', 'Bob')['success']
        assert game.pending_choice_for('Alice')['options'] == ['coin', 'ore']

        game.resolve_choice('Alice', 'master_merchant', 'coin')
        # The second question is asked against what the first one left behind.
        assert game.pending_choice_for('Alice')['options'] == ['ore']
        game.resolve_choice('Alice', 'master_merchant', 'ore')

        assert game.get_player('Alice').commodities['coin'] == 1
        assert game.get_player('Alice').resources['ore'] == 1
        assert bob.total_cards() == 0

    def test_only_a_player_ahead_of_you_can_be_robbed(self, game):
        game.get_player('Bob').resources = {'ore': 3}
        hold(game, 'Alice', 'master_merchant')

        assert not game.play_progress_card('Alice', 'master_merchant', 'Bob')['success']


class TestSpy:
    def test_a_progress_card_moves_from_their_hand_to_yours(self, game):
        game.ck.progress_hands['Bob'] = ['warlord', 'bishop']
        hold(game, 'Alice', 'spy')

        assert game.play_progress_card('Alice', 'spy', 'Bob')['success']
        assert game.pending_choice_for('Alice')['options'] == ['bishop', 'warlord']

        game.resolve_choice('Alice', 'spy', 'bishop')

        assert game.ck.hand_of('Alice') == ['bishop']
        assert game.ck.hand_of('Bob') == ['warlord']

    def test_a_player_holding_nothing_cannot_be_spied_on(self, game):
        hold(game, 'Alice', 'spy')
        assert not game.play_progress_card('Alice', 'spy', 'Bob')['success']


class TestWedding:
    def test_the_giver_chooses_what_they_hand_over(self, game):
        bob = game.get_player('Bob')
        bob.resources = {'ore': 1, 'wood': 1}
        bob.victory_points = 5
        hold(game, 'Alice', 'wedding')

        assert game.play_progress_card('Alice', 'wedding')['success']
        assert game.pending_choice_for('Bob')['options'] == ['ore', 'wood']

        game.resolve_choice('Bob', 'wedding', 'wood')
        game.resolve_choice('Bob', 'wedding', 'ore')

        assert game.get_player('Alice').resources == {'wood': 1, 'ore': 1}
        assert bob.total_cards() == 0

    def test_nobody_ahead_means_the_card_cannot_be_played(self, game):
        game.get_player('Bob').resources = {'ore': 2}
        hold(game, 'Alice', 'wedding')

        assert not game.play_progress_card('Alice', 'wedding')['success']


class TestDeserter:
    def _knight_for(self, game, player_name, vertex_key, rank=ck_module.BASIC):
        game.ck.knights.setdefault(player_name, []).append(ck_module.Knight(vertex_key, rank))
        return vertex_key

    def test_the_opponent_chooses_which_knight_leaves(self, game):
        first, second = sorted(game.vertices)[:2]
        self._knight_for(game, 'Bob', first)
        self._knight_for(game, 'Bob', second)
        hold(game, 'Alice', 'deserter')

        assert game.play_progress_card('Alice', 'deserter', 'Bob')['success']
        assert game.pending_choice_for('Bob')['options'] == [first, second]

        game.resolve_choice('Bob', 'deserter', second)

        assert [k.vertex for k in game.ck.knights_of('Bob')] == [first]

    def test_the_replacement_is_placed_where_its_new_owner_says(self, game):
        # Alice needs a road for a knight of her own to stand on.
        edge_key = next(key for key in sorted(game.edges) if game.land_hexes_of_edge(key))
        game.edges[edge_key].road = {'player': 'Alice'}
        game.get_player('Alice').roads.append(edge_key)
        landing = sorted(game.edges[edge_key].neighbors['vertices'])[-1]

        self._knight_for(game, 'Bob', 'far-away-vertex')
        hold(game, 'Alice', 'deserter')
        game.play_progress_card('Alice', 'deserter', 'Bob')
        game.resolve_choice('Bob', 'deserter', 'far-away-vertex')

        assert landing in game.pending_choice_for('Alice')['options']
        game.resolve_choice('Alice', 'deserter_placement', landing)

        knights = game.ck.knights_of('Alice')
        assert [(k.vertex, k.rank, k.active) for k in knights] == [(landing, ck_module.BASIC,
                                                                   False)]

    def test_an_opponent_with_no_knights_cannot_be_targeted(self, game):
        hold(game, 'Alice', 'deserter')
        assert not game.play_progress_card('Alice', 'deserter', 'Bob')['success']
