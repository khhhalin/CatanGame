// The Barbarian Attack panel: the coastal war at a glance — how many barbarians
// are on the coast and in the supply, how many prisoners you hold, how many
// knights you have out, and how many cards are left — plus the two gestures the
// scenario needs: buy a card, and place the knight a Knighthood or Swift Knight
// grants. Read from `board.tb`, where all the war state rides. Mirrors rivers.js
// and caravans.js: one render on every board update that hides the whole panel
// on a table not playing the scenario.
//
// No rule logic lives here beyond erring permissive: the server checks the deck,
// the knight supply and the legal paths, and its answer is what the board is
// drawn from. Knight placement re-uses the board's edge gesture (the
// `barbarian_knight` kind in placement.js), so a tap on a legal path places it.

import { gameBoard, placeRoadBtn, placeSettlementBtn, upgradeCityBtn } from './dom.js';
import { markDirty } from './board.js';
import { displayError } from './notices.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

function el(id) {
    return document.getElementById(id);
}

/** Whether the table is playing Barbarian Attack. */
function barbarianAttackInPlay(board) {
    return Boolean(board?.rules?.barbarian_attack);
}

/**
 * Render the Barbarian Attack panel from the board, hidden whole on a table
 * without the scenario. Called on every board update.
 */
export function renderBarbarianAttack() {
    const panel = el('right-barbarian-attack');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const show = barbarianAttackInPlay(board);
    panel.classList.toggle('hidden', !show);
    if (!show) {
        return;
    }
    renderStatus(board);
    renderActions(board);
}

function renderStatus(board) {
    const status = el('barbarian-status');
    if (!status) {
        return;
    }
    const tb = board.tb || {};
    const me = (board.players || []).find(p => p.is_you) || {};
    const onCoast = Object.values(tb.barbarians || {}).reduce((a, b) => a + b, 0);
    const myKnights = Object.values(tb.knights || {})
        .filter(owner => owner === me.name).length;
    const prisoners = (tb.prisoners || {})[me.name] || 0;

    const items = [
        ['Barbarians on the coast', onCoast],
        ['In the supply', tb.barbarians_left ?? 0],
        ['Your knights', myKnights],
        ['Your prisoners', prisoners],
        ['Cards left', tb.ba_deck_remaining ?? 0],
    ];
    status.textContent = '';
    for (const [label, value] of items) {
        const item = document.createElement('span');
        item.className = 'ep-supply-item';
        item.innerHTML = `${label} <strong>${value}</strong>`;
        status.appendChild(item);
    }
}

function renderActions(board) {
    const mine = isMyTurn();
    const tb = board.tb || {};
    const me = (board.players || []).find(p => p.is_you) || {};

    const buyBtn = el('barbarian-buy-card');
    if (buyBtn) {
        buyBtn.disabled = !mine || Boolean(tb.pending_card);
        buyBtn.title = mine ? 'Reveal and resolve a scenario card' : 'Not your turn';
    }

    // A pending Knighthood/Swift Knight arms the knight-placement gesture and
    // tells the player to tap a path.
    const owed = tb.pending_card && tb.pending_card.player === me.name;
    const placeBtn = el('barbarian-place-knight');
    if (placeBtn) {
        placeBtn.classList.toggle('hidden', !owed);
        placeBtn.classList.toggle(
            'active', viewState.selectedBuilding === 'barbarian_knight');
    }
    const hint = el('barbarian-hint');
    if (hint) {
        hint.classList.toggle('hidden', !owed);
        if (owed) {
            const card = tb.pending_card.card === 'knighthood'
                ? 'a castle path' : 'any free path';
            hint.textContent = `Place your knight — tap ${card}.`;
        }
    }
    if (!owed && viewState.selectedBuilding === 'barbarian_knight') {
        viewState.selectedBuilding = null;
        gameBoard?.classList.remove('placement-mode');
    }

    // Move knight: shown whenever you have a knight out, disabled off-turn or
    // while a placement is still owed (the engine refuses a move until then).
    const myKnights = Object.values(tb.knights || {})
        .filter(owner => owner === me.name).length;
    const moveBtn = el('barbarian-move-knight');
    if (moveBtn) {
        moveBtn.classList.toggle('hidden', myKnights === 0);
        moveBtn.disabled = !mine || Boolean(tb.pending_card);
        moveBtn.classList.toggle(
            'active', viewState.selectedBuilding === 'barbarian_knight_move');
        moveBtn.title = mine ? 'Move one of your knights' : 'Not your turn';
    }
    settleKnightMove(tb, me.name);
    // A mode left armed when it can no longer run — the turn passed, or a card
    // now owes a placement — is disarmed so a stray tap does nothing.
    if (viewState.selectedBuilding === 'barbarian_knight_move'
        && (!mine || tb.pending_card)) {
        clearKnightMoveMode();
    }
}

// The move just sent, so the mode can retire once the board confirms it — the
// same survives-a-refusal pattern the ship move uses: a refused move never
// broadcasts a board, so the mode simply stays armed to aim again.
let pendingKnightMove = null;

/**
 * Drop the move mode once the board shows the knight reached its destination.
 *
 * @param {object} tb - The Barbarian Attack state from the board
 * @param {string} myName - This player's name
 */
function settleKnightMove(tb, myName) {
    if (!pendingKnightMove) {
        return;
    }
    const knights = tb.knights || {};
    if (knights[pendingKnightMove.to] === myName
        && knights[pendingKnightMove.from] !== myName) {
        pendingKnightMove = null;
        clearKnightMoveMode();
    }
}

/**
 * Disarm the knight-move mode and forget any half-made selection.
 */
function clearKnightMoveMode() {
    if (viewState.selectedBuilding === 'barbarian_knight_move') {
        viewState.selectedBuilding = null;
    }
    viewState.barbarianKnightMoveFrom = null;
    gameBoard?.classList.remove('placement-mode');
}

/**
 * First tap of a knight move: pick one of your own knights up. Refused rather
 * than recorded when the path holds no knight of yours, the way a ship move is.
 *
 * @param {string} edgeKey - The path tapped
 */
export function selectBarbarianKnightToMove(edgeKey) {
    const owner = (getBoard()?.tb?.knights || {})[edgeKey];
    if (owner !== viewState.identity.name) {
        displayError('Tap one of your own knights to move it.');
        return;
    }
    viewState.barbarianKnightMoveFrom = edgeKey;
    markDirty();
}

/**
 * Second tap: send the move from the held knight to this path. The server
 * checks the reach and refuses an illegal move, leaving the mode armed to retry.
 *
 * @param {string} toEdge - The destination path tapped
 */
export function moveBarbarianKnight(toEdge) {
    const from = viewState.barbarianKnightMoveFrom;
    if (!from) {
        return;
    }
    emitGame('move_barbarian_knight',
             { name: viewState.identity.name, from, to: toEdge });
    pendingKnightMove = { from, to: toEdge };
    viewState.barbarianKnightMoveFrom = null;
    markDirty();
}

/** Arm (or disarm) the knight-placement gesture, clearing the other board build
 * modes so exactly one is ever selected. Then a tap on a legal path places it. */
function armKnightMode() {
    viewState.selectedBuilding =
        viewState.selectedBuilding === 'barbarian_knight' ? null : 'barbarian_knight';
    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn]
        .forEach(button => button?.classList.remove('active'));
    gameBoard?.classList.toggle('placement-mode', Boolean(viewState.selectedBuilding));
    markDirty();
    renderBarbarianAttack();
}

/** Arm (or disarm) the knight-move gesture, clearing the other board build
 * modes so exactly one is ever selected. First tap picks a knight up, the
 * second sends it. */
function armKnightMoveMode() {
    viewState.selectedBuilding =
        viewState.selectedBuilding === 'barbarian_knight_move'
            ? null : 'barbarian_knight_move';
    viewState.barbarianKnightMoveFrom = null;
    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn]
        .forEach(button => button?.classList.remove('active'));
    gameBoard?.classList.toggle('placement-mode', Boolean(viewState.selectedBuilding));
    markDirty();
    renderBarbarianAttack();
}

el('barbarian-buy-card')?.addEventListener('click', () => {
    emitGame('buy_barbarian_card', {});
});
el('barbarian-place-knight')?.addEventListener('click', armKnightMode);
el('barbarian-move-knight')?.addEventListener('click', armKnightMoveMode);
