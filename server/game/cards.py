"""The card registry: one place a card is defined, one interface to resolve it.

A card is a **descriptor** (id, name, family, deck, timing, needs_target,
victory_points) paired with a **resolver** — `resolve(game, player_name, target)
-> result dict`. The resolver calls the engine's own methods (`get_player`,
`bank`, robber and knight operations, …): the `Game` object is the API a card is
written against. This is the "engine as an API" seam — adding a card is
registering one self-contained unit, with no edit to any core dispatch.

Two families share the registry:

- **dev** — the base-game development deck (knight, victory point, road building,
  year of plenty, monopoly). Their effects live here as small resolvers.
- **progress** — the Cities & Knights progress cards. Their effects reach deep
  into engine internals (the knight roster, the improvement tracks, the robber),
  so each resolver stays an engine method and the registry *delegates* to it by
  its `_progress_<id>` name. That is not a stopgap: a resolver that needs the
  whole engine is correctly written against the engine. The registry still owns
  *what the card is* and gives every card one uniform play path.

The registry owns the card's identity and effect. Each family's **lifecycle** —
buying versus drawing, the count map versus the hand, pending follow-ups — stays
in that family's rules mixin (`dev_card_rules.py`, `cities_knights_rules.py`).
Deck composition also stays where it is dealt from (`bank.py` for dev cards,
`progress_cards.py` for the three progress decks); the registry never becomes a
second copy of a count.
"""

from collections.abc import Callable
from dataclasses import dataclass

from game import progress_cards

DEV = "dev"
PROGRESS = "progress"


@dataclass(frozen=True)
class Card:
    """One card: its descriptor and how its effect resolves.

    `resolve(game, player_name, target)` returns the family's usual result dict,
    or is `None` for a card that is never *played* (a progress card revealed for
    its victory point the moment it is drawn). `count` and deck composition are
    owned elsewhere; the fields here that duplicate a descriptor are mirrored, not
    authoritative — the registry tests pin them against their source.
    """

    id: str
    name: str
    family: str
    deck: str
    timing: str
    needs_target: str | None
    victory_points: int
    resolve: Callable | None = None
    summary: str = ""


REGISTRY: dict[str, Card] = {}


def register(card: Card) -> Card:
    """Add a card to the registry. Refuses a duplicate id across all families.

    This is the extension point: a new card — official or homebrew — is one
    `register(Card(...))` call with its resolver, and needs no change to any
    dispatch site.
    """
    if card.id in REGISTRY:
        raise ValueError(f"duplicate card id: {card.id!r}")
    REGISTRY[card.id] = card
    return card


def get(card_id: str) -> Card | None:
    """The registered card, or None if no card has that id."""
    return REGISTRY.get(card_id)


def by_family(family: str) -> list[Card]:
    """Every registered card in one family, in registration order."""
    return [card for card in REGISTRY.values() if card.family == family]


# --- dev card resolvers ---------------------------------------------------
#
# Each mutates the game and returns only the result keys its effect sets;
# `play_dev_card` starts from a full default result and merges these in, so the
# behaviour is exactly the per-type branch it replaced.


def _dev_knight(game, player_name: str, target) -> dict:
    player = game.get_player(player_name)
    game.must_move_robber = True
    player.knights_played += 1
    game.update_largest_army()
    return {"must_move_robber": True}


def _dev_victory_point(game, player_name: str, target) -> dict:
    player = game.get_player(player_name)
    player.victory_points += 1
    points = game.claim_victory(player_name)
    if points is not None:
        return {"won": True, "victory_points": points}
    return {}


def _dev_invention(game, player_name: str, target) -> dict:
    # Record who is owed the follow-up. Without this, use_invention is a free
    # action any client can call without ever holding the card.
    game.pending_invention = player_name
    return {"needs_resources": True}


def _dev_two_roads(game, player_name: str, target) -> dict:
    game.free_roads_remaining = 2
    return {}


def _dev_monopoly(game, player_name: str, target) -> dict:
    game.pending_monopoly = player_name
    return {"needs_resource": True}


_DEV_CARDS = [
    ("knight", "Knight", 0, _dev_knight),
    ("victory_point", "Victory Point", 1, _dev_victory_point),
    ("invention", "Year of Plenty", 0, _dev_invention),
    ("two_roads", "Road Building", 0, _dev_two_roads),
    ("monopoly", "Monopoly", 0, _dev_monopoly),
]


# --- progress card resolvers ----------------------------------------------
#
# The effect is an engine method `_progress_<id>`; the registry delegates to it.
# A card that is only ever revealed on draw (its victory point) has no play
# resolver and so no method — its `resolve` is None, and playing it is refused
# with "not implemented yet", exactly as the direct `getattr` did before.


def _delegate(card_id: str) -> Callable:
    def resolve(game, player_name: str, target):
        return getattr(game, f"_progress_{card_id}")(player_name, target)

    return resolve


def _register_dev_cards() -> None:
    for card_id, name, victory_points, resolver in _DEV_CARDS:
        register(Card(
            id=card_id, name=name, family=DEV, deck=DEV, timing="turn",
            needs_target=None, victory_points=victory_points, resolve=resolver,
        ))


def _register_progress_cards() -> None:
    for descriptor in progress_cards.PROGRESS_CARDS:
        immediate = descriptor["timing"] == progress_cards.TIMING_IMMEDIATE
        register(Card(
            id=descriptor["id"],
            name=descriptor["name"],
            family=PROGRESS,
            deck=descriptor["deck"],
            timing=descriptor["timing"],
            needs_target=descriptor["needs_target"],
            victory_points=descriptor["victory_points"],
            resolve=None if immediate else _delegate(descriptor["id"]),
            summary=descriptor.get("summary", ""),
        ))


_register_dev_cards()
_register_progress_cards()
