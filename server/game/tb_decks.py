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
