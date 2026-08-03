// The dice and round countdowns. Display only - the server owns turn expiry,
// and a client that owned the clock would own unlimited thinking time.

import { diceTimerEl, roundTimerEl } from './dom.js';
import { getBoard, getGamePhase, isGameRunning, isMyTurn, viewState } from './state.js';

/**
 * Update timer displays based on board data
 */
export function updateTimers(boardData) {
    if (!boardData || !diceTimerEl || !roundTimerEl) return;
    
    // Only show timers in playing phase
    if (boardData.game_phase === 'setup') {
        diceTimerEl.textContent = 'Dice: -';
        roundTimerEl.textContent = 'Round: -';
        if (viewState.timers.handle) clearInterval(viewState.timers.handle);
        return;
    }
    
    viewState.timers.diceSeconds = boardData.dice_roll_time || 15;
    viewState.timers.roundSeconds = boardData.round_time || 120;
    viewState.timers.updatedAt = Date.now();
    const hasRolled = boardData.has_rolled_dice;
    
    // Dice timer - only show if hasn't rolled yet
    if (hasRolled) {
        diceTimerEl.textContent = 'Dice: -';
        diceTimerEl.className = 'timer';
    } else {
        diceTimerEl.textContent = `Dice: ${viewState.timers.diceSeconds}s`;
        diceTimerEl.className = 'timer' + (viewState.timers.diceSeconds <= 5 ? ' danger' : viewState.timers.diceSeconds <= 10 ? ' warning' : '');
    }
    
    // Round timer - only show after dice rolled
    if (hasRolled) {
        roundTimerEl.textContent = `Round: ${viewState.timers.roundSeconds}s`;
        roundTimerEl.className = 'timer' + (viewState.timers.roundSeconds <= 30 ? ' danger' : viewState.timers.roundSeconds <= 60 ? ' warning' : '');
    } else {
        roundTimerEl.textContent = 'Round: -';
        roundTimerEl.className = 'timer';
    }
    
    // Start timer interval if it's player's turn and playing phase
    if (boardData.game_phase === 'playing' && isMyTurn()) {
        startTimerInterval();
    } else {
        if (viewState.timers.handle) clearInterval(viewState.timers.handle);
    }
}

export function startTimerInterval() {
    if (viewState.timers.handle) clearInterval(viewState.timers.handle);
    
    viewState.timers.handle = setInterval(() => {
        if (!isGameRunning() || !isMyTurn() || getGamePhase() === 'setup') {
            clearInterval(viewState.timers.handle);
            return;
        }
        
        const elapsed = Math.floor((Date.now() - viewState.timers.updatedAt) / 1000);
        
        // Calculate current times
        const currentDiceTime = Math.max(0, viewState.timers.diceSeconds - elapsed);
        const currentRoundTime = Math.max(0, viewState.timers.roundSeconds - elapsed);
        const hasRolled = getBoard()?.has_rolled_dice;

        // Display only: the server owns turn expiry. A client-side auto-emit
        // here would play the turn from a backgrounded tab.

        // Update dice timer display
        if (hasRolled) {
            diceTimerEl.textContent = 'Dice: -';
            diceTimerEl.className = 'timer';
        } else {
            diceTimerEl.textContent = `Dice: ${currentDiceTime}s`;
            diceTimerEl.className = 'timer' + (currentDiceTime <= 5 ? ' danger' : currentDiceTime <= 10 ? ' warning' : '');
        }
        
        // Update round timer display (only after dice rolled)
        if (hasRolled) {
            roundTimerEl.textContent = `Round: ${currentRoundTime}s`;
            roundTimerEl.className = 'timer' + (currentRoundTime <= 30 ? ' danger' : currentRoundTime <= 60 ? ' warning' : '');
        } else {
            roundTimerEl.textContent = 'Round: -';
            roundTimerEl.className = 'timer';
        }
    }, 1000);
}
