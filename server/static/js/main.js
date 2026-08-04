// Entry point. The imports below are the whole application: each module
// registers its own listeners as it evaluates, and `net.js` last of all binds
// the socket handlers that drive them.

import { displayError } from './notices.js';
import { getBoard, getCurrentPlayer, getRole, isGameRunning, viewState } from './state.js';
import './board.js';
import './lobby.js';
import './panels.js';
import './cities-knights.js';
import './seafarers.js';
import './trade.js';
import './event-log.js';
import './net.js';

// Last-resort nets: an exception in a handler or a rejected promise otherwise
// leaves the player with a frozen board and no explanation
window.addEventListener('error', (event) => {
    console.error('Uncaught error:', event.error || event.message);
    displayError('Something went wrong. Reload the page if the game stops responding.');
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled rejection:', event.reason);
    displayError('Something went wrong. Reload the page if the game stops responding.');
});

// Read-only debug hook. Part IV of coding-rules.md asks for a way to dump the
// client's state on demand: reproducing a bug from one snapshot is far cheaper
// than reproducing it from a sequence of clicks, and the browser playthrough
// tests need to know which vertices are legal before they can click one.
window.__catanDebug = {
    getBoard,
    getUser: () => viewState.identity.name,
    getRole,
    getCurrentPlayer,
    isGameStarted: isGameRunning,
    // The catalogue the server sent and what the table has selected. A test
    // that copies the rule list into itself cannot notice the picker failing
    // to render a rule the server offers — which is how the map choices were
    // unselectable while every test passed.
    getRules: () => ({
        catalogue: viewState.server.rules.catalogue,
        selected: viewState.server.rules.selected,
        presets: viewState.server.rules.presets,
        locked: viewState.server.rules.locked,
    }),
    // What the next tap on the board would be an attempt at. A two-tap
    // placement - a knight move, a ship move - has a half-finished state that
    // nothing on screen names, so "it did nothing" and "it is waiting for the
    // second tap" are indistinguishable from the outside without this.
    getSelection: () => ({
        mode: viewState.selectedBuilding,
        knightMoveFrom: viewState.knightMoveFrom,
        shipMoveFrom: viewState.shipMoveFrom,
        pending: viewState.placement.pending
    })
};
