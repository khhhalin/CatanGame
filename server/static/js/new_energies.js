// CATAN: New Energies panel. The shared global-footprint level, each player's
// local footprint and energy, the event-disc bag count and this turn's draw,
// and the one energy action a player drives without a board click — spending
// 2 energy for a resource or science card. Read from `board.new_energies`.
// Gated on the individual `power_plants` rule, not the presence of the object.
// Mirrors oil.js: one render on every board update.

import { getBoard, isMyTurn } from './state.js';
import { emitGame } from './socket.js';

// Whether the buy-card resource picker row is open.
let buyOpen = false;

function el(id) {
    return document.getElementById(id);
}

/**
 * Render the New Energies panel from the board, and hide it whole on a table
 * without the scenario. Called on every board update.
 */
export function renderNewEnergies() {
    const panel = el('right-new-energies');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const ne = board?.new_energies;
    const show = Boolean(ne) && board?.rules?.power_plants === true;
    panel.classList.toggle('hidden', !show);
    if (!show) {
        buyOpen = false;
        return;
    }
    renderStatus(board, ne);
    renderActions(board, ne);
}

function chip(label, value) {
    const item = document.createElement('span');
    item.className = 'ep-supply-item';
    item.innerHTML = `${label} <strong>${value}</strong>`;
    return item;
}

function renderStatus(board, ne) {
    const status = el('new-energies-status');
    if (!status) {
        return;
    }
    status.textContent = '';

    const footprint = ne.global_footprint;
    if (footprint) {
        status.appendChild(chip('Footprint', `${footprint.level}/${footprint.max}`));
    }
    if (ne.events) {
        status.appendChild(chip('Bag', ne.events.bag));
        status.appendChild(chip('Draw', ne.events.draw_count));
    }
    for (const player of board.players || []) {
        const energy = ne.energy?.[player.name] ?? 0;
        const lf = footprint?.local?.[player.name];
        const label = lf === undefined ? player.name : `${player.name} (LF ${lf})`;
        status.appendChild(chip(label, `${energy}⚡`));
    }
}

function renderActions(board, ne) {
    const actions = el('new-energies-actions');
    if (!actions) {
        return;
    }
    actions.textContent = '';
    const me = board.players?.find(p => p.is_you);
    const myEnergy = me ? (ne.energy?.[me.name] ?? 0) : 0;
    const mine = isMyTurn();
    if (!mine) {
        buyOpen = false;
    }

    const perCard = ne.energy_per_card ?? 2;
    const canBuy = mine && myEnergy >= perCard;
    const buy = document.createElement('button');
    buy.type = 'button';
    buy.className = 'ep-action-btn';
    buy.id = 'new-energies-buy';
    buy.textContent = `Spend ${perCard} energy`;
    buy.disabled = !canBuy;
    buy.addEventListener('click', () => {
        buyOpen = !buyOpen;
        renderNewEnergies();
    });
    actions.appendChild(buy);

    if (buyOpen && canBuy) {
        const options = [...(board.resource_types || []), 'science'];
        for (const card of options) {
            const pick = document.createElement('button');
            pick.type = 'button';
            pick.className = 'ep-action-btn new-energies-buy-opt';
            pick.dataset.card = card;
            pick.textContent = card;
            pick.addEventListener('click', () => {
                buyOpen = false;
                emitGame('spend_energy', { card });
            });
            actions.appendChild(pick);
        }
    }
}
