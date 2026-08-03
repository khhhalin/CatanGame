// The dice and round countdowns.
//
// Display only - the server owns turn expiry, and a client that owned the clock
// would own unlimited thinking time.
//
// Both numbers are *derived*, never counted. The server sends the seconds it
// has left on each clock in every board payload (`dice_roll_time`,
// `round_time`); this module records them with the wall-clock instant they
// arrived and, once a second, shows the difference. Two consequences, and both
// were bugs before:
//
//   - Every tab shows the same number, because every tab is subtracting from
//     the same server-sent figure rather than from a count of its own.
//   - The round clock appears the moment the payload says the dice are up. It
//     used to be gated behind a ticker that only ran on the current player's
//     own tab, so for everyone else neither clock ever moved and the round one
//     never arrived at all.

import { diceTimerEl, roundTimerEl } from './dom.js';
import { getBoard, getGamePhase, hasRolledDice, isGameRunning, viewState } from './state.js';

// Where each clock changes colour, in seconds remaining.
const DICE_WARNING = 10;
const DICE_DANGER = 5;
const ROUND_WARNING = 60;
const ROUND_DANGER = 30;

/**
 * Record the clocks a server message carried.
 *
 * Safe to call with any payload: a message that says nothing about the clocks
 * leaves the last reading alone rather than resetting it to a default, which is
 * what would make the display jump backwards.
 *
 * @param {object} data - Any payload that may carry `dice_roll_time`/`round_time`
 */
export function noteServerClocks(data) {
    if (!data) {
        return;
    }
    if (typeof data.dice_roll_time !== 'number' && typeof data.round_time !== 'number') {
        return;
    }
    if (typeof data.dice_roll_time === 'number') {
        viewState.timers.diceSeconds = data.dice_roll_time;
    }
    if (typeof data.round_time === 'number') {
        viewState.timers.roundSeconds = data.round_time;
    }
    // One anchor for both: the server computed them at the same instant.
    viewState.timers.updatedAt = Date.now();
}

/**
 * Paint both clocks from the last server reading and the time since.
 *
 * @param {object} [boardData] - A payload to record first, if one prompted this
 */
export function updateTimers(boardData) {
    noteServerClocks(boardData);
    renderTimers();
    startTimerInterval();
}

/**
 * Seconds left on a clock, given what the server said and how long ago.
 *
 * @param {number} serverSeconds - Remaining, as of the last payload
 * @returns {number}
 */
function remaining(serverSeconds) {
    const elapsed = Math.floor((Date.now() - viewState.timers.updatedAt) / 1000);
    return Math.max(0, serverSeconds - elapsed);
}

/**
 * The urgency class for a countdown.
 */
function timerClass(seconds, warningAt, dangerAt) {
    if (seconds <= dangerAt) {
        return 'timer danger';
    }
    if (seconds <= warningAt) {
        return 'timer warning';
    }
    return 'timer';
}

/**
 * Show both clocks for whatever the board currently is.
 *
 * A clock that does not apply reads "—" rather than disappearing: a control
 * that comes and goes is what made the round timer look broken, because its
 * absence and a stuck value are indistinguishable.
 */
function renderTimers() {
    if (!diceTimerEl || !roundTimerEl) {
        return;
    }

    if (!isGameRunning() || getGamePhase() === 'setup') {
        diceTimerEl.textContent = 'Dice: —';
        diceTimerEl.className = 'timer';
        roundTimerEl.textContent = 'Round: —';
        roundTimerEl.className = 'timer';
        return;
    }

    // Exactly one of the two is live at any moment: the dice clock runs until
    // the roll, the round clock from the roll to the end of the turn.
    if (hasRolledDice()) {
        diceTimerEl.textContent = 'Dice: rolled';
        diceTimerEl.className = 'timer';

        const left = remaining(viewState.timers.roundSeconds);
        roundTimerEl.textContent = `Round: ${left}s`;
        roundTimerEl.className = timerClass(left, ROUND_WARNING, ROUND_DANGER);
        return;
    }

    const left = remaining(viewState.timers.diceSeconds);
    diceTimerEl.textContent = `Dice: ${left}s`;
    diceTimerEl.className = timerClass(left, DICE_WARNING, DICE_DANGER);
    roundTimerEl.textContent = 'Round: —';
    roundTimerEl.className = 'timer';
}

/**
 * Keep the display moving between server messages.
 *
 * Deliberately not gated on whose turn it is: the clocks are the table's, not
 * the current player's, and a spectator watching a frozen countdown cannot tell
 * a slow player from a dropped connection.
 */
export function startTimerInterval() {
    if (viewState.timers.handle) {
        return;
    }

    viewState.timers.handle = setInterval(() => {
        if (!isGameRunning() || !getBoard()) {
            clearInterval(viewState.timers.handle);
            viewState.timers.handle = null;
            renderTimers();
            return;
        }
        renderTimers();
    }, 1000);
}
