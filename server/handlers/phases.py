"""What the current phase forbids, for handlers that build or spend.

The server is authoritative, so a phase that blocks building has to be enforced
here whatever the UI happens to draw. `game.py` already refuses the base-game
placements while the robber is unmoved; this covers the rest of the pending
states — an unchosen victim, an owed discard, an open pending choice — and the
Cities & Knights purchases, which had no phase check at all.
"""

import state
from state import reject


def phase_block(name: str) -> tuple[str, str] | None:
    """(code, message) if this player may not act right now, else None."""
    game = state.session().game
    if game is None:
        return None

    if game.must_move_robber:
        return 'MUST_MOVE_ROBBER', 'You must move the robber first'
    if game.must_choose_victim:
        return 'MUST_CHOOSE_VICTIM', 'You must choose a victim to steal from'
    # A pending choice freezes the whole table, not only the player who owes
    # it: the game has stopped on a question, and building on around it would
    # let the current player spend cards a Wedding is about to take.
    blocked = game.choice_block(name)
    if blocked is not None:
        return blocked['code'], blocked['error']
    # Anyone who owes a discard is frozen, whoever's turn it is: they are over
    # the hand limit, and building would let them spend their way under it
    # instead of paying the 7.
    if name in game.players_needing_discard:
        return 'MUST_DISCARD', 'You must discard down to the hand limit first'
    # And the table waits with them: the 7 is still being resolved, and a rule
    # that stops the robber but lets the roller keep building is half a rule.
    if game.players_needing_discard:
        owed = ', '.join(sorted(game.players_needing_discard))
        return 'MUST_DISCARD', f'Waiting for {owed} to discard'
    return None


def blocked_by_phase(name: str) -> bool:
    """Whether to stop. Rejects the sender itself, so callers just return."""
    block = phase_block(name)
    if block is None:
        return False
    reject(*block)
    return True
