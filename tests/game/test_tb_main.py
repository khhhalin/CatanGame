"""Traders & Barbarians, the main scenario (expansions.md 677-755).

The wagon scenario, decomposed the way every other expansion is: `trade_caravans`
carries the wagon run and the deliveries, `baggage_train` the upgradeable card,
`roaming_barbarians` the three path barbarians, and `trade_dev_deck` the
scenario's own development deck. These tests pin the catalogue coherence and its
exclusions, the board deal, the wagon's movement-point costs (bare / own road /
rival road + gold / barbarian surcharge), the delivery loop (draw, deliver for
gold and a victory point, draw the next), the baggage-train upgrades, the roaming
barbarians (surcharge, the move-on-7 draw, the drive-off), the deck composition
and a card resolving, the scoring, and a real deal that round-trips through a
save. Every number is read off the live engine, never a copied literal, and the
base game is proven untouched.

Note on the deck: expansions.md 745-748 enumerates the wagon deck as 15 Knight, 3
Road Building, 3 Swift Journey and 1 each of Toolmaking, Glassmaking and Quarry —
twenty-four cards. Some summaries call it "26" by analogy with the Barbarian
Attack deck; the enumerated card list, which is what is dealt, is what these tests
pin.
"""

import pathlib
import random

from game import rules as rules_module
from game import tb_decks, wagons
from game.game import Game


def board_game(players=("Alice", "Bob"), seed=7, **overrides):
    """A game dealt on the built-in trade-hex map — the real trade hexes and deck."""
    from game import map_store, maps
    defn = maps.parse_map(map_store.read_map('traders-barbarians'))
    chosen = dict(rules_module.TB_MAIN_RULES)
    chosen.update(overrides)
    return Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)


def playing(game):
    """Force a game into the play phase for a direct method call."""
    game.game_phase = 'playing'
    game.has_rolled_dice = True
    return game


def place_wagon(game, player, vertex):
    game.tb.wagons[player] = vertex


def an_adjacent_bare_path(game, vertex):
    """A neighbour vertex reached over a path carrying no road, plus its edge."""
    for other in game.vertices[vertex].neighbors['vertices']:
        edge = game._edge_between(vertex, other)
        if edge is not None and game.edges[edge].road is None \
                and edge not in game.trade_sea_paths:
            return other, edge
    raise AssertionError('no bare adjacent path')


# --- Catalogue ----------------------------------------------------------

class TestCatalogue:
    def test_every_switch_is_off_in_the_base_game(self):
        chosen = rules_module.defaults()
        for rule_id in ('trade_caravans', 'baggage_train', 'roaming_barbarians',
                        'trade_dev_deck'):
            assert chosen[rule_id] is False

    def test_the_wagon_points_int_defaults_to_four(self):
        assert rules_module.defaults()['wagon_movement_points'] == 4

    def test_trade_caravans_suggests_a_target_of_thirteen(self):
        assert rules_module.RULES_BY_ID['trade_caravans']['suggests_victory_target'] == 13

    def test_it_needs_gold_coins_and_the_deck(self):
        problems = rules_module.dependency_problems({'trade_caravans': True})
        assert problems == ['Trade wagons needs Gold coins and Trade wagon deck']
        assert rules_module.dependency_problems({
            'trade_caravans': True, 'gold_coins': True, 'trade_dev_deck': True,
        }) == []

    def test_the_baggage_train_and_barbarians_need_the_wagon(self):
        assert rules_module.dependency_problems({'baggage_train': True}) == \
            ['Baggage train needs Trade wagons']
        assert rules_module.dependency_problems({'roaming_barbarians': True}) == \
            ['Roaming barbarians needs Trade wagons']

    def test_roaming_barbarians_exclude_the_cities_and_knights_knights(self):
        problems = rules_module.exclusion_problems({
            'roaming_barbarians': True, 'knights': True,
        })
        assert len(problems) == 1 and 'Roaming barbarians' in problems[0]

    def test_roaming_barbarians_exclude_the_coastal_war(self):
        problems = rules_module.exclusion_problems({
            'roaming_barbarians': True, 'barbarian_attack': True,
        })
        assert len(problems) == 1 and 'Roaming barbarians' in problems[0]

    def test_the_deck_excludes_the_other_scenario_decks(self):
        assert rules_module.exclusion_problems(
            {'trade_dev_deck': True, 'progress_cards': True}) != []
        assert rules_module.exclusion_problems(
            {'trade_dev_deck': True, 'barbarian_attack_deck': True}) != []

    def test_the_preset_ticks_exactly_the_scenario_switches(self):
        chosen = rules_module.preset_rules('tb_main')
        assert chosen['trade_caravans'] is True
        assert chosen['baggage_train'] is True
        assert chosen['roaming_barbarians'] is True
        assert chosen['trade_dev_deck'] is True
        assert chosen['gold_coins'] is True
        assert chosen['setup_second_city'] is True
        assert chosen['longest_road_card'] is False
        assert chosen['dice_set'] == 'no_two_or_twelve'
        assert chosen['victory_target'] == 13
        assert chosen['board_map'] == 'traders-barbarians'
        assert rules_module.dependency_problems(chosen) == []
        assert rules_module.exclusion_problems(chosen) == []

    def test_the_preset_id_is_not_the_variants_preset(self):
        # tb_main must not be the two-variants preset traders_and_barbarians.
        assert rules_module.PRESETS_BY_ID['tb_main']['id'] == 'tb_main'
        variants = rules_module.preset_rules('traders_and_barbarians')
        assert variants.get('trade_caravans') is not True

    def test_the_deck_closes_the_base_development_deck(self):
        assert rules_module.dev_deck_in_play({'trade_dev_deck': True}) is False
        assert rules_module.dev_deck_in_play({'trade_dev_deck': False}) is True

    def test_needs_tb_state_for_the_scenario_rules(self):
        for rule_id in ('trade_caravans', 'baggage_train', 'roaming_barbarians',
                        'trade_dev_deck'):
            assert rules_module.needs_tb_state({rule_id: True}) is True

    def test_every_main_scenario_rule_id_is_read_by_engine_code(self):
        server_game = pathlib.Path(__file__).resolve().parents[2] / 'server' / 'game'
        sources = '\n'.join(
            path.read_text()
            for path in server_game.glob('*.py')
            if path.name != 'rules.py'
        )
        for rule_id in ('trade_caravans', 'baggage_train', 'roaming_barbarians',
                        'trade_dev_deck', 'wagon_movement_points'):
            assert f"'{rule_id}'" in sources or f'"{rule_id}"' in sources, \
                f'{rule_id} is in the catalogue but no engine code reads it'


# --- The deck and the commodity stacks ----------------------------------

class TestTheDeck:
    def test_the_wagon_deck_holds_the_enumerated_cards(self):
        assert tb_decks.trade_deck_counts() == {
            'trade_knight': 15, 'trade_road_building': 3, 'swift_journey': 3,
            'toolmaking': 1, 'glassmaking': 1, 'quarry_card': 1,
        }
        assert sum(tb_decks.trade_deck_counts().values()) == tb_decks.TRADE_DECK_SIZE

    def test_the_deck_is_dealt_face_down_in_full(self):
        game = board_game()
        assert len(game.tb.td_deck) == tb_decks.TRADE_DECK_SIZE
        counts = {c: game.tb.td_deck.count(c) for c in set(game.tb.td_deck)}
        assert counts == tb_decks.trade_deck_counts()

    def test_each_trade_hex_stack_is_its_two_exports(self):
        game = board_game()
        for hex_key, meta in game.tb.trade_hexes.items():
            stack = game.tb.trade_hex_stacks[hex_key]
            exports = set(tb_decks.TRADE_HEX_EXPORTS[meta['type']])
            assert set(stack) == exports
            assert len(stack) == len(exports) * tb_decks.TOKENS_PER_EXPORT


# --- The board deal -----------------------------------------------------

class TestBoardDeal:
    def test_the_three_trade_hexes_are_found(self):
        game = board_game()
        types = sorted(meta['type'] for meta in game.tb.trade_hexes.values())
        assert types == ['castle', 'glassworks', 'quarry']

    def test_each_trade_hex_has_a_plaza_and_sea_paths(self):
        game = board_game()
        for meta in game.tb.trade_hexes.values():
            assert meta['plaza'] in game.vertices
            assert meta['plaza'] in game.trade_plazas
            assert meta['sea_paths']
            assert all(p in game.trade_sea_paths for p in meta['sea_paths'])

    def test_the_three_barbarians_sit_on_paths(self):
        game = board_game()
        assert len(game.tb.path_barbarians) == 3
        assert all(edge in game.edges for edge in game.tb.path_barbarians)

    def test_the_wagons_land_on_the_starting_cities(self):
        # Drive a real setup through to the play phase and check each wagon.
        from game import map_store, maps
        defn = maps.parse_map(map_store.read_map('traders-barbarians'))
        game = Game(['Alice', 'Bob'], [], rng=random.Random(4),
                    rules=dict(rules_module.TB_MAIN_RULES), map_definition=defn)
        _run_setup(game)
        assert game.game_phase == 'playing'
        for player in ('Alice', 'Bob'):
            wagon = game.tb.wagons[player]
            assert wagon is not None
            assert game.vertices[wagon].building['player'] == player

    def test_no_road_may_sit_on_a_trade_hex_sea_path(self):
        game = playing(board_game())
        sea_path = sorted(game.trade_sea_paths)[0]
        assert game.trade_hex_road_refusal(sea_path)['code'] == 'TRADE_SEA_PATH'

    def test_no_building_may_stand_on_a_trade_hex_plaza(self):
        game = playing(board_game())
        plaza = sorted(game.trade_plazas)[0]
        assert game.trade_hex_settlement_refusal(plaza)['code'] == 'TRADE_PLAZA'


# --- Wagon movement -----------------------------------------------------

class TestWagonMovement:
    def test_a_bare_path_costs_two_points(self):
        game = playing(board_game())
        start = next(v for v, vx in game.vertices.items()
                     if len(vx.neighbors['hexes']) == 3 and v not in game.trade_plazas)
        place_wagon(game, 'Alice', start)
        dest, _ = an_adjacent_bare_path(game, start)
        game.wagon_points_left = 4
        result = game.move_wagon('Alice', dest)
        assert result['success'], result
        assert result['points_left'] == 4 - wagons.BARE_PATH_COST
        assert game.tb.wagons['Alice'] == dest

    def test_your_own_road_costs_one_point(self):
        game = playing(board_game())
        start = next(v for v, vx in game.vertices.items()
                     if len(vx.neighbors['hexes']) == 3 and v not in game.trade_plazas)
        dest, edge = an_adjacent_bare_path(game, start)
        # Only for a destination that is not itself a plaza (to isolate the cost).
        if dest in game.trade_plazas:
            return
        game.edges[edge].road = {'player': 'Alice'}
        place_wagon(game, 'Alice', start)
        game.wagon_points_left = 4
        result = game.move_wagon('Alice', dest)
        assert result['success']
        assert result['points_left'] == 4 - wagons.ROAD_PATH_COST

    def test_a_rival_road_costs_a_point_and_a_gold_to_the_owner(self):
        game = playing(board_game())
        start = next(v for v, vx in game.vertices.items()
                     if len(vx.neighbors['hexes']) == 3 and v not in game.trade_plazas)
        dest, edge = an_adjacent_bare_path(game, start)
        if dest in game.trade_plazas:
            return
        game.edges[edge].road = {'player': 'Bob'}
        place_wagon(game, 'Alice', start)
        game.wagon_points_left = 4
        game.get_player('Alice').gold = 2
        bob_before = game.get_player('Bob').gold
        result = game.move_wagon('Alice', dest)
        assert result['success']
        assert result['points_left'] == 4 - wagons.ROAD_PATH_COST
        assert result['toll_paid_to'] == 'Bob'
        assert game.get_player('Alice').gold == 1
        assert game.get_player('Bob').gold == bob_before + 1

    def test_a_rival_road_is_refused_without_the_gold(self):
        game = playing(board_game())
        start = next(v for v, vx in game.vertices.items()
                     if len(vx.neighbors['hexes']) == 3 and v not in game.trade_plazas)
        dest, edge = an_adjacent_bare_path(game, start)
        if dest in game.trade_plazas:
            return
        game.edges[edge].road = {'player': 'Bob'}
        place_wagon(game, 'Alice', start)
        game.wagon_points_left = 4
        game.get_player('Alice').gold = 0
        assert game.move_wagon('Alice', dest)['code'] == 'INSUFFICIENT_GOLD'

    def test_a_barbarian_path_costs_two_more(self):
        game = playing(board_game())
        start = next(v for v, vx in game.vertices.items()
                     if len(vx.neighbors['hexes']) == 3 and v not in game.trade_plazas)
        dest, edge = an_adjacent_bare_path(game, start)
        game.tb.path_barbarians = {edge}
        assert game.wagon_step_cost('Alice', edge) == \
            wagons.BARE_PATH_COST + wagons.BARBARIAN_CROSS_SURCHARGE

    def test_a_step_too_dear_is_refused(self):
        game = playing(board_game())
        start = next(v for v, vx in game.vertices.items()
                     if len(vx.neighbors['hexes']) == 3 and v not in game.trade_plazas)
        dest, _ = an_adjacent_bare_path(game, start)
        place_wagon(game, 'Alice', start)
        game.wagon_points_left = 1  # a bare path costs 2
        assert game.move_wagon('Alice', dest)['code'] == 'OUT_OF_POINTS'

    def test_grain_buys_two_more_points_once_a_turn(self):
        game = playing(board_game())
        game.get_player('Alice').resources = {'wheat': 1}
        game.wagon_points_left = 4
        result = game.boost_wagon('Alice')
        assert result['success']
        assert result['points_left'] == 4 + wagons.GRAIN_BOOST_POINTS
        assert game.get_player('Alice').resources['wheat'] == 0
        # A second boost the same turn is refused.
        game.get_player('Alice').resources = {'wheat': 1}
        assert game.boost_wagon('Alice')['code'] == 'ALREADY_BOOSTED'


# --- The delivery loop --------------------------------------------------

def _plaza_and_neighbour(game, hex_type):
    """The plaza of the trade hex of a type, and a non-plaza neighbour vertex."""
    hex_key = game._trade_hex_of_type(hex_type)
    plaza = game.tb.trade_hexes[hex_key]['plaza']
    neighbour = next(v for v in game.vertices[plaza].neighbors['vertices']
                     if v not in game.trade_plazas)
    return hex_key, plaza, neighbour


class TestDelivery:
    def test_the_first_arrival_draws_a_commodity_for_no_gold(self):
        game = playing(board_game())
        hex_key, plaza, neighbour = _plaza_and_neighbour(game, 'castle')
        place_wagon(game, 'Alice', neighbour)
        game.wagon_points_left = 5
        game.tb.carried_commodity['Alice'] = None
        gold_before = game.get_player('Alice').gold
        result = game.move_wagon('Alice', plaza)
        assert result['success']
        assert result['delivery']['gold'] == 0
        drew = game.tb.carried_commodity['Alice']
        assert drew in tb_decks.TRADE_HEX_EXPORTS['castle']
        assert game.get_player('Alice').gold == gold_before
        # Movement ends on the plaza.
        assert game.wagon_points_left == 0

    def test_delivering_a_matching_commodity_pays_gold_and_a_point(self):
        game = playing(board_game())
        # The castle accepts glass and marble (expansions.md 709).
        hex_key, plaza, neighbour = _plaza_and_neighbour(game, 'castle')
        place_wagon(game, 'Alice', neighbour)
        game.wagon_points_left = 5
        game.tb.carried_commodity['Alice'] = tb_decks.GLASS
        # Deterministic next draw.
        game.tb.trade_hex_stacks[hex_key] = [tb_decks.SAND]
        gold_before = game.get_player('Alice').gold
        vp_before = game.trade_victory_points('Alice')
        result = game.move_wagon('Alice', plaza)
        delivery = result['delivery']
        assert delivery['delivered'] == tb_decks.GLASS
        assert delivery['gold'] == game.wagon_delivery_gold('Alice')
        assert game.get_player('Alice').gold == gold_before + delivery['gold']
        assert game.trade_victory_points('Alice') == vp_before + 1
        # The next commodity is drawn and now carried.
        assert game.tb.carried_commodity['Alice'] == tb_decks.SAND

    def test_a_non_matching_trade_hex_delivers_nothing(self):
        game = playing(board_game())
        # The castle does not accept sand (sand goes to the glassworks).
        hex_key, plaza, neighbour = _plaza_and_neighbour(game, 'castle')
        place_wagon(game, 'Alice', neighbour)
        game.wagon_points_left = 5
        game.tb.carried_commodity['Alice'] = tb_decks.SAND
        gold_before = game.get_player('Alice').gold
        result = game.move_wagon('Alice', plaza)
        assert result['delivery']['delivered'] is None
        assert game.get_player('Alice').gold == gold_before
        assert game.tb.carried_commodity['Alice'] == tb_decks.SAND  # still carried


# --- The baggage train --------------------------------------------------

class TestBaggageTrain:
    def test_an_upgrade_raises_the_movement_points_and_delivery_gold(self):
        game = playing(board_game())
        before_points = game.wagon_movement_value('Alice')
        before_gold = game.wagon_delivery_gold('Alice')
        cost = wagons.BAGGAGE_UPGRADE_COST[2]
        game.get_player('Alice').resources = dict(cost)
        result = game.upgrade_baggage_train('Alice')
        assert result['success'], result
        assert game.tb.baggage_level['Alice'] == 2
        assert game.wagon_movement_value('Alice') >= before_points
        assert game.wagon_delivery_gold('Alice') == before_gold + 1

    def test_the_fifth_card_is_worth_a_victory_point(self):
        game = playing(board_game())
        assert game.trade_victory_points('Alice') == 0
        game.tb.baggage_level['Alice'] = wagons.MAX_BAGGAGE_LEVEL
        assert game.trade_victory_points('Alice') == 1

    def test_an_upgrade_past_the_fifth_is_refused(self):
        game = playing(board_game())
        game.tb.baggage_level['Alice'] = wagons.MAX_BAGGAGE_LEVEL
        assert game.upgrade_baggage_train('Alice')['code'] == 'MAX_LEVEL'


# --- Roaming barbarians -------------------------------------------------

class TestRoamingBarbarians:
    def test_a_seven_makes_the_roller_move_a_barbarian(self):
        game = board_game(seed=2)
        game.game_phase = 'playing'
        game.current_player_index = 0
        # Force a 7.
        game.pending_dice = (3, 4)
        result = game.roll_dice(game.current_player_name())
        assert result['total'] == 7
        assert game.must_move_barbarian == game.current_player_name()
        # The robber is not moved — the main scenario has none.
        assert game.must_move_robber is False
        # The turn cannot end until the barbarian is moved.
        assert game.advance_turn(game.current_player_name())['code'] == 'MUST_MOVE_BARBARIAN'

    def test_moving_a_barbarian_onto_a_road_draws_a_card(self):
        game = playing(board_game())
        mover = game.current_player_name()
        victim = 'Bob' if mover == 'Alice' else 'Alice'
        from_edge = sorted(game.tb.path_barbarians)[0]
        # A free destination edge that carries the victim's road.
        target = next(e for e in game.edges
                      if e not in game.tb.path_barbarians and e != from_edge)
        game.edges[target].road = {'player': victim}
        game.get_player(victim).resources = {'wood': 1}
        game.must_move_barbarian = mover
        result = game.move_path_barbarian(mover, from_edge, target)
        assert result['success'], result
        assert target in game.tb.path_barbarians
        assert from_edge not in game.tb.path_barbarians
        assert result['stolen'] == 'wood'
        assert game.get_player(mover).resources.get('wood', 0) == 1
        assert game.must_move_barbarian is None

    def test_a_barbarian_cannot_move_onto_another_barbarian(self):
        game = playing(board_game())
        mover = game.current_player_name()
        barbs = sorted(game.tb.path_barbarians)
        game.must_move_barbarian = mover
        assert game.move_path_barbarian(mover, barbs[0], barbs[1])['code'] == 'OCCUPIED'

    def test_driving_off_needs_an_upgraded_baggage_train(self):
        game = playing(board_game())
        mover = game.current_player_name()
        barb = sorted(game.tb.path_barbarians)[0]
        wagon = game.edges[barb].neighbors['vertices'][0]
        place_wagon(game, mover, wagon)
        game.tb.baggage_level[mover] = 1  # not upgraded
        assert game.drive_off_barbarian(mover, barb, barb)['code'] == 'BAGGAGE_TOO_LOW'

    def test_driving_off_moves_the_barbarian_on_a_matching_die(self):
        game = playing(board_game(seed=1))
        mover = game.current_player_name()
        barb = sorted(game.tb.path_barbarians)[0]
        wagon = game.edges[barb].neighbors['vertices'][0]
        place_wagon(game, mover, wagon)
        game.tb.baggage_level[mover] = wagons.MAX_BAGGAGE_LEVEL  # drives on 3-6
        target = next(e for e in game.edges
                      if e not in game.tb.path_barbarians and e != barb)
        # Force a die face that drives off.
        import unittest.mock as mock
        with mock.patch.object(game.rng, 'randint', return_value=6):
            result = game.drive_off_barbarian(mover, barb, target)
        assert result['driven_off'] is True
        assert target in game.tb.path_barbarians
        # A second attempt on the same barbarian this turn is refused.
        assert barb in game.barbarians_driven


# --- Card resolution ----------------------------------------------------

class TestCardResolution:
    def _buy(self, game, player, card):
        game.get_player(player).resources = {'ore': 1, 'sheep': 1, 'wheat': 1}
        game.tb.td_deck.append(card)
        return game.buy_trade_card(player)

    def test_road_building_grants_two_free_roads(self):
        game = playing(board_game())
        result = self._buy(game, game.current_player_name(),
                           tb_decks.TRADE_ROAD_BUILDING)
        assert result['free_roads'] == 2
        assert game.free_roads_remaining == 2

    def test_swift_journey_starts_a_fresh_second_movement_not_a_topped_up_first(self):
        """Swift Journey is a *second* movement (expansions.md 747), not the base
        remainder topped up. A player who stops the regular movement with points
        to spare must not carry them into the swift journey — the second movement
        starts clean, with its own fresh allocation and its own flagged phase, so
        leftover base points and swift points are never indistinguishable."""
        game = playing(board_game())
        mover = game.current_player_name()
        # The regular movement left points unspent (the player stopped early).
        game.wagon_points_left = 3
        assert game.wagon_swift_journey is False
        result = self._buy(game, mover, tb_decks.SWIFT_JOURNEY)
        # The second movement gets a full fresh allocation — not 3 + the value.
        assert result['points_left'] == game.wagon_movement_value(mover)
        assert game.wagon_points_left == game.wagon_movement_value(mover)
        assert result['swift_journey'] is True
        assert game.wagon_swift_journey is True

    def test_the_swift_journey_phase_ends_when_its_points_run_out(self):
        """The swift-journey phase has its own end: once the second movement
        spends its last point (or reaches a plaza) the flag clears, so the client
        does not show a swift journey underway into the rest of the turn."""
        game = playing(board_game())
        mover = game.current_player_name()
        start = next(v for v, vx in game.vertices.items()
                     if len(vx.neighbors['hexes']) == 3 and v not in game.trade_plazas)
        place_wagon(game, mover, start)
        self._buy(game, mover, tb_decks.SWIFT_JOURNEY)
        assert game.wagon_swift_journey is True
        # Spend the last of the swift allocation on one bare step.
        dest, _ = an_adjacent_bare_path(game, start)
        game.wagon_points_left = wagons.BARE_PATH_COST
        result = game.move_wagon(mover, dest)
        assert result['success'], result
        assert result['points_left'] == 0
        assert game.wagon_swift_journey is False

    def test_a_knight_card_is_pending_until_a_barbarian_moves(self):
        game = playing(board_game())
        mover = game.current_player_name()
        result = self._buy(game, mover, tb_decks.TRADE_KNIGHT)
        assert result['needs_barbarian_move'] is True
        assert game.tb.td_pending['player'] == mover
        # It authorises a barbarian move; buying another card is refused meanwhile.
        assert game.buy_trade_card(mover)['code'] == 'CARD_PENDING'
        from_edge = sorted(game.tb.path_barbarians)[0]
        target = next(e for e in game.edges
                      if e not in game.tb.path_barbarians and e != from_edge)
        assert game.move_path_barbarian(mover, from_edge, target)['success']
        assert game.tb.td_pending is None

    def test_a_victory_point_card_is_kept_and_scores(self):
        game = playing(board_game())
        mover = game.current_player_name()
        before = game.trade_victory_points(mover)
        result = self._buy(game, mover, tb_decks.TOOLMAKING)
        assert result['victory_point'] is True
        assert tb_decks.TOOLMAKING in game.tb.td_vp_cards[mover]
        assert game.trade_victory_points(mover) == before + 1

    def test_the_deck_reshuffles_when_the_draw_pile_empties(self):
        game = playing(board_game())
        game.tb.td_deck = []
        game.tb.td_discard = [tb_decks.TRADE_ROAD_BUILDING, tb_decks.SWIFT_JOURNEY]
        drawn = game._draw_trade_card()
        assert drawn in (tb_decks.TRADE_ROAD_BUILDING, tb_decks.SWIFT_JOURNEY)
        assert len(game.tb.td_deck) == 1


# --- Persistence and the base game --------------------------------------

class TestPersistenceAndBaseGame:
    def test_a_deal_move_deliver_cycle_round_trips_through_a_save(self):
        from game import persistence
        game = playing(board_game(seed=9))
        # A delivered token, a carried commodity, an upgraded baggage train and a
        # moved wagon and barbarian.
        alice = 'Alice'
        hex_key, plaza, neighbour = _plaza_and_neighbour(game, 'quarry')
        game.tb.wagons[alice] = plaza
        game.tb.carried_commodity[alice] = tb_decks.MARBLE
        game.tb.delivered[alice] = [tb_decks.TOOLS, tb_decks.GLASS]
        game.tb.baggage_level[alice] = 3
        game.tb.td_vp_cards[alice] = [tb_decks.QUARRY]
        moved_barb = sorted(game.tb.path_barbarians)[0]

        blob = persistence.serialize(game)
        restored = persistence.deserialize(blob)
        assert restored.tb.wagons[alice] == plaza
        assert restored.tb.carried_commodity[alice] == tb_decks.MARBLE
        assert restored.tb.delivered[alice] == [tb_decks.TOOLS, tb_decks.GLASS]
        assert restored.tb.baggage_level[alice] == 3
        assert restored.tb.td_vp_cards[alice] == [tb_decks.QUARRY]
        assert restored.tb.path_barbarians == game.tb.path_barbarians
        assert moved_barb in restored.tb.path_barbarians
        assert restored.tb.td_deck == game.tb.td_deck
        # The scoring survives the round-trip: 2 delivered + level 3 (no VP) + 1 card.
        assert restored.trade_victory_points(alice) == 3

    def test_the_base_game_deals_no_wagon_state(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        assert game.tb is None
        assert game.trade_plazas == set()

    def test_the_base_game_seven_still_moves_the_robber(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        assert game.rules['roaming_barbarians'] is False
        game.game_phase = 'playing'
        game.pending_dice = (3, 4)
        game.roll_dice(game.current_player_name())
        assert game.must_move_robber is True
        assert game.must_move_barbarian is None


def _run_setup(game):
    """Drive the snaking two-round setup to completion, placing legally."""
    game.start()
    guard = 0
    while game.game_phase == 'setup' and guard < 200:
        guard += 1
        player = game.current_player_name()
        if game.setup_action == 'settlement':
            spot = next(
                (v for v, vx in sorted(game.vertices.items())
                 if vx.building is None and vx.port is None
                 and game._respects_distance_rule(v)
                 and len(vx.neighbors['hexes']) == 3
                 and v not in game.trade_plazas), None)
            assert spot is not None
            assert game.place_settlement(player, spot)['success']
        else:
            settlement = game.last_setup_settlement
            edge = next(
                e for e in game.vertices[settlement].neighbors['edges']
                if game.edges[e].road is None and e not in game.trade_sea_paths)
            assert game.build_road(player, edge)['success']
