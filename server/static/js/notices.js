// The client's only notification surface.

import { noticeRegion } from './dom.js';

const NOTICE_TIMEOUT_MS = 6000;

/**
 * Show a non-blocking notice in the live region.
 * This is the only error/notification surface in the client - nothing here
 * blocks the render loop or covers the board.
 *
 * @param {string} message - Human-readable text to show
 * @param {string} level - 'error', 'info' or 'success'
 * @param {boolean} sticky - Keep the notice until the next one replaces it
 */
export function showNotice(message, level = 'info', sticky = false) {
    console.log(`[notice:${level}]`, message);
    if (!noticeRegion) {
        return;
    }

    const notice = document.createElement('div');
    notice.className = `notice notice-${level}`;
    notice.textContent = message;
    noticeRegion.appendChild(notice);

    if (!sticky) {
        setTimeout(() => notice.remove(), NOTICE_TIMEOUT_MS);
    }
}

/**
 * Show a recoverable error to the player.
 */
export function displayError(message) {
    showNotice(message, 'error');
}

/**
 * Append a line to the running game log.
 * Kept separate from displayError so ordinary events do not read as failures.
 */
export function logToGameConsole(message) {
    showNotice(message, 'info');
}
