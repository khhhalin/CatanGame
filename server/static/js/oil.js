// Catan: Oil Springs panel. The oil supply, the shared disaster track, each
// player's oil and sequestered total, the Champion of the Environment, and the
// two turn actions — sequester an oil, or convert one into two of a resource.
// Read from `board.oil`. Gated on the individual `oil_tokens` rule, not on the
// presence of the sub-object. Mirrors fish.js: one render on every board update.

import { getBoard, isMyTurn } from './state.js';
import { emitGame } from './socket.js';

// Whether the convert-oil resource picker row is open.
let convertOpen = false;

function el(id) {
    return document.getElementById(id);
}

/**
 * Render the Oil Springs panel from the board, and hide it whole on a table
 * without the scenario. Called on every board update.
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
        convertOpen = false;
        return;
    }
    renderStatus(board, oil);
    renderActions(board, oil);
}

function chip(label, value) {
    const item = document.createElement('span');
    item.className = 'ep-supply-item';
    item.innerHTML = `${label} <strong>${value}</strong>`;
    return item;
}

function renderStatus(board, oil) {
    const status = el('oil-status');
    if (!status) {
        return;
    }
    status.textContent = '';
    if (oil.disaster_track !== undefined) {
        status.appendChild(chip('Disaster', `${oil.disaster_track}/5`));
        status.appendChild(chip('Tokens lost', `${oil.numbers_removed}/${oil.board_death_at}`));
    }
    status.appendChild(chip('Oil supply', oil.supply));
    if (oil.champion) {
        status.appendChild(chip('Champion', oil.champion));
    }
    for (const player of board.players || []) {
        const held = oil.oil?.[player.name] ?? 0;
        const seq = oil.sequestered?.[player.name] ?? 0;
        status.appendChild(chip(player.name, seq ? `${held} (${seq} seq)` : held));
    }
}

function renderActions(board, oil) {
    const actions = el('oil-actions');
    if (!actions) {
        return;
    }
    actions.textContent = '';
    const me = board.players?.find(p => p.is_you);
    const myOil = me ? (oil.oil?.[me.name] ?? 0) : 0;
    const mine = isMyTurn();
    if (!mine) {
        convertOpen = false;
    }

    // Sequester: allowed only if you have not used oil and not already
    // sequestered this turn. Gated on the sequester rule being in play.
    if (board.rules?.oil_sequester_vp === true) {
        const canSequester = mine && myOil > 0
            && !oil.sequestered_this_turn && (oil.used_oil_this_turn ?? 0) === 0;
        const seq = document.createElement('button');
        seq.type = 'button';
        seq.className = 'ep-action-btn';
        seq.id = 'oil-sequester';
        seq.textContent = 'Sequester oil';
        seq.disabled = !canSequester;
        seq.addEventListener('click', () => emitGame('sequester_oil', {}));
        actions.appendChild(seq);
    }

    // Convert: allowed while you hold oil and the track has room. Gated on the
    // disaster-track rule, which is what governs oil use.
    if (board.rules?.disaster_track === true) {
        const canConvert = mine && myOil > 0 && (oil.disaster_track ?? 0) < 5;
        const convert = document.createElement('button');
        convert.type = 'button';
        convert.className = 'ep-action-btn';
        convert.id = 'oil-convert';
        convert.textContent = 'Convert oil';
        convert.disabled = !canConvert;
        convert.addEventListener('click', () => {
            convertOpen = !convertOpen;
            renderOil();
        });
        actions.appendChild(convert);

        if (convertOpen && canConvert) {
            for (const resource of board.resource_types || []) {
                const pick = document.createElement('button');
                pick.type = 'button';
                pick.className = 'ep-action-btn oil-convert-opt';
                pick.dataset.resource = resource;
                pick.textContent = resource;
                pick.addEventListener('click', () => {
                    convertOpen = false;
                    emitGame('convert_oil', { resource });
                });
                actions.appendChild(pick);
            }
        }
    }
}
