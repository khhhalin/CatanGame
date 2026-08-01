"""Payload validation for anything a browser sends us.

Socket.IO payloads are arbitrary client-controlled JSON. Every value that
reaches game state passes through here first, using allowlists rather than
blocklists so a field nobody thought about is rejected instead of accepted.
"""

RESOURCE_TYPES = ("wood", "brick", "sheep", "wheat", "ore")

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


def clean_resource_counts(raw, field: str = "resources", total_max: int = 100) -> dict:
    """Validate a {resource_type: count} mapping from a client.

    Negative counts are the specific danger here: a negative count passes a
    naive `held < count` check and then *adds* resources when subtracted, so
    every value must be a non-negative int and every key a known resource.
    Zero-valued entries are dropped so callers never see them.
    """
    if not isinstance(raw, dict):
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} must be an object")

    cleaned = {}
    for resource_type, count in raw.items():
        require_choice(resource_type, f"{field} key", RESOURCE_TYPES)
        count = require_int(count, f"{field}[{resource_type}]", minimum=0, maximum=total_max)
        if count > 0:
            cleaned[resource_type] = count

    if sum(cleaned.values()) > total_max:
        raise InvalidPayload("INVALID_PAYLOAD", f"{field} totals more than {total_max} cards")
    return cleaned
