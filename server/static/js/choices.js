// The pending-choice phase: the game stops and one named player decides.
//
// Nine rules need the server to interrupt play and ask a *particular* player
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

import { resourceTile, statusIcon } from './icons.js';
import { choiceContext, choiceIndicator, choiceOptions, choicePanel, choicePrompt, choiceWaitingText } from './dom.js';
import { emitGame } from './socket.js';
import { getBoard, viewState } from './state.js';

// The kinds whose options are vertex keys. A raw "3,-3,0" means nothing to a
// player, so these are highlighted on the board and described by the terrain
// they stand on instead of being listed as keys.
const VERTEX_KINDS = ['barbarian_city', 'deserter', 'deserter_placement',
    'helper_knight_to_building'];

// The kinds whose options are edge keys and are answered by tapping a ringed
// path on the board, the way the vertex kinds are answered by tapping a ringed
// intersection. A raw edge key means nothing to a player, so - like the vertex
// kinds - these are highlighted on the board and their buttons describe the
// terrain the path runs between instead of listing a coordinate.
const EDGE_CHOICE_KINDS = ['helper_makeshift_road', 'helper_move_road_from',
    'helper_move_road_to'];

// What each kind is about, as a heading. The sentence under it is the server's
// own `prompt`: the wording lives in `game/pending_choice.py` so a refusal, a
// log line and this panel cannot drift apart.
const CHOICE_TITLES = {
    barbarian_city: 'The barbarians are sacking a city',
    progress_deck: 'Draw a progress card',
    commercial_harbor: 'Commercial Harbor',
    merchant_fleet: 'Merchant Fleet',
    master_merchant: 'Master Merchant',
    spy: 'Spy',
    wedding: 'Wedding',
    deserter: 'Deserter',
    deserter_placement: 'Your new knight',
    camel_placement: 'Place the camel',
    intrigue_coast: 'Intrigue',
    treason_source: 'Treason',
    treason_destination: 'Treason',
    gold_field_choice: 'Gold field',
    gift_harbor: 'Place your gift harbour',
    helper_makeshift_road: 'Makeshift road',
    helper_move_road_from: 'Move a road',
    helper_move_road_to: 'Move a road',
    helper_knight_to_building: 'Assign a knight',
};

// The line icon that leads each heading, keyed by what the choice is about, not
// by a glyph. Decorative: the title text beside it carries the meaning, so the
// icon is aria-hidden. `spy` reuses the dev/progress glyph (it steals a progress
// card) and `wedding` the hand glyph (it hands cards across the table) - the set
// has no glyph of its own for either.
const CHOICE_ICONS = {
    barbarian_city: 'city',
    progress_deck: 'progress',
    commercial_harbor: 'harbormaster',
    merchant_fleet: 'ship',
    master_merchant: 'merchant',
    spy: 'progress',
    wedding: 'hand',
    deserter: 'knight',
    deserter_placement: 'knight',
    intrigue_coast: 'harbormaster',
    treason_source: 'harbormaster',
    treason_destination: 'harbormaster',
    gold_field_choice: 'hand',
    gift_harbor: 'harbormaster',
    helper_makeshift_road: 'road',
    helper_move_road_from: 'road',
    helper_move_road_to: 'road',
    helper_knight_to_building: 'knight',
};

// The kinds whose options are a coastal hex key. Like the camel's path, a raw
// "0,-3,3" means nothing, so these are described by the terrain they name.
const HEX_KINDS = ['intrigue_coast', 'treason_source', 'treason_destination'];

// What a vertex option is, so "City on wheat 6, ore 9" reads as the thing being
// chosen rather than as a coordinate.
const VERTEX_NOUNS = {
    barbarian_city: 'City',
    deserter: 'Knight',
    deserter_placement: 'Stand',
    helper_knight_to_building: 'Build',
};

// The piece a vertex option stands for, so its button leads with that piece's
// line icon. A deserting knight's new stand is still a knight.
const VERTEX_ICONS = {
    barbarian_city: 'city',
    deserter: 'knight',
    deserter_placement: 'knight',
    helper_knight_to_building: 'settlement',
};

// The kinds whose options are a held card - a resource or a commodity. Their
// buttons are a filled coloured tile that names itself, with no text beside it.
const CARD_KINDS = ['commercial_harbor', 'merchant_fleet', 'master_merchant', 'wedding',
    'gold_field_choice'];

const DECK_LABELS = { science: 'Science', trade: 'Trade', politics: 'Politics' };

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
export function choiceHighlightKeys() {
    const mine = myPendingChoice();
    if (!mine || !Array.isArray(mine.options)) {
        return [];
    }
    if (VERTEX_KINDS.includes(mine.kind) || EDGE_CHOICE_KINDS.includes(mine.kind)) {
        return mine.options;
    }
    return [];
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
    const mine = myPendingChoice();
    if (!mine || !Array.isArray(mine.options)) {
        return false;
    }
    const isVertex = VERTEX_KINDS.includes(mine.kind);
    const isEdge = EDGE_CHOICE_KINDS.includes(mine.kind);
    if (!isVertex && !isEdge) {
        return false;
    }
    const canvas = document.getElementById('board-canvas');
    const position = window.BoardRenderer.clientToBoard(canvas, clientX, clientY);
    // An edge kind snaps to the nearest path, a vertex kind to the nearest
    // intersection - the same two hit-tests placement uses.
    const key = isEdge
        ? window.BoardRenderer.findNearestEdge(getBoard(), position.x, position.y)
        : window.BoardRenderer.findNearestVertex(getBoard(), position.x, position.y);
    if (!key || !mine.options.includes(key)) {
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
 * A card type - a resource or a commodity - named in prose.
 *
 * @param {string} cardType - e.g. 'wheat' or 'cloth'
 * @returns {string}
 */
function describeCard(cardType) {
    return cardType;
}

/**
 * The icon that leads one option's button. A held card is a filled coloured
 * tile that names itself (so it carries a label and stands without text); every
 * other option pairs a decorative line icon with the text below.
 *
 * @param {object} choice - Pending choice from the payload
 * @param {string} option - One of its options
 * @returns {string} - Icon markup, or '' when the kind has none
 */
function optionIcon(choice, option) {
    if (CARD_KINDS.includes(choice.kind)) {
        const label = option.charAt(0).toUpperCase() + option.slice(1);
        return resourceTile(option, { label });
    }
    if (VERTEX_KINDS.includes(choice.kind)) {
        return statusIcon(VERTEX_ICONS[choice.kind]);
    }
    if (choice.kind === 'progress_deck') {
        // The option is the deck itself, so the glyph names which deck.
        return statusIcon(DECK_LABELS[option] ? `progress_${option}` : 'progress');
    }
    if (choice.kind === 'spy') {
        return statusIcon('progress');
    }
    return '';
}

/**
 * What one option should say on its button, beside its icon. Empty for the card
 * kinds, whose labelled tile is the whole option.
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
    if (choice.kind === 'camel_placement' || choice.kind === 'gift_harbor'
        || EDGE_CHOICE_KINDS.includes(choice.kind)) {
        return describeEdge(option);
    }
    if (HEX_KINDS.includes(choice.kind)) {
        return describeHex(option);
    }
    return '';
}

/**
 * Describe a coastal hex by its terrain and number, so an Intrigue coast option
 * reads as "Coast on wheat 5" rather than a bare coordinate.
 *
 * @param {string} key - Hex key
 * @returns {string}
 */
function describeHex(key) {
    const hex = getBoard()?.hexes?.[key];
    if (!hex) {
        return `Coast at ${key}`;
    }
    return hex.number ? `Coast on ${hex.type} ${hex.number}` : `Coast on ${hex.type}`;
}

/**
 * Describe a path (edge) by the hexes it runs between, so a camel-placement
 * option reads as a place rather than a coordinate.
 *
 * @param {string} key - Edge key
 * @returns {string}
 */
function describeEdge(key) {
    const board = getBoard();
    const hexes = board?.edges?.[key]?.neighbors?.hexes || [];
    const land = hexes
        .map(hexKey => board.hexes?.[hexKey])
        .filter(hex => hex && hex.type !== 'ocean')
        .map(hex => (hex.number ? `${hex.type} ${hex.number}` : hex.type));
    return land.length > 0 ? `Path by ${land.join(', ')}` : `Path at ${key}`;
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
    if (choice.kind === 'merchant_fleet') {
        // All eight types are offered whether or not any are held right now,
        // which is the part of the card a player asks about when they see a
        // list including cards they do not have.
        return 'The rate lasts the rest of your turn, held or not.';
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
    if (choice.kind === 'treason_source') {
        const more = context.left > 1 ? ` (${context.left} to remove)` : '';
        return `Remove a barbarian to redeploy${more}.`;
    }
    if (choice.kind === 'treason_destination') {
        const more = context.left > 1 ? ` (${context.left} to place)` : '';
        return `Redeploy a barbarian onto another coast${more}.`;
    }
    if (choice.kind === 'gift_harbor') {
        const port = context.port || {};
        const harbour = port.type === 'resource'
            ? `a 2:1 ${describeCard(port.resource)} harbour`
            : 'a 3:1 harbour';
        return `Choose a coastal side of one of your settlements for ${harbour}.`;
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
    return `Waiting for ${choice.player} to ${prompt}`;
}

// ---------------------------------------------------------------- rendering

/**
 * Put an icon and its text into an element: the icon markup first (this
 * module's own, safe to parse), then the text as a node (server data, never
 * markup). Either half may be empty - a labelled tile stands with no text, a
 * plain option with no icon.
 *
 * @param {HTMLElement} element - Target, its contents replaced
 * @param {string} iconMarkup - Icon HTML from icons.js, or ''
 * @param {string} text - Label text, or ''
 */
function fillIconLabel(element, iconMarkup, text) {
    element.innerHTML = iconMarkup || '';
    if (text) {
        element.appendChild(document.createTextNode(iconMarkup ? ` ${text}` : text));
    }
}

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

    const titleIcon = CHOICE_ICONS[choice.kind] ? statusIcon(CHOICE_ICONS[choice.kind]) : '';
    fillIconLabel(choicePrompt, titleIcon, CHOICE_TITLES[choice.kind] || 'Your decision');

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
    } else if (EDGE_CHOICE_KINDS.includes(choice.kind)) {
        const hint = document.createElement('div');
        hint.className = 'choice-hint';
        hint.textContent = 'Tap a ringed path on the board, or use a button below.';
        fragment.appendChild(hint);
    }

    options.forEach(option => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'choice-option';
        button.dataset.choiceOption = option;
        // The icon markup is this module's own, but the text is server data - a
        // card name or a player's own words - so it goes in as a text node,
        // never parsed as markup.
        fillIconLabel(button, optionIcon(choice, option), optionLabel(choice, option));
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
