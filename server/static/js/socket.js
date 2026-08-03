// The Socket.IO connection, created exactly once.
//
// `io` is a global from the library's own script tag in the template, which is
// why it is read here rather than imported. Every other module imports this
// instance; a second `io()` call would open a second session and the server
// would see two players where there is one.

import { connectionStatus } from './dom.js';
import { displayError } from './notices.js';

/**
 * Stand-in socket used when the Socket.IO library failed to load (blocked CDN).
 * Keeps the rest of the file free of null checks - every emit is refused and
 * reported through the same notice region as any other error.
 */
function createOfflineSocket() {
    return {
        connected: false,
        on: () => {},
        emit: () => {}
    };
}

export const socketAvailable = typeof io === 'function';
export const socket = socketAvailable ? io() : createOfflineSocket();

/**
 * Emit a command to the server, refusing to do so while disconnected.
 * Socket.IO drops emits from a disconnected socket silently, which the player
 * experiences as the game ignoring them.
 *
 * @param {string} event - Socket.IO event name
 * @param {object} payload - Event payload
 * @returns {boolean} - Whether the emit was sent
 */
export function emitGame(event, payload) {
    if (!socket.connected) {
        displayError('Not connected to the server - your action was not sent.');
        return false;
    }
    socket.emit(event, payload);
    return true;
}

/**
 * Update the visible connection indicator.
 *
 * @param {string} state - 'connected', 'connecting' or 'offline'
 * @param {string} label - Text to show
 */
export function setConnectionStatus(state, label) {
    if (!connectionStatus) {
        return;
    }
    connectionStatus.className = `connection-status connection-${state}`;
    connectionStatus.textContent = label;
}
