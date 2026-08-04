"""Turn order and the two server-side clocks.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. The clocks are server-owned on purpose — a client that owns the timer
owns unlimited thinking time — so they live next to the turn advance they guard.
"""

import logging
import time

from game.results import refused

logger = logging.getLogger(__name__)


class TurnClock:
    """Starting the game, advancing turns, and the dice/round timers."""

    def start(self):
        """Start the game, seating the players in the chosen order.

        Shuffling is what "roll the dice for the starting player" amounts to;
        a table that wants to replay a start keeps the order they joined in.
        """
        if self.rules['turn_order'] == 'random':
            self.rng.shuffle(self.players)
        self.game_state = "started"
        self.start_turn()
        logger.debug("\n=== Game started! ===")
        logger.debug(f"Player order: {self.players}")
        logger.debug(f"Current player: {self.players[self.current_player_index]}")
        logger.debug("=====================\n")

    def start_turn(self):
        """Start a new turn and reset timers."""
        self.turn_start_time = time.time()
        self.dice_rolled_time = None
        self.has_rolled_dice = False
        self.free_roads_remaining = 0  # Reset free roads at start of turn
        # Seafarers allows one ship to be moved per turn, and the allowance
        # does not accumulate.
        self.ship_moved_this_turn = False

    def advance_turn(self, player_name: str) -> dict:
        """End the current turn at a player's request."""
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        if self.must_choose_victim:
            return refused('MUST_CHOOSE_VICTIM', 'You must choose a victim to steal from')

        # A turn that ended with a decision outstanding would carry it into the
        # next player's turn, which is the bug the robber flags already paid
        # for. The watchdog answers an abandoned choice before it gets here.
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        # A discard belongs to the roll still being resolved, so the turn ends
        # for nobody while any of it is unpaid. Checking only the caller let the
        # roller finish their turn while two opponents were still discarding.
        if player_name in self.players_needing_discard:
            return refused('MUST_DISCARD', 'You must discard resources first')
        if self.players_needing_discard:
            owed = ', '.join(sorted(self.players_needing_discard))
            return refused('MUST_DISCARD', f'Waiting for {owed} to discard')

        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot skip turn during setup phase')

        # The seat's own player normally ends the turn. Once the round timer has
        # run out anyone may advance it, so an absent player cannot stall the table.
        current_name = self.players[self.current_player_index].name
        if player_name != current_name and not self.is_round_expired():
            return refused('NOT_YOUR_TURN', f'Only {current_name} can advance the turn')

        return {'success': True, 'error': '', 'current_player': self.force_advance_turn()}

    def force_advance_turn(self) -> str:
        """Move to the next player and reset the per-turn state, unconditionally.

        The turn watchdog uses this: a turn that has timed out ends whether or
        not the player whose turn it was is still at the table.
        """
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        self.turn_count += 1

        # A new turn clears any follow-up the previous player never used, so an
        # unspent Invention cannot be redeemed two turns later.
        self.pending_invention = None
        self.pending_monopoly = None
        self.free_roads_remaining = 0

        self.start_turn()
        if self.rules['knights'] and self.ck is not None:
            # Clears each knight's per-turn flags. Without it a knight that acts
            # once stays spent for the rest of the game.
            self.ck.start_turn()

        return self.players[self.current_player_index].name

    def get_dice_roll_time_remaining(self) -> int:
        """Get seconds remaining for dice roll."""
        if self.turn_start_time is None or self.has_rolled_dice:
            return self.dice_roll_time_limit
        elapsed = time.time() - self.turn_start_time
        return max(0, self.dice_roll_time_limit - int(elapsed))

    def get_round_time_remaining(self) -> int:
        """Get seconds remaining for round (starts after dice roll)."""
        if self.turn_start_time is None:
            return self.round_time_limit
        # If dice not rolled yet, return full time (will be shown as "-")
        if not self.has_rolled_dice:
            return self.round_time_limit
        # Calculate from dice roll time
        if self.dice_rolled_time is None:
            return self.round_time_limit
        elapsed = time.time() - self.dice_rolled_time
        return max(0, self.round_time_limit - int(elapsed))

    def is_dice_roll_expired(self) -> bool:
        """Check if dice roll time has expired."""
        if self.has_rolled_dice:
            return False
        return self.get_dice_roll_time_remaining() <= 0

    def is_round_expired(self) -> bool:
        """Check if round time has expired."""
        return self.get_round_time_remaining() <= 0

    def set_dice_rolled(self):
        """Mark that dice has been rolled."""
        self.has_rolled_dice = True
        self.dice_rolled_time = time.time()
