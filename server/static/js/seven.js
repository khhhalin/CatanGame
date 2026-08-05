// The two dialogs a roll of seven opens: the discard, and the choice of who to
// rob.
//
// Both listeners here - the victim list and the discard submit - are delegated
// and register when this module is first evaluated. panels.js imports it at the
// top for that side effect.

import { COMMODITY_TYPES } from './constants.js';
import { discardAmountSpan, discardCommodityRow, discardModal, submitDiscardBtn, victimList, victimModal } from './dom.js';
import { renderDialogHands } from './hand.js';
import { displayError } from './notices.js';
import { emitGame } from './socket.js';
import { getBoard, getDiscardAmount, getRobberVictims, viewState } from './state.js';

// Everything a 7 counts, which is what a discard may name. The five resources
// and - on a table that plays them - the three commodities: the engine takes
// both (`clean_card_counts`), and a hand that is over the limit on commodities
// alone must be able to pay.
const DISCARDABLE_CARDS = ['wood', 'brick', 'sheep', 'wheat', 'ore', ...COMMODITY_TYPES];

/**
 * Open the discard dialog for a fresh discard.
 * The inputs are zeroed here and nowhere else, so a board update that arrives
 * while the dialog is open cannot reset what has been typed into it.
 *
 * @param {number} amount - Cards the server says this player owes the bank
 */
export function openDiscardModal(amount) {
    discardAmountSpan.textContent = amount;
    DISCARDABLE_CARDS.forEach(card => {
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
    discardModal.classList.add('show');
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
    DISCARDABLE_CARDS.forEach(card => {
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
