// CATAN - The Helpers panel: the tile you hold and its one-shot advantage, an
// Activate affordance carrying whatever the tile needs, and the display of
// tiles you can exchange into. Read from `board.helpers` — the display pile,
// every player's held tile and the tile catalogue ride on the board payload's
// own `helpers_client_state`. Mirrors pirate_islands.js: one render on every
// board update that hides the whole panel on a table not playing the scenario.
//
// The exchange-or-flip that follows a use is a pending choice, drawn by the
// shared choices.js dialog, not here. No rule logic lives here beyond erring
// permissive: the button offers the action and the server checks the tile, the
// turn and the board before it does anything.

import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

function el(id) {
    return document.getElementById(id);
}

/** The helper subsystem's client state, or null off the scenario. */
function helperState(board) {
    return board?.rules?.helper_tiles ? (board.helpers || null) : null;
}

/**
 * Render the Helpers panel from the board, hidden whole on a table without the
 * scenario. Called on every board update.
 */
export function renderHelperTiles() {
    const panel = el('right-helpers');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const state = helperState(board);
    panel.classList.toggle('hidden', !state);
    if (!state) {
        return;
    }
    const me = viewState.identity.name;
    const held = (state.held || {})[me] || null;
    const tile = held ? (state.catalogue || {})[held.tile] : null;
    renderHeld(state, held, tile);
    renderActions(state, held, tile);
    renderDisplay(state);
}

/** The tile in front of you: name, advantage, which side is up, and its text. */
function renderHeld(state, held, tile) {
    const box = el('helper-held');
    if (!box) {
        return;
    }
    box.textContent = '';
    if (!held || !tile) {
        box.textContent = 'No helper tile in front of you.';
        return;
    }
    const title = document.createElement('div');
    title.className = 'helper-title';
    title.textContent = `${tile.name} — ${tile.title}`;
    box.appendChild(title);

    const side = document.createElement('span');
    side.className = `helper-side helper-side-${held.side}`;
    side.textContent = held.side === 'sun' ? '☀ Sun' : '☽ Moon';
    box.appendChild(side);

    const summary = document.createElement('div');
    summary.className = 'helper-summary';
    summary.textContent = tile.summary;
    box.appendChild(summary);
}

/**
 * The Activate control, plus one resource picker per resource the tile asks for.
 * Whatever the pickers hold rides along as params; the server ignores any it
 * does not need this time (the robber's hex may already fix Kaja's resource).
 */
function renderActions(state, held, tile) {
    const actions = el('helper-actions');
    if (!actions) {
        return;
    }
    actions.textContent = '';
    if (!held || !tile) {
        return;
    }
    const used = (state.used_this_turn || []).includes(viewState.identity.name);
    const pickers = [];
    (tile.needs || []).forEach((need, index) => {
        if (need !== 'resource') {
            return;
        }
        const picker = resourcePicker(`${held.tile}-res-${index}`);
        pickers.push(picker);
        actions.appendChild(picker);
    });

    const activate = document.createElement('button');
    activate.type = 'button';
    activate.className = 'ep-action-btn helper-activate';
    activate.textContent = used ? 'Helper used this turn' : 'Activate';
    activate.disabled = used || !canActOffTurn(tile);
    activate.addEventListener('click', () => {
        const params = {};
        if (pickers.length === 1) {
            params.resource = pickers[0].value;
        } else if (pickers.length > 1) {
            params.resources = pickers.map(picker => picker.value);
        }
        emitGame('activate_helper', { tile: held.tile, params });
    });
    actions.appendChild(activate);
}

/** Whether the seat may even attempt this tile now (own turn, bar exceptions). */
function canActOffTurn(tile) {
    // Resource compensation and protection from the 7 fire on any player's roll;
    // everything else is own-turn only. The server has the final say either way.
    if (tile.when === 'after_production' || tile.when === 'on_seven') {
        return true;
    }
    return isMyTurn();
}

/** A five-way resource dropdown, defaulting to wood. */
function resourcePicker(id) {
    const select = document.createElement('select');
    select.className = 'helper-resource';
    select.id = id;
    ['wood', 'brick', 'sheep', 'wheat', 'ore'].forEach(resource => {
        const option = document.createElement('option');
        option.value = resource;
        option.textContent = resource;
        select.appendChild(option);
    });
    return select;
}

/** The display: the tiles a player could exchange into, named. */
function renderDisplay(state) {
    const box = el('helper-display');
    if (!box) {
        return;
    }
    box.textContent = '';
    const pile = state.pile || [];
    const label = document.createElement('div');
    label.className = 'helper-display-label';
    label.textContent = pile.length
        ? `Display: ${pile.map(id => (state.catalogue[id] || {}).name || id).join(', ')}`
        : 'Display empty';
    box.appendChild(label);
}
