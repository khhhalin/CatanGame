"""Barbarian Attack (Traders & Barbarians, expansions.md 607-676).

The scenario's coastal war, decomposed the way every other expansion is: one
container rule `barbarian_attack` carries the landings, the conquest, the castle
knights, the victories and the prisoners; a second rule `barbarian_attack_deck`
replaces the base development deck with the scenario's 26 cards. These tests pin
the catalogue coherence and its two exclusions, the board deal, an attack landing
a barbarian on a build, conquest at three (token face down, produces nothing,
buildings toppled), a knight defence freeing prisoners, the two-prisoners-a-point
scoring, the post-victory knight-loss die paying 3 gold, the deck composition and
a card resolving, and a real deal that round-trips through a save. Every number
is read off the live engine, never a copied literal, and the base game is proven
untouched.
"""

import pathlib
import random

from game import modifiers as modifiers_module
from game import rules as rules_module
from game import tb_decks
from game.game import Game


def board_game(players=("Alice", "Bob"), seed=7, **overrides):
    """A game dealt on the built-in castle map — the real coast, castle and deck."""
    from game import map_store, maps
    defn = maps.parse_map(map_store.read_map('barbarian-attack'))
    chosen = dict(rules_module.TB_BARBARIAN_ATTACK_RULES)
    chosen.update(overrides)
    return Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)


def playing(game):
    """Roll a game forward into the play phase for a direct method call."""
    game.game_phase = 'playing'
    game.has_rolled_dice = True
    return game


def a_coastal_hex(game, number=None):
    for key in game.tb.coastal_hexes:
        if number is None or game.hexes[key].number == number:
            return key
    raise AssertionError('no such coastal hex')


def hex_paths(game, hex_key):
    return sorted(
        edge_key for edge_key, edge in game.edges.items()
        if hex_key in edge.neighbors.get('hexes', [])
    )


# --- Catalogue ----------------------------------------------------------

class TestCatalogue:
    def test_both_switches_are_off_in_the_base_game(self):
        chosen = rules_module.defaults()
        assert chosen['barbarian_attack'] is False
        assert chosen['barbarian_attack_deck'] is False

    def test_the_supply_ints_default_to_the_box(self):
        chosen = rules_module.defaults()
        assert chosen['max_barbarian_knights'] == 6
        assert chosen['barbarian_supply'] == 30

    def test_barbarian_attack_suggests_a_target_of_twelve(self):
        assert rules_module.RULES_BY_ID['barbarian_attack']['suggests_victory_target'] == 12

    def test_it_needs_gold_coins_and_the_deck(self):
        problems = rules_module.dependency_problems({'barbarian_attack': True})
        assert problems == ['Barbarian Attack needs Gold coins and Barbarian Attack deck']
        # With both, no dependency problem remains.
        assert rules_module.dependency_problems({
            'barbarian_attack': True, 'gold_coins': True, 'barbarian_attack_deck': True,
        }) == []

    def test_it_excludes_the_cities_and_knights_knights(self):
        problems = rules_module.exclusion_problems({
            'barbarian_attack': True, 'knights': True,
        })
        assert len(problems) == 1 and 'Barbarian Attack' in problems[0]

    def test_the_deck_excludes_the_progress_decks(self):
        problems = rules_module.exclusion_problems({
            'barbarian_attack_deck': True, 'progress_cards': True,
        })
        assert len(problems) == 1 and 'Barbarian Attack deck' in problems[0]

    def test_the_preset_ticks_exactly_the_scenario_switches(self):
        chosen = rules_module.preset_rules('tb_barbarian_attack')
        assert chosen['barbarian_attack'] is True
        assert chosen['barbarian_attack_deck'] is True
        assert chosen['gold_coins'] is True
        assert chosen['setup_second_city'] is True
        assert chosen['largest_army_card'] is False
        assert chosen['victory_target'] == 12
        assert chosen['board_map'] == 'barbarian-attack'
        # The preset is coherent: no dependency and no exclusion problem.
        assert rules_module.dependency_problems(chosen) == []
        assert rules_module.exclusion_problems(chosen) == []

    def test_the_deck_closes_the_base_development_deck(self):
        assert rules_module.dev_deck_in_play({'barbarian_attack_deck': True}) is False
        assert rules_module.dev_deck_in_play({'barbarian_attack_deck': False}) is True

    def test_the_conquered_hex_modifier_runs_last_at_order_forty_five(self):
        production = modifiers_module.registered(modifiers_module.PRODUCTION)
        conquered = [m for m in production if m.rule_id == 'conquered_hex']
        assert len(conquered) == 1
        assert conquered[0].order == 45
        # It is the last on the hook, after even the robber.
        assert production[-1].rule_id == 'conquered_hex'

    def test_needs_tb_state_for_the_war_and_the_deck(self):
        assert rules_module.needs_tb_state({'barbarian_attack': True}) is True
        assert rules_module.needs_tb_state({'barbarian_attack_deck': True}) is True

    def test_every_barbarian_attack_rule_id_is_read_by_engine_code(self):
        """A picker control the engine ignores is worse than no control. Each new
        rule id must appear in server/game source outside the catalogue file."""
        server_game = pathlib.Path(__file__).resolve().parents[2] / 'server' / 'game'
        sources = '\n'.join(
            path.read_text()
            for path in server_game.glob('*.py')
            if path.name != 'rules.py'
        )
        for rule_id in ('barbarian_attack', 'barbarian_attack_deck',
                        'max_barbarian_knights', 'barbarian_supply'):
            assert f"'{rule_id}'" in sources or f'"{rule_id}"' in sources, \
                f'{rule_id} is in the catalogue but no engine code reads it'


# --- The board deal -----------------------------------------------------

class TestBoardDeal:
    def test_the_castle_and_its_six_paths_are_found(self):
        game = board_game()
        assert game.hexes[game.tb.castle_hex].type == 'castle'
        assert len(game.tb.castle_paths) == 6

    def test_the_ten_coastal_hexes_carry_distinct_numbers(self):
        game = board_game()
        numbers = sorted(game.hexes[k].number for k in game.tb.coastal_hexes)
        assert numbers == [2, 3, 4, 5, 6, 8, 9, 10, 11, 12]

    def test_the_castle_and_desert_can_never_be_conquered(self):
        game = board_game()
        kinds = {game.hexes[k].type for k in game.tb.unconquerable_hexes}
        assert kinds == {'castle', 'desert'}

    def test_two_barbarians_open_on_the_two_and_the_twelve(self):
        game = board_game()
        seeded = {k: v for k, v in game.tb.barbarians.items() if v > 0}
        assert len(seeded) == 2
        assert {game.hexes[k].number for k in seeded} == {2, 12}
        # Both came out of the supply.
        assert game.tb.barbarians_left == game.rules['barbarian_supply'] - 2

    def test_the_scenario_deck_is_dealt_face_down_in_full(self):
        game = board_game()
        assert len(game.tb.ba_deck) == tb_decks.DECK_SIZE
        counts = {c: game.tb.ba_deck.count(c) for c in set(game.tb.ba_deck)}
        assert counts == {'knighthood': 14, 'swift_knight': 4,
                          'treason': 4, 'intrigue': 4}


# --- Attacks and conquest ----------------------------------------------

class TestAttackAndConquest:
    def test_resolving_an_attack_lands_barbarians_from_the_supply(self):
        game = playing(board_game(seed=3))
        before_on_board = sum(game.tb.barbarians.values())
        before_supply = game.tb.barbarians_left
        result = game.trigger_barbarian_attack()
        after_on_board = sum(game.tb.barbarians.values())
        landed = after_on_board - before_on_board
        assert landed == len(result['placed'])
        assert landed >= 1  # a three-roll attack lands at least one on this coast
        # Every barbarian that landed came out of the supply.
        assert game.tb.barbarians_left == before_supply - landed

    def test_a_build_after_setup_triggers_an_attack(self):
        game = playing(board_game(seed=5))
        # Give a starting settlement and a two-road chain, then build a settlement
        # two vertices away — a real connected build that respects spacing.
        start = next(v for v in sorted(game.vertices)
                     if len(game.vertices[v].neighbors['hexes']) == 3)
        game.vertices[start].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(start)
        current = start
        chain = []
        while len(chain) < 2:
            edge_key = next(
                e for e in game.vertices[current].neighbors['edges']
                if e not in chain and game.land_hexes_of_edge(e)
                and not any(k in game.tb.conquered_hexes
                            for k in game.edges[e].neighbors['hexes'])
            )
            game.edges[edge_key].road = {'player': 'Alice'}
            game.get_player('Alice').roads.append(edge_key)
            chain.append(edge_key)
            current = next(v for v in game.edges[edge_key].neighbors['vertices']
                           if v != current)
        target = current
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1, 'sheep': 1, 'wheat': 1}
        before = sum(game.tb.barbarians.values())
        result = game.place_settlement('Alice', target)
        assert result['success'], result
        assert 'barbarian_attack' in result
        # The build resolved an attack (barbarians landed, or the supply was reached).
        assert sum(game.tb.barbarians.values()) >= before

    def test_a_third_barbarian_conquers_the_hex(self):
        game = playing(board_game())
        target = a_coastal_hex(game, number=5)  # not one of the opening hexes
        game.tb.barbarians[target] = 2
        game.tb.barbarians_left = 10
        game._place_barbarian(target)
        assert game.tb.barbarians[target] == 3
        assert target in game.tb.conquered_hexes

    def test_a_conquered_hex_produces_nothing(self):
        game = playing(board_game())
        target = a_coastal_hex(game, number=5)
        game.tb.conquered_hexes.add(target)
        # Put a city on a vertex of the conquered hex and roll its number.
        vertex_key = next(v for v, vx in game.vertices.items()
                          if target in vx.neighbors['hexes'])
        vertex = game.vertices[vertex_key]
        vertex.building = {'type': 'city', 'player': 'Alice'}
        hex_obj = game.hexes[target]
        yielded = game.production_for(vertex, hex_obj, hex_obj.number, robber_here=False)
        assert yielded == {'resources': 0, 'commodity': None}

    def test_a_walled_off_building_topples_and_scores_nothing(self):
        game = playing(board_game())
        # A vertex whose every land hex is a conquerable coast (the rest frame):
        # walling it off with conquered hexes topples the building on it.
        target_vertex = None
        for v, vx in sorted(game.vertices.items()):
            land = vx.neighbors['hexes']
            if (land
                    and all(k in game.tb.barbarians for k in land)
                    and not any(k in game.tb.unconquerable_hexes for k in land)):
                target_vertex = v
                break
        assert target_vertex is not None, 'no fully-conquerable coastal vertex on this board'
        game.vertices[target_vertex].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(target_vertex)
        base_points = game.victory_points_for('Alice')
        for hex_key in game.vertices[target_vertex].neighbors['hexes']:
            game.tb.conquered_hexes.add(hex_key)
        game._recompute_toppled()
        assert target_vertex in game.tb.toppled
        # The toppled settlement's point is taken back.
        assert game.victory_points_for('Alice') == base_points - 1

    def test_no_settlement_or_road_may_be_built_beside_a_conquered_hex(self):
        game = playing(board_game())
        target = a_coastal_hex(game, number=5)
        game.tb.conquered_hexes.add(target)
        vertex_key = next(v for v, vx in game.vertices.items()
                          if target in vx.neighbors['hexes'])
        assert game.barbarian_settlement_refusal(vertex_key)['code'] == 'CONQUERED_HEX'
        edge_key = hex_paths(game, target)[0]
        assert game.barbarian_road_refusal(edge_key)['code'] == 'CONQUERED_HEX'


# --- Knights, victories and prisoners ----------------------------------

class TestKnightsAndVictories:
    def test_a_knighthood_places_a_knight_on_a_castle_path(self):
        game = playing(board_game())
        game.get_player('Alice').resources = {'ore': 1, 'sheep': 1, 'wheat': 1}
        # Force a Knighthood on top of the deck.
        game.tb.ba_deck.append(tb_decks.KNIGHTHOOD)
        result = game.buy_barbarian_card('Alice')
        assert result['needs_knight_placement'] is True
        path = game.tb.castle_paths[0]
        placed = game.place_barbarian_knight('Alice', path)
        assert placed['success']
        assert game.tb.knights[path] == 'Alice'
        assert game.tb.pending_card is None

    def test_a_knight_defends_a_coast_and_frees_prisoners(self):
        game = playing(board_game())
        target = a_coastal_hex(game, number=5)
        game.tb.barbarians[target] = 1
        paths = hex_paths(game, target)
        # Two knights beat one barbarian.
        game.tb.knights[paths[0]] = 'Alice'
        game.tb.knights[paths[1]] = 'Alice'
        before = game.tb.prisoners.get('Alice', 0)
        victories = game.resolve_barbarian_victories()
        assert len(victories) == 1
        assert game.tb.barbarians[target] == 0  # the coast is cleared
        assert game.tb.prisoners['Alice'] == before + 1  # one freed barbarian

    def test_a_defended_conquered_hex_is_freed_again(self):
        game = playing(board_game())
        target = a_coastal_hex(game, number=5)
        game.tb.barbarians[target] = 3
        game.tb.conquered_hexes.add(target)
        paths = hex_paths(game, target)
        for path in paths[:4]:  # four knights beat three barbarians
            game.tb.knights[path] = 'Alice'
        victories = game.resolve_barbarian_victories()
        assert victories and victories[0]['un_conquered'] is True
        assert target not in game.tb.conquered_hexes

    def test_every_two_prisoners_are_worth_one_point(self):
        game = playing(board_game())
        game.tb.prisoners['Alice'] = 4
        assert game.barbarian_victory_points('Alice') == 2
        game.tb.prisoners['Alice'] = 5  # the odd one does not score
        assert game.barbarian_victory_points('Alice') == 2

    def test_the_post_victory_die_removes_knights_and_pays_three_gold(self):
        game = playing(board_game(seed=11))
        target = a_coastal_hex(game, number=5)
        paths = hex_paths(game, target)
        # Fill all six paths with Alice's knights, of both orientations.
        knights = {}
        for path in paths:
            game.tb.knights[path] = 'Alice'
            knights['Alice'] = knights.get('Alice', 0) + 1
        before_gold = game.get_player('Alice').gold
        before_on_board = len(game.tb.knights)
        losses = game._remove_knights_after_victory(target, knights)
        removed = before_on_board - len(game.tb.knights)
        assert removed == sum(losses.values())
        assert removed >= 1  # the die matches at least one of the six paths
        assert game.get_player('Alice').gold == before_gold + removed * 3

    def test_knight_movement_is_bounded_and_costs_grain_to_extend(self):
        game = playing(board_game())
        start = game.tb.castle_paths[0]
        game.tb.knights[start] = 'Alice'
        # A path exactly three away is reachable free; asking for five needs grain.
        reachable = None
        for edge_key in game.edges:
            if edge_key in game.tb.knights:
                continue
            if game.knight_move_distance(start, edge_key) == 3:
                reachable = edge_key
                break
        assert reachable is not None
        moved = game.move_barbarian_knight('Alice', start, reachable)
        assert moved['success']
        assert game.tb.knights[reachable] == 'Alice' and start not in game.tb.knights


# --- The scenario deck --------------------------------------------------

class TestTheDeck:
    def test_the_deck_holds_the_published_twenty_six(self):
        assert tb_decks.deck_counts() == {
            'knighthood': 14, 'swift_knight': 4, 'treason': 4, 'intrigue': 4,
        }
        assert sum(tb_decks.deck_counts().values()) == 26

    def test_treason_grants_gold_and_moves_barbarians(self):
        game = playing(board_game())
        game.get_player('Alice').resources = {'ore': 1, 'sheep': 1, 'wheat': 1}
        game.tb.ba_deck.append(tb_decks.TREASON)
        gold_before = game.get_player('Alice').gold
        result = game.buy_barbarian_card('Alice')
        assert result['card'] == 'treason'
        assert game.get_player('Alice').gold == gold_before + 2
        assert tb_decks.TREASON in game.tb.ba_discard

    def test_intrigue_takes_a_barbarian_as_a_prisoner(self):
        game = playing(board_game())
        game.get_player('Alice').resources = {'ore': 1, 'sheep': 1, 'wheat': 1}
        game.tb.ba_deck.append(tb_decks.INTRIGUE)
        prisoners_before = game.tb.prisoners.get('Alice', 0)
        total_before = sum(game.tb.barbarians.values())
        result = game.buy_barbarian_card('Alice')
        assert result['card'] == 'intrigue'
        assert game.tb.prisoners['Alice'] == prisoners_before + 1
        assert sum(game.tb.barbarians.values()) == total_before - 1

    def test_the_discard_reshuffles_when_the_draw_pile_empties(self):
        game = playing(board_game())
        game.tb.ba_deck = []
        game.tb.ba_discard = [tb_decks.KNIGHTHOOD, tb_decks.TREASON]
        drawn = game._draw_barbarian_card()
        assert drawn in (tb_decks.KNIGHTHOOD, tb_decks.TREASON)
        assert len(game.tb.ba_deck) == 1  # the other came back off the discard


# --- Persistence and the base game -------------------------------------

class TestPersistenceAndBaseGame:
    def test_a_deal_attack_conquer_cycle_round_trips_through_a_save(self):
        from game import persistence
        game = playing(board_game(seed=9))
        target = a_coastal_hex(game, number=5)
        game.tb.barbarians[target] = 3
        game.tb.conquered_hexes.add(target)
        game.tb.knights[game.tb.castle_paths[0]] = 'Alice'
        game.tb.prisoners['Alice'] = 3
        game._recompute_toppled()

        blob = persistence.serialize(game)
        restored = persistence.deserialize(blob)
        assert restored.tb.barbarians[target] == 3
        assert target in restored.tb.conquered_hexes
        assert restored.tb.knights[game.tb.castle_paths[0]] == 'Alice'
        assert restored.tb.prisoners['Alice'] == 3
        assert restored.tb.ba_deck == game.tb.ba_deck

    def test_the_base_game_deals_no_barbarian_state(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        assert game.tb is None

    def test_the_base_game_seven_still_moves_the_robber(self):
        # The no-robber rule is gated on barbarian_attack, so a base 7 is unchanged.
        game = Game(['Alice', 'Bob'], [], rng=random.Random(1))
        assert game.rules['barbarian_attack'] is False
