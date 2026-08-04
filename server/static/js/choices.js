// The pending-choice phase: the game stops and one named player decides.
//
// Eight rules need the server to interrupt play and ask a *particular* player
// to pick one of a set of legal options - which city the barbarians sack, which
// commodity a Commercial Harbor takes, which knight a Deserter lures away.
// While one is open the server refuses every action from everybody, so the two
// things this file has to put on screen are:
//
//   - to the chooser: the question and its answers;
//   - to everyone else: who the table is waiting for, and what for. A frozen
//     table with no explanation is exactly the failure this exists to prevent.
//
// Everything is rendered from `board.pending_choices`, never from the
// `choice_required` event. The board payload carries the same fields (with the
// options redacted for anyone but the chooser) and it is also what a reconnect
// or a page reload comes back to, so reading it here means a player who
// refreshes mid-question still gets asked. The event is a nudge, nothing more.
//
// The options are never re-derived. `option` is sent back to the server exactly
// as it was offered, because the recorded list is the server's allowlist and a
// value this client invented would be refused by it - correctly.

import { COMMODITY_ICONS, RESOURCE_ICONS } from './constants.js';
import { choiceContext, choiceIndicator, choiceOptions, choicePanel, choicePrompt, choiceWaitingText } from './dom.js';
import { emitGame } from './socket.js';
import { getBoard, viewState } from './state.js';

// The kinds whose options are vertex keys. A raw "3,-3,0" means nothing to a
// player, so these are highlighted on the board and described by the terrain
// they stand on instead of being listed as keys.
const VERTEX_KINDS = ['barbarian_city', 'deserter', 'deserter_placement'];

// What each kind is about, as a heading. The sentence under it is the server's
// own `prompt`: the wording lives in `game/pending_choice.py` so a refusal, a
// log line and this panel cannot drift apart.
const CHOICE_TITLES = {
    barbarian_city: '🏴‍☠️ The barbarians are sacking a city',
    progress_deck: '🎴 Draw a progress card',
    commercial_harbor: '⚓ Commercial Harbor',
    master_merchant: '💰 Master Merchant',
    spy: '🕵️ Spy',
    wedding: '💍 Wedding',
    deserter: '🏃 Deserter',
    deserter_placement: '⚔️ Your new knight',
};

// What a vertex option is, so "City on wheat 6, ore 9" reads as the thing being
// chosen rather than as a coordinate.
const VERTEX_NOUNS = {
    barbarian_city: 'City',
    deserter: 'Knight',
    deserter_placement: 'Stand',
};

const DECK_LABELS = { science: '🟢 Science', trade: '🟡 Trade', politics: '🔵 Politics' };

const KNIGHT_RANK_NAMES = { 1: 'Basic', 2: 'Strong', 3: 'Mighty' };

// Rebuilding the panel destroys focus, so it is only rebuilt when the question
// actually changed - and a Master Merchant asks the same kind twice in a row
// against a shrinking hand, so the options are part of the identity.
let renderedSignature = '';

/**
 * Every decision the table is waiting on, as this tab is entitled to see them.
 *
 * @returns {Array} - Pending choices from the board payload
 */
function pendingChoices() {
    const choices = getBoard()?.pending_choices;
    return Array.isArray(choices) ? choices : [];
}

/**
 * The decision this tab owes, or null.
 * Only this one carries an `options` list - the server sends the options to the
 * chooser's sockets alone, because they can be the contents of another
 * player's hand.
 *
 * @returns {object|null}
 */
export function myPendingChoice() {
    const me = viewState.identity.name;
    return pendingChoices().find(choice => choice.player === me) || null;
}

/**
 * The intersections to ring on the board, or an empty list.
 * Only ever this player's own question: highlighting somebody else's options
 * would show the table which cities are on offer before they have answered.
 *
 * @returns {Array<string>} - Vertex keys
 */
export function choiceHighlightVertices() {
    const mine = myPendingChoice();
    if (!mine || !VERTEX_KINDS.includes(mine.kind) || !Array.isArray(mine.options)) {
        return [];
    }
    return mine.options;
}

/**
 * Answer the open question with one of the options the server offered.
 *
 * @param {string} option - An entry of the offered list, verbatim
 */
function sendChoice(option) {
    const mine = myPendingChoice();
    if (!mine || !(mine.options || []).includes(option)) {
        return;
    }
    emitGame('make_choice', {
        name: viewState.identity.name, kind: mine.kind, option
    });
}

/**
 * Handle a tap on the board while a vertex-kind question is open.
 *
 * Consulted before placement, not after: a choice is owed by whoever the rule
 * names, who may not be the player on turn, and `currentPlacementKind` answers
 * null for everybody else.
 *
 * @param {number} clientX - Pointer clientX of the tap
 * @param {number} clientY - Pointer clientY of the tap
 * @returns {boolean} - Whether the tap was an answer
 */
export function handleChoiceTap(clientX, clientY) {
    const options = choiceHighlightVertices();
    if (options.length === 0) {
        return false;
    }
    const canvas = document.getElementById('board-canvas');
    const position = window.BoardRenderer.clientToBoard(canvas, clientX, clientY);
    const key = window.BoardRenderer.findNearestVertex(getBoard(), position.x, position.y);
    if (!key || !options.includes(key)) {
        // Still swallowed: while a choice is open the server refuses every
        // build anyway, so falling through to placement would only raise a
        // ghost that can never be confirmed.
        return true;
    }
    sendChoice(key);
    return true;
}

// ------------------------------------------------------------------ wording

/**
 * Describe an intersection by what it touches, so a player can find it.
 *
 * @param {string} kind - Choice kind, which decides the noun
 * @param {string} key - Vertex key
 * @returns {string}
 */
function describeVertex(kind, key) {
    const board = getBoard();
    const noun = VERTEX_NOUNS[kind] || 'Intersection';
    const neighbours = board?.vertices?.[key]?.neighbors?.hexes || [];
    const land = neighbours
        .map(hexKey => board.hexes?.[hexKey])
        .filter(hex => hex && hex.type !== 'ocean')
        .map(hex => (hex.number ? `${hex.type} ${hex.number}` : hex.type));
    return land.length > 0 ? `${noun} on ${land.join(', ')}` : `${noun} at ${key}`;
}

/**
 * A card type - a resource or a commodity - with its icon.
 *
 * @param {string} cardType - e.g. 'wheat' or 'cloth'
 * @returns {string}
 */
function describeCard(cardType) {
    const icon = RESOURCE_ICONS[cardType] || COMMODITY_ICONS[cardType] || '';
    return icon ? `${icon} ${cardType}` : cardType;
}

/**
 * What one option should say on its button.
 *
 * @param {object} choice - Pending choice from the payload
 * @param {string} option - One of its options
 * @returns {string}
 */
function optionLabel(choice, option) {
    if (VERTEX_KINDS.includes(choice.kind)) {
        return describeVertex(choice.kind, option);
    }
    if (choice.kind === 'progress_deck') {
        return DECK_LABELS[option] || option;
    }
    if (choice.kind === 'spy') {
        // The catalogue the server sends with every board is the one place a
        // card's name lives; naming them again here would be a second copy to
        // keep in step.
        const card = getBoard()?.cities_knights?.progress_cards?.[option];
        return card?.name || option;
    }
    return describeCard(option);
}

/**
 * The sentence under the heading: who is doing this to whom, and how much of it
 * is left.
 *
 * @param {object} choice - Pending choice from the payload
 * @returns {string}
 */
function describeContext(choice) {
    const context = choice.context || {};
    const left = context.left;
    // Master Merchant and Wedding take two cards one at a time, because the
    // second question has to be asked against the hand the first one left.
    const remaining = typeof left === 'number' ? ` (${left} still to go)` : '';

    if (choice.kind === 'commercial_harbor') {
        return `${context.to} offers you ${describeCard(context.resource)} for one commodity.`;
    }
    if (choice.kind === 'master_merchant') {
        return `Take a card out of ${context.victim}'s hand${remaining}.`;
    }
    if (choice.kind === 'wedding') {
        return `A wedding gift for ${context.to}${remaining}.`;
    }
    if (choice.kind === 'spy') {
        return `Take a progress card from ${context.victim}.`;
    }
    if (choice.kind === 'deserter') {
        return `${context.to} has lured one of your knights away.`;
    }
    if (choice.kind === 'deserter_placement') {
        const rank = KNIGHT_RANK_NAMES[context.rank] || '';
        return `Where the deserting ${rank} knight joins you.`.replace('  ', ' ');
    }
    if (choice.kind === 'progress_deck' && context.reason === 'defence') {
        return 'Your share of the joint defence against the barbarians.';
    }
    return '';
}

/**
 * "Waiting for Bob to choose which of his cities the barbarians sack."
 *
 * The prompt is written to the player who owes the answer, so it says "your".
 * Only the pronoun is rewritten - the wording itself stays the server's, so
 * this line and the refusal a player gets for acting anyway agree.
 *
 * @param {object} choice - Pending choice from the payload
 * @returns {string}
 */
function waitingSentence(choice) {
    const prompt = String(choice.prompt || 'decide').replace(/\byour\b/g, 'their');
    return `⏳ Waiting for ${choice.player} to ${prompt}`;
}

// ---------------------------------------------------------------- rendering

/**
 * Show, hide and fill the choice panel and the waiting indicator.
 * Called from every path that replaces the board payload.
 */
export function renderPendingChoices() {
    if (!choicePanel || !choiceIndicator) {
        return;
    }

    const mine = myPendingChoice();
    const others = pendingChoices().filter(choice => choice.player !== viewState.identity.name);

    if (mine) {
        renderMyChoice(mine);
    } else {
        hidePanel();
    }

    // An observer, or a player waiting on somebody else. The chooser is told by
    // the panel and does not need telling twice.
    if (!mine && others.length > 0) {
        choiceWaitingText.textContent = waitingSentence(others[0]);
        choiceIndicator.classList.remove('hidden');
    } else {
        choiceIndicator.classList.add('hidden');
    }
}

/**
 * Build the chooser's panel, but only when the question actually changed.
 *
 * @param {object} choice - This player's pending choice
 */
function renderMyChoice(choice) {
    const options = Array.isArray(choice.options) ? choice.options : [];
    const signature = `${choice.kind}|${JSON.stringify(choice.context)}|${options.join('|')}`;
    if (signature === renderedSignature) {
        return;
    }
    renderedSignature = signature;

    choicePrompt.textContent = CHOICE_TITLES[choice.kind] || 'Your decision';

    const prompt = String(choice.prompt || '');
    const sentence = prompt ? prompt.charAt(0).toUpperCase() + prompt.slice(1) + '.' : '';
    const context = describeContext(choice);
    choiceContext.textContent = [sentence, context].filter(Boolean).join(' ');

    const fragment = document.createDocumentFragment();

    if (VERTEX_KINDS.includes(choice.kind)) {
        const hint = document.createElement('div');
        hint.className = 'choice-hint';
        hint.textContent = 'Tap a ringed intersection on the board, or use a button below.';
        fragment.appendChild(hint);
    }

    options.forEach(option => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'choice-option';
        button.dataset.choiceOption = option;
        // Built rather than interpolated: an option is server data, and a card
        // name or a player's own text must never be parsed as markup here.
        button.textContent = optionLabel(choice, option);
        fragment.appendChild(button);
    });

    choiceOptions.innerHTML = '';
    choiceOptions.appendChild(fragment);
    choicePanel.classList.remove('hidden');
    takeChoiceFocus();
}

function hidePanel() {
    renderedSignature = '';
    choicePanel.classList.add('hidden');
    choiceOptions.innerHTML = '';
}

/**
 * Move focus onto the first answer as the question appears.
 *
 * Conditional for the same reason the placement ✓ is: focus belongs to the
 * player, and somebody part-way through a chat message must not have their
 * next keystroke answer a question they have not read.
 */
function takeChoiceFocus() {
    const active = document.activeElement;
    const typing = active instanceof HTMLElement
        && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName);
    if (typing) {
        return;
    }
    choiceOptions.querySelector('.choice-option')?.focus();
}

// One delegated listener - the option buttons are rebuilt on every question.
choiceOptions?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-choice-option]');
    if (button) {
        sendChoice(button.dataset.choiceOption);
    }
});
