// The player's own hand and the bank, as chips.
//
// The hand is built once and painted in three places - the rail panel and the
// two dialogs that cover it - so a chip cannot say one thing in the panel and
// another in the dialog asking about it. That is why renderResourcePanel calls
// renderDialogHands and why the two stay in one file.

import { ckEnabled } from './cities-knights.js';
import { COMMODITY_ICONS, COMMODITY_TYPES, RESOURCE_ICONS } from './constants.js';
import { bankChipValue, bankDisplay, discardHandNote, resourceDisplay, tradeHandNote } from './dom.js';
import { findMyPlayer } from './player-view.js';
import { getBoard } from './state.js';

/**
 * One player's own cards as chips: the five resources, and the three
 * commodities where they are dealt.
 *
 * Built once and painted in three places - the rail's hand panel and the two
 * dialogs that cover it - so a chip cannot say one thing in the panel and
 * another in the dialog asking for it.
 *
 * @param {object} player - Own player entry from the board payload
 * @param {boolean} commodities - Whether to show cloth, coin and paper
 * @returns {string} - HTML for the chip row
 */
function handChips(player, commodities) {
    const resources = player.resources || {};
    let html = '';
    for (const type of ['wood', 'brick', 'sheep', 'wheat', 'ore']) {
        const count = resources[type] || 0;
        html += `<div class="resource res-${type}">${RESOURCE_ICONS[type]}${count}</div>`;
    }

    // Commodities sit in the same row as the resources: they are spent, traded
    // and discarded like them, and a separate box implied they were not.
    if (commodities) {
        const held = player.commodities || {};
        for (const type of COMMODITY_TYPES) {
            const count = held[type] || 0;
            html += `<div class="resource commodity com-${type}" title="${type}">`
                + `${COMMODITY_ICONS[type]}${count}</div>`;
        }
    }
    return html;
}

/**
 * Render resource panel - shows current user's resources
 */
export function renderResourcePanel() {
    if (!getBoard() || !getBoard().players) {
        return;
    }

    const player = findMyPlayer();
    if (!player) {
        return;
    }

    resourceDisplay.innerHTML = handChips(player, ckEnabled());
    renderDialogHands();
}

/**
 * Restate the hand inside the discard and trade dialogs.
 *
 * The tester could not see their cards while either dialog was up - both cover
 * the aside the hand panel lives in, and both are asking a question that can
 * only be answered from it. Rendered from the same payload on every board
 * update, so a card gained or lost while the dialog is open shows there too.
 */
export function renderDialogHands() {
    const player = findMyPlayer();
    if (!player) {
        return;
    }
    // Commodities are their own rule: the dialogs offer a row for them only
    // when the table deals them, and a chip for a card that cannot exist would
    // be a count of nothing.
    const commodities = getBoard()?.rules?.commodities === true;
    const chips = handChips(player, commodities);
    for (const strip of [discardHandNote, tradeHandNote]) {
        const row = strip?.querySelector('.resource-display');
        if (row) {
            row.innerHTML = chips;
        }
    }
}

/**
 * Render bank panel - shows bank resources as percentage
 */
export function renderBank() {
    if (!getBoard() || !getBoard().bank) {
        return;
    }
    
    const bank = getBoard().bank;
    const resourceIcons = {
        wood: '🌲',
        brick: '🧱',
        sheep: '🐑',
        wheat: '🌾',
        ore: '🪨'
    };
    const resourceNames = {
        wood: 'Wood',
        brick: 'Brick',
        sheep: 'Sheep',
        wheat: 'Wheat',
        ore: 'Ore'
    };
    
    const RESOURCE_LIMIT = 19;

    let html = '';
    for (const [type, count] of Object.entries(bank)) {
        const percentage = Math.round((count / RESOURCE_LIMIT) * 100 / 25) * 25;
        html += `<div class="bank-resource bank-${type}">${resourceIcons[type]}${percentage}%</div>`;
    }

    bankDisplay.innerHTML = html;

    // The one number worth reading without opening the panel: whether anything
    // has actually run out, because that is what changes what a trade is worth.
    if (bankChipValue) {
        const empty = Object.entries(bank)
            .filter(([, count]) => count === 0)
            .map(([type]) => RESOURCE_ICONS[type] || type);
        const total = Object.values(bank).reduce((sum, count) => sum + count, 0);
        bankChipValue.textContent = empty.length > 0
            ? `${total} cards · out: ${empty.join('')}`
            : `${total} cards`;
    }
}
