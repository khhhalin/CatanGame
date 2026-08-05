"""The 54 Cities & Knights progress cards, as data rather than code.

Cities & Knights replaces development cards entirely with three 18-card decks —
green science, yellow trade, blue politics — drawn from when the event die shows
a city gate. The card texts live here as plain dicts so the deck composition can
be checked against `expansions.md` at a glance, and so the eventual UI prompt and
the server's pending-action validation can both key on the same `needs_target`
field instead of each hard-coding a switch over card ids.

Nothing here touches game state or transport: resolving a card belongs in the
engine, but *what* a card needs before it can be resolved is a property of the
card and belongs with the card.

`needs_target` vocabulary — the extra input the player must supply for the server
to resolve the card. `None` means the card resolves from board state alone:

    None                  no extra input
    "resource"            one of the five resource types
    "commodity"           one of the three commodity types
    "resource_or_commodity"  either, chosen by the player
    "player"              another player at the table
    "two_number_tokens"   the two number tokens to swap
    "knight"              one or more knights on the board
    "road"                a road edge
    "vertex"              an intersection carrying a building
    "hex"                 a land hex
    "dice"                the two production die values (Alchemist only)
    "improvement"         which of the three improvement tracks to build on

The last three are not in the base vocabulary the rest of the engine uses; they
are here because Alchemist, Crane, and the merchant-placing cards genuinely take
input of no other shape.

Counts follow the published deck composition. `deck_counts()` exists so a test
can assert 18/18/18 — a miscounted deck does not crash, it just quietly skews the
game's odds for the rest of its life.
"""

import random

SCIENCE = "science"
TRADE = "trade"
POLITICS = "politics"

DECKS = (SCIENCE, TRADE, POLITICS)

CARDS_PER_DECK = 18

# Played before the dice are rolled, on the player's own turn, or revealed the
# moment it is drawn.
TIMING_BEFORE_ROLL = "before_roll"
TIMING_TURN = "turn"
TIMING_IMMEDIATE = "immediate"


PROGRESS_CARDS = [
    # --- Green: science -------------------------------------------------
    {
        "id": "alchemist",
        "name": "Alchemist",
        "deck": SCIENCE,
        "count": 2,
        "summary": (
            "The Alchemist card is the only card that is played before the dice "
            "are rolled, and it lets the player choose the values of the red and "
            "yellow production dice."
        ),
        "timing": TIMING_BEFORE_ROLL,
        "needs_target": "dice",
        "victory_points": 0,
    },
    {
        "id": "crane",
        "name": "Crane",
        "deck": SCIENCE,
        "count": 2,
        "summary": (
            "The Crane card lets the player build one city improvement for one "
            "commodity less than its normal cost."
        ),
        "timing": TIMING_TURN,
        "needs_target": "improvement",
        "victory_points": 0,
    },
    {
        "id": "engineer",
        "name": "Engineer",
        "deck": SCIENCE,
        "count": 1,
        "summary": (
            "The Engineer card lets the player build one city wall for free on "
            "one of their cities."
        ),
        "timing": TIMING_TURN,
        "needs_target": "vertex",
        "victory_points": 0,
    },
    {
        "id": "inventor",
        "name": "Inventor",
        "deck": SCIENCE,
        "count": 2,
        "summary": (
            "The Inventor card lets the player swap two number tokens on the "
            "board, excluding tokens showing 2, 6, 8, or 12."
        ),
        "timing": TIMING_TURN,
        "needs_target": "two_number_tokens",
        "victory_points": 0,
    },
    {
        "id": "irrigation",
        "name": "Irrigation",
        "deck": SCIENCE,
        "count": 2,
        "summary": (
            "The Irrigation card gives the player two grain for each of their "
            "settlements and cities adjacent to a field hex."
        ),
        "timing": TIMING_TURN,
        "needs_target": None,
        "victory_points": 0,
    },
    {
        "id": "medicine",
        "name": "Medicine",
        "deck": SCIENCE,
        "count": 2,
        "summary": (
            "The Medicine card lets the player upgrade a settlement into a city "
            "for two ore and one grain instead of the normal cost."
        ),
        "timing": TIMING_TURN,
        "needs_target": "vertex",
        "victory_points": 0,
    },
    {
        "id": "mining",
        "name": "Mining",
        "deck": SCIENCE,
        "count": 2,
        "summary": (
            "The Mining card gives the player two ore for each of their "
            "settlements and cities adjacent to a mountain hex."
        ),
        "timing": TIMING_TURN,
        "needs_target": None,
        "victory_points": 0,
    },
    {
        "id": "printer",
        "name": "Printer",
        "deck": SCIENCE,
        "count": 1,
        "summary": (
            "The Printer card is a science card worth 1 victory point that is "
            "revealed immediately."
        ),
        "timing": TIMING_IMMEDIATE,
        "needs_target": None,
        "victory_points": 1,
    },
    {
        "id": "road_building",
        "name": "Road Building",
        "deck": SCIENCE,
        "count": 2,
        "summary": "The Road Building card lets the player build two roads for free.",
        "timing": TIMING_TURN,
        "needs_target": "road",
        "victory_points": 0,
    },
    {
        "id": "smith",
        "name": "Smith",
        "deck": SCIENCE,
        "count": 2,
        "summary": (
            "The Smith card lets the player promote up to two of their knights "
            "one rank each for free."
        ),
        "timing": TIMING_TURN,
        "needs_target": "knight",
        "victory_points": 0,
    },
    # --- Yellow: trade --------------------------------------------------
    {
        "id": "commercial_harbor",
        "name": "Commercial Harbor",
        "deck": TRADE,
        "count": 2,
        "summary": (
            "The Commercial Harbor card forces each other player to either trade "
            "one commodity of their choice for one resource offered by the "
            "player, or decline if they hold no commodities."
        ),
        "timing": TIMING_TURN,
        "needs_target": "resource",
        "victory_points": 0,
    },
    {
        "id": "master_merchant",
        "name": "Master Merchant",
        "deck": TRADE,
        "count": 2,
        "summary": (
            "The Master Merchant card lets the player look at the hand of a "
            "player who has more victory points than they do and take two cards "
            "of their choice from it."
        ),
        "timing": TIMING_TURN,
        "needs_target": "player",
        "victory_points": 0,
    },
    {
        "id": "merchant",
        "name": "Merchant",
        "deck": TRADE,
        "count": 6,
        "summary": (
            "A player who plays a Merchant card places the merchant piece on any "
            "land hex adjacent to one of their own settlements or cities, may "
            "then trade that hex's resource type with the bank at a 2:1 rate, "
            "and scores 1 victory point for as long as they control it."
        ),
        "timing": TIMING_TURN,
        "needs_target": "hex",
        "victory_points": 0,
    },
    {
        "id": "merchant_fleet",
        "name": "Merchant Fleet",
        "deck": TRADE,
        "count": 2,
        "summary": (
            "The Merchant Fleet card lets the player trade one chosen resource "
            "or commodity at a 2:1 rate with the bank for the rest of the turn."
        ),
        "timing": TIMING_TURN,
        "needs_target": "resource_or_commodity",
        "victory_points": 0,
    },
    {
        "id": "resource_monopoly",
        "name": "Resource Monopoly",
        "deck": TRADE,
        "count": 4,
        "summary": (
            "The Resource Monopoly card forces every other player to give the "
            "playing player two cards of one named resource, or as many as they "
            "hold if they hold fewer."
        ),
        "timing": TIMING_TURN,
        "needs_target": "resource",
        "victory_points": 0,
    },
    {
        "id": "trade_monopoly",
        "name": "Trade Monopoly",
        "deck": TRADE,
        "count": 2,
        "summary": (
            "The Trade Monopoly card forces every other player to give the "
            "playing player one card of one named commodity if they hold any."
        ),
        "timing": TIMING_TURN,
        "needs_target": "commodity",
        "victory_points": 0,
    },
    # --- Blue: politics -------------------------------------------------
    {
        "id": "bishop",
        "name": "Bishop",
        "deck": POLITICS,
        "count": 2,
        "summary": (
            "The Bishop card lets the player move the robber and then steal one "
            "random card from every player with a building adjacent to the "
            "robber's new hex."
        ),
        "timing": TIMING_TURN,
        "needs_target": "hex",
        "victory_points": 0,
    },
    {
        "id": "constitution",
        "name": "Constitution",
        "deck": POLITICS,
        "count": 1,
        "summary": (
            "The Constitution card is a politics card worth 1 victory point that "
            "is revealed immediately."
        ),
        "timing": TIMING_IMMEDIATE,
        "needs_target": None,
        "victory_points": 1,
    },
    {
        "id": "deserter",
        "name": "Deserter",
        "deck": POLITICS,
        "count": 2,
        "summary": (
            "The Deserter card lets the player remove one knight of a chosen "
            "opponent and place a knight of the same rank of their own on the "
            "board for free, if they have a matching knight token available."
        ),
        "timing": TIMING_TURN,
        # The card names an *opponent*, not a knight: which of their knights
        # deserts is that opponent's own decision, and the engine asks them for
        # it once the card is played.
        "needs_target": "player",
        "victory_points": 0,
    },
    {
        "id": "diplomat",
        "name": "Diplomat",
        "deck": POLITICS,
        "count": 2,
        "summary": (
            "The Diplomat card lets the player remove any open road that does not "
            "connect at both ends to another road or building, and if the removed "
            "road is their own they may rebuild it elsewhere for free."
        ),
        "timing": TIMING_TURN,
        "needs_target": "road",
        "victory_points": 0,
    },
    {
        "id": "intrigue",
        "name": "Intrigue",
        "deck": POLITICS,
        "count": 2,
        "summary": (
            "The Intrigue card lets the player displace an opponent's knight that "
            "stands on an intersection adjacent to one of the player's own roads, "
            "without needing a stronger knight."
        ),
        "timing": TIMING_TURN,
        "needs_target": "knight",
        "victory_points": 0,
    },
    {
        "id": "saboteur",
        "name": "Saboteur",
        "deck": POLITICS,
        "count": 2,
        "summary": (
            "The Saboteur card forces every player with at least as many victory "
            "points as the playing player to discard half of their hand, rounded "
            "down."
        ),
        "timing": TIMING_TURN,
        "needs_target": None,
        "victory_points": 0,
    },
    {
        "id": "spy",
        "name": "Spy",
        "deck": POLITICS,
        "count": 3,
        "summary": (
            "The Spy card lets the player look at the progress card hand of "
            "another player and take one card from it."
        ),
        "timing": TIMING_TURN,
        "needs_target": "player",
        "victory_points": 0,
    },
    {
        "id": "warlord",
        "name": "Warlord",
        "deck": POLITICS,
        "count": 2,
        "summary": (
            "The Warlord card activates all of the playing player's inactive "
            "knights for free."
        ),
        "timing": TIMING_TURN,
        "needs_target": None,
        "victory_points": 0,
    },
    {
        "id": "wedding",
        "name": "Wedding",
        "deck": POLITICS,
        "count": 2,
        "summary": (
            "The Wedding card forces every player with more victory points than "
            "the playing player to give that player two cards of the giver's "
            "choice from their hand."
        ),
        "timing": TIMING_TURN,
        "needs_target": None,
        "victory_points": 0,
    },
]

CARDS_BY_ID = {card["id"]: card for card in PROGRESS_CARDS}

# Cards that name a target on the card and take none when they are played.
# Road Building's two roads go down afterwards through the ordinary free-road
# flow, and a Merchant Fleet's card type is asked for as a pending choice the
# engine opens and checks its own options against. It lives with the cards
# rather than in the socket handler because the client needs the same answer:
# these are played by pressing Play, with nothing picked first.
TARGET_CHOSEN_LATER = frozenset({"road_building", "merchant_fleet"})


def deck_counts() -> dict[str, int]:
    """Total cards in each deck, for asserting the 18/18/18 composition."""
    totals = dict.fromkeys(DECKS, 0)
    for card in PROGRESS_CARDS:
        totals[card["deck"]] += card["count"]
    return totals


def build_deck(deck_name: str, rng: random.Random) -> list[str]:
    """A freshly shuffled deck of card ids, each id repeated by its `count`.

    The RNG is injected rather than taken from the `random` module so a game can
    be replayed exactly from its seed — a draw order that cannot be reproduced
    cannot be debugged.
    """
    if deck_name not in DECKS:
        raise ValueError(f"unknown progress card deck: {deck_name}")

    deck = [
        card["id"]
        for card in PROGRESS_CARDS
        if card["deck"] == deck_name
        for _ in range(card["count"])
    ]
    rng.shuffle(deck)
    return deck


def draw_threshold(level: int) -> int:
    """The highest red die value that still draws a card at this improvement level.

    Level 1 draws on 1-2, each further level adds one, and level 5 always draws.
    Returned as a plain int so the caller's check is a single `red <= threshold`:
    0 means never (level 0) and 6 means always (level 5), since no die shows 6
    or less than 1 by accident.
    """
    if level < 0 or level > 5:
        raise ValueError(f"improvement level must be 0-5, got {level}")
    if level == 0:
        return 0
    if level == 5:
        return 6
    return level + 1


def _check_deck_sizes() -> None:
    """Guard the published composition at import time.

    A deck that is one card short never raises; it just silently biases every
    game played on it, so the cheapest place to catch it is here.
    """
    for deck_name, total in deck_counts().items():
        if total != CARDS_PER_DECK:
            raise AssertionError(
                f"{deck_name} deck has {total} cards, expected {CARDS_PER_DECK}"
            )

    ids = [card["id"] for card in PROGRESS_CARDS]
    if len(ids) != len(set(ids)):
        raise AssertionError("progress card ids must be unique")


_check_deck_sizes()
