// Which player this socket is. Its own module because it is the only thing the
// expansion modules wanted from panels.js, and reaching back for it closed an
// import cycle - panels -> cities-knights -> panels, and the same by way of
// seafarers.js - which a `const` read across would have turned into a
// load-order bug.

import { getBoard, viewState } from './state.js';

/**
 * Find this socket's own player entry in the board data.
 * Only that entry carries populated `resources` and `dev_cards`; every other
 * player is sent as counts only.
 *
 * @returns {object|null} - Own player entry, or null (e.g. for observers)
 */
export function findMyPlayer() {
    const players = getBoard()?.players || [];
    return players.find(p => p.is_you) || players.find(p => p.name === viewState.identity.name) || null;
}
