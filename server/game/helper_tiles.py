"""The 12 Helpers of Catan, as data rather than code.

CATAN - The Helpers is a scenario of 12 double-sided "helper" tiles, each a
named character with a one-shot activated advantage. A player always holds one
tile; using its advantage is allowed once on their own turn (a couple of tiles
are exceptions and fire on any player's roll). Immediately after using it the
player either *exchanges* the tile for a fresh one from the display, or *flips*
it from its sun side to its moon side to use once more on a later turn; a
moon-side tile can only be exchanged after use. No tile ever changes victory
points directly (Helpers_Rules.pdf, "Using The Helpers", p. 4).

The tile texts live here as plain dicts so the deck composition can be read at a
glance and so the engine's activation path, the socket validation and the client
panel all key on the same fields instead of each hard-coding a switch over tile
ids. Resolving a tile belongs in the engine (game/helpers.py); *what* a tile
needs before it can be resolved is a property of the tile and belongs with it.

`when` - the timing icon in the sun/moon corner (Helpers_Rules.pdf p. 4):
    "turn"              once during your own turn
    "after_production"  immediately after any player's production roll
    "on_seven"          the moment any player rolls a 7 (a forced reaction)

`rule` - the individual catalogue rule that gates the tile. Each is switchable
on its own and is genuinely read by the engine (the draw pile is built from the
tiles whose rule is on, and `HELPER_TILE_RULE` gates every activation), so there
is no branch anywhere on the scenario name.

`needs` - the extra input the player supplies to activate, checked by the socket
handler and the engine. `[]` means the tile resolves from board state alone.
Each entry is one of the vocabulary words below.
"""

# Extra-input vocabulary an activation can ask for. The handler validates each
# against this list; the engine re-checks against real state.
NEEDS_RESOURCE = "resource"          # one of the five resource types
NEEDS_PLAYER = "player"              # another player at the table
NEEDS_EDGE = "edge"                  # a road edge on the board
NEEDS_DEV_CARD = "dev_card"          # one of the player's unplayed dev-card types
NEEDS_BUILD = "build"               # "settlement" or "city"
NEEDS_VERTEX = "vertex"              # an intersection to build on

# Timing icons.
WHEN_TURN = "turn"
WHEN_AFTER_PRODUCTION = "after_production"
WHEN_ON_SEVEN = "on_seven"


HELPER_TILES = [
    {
        "id": "asla",
        "number": 1,
        "name": "Asla",
        "title": "Forced Trade",
        "when": WHEN_TURN,
        "rule": "helper_forced_trade",
        "needs": [NEEDS_RESOURCE, NEEDS_PLAYER],
        "summary": (
            "Choose 1 resource type and request it from 1 or 2 players, one "
            "after the other. Each who holds it must give you 1; for each you "
            "receive, give them back 1 resource of your choice."
        ),
        "source": "Helpers_Rules.pdf, 'The Helpers in Detail', Forced Trade (Asla), p. 6",
    },
    {
        "id": "yngvi",
        "number": 2,
        "name": "Yngvi",
        "title": "Makeshift Road Building",
        "when": WHEN_TURN,
        "rule": "helper_makeshift_road",
        "needs": [NEEDS_EDGE, NEEDS_RESOURCE],
        "summary": (
            "When you build a road, you may substitute 1 lumber or 1 brick with "
            "any 1 other resource of your choice."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Makeshift Road Building "
            "(Yngvi), p. 6"
        ),
    },
    {
        "id": "hilda",
        "number": 3,
        "name": "Hilda",
        "title": "Resource Compensation",
        "when": WHEN_AFTER_PRODUCTION,
        "rule": "helper_resource_compensation",
        "needs": [NEEDS_RESOURCE],
        "summary": (
            "Immediately after any production roll that is not a 7, if you "
            "received no resources, take any 1 resource card of your choice from "
            "the supply."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Resource Compensation "
            "(Hilda), p. 8"
        ),
    },
    {
        "id": "hogni",
        "number": 4,
        "name": "Hogni",
        "title": "Move a Road",
        "when": WHEN_TURN,
        "rule": "helper_move_road",
        "needs": [NEEDS_EDGE, NEEDS_EDGE],
        "summary": (
            "Remove 1 of your end roads (a road with one end connecting to none "
            "of your own pieces) and place it in another location, following "
            "normal placement rules."
        ),
        "source": "Helpers_Rules.pdf, 'The Helpers in Detail', Move a Road (Hogni), p. 7",
    },
    {
        "id": "thorolf",
        "number": 5,
        "name": "Thorolf",
        "title": "Protection from the 7",
        "when": WHEN_ON_SEVEN,
        "rule": "helper_protection_from_seven",
        "needs": [NEEDS_RESOURCE],
        "summary": (
            "When any player rolls a 7, you must use this at once: if you have "
            "more than 7 cards, keep them all instead of discarding half; if you "
            "have 7 or fewer, take any 1 resource of your choice from the supply."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Protection from the 7 "
            "(Thorolf), p. 9"
        ),
    },
    {
        "id": "diara",
        "number": 6,
        "name": "Diara",
        "title": "Development Card Choice",
        "when": WHEN_TURN,
        "rule": "helper_dev_card_choice",
        "needs": [NEEDS_RESOURCE, NEEDS_RESOURCE],
        "summary": (
            "When you buy a development card you may substitute 1 of the 3 "
            "resources with any 1 other of your choice. After paying, look at the "
            "top 3 cards, keep 1 and shuffle the other 2 back into the deck."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Development Card Choice "
            "(Diara), p. 9"
        ),
    },
    {
        "id": "ryan",
        "number": 7,
        "name": "Ryan",
        "title": "Take Card from Leader",
        "when": WHEN_AFTER_PRODUCTION,
        "rule": "helper_take_from_leader",
        "needs": [NEEDS_PLAYER, NEEDS_RESOURCE],
        "summary": (
            "After your production roll is resolved, choose 1 opponent who has "
            "more victory points than you, look at their hand and take 1 resource "
            "card of your choice."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Take Card From Leader "
            "(Ryan), p. 10"
        ),
    },
    {
        "id": "gregor",
        "number": 8,
        "name": "Gregor",
        "title": "Assign Knight to Building",
        "when": WHEN_TURN,
        "rule": "helper_knight_to_building",
        "needs": [NEEDS_BUILD, NEEDS_VERTEX],
        "summary": (
            "Discard 1 of your played knight cards to build for a reduced cost: "
            "a settlement for 1 lumber + 1 brick, or a city for 2 ore + 1 grain. "
            "The discarded knight no longer counts toward the Largest Army."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Assign Knight to "
            "Building (Gregor), p. 10"
        ),
    },
    {
        "id": "stina",
        "number": 9,
        "name": "Stina",
        "title": "2:1 Trade Frenzy",
        "when": WHEN_TURN,
        "rule": "helper_trade_frenzy",
        "needs": [NEEDS_RESOURCE, NEEDS_RESOURCE],
        "summary": (
            "Choose 1 type of resource and exchange it with the bank at 2:1 as "
            "many times as you like, all at once. This is not a 2:1 rate for the "
            "whole turn."
        ),
        "source": "Helpers_Rules.pdf, 'The Helpers in Detail', 2:1 Trade Frenzy (Stina), p. 11",
    },
    {
        "id": "digur",
        "number": 10,
        "name": "Digur",
        "title": "Chase Robber to Desert",
        "when": WHEN_TURN,
        "rule": "helper_chase_robber",
        "needs": [],
        "summary": (
            "Move the robber to the desert (before or after your production "
            "roll). You receive 1 resource of the type produced by the hex the "
            "robber left. You cannot play this if the robber is already in the "
            "desert."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Chase Robber to Desert "
            "(Digur), p. 10"
        ),
    },
    {
        "id": "kaja",
        "number": 11,
        "name": "Kaja",
        "title": "Take Robber's Resource",
        "when": WHEN_TURN,
        "rule": "helper_take_robber_resource",
        "needs": [NEEDS_RESOURCE],
        "summary": (
            "Take 1 resource card from the supply matching the terrain hex the "
            "robber currently occupies. If the robber is in the desert, take a "
            "resource of your choice."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Take Robber's Resource "
            "(Kaja), p. 11"
        ),
    },
    {
        "id": "carla",
        "number": 12,
        "name": "Carla",
        "title": "Development Card Swap",
        "when": WHEN_TURN,
        "rule": "helper_dev_card_swap",
        "needs": [NEEDS_DEV_CARD],
        "summary": (
            "Place 1 of your unplayed development cards at the bottom of the "
            "development card stack and draw 1 from the top. The drawn card "
            "cannot be played on the turn you receive it."
        ),
        "source": (
            "Helpers_Rules.pdf, 'The Helpers in Detail', Development Card Swap "
            "(Carla), p. 11"
        ),
    },
]

HELPER_TILES_BY_ID = {tile["id"]: tile for tile in HELPER_TILES}

# tile id -> the individual rule that must be on for the tile to be in the game
# and for its advantage to be activated. Read by game/helpers.py to build the
# draw pile and to gate every activation, so each ability rule is genuinely
# consulted by engine code (no branch on the scenario name).
HELPER_TILE_RULE = {tile["id"]: tile["rule"] for tile in HELPER_TILES}

# Every ability rule id, in tile order. The framework rule `helper_tiles`
# enables the subsystem; these twelve each switch one advantage.
HELPER_ABILITY_RULES = [tile["rule"] for tile in HELPER_TILES]


def tiles_in_play(rules: dict) -> list:
    """The tile ids whose ability rule is switched on, in tile-number order.

    This is the pool the starting stack and the display are drawn from. A table
    that ticks only some abilities plays with only those tiles, exactly as the
    scenario's own set-up removes the unselected helpers from the game
    (Helpers_Rules.pdf, 'Set-up', p. 3).
    """
    return [tile["id"] for tile in HELPER_TILES if rules.get(tile["rule"])]


def _check_unique() -> None:
    ids = [tile["id"] for tile in HELPER_TILES]
    if len(ids) != len(set(ids)):
        raise AssertionError("helper tile ids must be unique")
    numbers = sorted(tile["number"] for tile in HELPER_TILES)
    if numbers != list(range(1, 13)):
        raise AssertionError("helper tiles must be numbered 1-12 exactly once")


_check_unique()
