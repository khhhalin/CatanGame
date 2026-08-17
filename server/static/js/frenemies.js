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
// Which guild's redemption picker is open (merchant/trader need a resource), the
// trader's chosen give resource, and whether the exchange picker is open.
let redeemGuild = null;
let traderGive = null;
let exchangeOpen = false;

const GUILD_ORDER = ['trader', 'merchant', 'road_builder', 'scholar', 'master_builder'];

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
        redeemGuild = null;
        exchangeOpen = false;
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

    // The guild hall: redeem usable favours, or exchange one for a fresh draw.
    if (state.guild_hall && mine) {
        renderGuild(actions, board, state);
    } else {
        redeemGuild = null;
        exchangeOpen = false;
    }
}

function renderGuild(actions, board, state) {
    const usable = state.your_favours?.usable || {};
    const costs = state.costs || {};
    const redeemed = state.redeemed_this_turn;
    const exchanged = state.exchanged_this_turn;

    for (const guild of GUILD_ORDER) {
        const cost = costs[guild] ?? 1;
        const have = usable[guild] || 0;
        const affordable = have >= cost && !exchanged
            && !(guild === 'master_builder' && (state.vp_supply ?? 0) < 1);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ep-action-btn';
        btn.id = `frenemies-redeem-${guild}`;
        btn.textContent = `${GUILD_LABEL[guild]} (${cost})`;
        btn.disabled = !affordable;
        btn.addEventListener('click', () => {
            if (guild === 'merchant' || guild === 'trader') {
                redeemGuild = redeemGuild === guild ? null : guild;
                traderGive = null;
                renderFrenemies();
            } else {
                emitGame('redeem_favour', { guild });
            }
        });
        actions.appendChild(btn);

        if (redeemGuild === guild && affordable) {
            renderResourcePicker(actions, board, guild);
        }
    }

    // Exchange, only if you have taken no guild action this turn.
    const canExchange = !redeemed && !exchanged
        && Object.values(usable).some(n => n > 0) && (state.bag_remaining ?? 0) > 0;
    const exchange = document.createElement('button');
    exchange.type = 'button';
    exchange.className = 'ep-action-btn';
    exchange.id = 'frenemies-exchange';
    exchange.textContent = 'Exchange a token';
    exchange.disabled = !canExchange;
    exchange.addEventListener('click', () => {
        exchangeOpen = !exchangeOpen;
        renderFrenemies();
    });
    actions.appendChild(exchange);

    if (exchangeOpen && canExchange) {
        for (const guild of GUILD_ORDER) {
            if ((usable[guild] || 0) <= 0) {
                continue;
            }
            const ret = document.createElement('button');
            ret.type = 'button';
            ret.className = 'ep-action-btn frenemies-exchange-opt';
            ret.dataset.guild = guild;
            ret.textContent = `Return ${GUILD_LABEL[guild]}`;
            ret.addEventListener('click', () => {
                exchangeOpen = false;
                emitGame('exchange_favour', { return: guild });
            });
            actions.appendChild(ret);
        }
    }
}

function renderResourcePicker(actions, board, guild) {
    const resources = board.resource_types || [];
    // The traders take a give resource first, then the different receive one.
    if (guild === 'trader' && traderGive === null) {
        for (const resource of resources) {
            const opt = resourceButton(resource, `frenemies-trader-give-${resource}`);
            opt.addEventListener('click', () => {
                traderGive = resource;
                renderFrenemies();
            });
            actions.appendChild(opt);
        }
        return;
    }
    for (const resource of resources) {
        if (guild === 'trader' && resource === traderGive) {
            continue;  // the traders swap for a different resource
        }
        const id = guild === 'trader'
            ? `frenemies-trader-recv-${resource}`
            : `frenemies-merchant-${resource}`;
        const opt = resourceButton(resource, id);
        opt.addEventListener('click', () => {
            const payload = guild === 'trader'
                ? { guild, give: traderGive, receive: resource }
                : { guild, resource };
            redeemGuild = null;
            traderGive = null;
            emitGame('redeem_favour', payload);
        });
        actions.appendChild(opt);
    }
}

function resourceButton(resource, id) {
    const opt = document.createElement('button');
    opt.type = 'button';
    opt.className = 'ep-action-btn frenemies-res-opt';
    opt.id = id;
    opt.dataset.resource = resource;
    opt.textContent = resource;
    return opt;
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
