"""Catan: Frenemies — favour tokens earned for pro-social acts.

Chunk 1: the bag, the blind draw, the not-this-turn lock, and the three
earn-triggers — a harmless robber move, gifting a resource to a player who is
not ahead of you, and joining your road network to an opponent's for the first
time. Later chunks add the guild-hall redemption.

Source: catan_frenemies_rules_093012s.pdf, the 3-4 player rules.
"""

import random
from collections import Counter

from game import rules as rules_module
from game.favours import FAVOUR_BAG_COMPOSITION, FAVOUR_BAG_SIZE
from game.game import Game


def frenemies_game(players=('Alice', 'Bob'), seed=12345, **overrides):
    """A base-board game past setup with the favour-token rule on.

    No buildings are placed, so every hex is harmless until a test puts one
    down — which is exactly what the robber-move triggers need to distinguish.
    """
    chosen = {'favour_tokens': True, 'turn_order': 'lobby'}
    chosen.update(overrides)
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.start_turn()
    game.has_rolled_dice = True
    return game


def _line(game, start_vertex):
    """A start vertex, an edge out of it, its far vertex, and a second edge
    out of that far vertex — three intersections in a row along real board
    geometry. Returns (first_edge, middle_vertex, second_edge, end_vertex)."""
    first = next(
        key for key in sorted(game.edges)
        if start_vertex in game.edges[key].neighbors['vertices']
    )
    middle = next(v for v in game.edges[first].neighbors['vertices'] if v != start_vertex)
    second = next(
        key for key in sorted(game.edges)
        if key != first and middle in game.edges[key].neighbors['vertices']
    )
    end = next(v for v in game.edges[second].neighbors['vertices'] if v != middle)
    return first, middle, second, end


def _land_hex_without_building(game):
    """A land hex with nothing built on any of its corners."""
    for key, hex_obj in game.hexes.items():
        if hex_obj.type in ('ocean', 'sea'):
            continue
        if not game._favour_hex_has_building(key):
            return key
    raise AssertionError('no empty land hex on the board')


class TestTheBag:
    def test_the_bag_holds_the_rulebook_58_tokens(self):
        """The 4-player supply is 8 Trader, 8 Merchant, 8 Road Builder, 17
        Scholar and 17 Master Builder — 58 tokens (p. 1). Asserted against the
        bag the game actually dealt, not a second copy of the literal."""
        game = frenemies_game()
        assert len(game.favour_bag) == FAVOUR_BAG_SIZE == 58
        assert Counter(game.favour_bag) == FAVOUR_BAG_COMPOSITION

    def test_a_base_game_deals_no_bag(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        assert game.favour_bag == []
        assert game.frenemies_client_state('Alice') is None


class TestHarmlessRobber:
    def test_a_move_to_an_empty_hex_earns_one_favour(self):
        game = frenemies_game()
        game.robber_hex = None
        game.must_move_robber = True
        target = _land_hex_without_building(game)

        result = game.move_robber('Alice', target)

        assert result['success']
        assert game.favour_holdings_total('Alice') == 1

    def test_a_move_that_can_rob_someone_earns_nothing(self):
        game = frenemies_game()
        game.robber_hex = None
        game.must_move_robber = True
        # Put Bob on a corner of a land hex, then send the robber there.
        target = next(k for k, h in game.hexes.items() if h.type not in ('ocean', 'sea', 'desert'))
        corner = next(v for v in sorted(game.vertices)
                      if target in game.vertices[v].neighbors.get('hexes', []))
        game.vertices[corner].building = {'type': 'settlement', 'player': 'Bob'}
        game.get_player('Bob').settlements.append(corner)

        result = game.move_robber('Alice', target)

        assert result['success']
        assert result['victims'] == ['Bob']
        assert game.favour_holdings_total('Alice') == 0

    def test_a_move_to_a_hex_touching_only_your_own_building_earns_nothing(self):
        """Way 1 is a hex with *no* surrounding settlement or city; one touching
        only the mover's own building is not it (p. 1)."""
        game = frenemies_game()
        game.robber_hex = None
        game.must_move_robber = True
        target = next(k for k, h in game.hexes.items() if h.type not in ('ocean', 'sea', 'desert'))
        corner = next(v for v in sorted(game.vertices)
                      if target in game.vertices[v].neighbors.get('hexes', []))
        game.vertices[corner].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(corner)

        game.move_robber('Alice', target)

        assert game.favour_holdings_total('Alice') == 0

    def test_declining_to_steal_on_the_desert_earns_a_favour(self):
        game = frenemies_game()
        desert = next(k for k, h in game.hexes.items() if h.type == 'desert')
        corner = next(v for v in sorted(game.vertices)
                      if desert in game.vertices[v].neighbors.get('hexes', []))
        game.vertices[corner].building = {'type': 'settlement', 'player': 'Bob'}
        game.get_player('Bob').settlements.append(corner)
        game.robber_hex = None
        game.must_move_robber = True

        moved = game.move_robber('Alice', desert)
        assert moved['victims'] == ['Bob']  # a real steal is on offer
        assert game.favour_holdings_total('Alice') == 0  # not yet earned

        declined = game.decline_steal('Alice')
        assert declined['success']
        assert not game.must_choose_victim
        assert game.favour_holdings_total('Alice') == 1

    def test_declining_a_steal_off_the_desert_is_refused(self):
        game = frenemies_game()
        target = next(k for k, h in game.hexes.items() if h.type not in ('ocean', 'sea', 'desert'))
        corner = next(v for v in sorted(game.vertices)
                      if target in game.vertices[v].neighbors.get('hexes', []))
        game.vertices[corner].building = {'type': 'settlement', 'player': 'Bob'}
        game.get_player('Bob').settlements.append(corner)
        game.robber_hex = None
        game.must_move_robber = True
        game.move_robber('Alice', target)

        result = game.decline_steal('Alice')
        assert not result['success']
        assert result['code'] == 'NOT_HARMLESS'
        assert game.favour_holdings_total('Alice') == 0


class TestGift:
    def test_gifting_to_an_opponent_not_ahead_earns_a_favour(self):
        game = frenemies_game()
        game.get_player('Alice').resources = {'wood': 1}

        result = game.gift_resource('Alice', 'Bob', 'wood')

        assert result['success']
        assert game.get_player('Alice').resources.get('wood', 0) == 0
        assert game.get_player('Bob').resources.get('wood', 0) == 1
        assert game.favour_holdings_total('Alice') == 1

    def test_gifting_to_an_opponent_who_is_ahead_is_refused(self):
        game = frenemies_game()
        game.get_player('Alice').resources = {'wood': 1}
        # Bob has a settlement: 1 visible point to Alice's 0.
        bob_vertex = sorted(game.vertices)[0]
        game.vertices[bob_vertex].building = {'type': 'settlement', 'player': 'Bob'}
        game.get_player('Bob').settlements.append(bob_vertex)

        result = game.gift_resource('Alice', 'Bob', 'wood')

        assert not result['success']
        assert result['code'] == 'RECIPIENT_AHEAD'
        assert game.get_player('Alice').resources.get('wood', 0) == 1
        assert game.favour_holdings_total('Alice') == 0

    def test_only_one_gift_a_turn(self):
        game = frenemies_game()
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1}

        assert game.gift_resource('Alice', 'Bob', 'wood')['success']
        second = game.gift_resource('Alice', 'Bob', 'brick')
        assert not second['success']
        assert second['code'] == 'ALREADY_GIFTED'
        assert game.favour_holdings_total('Alice') == 1


class TestNetworkConnection:
    def _setup_neighbouring_networks(self, game):
        """Alice's road reaches a middle vertex; Bob has a road on the far
        vertex Alice's next road will reach. Returns the edge Alice must build."""
        home = sorted(game.vertices)[0]
        game.vertices[home].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(home)
        first, middle, second, end = _line(game, home)
        # Alice's existing road toward the middle vertex.
        game.edges[first].road = {'player': 'Alice'}
        game.get_player('Alice').roads.append(first)
        # Bob's road hanging off the far vertex `second` will reach.
        third = next(
            key for key in sorted(game.edges)
            if key not in (first, second) and end in game.edges[key].neighbors['vertices']
        )
        game.edges[third].road = {'player': 'Bob'}
        game.get_player('Bob').roads.append(third)
        return second

    def test_first_connection_pays_three_to_you_and_one_to_them(self):
        game = frenemies_game()
        second = self._setup_neighbouring_networks(game)
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1}

        result = game.build_road('Alice', second)

        assert result['success'], result
        assert game.favour_holdings_total('Alice') == 3
        assert game.favour_holdings_total('Bob') == 1

    def test_a_second_road_between_the_same_networks_pays_nothing(self):
        game = frenemies_game()
        second = self._setup_neighbouring_networks(game)
        game.get_player('Alice').resources = {'wood': 2, 'brick': 2}
        game.build_road('Alice', second)
        before_alice = game.favour_holdings_total('Alice')
        before_bob = game.favour_holdings_total('Bob')

        # Any further Alice road cannot re-pay the Alice/Bob pair.
        another = next(
            key for key in sorted(game.edges)
            if game.edges[key].road is None
            and game._road_connects('Alice', key)
            and game.land_hexes_of_edge(key)
        )
        game.build_road('Alice', another)

        assert game.favour_holdings_total('Alice') == before_alice
        assert game.favour_holdings_total('Bob') == before_bob

    def test_connecting_your_own_networks_pays_nothing(self):
        """You never earn favours for joining your own roads (p. 1)."""
        game = frenemies_game()
        home = sorted(game.vertices)[0]
        game.vertices[home].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(home)
        first, middle, second, end = _line(game, home)
        game.edges[first].road = {'player': 'Alice'}
        game.get_player('Alice').roads.append(first)
        # A second Alice road on the far vertex — joining two of her own runs.
        third = next(
            key for key in sorted(game.edges)
            if key not in (first, second) and end in game.edges[key].neighbors['vertices']
        )
        game.edges[third].road = {'player': 'Alice'}
        game.get_player('Alice').roads.append(third)
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1}

        game.build_road('Alice', second)

        assert game.favour_holdings_total('Alice') == 0


class TestNotThisTurn:
    def test_a_favour_drawn_on_your_turn_is_locked_until_your_next(self):
        """A token you draw during your own turn may not be used until your next
        turn (p. 2). It is usable the moment an opponent draws it, though."""
        game = frenemies_game()
        game.get_player('Alice').resources = {'wood': 1}
        game.gift_resource('Alice', 'Bob', 'wood')

        # Locked now: held but not usable.
        assert game.favour_holdings_total('Alice') == 1
        assert sum(game.favour_usable.get('Alice', {}).values()) == 0
        assert sum(game.favour_locked.get('Alice', {}).values()) == 1

        # Round back to Alice: the lock lifts at the start of her next turn.
        game.advance_turn('Alice')
        game.advance_turn('Bob')
        assert game.current_player_name() == 'Alice'
        assert sum(game.favour_usable.get('Alice', {}).values()) == 1
        assert sum(game.favour_locked.get('Alice', {}).values()) == 0


def guild_game(**overrides):
    """A Frenemies game with the guild hall on, no favours yet held."""
    return frenemies_game(guild_hall=True, **overrides)


class TestGuildRedemption:
    def test_traders_swap_one_resource_for_another_at_the_bank(self):
        game = guild_game()
        game.favour_usable['Alice'] = {'trader': 1}
        game.get_player('Alice').resources = {'wood': 1}

        result = game.redeem_favour('Alice', 'trader', give='wood', receive='ore')

        assert result['success'], result
        assert game.get_player('Alice').resources.get('wood', 0) == 0
        assert game.get_player('Alice').resources.get('ore', 0) == 1
        assert game.favour_usable['Alice'].get('trader', 0) == 0

    def test_traders_will_not_swap_for_the_same_resource(self):
        game = guild_game()
        game.favour_usable['Alice'] = {'trader': 1}
        game.get_player('Alice').resources = {'wood': 1}

        result = game.redeem_favour('Alice', 'trader', give='wood', receive='wood')
        assert not result['success']
        assert result['code'] == 'INVALID_RESOURCE'
        assert game.favour_usable['Alice']['trader'] == 1  # token not spent

    def test_merchants_take_any_one_resource(self):
        game = guild_game()
        game.favour_usable['Alice'] = {'merchant': 1}

        result = game.redeem_favour('Alice', 'merchant', resource='ore')
        assert result['success']
        assert game.get_player('Alice').resources.get('ore', 0) == 1
        assert game.favour_usable['Alice'].get('merchant', 0) == 0

    def test_road_builders_grant_a_free_road(self):
        game = guild_game()
        game.favour_usable['Alice'] = {'road_builder': 1}

        result = game.redeem_favour('Alice', 'road_builder')
        assert result['success']
        assert game.free_roads_remaining == 1
        assert game.favour_usable['Alice'].get('road_builder', 0) == 0

    def test_scholars_draw_a_development_card_for_two_tokens(self):
        game = guild_game()
        game.favour_usable['Alice'] = {'scholar': 2}
        before = game.get_player('Alice').total_dev_cards()

        result = game.redeem_favour('Alice', 'scholar')
        assert result['success']
        assert game.get_player('Alice').total_dev_cards() == before + 1
        assert game.favour_usable['Alice'].get('scholar', 0) == 0

    def test_a_scholar_favour_needs_two_tokens(self):
        game = guild_game()
        game.favour_usable['Alice'] = {'scholar': 1}

        result = game.redeem_favour('Alice', 'scholar')
        assert not result['success']
        assert result['code'] == 'NOT_ENOUGH_FAVOURS'
        assert game.favour_usable['Alice']['scholar'] == 1

    def test_master_builders_hand_out_a_victory_point_marker(self):
        game = guild_game()
        game.favour_usable['Alice'] = {'master_builder': 2}
        before = game.victory_points_for('Alice')

        result = game.redeem_favour('Alice', 'master_builder')
        assert result['success']
        assert game.favour_vp_markers['Alice'] == 1
        assert game.favour_vp_supply == 7
        assert game.victory_points_for('Alice') == before + 1

    def test_the_marker_supply_is_eight_and_runs_out(self):
        """There are 8 Victory-Point markers (p. 1)."""
        game = guild_game()
        assert game.favour_vp_supply == 8
        game.favour_vp_supply = 0
        game.favour_usable['Alice'] = {'master_builder': 2}

        result = game.redeem_favour('Alice', 'master_builder')
        assert not result['success']
        assert result['code'] == 'NO_VP_MARKERS'
        assert game.favour_usable['Alice']['master_builder'] == 2

    def test_a_token_drawn_this_turn_cannot_be_redeemed(self):
        """Locked tokens are not usable until your next turn (p. 2)."""
        game = guild_game()
        game.favour_locked['Alice'] = {'merchant': 1}

        result = game.redeem_favour('Alice', 'merchant', resource='ore')
        assert not result['success']
        assert result['code'] == 'NOT_ENOUGH_FAVOURS'


class TestGuildExchange:
    def test_exchange_draws_one_and_returns_one(self):
        game = guild_game()
        game.favour_bag = ['trader', 'scholar']  # 'scholar' drawn (popped)
        game.favour_usable['Alice'] = {'merchant': 1}

        result = game.exchange_favour('Alice', 'merchant')
        assert result['success']
        assert result['drawn'] == 'scholar'
        assert result['returned'] == 'merchant'
        # The scholar is now held; the merchant went back to the bag.
        assert game.favour_usable['Alice'].get('scholar', 0) == 1
        assert game.favour_usable['Alice'].get('merchant', 0) == 0
        assert 'merchant' in game.favour_bag

    def test_a_turn_redeems_or_exchanges_never_both(self):
        game = guild_game()
        game.favour_usable['Alice'] = {'merchant': 2}
        assert game.redeem_favour('Alice', 'merchant', resource='ore')['success']

        blocked = game.exchange_favour('Alice', 'merchant')
        assert not blocked['success']
        assert blocked['code'] == 'ALREADY_REDEEMED'

    def test_only_one_exchange_a_turn(self):
        game = guild_game()
        game.favour_bag = ['trader', 'trader', 'scholar']
        game.favour_usable['Alice'] = {'merchant': 1}
        assert game.exchange_favour('Alice', 'merchant')['success']

        second = game.exchange_favour('Alice', 'scholar')
        assert not second['success']
        assert second['code'] == 'ALREADY_EXCHANGED'


class TestGuildDependency:
    def test_the_guild_hall_needs_the_favour_tokens(self):
        problems = rules_module.dependency_problems(
            rules_module.coerce({'guild_hall': True}))
        assert any('Guild hall' in problem for problem in problems)

    def test_the_favour_markers_score_only_with_the_guild(self):
        game = frenemies_game()  # favours on, guild off
        game.favour_vp_markers['Alice'] = 3
        assert game.favour_victory_points('Alice') == 0


class TestPreset:
    def test_the_frenemies_preset_ticks_favours_and_the_guild_at_eleven(self):
        chosen = rules_module.preset_rules('frenemies')
        assert chosen['favour_tokens'] is True
        assert chosen['guild_hall'] is True
        assert chosen['victory_target'] == 11

    def test_the_rule_suggests_eleven_points(self):
        rule = next(r for r in rules_module.RULES if r['id'] == 'favour_tokens')
        assert rule['suggests_victory_target'] == 11
