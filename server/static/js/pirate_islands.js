// The Pirate Islands panel: your warships and your own-colour fortress at a
// glance, plus a Build warship affordance (reveal a Knight to turn a ship into a
// warship) and an Attack fortress affordance (roll the die-combat). Read from
// `board.pirate_islands` — the fleet, the fortresses and every player's warship
// count ride on the board payload's own `pirate_islands_client_state`. Mirrors
// wonders.js: one render on every board update that hides the whole panel on a
// table not playing the scenario.
//
// No rule logic lives here beyond erring permissive: the buttons offer the
// actions, and the server checks the Knight, the ship, the route and the turn
// before it does anything. Its answer is what the board is drawn from.

import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

function el(id) {
    return document.getElementById(id);
}

/** The Pirate Islands scenario's client state, or null off the scenario. */
function pirateState(board) {
    const on = board?.rules?.pirate_fleet || board?.rules?.pirate_fortresses;
    return on ? (board.pirate_islands || null) : null;
}

/** This seat's own-colour fortress, or null. */
function myFortress(state, me) {
    return (state.fortresses || []).find(fort => fort.owner === me) || null;
}

/**
 * Render the Pirate Islands panel from the board, hidden whole on a table
 * without the scenario. Called on every board update.
 */
export function renderPirateIslands() {
    const panel = el('right-pirate');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const state = pirateState(board);
    panel.classList.toggle('hidden', !state);
    if (!state) {
        return;
    }
    renderStatus(state);
    renderActions(state);
}

/** The heading line: your warships, and your fortress's chits or its recapture. */
function renderStatus(state) {
    const status = el('pirate-status');
    if (!status) {
        return;
    }
    const me = viewState.identity.name;
    const warships = (state.warships || {})[me] || 0;
    const fort = myFortress(state, me);
    status.textContent = '';

    const ships = document.createElement('span');
    ships.className = 'ep-supply-item';
    ships.innerHTML = `Warships <strong>${warships}</strong>`;
    status.appendChild(ships);

    const fortress = document.createElement('span');
    fortress.className = 'ep-supply-item';
    if (!fort) {
        fortress.innerHTML = 'No fortress of your colour';
    } else if (fort.captured) {
        fortress.innerHTML = 'Fortress <strong>recaptured</strong>';
    } else {
        fortress.innerHTML = `Fortress chits <strong>${fort.chits}</strong>`;
    }
    status.appendChild(fortress);
}

/** The two buttons: Build warship and Attack fortress. */
function renderActions(state) {
    const actions = el('pirate-actions');
    if (!actions) {
        return;
    }
    const me = viewState.identity.name;
    const fort = myFortress(state, me);
    actions.textContent = '';

    const build = document.createElement('button');
    build.type = 'button';
    build.className = 'ep-action-btn pirate-build-warship';
    build.textContent = 'Build warship';
    build.disabled = !isMyTurn();
    build.addEventListener('click', () => emitGame('build_warship', {}));
    actions.appendChild(build);

    const attack = document.createElement('button');
    attack.type = 'button';
    attack.className = 'ep-action-btn pirate-attack-fortress';
    attack.textContent = 'Attack fortress';
    attack.disabled = !isMyTurn() || !fort || fort.captured;
    attack.addEventListener('click', () => emitGame('attack_pirate_fortress', {}));
    actions.appendChild(attack);
}
