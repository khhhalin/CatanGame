// Catan: Frenemies panel. The favour-token bag, each player's token count, the
// viewer's own tokens by guild, and the two earn-actions that need a click —
// gifting a resource to a player who is not ahead of you, and declining a steal
// on the desert. Read from `board.frenemies`. Gated on the individual
// `favour_tokens` rule, not on the presence of the sub-object. Mirrors oil.js:
// one render on every board update. Guild-hall redemption is added by chunk 2.

import { getBoard, isMyTurn, hasRolledDice } from './state.js';
import { emitGame } from './socket.js';

const GUILD_LABEL = {
    trader: 'Trader',
    merchant: 'Merchant',
    road_builder: 'Road Builder',
    scholar: 'Scholar',
    master_builder: 'Master Builder',
};

// Which opponent a gift is being aimed at, or null when the picker is closed.
let giftRecipient = null;
let giftOpen = false;

function el(id) {
    return document.getElementById(id);
}

/**
 * Render the Frenemies panel from the board, and hide it whole on a table
 * without the scenario. Called on every board update.
 */
export function renderFrenemies() {
    const panel = el('right-frenemies');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const state = board?.frenemies;
    const show = Boolean(state) && board?.rules?.favour_tokens === true;
    panel.classList.toggle('hidden', !show);
    if (!show) {
        giftOpen = false;
        giftRecipient = null;
        return;
    }
    renderStatus(board, state);
    renderActions(board, state);
}

function chip(label, value) {
    const item = document.createElement('span');
    item.className = 'ep-supply-item';
    item.innerHTML = `${label} <strong>${value}</strong>`;
    return item;
}

function renderStatus(board, state) {
    const status = el('frenemies-status');
    if (!status) {
        return;
    }
    status.textContent = '';
    status.appendChild(chip('Bag', state.bag_remaining));
    for (const player of board.players || []) {
        const count = state.counts?.[player.name] ?? 0;
        const markers = state.vp_markers?.[player.name] ?? 0;
        const label = markers ? `${player.name} (${markers} VP)` : player.name;
        status.appendChild(chip(label, count));
    }

    // The viewer's own tokens, broken out by guild — the one holding the table
    // does not see.
    const usable = state.your_favours?.usable || {};
    const locked = state.your_favours?.locked || {};
    for (const guild of Object.keys(GUILD_LABEL)) {
        const free = usable[guild] || 0;
        const held = locked[guild] || 0;
        if (free || held) {
            const value = held ? `${free} (+${held} locked)` : `${free}`;
            status.appendChild(chip(GUILD_LABEL[guild], value));
        }
    }
}

function renderActions(board, state) {
    const actions = el('frenemies-actions');
    if (!actions) {
        return;
    }
    actions.textContent = '';
    const me = board.players?.find(p => p.is_you);
    const mine = isMyTurn();

    // Decline a steal on the desert for a favour token.
    if (state.can_decline) {
        const decline = document.createElement('button');
        decline.type = 'button';
        decline.className = 'ep-action-btn';
        decline.id = 'frenemies-decline';
        decline.textContent = 'Decline the steal (earn a favour)';
        decline.addEventListener('click', () => emitGame('decline_steal', {}));
        actions.appendChild(decline);
    }

    // Gift one resource to an opponent who is not ahead of you, once a turn.
    const canGift = mine && hasRolledDice() && me
        && !state.gift_made_this_turn && sumHand(me.resources) > 0;
    if (canGift) {
        const gift = document.createElement('button');
        gift.type = 'button';
        gift.className = 'ep-action-btn';
        gift.id = 'frenemies-gift';
        gift.textContent = 'Gift a resource';
        gift.disabled = false;
        gift.addEventListener('click', () => {
            giftOpen = !giftOpen;
            giftRecipient = null;
            renderFrenemies();
        });
        actions.appendChild(gift);

        if (giftOpen) {
            renderGiftPicker(actions, board, me, state);
        }
    } else {
        giftOpen = false;
        giftRecipient = null;
    }
}

function renderGiftPicker(actions, board, me, state) {
    // Step one: which opponent not ahead of you.
    if (giftRecipient === null) {
        const myPoints = state.counts ? points(board, me.name) : 0;
        for (const player of board.players || []) {
            if (player.is_you) {
                continue;
            }
            const opt = document.createElement('button');
            opt.type = 'button';
            opt.className = 'ep-action-btn frenemies-gift-to';
            opt.dataset.recipient = player.name;
            opt.textContent = player.name;
            // Only players on as many visible points as you or fewer are legal.
            opt.disabled = points(board, player.name) > myPoints;
            opt.addEventListener('click', () => {
                giftRecipient = player.name;
                renderFrenemies();
            });
            actions.appendChild(opt);
        }
        return;
    }

    // Step two: which resource from your hand.
    for (const resource of Object.keys(me.resources || {})) {
        if ((me.resources[resource] || 0) <= 0) {
            continue;
        }
        const pick = document.createElement('button');
        pick.type = 'button';
        pick.className = 'ep-action-btn frenemies-gift-res';
        pick.dataset.resource = resource;
        pick.textContent = resource;
        pick.addEventListener('click', () => {
            const recipient = giftRecipient;
            giftOpen = false;
            giftRecipient = null;
            emitGame('gift_resource', { recipient, resource });
        });
        actions.appendChild(pick);
    }
}

function sumHand(resources) {
    return Object.values(resources || {}).reduce((total, n) => total + (n || 0), 0);
}

// A player's visible victory points, read off the scoreboard the board carries.
function points(board, name) {
    const player = board.players?.find(p => p.name === name);
    return player?.victory_points ?? 0;
}
