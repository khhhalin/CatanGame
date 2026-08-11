"""Catalogue rules whose *number* nobody had ever changed.

An audit found six rule ids that appear in no test at all, and five more that
are only ever mentioned — asserted to render in the picker, or to declare their
lobby fields, neither of which is behaviour. Every test here sets its rule to a
value the table could not get by accident, drives the thing the rule governs,
and then checks the default still does what it always did.

What a player would notice if one of these broke: a lobby control that does
nothing. A table that ticks "City walls per player: 1" and gets three anyway
has been lied to by the picker, and no amount of state-shape assertion catches
it.
"""

import random

from game import cities_knights as ck_module
from game import rules as rules_module
from game.game import Game
from seafarers_board import coastal_vertex, give_building, seafarers_game, ship_path


def a_vertex(game):
    """Any intersection the graph has both sides and neighbours for."""
    for key in sorted(game.vertices):
        vertex = game.vertices[key]
        if vertex.neighbors.get('vertices') and vertex.neighbors.get('edges'):
            return key
    raise AssertionError('board has no connected intersections')


def give_road_chain(game, player_name, length):
    """Lay a connected chain of roads without going through placement rules."""
    current = a_vertex(game)
    path = [current]
    player = game.get_player(player_name)
    for _ in range(length):
        edge_key = next(
            key
            for key in sorted(game.vertices[current].neighbors['edges'])
            if game.edges[key].road is None
            and all(end not in path
                    for end in game.edges[key].neighbors['vertices'] if end != current)
        )
        game.edges[edge_key].road = {'player': player_name}
        player.roads.append(edge_key)
        current = next(
            end for end in game.edges[edge_key].neighbors['vertices'] if end != current
        )
        path.append(current)
    return path


def base_game(rules=None, players=('Alice', 'Bob'), seed=11):
    """A two-player base game past setup, seated in lobby order."""
    chosen = {'turn_order': 'lobby'}
    chosen.update(rules or {})
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen)
    game.start()
    game.game_phase = 'playing'
    game.start_turn()
    return game


def ck_game(rules=None, players=('Alice', 'Bob')):
    chosen = rules_module.preset_rules('cities_and_knights')
    chosen['turn_order'] = 'lobby'
    chosen.update(rules or {})
    game = Game(list(players), [], rng=random.Random(7), rules=chosen)
    game.game_phase = 'playing'
    game.start_turn()
    return game


class TestHoldADevelopmentCardATurn:
    """`dev_card_hold_a_turn`. Untested in either position — the default-on
    behaviour is the base-game rule that a card bought this turn is dead until
    the next one, and nothing was checking it."""

    @staticmethod
    def buy_a_monopoly(game, player_name='Alice'):
        """Stack the deck so the purchase is deterministic, then buy."""
        game.bank.dev_cards_deck = {'monopoly': 5}
        game.get_player(player_name).resources = {'ore': 1, 'wheat': 1, 'sheep': 1}
        bought = game.buy_dev_card(player_name)
        assert bought['success'] and bought['card_type'] == 'monopoly'

    def test_by_default_a_card_cannot_be_played_the_turn_it_was_bought(self):
        game = base_game()
        self.buy_a_monopoly(game)
        game.set_dice_rolled()

        result = game.play_dev_card('Alice', 'monopoly')

        assert not result['success']
        assert 'same turn it was purchased' in result['error']
        assert game.pending_monopoly is None

    def test_the_same_card_plays_once_the_turn_has_come_round(self):
        """The other half: the hold is a turn, not forever."""
        game = base_game()
        self.buy_a_monopoly(game)

        game.set_dice_rolled()
        assert game.advance_turn('Alice')['success']
        game.set_dice_rolled()
        assert game.advance_turn('Bob')['success']

        game.set_dice_rolled()
        assert game.play_dev_card('Alice', 'monopoly')['success']

    def test_a_table_that_turns_the_hold_off_may_play_it_at_once(self):
        game = base_game({'dev_card_hold_a_turn': False})
        self.buy_a_monopoly(game)
        game.set_dice_rolled()

        result = game.play_dev_card('Alice', 'monopoly')

        assert result['success'], result['error']
        assert result['needs_resource']


class TestTheRobberOnTheDesert:
    """`robber_may_return_to_desert`. Both branches of `robber_is_allowed` and
    of `friendly_robber_fallback` were unexercised."""

    @staticmethod
    def desert_and_elsewhere(game):
        desert = next(
            key for key, hex_obj in sorted(game.hexes.items()) if hex_obj.type == 'desert'
        )
        land = next(
            key for key, hex_obj in sorted(game.hexes.items())
            if hex_obj.type not in ('ocean', 'desert')
        )
        # The robber starts on the desert, and a move to where it already
        # stands is refused for a different reason.
        game.robber_hex = land
        game.must_move_robber = True
        return desert

    def test_by_default_the_desert_is_somewhere_the_robber_may_go(self):
        game = base_game()
        desert = self.desert_and_elsewhere(game)

        assert game.robber_is_allowed(desert)
        assert game.move_robber('Alice', desert)['success']
        assert game.robber_hex == desert

    def test_a_table_that_bars_the_desert_refuses_the_move(self):
        game = base_game({'robber_may_return_to_desert': False})
        desert = self.desert_and_elsewhere(game)

        assert not game.robber_is_allowed(desert)
        result = game.move_robber('Alice', desert)

        assert not result['success']
        assert game.robber_hex != desert
        assert game.must_move_robber, 'the robber is still owed'
        # NOTE: the refusal comes back as FRIENDLY_ROBBER with a message about
        # a player on two victory points, even at a table where Friendly Robber
        # is off — `move_robber` has one message for every `robber_is_allowed`
        # refusal. The player is told the wrong reason. Filed, not pinned here:
        # asserting the wrong code would make the bug permanent.

    def test_friendly_robber_has_nowhere_to_fall_back_to(self):
        """Friendly Robber sends the robber to the desert when every other hex
        is protected. With the desert barred as well there is no answer, and
        the fallback has to say so rather than name a hex the move would then
        refuse."""
        game = base_game({'friendly_robber': True})
        assert game.hexes[game.friendly_robber_fallback()].type == 'desert'

        barred = base_game({'friendly_robber': True, 'robber_may_return_to_desert': False})
        assert barred.friendly_robber_fallback() is None


class TestProgressCardsInHand:
    """`progress_hand_limit`. `hand_is_full` is only ever asked at its default
    of four; the number the lobby sets reached nothing under test."""

    @staticmethod
    def deal_three_to_alice(game):
        game.ck.improvements['Alice']['trade'] = 5
        game.ck.progress_decks['trade'] = ['merchant', 'commercial_harbor', 'merchant_fleet']
        for _ in range(3):
            game._deal_progress_cards('trade', 1)
        return game.ck.hand_of('Alice')

    def test_a_table_that_allows_two_stops_at_two(self):
        game = ck_game({'progress_hand_limit': 2})
        hand = self.deal_three_to_alice(game)

        assert len(hand) == 2
        assert game.ck.hand_is_full('Alice')
        # The card that would not fit went back under the deck, not out of play.
        assert game.ck.progress_decks['trade'] == ['merchant']

    def test_the_default_of_four_takes_all_three(self):
        game = ck_game()
        hand = self.deal_three_to_alice(game)

        assert len(hand) == 3
        assert not game.ck.hand_is_full('Alice')
        assert game.ck.progress_hand_limit == ck_module.PROGRESS_HAND_LIMIT


class TestCityWallsPerPlayer:
    """`max_city_walls`. The existing wall test builds up to the module
    constant, so it passes whatever the lobby asked for."""

    @staticmethod
    def alice_with_four_cities(game):
        player = game.get_player('Alice')
        player.cities = ['c1', 'c2', 'c3', 'c4']
        player.resources = {'brick': 99}
        return player

    def test_a_table_that_allows_one_wall_refuses_the_second(self):
        game = ck_game({'max_city_walls': 1})
        self.alice_with_four_cities(game)

        assert game.build_city_wall('Alice', 'c1')['success']
        refused = game.build_city_wall('Alice', 'c2')

        assert not refused['success']
        assert 'all 1 city walls' in refused['error']
        assert game.ck.walls_of('Alice') == ['c1']

    def test_a_table_that_allows_four_builds_four(self):
        game = ck_game({'max_city_walls': 4})
        self.alice_with_four_cities(game)

        for vertex_key in ('c1', 'c2', 'c3', 'c4'):
            assert game.build_city_wall('Alice', vertex_key)['success'], vertex_key
        assert len(game.ck.walls_of('Alice')) == 4

    def test_zero_walls_means_the_first_one_is_refused(self):
        """The catalogue's minimum. A table can switch walls off by number as
        well as by rule, and the two must agree."""
        game = ck_game({'max_city_walls': 0})
        self.alice_with_four_cities(game)

        assert not game.build_city_wall('Alice', 'c1')['success']
        assert game.ck.walls_of('Alice') == []


class TestShipsPerPlayer:
    """`max_ships`. The existing supply test fills the hand to `game.MAX_SHIPS`
    and so proves only that the engine agrees with itself."""

    @staticmethod
    def alice_at_sea(game):
        vertex_key = coastal_vertex(game)
        give_building(game, 'Alice', vertex_key)
        return ship_path(game, vertex_key, 4)[0]

    def test_a_table_that_allows_three_refuses_the_fourth(self):
        game = seafarers_game(max_ships=3)
        edges = self.alice_at_sea(game)

        for edge_key in edges[:3]:
            game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}
            assert game.build_ship('Alice', edge_key)['success'], edge_key

        game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}
        refused = game.build_ship('Alice', edges[3])

        assert refused['code'] == 'NO_PIECES_LEFT'
        assert 'all 3 ships' in refused['error']
        assert game.edges[edges[3]].ship is None

    def test_the_default_of_fifteen_lets_a_fourth_through(self):
        game = seafarers_game()
        edges = self.alice_at_sea(game)

        for edge_key in edges:
            game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}
            assert game.build_ship('Alice', edge_key)['success'], edge_key
        assert len(game.get_player('Alice').ships) == 4


class TestPointsForANewIsland:
    """`island_points_per_island`. Every island test asserts the number 2,
    which is the default written down twice."""

    @staticmethod
    def a_second_island(game):
        """Sink the ring around the centre hex, as tests/game/test_islands.py
        does, and return an intersection on the island that leaves."""
        centre = '0,0,0'
        for hex_key in game.hexes[centre].neighbors:
            game.hexes[hex_key].type = 'ocean'
            game.hexes[hex_key].number = None
        return next(
            key for key, vertex in sorted(game.vertices.items())
            if centre in vertex.neighbors['hexes']
        )

    def test_a_table_that_pays_five_scores_five(self):
        game = seafarers_game(island_points_per_island=5)
        landing = self.a_second_island(game)

        assert game.record_island_settlement('Alice', landing, award=True) == 5
        assert game.island_points['Alice'] == 5
        assert game.victory_points_for('Alice') == 5

    def test_the_default_pays_two(self):
        game = seafarers_game()
        landing = self.a_second_island(game)

        assert game.record_island_settlement('Alice', landing, award=True) == 2
        assert game.victory_points_for('Alice') == 2


class TestTheSpecialCards:
    """`largest_army_card` and `longest_road_card`. Both off-branches — the
    early return in `update_largest_army` and in `update_longest_road` — were
    never taken by a test."""

    @staticmethod
    def alice_plays_three_knights(game):
        player = game.get_player('Alice')
        player.knights_played = 3
        game.update_largest_army()

    def test_by_default_three_knights_take_the_largest_army(self):
        game = base_game()
        self.alice_plays_three_knights(game)

        assert game.largest_army_holder == 'Alice'
        assert game.victory_points_for('Alice') == 2

    def test_a_table_without_the_card_awards_nothing_for_an_army(self):
        game = base_game({'largest_army_card': False})
        self.alice_plays_three_knights(game)

        assert game.largest_army_holder is None
        assert game.victory_points_for('Alice') == 0

    @staticmethod
    def alice_builds_a_long_road(game):
        """Lay a run of connected sides straight into the graph — the road
        placement rules are not what is under test, the award is."""
        give_road_chain(game, 'Alice', game.rules['longest_road_minimum'])
        game.update_longest_road()
        assert game.calculate_longest_road('Alice') >= game.rules['longest_road_minimum']

    def test_by_default_a_long_road_takes_the_card(self):
        game = base_game()
        self.alice_builds_a_long_road(game)

        assert game.longest_road_holder == 'Alice'
        assert game.victory_points_for('Alice') == 2

    def test_a_table_without_the_card_awards_nothing_for_a_road(self):
        game = base_game({'longest_road_card': False})
        self.alice_builds_a_long_road(game)

        assert game.longest_road_holder is None
        assert game.victory_points_for('Alice') == 0


class TestTheBarbarianTrack:
    """`barbarian_track_length`. The number reaches `advance_barbarians`, and
    no test had ever moved it off seven."""

    @staticmethod
    def advance(game, times):
        arrived = False
        for _ in range(times):
            arrived = game.ck.advance_barbarians()
        return arrived

    def test_a_three_space_track_lands_the_ship_on_the_third_move(self):
        game = ck_game({'barbarian_track_length': 3})

        assert not self.advance(game, 2)
        assert self.advance(game, 1)

    def test_the_default_track_takes_seven(self):
        game = ck_game()

        assert not self.advance(game, 6)
        assert self.advance(game, 1)


class TestPieceSupplies:
    """`max_cities` and `max_roads`. Both are read into `MAX_*` at construction
    and refuse a build; only the settlement supply had a behavioural test."""

    def test_a_table_that_allows_one_city_refuses_the_second(self):
        game = base_game({'max_cities': 1})
        player = game.get_player('Alice')

        settlements = [
            key for key in sorted(game.vertices)
            if game.vertices[key].neighbors['hexes']
        ][:2]
        for vertex_key in settlements:
            give_building(game, 'Alice', vertex_key)

        player.resources = {'ore': 9, 'wheat': 9}
        assert game.upgrade_city('Alice', settlements[0])['success']

        refused = game.upgrade_city('Alice', settlements[1])
        assert refused['code'] == 'NO_PIECES_LEFT'
        assert 'all 1 cities' in refused['error']

    def test_a_table_that_allows_two_roads_refuses_the_third(self):
        """Driven through `build_road`, so the supply is checked on the path a
        player actually takes."""
        game = base_game({'max_roads': 2})
        player = game.get_player('Alice')
        vertex_key = a_vertex(game)
        give_building(game, 'Alice', vertex_key)

        laid = []
        for _ in range(2):
            edge_key = next(
                key for key in sorted(game.vertices[vertex_key].neighbors['edges'])
                if game.edges[key].road is None
            )
            player.resources = {'wood': 1, 'brick': 1}
            assert game.build_road('Alice', edge_key)['success'], edge_key
            laid.append(edge_key)

        player.resources = {'wood': 1, 'brick': 1}
        third = next(
            key for key in sorted(game.vertices[vertex_key].neighbors['edges'])
            if key not in laid and game.edges[key].road is None
        )
        refused = game.build_road('Alice', third)

        assert refused['code'] == 'NO_PIECES_LEFT'
        assert 'all 2 roads' in refused['error']
        assert game.edges[third].road is None


class TestTradeOfferClock:
    """`trade_offer_seconds`. The countdown a proposer and a responder both
    watch was a client literal, and the server's own expiry was a matching
    literal a table could not change.

    What a player would notice: an offer whose timer reads 0 that the proposer
    can still complete, or a table that asked for a minute to think and got ten
    seconds.
    """

    @staticmethod
    def an_offer(game):
        """Alice offers 1 wood for 1 brick, which no bank rate would take."""
        game.get_player('Alice').resources = {'wood': 1}
        game.get_player('Bob').resources = {'brick': 1}
        proposed = game.propose_trade('Alice', {'wood': 1}, {'brick': 1})
        assert proposed['success'] and proposed['kind'] == 'offer'
        return proposed['offer']

    @staticmethod
    def wind_back(offer, seconds):
        """Age an offer without waiting for it, as the turn timers do."""
        offer['created_at'] -= seconds

    @staticmethod
    def listed(game):
        return [offer['id'] for offer in game.get_board_data('Alice')['trades']['active']]

    def test_the_default_leaves_an_offer_standing_across_a_turn(self):
        """Regression (player report: "trade offers disappear on turn end").

        Nothing on the turn path clears an offer; the only thing that did was
        the default 10-second clock, which came due about when a turn ended.
        The default is now no clock at all, so an offer stands until it is taken
        or withdrawn. Fails on the old default: winding past 10s pruned it.
        """
        game = base_game()
        offer = self.an_offer(game)
        self.wind_back(offer, 3600)
        assert self.listed(game) == [offer['id']]

    def test_a_table_that_asks_for_a_minute_keeps_the_offer_that_long(self):
        game = base_game({'trade_offer_seconds': 60})
        offer = self.an_offer(game)
        self.wind_back(offer, 30)
        assert self.listed(game) == [offer['id']]

        self.wind_back(offer, 31)
        assert self.listed(game) == []

    def test_an_expired_offer_can_no_longer_be_completed(self):
        """The countdown was a lie: nothing on the completion path looked at
        the deadline, so an offer whose timer had reached 0 still moved cards
        as long as no board update had pruned it first. Runs with an explicit
        clock now the default is off."""
        game = base_game({'trade_offer_seconds': 10})
        offer = self.an_offer(game)
        assert game.accept_trade(offer['id'], 'Bob')['success']

        self.wind_back(offer, 11)
        refused = game.complete_trade(offer['id'], 'Alice', 'Bob')

        assert refused['success'] is False
        assert game.get_player('Alice').resources == {'wood': 1}
        assert game.get_player('Bob').resources == {'brick': 1}

    def test_an_expired_offer_can_no_longer_be_accepted(self):
        game = base_game({'trade_offer_seconds': 10})
        offer = self.an_offer(game)
        self.wind_back(offer, 11)

        refused = game.accept_trade(offer['id'], 'Bob')

        assert refused['success'] is False
        assert offer['accepted_by'] == {}

    def test_zero_means_an_offer_stands_until_somebody_takes_it(self):
        """A table that wants the physical game's non-existent trade clock."""
        game = base_game({'trade_offer_seconds': 0})
        offer = self.an_offer(game)
        self.wind_back(offer, 3600)

        assert self.listed(game) == [offer['id']]
        assert game.accept_trade(offer['id'], 'Bob')['success']
        assert game.complete_trade(offer['id'], 'Alice', 'Bob')['success']
        assert game.get_player('Bob').resources == {'brick': 0, 'wood': 1}
