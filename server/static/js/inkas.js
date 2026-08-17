// Catan Histories: Rise of the Inkas panel. Each player's tribe number, their
// culture markers (11 wins) and their active tribe's progress toward its apex,
// plus a prompt when the viewer owes a free founding settlement after a decline.
// Read from `board.inkas`. Gated on the individual `tribe_decline` rule, not on
// the presence of the sub-object. Mirrors oil.js: one render on every board
// update.

import { getBoard } from './state.js';

const TRIBE_NUMERAL = { 1: 'I', 2: 'II', 3: 'III' };

function el(id) {
    return document.getElementById(id);
}

/**
 * Render the Rise of the Inkas panel from the board, hidden whole on a table
 * without the scenario. Called on every board update.
 */
export function renderInkas() {
    const panel = el('right-inkas');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const inkas = board?.inkas;
    const show = Boolean(inkas) && board?.rules?.tribe_decline === true;
    panel.classList.toggle('hidden', !show);
    if (!show) {
        return;
    }
    renderStatus(board, inkas);
    renderHint(board, inkas);
}

function chip(label, value) {
    const item = document.createElement('span');
    item.className = 'ep-supply-item';
    item.innerHTML = `${label} <strong>${value}</strong>`;
    return item;
}

function renderStatus(board, inkas) {
    const status = el('inkas-status');
    if (!status) {
        return;
    }
    status.textContent = '';
    for (const player of board.players || []) {
        const line = inkas.players?.[player.name];
        if (!line) {
            continue;
        }
        const tribe = TRIBE_NUMERAL[line.tribe] || line.tribe;
        const goal = inkas.goals?.[String(line.tribe)];
        const progress = goal ? `${line.active_tribe_culture}/${goal}` : line.active_tribe_culture;
        status.appendChild(
            chip(player.name, `Tribe ${tribe} · ${progress} · ${line.culture_points}/11`)
        );
    }
}

function renderHint(board, inkas) {
    const hint = el('inkas-hint');
    if (!hint) {
        return;
    }
    const me = (board.players || []).find((p) => p.is_you);
    const owed = me && inkas.founding_player === me.name;
    hint.classList.toggle('hidden', !owed);
    if (owed) {
        hint.textContent =
            'Your tribe has declined. Found your next tribe: click an open '
            + 'intersection away from any road to place your free settlement.';
    }
}
