"""The Rivers of Catan (Traders & Barbarians, expansions.md 527-570).

Decomposed into individual switches like every other expansion: the shared
`gold_coins` currency, `river_gold`, `bridges`, and the two scoring tiles
`wealthiest_settler` / `poor_settler`. These tests pin the catalogue coherence,
the coin economy (buy/sell/immunity), the river coin grants, bridge building and
the Longest-Road counting, and the two victory-point tiles.

Everything is asserted against the live engine — a game is dealt, a coin is
earned or spent, a tile moves — never against a copied literal.
"""

import random

from game import rules as rules_module
from game.game import Game


def make_game(rules=None, players=("Alice", "Bob")):
    return Game(list(players), [], rng=random.Random(4242), rules=rules)


def rivers_rules(**overrides):
    """The Rivers preset, coerced, with any overrides applied."""
    chosen = dict(rules_module.TB_RIVERS_RULES)
    # No board_map so tests deal the default board; they set river hexes and
    # bridge sites directly rather than lean on a dealt map.
    chosen.pop("board_map", None)
    chosen.update(overrides)
    return rules_module.coerce(chosen)


def playing_game(**overrides):
    """A Rivers game rolled forward into the play phase, ready to build."""
    game = make_game(rules=rivers_rules(**overrides))
    game.game_phase = 'playing'
    game.has_rolled_dice = True
    return game


def an_inland_vertex(game):
    """A vertex that borders three land hexes — safe to build on and to paint a
    river hex beside without falling off the coast."""
    for key, vertex in sorted(game.vertices.items()):
        if len(vertex.neighbors['hexes']) == 3:
            return key
    raise AssertionError('no inland vertex on this board')


def paint_river_beside(game, vertex_key):
    """Turn one of a vertex's neighbouring hexes into a river hex, and return it."""
    hex_key = game.vertices[vertex_key].neighbors['hexes'][0]
    game.hexes[hex_key].type = 'river'
    return hex_key


def walk_path(game, start_vertex, length):
    """A simple (non-repeating) chain of `length` edge keys from a vertex,
    walking the board's own graph so the roads are genuinely connected."""
    edges, seen_vertices, current = [], {start_vertex}, start_vertex
    while len(edges) < length:
        step = None
        for edge_key in game.vertices[current].neighbors['edges']:
            if edge_key in edges:
                continue
            others = [v for v in game.edges[edge_key].neighbors['vertices']
                      if v != current and v not in seen_vertices]
            if others:
                step = (edge_key, others[0])
                break
        if step is None:
            raise AssertionError('cannot extend the path on this board')
        edges.append(step[0])
        seen_vertices.add(step[1])
        current = step[1]
    return edges


class TestCatalogue:
    def test_the_five_rivers_rules_are_off_in_the_base_game(self):
        chosen = rules_module.defaults()
        for rule_id in ("gold_coins", "river_gold", "bridges",
                        "wealthiest_settler", "poor_settler"):
            assert chosen[rule_id] is False, rule_id

    def test_max_bridges_defaults_to_three(self):
        assert rules_module.defaults()["max_bridges"] == 3

    def test_the_river_rules_need_the_coin_currency(self):
        problems = rules_module.dependency_problems({
            "river_gold": True,
            "wealthiest_settler": True,
            "poor_settler": True,
        })
        assert len(problems) == 3
        assert all("Gold coins" in p for p in problems)

    def test_bridges_stand_alone_without_the_coin_currency(self):
        # Bridges depend on the river map's crossing sites, not on gold_coins:
        # a table could build them for the Longest Road with no coin economy.
        assert rules_module.dependency_problems({"bridges": True}) == []

    def test_gold_coins_excludes_ep_gold(self):
        problems = rules_module.exclusion_problems({"gold": True, "gold_coins": True})
        assert len(problems) == 1

    def test_gold_coins_alone_is_fine(self):
        assert rules_module.exclusion_problems({"gold_coins": True}) == []
        assert rules_module.exclusion_problems({"gold": True}) == []

    def test_the_rivers_preset_is_coherent(self):
        chosen = rules_module.preset_rules("tb_rivers")
        assert rules_module.dependency_problems(chosen) == []
        assert rules_module.exclusion_problems(chosen) == []

    def test_the_rivers_preset_ticks_its_rules_and_suggests_ten(self):
        chosen = rules_module.preset_rules("tb_rivers")
        for rule_id in ("gold_coins", "river_gold", "bridges",
                        "wealthiest_settler", "poor_settler"):
            assert chosen[rule_id] is True, rule_id
        assert chosen["victory_target"] == 10
        assert chosen["board_map"] == "rivers"

    def test_a_rivers_game_builds_no_fish_container(self):
        # Rivers needs no TB fish state: coins live on the player and bridge
        # sites on the board, so `tb` stays None exactly as in a base game.
        assert make_game(rules=rivers_rules()).tb is None


class TestCoinEconomy:
    def test_two_gold_buys_one_resource_twice_a_turn(self):
        game = playing_game()
        alice = game.get_player('Alice')
        alice.gold = 4
        assert game.buy_resource_with_gold('Alice', 'wood')['success']
        assert alice.gold == 2 and alice.resources.get('wood') == 1
        assert game.buy_resource_with_gold('Alice', 'brick')['success']
        assert alice.gold == 0
        # Third buy in the same turn is refused by the per-turn cap, not the purse.
        alice.gold = 4
        third = game.buy_resource_with_gold('Alice', 'ore')
        assert not third['success'] and third['code'] == 'GOLD_LIMIT'

    def test_the_buy_needs_two_gold(self):
        game = playing_game()
        game.get_player('Alice').gold = 1
        result = game.buy_resource_with_gold('Alice', 'wood')
        assert not result['success'] and result['code'] == 'INSUFFICIENT_GOLD'

    def test_four_identical_resources_buy_one_coin(self):
        game = playing_game()
        alice = game.get_player('Alice')
        alice.resources = {'wood': 4}
        result = game.sell_resources_for_gold_coins('Alice', 'wood')
        assert result['success'] and result['rate'] == 4
        assert alice.gold == 1 and alice.resources['wood'] == 0

    def test_three_short_of_four_is_refused(self):
        game = playing_game()
        game.get_player('Alice').resources = {'wood': 3}
        result = game.sell_resources_for_gold_coins('Alice', 'wood')
        assert not result['success'] and result['code'] == 'INSUFFICIENT_RESOURCES'

    def test_a_matching_three_to_one_harbour_makes_it_three(self):
        game = playing_game()
        vertex = an_inland_vertex(game)
        game.vertices[vertex].port = {'type': 'generic'}
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(vertex)
        assert game.coin_sell_rate('Alice') == 3
        game.get_player('Alice').resources = {'ore': 3}
        result = game.sell_resources_for_gold_coins('Alice', 'ore')
        assert result['success'] and result['rate'] == 3

    def test_a_two_to_one_harbour_never_cheapens_a_coin(self):
        game = playing_game()
        vertex = an_inland_vertex(game)
        # A resource (2:1) harbour for wood — it must not lower the coin rate.
        game.vertices[vertex].port = {'type': 'resource', 'resource': 'wood'}
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(vertex)
        assert game.coin_sell_rate('Alice') == 4

    def test_coins_survive_the_robber(self):
        game = playing_game()
        alice = game.get_player('Alice')
        alice.gold = 5
        alice.resources = {'wood': 1}
        game.steal_resource('Alice', 'Bob')
        # The one resource card can be taken; the gold cannot.
        assert alice.gold == 5

    def test_gold_is_not_a_card_a_monopoly_could_name(self):
        # Monopoly declares a card type and sweeps every hand of it. Gold lives
        # in its own field, not among the card types, so it can never be named.
        from game import validation
        assert 'gold' not in validation.CARD_TYPES

    def test_the_coin_economy_is_off_without_the_rule(self):
        game = playing_game(gold_coins=False, river_gold=False,
                            wealthiest_settler=False, poor_settler=False)
        game.get_player('Alice').resources = {'wood': 4}
        result = game.sell_resources_for_gold_coins('Alice', 'wood')
        assert not result['success'] and result['code'] == 'RULE_OFF'


class TestRiverGold:
    def test_a_settlement_beside_a_river_pays_a_coin(self):
        game = playing_game()
        vertex = an_inland_vertex(game)
        paint_river_beside(game, vertex)
        assert game.grant_river_settlement_gold('Alice', vertex) == 1
        assert game.get_player('Alice').gold == 1

    def test_a_settlement_away_from_a_river_pays_nothing(self):
        game = playing_game()
        vertex = an_inland_vertex(game)  # no river painted beside it
        assert game.grant_river_settlement_gold('Alice', vertex) == 0
        assert game.get_player('Alice').gold == 0

    def test_a_road_beside_a_river_pays_a_coin(self):
        game = playing_game()
        edge_key = next(iter(game.edges))
        river_hex = game.edges[edge_key].neighbors['hexes'][0]
        game.hexes[river_hex].type = 'river'
        assert game.grant_river_road_gold('Alice', edge_key) == 1
        assert game.get_player('Alice').gold == 1

    def test_no_river_coin_without_the_rule(self):
        game = playing_game(river_gold=False)
        vertex = an_inland_vertex(game)
        paint_river_beside(game, vertex)
        assert game.grant_river_settlement_gold('Alice', vertex) == 0

    def test_setup_placement_pays_the_river_coin(self):
        # The grant fires during set-up, driven through the real placement path.
        game = make_game(rules=rivers_rules())
        assert game.game_phase == 'setup'
        placer = game.current_player_name()
        vertex = an_inland_vertex(game)
        paint_river_beside(game, vertex)
        result = game.place_settlement(placer, vertex)
        assert result['success'] and result['river_gold'] == 1
        assert game.get_player(placer).gold == 1

    def test_a_city_upgrade_pays_no_river_coin(self):
        game = playing_game()
        vertex = an_inland_vertex(game)
        paint_river_beside(game, vertex)
        alice = game.get_player('Alice')
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}
        alice.settlements.append(vertex)
        alice.gold = 0
        alice.resources = {'wheat': 2, 'ore': 3}
        result = game.upgrade_city('Alice', vertex)
        assert result['success']
        assert alice.gold == 0  # no coin for the upgrade


class TestBridges:
    def _connected_site(self, game, player='Alice'):
        """Place a settlement for a player and return an adjacent bridge site."""
        vertex = an_inland_vertex(game)
        edge_key = game.vertices[vertex].neighbors['edges'][0]
        game.vertices[vertex].building = {'type': 'settlement', 'player': player}
        game.get_player(player).settlements.append(vertex)
        game.bridge_sites = {edge_key}
        return edge_key

    def test_a_bridge_costs_two_brick_one_lumber_and_pays_three_gold(self):
        game = playing_game()
        edge_key = self._connected_site(game)
        alice = game.get_player('Alice')
        alice.resources = {'brick': 2, 'wood': 1}
        result = game.build_bridge('Alice', edge_key)
        assert result['success']
        assert alice.resources == {'brick': 0, 'wood': 0}
        assert alice.gold == 3
        assert game.edges[edge_key].road == {'player': 'Alice', 'kind': 'bridge'}

    def test_a_bridge_only_on_a_site(self):
        game = playing_game()
        self._connected_site(game)
        other = next(e for e in game.edges if e not in game.bridge_sites)
        game.get_player('Alice').resources = {'brick': 2, 'wood': 1}
        result = game.build_bridge('Alice', other)
        assert not result['success'] and result['code'] == 'INVALID_PLACEMENT'

    def test_a_bridge_must_connect_to_your_network(self):
        game = playing_game()
        # A lone bridge site with no building or road of Alice's touching it.
        edge_key = next(iter(game.edges))
        game.bridge_sites = {edge_key}
        game.get_player('Alice').resources = {'brick': 2, 'wood': 1}
        result = game.build_bridge('Alice', edge_key)
        assert not result['success'] and result['code'] == 'INVALID_PLACEMENT'

    def test_a_normal_road_may_never_sit_on_a_bridge_site(self):
        game = playing_game()
        edge_key = self._connected_site(game)
        game.free_roads_remaining = 1  # skip the cost; the guard is the point
        result = game.build_road('Alice', edge_key)
        assert not result['success'] and result['code'] == 'INVALID_PLACEMENT'

    def test_road_building_cannot_place_a_bridge(self):
        # Road Building drives build_road with a free placement; the same
        # bridge-site guard refuses it, so the card can never place a bridge.
        game = playing_game()
        edge_key = self._connected_site(game)
        game.free_roads_remaining = 2
        result = game.build_road('Alice', edge_key)
        assert not result['success']
        assert game.free_roads_remaining == 2  # the free road was not spent

    def test_a_player_may_build_at_most_max_bridges(self):
        game = playing_game(max_bridges=1)
        edge_key = self._connected_site(game)
        alice = game.get_player('Alice')
        alice.resources = {'brick': 2, 'wood': 1}
        assert game.build_bridge('Alice', edge_key)['success']
        # A second site, still connected, but the cap is reached.
        vertex2 = game.edges[edge_key].neighbors['vertices'][1]
        edge2 = next(e for e in game.vertices[vertex2].neighbors['edges']
                     if e != edge_key)
        game.bridge_sites.add(edge2)
        alice.resources = {'brick': 2, 'wood': 1}
        result = game.build_bridge('Alice', edge2)
        assert not result['success'] and result['code'] == 'NO_PIECES_LEFT'

    def test_a_bridge_counts_for_the_longest_road(self):
        game = playing_game()
        start = an_inland_vertex(game)
        game.vertices[start].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(start)
        chain = walk_path(game, start, 5)
        # Four ordinary roads, then a bridge as the connected fifth segment.
        for edge_key in chain[:4]:
            game.edges[edge_key].road = {'player': 'Alice'}
            game.get_player('Alice').roads.append(edge_key)
        game.bridge_sites = {chain[4]}
        game.get_player('Alice').resources = {'brick': 2, 'wood': 1}
        assert game.build_bridge('Alice', chain[4])['success']
        game.update_longest_road()
        assert game.longest_road_length['Alice'] == 5
        assert game.longest_road_holder == 'Alice'


class TestScoringTiles:
    def test_the_sole_wealthiest_holds_the_plus_one(self):
        game = playing_game()
        game.get_player('Alice').gold = 3
        game.get_player('Bob').gold = 1
        assert game.holds_wealthiest_settler('Alice')
        assert not game.holds_wealthiest_settler('Bob')
        assert game.river_tile_points('Alice') == 1

    def test_a_tie_leaves_the_wealthiest_tile_with_nobody(self):
        game = playing_game()
        game.get_player('Alice').gold = 2
        game.get_player('Bob').gold = 2
        assert not game.holds_wealthiest_settler('Alice')
        assert not game.holds_wealthiest_settler('Bob')

    def test_the_wealthiest_tile_swings_a_victory_point(self):
        game = playing_game()
        game.get_player('Alice').gold = 5
        game.get_player('Bob').gold = 0
        before = game.victory_points_for('Alice')
        game.get_player('Bob').gold = 5  # Bob catches up: Alice is no longer sole
        after = game.victory_points_for('Alice')
        assert before - after == 1

    def test_every_player_tied_for_fewest_holds_the_poor_tile(self):
        game = make_game(rules=rivers_rules(), players=('Alice', 'Bob', 'Carol'))
        game.game_phase = 'playing'
        game.get_player('Alice').gold = 0
        game.get_player('Bob').gold = 0
        game.get_player('Carol').gold = 3
        assert game.holds_poor_settler('Alice')
        assert game.holds_poor_settler('Bob')
        assert not game.holds_poor_settler('Carol')
        assert game.river_tile_points('Alice') == -2

    def test_the_poor_tile_returns_when_you_climb_off_the_bottom(self):
        game = playing_game()
        game.get_player('Alice').gold = 0
        game.get_player('Bob').gold = 2
        assert game.holds_poor_settler('Alice')
        game.get_player('Alice').gold = 2  # tied now — no longer alone at the bottom
        assert not game.holds_poor_settler('Alice')

    def test_the_tiles_are_dead_without_their_rules(self):
        game = playing_game(wealthiest_settler=False, poor_settler=False)
        game.get_player('Alice').gold = 9
        assert game.river_tile_points('Alice') == 0
