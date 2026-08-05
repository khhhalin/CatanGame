// The player's own hand and the bank, as filled coloured tiles.
//
// The hand is built once and painted in three places - the rail panel and the
// two dialogs that cover it - so a chip cannot say one thing in the panel and
// another in the dialog asking about it. That is why renderResourcePanel calls
// renderDialogHands and why the two stay in one file.

import { ckEnabled } from './cities-knights.js';
import { COMMODITY_TYPES } from './constants.js';
import { bankChipValue, bankDisplay, discardHandNote, resourceDisplay, tradeHandNote } from './dom.js';
import { resourceTile } from './icons.js';
import { findMyPlayer } from './player-view.js';
import { getBoard } from './state.js';

// Board order for the five base resources, shared by the hand and the bank.
const RESOURCE_ORDER = ['wood', 'brick', 'sheep', 'wheat', 'ore'];

// The accessible name for a tile: its terrain colour is the only thing saying
// which card the count beside it belongs to, so the tile carries the label.
const CARD_NAMES = {
    wood: 'Wood', brick: 'Brick', sheep: 'Sheep', wheat: 'Wheat', ore: 'Ore',
    cloth: 'Cloth', coin: 'Coin', paper: 'Paper',
};

/**
 * One held card: its coloured tile and a large count. A count of zero is greyed
 * (`.spent`) rather than dropped, so the gap itself reads as "none of this".
 *
 * @param {string} card - Resource or commodity id
 * @param {number} count - How many are held
 * @returns {string}
 */
function resourceCell(card, count) {
    const spent = count === 0 ? ' spent' : '';
    return `<div class="res-cell${spent}">`
        + resourceTile(card, { label: CARD_NAMES[card] || card })
        + `<span class="count num">${count}</span></div>`;
}

/**
 * One player's own cards as tiles: the five resources, and the three
 * commodities where they are dealt.
 *
 * Built once and painted in three places - the rail's hand panel and the two
 * dialogs that cover it - so a chip cannot say one thing in the panel and
 * another in the dialog asking for it.
 *
 * @param {object} player - Own player entry from the board payload
 * @param {boolean} commodities - Whether to show cloth, coin and paper
 * @returns {string} - HTML for the tile row
 */
function handChips(player, commodities) {
    const resources = player.resources || {};
    let html = '<div class="res-row">';
    for (const type of RESOURCE_ORDER) {
        html += resourceCell(type, resources[type] || 0);
    }

    // Commodities sit in the same row as the resources: they are spent, traded
    // and discarded like them, and a separate box implied they were not.
    if (commodities) {
        const held = player.commodities || {};
        for (const type of COMMODITY_TYPES) {
            html += resourceCell(type, held[type] || 0);
        }
    }
    return html + '</div>';
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
 * Render bank panel - a tile, a thin stock meter and the real card count per
 * resource, so "how close is the bank to running out" is legible at a glance.
 *
 * The meter's full mark is `bank_resource_limit`, read from the table's rules
 * rather than a copy here: a table that raises the limit used to drive the old
 * hardcoded 19 past 100%.
 */
export function renderBank() {
    if (!getBoard() || !getBoard().bank) {
        return;
    }

    const bank = getBoard().bank;
    // The server owns the per-resource ceiling; reading it here is what keeps
    // the meter honest when a table sets it above the base-game 19. The fallback
    // only ever bites a payload with no rules at all, which a live board is not.
    const limit = getBoard().rules?.bank_resource_limit ?? 19;

    let html = '<div class="bank-row">';
    for (const type of RESOURCE_ORDER) {
        const count = bank[type] || 0;
        const width = Math.max(0, Math.min(100, Math.round((count / limit) * 100)));
        // --tile drives the meter fill (see .bank-cell .meter i); the tile
        // itself carries its own colour through resourceTile's t-* class.
        html += `<div class="bank-cell" style="--tile: var(--terrain-${type})">`
            + resourceTile(type, { label: CARD_NAMES[type] || type })
            + `<span class="meter"><i style="width: ${width}%"></i></span>`
            + `<span class="pct num">${count}</span></div>`;
    }

    bankDisplay.innerHTML = html + '</div>';

    // The one number worth reading without opening the panel: whether anything
    // has actually run out, because that is what changes what a trade is worth.
    if (bankChipValue) {
        const empty = Object.entries(bank)
            .filter(([, count]) => count === 0)
            .map(([type]) => CARD_NAMES[type] || type);
        const total = Object.values(bank).reduce((sum, count) => sum + count, 0);
        bankChipValue.textContent = empty.length > 0
            ? `${total} cards · out: ${empty.join(', ')}`
            : `${total} cards`;
    }
}
