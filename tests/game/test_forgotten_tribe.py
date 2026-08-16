"""The Seafarers scenario "The Forgotten Tribe", built as a board plus a preset.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 5 "The Forgotten Tribe"
(p. 20). The small islands around the main land carry marked coast edges;
sailing a ship onto one — building or moving it there — claims the gift printed
on it, once. The gift bag is 8 Catan chits (1 VP each), 4 development cards, and
6 harbours (5 special 2:1, one per resource, and 1 generic 3:1). No building on
the barren small islands, the robber may not move to them, and the game ends at
13 victory points.

The mechanic reuses machinery that already exists: a chit is a special point
banked like the island bonus, a development card is drawn from the shared deck
on the same terms as a bought one, and a harbour is placed through the pending
-choice system onto the same edge/vertex `port` geometry the auto-placer writes.
So what is worth pinning is the board the scenario ships — read off the
generated board, never a literal copied from the file — and that a ship reaching
a marked edge claims and applies each of the three gifts.

The only draw from the "gift bag" is the development card, off the shared dev
deck, which is seeded through the game's injected Random; the chit and the
harbour are fixed by which edge is reached, so the board fully determines them.
"""

import random
from collections import Counter

from game import map_store, maps
from game import rules as rules_module
from game.game import Game
from seafarers_board import give_building


def ft_game(players=('Alice', 'Bob'), seed=12345):
    """A Forgotten Tribe game past setup, on the built-in board."""
    defn = maps.parse_map(map_store.read_map('forgotten-tribe'))
    chosen = dict(rules_module.preset_rules('forgotten_tribe'))
    chosen['turn_order'] = 'lobby'
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.start_turn()
    return game


def barren_hexes(game):
    return sorted(game.barren_island_hexes)


def producing_hexes(game):
    return [key for key, hex_obj in game.hexes.items()
            if hex_obj.type not in ('ocean', 'desert')]


def edge_of_kind(game, kind):
    """The first marked gift edge of this kind, in a stable order."""
    for edge_key in sorted(game.gift_edges):
        if game.gift_edges[edge_key]['gift'] == kind:
            return edge_key
    raise AssertionError(f'no {kind} gift edge on this board')


def claim_by_building_ship(game, player, edge_key):
    """Stand a settlement at the gift edge and lay a free ship on it.

    Scaffolding only: the behaviour under test is the claim the ship triggers,
    so a full turn's roads and resources would only add noise. A settlement at
    one end satisfies the ship-connection rule, and the free ship keeps the hand
    showing the reward alone.
    """
    vertex_key = game.edges[edge_key].neighbors['vertices'][0]
    give_building(game, player, vertex_key)
    actor = game.get_player(player)
    actor.resources = {}
    game.free_roads_remaining = 1
    return game.build_ship(player, edge_key)


class TestTheBoardAsDealt:
    """Every assertion reads the board the engine generated, so a literal that
    drifts from the file is caught where it is consumed, not where it is
    declared."""

    def test_it_marks_eighteen_gift_edges_in_the_printed_mix(self):
        """Rulebook gift bag: 8 Catan chits, 4 development cards, 6 harbours."""
        game = ft_game()
        kinds = Counter(gift['gift'] for gift in game.gift_edges.values())
        assert kinds == {'victory_point': 8, 'dev_card': 4, 'harbor': 6}

    def test_the_six_harbour_gifts_are_five_two_to_one_and_one_generic(self):
        """Rulebook harbours: one special 2:1 per resource and one generic 3:1,
        every one delivered as a gift rather than printed on the coast."""
        game = ft_game()
        ports = sorted(
            gift['port'] for gift in game.gift_edges.values() if gift['gift'] == 'harbor'
        )
        assert ports == ['brick', 'generic', 'ore', 'sheep', 'wheat', 'wood']

    def test_no_harbour_is_printed_on_the_coast_at_start(self):
        """Every harbour is a gift, so the board deals none: no edge or vertex
        carries a port before a single one is claimed."""
        game = ft_game()
        assert not any(edge.port for edge in game.edges.values())
        assert not any(vertex.port for vertex in game.vertices.values())

    def test_it_deals_four_barren_single_hex_islands_with_no_tokens(self):
        """The small islands do not produce and never receive number tokens, so
        each is a single desert hex out at sea."""
        game = ft_game()
        barren = barren_hexes(game)
        assert len(barren) == 4
        for key in barren:
            assert game.hexes[key].type == 'desert'
            assert game.hexes[key].number is None

    def test_the_main_island_carries_the_eighteen_printed_tokens(self):
        """Rulebook token bag for the producing hexes of the main island."""
        game = ft_game()
        tokens = sorted(game.hexes[key].number for key in producing_hexes(game))
        assert tokens == [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]


class TestClaimingAGift:
    """A ship reaching a marked coast edge is the whole scenario. Each of the
    three gifts is applied off the shared machinery it belongs to."""

    def test_a_chit_edge_adds_one_special_victory_point(self):
        game = ft_game()
        edge_key = edge_of_kind(game, 'victory_point')
        # The settlement's own point is placed first, then measured, so the
        # chit's point is the only change the claim makes.
        vertex_key = game.edges[edge_key].neighbors['vertices'][0]
        give_building(game, 'Alice', vertex_key)
        game.get_player('Alice').resources = {}
        game.free_roads_remaining = 1
        vp_before = game.victory_points_for('Alice')

        result = game.build_ship('Alice', edge_key)

        assert result['success']
        assert result['gift'] == {'gift': 'victory_point', 'victory_points': 1}
        assert game.victory_points_for('Alice') == vp_before + 1

    def test_a_dev_card_edge_puts_a_card_in_the_hand_unplayable_this_turn(self):
        game = ft_game()
        edge_key = edge_of_kind(game, 'dev_card')
        alice = game.get_player('Alice')
        before = alice.total_dev_cards()

        result = claim_by_building_ship(game, 'Alice', edge_key)

        assert result['success']
        card_type = result['gift']['card_type']
        assert card_type is not None
        assert alice.total_dev_cards() == before + 1
        # Stamped with this turn, so it cannot be played the turn it was gifted,
        # exactly as a bought card cannot.
        assert alice.dev_cards[card_type]['purchase_turn'] == game.turn_count

    def test_a_harbour_edge_opens_a_placement_choice_that_lays_a_real_port(self):
        game = ft_game()
        edge_key = edge_of_kind(game, 'harbor')
        port = game.gift_edges[edge_key]['port']

        result = claim_by_building_ship(game, 'Alice', edge_key)

        assert result['success']
        assert result['gift']['pending'] is True
        choice = game.pending_choice_for('Alice')
        assert choice is not None and choice['kind'] == 'gift_harbor'

        placed_edge = choice['options'][0]
        answer = game.resolve_choice('Alice', 'gift_harbor', placed_edge)
        assert answer['success']
        # The harbour lands on the same edge/vertex geometry the auto-placer
        # writes, so it trades like a printed one.
        expected = {'type': 'generic'} if port == 'generic' \
            else {'type': 'resource', 'resource': port}
        assert game.edges[placed_edge].port == expected
        for vertex_key in game.edges[placed_edge].neighbors['vertices']:
            assert game.vertices[vertex_key].port == expected

    def test_a_gift_edge_pays_out_only_once(self):
        """A ship moved back onto a spent edge claims nothing: the chit, the
        card and the harbour are each taken once."""
        game = ft_game()
        edge_key = edge_of_kind(game, 'victory_point')
        claim_by_building_ship(game, 'Alice', edge_key)
        assert edge_key in game.claimed_gift_edges

        # The same edge, claimed a second time by hand, yields nothing.
        assert game.claim_coast_gift('Alice', edge_key) is None
        assert game.claim_coast_gift('Bob', edge_key) is None

    def test_moving_a_ship_onto_a_gift_edge_claims_it_too(self):
        """The rulebook grants the gift when you "build (or move) a ship" onto
        the edge, so the move path claims exactly as the build path does."""
        game = ft_game()
        edge_key = edge_of_kind(game, 'victory_point')
        ends = game.edges[edge_key].neighbors['vertices']

        # A ship one side away with a free end, and a settlement to leave from,
        # so the move is legal and lands on the marked edge.
        give_building(game, 'Alice', ends[0])
        neighbour = next(
            other for other in game.vertices[ends[0]].neighbors['edges']
            if other != edge_key and game.is_sea_edge(other)
        )
        game.edges[neighbour].ship = {'player': 'Alice', 'built_turn': -1}
        game.get_player('Alice').ships.append(neighbour)
        vp_before = game.victory_points_for('Alice')

        result = game.move_ship('Alice', neighbour, edge_key)

        assert result['success'], result
        assert result['gift'] == {'gift': 'victory_point', 'victory_points': 1}
        assert game.victory_points_for('Alice') == vp_before + 1


class TestTheBarrenIslandRestrictions:
    """The small islands exist only to carry the gifts: nothing may be built on
    them and the robber may not move to them."""

    def test_a_settlement_on_a_barren_island_is_refused(self):
        game = ft_game()
        barren = barren_hexes(game)[0]
        vertex_key = next(
            key for key, vertex in game.vertices.items()
            if barren in vertex.neighbors['hexes']
        )
        refusal = game.barren_island_build_refusal(
            game.vertices[vertex_key].neighbors['hexes']
        )
        assert refusal is not None
        assert refusal['code'] == 'BARREN_ISLAND'

    def test_the_robber_may_not_move_to_a_barren_island(self):
        game = ft_game()
        barren = barren_hexes(game)[0]
        assert game.robber_is_allowed(barren) is False
        code, _ = game.robber_refusal(barren)
        assert code == 'BARREN_ISLAND'


class TestThePreset:
    def test_it_turns_on_the_gift_rules_and_ends_at_thirteen(self):
        """A rulebook pin: The Forgotten Tribe claims gifts by ship, bans
        building and the robber on the barren islands, and ends at 13."""
        chosen = rules_module.preset_rules('forgotten_tribe')
        assert chosen is not None
        assert chosen['victory_target'] == 13
        assert chosen['coast_gifts'] is True
        assert chosen['no_build_barren_islands'] is True
        assert chosen['robber_avoids_barren_islands'] is True
        assert chosen['ships'] is True
        assert chosen['pirate'] is True
