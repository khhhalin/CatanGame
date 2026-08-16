"""The Seafarers scenario "Cloth for Catan", built as a board plus a preset.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 6 "Cloth for Catan"
(p. 22). The small islands carry eight villages — number tokens sitting on
intersections, each with a supply of cloth bolts. Joining one of your own
settlements or cities to a village by a shipping route pays 1 bolt at once, then
1 more from that village every time its number is rolled, until the village is
empty. Two bolts of cloth score 1 victory point; an unpaired bolt scores
nothing. No victory points are awarded for the Longest Trade Route, and players
start with a third settlement. Win at 14.

What is worth pinning is the board the scenario deals — read off the generated
board, never a literal copied from the file — the cloth a route earns when a
village number is rolled, the two-bolts-to-a-point scoring with an odd bolt
scoring nothing, that no line award is handed out, and that setup runs the extra
round that leaves everyone with three settlements.
"""

import random
from collections import Counter, deque

from game import map_store, maps, persistence, tiles
from game import rules as rules_module
from game.game import Game
from seafarers_board import (
    build_ships_along,
    coastal_vertex,
    give_building,
    other_end,
    sea_edges_at,
    ship_path,
)


def cloth_game(players=('Alice', 'Bob'), seed=12345, **overrides):
    """A Cloth for Catan game on the built-in board, rules from the preset."""
    defn = maps.parse_map(map_store.read_map('cloth-for-catan'))
    chosen = dict(rules_module.preset_rules('cloth_for_catan'))
    chosen['turn_order'] = 'lobby'
    # The map the scenario is played on, recorded the way the lobby records it,
    # so a saved game regenerates this board rather than a default one.
    chosen['board_layout'] = 'custom'
    chosen['board_map'] = 'cloth-for-catan'
    chosen.update(overrides)
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)
    game.start()
    return game


def _playing(game):
    """Move a freshly-built game into normal play without running setup."""
    game.game_phase = 'playing'
    game.start_turn()
    return game


def sea_route_to_village(game, village_vertex):
    """A run of sea sides joining a main-island vertex to this village.

    Found by breadth-first search over the sea sides rather than written down,
    so the route is real geometry on the generated board. Returns (anchor,
    edges): the main-land intersection a settlement can anchor the route on, and
    the sides from the village out to it, the first of which meets the village.
    """
    visited = {village_vertex}
    queue = deque([(village_vertex, [])])
    while queue:
        vertex_key, edges = queue.popleft()
        hexes = game.vertices[vertex_key].neighbors['hexes']
        if vertex_key != village_vertex and any(game.is_main_land(h) for h in hexes):
            return vertex_key, edges
        for edge_key in sea_edges_at(game, vertex_key):
            ahead = other_end(game, edge_key, vertex_key)
            if ahead not in visited:
                visited.add(ahead)
                queue.append((ahead, edges + [edge_key]))
    raise AssertionError(f'no sea route from village {village_vertex} to the main land')


def connect_by_ships(game, player_name, village_vertex):
    """Anchor a settlement on the main land and lay a whole ship route to a
    village, bypassing cost and turn order. Returns the anchor vertex."""
    anchor, edges = sea_route_to_village(game, village_vertex)
    give_building(game, player_name, anchor)
    build_ships_along(game, player_name, edges)
    return anchor


class TestTheBoardAsDealt:
    """Every assertion reads the board the engine generated, so a literal that
    drifts from the file is caught where it is consumed, not where it is
    declared."""

    def test_it_deals_eight_villages_each_holding_five_bolts(self):
        """Rulebook: two villages on each of the four small islands, 5 Catan
        chits set beside each village."""
        game = _playing(cloth_game())
        assert len(game.village_number) == 8
        assert list(game.village_cloth.values()) == [5] * 8
        # 50 chits in all: 8 x 5 beside the villages and 10 in general supply.
        assert game.cloth_general_supply == 10

    def test_each_village_sits_on_a_barren_small_island(self):
        """A village is a number token on an intersection of a small island, and
        those islands are barren — the no-build and robber bans read them."""
        game = _playing(cloth_game())
        for vertex_key in game.village_number:
            hexes = game.vertices[vertex_key].neighbors['hexes']
            assert hexes, f'village {vertex_key} touches no hex'
            assert all(hex_key in game.barren_island_hexes for hex_key in hexes)
        # Four small islands carry them, two apiece.
        island_of = {}
        for vertex_key in game.village_number:
            for hex_key in game.vertices[vertex_key].neighbors['hexes']:
                island_of.setdefault(hex_key, 0)
                island_of[hex_key] += 1
        assert sorted(island_of.values()) == [2, 2, 2, 2]

    def test_the_village_numbers_are_die_rolls_and_never_seven(self):
        """A village pays on its number, so every one must be a number a die can
        roll and none may be a 7."""
        numbers = sorted(game_numbers := list(cloth_game().village_number.values()))
        assert len(game_numbers) == 8
        assert all(2 <= n <= 12 and n != 7 for n in numbers)

    def test_the_main_island_carries_the_eighteen_printed_tokens(self):
        """The producing hexes of the main island carry the standard token bag,
        read off the generated board."""
        game = _playing(cloth_game())
        producing = [key for key, hex_obj in game.hexes.items()
                     if hex_obj.type not in ('ocean', 'desert')]
        tokens = sorted(game.hexes[key].number for key in producing)
        assert tokens == [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]


class TestCloth:
    def test_a_villages_roll_pays_the_route_joined_to_it(self):
        """When a village number is rolled, a player whose shipping route reaches
        it takes a bolt from its supply; a player with no route takes none."""
        game = _playing(cloth_game())
        village = min(game.village_number)
        number = game.village_number[village]
        connect_by_ships(game, 'Alice', village)

        supply_before = game.village_cloth[village]
        gained = game.distribute_cloth(number)

        assert gained == {'Alice': 1}
        assert game.cloth_tokens['Alice'] == 1
        assert 'Bob' not in gained
        assert game.village_cloth[village] == supply_before - 1

    def test_two_bolts_score_a_point_and_an_odd_bolt_scores_nothing(self):
        """Two bolts of cloth are worth 1 victory point; an unpaired bolt is
        worth nothing (integer division)."""
        game = _playing(cloth_game())
        village = min(game.village_number)
        number = game.village_number[village]
        connect_by_ships(game, 'Alice', village)

        base = game.victory_points_for('Alice')

        game.distribute_cloth(number)               # first bolt
        assert game.cloth_victory_points('Alice') == 0
        assert game.victory_points_for('Alice') == base

        game.distribute_cloth(number)               # second bolt: a pair
        assert game.cloth_victory_points('Alice') == 1
        assert game.victory_points_for('Alice') == base + 1

    def test_an_empty_village_pays_no_one_and_leaves_the_general_supply(self):
        """"If there are zero Catan chits next to a village when its number is
        rolled, no one receives any" — and the general supply is not touched."""
        game = _playing(cloth_game())
        village = min(game.village_number)
        number = game.village_number[village]
        connect_by_ships(game, 'Alice', village)

        game.village_cloth[village] = 0
        general_before = game.cloth_general_supply

        gained = game.distribute_cloth(number)

        assert gained == {}
        assert game.cloth_general_supply == general_before

    def test_the_general_supply_covers_a_short_village(self):
        """A village short of paying every connected player draws the shortfall
        from the general supply, but only once it has a bolt of its own to
        start with."""
        game = _playing(cloth_game())
        village = min(game.village_number)
        number = game.village_number[village]
        # Two players joined to the same village by two separate one-ship routes,
        # each anchored on its own settlement.
        edges = sea_edges_at(game, village)
        for player_name, edge_key in (('Alice', edges[0]), ('Bob', edges[1])):
            give_building(game, player_name, other_end(game, edge_key, village))
            build_ships_along(game, player_name, [edge_key])
        assert set(game.village_route_players(village)) == {'Alice', 'Bob'}

        game.village_cloth[village] = 1             # one bolt, two players owed
        general_before = game.cloth_general_supply

        gained = game.distribute_cloth(number)

        assert gained == {'Alice': 1, 'Bob': 1}
        assert game.village_cloth[village] == 0
        assert game.cloth_general_supply == general_before - 1

    def test_building_a_ship_to_a_village_earns_the_first_bolt_at_once(self):
        """"You immediately take 1 bolt of cloth from the supply of this
        village" the moment the route reaches it."""
        game = _playing(cloth_game())
        village = min(game.village_number)
        anchor, edges = sea_route_to_village(game, village)
        give_building(game, 'Alice', anchor)
        # Lay every ship but the one that meets the village, then build that last
        # one for real so the engine's own build path pays the opening bolt.
        build_ships_along(game, 'Alice', edges[1:])
        game.current_player_index = next(
            i for i, p in enumerate(game.players) if p.name == 'Alice')
        game.free_roads_remaining = 1
        game.get_player('Alice').resources = {}

        supply_before = game.village_cloth[village]
        result = game.build_ship('Alice', edges[0])

        assert result['success'], result
        assert result['cloth'] == {village: 1}
        assert game.cloth_tokens['Alice'] == 1
        assert game.village_cloth[village] == supply_before - 1

    def test_a_second_ship_to_the_same_village_earns_nothing_more(self):
        """The opening bolt is paid once per village: extending the route again
        does not pay it a second time."""
        game = _playing(cloth_game())
        village = min(game.village_number)
        connect_by_ships(game, 'Alice', village)
        first = game.claim_cloth_connections('Alice')
        again = game.claim_cloth_connections('Alice')
        assert first == {village: 1}
        assert again == {}
        assert game.cloth_tokens['Alice'] == 1


class TestPersistence:
    def test_cloth_progress_survives_a_restart(self, tmp_path):
        """Banked bolts, a depleted village and an established trade relation are
        decided state — losing any on reload is losing the game the table played.
        """
        game = _playing(cloth_game())
        village = min(game.village_number)
        connect_by_ships(game, 'Alice', village)
        game.claim_cloth_connections('Alice')       # the opening bolt, village -1
        game.cloth_general_supply -= 2               # a couple spent elsewhere

        path = str(tmp_path / 'game.json')
        persistence.save(game, path)
        restored = persistence.load(path)

        assert restored.cloth_tokens == game.cloth_tokens
        assert restored.village_cloth[village] == game.village_cloth[village]
        assert restored.village_cloth[village] == 4
        assert restored.cloth_general_supply == game.cloth_general_supply
        # The trade relation is remembered, so the opening bolt is not paid twice.
        assert 'Alice' in restored.village_traders[village]
        assert restored.claim_cloth_connections('Alice') == {}
        assert restored.victory_points_for('Alice') == game.victory_points_for('Alice')


class TestNoLineAward:
    def test_a_long_ship_route_wins_no_card_under_the_preset(self):
        """No victory points are awarded for the Longest Trade Route, so a route
        long enough to hold it under Seafarers holds nothing here."""
        game = _playing(cloth_game())
        assert game.rules['longest_trade_route'] is False
        assert game.rules['longest_road_card'] is False

        # A run of six ships anchored on a settlement would take the Trade Route
        # card in a scenario that awarded it.
        start = coastal_vertex(game)
        edges, _ = ship_path(game, start, 6)
        give_building(game, 'Alice', start)
        build_ships_along(game, 'Alice', edges)

        game.update_longest_road()
        # Nobody holds the line card, and Alice scores only her one settlement —
        # no two-point award is added on top of it.
        assert game.longest_road_holder is None
        assert game.victory_points_for('Alice') == 1
        assert game.victory_points_for('Bob') == 0


def _dice_for(total):
    """A die pair that sums to a village number (2..12, never 7)."""
    if total <= 7:
        return (1, total - 1)
    return (6, total - 6)


def _drain_all_but(game, keep):
    """Empty every village but `keep` of them, so the next depletion ends the
    game. Leaves `keep` villages holding a bolt; the rest hold none."""
    villages = sorted(game.village_number)
    for vertex_key in villages[keep:]:
        game.village_cloth[vertex_key] = 0


class TestVillagesOutEnd:
    """The scenario's second end condition (expansions.md 191-192): the game
    ends the instant three or fewer villages still hold cloth, and the winner is
    the player with the most victory points, a tie broken in favour of more
    bolts of cloth."""

    def test_the_depleting_roll_ends_the_game_for_the_most_victory_points(self):
        """When a roll empties the fourth-from-last village — dropping the count
        to three — the game finishes and the leader on victory points wins."""
        game = _playing(cloth_game())
        village = min(game.village_number)
        number = game.village_number[village]
        connect_by_ships(game, 'Alice', village)

        # Four villages hold cloth going into the roll; the target village holds
        # its last bolt, so paying it out drops the count to three.
        _drain_all_but(game, 4)
        game.village_cloth[village] = 1
        assert game.villages_with_cloth_remaining() == 4

        # Alice leads: her banked bolts score points Bob has no answer to.
        game.cloth_tokens['Alice'] = 5
        game.pending_dice = _dice_for(number)

        result = game.roll_dice('Alice')

        assert game.villages_with_cloth_remaining() == 3
        assert game.game_state == 'finished'
        assert result['game_over'] == {
            'winner': 'Alice',
            'victory_points': game.victory_points_for('Alice'),
            'reason': 'villages_depleted',
        }

    def test_a_tie_on_points_is_broken_by_more_bolts_of_cloth(self):
        """Level on victory points, the villages-out win goes to the player
        holding more bolts of cloth."""
        game = _playing(cloth_game())
        _drain_all_but(game, 3)
        assert game.villages_with_cloth_remaining() == 3

        # Equal victory points (one cloth point each), Alice with the odd bolt
        # that breaks the tie.
        game.cloth_tokens['Alice'] = 3
        game.cloth_tokens['Bob'] = 2
        assert game.victory_points_for('Alice') == game.victory_points_for('Bob')

        ended = game.cloth_alternate_end()

        assert ended['winner'] == 'Alice'
        assert ended['reason'] == 'villages_depleted'
        assert game.game_state == 'finished'

    def test_reaching_the_target_on_your_turn_wins_ahead_of_the_villages_end(self):
        """The primary 14-VP win takes precedence: a roller who reaches the
        target on their own turn wins by points, even if the same roll empties
        the last village (expansions.md 191)."""
        game = _playing(cloth_game())
        village = min(game.village_number)
        number = game.village_number[village]
        connect_by_ships(game, 'Alice', village)
        _drain_all_but(game, 4)
        game.village_cloth[village] = 1

        # One bolt short of the target; the roll's bolt pushes Alice to 14 while
        # it also drops the village count to three.
        target = game.victory_points_to_win
        base = game.victory_points_for('Alice')
        game.cloth_tokens['Alice'] = 2 * (target - base) - 1
        game.pending_dice = _dice_for(number)

        result = game.roll_dice('Alice')

        assert game.villages_with_cloth_remaining() == 3
        assert result['game_over']['winner'] == 'Alice'
        assert result['game_over']['victory_points'] >= target
        assert result['game_over']['reason'] == 'victory_target'


class TestTheEndIsGatedOnTheRule:
    """A game without villages must never trip the villages-out end. It has zero
    villages holding cloth, which is `<= 3`, so nothing but the `cloth_villages`
    gate stops every base-game roll from ending the game on the spot."""

    def test_a_base_game_roll_never_reports_a_villages_out_win(self):
        game = Game(['Alice', 'Bob'], [], rng=random.Random(5))
        game.start()
        game.game_phase = 'playing'
        game.current_player_index = 0
        game.start_turn()

        assert game.rules['cloth_villages'] is False
        # The count the alternate end reads is already at zero — the gate is the
        # only thing between that and a game that ends before anyone plays.
        assert game.villages_with_cloth_remaining() == 0

        result = game.roll_dice('Alice')

        assert result['game_over'] is None
        assert game.game_state != 'finished'


class TestThirdSettlement:
    def _play_setup(self, game):
        seats = []
        while game.game_phase == 'setup':
            actor = game.current_player_name()
            seats.append(actor)
            vertex_key = next(
                key for key in sorted(game.vertices)
                if game.place_settlement(actor, key)['success'])
            edge_key = next(
                key for key in game.vertices[vertex_key].neighbors['edges']
                if game.build_road(actor, key)['success'])
            del edge_key
        return seats

    def test_every_player_starts_with_three_settlements(self):
        """Setup runs a third round: after the two normal settlements everyone
        places a third one."""
        game = cloth_game()
        seats = self._play_setup(game)
        assert game.game_phase == 'playing'
        assert len(seats) == 3 * len(game.players)
        for player in game.players:
            assert len(player.settlements) == 3

    def test_without_the_rule_the_same_board_starts_with_two(self):
        """The extra round is the rule's doing, not the board's: turn it off and
        setup ends after two settlements apiece."""
        game = cloth_game(setup_third_settlement=False)
        seats = self._play_setup(game)
        assert len(seats) == 2 * len(game.players)
        for player in game.players:
            assert len(player.settlements) == 2

    def test_the_opening_hand_comes_from_the_third_settlement(self):
        """"When you place your third settlement, you receive your starting
        resources" — so the hand matches the third settlement's hexes, not the
        second's."""
        game = cloth_game()
        self._play_setup(game)
        for player in game.players:
            third = player.settlements[2]
            expected = Counter()
            for hex_key in game.vertices[third].neighbors['hexes']:
                resource = tiles.produces(game.hexes[hex_key].type)
                if resource is not None:
                    expected[resource] += 1
            held = Counter({r: n for r, n in player.resources.items() if n})
            assert held == expected
