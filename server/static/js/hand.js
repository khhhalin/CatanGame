// The player's own hand and the bank.
//
// The hand shows in three places from one payload, so no two can disagree about
// what is held: the physical fan of cards in the bottom tray (renderResourcePanel)
// and the compact tile restatement inside the discard and trade dialogs that
// cover it (renderDialogHands). Both read the same player entry and iterate the
// same order, so a count in the fan and the same count in a dialog are the same
// number. They differ only in form - a fanned card on the table versus a small
// tile in a modal - which is why there are two renderers and not one.
//
// CLICK-TO-TRADE HOOK (for the trade component): every fan card carries
// `data-card="<resource|commodity id>"` and toggles the `.is-up` class to show
// it lifted into an offer. Bind to `#resource-display .hand-card`, read
// `dataset.card`, and add/remove `is-up`; nothing here consumes the click.

import { ckEnabled } from './cities-knights.js';
import { COMMODITY_TYPES } from './constants.js';
import { bankChipValue, bankDisplay, discardHandNote, resourceDisplay, tradeHandNote } from './dom.js';
import { icon, resourceTile } from './icons.js';
import { findMyPlayer } from './player-view.js';
import { getBoard } from './state.js';

// Board order for the five base resources, shared by the hand and the bank.
const RESOURCE_ORDER = ['wood', 'brick', 'sheep', 'wheat', 'ore'];

// The tile colour class each holdable draws its terrain fill from - the same
// `.t-*` variants the icon set and pickers use, so a card and a picker tile for
// the same resource are the same colour.
const TILE_VARIANT = {
    wood: 't-wood', brick: 't-brick', sheep: 't-sheep', wheat: 't-wheat', ore: 't-ore',
    cloth: 't-cloth', coin: 't-coin', paper: 't-paper',
};

// The accessible name for a tile: its terrain colour is the only thing saying
// which card the count beside it belongs to, so the tile carries the label.
const CARD_NAMES = {
    wood: 'Wood', brick: 'Brick', sheep: 'Sheep', wheat: 'Wheat', ore: 'Ore',
    cloth: 'Cloth', coin: 'Coin', paper: 'Paper',
};

/**
 * One physical hand card: a terrain-coloured face with the resource glyph, a
 * count in the top corner and a label strip along the bottom. A count of zero
 * greys the whole card (`.spent`) rather than dropping it, so the gap in the
 * fan itself reads as "none of this".
 *
 * The card face carries the terrain fill (not a nested tile) so the corner
 * count sits directly on the colour it is checked for contrast against - the
 * same relationship the WCAG sweep walks, so what passes is what is painted.
 *
 * @param {string} card - Resource or commodity id
 * @param {number} count - How many are held
 * @param {number} rotation - Fan angle in degrees for this card's place in the hand
 * @returns {string}
 */
function handCard(card, count, rotation) {
    const spent = count === 0 ? ' spent' : '';
    const variant = TILE_VARIANT[card] || '';
    const name = CARD_NAMES[card] || card;
    return `<div class="hand-card ${variant}${spent}" data-card="${card}"`
        + ` style="--rot: ${rotation}deg">`
        + `<span class="hand-card-count num">${count}</span>`
        + `<span class="hand-card-face">${icon(card, { cls: 'hand-card-glyph' })}</span>`
        + `<span class="hand-card-label">${name}</span>`
        + '</div>';
}

/**
 * The player's hand as a fan of physical cards: the five resources, and the
 * three commodities where the table deals them. Cards are rotated symmetrically
 * about the centre so the row reads as a held fan.
 *
 * @param {object} player - Own player entry from the board payload
 * @param {boolean} commodities - Whether to show cloth, coin and paper
 * @returns {string} - HTML for the fan
 */
function handFan(player, commodities) {
    const resources = player.resources || {};
    const cards = RESOURCE_ORDER.map((type) => [type, resources[type] || 0]);

    // Commodities join the fan: they are spent, traded and discarded like
    // resources, and a separate row implied they were not.
    if (commodities) {
        const held = player.commodities || {};
        for (const type of COMMODITY_TYPES) {
            cards.push([type, held[type] || 0]);
        }
    }

    // Spread narrows as the fan grows, so eight cards do not swing as wide as
    // five. The angles are symmetric about the middle card.
    const step = Math.min(4, 30 / cards.length);
    const centre = (cards.length - 1) / 2;
    const html = cards
        .map(([type, count], index) => handCard(type, count, (index - centre) * step))
        .join('');
    return `<div class="hand-fan">${html}</div>`;
}

/**
 * One held card as a compact tile: its coloured tile and a count. Used inside
 * the dialogs that restate the hand.
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
 * The hand as a compact tile row for the discard and trade dialogs, which have
 * no room for the fan and only need the counts legible while asking about them.
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

    if (commodities) {
        const held = player.commodities || {};
        for (const type of COMMODITY_TYPES) {
            html += resourceCell(type, held[type] || 0);
        }
    }
    return html + '</div>';
}

/**
 * Render resource panel - the player's fan of physical cards in the bottom tray.
 */
export function renderResourcePanel() {
    if (!getBoard() || !getBoard().players) {
        return;
    }

    const player = findMyPlayer();
    if (!player) {
        return;
    }

    resourceDisplay.innerHTML = handFan(player, ckEnabled());
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
