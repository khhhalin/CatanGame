"""The Caravans (Traders & Barbarians, expansions.md 571-606).

One container rule, `caravans`, decomposed the way every other expansion is: it
carries the camel piece, the oasis-arrow geometry, the voting round and the two
scoring effects, because none of them means anything without the others. These
tests pin the catalogue coherence and the oasis-map dependency, the caravan
geometry (non-branching, three chains, the supply cap), the voting round (a build
opens it, the bids resolve, one camel lands), the road-counts-as-two Longest Road
and the between-two-camels victory point, and prove the base game is untouched.

Everything is asserted against the live engine — a game is dealt, a camel is
placed, a tile scores — never against a copied literal.
"""

import random

from game import rules as rules_module
from game.game import Game


def make_game(rules=None, players=("Alice", "Bob")):
    return Game(list(players), [], rng=random.Random(4242), rules=rules)


def caravans_rules(**overrides):
    """The Caravans preset, coerced, minus the board_map so tests deal the
    default board and inject camels directly rather than lean on the oasis map."""
    chosen = dict(rules_module.TB_CARAVANS_RULES)
    chosen.pop("board_map", None)
    chosen.update(overrides)
    return rules_module.coerce(chosen)


def playing_game(**overrides):
    """A Caravans game rolled forward into the play phase."""
    game = make_game(rules=caravans_rules(**overrides))
    game.game_phase = 'playing'
    game.has_rolled_dice = True
    return game


def oasis_board_game(players=("Alice", "Bob"), seed=7):
    """A game dealt on the built-in Caravans map — an oasis with three arrows."""
    from game import map_store, maps
    defn = maps.parse_map(map_store.read_map('caravans'))
    chosen = dict(rules_module.TB_CARAVANS_RULES)
    return Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)


def an_inland_vertex(game):
    for key, vertex in sorted(game.vertices.items()):
        if len(vertex.neighbors['hexes']) == 3:
            return key
    raise AssertionError('no inland vertex on this board')


def walk_path(game, start_vertex, length):
    """A simple chain of `length` connected edge keys walking the board graph."""
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
    def test_caravans_is_off_in_the_base_game(self):
        assert rules_module.defaults()["caravans"] is False

    def test_max_camels_defaults_to_twenty_two(self):
        assert rules_module.defaults()["max_camels"] == 22

    def test_caravans_suggests_a_target_of_twelve(self):
        assert rules_module.RULES_BY_ID["caravans"]["suggests_victory_target"] == 12

    def test_caravans_needs_no_other_rule(self):
        # It depends on the oasis map, not another switch, so the rule set alone
        # is coherent — the map dependency is checked separately.
        assert rules_module.dependency_problems({"caravans": True}) == []

    def test_the_preset_is_coherent(self):
        chosen = rules_module.preset_rules("tb_caravans")
        assert rules_module.dependency_problems(chosen) == []
        assert rules_module.exclusion_problems(chosen) == []

    def test_the_preset_ticks_caravans_and_suggests_twelve(self):
        chosen = rules_module.preset_rules("tb_caravans")
        assert chosen["caravans"] is True
        assert chosen["victory_target"] == 12
        assert chosen["board_map"] == "caravans"

    def test_caravans_needs_the_oasis_map(self):
        from game import map_store, maps
        oasis = maps.parse_map(map_store.read_map("caravans"))
        rivers = maps.parse_map(map_store.read_map("rivers"))
        # The oasis board is accepted; a board with no oasis is refused by name.
        assert maps.start_problems(oasis, {"caravans": True}) == []
        problems = maps.start_problems(rivers, {"caravans": True})
        assert len(problems) == 1 and "oasis" in problems[0]

    def test_a_caravans_game_builds_the_tb_container(self):
        # Camels, chains and the open vote need somewhere to live.
        assert make_game(rules=caravans_rules()).tb is not None

    def test_a_base_game_builds_no_tb_container(self):
        assert make_game(rules=rules_module.defaults()).tb is None


class TestCamelGeometry:
    def test_the_first_camel_may_only_start_on_an_arrow(self):
        game = oasis_board_game()
        offered = {o['edge'] for o in game.legal_camel_placements()}
        assert offered == set(game.oasis_arrows)
        assert len(game.oasis_arrows) == 3

    def test_placing_a_camel_starts_a_caravan_with_a_head(self):
        game = oasis_board_game()
        arrow = game.oasis_arrows[0]
        result = game.place_camel(arrow)
        assert result['success']
        assert arrow in game.tb.camels
        assert len(game.tb.caravans) == 1
        caravan = game.tb.caravans[0]
        # The head points away from the oasis — to the far end of the arrow.
        assert caravan['frontier'] == game._oasis_arrow_front(arrow)
        assert game.tb.camels[arrow]['front'] == caravan['frontier']

    def test_a_caravan_extends_from_the_front_and_never_branches(self):
        game = oasis_board_game()
        arrow = game.oasis_arrows[0]
        game.place_camel(arrow)
        caravan = game.tb.caravans[0]
        frontier = caravan['frontier']
        # Every extension leaves from the frontier, none reuses the arrow path,
        # and a single caravan offers at most two continuations (no branching).
        extensions = [o for o in game.legal_camel_placements() if o['caravan'] == 0]
        assert extensions, 'the caravan should be extendable'
        assert len(extensions) <= 2
        for option in extensions:
            assert frontier in game.edges[option['edge']].neighbors['vertices']
            assert option['edge'] != arrow

    def test_only_three_caravans_ever_start(self):
        game = oasis_board_game()
        for arrow in game.oasis_arrows:
            assert game.place_camel(arrow)['success']
        assert len(game.tb.caravans) == 3
        # With all three arrows used no fresh caravan is on offer any more.
        assert all(o['caravan'] is not None for o in game.legal_camel_placements())

    def test_a_path_with_a_camel_is_never_offered_again(self):
        game = oasis_board_game()
        arrow = game.oasis_arrows[0]
        game.place_camel(arrow)
        assert arrow not in {o['edge'] for o in game.legal_camel_placements()}

    def test_the_supply_cap_ends_every_caravan(self):
        game = oasis_board_game()
        game.rules['max_camels'] = 1
        game.place_camel(game.oasis_arrows[0])
        # One camel placed, the supply is spent, nothing more is legal.
        assert game.legal_camel_placements() == []

    def test_an_illegal_path_is_refused(self):
        game = oasis_board_game()
        # An oasis-edge path is never legal for a first camel (expansions.md 586).
        oasis_edges = [
            key for key, edge in game.edges.items()
            if sum(1 for v in edge.neighbors['vertices']
                   if game.oasis_hex in game.vertices[v].neighbors['hexes']) == 2
        ]
        result = game.place_camel(oasis_edges[0])
        assert not result['success'] and result['code'] == 'INVALID_PLACEMENT'


class TestScoring:
    def _two_camels_around(self, game, vertex):
        """Put camels on two of a vertex's incident paths."""
        edges = game.vertices[vertex].neighbors['edges'][:2]
        for edge_key in edges:
            game.tb.camels[edge_key] = {'front': vertex}
        return edges

    def test_a_building_between_two_camels_scores_one(self):
        game = playing_game()
        vertex = an_inland_vertex(game)
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(vertex)
        assert game.camel_victory_points('Alice') == 0
        edges = self._two_camels_around(game, vertex)
        assert game.camel_victory_points('Alice') == 1
        # The point swings the real victory total.
        with_point = game.victory_points_for('Alice')
        del game.tb.camels[edges[0]]  # a camel is no longer beside it
        assert game.camel_victory_points('Alice') == 0
        assert game.victory_points_for('Alice') == with_point - 1

    def test_one_camel_beside_a_building_is_not_enough(self):
        game = playing_game()
        vertex = an_inland_vertex(game)
        game.vertices[vertex].building = {'type': 'city', 'player': 'Alice'}
        game.get_player('Alice').cities.append(vertex)
        edge = game.vertices[vertex].neighbors['edges'][0]
        game.tb.camels[edge] = {'front': vertex}
        assert game.camel_victory_points('Alice') == 0

    def test_the_scoring_is_dead_without_the_rule(self):
        game = playing_game(caravans=False)
        # tb is gone with the rule off, so nothing can score.
        assert game.camel_victory_points('Alice') == 0


class TestLongestRoad:
    def test_a_road_on_a_camel_path_counts_as_two(self):
        game = playing_game()
        start = an_inland_vertex(game)
        game.vertices[start].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(start)
        chain = walk_path(game, start, 4)
        for edge_key in chain:
            game.edges[edge_key].road = {'player': 'Alice'}
            game.get_player('Alice').roads.append(edge_key)
        # Four plain roads make a road of length four.
        assert game.calculate_longest_road('Alice') == 4
        # Two of them now share a path with a camel; the length becomes six
        # (expansions.md 600): 2 + 1 + 2 + 1.
        game.tb.camels[chain[0]] = {'front': start}
        game.tb.camels[chain[2]] = {'front': start}
        assert game.calculate_longest_road('Alice') == 6

    def test_camels_do_not_lengthen_roads_without_the_rule(self):
        game = playing_game(caravans=False)
        start = an_inland_vertex(game)
        game.vertices[start].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(start)
        chain = walk_path(game, start, 3)
        for edge_key in chain:
            game.edges[edge_key].road = {'player': 'Alice'}
            game.get_player('Alice').roads.append(edge_key)
        assert game.calculate_longest_road('Alice') == 3


class TestVotingRound:
    def _ready_to_vote(self, players=("Alice", "Bob")):
        """An oasis game where Alice has ended a turn in which she built."""
        game = oasis_board_game(players=players)
        game.game_phase = 'playing'
        game.has_rolled_dice = True
        game.current_player_index = 0  # Alice's turn
        game.camel_owed = True
        return game

    def test_ending_a_building_turn_opens_the_vote(self):
        game = self._ready_to_vote()
        result = game.advance_turn('Alice')
        assert result['success'] and result.get('camel_vote')
        # The turn is held open — still Alice's — until the camel is placed.
        assert result['current_player'] == 'Alice'
        assert game.tb.camel_vote is not None
        assert game.current_player_index == 0

    def test_bids_resolve_and_place_exactly_one_camel(self):
        game = self._ready_to_vote()
        game.get_player('Alice').resources = {'sheep': 2}
        game.get_player('Bob').resources = {'wheat': 1}
        game.advance_turn('Alice')
        # Bob bids one, Alice bids two — Alice holds the majority and chooses.
        assert game.bid_camel('Bob', ['wheat'])['success']
        opened = game.bid_camel('Alice', ['sheep', 'sheep'])
        assert opened['success']
        # More than one arrow is legal, so the winner is asked which path.
        choice = game.pending_choice_for('Alice')
        assert choice is not None and choice['kind'] == 'camel_placement'
        target = choice['options'][0]
        game.resolve_choice('Alice', 'camel_placement', target)
        # Exactly one camel is on the board, on the path Alice chose.
        assert len(game.tb.camels) == 1 and target in game.tb.camels
        # Every bid card is discarded and the turn has passed to Bob.
        assert game.get_player('Alice').resources.get('sheep', 0) == 0
        assert game.get_player('Bob').resources.get('wheat', 0) == 0
        assert game.tb.camel_vote is None
        assert game.current_player_index == 1

    def test_a_tie_falls_to_the_finisher(self):
        game = self._ready_to_vote()
        game.get_player('Alice').resources = {'sheep': 1}
        game.get_player('Bob').resources = {'wheat': 1}
        game.advance_turn('Alice')
        game.bid_camel('Bob', ['wheat'])
        game.bid_camel('Alice', ['sheep'])  # one each — a tie
        # The finisher (Alice) is asked, even on a tied vote.
        choice = game.pending_choice_for('Alice')
        assert choice is not None and choice['kind'] == 'camel_placement'

    def test_a_bid_must_be_wool_or_grain(self):
        game = self._ready_to_vote()
        game.get_player('Alice').resources = {'ore': 1}
        game.advance_turn('Alice')
        result = game.bid_camel('Alice', ['ore'])
        assert not result['success'] and result['code'] == 'INVALID_BID'

    def test_you_cannot_bid_cards_you_do_not_hold(self):
        game = self._ready_to_vote()
        game.get_player('Alice').resources = {}
        game.advance_turn('Alice')
        result = game.bid_camel('Alice', ['sheep'])
        assert not result['success'] and result['code'] == 'INSUFFICIENT_RESOURCES'

    def test_a_player_bids_only_once(self):
        game = self._ready_to_vote()
        game.get_player('Alice').resources = {'sheep': 2}
        game.advance_turn('Alice')
        assert game.bid_camel('Alice', ['sheep'])['success']
        again = game.bid_camel('Alice', ['sheep'])
        assert not again['success'] and again['code'] == 'ALREADY_BID'

    def test_a_build_is_refused_while_the_vote_is_open(self):
        game = self._ready_to_vote()
        game.advance_turn('Alice')
        blocked = game.build_road('Alice', next(iter(game.edges)))
        assert not blocked['success'] and blocked['code'] == 'CAMEL_VOTE'

    def test_a_single_legal_path_is_placed_without_a_choice(self):
        # When exactly one path is legal there is nothing to decide, so the camel
        # is placed at once and the turn advances with no pending choice.
        game = self._ready_to_vote()
        only = game.oasis_arrows[0]
        game.legal_camel_placements = lambda: [
            {'edge': only, 'front': game._oasis_arrow_front(only),
             'caravan': None, 'arrow': only}
        ]
        game.advance_turn('Alice')
        game.bid_camel('Bob', [])
        game.bid_camel('Alice', [])
        assert game.pending_choice_for('Alice') is None
        assert only in game.tb.camels
        assert game.current_player_index == 1  # the turn has advanced


class TestCaravansBoard:
    """The built-in Caravans map: dealt, played through a cycle, and saved."""

    def test_the_map_deals_an_oasis_and_three_arrows(self):
        game = oasis_board_game()
        oasis = [k for k, h in game.hexes.items() if h.type == 'oasis']
        assert oasis == [game.oasis_hex]
        assert len(game.oasis_arrows) == 3
        for arrow in game.oasis_arrows:
            assert arrow in game.edges
            assert game._oasis_arrow_front(arrow) is not None

    def test_a_full_cycle_deals_builds_votes_and_places_a_camel(self):
        game = oasis_board_game()
        game.game_phase = 'playing'
        game.has_rolled_dice = True
        game.current_player_index = 0
        game.camel_owed = True
        game.advance_turn('Alice')
        game.bid_camel('Bob', [])
        game.bid_camel('Alice', [])
        # The finisher chooses when nobody bid (expansions.md 597).
        choice = game.pending_choice_for('Alice')
        if choice is not None:
            game.resolve_choice('Alice', 'camel_placement', choice['options'][0])
        assert len(game.tb.camels) == 1

    def test_the_camels_survive_a_save_and_load(self, tmp_path):
        from game import persistence
        game = oasis_board_game()
        game.place_camel(game.oasis_arrows[0])
        game.place_camel(game.oasis_arrows[1])
        before_camels = dict(game.tb.camels)
        before_caravans = [dict(c) for c in game.tb.caravans]
        path = str(tmp_path / 'caravans.json')
        persistence.save(game, path)
        reloaded = persistence.load(path)
        assert reloaded.tb.camels == before_camels
        assert reloaded.tb.caravans == before_caravans
        assert set(reloaded.oasis_arrows) == set(game.oasis_arrows)


class TestBaseGameUnchanged:
    def test_a_standard_board_has_no_oasis_or_camels(self):
        game = make_game(rules=rules_module.defaults())
        assert game.oasis_hex is None
        assert game.oasis_arrows == []
        assert game.tb is None

    def test_the_longest_road_walk_is_unweighted_off_the_rule(self):
        # A plain game's road length is a plain edge count — the camel weighting
        # is inert without the rule and without a tb container.
        game = make_game(rules=rules_module.defaults())
        game.game_phase = 'playing'
        start = an_inland_vertex(game)
        game.vertices[start].building = {'type': 'settlement', 'player': 'Alice'}
        game.get_player('Alice').settlements.append(start)
        chain = walk_path(game, start, 5)
        for edge_key in chain:
            game.edges[edge_key].road = {'player': 'Alice'}
            game.get_player('Alice').roads.append(edge_key)
        assert game.calculate_longest_road('Alice') == 5
