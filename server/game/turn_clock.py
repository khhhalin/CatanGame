"""Turn order and the server-side clock, one phase at a time.

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
        # The Pirate Islands lets a player attack a fortress only once per turn
        # ("it is not possible to attack a pirate fortress more than once per
        # turn", p. 22); the record starts empty each turn.
        self.fortress_attacked_this_turn = False
        # A transport ship may move once per turn; the allowance does not
        # accumulate, so the record of which ships have moved starts empty.
        self.transport_ships_moved = set()
        # The gold-supply conversions are each capped per turn (game/gold.py),
        # so the counts start fresh with the turn.
        self.gold_conversions = {}
        # A fresh turn is back before its movement phase, so the next player
        # builds and trades normally (expansions.md 851-862). Only read when
        # `movement_phase` is on; see `movement_phase_block`.
        self.turn_phase = 'production'
        # The Caravans camel is owed only for the turn that earned it; a fresh
        # turn starts with none due (expansions.md 578).
        self.camel_owed = False
        # Traders & Barbarians main scenario: a fresh wagon-movement allowance
        # (lazily set on the first move from the baggage-train card), the grain
        # boost unspent, no barbarian driven yet, and no barbarian move owed
        # (a 7 sets it, and it is cleared when the barbarian is moved).
        self.wagon_points_left = None
        self.wagon_grain_used = False
        self.wagon_swift_journey = False
        self.barbarians_driven = set()
        self.must_move_barbarian = None
        # A helper's advantage may be used once per turn (Helpers_Rules.pdf p. 4);
        # the record of who has spent theirs starts empty each turn. Off the
        # scenario this set never fills. The last roll is forgotten too, so a
        # helper that reacts to production cannot fire on the previous turn's.
        self.helper_used_this_turn = set()
        self.last_roll_total = None
        self.last_roll_gains = {}
        # Oil Springs: a fresh turn has used no oil yet and has not sequestered.
        # The shared disaster track persists across turns; only these per-turn
        # records reset.
        self.oil_used_this_turn = 0
        self.oil_sequestered_this_turn = False
        # New Energies: only one power plant may be built per turn (a triggered
        # event may add one on top), and only one fossil plant demolished. A
        # fresh turn has done neither. Inert off the scenario.
        self.power_plant_built_this_turn = False
        self.fossil_demolished_this_turn = False
        # Catan for Two: a fresh turn may again trade one face-up knight for
        # trade tokens (rulebook "Once during your turn"). Inert off the variant.
        self.trade_token_knight_discarded = False
        # Catan: Frenemies: the tokens this player drew last turn have now waited
        # a turn and become usable, and a fresh turn may gift a resource again.
        self.start_favour_turn()

    def movement_phase_block(self):
        """Refuse a build or trade once this turn's ship movement has begun.

        E&P fixes the turn order production -> trade/build -> movement, and
        moving a ship is the point of no return: nothing may be built or traded
        afterwards (expansions.md 851-862). Founding a settlement with a settler
        ship is the one build allowed during movement, so that path never calls
        this. Off — or before a ship moves — it is a no-op, so the base game and
        Seafarers turn structure are untouched.
        """
        if self.rules['movement_phase'] and self.turn_phase == 'movement':
            return refused(
                'MOVEMENT_STARTED', 'You cannot build or trade after moving a ship this turn'
            )
        return None

    def advance_turn(self, player_name: str) -> dict:
        """End the current turn at a player's request."""
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        # Main scenario: a 7 makes the roller move a barbarian before ending
        # their turn, exactly as the robber move blocks a turn's end.
        if self.must_move_barbarian:
            return refused('MUST_MOVE_BARBARIAN', 'You must move a barbarian first')

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

        # The Caravans: a turn in which a settlement was built or upgraded earns a
        # camel, placed at the turn's end by a voting round (expansions.md 578).
        # Open the round and hold the turn open rather than advancing — it passes
        # to the next player once the camel is placed (`_finish_camel_vote`).
        if self._camel_vote_owed(current_name):
            self.open_camel_vote(current_name)
            return {'success': True, 'error': '', 'current_player': current_name,
                    'camel_vote': True}

        # Barbarian Attack: the coast is checked for victories at the end of the
        # turn, after the player has moved their knights (expansions.md 648). A
        # no-op without the rule.
        victories = None
        if self.rules['barbarian_attack']:
            victories = self.resolve_barbarian_victories()

        # Oil Springs: a disaster owed by this turn's oil use is resolved now —
        # after the turn's actions but before the board passes on (p. 2). It can
        # end the game (the board dies at five lost tokens), so the advance stops
        # there rather than handing the turn on.
        oil_disaster = None
        if self.oil_disaster_owed():
            oil_disaster = self.resolve_oil_disaster()
            if self.game_state == 'finished':
                return {'success': True, 'error': '', 'current_player': current_name,
                        'oil_disaster': oil_disaster, 'barbarian_victories': victories}

        return {'success': True, 'error': '',
                'current_player': self.force_advance_turn(),
                'oil_disaster': oil_disaster,
                'barbarian_victories': victories}

    def _camel_vote_owed(self, player_name: str) -> bool:
        """Whether ending this turn should open a camel voting round rather than
        advancing: the Caravans are on, a settlement was built or upgraded this
        turn, no vote is already open, the supply has camels left, and there is a
        legal path to place one on."""
        return bool(
            self.rules['caravans']
            and self.tb is not None
            and self.camel_owed
            and self.tb.camel_vote is None
            and len(self.tb.camels) < self.rules['max_camels']
            and self.legal_camel_placements()
        )

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
        # "for the rest of the turn" — and this is the path the watchdog takes,
        # so an abandoned turn cannot carry a Merchant Fleet into the next one.
        self.merchant_fleet_types = {}
        # An open trade offer is good only while its maker is on; their turn
        # ending takes it off the table (TEST 6). Both the manual next-turn and
        # the watchdog's forced advance pass through here, so neither leaves an
        # offer hanging into the next player's turn.
        self.trade_manager.cancel_all_active()

        self.start_turn()
        if self.rules['knights'] and self.ck is not None:
            # Clears each knight's per-turn flags. Without it a knight that acts
            # once stays spent for the rest of the game.
            self.ck.start_turn()

        return self.players[self.current_player_index].name

    def _timer_limit(self, rule_id: str, config, config_attr: str, fallback: int) -> int:
        """How long one clock runs: the table's number, or this server's.

        Zero is the catalogue default for every clock and means "leave it to
        the server", which is what keeps a deployment's own configuration —
        and a test run's one-second clocks — in force for a table that never
        opened the setting.
        """
        return self.rules[rule_id] or getattr(config, config_attr, fallback)

    def timer_limit_for(self, phase: str) -> int | None:
        """How long the clock for one phase runs, or None if there is none."""
        return {
            'dice': self.dice_roll_time_limit,
            'discard': self.discard_time_limit,
            'robber': self.robber_time_limit,
            'choice': self.choice_time_limit,
            'turn': self.round_time_limit,
        }.get(phase)

    def _phase_now(self) -> str | None:
        """The phase the game is in this instant, whatever the clock says.

        Ordered by what actually blocks the table: nothing can be built or
        traded while a 7 is unpaid, the robber is refused until every discard
        is in, and a pending choice freezes everyone including the player whose
        turn it is not.
        """
        if self.game_state != 'started' or self.game_phase == 'setup':
            return None
        if self.players_needing_discard:
            return 'discard'
        if self.must_move_robber or self.must_choose_victim:
            return 'robber'
        if self.pending_choices:
            return 'choice'
        if not self.has_rolled_dice:
            return 'dice'
        return 'turn'

    def timer_phase(self) -> str | None:
        """Which clock is running, restarting it when the phase has changed.

        Worked out from the game's own state rather than started by hand: every
        rule that can open a discard, a robber move or a decision would
        otherwise have to remember to start a clock for it, and the one that
        forgot would hand the next phase a clock that had already run out.
        """
        phase = self._phase_now()
        if phase != self.clock_phase:
            self.clock_phase = phase
            self.clock_started_time = time.time()
        return phase

    def timer_remaining(self) -> int | None:
        """Seconds left on the running clock, or None when none is running."""
        phase = self.timer_phase()
        if phase is None:
            return None
        # A pending choice carries its own deadline, because a choice can be
        # opened while another phase's clock is already running and it is often
        # owed by a player whose turn it is not.
        if phase == 'choice':
            deadline = min(choice['deadline'] for choice in self.pending_choices)
            return max(0, int(deadline - time.time()))
        limit = self.timer_limit_for(phase)
        return max(0, limit - int(time.time() - self.clock_started_time))

    def timer_expired(self) -> bool:
        """Whether the running clock has run out."""
        remaining = self.timer_remaining()
        return remaining is not None and remaining <= 0

    def timer_state(self) -> dict:
        """The running clock, for the client to count down against."""
        phase = self.timer_phase()
        return {
            'phase': phase,
            'remaining': self.timer_remaining(),
            'limit': self.timer_limit_for(phase),
        }

    def get_dice_roll_time_remaining(self) -> int:
        """Seconds left to roll. Full time once the dice are up."""
        if self.timer_phase() != 'dice':
            return self.dice_roll_time_limit
        return self.timer_remaining()

    def get_round_time_remaining(self) -> int:
        """Seconds left in the turn proper.

        Full time until it starts, which is only once the roll and anything it
        caused — a discard, a robber move — has been settled. Those have clocks
        of their own now, so a slow discard no longer costs a player their turn.
        """
        if self.timer_phase() != 'turn':
            return self.round_time_limit
        return self.timer_remaining()

    def is_dice_roll_expired(self) -> bool:
        """Check if dice roll time has expired."""
        return self.timer_phase() == 'dice' and self.timer_expired()

    def is_round_expired(self) -> bool:
        """Check if the turn proper has run out of time."""
        return self.timer_phase() == 'turn' and self.timer_expired()

    def set_dice_rolled(self):
        """Mark that dice has been rolled."""
        self.has_rolled_dice = True
        self.dice_rolled_time = time.time()
