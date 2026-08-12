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

el('barbarian-buy-card')?.addEventListener('click', () => {
    emitGame('buy_barbarian_card', {});
});
el('barbarian-place-knight')?.addEventListener('click', armKnightMode);
