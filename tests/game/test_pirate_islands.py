"""The Seafarers scenario "The Pirate Islands": the fleet, warships and fortresses.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 7 "The Pirate Islands"
(pp. 20-22). A neutral pirate fleet circles the two central desert islands
clockwise, sailing the lower of the two dice after every roll and raiding any
coast it lands beside; players convert ships into warships by revealing Knight
cards, and win by recapturing their own-colour fortress while holding 10 points.
There is no robber, no Longest Trade Route and no Largest Army (p. 20).

What is worth pinning is what a player would notice: the fleet on the generated
board (its start and track read off the real hexes, the four fortresses off the
real corners), that it sails exactly the lower die, that a coast it lands beside
is robbed of a card plus one per city, that a stronger coast repels it for a card
of choice, that a Knight card turns a ship into a warship, and that a 7 moves no
robber and no line or army award is handed out.
"""

import random

from game import map_store, maps
from game import rules as rules_module
from game.game import Game
from seafarers_board import give_building


def pirate_game(players=('Alice', 'Bob', 'Carol', 'Dave'), seed=7, **overrides):
    """A Pirate Islands game on the built-in board, rules from the preset."""
    defn = maps.parse_map(map_store.read_map('pirate-islands'))
    chosen = dict(rules_module.preset_rules('pirate_islands'))
    chosen['turn_order'] = 'lobby'
    chosen['board_layout'] = 'custom'
    chosen['board_map'] = 'pirate-islands'
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


def _coastal_vertex_of(game, hex_key):
    """An intersection touching this hex, for standing a raid target on."""
    for vertex_key in sorted(game.vertices):
        if hex_key in game.vertices[vertex_key].neighbors['hexes']:
            return vertex_key
    raise AssertionError(f'no intersection touches {hex_key}')


def _landable_track_hex(game):
    """A track hex bordering land, and where to sit the fleet so it lands there.

    The deep-sea stretch of the track has no coastal intersection to raid, so a
    raid test needs a track hex with a settleable corner. Returns (start_index,
    hex, vertex) so the caller can seat the fleet two hops short and roll a 2.
    """
    for landing, hex_key in enumerate(game.pirate_fleet_track):
        for vertex_key in game.hex_corner_keys(hex_key):
            vertex = game.vertices.get(vertex_key)
            # A coastal corner: it exists on the board and stands on land.
            if vertex is not None and vertex.neighbors['hexes']:
                start = (landing - 2) % len(game.pirate_fleet_track)
                return start, hex_key, vertex_key
    raise AssertionError('no track hex has a settleable coast on this board')


class TestBoard:
    def test_four_fortresses_and_the_fleet_start_are_on_the_generated_board(self):
        """The map's fleet and fortresses land on the board the engine deals.

        The literal in the map file (track hexes, fortress corners) is asserted
        against the generated board, never against a second copy of itself.
        """
        game = pirate_game()

        forts = game.pirate_fortresses
        assert len(forts) == 4
        # Handed to the four players in seat order.
        assert sorted(f['owner'] for f in forts.values()) == \
            ['Alice', 'Bob', 'Carol', 'Dave']
        for vertex_key, fort in forts.items():
            assert vertex_key in game.vertices
            assert fort['chits'] == 3 and fort['captured'] is False
            # Each fortress corner sits on a producing western island, not open sea.
            land = [h for h in game.vertices[vertex_key].neighbors['hexes']
                    if game.hexes[h].type not in ('ocean', 'desert')]
            assert land, f'fortress {vertex_key} is not on a producing island'

        start = game.pirate_fleet_hex()
        assert start == game.pirate_fleet_track[0]
        assert len(game.pirate_fleet_track) == 8
        # The whole track is open water — the fleet never sails onto land.
        assert all(game.hexes[h].type == 'ocean' for h in game.pirate_fleet_track)


class TestFleetMovement:
    def test_the_fleet_sails_the_lower_of_the_two_dice(self):
        game = _playing(pirate_game())
        assert game.pirate_fleet_index == 0

        game.pending_dice = (5, 2)  # lower die is 2
        result = game.roll_dice('Alice')

        assert game.pirate_fleet_index == 2
        assert game.pirate_fleet_hex() == game.pirate_fleet_track[2]
        assert result['pirate_fleet']['steps'] == 2
        assert result['pirate_fleet']['hex'] == game.pirate_fleet_track[2]

    def test_the_fleet_wraps_around_the_end_of_its_track(self):
        game = _playing(pirate_game())
        game.pirate_fleet_index = 6

        game.pending_dice = (4, 5)  # lower die is 4; 6 + 4 = 10 -> 2 (mod 8)
        game.roll_dice('Alice')

        assert game.pirate_fleet_index == 2

    def test_equal_dice_move_the_fleet_that_many_hexes(self):
        game = _playing(pirate_game())

        game.pending_dice = (4, 4)
        game.roll_dice('Alice')

        assert game.pirate_fleet_index == 4


class TestFleetRaid:
    def test_the_fleet_robs_a_coast_it_lands_beside(self):
        game = _playing(pirate_game())
        start, _landed, vertex = _landable_track_hex(game)
        game.pirate_fleet_index = start
        give_building(game, 'Alice', vertex)
        alice = game.get_player('Alice')
        alice.resources = {'wood': 3, 'brick': 1}

        game.pending_dice = (2, 6)  # lower die 2; Alice has no warships -> raided
        result = game.roll_dice('Alice')

        attacks = {a['player']: a for a in result['pirate_fleet']['attacks']}
        assert attacks['Alice']['outcome'] == 'raided'
        # One card lost (one settlement, no cities): 1 + 0.
        assert sum(attacks['Alice']['lost'].values()) == 1
        assert sum(alice.resources.values()) == 3

    def test_the_raid_takes_one_card_per_city_as_well(self):
        game = _playing(pirate_game())
        start, _landed, vertex = _landable_track_hex(game)
        game.pirate_fleet_index = start
        give_building(game, 'Alice', vertex, 'city')
        alice = game.get_player('Alice')
        alice.resources = {'wood': 2, 'brick': 2, 'sheep': 2}

        game.pending_dice = (2, 6)
        game.roll_dice('Alice')

        # 1 + one city = two cards drawn from the hand.
        assert sum(alice.resources.values()) == 4

    def test_a_stronger_coast_repels_the_fleet_for_a_card_of_choice(self):
        game = _playing(pirate_game())
        start, _landed, vertex = _landable_track_hex(game)
        game.pirate_fleet_index = start
        give_building(game, 'Alice', vertex)
        game.player_warships['Alice'] = 3  # stronger than a pirate strength of 2

        game.pending_dice = (2, 6)
        result = game.roll_dice('Alice')

        attack = next(a for a in result['pirate_fleet']['attacks']
                      if a['player'] == 'Alice')
        assert attack['outcome'] == 'repelled'
        pending = game.pending_choice_for('Alice')
        assert pending is not None and pending['kind'] == 'pirate_repel_reward'

        game.resolve_choice('Alice', 'pirate_repel_reward', 'wheat')
        assert game.get_player('Alice').resources['wheat'] == 1

    def test_an_equal_coast_neither_loses_nor_gains(self):
        game = _playing(pirate_game())
        start, _landed, vertex = _landable_track_hex(game)
        game.pirate_fleet_index = start
        give_building(game, 'Alice', vertex)
        game.player_warships['Alice'] = 2  # equal to the pirate strength of 2
        alice = game.get_player('Alice')
        alice.resources = {'wood': 2}

        game.pending_dice = (2, 6)
        result = game.roll_dice('Alice')

        attack = next(a for a in result['pirate_fleet']['attacks']
                      if a['player'] == 'Alice')
        assert attack['outcome'] == 'tie'
        assert alice.resources == {'wood': 2}
        assert game.pending_choice_for('Alice') is None


class TestWarships:
    def test_revealing_a_knight_turns_a_ship_into_a_warship(self):
        game = _playing(pirate_game())
        alice = game.get_player('Alice')
        alice.ships = ['0,-1,1', '1,-1,0']
        alice.dev_cards['knight']['count'] = 1

        result = game.build_warship('Alice')

        assert result['success'] is True
        assert result['warships'] == 1
        assert game.player_warships['Alice'] == 1
        assert alice.dev_cards['knight']['count'] == 0

    def test_a_warship_needs_a_knight_to_reveal(self):
        game = _playing(pirate_game())
        game.get_player('Alice').ships = ['0,-1,1']

        result = game.build_warship('Alice')

        assert result['success'] is False
        assert game.player_warships.get('Alice', 0) == 0

    def test_a_warship_needs_a_plain_ship_to_convert(self):
        game = _playing(pirate_game())
        alice = game.get_player('Alice')
        alice.ships = ['0,-1,1']
        alice.dev_cards['knight']['count'] = 2
        # The one ship is already a warship.
        game.player_warships['Alice'] = 1

        result = game.build_warship('Alice')

        assert result['success'] is False
        assert result['code'] == 'NO_SHIP_TO_CONVERT'
        assert game.player_warships['Alice'] == 1


class FixedDie:
    """An RNG whose ``randint`` always returns a scripted die face.

    The fortress roll is the one place combat turns on a die, so pinning it lets
    a test drive the win and the loss branches deterministically. Everything else
    the engine asks the RNG for delegates to a real seeded generator.
    """

    def __init__(self, value, base):
        self.value = value
        self.base = base

    def randint(self, a, b):
        return self.value

    def __getattr__(self, name):
        return getattr(self.base, name)


def _route_to_own_fortress(game, player_name):
    """Sit a ship on a side of this player's fortress so its route has reached it."""
    vertex_key, _fort = game.own_fortress(player_name)
    edge_key = sorted(game.vertices[vertex_key].neighbors['edges'])[0]
    game.get_player(player_name).ships.append(edge_key)
    return vertex_key


class TestFortressCombat:
    def test_more_warships_than_the_roll_strips_a_chit(self):
        game = _playing(pirate_game())
        _route_to_own_fortress(game, 'Alice')
        game.player_warships['Alice'] = 4
        game.rng = FixedDie(2, game.rng)  # pirate strength 2 < 4 warships

        result = game.attack_pirate_fortress('Alice')

        assert result['outcome'] == 'won'
        assert result['chits'] == 2
        _vertex, fort = game.own_fortress('Alice')
        assert fort['chits'] == 2 and fort['captured'] is False

    def test_fewer_warships_than_the_roll_costs_two_warships(self):
        game = _playing(pirate_game())
        _route_to_own_fortress(game, 'Alice')
        game.player_warships['Alice'] = 3
        game.rng = FixedDie(5, game.rng)  # pirate strength 5 > 3 warships

        result = game.attack_pirate_fortress('Alice')

        assert result['outcome'] == 'lost'
        assert result['lost_warships'] == 2
        assert game.player_warships['Alice'] == 1
        _vertex, fort = game.own_fortress('Alice')
        assert fort['chits'] == 3  # the fortress is untouched

    def test_an_equal_roll_costs_one_warship(self):
        game = _playing(pirate_game())
        _route_to_own_fortress(game, 'Alice')
        game.player_warships['Alice'] = 3
        game.rng = FixedDie(3, game.rng)  # a tie at 3

        result = game.attack_pirate_fortress('Alice')

        assert result['outcome'] == 'tie'
        assert game.player_warships['Alice'] == 2

    def test_an_attack_needs_the_route_to_have_reached_the_fortress(self):
        game = _playing(pirate_game())
        game.player_warships['Alice'] = 4

        result = game.attack_pirate_fortress('Alice')

        assert result['success'] is False
        assert result['code'] == 'ROUTE_NOT_REACHED'

    def test_a_fortress_may_be_attacked_only_once_a_turn(self):
        game = _playing(pirate_game())
        _route_to_own_fortress(game, 'Alice')
        game.player_warships['Alice'] = 4
        game.rng = FixedDie(2, game.rng)

        first = game.attack_pirate_fortress('Alice')
        second = game.attack_pirate_fortress('Alice')

        assert first['success'] is True
        assert second['success'] is False
        assert second['code'] == 'ALREADY_ATTACKED'


class TestRecaptureAndVictory:
    def test_clearing_the_last_chit_recaptures_the_settlement(self):
        game = _playing(pirate_game())
        vertex_key = _route_to_own_fortress(game, 'Alice')
        _vertex, fort = game.own_fortress('Alice')
        fort['chits'] = 1
        game.player_warships['Alice'] = 4
        game.rng = FixedDie(1, game.rng)

        result = game.attack_pirate_fortress('Alice')

        assert result['captured'] is True
        assert fort['captured'] is True
        # The corner is now Alice's own settlement — scoring and on the board.
        assert game.vertices[vertex_key].building == \
            {'type': 'settlement', 'player': 'Alice'}
        assert vertex_key in game.get_player('Alice').settlements

    def test_recapture_with_ten_points_wins(self):
        game = _playing(pirate_game())
        _route_to_own_fortress(game, 'Alice')
        _vertex, fort = game.own_fortress('Alice')
        fort['chits'] = 1
        game.player_warships['Alice'] = 4
        game.rng = FixedDie(1, game.rng)
        # Nine points already; the recaptured settlement is the tenth.
        game.get_player('Alice').victory_points = 9

        result = game.attack_pirate_fortress('Alice')

        assert result['captured'] is True
        assert result['won'] is True
        assert game.game_state == 'finished'

    def test_recapture_without_ten_points_is_not_a_win(self):
        game = _playing(pirate_game())
        _route_to_own_fortress(game, 'Alice')
        _vertex, fort = game.own_fortress('Alice')
        fort['chits'] = 1
        game.player_warships['Alice'] = 4
        game.rng = FixedDie(1, game.rng)

        result = game.attack_pirate_fortress('Alice')

        assert result['captured'] is True
        assert result['won'] is False
        assert game.game_state != 'finished'

    def test_ten_points_without_recapture_is_not_a_win(self):
        game = _playing(pirate_game())
        alice = game.get_player('Alice')
        alice.victory_points = 12  # well past the target

        # Nobody has recaptured their fortress, so the threshold win is gated out.
        assert game.claim_victory('Alice') is None
        assert game.game_state != 'finished'


class TestNoRobberNoAwards:
    def test_a_seven_moves_no_robber(self):
        game = _playing(pirate_game())

        game.pending_dice = (3, 4)  # a 7
        game.roll_dice('Alice')

        assert game.must_move_robber is False

    def test_the_scenario_hands_out_no_longest_road_or_largest_army(self):
        game = _playing(pirate_game())
        alice = game.get_player('Alice')
        alice.knights_played = 5

        game.update_largest_army()
        game.update_longest_road()

        assert game.largest_army_holder is None
        assert game.longest_road_holder is None
        # No settlements, and neither award: nothing scores.
        assert game.victory_points_for('Alice') == 0
        assert game.rules['longest_road_card'] is False
        assert game.rules['largest_army_card'] is False
