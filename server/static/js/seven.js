// The two dialogs a roll of seven opens: the discard, and the choice of who to
// rob.
//
// Both listeners here - the victim list and the discard submit - are delegated
// and register when this module is first evaluated. panels.js imports it at the
// top for that side effect.

import { COMMODITY_TYPES } from './constants.js';
import { discardAmountSpan, discardCommodityRow, discardHandNote, discardModal, submitDiscardBtn, victimList, victimModal } from './dom.js';
import { renderDialogHands } from './hand.js';
import { resourceName, resourceTile } from './icons.js';
import { displayError } from './notices.js';
import { emitGame } from './socket.js';
import { extraResourceTypes, getBoard, getDiscardAmount, getRobberVictims, resourceOrder, viewState } from './state.js';

/**
 * Everything a 7 counts, which is what a discard may name. The in-play resources
 * (the five on a standard board, plus cotton where a map deals it) and — on a
 * table that plays them — the three commodities: the engine takes both
 * (`clean_card_counts`), and a hand over the limit on commodities alone must be
 * able to pay.
 *
 * @returns {string[]}
 */
function discardableCards() {
    return [...resourceOrder(), ...COMMODITY_TYPES];
}

/**
 * Open the discard dialog for a fresh discard.
 * The inputs are zeroed here and nowhere else, so a board update that arrives
 * while the dialog is open cannot reset what has been typed into it.
 *
 * @param {number} amount - Cards the server says this player owes the bank
 */
export function openDiscardModal(amount) {
    discardAmountSpan.textContent = amount;
    // A cotton map's picker gains a cotton field; a standard board's is untouched.
    syncDiscardExtras();
    discardableCards().forEach(card => {
        const input = document.getElementById(`discard-${card}`);
        if (input) {
            input.value = 0;
        }
    });

    // Only the tables that play commodities have any to hand back. Read off
    // the running game's rules rather than off "is this Cities & Knights":
    // commodities is a switch of its own and a table may take it alone.
    const commodities = getBoard()?.rules?.commodities === true;
    discardCommodityRow?.classList.toggle('hidden', !commodities);

    renderDialogHands();
    syncDiscardState();
    discardModal.classList.add('show');
}

// --- Click-to-stage, mirroring the trade tray -----------------------------
//
// The tester asked for the discard to work like the trade menu: click a card in
// the hand to stage it, and let Confirm fire only once the owed count is met,
// rather than typing numbers and being told off on submit. The number inputs
// stay as the selection's source of truth (they survive board updates); the
// clicks and the gate drive them.

/** How many of a card the hand actually holds, so a stage cannot exceed it. */
function heldCount(card) {
    const me = (getBoard()?.players || []).find(p => p.name === viewState.identity.name);
    if (!me) {
        return 0;
    }
    const store = COMMODITY_TYPES.includes(card) ? me.commodities : me.resources;
    return (store || {})[card] || 0;
}

/**
 * Grow the discard picker with a field for each resource a map added on top of
 * the base five — cotton on a cotton map, nothing on a standard board. The
 * printed base-five rows are never touched, so a standard board's dialog is
 * byte-for-byte what it always was. Idempotent, and each injected field gets the
 * same live-total listener the static ones were wired with at load.
 */
function syncDiscardExtras() {
    const selector = discardModal?.querySelector('.resource-selector');
    if (!selector) {
        return;
    }
    selector.querySelectorAll('.res-extra').forEach(node => node.remove());
    for (const card of extraResourceTypes()) {
        selector.insertAdjacentHTML('beforeend',
            `<label class="res-extra">`
            + `${resourceTile(card, { label: resourceName(card) })} ${resourceName(card)}: `
            + `<input type="number" id="discard-${card}" min="0" max="10" value="0"></label>`);
        document.getElementById(`discard-${card}`)
            ?.addEventListener('input', syncDiscardState);
    }
}

/** The staged discard total across every card input. */
function discardTotal() {
    return discardableCards().reduce((sum, card) => {
        const input = document.getElementById(`discard-${card}`);
        return sum + (input ? (parseInt(input.value) || 0) : 0);
    }, 0);
}

/** Mark Confirm ready when the staged pile is exactly what is owed, and lift
 *  each staged hand chip the way the trade tray marks a card it holds.
 *
 *  Readiness is a cue, not a lock: the button stays clickable while the pile is
 *  short so a click still surfaces the "you owe N" refusal the submit handler
 *  raises (a real, tested behaviour) rather than silently doing nothing. */
function syncDiscardState() {
    submitDiscardBtn.classList.toggle('ready', discardTotal() === getDiscardAmount());
    const strip = discardHandNote?.querySelector('.resource-display');
    strip?.querySelectorAll('[data-card]').forEach(cell => {
        const input = document.getElementById(`discard-${cell.dataset.card}`);
        cell.classList.toggle('is-up', !!input && (parseInt(input.value) || 0) > 0);
    });
}

// Clicking a held card stages one more of it, cycling back to none once the
// whole held count is selected — the same gesture handleHandClick gives trade.
discardHandNote?.addEventListener('click', (event) => {
    const cell = event.target.closest('[data-card]');
    if (!cell) {
        return;
    }
    const input = document.getElementById(`discard-${cell.dataset.card}`);
    if (!input) {
        return;
    }
    const next = (parseInt(input.value) || 0) + 1;
    input.value = next > heldCount(cell.dataset.card) ? 0 : next;
    syncDiscardState();
});

// The number inputs stay usable directly; keep the gate honest when they change.
// The base five and commodities are wired here at load; a map's own field
// (cotton) is wired when it is injected in syncDiscardExtras.
discardableCards().forEach(card => {
    document.getElementById(`discard-${card}`)?.addEventListener('input', syncDiscardState);
});

// The hand chips are rebuilt on every board update; re-apply the lift after.
if (discardHandNote) {
    new MutationObserver(syncDiscardState).observe(discardHandNote, { childList: true, subtree: true });
}

// Whether the single-candidate answer has already gone. Reset by updateGameUI
// as soon as the server says nothing is pending.
let autoVictimSent = false;

/**
 * Ask who to rob - but only when there is actually a question.
 *
 * A dialog offering one button is not a choice, it is a click the player has to
 * make to carry on. With a single candidate the answer is settled here and the
 * modal never opens.
 */
export function offerVictimChoice() {
    const victims = getRobberVictims();

    if (victims.length === 1) {
        // This runs on every board payload while the flag is up, and the flag
        // stays up until the server has answered, so the send is latched. It is
        // cleared again the moment nothing is pending.
        if (!autoVictimSent) {
            autoVictimSent = true;
            emitGame('choose_robber_victim', { name: viewState.identity.name, victim: victims[0] });
        }
        victimModal.classList.remove('show');
        return;
    }

    if (victims.length === 0) {
        // Nothing to steal. The dialog has no way to close itself, so opening
        // it would strand the turn.
        victimModal.classList.remove('show');
        return;
    }

    renderVictimList();
    victimModal.classList.add('show');
}

export function renderVictimList() {
    victimList.innerHTML = '';
    
    const players = getBoard()?.players || [];
    
    getRobberVictims().forEach(victimName => {
        const player = players.find(p => p.name === victimName);
        const color = player?.color || '#cccccc';
        
        const item = document.createElement('div');
        item.className = 'victim-item';
        item.dataset.victim = victimName;

        // Built rather than interpolated: a player named with markup would
        // otherwise be parsed as HTML in everyone else's robber dialog.
        const swatch = document.createElement('div');
        swatch.className = 'victim-color';
        swatch.style.backgroundColor = color;
        item.appendChild(swatch);
        item.appendChild(document.createTextNode(victimName));

        victimList.appendChild(item);
    });
}

// One delegated listener - the victim list is rebuilt on every robber move
victimList.addEventListener('click', (event) => {
    const item = event.target.closest('[data-victim]');
    if (!item) {
        return;
    }
    emitGame('choose_robber_victim', { name: viewState.identity.name, victim: item.dataset.victim });
    victimModal.classList.remove('show');
});

submitDiscardBtn.addEventListener('click', () => {
    // Every card the limit counts, not the five resources: a commodity typed
    // into a row the submit ignored was the shape of the tester's report.
    const resources = {};
    discardableCards().forEach(card => {
        const input = document.getElementById(`discard-${card}`);
        resources[card] = input ? (parseInt(input.value) || 0) : 0;
    });

    const total = Object.values(resources).reduce((sum, count) => sum + count, 0);

    if (total !== getDiscardAmount()) {
        displayError(`You must discard exactly ${getDiscardAmount()} cards`);
        return;
    }
    
    emitGame('discard_resources', { name: viewState.identity.name, resources: resources });
});

/**
 * Forget that the single-candidate answer has gone.
 *
 * updateGameUI clears the latch the moment the server says nothing is pending.
 * That was an assignment while both lived in panels.js; the latch itself has
 * not moved out of the module that reads it.
 */
export function resetAutoVictim() {
    autoVictimSent = false;
}
