"""The Fishermen of Catan: fish production, the spend ladder, the old boot and
the robber that starts off the board.

Every assertion is against the live engine — a settlement placed on a real
fishing-ground vertex and the actual roll that pays it, a hand seeded into the
real supply and spent through the real ladder — never a copied literal. What a
player would notice if one broke: fish that never arrive, a benefit that eats
tokens without paying, a boot that lets its holder win a point early, or a
robber that sits on the board from turn one.
"""

import random

import pytest
from game import map_store, maps
from game import rules as rules_module
from game import tb as tb_module
from game.game import Game


def fishermen_game(overrides=None, players=('Alice', 'Bob', 'Carol')):
    chosen = dict(rules_module.TB_FISHERMEN_RULES)
    if overrides:
        chosen.update(overrides)
    defn = maps.parse_map(map_store.read_map('fishermen'))
    game = Game(list(players), [], rng=random.Random(99), rules=chosen, map_definition=defn)
    game.game_phase = 'playing'
    # A deterministic, boot-free, abundant supply so production draws count
    # exactly. The boot draw and the short supply are exercised by their own
    # tests, which set the supply themselves.
    game.tb.supply = [1, 2, 3] * 20
    game.tb.discard = []
    return game


def a_fishing_ground(game, number=None):
    for ground in game.tb.fishing_grounds:
        if number is None or ground['number'] == number:
            return ground
    raise AssertionError('no fishing ground found')


def lake_vertices(game):
    return [
        key for key, vertex in game.vertices.items()
        if game.tb.lake_hex in vertex.neighbors.get('hexes', [])
    ]


class TestCatalogue:
    def test_the_preset_ticks_exactly_the_scenario(self):
        chosen = rules_module.preset_rules('tb_fishermen')
        for rule_id in ('fish_tokens', 'fishing_grounds', 'lake_hex', 'old_boot',
                        'robber_starts_off_board'):
            assert chosen[rule_id] is True, rule_id
        assert chosen['board_map'] == 'fishermen'
        assert chosen['victory_target'] == 10

    def test_the_scenario_is_coherent(self):
        chosen = rules_module.preset_rules('tb_fishermen')
        assert rules_module.dependency_problems(chosen) == []
        assert rules_module.exclusion_problems(chosen) == []

    def test_the_fish_sources_need_the_token_supply(self):
        """A fishing ground, the lake or the boot with no supply is refused, not
        propped up (DEPENDENCIES)."""
        for rule_id in ('fishing_grounds', 'lake_hex', 'old_boot'):
            chosen = rules_module.coerce({rule_id: True})
            assert rules_module.dependency_problems(chosen), rule_id

    def test_every_fish_rule_is_off_in_the_base_game(self):
        chosen = rules_module.defaults()
        for rule_id in ('fish_tokens', 'fishing_grounds', 'lake_hex', 'old_boot',
                        'robber_starts_off_board'):
            assert chosen[rule_id] is False, rule_id
        assert chosen['max_fish_held'] == 7
        assert chosen['fishing_ground_count'] == 6

    def test_fishing_ground_count_caps_how_many_the_board_carries(self):
        """The int rule is read at board setup — a lower count leaves the extra
        printed tiles off, so it is not a dead switch."""
        game = fishermen_game({'fishing_ground_count': 2})
        assert len(game.tb.fishing_grounds) == 2
        full = fishermen_game()
        assert len(full.tb.fishing_grounds) == 6

    def test_the_container_needs_the_tb_state_object(self):
        assert rules_module.needs_tb_state({'fish_tokens': True})
        assert not rules_module.needs_tb_state(rules_module.defaults())
        # robber_starts_off_board alone needs no container.
        assert not rules_module.needs_tb_state({'robber_starts_off_board': True})


class TestFishingGroundProduction:
    def test_a_settlement_draws_one_fish_on_the_ground_number(self):
        game = fishermen_game()
        ground = a_fishing_ground(game)
        vertex = ground['vertices'][0]
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}

        drawn = game.distribute_fish(ground['number'])

        assert drawn == {'Alice': 1}
        assert game.tb.held_fish('Alice') == 1

    def test_a_city_draws_two_fish(self):
        game = fishermen_game()
        ground = a_fishing_ground(game)
        vertex = ground['vertices'][0]
        game.vertices[vertex].building = {'type': 'city', 'player': 'Alice'}

        drawn = game.distribute_fish(ground['number'])

        assert drawn == {'Alice': 2}
        assert game.tb.held_fish('Alice') == 2

    def test_no_fish_on_a_number_the_ground_does_not_carry(self):
        game = fishermen_game()
        ground = a_fishing_ground(game)
        vertex = ground['vertices'][0]
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}

        other = next(n for n in (4, 5, 6, 8, 9, 10) if n != ground['number'])
        drawn = game.distribute_fish(other)

        assert drawn == {}
        assert game.tb.held_fish('Alice') == 0

    def test_a_building_off_the_ground_draws_nothing(self):
        """Only the three coastal intersections a ground touches collect (498)."""
        game = fishermen_game()
        ground = a_fishing_ground(game)
        on_ground = set(ground['vertices'])
        off_ground = next(k for k in game.vertices if k not in on_ground)
        game.vertices[off_ground].building = {'type': 'city', 'player': 'Bob'}

        assert game.distribute_fish(ground['number']) == {}


class TestLakeProduction:
    @pytest.mark.parametrize('number', [2, 3, 11, 12])
    def test_the_lake_pays_on_its_four_numbers(self, number):
        game = fishermen_game()
        vertex = lake_vertices(game)[0]
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}

        assert game.distribute_fish(number) == {'Alice': 1}

    def test_a_city_on_the_lake_draws_two(self):
        game = fishermen_game()
        vertex = lake_vertices(game)[0]
        game.vertices[vertex].building = {'type': 'city', 'player': 'Alice'}

        assert game.distribute_fish(2) == {'Alice': 2}

    def test_the_lake_is_silent_on_a_producing_number(self):
        game = fishermen_game()
        vertex = lake_vertices(game)[0]
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}

        assert game.distribute_fish(8) == {}


class TestShortSupply:
    def test_nobody_draws_when_the_supply_cannot_cover_the_table(self):
        """If there are not enough fish for everyone's production, nobody gets
        any that turn (515)."""
        game = fishermen_game()
        ground = a_fishing_ground(game)
        # Two cities want 2 fish each — four in all.
        for i, vertex in enumerate(ground['vertices'][:2]):
            owner = ('Alice', 'Bob')[i]
            game.vertices[vertex].building = {'type': 'city', 'player': owner}

        game.tb.supply = [1, 1, 1]      # only three tokens anywhere
        game.tb.discard = []

        drawn = game.distribute_fish(ground['number'])

        assert drawn == {}
        assert game.tb.held_fish('Alice') == 0
        assert game.tb.held_fish('Bob') == 0
        assert 'fish_supply_short' in game.production_modifiers

    def test_exactly_enough_supply_pays_out(self):
        game = fishermen_game()
        ground = a_fishing_ground(game)
        game.vertices[ground['vertices'][0]].building = {'type': 'city', 'player': 'Alice'}

        game.tb.supply = [1, 1]
        game.tb.discard = []

        assert game.distribute_fish(ground['number']) == {'Alice': 2}


class TestTheSupply:
    def test_the_box_holds_twenty_nine_fish_and_the_boot(self):
        """11 ones + 10 twos + 8 threes + the boot (508, 517)."""
        supply = tb_module.TB(rng=random.Random(1))
        supply.seed_supply()
        assert supply.supply_count() == 30
        fish = [t for t in supply.supply if t != tb_module.BOOT]
        assert sorted(fish) == [1] * 11 + [2] * 10 + [3] * 8
        assert supply.supply.count(tb_module.BOOT) == 1

    def test_the_hand_cap_is_not_exceeded(self):
        game = fishermen_game()
        game.tb.hands['Alice'] = [1] * game.rules['max_fish_held']
        game.tb.supply = [2]

        result = game.tb.draw_to_hand('Alice', game.rules['max_fish_held'])

        assert result == 'capped'
        assert game.tb.held_fish('Alice') == game.rules['max_fish_held']

    def test_the_bag_reshuffles_from_the_discard_when_it_empties(self):
        supply = tb_module.TB(rng=random.Random(1))
        supply.supply = []
        supply.discard = [1, 2, 3]
        drawn = supply.draw_raw()
        assert drawn in (1, 2, 3)
        assert supply.supply_count() == 2


class TestSpendLadder:
    def _ready(self, benefit_hand):
        game = fishermen_game()
        game.tb.hands['Alice'] = list(benefit_hand)
        return game

    def test_two_fish_send_the_robber_off_the_board(self):
        game = self._ready([2])
        game.robber_hex = '3,-3,0'
        result = game.spend_fish('Alice', 'robber_off', [2])
        assert result['success']
        assert game.robber_hex is None
        assert game.tb.held_fish('Alice') == 0

    def test_three_fish_steal_a_card(self):
        game = self._ready([1, 2])
        game.get_player('Bob').resources = {'wood': 3}
        result = game.spend_fish('Alice', 'steal', [1, 2], target='Bob')
        assert result['success']
        assert result['stolen'] == 'wood'
        assert game.get_player('Alice').resources.get('wood', 0) == 1
        assert game.get_player('Bob').resources['wood'] == 2

    def test_four_fish_take_a_bank_card(self):
        game = self._ready([2, 2])
        before = game.bank.resources['ore']
        result = game.spend_fish('Alice', 'bank_card', [2, 2], resource='ore')
        assert result['success']
        assert game.get_player('Alice').resources.get('ore', 0) == 1
        assert game.bank.resources['ore'] == before - 1

    def test_five_fish_grant_a_free_road(self):
        game = self._ready([2, 3])
        result = game.spend_fish('Alice', 'free_road', [2, 3])
        assert result['success']
        assert game.free_roads_remaining == 1

    def test_seven_fish_draw_a_free_dev_card(self):
        game = self._ready([1, 3, 3])
        before = game.bank.total_dev_cards_remaining()
        result = game.spend_fish('Alice', 'free_dev', [1, 3, 3])
        assert result['success']
        held = sum(c['count'] for c in game.get_player('Alice').dev_cards.values())
        assert held == 1
        assert game.bank.total_dev_cards_remaining() == before - 1

    def test_a_total_below_the_price_is_refused_and_keeps_the_fish(self):
        game = self._ready([1])
        result = game.spend_fish('Alice', 'steal', [1], target='Bob')
        assert not result['success']
        assert result['code'] == 'NOT_ENOUGH_FISH'
        assert game.tb.hand('Alice') == [1]

    def test_overpaying_loses_the_excess(self):
        """No change is given: a 3-token for the 2-benefit still costs the whole
        token (521)."""
        game = self._ready([3])
        game.robber_hex = '3,-3,0'
        result = game.spend_fish('Alice', 'robber_off', [3])
        assert result['success']
        assert game.tb.held_fish('Alice') == 0

    def test_spending_tokens_you_do_not_hold_is_refused(self):
        game = self._ready([1, 1])
        result = game.spend_fish('Alice', 'steal', [3], target='Bob')
        assert not result['success']
        assert game.tb.hand('Alice') == [1, 1]

    def test_a_refused_bank_card_eats_no_fish(self):
        game = self._ready([2, 2])
        game.bank.resources['ore'] = 0
        result = game.spend_fish('Alice', 'bank_card', [2, 2], resource='ore')
        assert not result['success']
        assert game.tb.hand('Alice') == [2, 2]

    def test_only_the_current_player_may_spend(self):
        game = self._ready([2, 2])
        game.tb.hands['Bob'] = [2, 2]
        result = game.spend_fish('Bob', 'bank_card', [2, 2], resource='ore')
        assert not result['success']
        assert result['code'] == 'NOT_YOUR_TURN'


class TestFishAreNotResourceCards:
    def test_fish_never_count_toward_the_discard_limit(self):
        """Fish are not cards, so a 7 does not force a hand holding only fish to
        discard (523)."""
        game = fishermen_game()
        game.tb.hands['Alice'] = [3, 3, 3, 3, 3]   # 15 fish pips, 5 tokens
        game.get_player('Alice').resources = {'wood': 3}   # under the limit

        game.check_discard_required()

        assert 'Alice' not in game.players_needing_discard

    def test_a_seven_leaves_the_fish_hand_untouched(self):
        game = fishermen_game()
        game.tb.hands['Alice'] = [1, 2, 3]
        game.current_player_index = 0
        game.get_player('Alice').resources = {'wood': 8}
        game.next_dice = lambda: (3, 4)   # a 7

        game.roll_dice('Alice')

        # The 7 forces a resource discard but never a fish discard.
        assert game.tb.hand('Alice') == [1, 2, 3]
        assert 'Alice' in game.players_needing_discard


class TestOldBoot:
    def test_the_boot_raises_only_its_holders_threshold(self):
        game = fishermen_game()
        game.tb.old_boot_holder = 'Alice'
        assert game.personal_target_delta('Alice') == 1
        assert game.personal_target_delta('Bob') == 0

    def test_the_holder_needs_one_more_point_to_win(self):
        game = fishermen_game()
        game.tb.old_boot_holder = 'Alice'
        alice = game.get_player('Alice')
        # Ten settlements' worth of points by fiat — enough for the base target.
        alice.victory_points = 10
        # 10 is the table target, but the boot pushes Alice's own target to 11.
        assert game.claim_victory('Alice') is None
        alice.victory_points = 11
        assert game.claim_victory('Alice') == 11

    def test_a_non_holder_still_wins_on_the_table_target(self):
        game = fishermen_game()
        game.tb.old_boot_holder = 'Alice'
        game.get_player('Bob').victory_points = 10
        assert game.claim_victory('Bob') == 10

    def test_the_boot_passes_to_a_player_with_equal_or_more_points(self):
        game = fishermen_game()
        game.tb.old_boot_holder = 'Alice'
        game.current_player_index = 0
        game.has_rolled_dice = True
        game.get_player('Alice').victory_points = 3
        game.get_player('Bob').victory_points = 3

        result = game.pass_old_boot('Alice', 'Bob')

        assert result['success']
        assert game.tb.old_boot_holder == 'Bob'

    def test_the_sole_leader_may_not_pass_the_boot(self):
        game = fishermen_game()
        game.tb.old_boot_holder = 'Alice'
        game.current_player_index = 0
        game.has_rolled_dice = True
        game.get_player('Alice').victory_points = 5
        game.get_player('Bob').victory_points = 3

        result = game.pass_old_boot('Alice', 'Bob')

        assert not result['success']
        assert result['code'] == 'BOOT_STAYS'
        assert game.tb.old_boot_holder == 'Alice'


class TestRobberStartsOffBoard:
    def test_the_robber_begins_off_the_board(self):
        game = fishermen_game()
        assert game.robber_hex is None

    def test_the_first_seven_brings_the_robber_in(self):
        game = fishermen_game()
        game.current_player_index = 0
        game.has_rolled_dice = False
        # Force the dice to a 7.
        game.next_dice = lambda: (3, 4)
        result = game.roll_dice('Alice')
        assert result['total'] == 7
        assert game.must_move_robber is True


class TestBaseGameUnchanged:
    def test_a_base_game_has_no_fish_state(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        assert game.tb is None

    def test_a_base_game_roll_carries_an_empty_fish_payload(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        game.game_phase = 'playing'
        game.current_player_index = 0
        result = game.roll_dice('Alice')
        assert result['fish'] == {}

    def test_a_base_game_leaves_the_robber_on_the_desert(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        assert game.robber_hex is not None
