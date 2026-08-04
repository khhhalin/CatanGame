// The turn's countdowns.
//
// Display only - the server owns expiry, and a client that owned the clock
// would own unlimited thinking time.
//
// Nothing here is counted and nothing here is inferred. A turn is now several
// phases with a clock each - dice, discard, robber, choice, turn - and the
// server says in every payload which one is running (`timer.phase`), how much
// of it is left (`timer.remaining`) and how long it was (`timer.limit`). This
// module records that reading with the wall-clock instant it arrived and, once
// a second, shows the difference. Two consequences, and both were bugs before:
//
//   - Every tab shows the same number, because every tab is subtracting from
//     the same server-sent figure rather than from a count of its own.
//   - A phase change appears on every tab at once. Working out which phase the
//     game is in from `has_rolled_dice` and the rest is exactly the local
//     guess that made the round clock never arrive for anyone but the roller.
//
// Two elements, both keeping the ids a dozen test modules drive: `#dice-timer`
// is whichever clock is running and names it, `#round-timer` is the turn
// proper. Before phases existed those were the only two clocks there were.

import { diceTimerEl, roundTimerEl } from './dom.js';
import { getBoard, getGamePhase, isGameRunning, viewState } from './state.js';

// What each phase is called on screen. `turn` is absent on purpose: it is the
// one clock with an element of its own.
const PHASE_LABELS = {
    dice: 'Dice',
    discard: 'Discard',
    robber: 'Robber',
    choice: 'Choice',
};

// Where a clock changes colour, as a share of the time it started with. A
// fraction rather than a count of seconds because every phase has a limit of
// its own and the table can change all of them in the lobby - a hardcoded
// "10 seconds left is a warning" says nothing on a 5-second discard clock.
const WARNING_SHARE = 0.5;
const DANGER_SHARE = 0.25;

/**
 * Record the clocks a server message carried.
 *
 * Safe to call with any payload: a message that says nothing about the clock
 * leaves the last reading alone rather than resetting it to a default, which is
 * what would make the display jump backwards.
 *
 * @param {object} data - Any payload that may carry a `timer` object
 */
export function noteServerClocks(data) {
    const timer = data?.timer;
    if (!timer || typeof timer !== 'object') {
        return;
    }
    viewState.timers.phase = timer.phase ?? null;
    viewState.timers.remaining = typeof timer.remaining === 'number' ? timer.remaining : null;
    viewState.timers.limit = typeof timer.limit === 'number' ? timer.limit : null;
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
 * Seconds left on the running clock, given what the server said and how long
 * ago it said it.
 *
 * @returns {number|null} - null when no clock is running
 */
function remaining() {
    if (viewState.timers.remaining === null) {
        return null;
    }
    const elapsed = Math.floor((Date.now() - viewState.timers.updatedAt) / 1000);
    return Math.max(0, viewState.timers.remaining - elapsed);
}

/**
 * The urgency class for a countdown, against the time it started with.
 *
 * @param {number} seconds - Left on the clock
 * @param {number|null} limit - What the clock started at
 */
function timerClass(seconds, limit) {
    if (!limit) {
        return 'timer';
    }
    if (seconds <= limit * DANGER_SHARE) {
        return 'timer danger';
    }
    if (seconds <= limit * WARNING_SHARE) {
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

    const phase = viewState.timers.phase;
    if (!isGameRunning() || getGamePhase() === 'setup' || !phase) {
        diceTimerEl.textContent = 'Dice: —';
        diceTimerEl.className = 'timer';
        roundTimerEl.textContent = 'Round: —';
        roundTimerEl.className = 'timer';
        return;
    }

    const left = remaining();
    const urgency = timerClass(left, viewState.timers.limit);

    // The turn proper. Its own element, because it is the clock a player is
    // spending while they decide what to build.
    if (phase === 'turn') {
        diceTimerEl.textContent = 'Dice: rolled';
        diceTimerEl.className = 'timer';
        roundTimerEl.textContent = `Round: ${left}s`;
        roundTimerEl.className = urgency;
        return;
    }

    // Everything the roll can hold the table up with. Named, because "45s" over
    // a table that has stopped says nothing about what it is waiting for - and
    // a discard clock running down while the turn clock reads "—" is the whole
    // point of splitting them.
    diceTimerEl.textContent = `${PHASE_LABELS[phase] || phase}: ${left}s`;
    diceTimerEl.className = urgency;
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
