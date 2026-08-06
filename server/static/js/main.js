// Entry point. The imports below are the whole application: each module
// registers its own listeners as it evaluates, and `net.js` last of all binds
// the socket handlers that drive them.

import { progressCardHasNoFlow } from './cities-knights.js';
import { getCommandCatalogue } from './commands.js';
import { displayError } from './notices.js';
import { getBoard, getCurrentPlayer, getRole, isGameRunning, viewState } from './state.js';
import './board.js';
import './changelog.js';
import './seam.js';
import './overlays.js';
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
    // The slash commands the server offers this table, for the same reason as
    // the rules above: the command bar renders from the server's catalogue, and
    // a test holding its own copy could not notice it failing to draw one.
    getCommands: getCommandCatalogue,
    // Whether one progress card in the server's catalogue has no way to be
    // played at all. Asked of the catalogue rather than of a list in a test,
    // so a card added with no client flow is caught the day it is added.
    progressCardHasNoFlow,
    // What the next tap on the board would be an attempt at. A two-tap
    // placement - a knight move, a ship move - has a half-finished state that
    // nothing on screen names, so "it did nothing" and "it is waiting for the
    // second tap" are indistinguishable from the outside without this.
    getSelection: () => ({
        mode: viewState.selectedBuilding,
        knightMoveFrom: viewState.knightMoveFrom,
        shipMoveFrom: viewState.shipMoveFrom,
        pending: viewState.placement.pending,
        // Which progress card the board is armed for, and what has been picked
        // for it so far. Same reason: a card that takes two number tokens has a
        // half-finished state nothing on the board names.
        progressPick: viewState.progressPick
    })
};
