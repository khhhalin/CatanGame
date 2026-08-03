"""The shape every engine action returns.

Its own leaf module because each rules mixin refuses actions, and importing the
helper from `game.game` would make every mixin import the class that inherits
it.
"""


def refused(code: str, error: str) -> dict:
    """A refused action, in the shape every engine action returns.

    The machine-readable code travels next to the prose because clients switch
    on the code while only the message is ever shown to a player.
    """
    return {'success': False, 'error': error, 'code': code}
