"""Payload validation for anything a browser sends us.

Socket.IO payloads are arbitrary client-controlled JSON. Every value that
reaches game state passes through here first, using allowlists rather than
blocklists so a field nobody thought about is rejected instead of accepted.
"""

# The five resources every printed box holds, in the order they have always been
# shown. A game never deals fewer than these.
BASE_RESOURCE_TYPES = ("wood", "brick", "sheep", "wheat", "ore")

# Every resource the type system knows. `cotton` is the sixth: it is not in any
# box and no built-in board deals it, but it is a real resource a custom map may
# place (game/tiles.py), so it belongs in the allowlist that trade, discard and
# monopoly validate against — naming it on a board that has no cotton simply
# moves nothing, because no player holds it and the bank stocks none.
RESOURCE_TYPES = BASE_RESOURCE_TYPES + ("cotton",)

# Cities & Knights commodities. Kept here rather than imported from
# `game.cities_knights` so this module stays free of game-state imports.
COMMODITY_TYPES = ("cloth", "coin", "paper")

# What a player can be made to hand over on a 7: commodities count toward the
# hand limit, so they have to be expressible in a discard.
CARD_TYPES = RESOURCE_TYPES + COMMODITY_TYPES

DEV_CARD_TYPES = ("knight", "two_roads", "invention", "monopoly", "victory_point")


class InvalidPayload(Exception):
    """A client sent something structurally wrong. Carries an error code so the
    handler can report it without inventing prose."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def require_str(value, field: str, max_length: int = 64) -> str:
    """Return value as a non-empty string, or raise."""
    if not isinstance(value, str):
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} must be a string")
    value = value.strip()
    if not value:
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} must not be empty")
    if len(value) > max_length:
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} is too long")
    return value


def require_int(value, field: str, minimum: int = 0, maximum: int = 10_000) -> int:
    """Return value as an int within bounds, or raise.

    bool is rejected explicitly because it is a subclass of int in Python and
    True would otherwise sail through as 1.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} must be a whole number")
    if value < minimum or value > maximum:
        raise InvalidPayload(
            "INVALID_PAYLOAD", f"{field} must be between {minimum} and {maximum}"
        )
    return value


def require_choice(value, field: str, allowed) -> str:
    """Return value if it is one of allowed, or raise."""
    if value not in allowed:
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} must be one of: {', '.join(allowed)}")
    return value


def _clean_counts(raw, field: str, allowed, total_max: int) -> dict:
    """Validate a {card_type: count} mapping from a client.

    Negative counts are the specific danger here: a negative count passes a
    naive `held < count` check and then *adds* cards when subtracted, so every
    value must be a non-negative int and every key one of `allowed`.
    Zero-valued entries are dropped so callers never see them.
    """
    if not isinstance(raw, dict):
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} must be an object")

    cleaned = {}
    for card_type, count in raw.items():
        require_choice(card_type, f"{field} key", allowed)
        count = require_int(count, f"{field}[{card_type}]", minimum=0, maximum=total_max)
        if count > 0:
            cleaned[card_type] = count

    if sum(cleaned.values()) > total_max:
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} totals more than {total_max} cards")
    return cleaned


def clean_resource_counts(raw, field: str = "resources", total_max: int = 100,
                          allow_oil: bool = False) -> dict:
    """Validate a {resource_type: count} mapping — the five resources only.

    On an Oil Springs table `allow_oil` admits `oil` too, because Year of Plenty
    may take oil from the supply (coilspringsgb_2015_web.pdf p. 1).
    """
    allowed = RESOURCE_TYPES + ("oil",) if allow_oil else RESOURCE_TYPES
    return _clean_counts(raw, field, allowed, total_max)


def clean_card_counts(raw, field: str = "cards", total_max: int = 100,
                      allow_oil: bool = False) -> dict:
    """Validate a {card_type: count} mapping over resources *and* commodities.

    Used by the discard on a 7: commodities count toward the hand limit, so a
    player over the limit has to be able to hand them back. On an Oil Springs
    table `allow_oil` admits `oil` too, because oil counts as a card on a 7 and
    may be discarded back to its supply (coilspringsgb_2015_web.pdf p. 1).
    """
    allowed = CARD_TYPES + ("oil",) if allow_oil else CARD_TYPES
    return _clean_counts(raw, field, allowed, total_max)
