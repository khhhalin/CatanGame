"""The Barbarian Attack development deck: its 26 cards and how they are drawn.

Barbarian Attack replaces the base development deck entirely with 26 cards — 14
Knighthood, 4 Swift Knight, 4 Treason and 4 Intrigue (expansions.md 617,
633-642). Each card is revealed and resolved the moment it is bought, then
discarded; when the stack runs out the discard pile is reshuffled into a fresh
stack.

The card texts live here as plain data so the composition can be checked against
`expansions.md` at a glance and so the buy path and the client can both key on
the same ids rather than hard-coding a switch over card names. Resolving a card
is engine work and lives in `game/barbarian_attack.py`; what a card *is* belongs
here with the card.

The deck itself is kept on the game's Traders & Barbarians state container
(`game/tb.py`) so it persists and reshuffles deterministically from the injected
RNG. `dev_deck_in_play` already returns False when `barbarian_attack_deck` is on,
so the base `buy_dev_card` path is closed and this deck is the only one dealt.
"""

import random

KNIGHTHOOD = "knighthood"
SWIFT_KNIGHT = "swift_knight"
TREASON = "treason"
INTRIGUE = "intrigue"

# The published composition (expansions.md 617). A miscounted deck does not
# crash — it silently skews every game — so `deck_counts` exists for a test to
# pin the 26-card split, and `_check_deck_size` guards it at import time.
BARBARIAN_ATTACK_CARDS = [
    {
        "id": KNIGHTHOOD,
        "name": "Knighthood",
        "count": 14,
        "summary": (
            "Place one of your knights on one of the six paths adjacent to the "
            "castle hex that is not already occupied by a knight."
        ),
    },
    {
        "id": SWIFT_KNIGHT,
        "name": "Swift Knight",
        "count": 4,
        "summary": (
            "Place one of your knights on any path on the board that is not "
            "already occupied by a knight."
        ),
    },
    {
        "id": TREASON,
        "name": "Treason",
        "count": 4,
        "summary": (
            "Take 2 gold, remove 2 barbarians from 2 different coastal hexes and "
            "place them on 2 other unconquered coastal hexes."
        ),
    },
    {
        "id": INTRIGUE,
        "name": "Intrigue",
        "count": 4,
        "summary": (
            "Remove 1 barbarian from a coastal hex of your choice and add it to "
            "your own prisoners. With no barbarian on any coast, discard and "
            "draw again."
        ),
    },
]

CARDS_BY_ID = {card["id"]: card for card in BARBARIAN_ATTACK_CARDS}

DECK_SIZE = 26


def deck_counts() -> dict:
    """Card id -> how many of it the deck holds, for pinning the composition."""
    return {card["id"]: card["count"] for card in BARBARIAN_ATTACK_CARDS}


def build_deck(rng: random.Random) -> list:
    """A freshly shuffled stack of card ids, each repeated by its count.

    The RNG is injected rather than taken from the module so a game replays
    exactly from its seed — an unreproducible draw order cannot be debugged.
    """
    deck = [
        card["id"]
        for card in BARBARIAN_ATTACK_CARDS
        for _ in range(card["count"])
    ]
    rng.shuffle(deck)
    return deck


def _check_deck_size() -> None:
    """Guard the published composition at import time."""
    total = sum(card["count"] for card in BARBARIAN_ATTACK_CARDS)
    if total != DECK_SIZE:
        raise AssertionError(
            f"Barbarian Attack deck has {total} cards, expected {DECK_SIZE}"
        )
    ids = [card["id"] for card in BARBARIAN_ATTACK_CARDS]
    if len(ids) != len(set(ids)):
        raise AssertionError("Barbarian Attack card ids must be unique")


_check_deck_size()


# --- The Traders & Barbarians main-scenario deck ---------------------------
# The wagon scenario replaces the base development deck with its own, exactly as
# Barbarian Attack does. expansions.md 691, 745-748 enumerates it as 15 Knight,
# 3 Road Building, 3 Swift Journey and 1 each of Toolmaking, Glassmaking and
# Quarry — twenty-four cards. (Some summaries call this a "26-card" deck by
# analogy with the Barbarian Attack deck; the enumerated card list, which is what
# is dealt, sums to 24, and `_check_trade_deck_size` guards that the ids and
# their counts stay consistent so the literal cannot silently drift.)
#
# The card texts live here as data so the buy path, the resolution in
# game/wagons.py and the client all key on the same ids. Resolving a card is
# engine work (game/wagons.py, game/path_barbarians.py); what a card *is* belongs
# here with the card.
TRADE_KNIGHT = "trade_knight"
TRADE_ROAD_BUILDING = "trade_road_building"
SWIFT_JOURNEY = "swift_journey"
TOOLMAKING = "toolmaking"
GLASSMAKING = "glassmaking"
QUARRY = "quarry_card"

# The three single cards that are simply worth a victory point, revealed only on
# the turn they win the game — read where the deck is resolved and where scoring
# counts held cards.
TRADE_VP_CARDS = (TOOLMAKING, GLASSMAKING, QUARRY)

TRADE_CARDS = [
    {
        "id": TRADE_KNIGHT,
        "name": "Knight",
        "count": 15,
        "summary": (
            "Move one barbarian to another path or road. If you place it on a "
            "road you draw one resource card from that road's owner."
        ),
    },
    {
        "id": TRADE_ROAD_BUILDING,
        "name": "Road Building",
        "count": 3,
        "summary": "Place 2 new roads as if you had just built them normally.",
    },
    {
        "id": SWIFT_JOURNEY,
        "name": "Swift Journey",
        "count": 3,
        "summary": (
            "Move your wagon a second time this turn, after you have already "
            "moved it in the regular manner."
        ),
    },
    {
        "id": TOOLMAKING,
        "name": "Toolmaking",
        "count": 1,
        "summary": "Worth 1 victory point, revealed only if it wins you the game.",
    },
    {
        "id": GLASSMAKING,
        "name": "Glassmaking",
        "count": 1,
        "summary": "Worth 1 victory point, revealed only if it wins you the game.",
    },
    {
        "id": QUARRY,
        "name": "Quarry",
        "count": 1,
        "summary": "Worth 1 victory point, revealed only if it wins you the game.",
    },
]

TRADE_CARDS_BY_ID = {card["id"]: card for card in TRADE_CARDS}

TRADE_DECK_SIZE = 24


def trade_deck_counts() -> dict:
    """Card id -> how many the wagon deck holds, for pinning the composition."""
    return {card["id"]: card["count"] for card in TRADE_CARDS}


def build_trade_deck(rng: random.Random) -> list:
    """A freshly shuffled wagon deck: each id repeated by its count.

    The RNG is injected so a game replays exactly from its seed.
    """
    deck = [
        card["id"]
        for card in TRADE_CARDS
        for _ in range(card["count"])
    ]
    rng.shuffle(deck)
    return deck


def _check_trade_deck_size() -> None:
    """Guard the enumerated wagon-deck composition at import time."""
    total = sum(card["count"] for card in TRADE_CARDS)
    if total != TRADE_DECK_SIZE:
        raise AssertionError(
            f"Trade wagon deck has {total} cards, expected {TRADE_DECK_SIZE}"
        )
    ids = [card["id"] for card in TRADE_CARDS]
    if len(ids) != len(set(ids)):
        raise AssertionError("Trade wagon card ids must be unique")


_check_trade_deck_size()


# --- The commodity tokens -------------------------------------------------
# The three trade hexes each hold a face-down stack of commodity tokens
# (expansions.md 683-686). A token's front shows a commodity, which names the
# trade hex it must be delivered to; you draw a token from the hex you are
# standing on. The castle exports tools and sand; the quarry exports marble and
# sand; the glassworks exports glass and tools (683-686). 36 tokens split three
# ways, twelve per hex — expansions.md gives no finer split, so each hex's two
# exports are dealt six and six. What each commodity is *delivered* to:
#   glass -> castle, marble -> castle, tools -> quarry, sand -> glassworks (709).
GLASS = "glass"
MARBLE = "marble"
SAND = "sand"
TOOLS = "tools"

# Which trade hex (by terrain type) each commodity is delivered to.
DELIVERY_TARGET = {
    GLASS: "castle",
    MARBLE: "castle",
    TOOLS: "quarry",
    SAND: "glassworks",
}

# What each trade hex's face-down stack is built from — its two exports, six each.
TRADE_HEX_EXPORTS = {
    "castle": (TOOLS, SAND),
    "quarry": (MARBLE, SAND),
    "glassworks": (GLASS, TOOLS),
}

TOKENS_PER_EXPORT = 6


def build_commodity_stack(hex_type: str, rng: random.Random) -> list:
    """A shuffled face-down stack for one trade hex — its two exports, six each."""
    exports = TRADE_HEX_EXPORTS.get(hex_type)
    if exports is None:
        return []
    stack = [commodity for commodity in exports for _ in range(TOKENS_PER_EXPORT)]
    rng.shuffle(stack)
    return stack
