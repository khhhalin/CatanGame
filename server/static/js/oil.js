// Catan: Oil Springs panel. The oil supply and every player's oil, read from
// `board.oil`. Later chunks add the disaster track and the consume/sequester
// affordances. Mirrors fish.js — one render, called on every board update, that
// hides the whole panel on a table not playing the scenario.

import { getBoard } from './state.js';

function el(id) {
    return document.getElementById(id);
}

/**
 * Render the Oil Springs panel from the board, and hide it whole on a table
 * without the scenario. Gated on the `oil_tokens` rule, not on the presence of
 * `board.oil`, so the individual-rule model holds. Called on every board update.
 */
export function renderOil() {
    const panel = el('right-oil');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const oil = board?.oil;
    const show = Boolean(oil) && board?.rules?.oil_tokens === true;
    panel.classList.toggle('hidden', !show);
    if (!show) {
        return;
    }
    renderStatus(board, oil);
}

function renderStatus(board, oil) {
    const status = el('oil-status');
    if (!status) {
        return;
    }
    status.textContent = '';
    const items = [['Oil supply', oil.supply]];
    for (const player of board.players || []) {
        items.push([player.name, oil.oil?.[player.name] ?? 0]);
    }
    for (const [label, value] of items) {
        const item = document.createElement('span');
        item.className = 'ep-supply-item';
        item.innerHTML = `${label} <strong>${value}</strong>`;
        status.appendChild(item);
    }
}
