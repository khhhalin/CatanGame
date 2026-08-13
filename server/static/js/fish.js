// The Fishermen of Catan panel: the fish-token supply, this player's own hand
// (private — others see only a count), who holds the old boot, and the spend
// ladder. Read from `board.tb`. Mirrors ep.js — one render, called on every
// board update, that hides the whole panel on a table not playing the scenario.

import { displayError } from './notices.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn } from './state.js';

// benefit id -> the fish total it costs and whether it needs a pick.
const BENEFITS = {
    robber_off: { price: 2, pick: null },
    steal: { price: 3, pick: 'player' },
    bank_card: { price: 4, pick: 'resource' },
    free_road: { price: 5, pick: null },
    free_dev: { price: 7, pick: null },
};

// Which benefit's pick row is open, or null.
let pickFor = null;

// Whether the old-boot taker picker is open.
let bootPickOpen = false;

/** The smallest set of held tokens whose total reaches `price`, or null if the
 * hand cannot pay it. Greedy from the smallest token keeps the overspend low
 * for the 1/2/3 tokens the box holds. */
function tokensFor(hand, price) {
    const sorted = [...hand].sort((a, b) => a - b);
    const chosen = [];
    let total = 0;
    for (const token of sorted) {
        if (total >= price) {
            break;
        }
        chosen.push(token);
        total += token;
    }
    return total >= price ? chosen : null;
}

function el(id) {
    return document.getElementById(id);
}

/**
 * Render the Fishermen panel from the board, and hide it whole on a table
 * without the scenario (no `tb` state). Called on every board update.
 */
export function renderFishermen() {
    const panel = el('right-fish');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const tb = board?.tb;
    // Caravans, Barbarian Attack and the main scenario all build tb-state too,
    // so `tb` alone is not the Fishermen table — gate on a fish rule, or the
    // panel leaks (disabled, tokenless) into every other T&B scenario.
    const show = Boolean(tb) && board?.rules?.fish_tokens === true;
    panel.classList.toggle('hidden', !show);
    if (!show) {
        return;
    }

    renderSupply(tb);
    renderHand(tb);
    renderActions(board, tb);
    renderBoot(board, tb);
}

function renderSupply(tb) {
    const supply = el('fish-supply');
    supply.textContent = '';
    const bag = document.createElement('span');
    bag.className = 'ep-supply-item';
    bag.innerHTML = `Supply <strong>${tb.supply_count}</strong>`;
    supply.appendChild(bag);
    if (tb.old_boot_holder) {
        const boot = document.createElement('span');
        boot.className = 'ep-supply-item';
        boot.innerHTML = `Old boot <strong>${tb.old_boot_holder}</strong>`;
        supply.appendChild(boot);
    }
}

function renderHand(tb) {
    const hand = el('fish-hand');
    hand.textContent = '';
    const tokens = tb.fish_hand || [];
    if (!tokens.length) {
        const empty = document.createElement('span');
        empty.className = 'fish-empty';
        empty.textContent = 'No fish tokens';
        hand.appendChild(empty);
        return;
    }
    for (const value of tokens) {
        const pip = document.createElement('span');
        pip.className = 'fish-token';
        pip.dataset.fish = String(value);
        pip.textContent = '\u{1F41F}'.repeat(value);
        pip.title = `${value} fish`;
        hand.appendChild(pip);
    }
}

function renderActions(board, tb) {
    const hand = tb.fish_hand || [];
    const mine = isMyTurn();
    for (const [benefit, spec] of Object.entries(BENEFITS)) {
        const button = document.querySelector(`#fish-actions [data-benefit="${benefit}"]`);
        if (!button) {
            continue;
        }
        const affordable = tokensFor(hand, spec.price) !== null;
        button.disabled = !(mine && affordable);
    }
    if (!mine) {
        closePick();
    }
    renderPick(board, tb);
}

function renderPick(board, tb) {
    const pick = el('fish-pick');
    pick.textContent = '';
    pick.classList.toggle('hidden', pickFor === null);
    if (pickFor === null) {
        return;
    }
    const spec = BENEFITS[pickFor];
    if (spec.pick === 'player') {
        const me = board.players?.find(p => p.is_you);
        for (const player of board.players || []) {
            if (me && player.name === me.name) {
                continue;
            }
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'ep-action-btn fish-pick-opt';
            chip.dataset.target = player.name;
            chip.textContent = player.name;
            chip.addEventListener('click', () => fire(pickFor, { target: player.name }));
            pick.appendChild(chip);
        }
    } else if (spec.pick === 'resource') {
        for (const resource of board.resource_types || []) {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'ep-action-btn fish-pick-opt';
            chip.dataset.resource = resource;
            chip.textContent = resource;
            chip.addEventListener('click', () => fire(pickFor, { resource }));
            pick.appendChild(chip);
        }
    }
}

function closePick() {
    pickFor = null;
    const pick = el('fish-pick');
    if (pick) {
        pick.classList.add('hidden');
        pick.textContent = '';
    }
}

/** The players the boot may be passed to: everyone on as many victory points as
 * the holder or more, the holder aside (519). Empty when the holder leads
 * alone, which is when the boot must stay put (520). */
function eligibleBootTakers(board, tb) {
    const me = board.players?.find(p => p.is_you);
    if (!me || tb.old_boot_holder !== me.name) {
        return [];
    }
    const myPoints = me.victory_points ?? 0;
    return (board.players || []).filter(
        player => player.name !== me.name && (player.victory_points ?? 0) >= myPoints,
    );
}

function renderBoot(board, tb) {
    const actions = el('fish-boot-actions');
    const button = el('fish-pass-boot');
    if (!actions || !button) {
        return;
    }
    const me = board.players?.find(p => p.is_you);
    const holds = Boolean(me) && tb.old_boot_holder === me.name;
    // Only the holder, on their own turn, once they have rolled, may pass it (519).
    const canAct = holds && isMyTurn() && board?.has_rolled_dice === true;
    actions.classList.toggle('hidden', !canAct);
    if (!canAct) {
        closeBootPick();
        return;
    }
    const takers = eligibleBootTakers(board, tb);
    button.disabled = takers.length === 0;
    if (takers.length === 0) {
        closeBootPick();
    }
    renderBootPick(takers);
}

function renderBootPick(takers) {
    const pick = el('fish-boot-pick');
    if (!pick) {
        return;
    }
    pick.textContent = '';
    pick.classList.toggle('hidden', !bootPickOpen);
    if (!bootPickOpen) {
        return;
    }
    for (const player of takers) {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'ep-action-btn fish-pick-opt';
        chip.dataset.target = player.name;
        chip.textContent = player.name;
        chip.addEventListener('click', () => {
            emitGame('pass_old_boot', { target: player.name });
            closeBootPick();
        });
        pick.appendChild(chip);
    }
}

function closeBootPick() {
    bootPickOpen = false;
    const pick = el('fish-boot-pick');
    if (pick) {
        pick.classList.add('hidden');
        pick.textContent = '';
    }
}

function fire(benefit, extra) {
    const board = getBoard();
    const tokens = tokensFor(board?.tb?.fish_hand || [], BENEFITS[benefit].price);
    if (!tokens) {
        displayError('You do not hold enough fish for that');
        return;
    }
    emitGame('spend_fish', { benefit, tokens, ...extra });
    closePick();
}

function onBenefit(benefit) {
    const spec = BENEFITS[benefit];
    if (!spec) {
        return;
    }
    if (spec.pick) {
        // Toggle the pick row for this benefit.
        pickFor = pickFor === benefit ? null : benefit;
        renderFishermen();
        return;
    }
    fire(benefit, {});
}

for (const button of document.querySelectorAll('#fish-actions [data-benefit]')) {
    button.addEventListener('click', () => onBenefit(button.dataset.benefit));
}

const passBootButton = document.getElementById('fish-pass-boot');
if (passBootButton) {
    passBootButton.addEventListener('click', () => {
        bootPickOpen = !bootPickOpen;
        renderFishermen();
    });
}
