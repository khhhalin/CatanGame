"""Cotton: a sixth resource that exists only where a map deals it.

`cotton` is registered as a terrain and a resource (game/tiles.py, game/resources.py,
game/validation.py) so a custom map can place cotton hexes with number tokens. The
proof this batch exists for is that one new resource flows through every path a
resource travels — production, the bank, a trade, a discard and a monopoly — with
no path special-cased for it, and that a standard board is left exactly as it was.

Every assertion here is against the live engine: a real payout onto a real hand, a
real bank, a real discard. None copies a literal the code also holds.

A player would notice each break: a cotton hex that paid nothing, a bank with no
cotton pile for a cotton roll to draw from, a cotton card that could not be traded,
discarded or monopolised — or, on the other side, a standard game that suddenly
grew a cotton pile it should never have.
"""

import random

from game import board as board_module
from game import maps
from game import rules as rules_module
from game.game import Game

# A small island: seven land hexes, one of them cotton, the rest base resources,
# and one desert so the robber has somewhere to start. Every producing hex takes
# a token, so seven tokens for the six producers plus none for the desert.
MAINLAND = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))
COTTON_MAP = {
    'map_version': 2,
    'id': 'cotton-map',
    'name': 'Cotton Map',
    'frame': {'radius': 3},
    'regions': [
        {
            'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND,
            'pool': {
                'mode': 'shuffled',
                'terrain': {'cotton': 1, 'wood': 2, 'wheat': 2, 'sheep': 1, 'desert': 1},
                'numbers': [3, 4, 5, 6, 9, 10],
            },
        },
        {
            'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
            'pool': {'mode': 'shuffled',
                     'terrain': {'sea': len(maps.frame_hex_keys(3)) - len(MAINLAND)},
                     'numbers': []},
        },
    ],
    'harbours': {'mode': 'bag', 'types': {}},
}


def cotton_game(seed=5) -> Game:
    rules = dict(rules_module.defaults())
    rules['board_layout'] = 'custom'
    rules['board_map'] = COTTON_MAP['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(seed), rules=rules,
                map_definition=maps.parse_map(COTTON_MAP))
    game.start()
    game.game_phase = 'playing'
    return game


def cotton_hex_key(game) -> str:
    """The one cotton hex the map dealt."""
    return next(key for key, hex_obj in game.hexes.items() if hex_obj.type == 'cotton')


def vertex_touching(game, hex_key) -> str:
    """A board vertex that borders the given hex."""
    return next(
        key for key, vertex in game.vertices.items()
        if hex_key in vertex.neighbors.get('hexes', [])
    )


def test_a_cotton_hex_pays_cotton_when_its_number_is_rolled():
    """A settlement on a cotton hex collects a cotton card on that hex's roll —
    the same path a wood hex pays wood, with cotton never named in it."""
    game = cotton_game()
    cotton_key = cotton_hex_key(game)
    number = game.hexes[cotton_key].number

    vertex = vertex_touching(game, cotton_key)
    game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}

    before = game.get_player('Alice').resources.get('cotton', 0)
    paid = game.distribute_resources(number)

    assert game.get_player('Alice').resources.get('cotton', 0) == before + 1, (
        'a settlement on a cotton hex was paid no cotton on its roll'
    )
    assert paid.get('Alice', {}).get('cotton') == 1


def test_the_bank_stocks_cotton_only_on_a_cotton_board():
    """The cotton board opens a cotton pile so a roll and a trade have somewhere
    to draw from; a standard board does not, because no hex there can ever deal
    it — a cotton pile no roll fills would be a pile a player would notice."""
    cotton = cotton_game()
    assert 'cotton' in cotton.bank.resources
    assert cotton.bank.resources['cotton'] == cotton.bank.resource_limit

    standard = Game(['Alice', 'Bob'], [], rng=random.Random(1))
    assert 'cotton' not in standard.bank.resources
    assert set(standard.bank.resources) == {'wood', 'brick', 'sheep', 'wheat', 'ore'}


def test_a_standard_game_deals_and_shows_exactly_the_base_five():
    """Base play is untouched: a standard board produces only the five, its bank
    holds only the five, and the resource list the client renders from is the five
    in their usual order — cotton exists in the type system but appears nowhere."""
    standard = Game(['Alice', 'Bob'], [], rng=random.Random(2))
    assert standard.producible_resources() == {'wood', 'brick', 'sheep', 'wheat', 'ore'}
    assert standard.in_play_resource_types() == ['wood', 'brick', 'sheep', 'wheat', 'ore']
    dealt = {t for t in (game_hex.type for game_hex in standard.hexes.values())
             if t not in ('ocean', 'desert')}
    assert dealt == {'wood', 'brick', 'sheep', 'wheat', 'ore'}


def test_cotton_joins_the_in_play_resource_list_after_the_five():
    """A cotton board sends the client the five and then cotton, so the hand, the
    bank and the pickers all render cotton where the map dealt it."""
    game = cotton_game()
    assert game.in_play_resource_types() == ['wood', 'brick', 'sheep', 'wheat', 'ore', 'cotton']


def test_cotton_can_be_traded_to_the_bank():
    """A player can offer cotton in a trade: four cotton buys one wood at the 4:1
    bank rate, the cotton going back to the bank and the wood coming out."""
    game = cotton_game()
    game.current_player_index = next(
        i for i, p in enumerate(game.players) if p.name == 'Alice'
    )
    game.set_dice_rolled()
    alice = game.get_player('Alice')
    alice.resources['cotton'] = 4
    # Draw the cotton pile down first, so the four coming back are visible rather
    # than clamped away against a pile already at the limit.
    game.bank.take('cotton', 10)
    cotton_before = game.bank.resources['cotton']
    wood_before = alice.resources.get('wood', 0)

    result = game.propose_trade('Alice', {'cotton': 4}, {'wood': 1})

    assert result['success'] and result['kind'] == 'bank', result
    assert alice.resources['cotton'] == 0
    assert alice.resources.get('wood', 0) == wood_before + 1
    assert game.bank.resources['cotton'] == cotton_before + 4


def test_cotton_counts_toward_a_discard_and_can_be_handed_back():
    """Cotton counts toward the hand limit that a 7 enforces, and a discard may
    name it: a hand pushed over the limit by cotton must, and can, hand cotton
    back to the bank."""
    game = cotton_game()
    alice = game.get_player('Alice')
    # Eight cards, over the default limit of seven, and cotton is what tips it.
    alice.resources.update({'wood': 4, 'wheat': 3, 'cotton': 1})

    game.check_discard_required()
    assert game.players_needing_discard.get('Alice') == 4, (
        'cotton did not count toward the hand that forced a discard'
    )

    # Draw the pile down so the returned cotton is visible, not clamped at limit.
    game.bank.take('cotton', 5)
    cotton_in_bank = game.bank.resources['cotton']
    assert game.discard('Alice', {'wood': 2, 'wheat': 1, 'cotton': 1})['success']
    assert alice.resources['cotton'] == 0
    assert game.bank.resources['cotton'] == cotton_in_bank + 1


def test_cotton_can_be_taken_by_a_monopoly():
    """A Monopoly declared on cotton sweeps every other player's cotton — the
    monopoly path reaches cotton with no mention of it, because the board stocks
    a cotton pile and the type system knows the word."""
    game = cotton_game()
    game.get_player('Alice').resources['cotton'] = 3
    game.pending_monopoly = 'Bob'

    result = game.use_monopoly('Bob', 'cotton')

    assert result['success']
    assert result['stolen_count'] == 3
    assert game.get_player('Bob').resources.get('cotton', 0) == 3
    assert game.get_player('Alice').resources.get('cotton', 0) == 0
