// The join screen, the lobby roster, and the house-rules picker.

import { setHighlight } from './board.js';
import { renderCitiesKnights } from './cities-knights.js';
import { activeRulesDiv, activeRulesPanel, diceDisplay, discardModal, gameBoard, gameScreen, inventionModal, joinBtn, joinColorPicker, joinScreen, monopolyModal, observerList, placeRoadBtn, placeSettlementBtn, playerCount, playerList, robberIndicator, rollDiceBtn, rulesList, rulesLockedNote, startGameBtn, startReasonEl, tradeModal, upgradeCityBtn, userScreen, usernameInput, victimModal } from './dom.js';
import { requestLogCatchUp } from './event-log.js';
import { displayError, showNotice } from './notices.js';
import { emitGame, socket } from './socket.js';
import { getBoard, getRole, isGameRunning, viewState } from './state.js';

/**
 * Handle join button click - connect to game
 */
function join(takeover = false) {
    const name = usernameInput.value.trim();
    if (!name) {
        displayError('Please enter a name');
        return;
    }

    const role = document.querySelector('input[name="role"]:checked').value;
    const color = joinColorPicker.value;

    viewState.identity.name = name;
    viewState.identity.requestedRole = role;
    viewState.identity.color = color;

    if (socket.connected) {
        socket.emit('join', { name: name, role: role, color: color, takeover: takeover });
        // A late arrival must see the rules the table already agreed on, and
        // the history of what has happened so far
        socket.emit('request_rules');
        requestLogCatchUp();
    } else {
        // The connect handler re-sends the join once the socket is up
        showNotice('Connecting to the server - you will be joined automatically.', 'info');
    }

    joinScreen.classList.add('hidden');
    userScreen.classList.remove('hidden');
    updateStartButton();
}

/**
 * Someone is already connected under this name. Offer to take their seat -
 * covering for a player who stepped away is intended, joining as them by
 * accident is not.
 */
export function handleNameTaken(message) {
    const name = usernameInput.value.trim();

    // Back to the join screen until this is resolved.
    viewState.identity.name = null;
    userScreen.classList.add('hidden');
    joinScreen.classList.remove('hidden');

    if (window.confirm(`${message}\n\nTake over ${name}'s seat and play as them?`)) {
        join(true);
    } else {
        usernameInput.value = '';
        usernameInput.focus();
    }
}

joinBtn.addEventListener('click', join);

usernameInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        join();
    }
});

/**
 * Handle Start Game button click
 */
startGameBtn.addEventListener('click', () => {
    emitGame('start_game');
});

/**
 * Update Start Game button visibility based on game state
 */
export function updateStartButton() {
    // Hiding the button outright made "why can I not start?" unanswerable.
    // Show it whenever a game is not running and say what is missing instead.
    if (isGameRunning()) {
        startGameBtn.classList.add('hidden');
        return;
    }

    startGameBtn.classList.remove('hidden');

    let reason = '';
    if (getRole() !== 'player') {
        reason = 'Observers cannot start the game - rejoin as a player.';
    } else if (viewState.server.roster.players.length < viewState.server.roster.minPlayers) {
        reason = `Waiting for players (${viewState.server.roster.players.length}/${viewState.server.roster.minPlayers}).`;
    }

    startGameBtn.disabled = Boolean(reason);
    startGameBtn.title = reason;
    if (startReasonEl) {
        startReasonEl.textContent = reason;
        startReasonEl.classList.toggle('hidden', !reason);
    }
}

/**
 * Drop back to the lobby after a game ends.
 * Dropping the board payload is most of the reset: whose turn it is, whether
 * the dice are up, and whether a robber move or a discard is pending are all
 * read back out of it. A running timer would otherwise apply to a game that no
 * longer exists. The player keeps their seat, so the identity is left alone.
 */
export function returnToLobby() {
    viewState.server.board = null;
    viewState.winnerAnnounced = false;
    viewState.selectedBuilding = null;

    if (viewState.timers.handle) {
        clearInterval(viewState.timers.handle);
        viewState.timers.handle = null;
    }

    setHighlight(null);

    [tradeModal, discardModal, victimModal, inventionModal, monopolyModal].forEach(modal => {
        modal?.classList.remove('show');
    });

    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn].forEach(button => {
        button.classList.remove('active');
    });
    gameBoard.classList.remove('placement-mode');
    robberIndicator?.classList.add('hidden');
    activeRulesPanel?.classList.add('hidden');
    viewState.knightMoveFrom = null;
    renderCitiesKnights();
    diceDisplay.innerHTML = '';
    rollDiceBtn.disabled = false;
    rollDiceBtn.textContent = 'Roll Dice';

    gameScreen.classList.add('hidden');
    userScreen.classList.remove('hidden');
    updateStartButton();
}

/**
 * Render the lobby roster from the list the server last broadcast.
 */
export function renderUserList() {
    const roster = viewState.server.roster;
    playerList.innerHTML = '';
    observerList.innerHTML = '';
    playerCount.textContent = roster.players.length;

    const appendName = (list, name) => {
        const li = document.createElement('li');
        li.textContent = name;
        if (name === viewState.identity.name) {
            li.classList.add('current-user');
        }
        list.appendChild(li);
    };

    roster.players.forEach(name => appendName(playerList, name));
    roster.observers.forEach(name => appendName(observerList, name));
}

// The sections the lobby splits the catalogue into, in display order, keyed by
// the `group` the server tags each rule with. Core is the box's fixed numbers -
// collapsed by default, because expansions and variants are what a table
// actually picks. A group the server invents later still shows up, under
// "Other", rather than silently vanishing from the picker.
const RULE_GROUPS = [
    {
        id: 'expansion',
        label: 'Expansions',
        hint: 'Whole published rule sets.',
        open: true
    },
    {
        id: 'variant',
        label: 'Variants',
        hint: 'Single published house rules.',
        open: true
    },
    {
        id: 'core',
        label: 'Base game numbers',
        hint: 'Piece supplies, deck composition, bank size - the numbers printed on the box.',
        open: false
    },
    {
        id: 'other',
        label: 'Other',
        hint: 'Rules this client has no section for yet.',
        open: true
    }
];

/**
 * Which section a catalogue entry belongs in.
 *
 * @param {object} rule - Catalogue entry
 * @returns {string} - A group id that RULE_GROUPS definitely contains
 */
function ruleGroupId(rule) {
    return RULE_GROUPS.some(group => group.id === rule.group) ? rule.group : 'other';
}

/**
 * Build the controls for one rule of the server's catalogue.
 * Nothing about the rule set is hardcoded here - a rule added server-side
 * shows up as soon as it is in the catalogue.
 *
 * @param {object} rule - Catalogue entry: {id, type, default, name, source, summary}
 * @returns {HTMLElement} - The row, not yet attached
 */
function buildRuleRow(rule) {
    const row = document.createElement('div');
    row.className = 'rule-row';

    const label = document.createElement('label');
    label.className = 'rule-label';
    label.setAttribute('for', `rule-${rule.id}`);
    label.textContent = rule.name;

    const input = document.createElement('input');
    input.id = `rule-${rule.id}`;
    input.dataset.ruleId = rule.id;
    input.dataset.ruleType = rule.type;
    if (rule.type === 'int') {
        input.type = 'number';
        input.className = 'rule-number';
        input.min = rule.minimum;
        input.max = rule.maximum;
    } else {
        input.type = 'checkbox';
        input.className = 'rule-toggle';
    }

    const head = document.createElement('div');
    head.className = 'rule-head';
    head.appendChild(label);
    head.appendChild(input);

    const source = document.createElement('div');
    source.className = 'rule-source';
    source.textContent = rule.source || '';

    const summary = document.createElement('div');
    summary.className = 'rule-summary';
    summary.textContent = rule.summary || '';

    row.appendChild(head);
    row.appendChild(source);
    row.appendChild(summary);
    return row;
}

/**
 * Build one collapsible section of the picker.
 * <details> rather than a scripted toggle: it collapses, remembers nothing the
 * client has to track, and is keyboard and screen-reader operable for free.
 *
 * @param {object} group - An entry of RULE_GROUPS
 * @param {Array<object>} rules - The catalogue entries in that group
 * @returns {HTMLElement} - The section, not yet attached
 */
function buildRuleGroup(group, rules) {
    const section = document.createElement('details');
    section.className = 'rule-group';
    section.dataset.group = group.id;
    section.open = group.open;

    const summary = document.createElement('summary');
    const label = document.createElement('span');
    label.textContent = group.label;
    const count = document.createElement('span');
    count.className = 'rule-group-count';
    count.textContent = rules.length === 1 ? '1 rule' : `${rules.length} rules`;
    summary.appendChild(label);
    summary.appendChild(count);

    const hint = document.createElement('p');
    hint.className = 'rule-group-hint';
    hint.textContent = group.hint;

    const body = document.createElement('div');
    body.className = 'rule-group-body';
    rules.forEach(rule => body.appendChild(buildRuleRow(rule)));

    section.appendChild(summary);
    section.appendChild(hint);
    section.appendChild(body);
    return section;
}

/**
 * Push the server's value for one rule onto its control.
 * The focused control is left alone so that a broadcast triggered by someone
 * else's change does not yank the number out from under the typist; it is
 * re-synced on focusout.
 */
function applyRuleValue(rule) {
    const input = rulesList.querySelector(`[data-rule-id="${rule.id}"]`);
    if (!input) {
        return;
    }

    input.disabled = viewState.server.rules.locked;

    if (input === document.activeElement) {
        return;
    }

    const value = viewState.server.rules.selected[rule.id] ?? rule.default;
    if (rule.type === 'int') {
        input.value = value;
    } else {
        input.checked = Boolean(value);
    }
}

/**
 * Render the lobby rules panel from the server's catalogue and selection.
 * The rows are rebuilt only when the catalogue itself changes, so a value
 * broadcast does not destroy focus or the caret in a number field.
 */
export function renderRulesPanel() {
    if (!rulesList) {
        return;
    }

    // The group is part of the signature: a rule that moves section has to
    // rebuild the DOM, exactly like one that changes type.
    const signature = viewState.server.rules.catalogue
        .map(rule => `${rule.id}:${rule.type}:${ruleGroupId(rule)}`)
        .join('|');
    if (signature !== viewState.renderedRulesSignature) {
        const fragment = document.createDocumentFragment();
        RULE_GROUPS.forEach(group => {
            const rules = viewState.server.rules.catalogue.filter(rule => ruleGroupId(rule) === group.id);
            if (rules.length > 0) {
                fragment.appendChild(buildRuleGroup(group, rules));
            }
        });
        rulesList.innerHTML = '';
        rulesList.appendChild(fragment);
        viewState.renderedRulesSignature = signature;
    }

    viewState.server.rules.catalogue.forEach(applyRuleValue);

    if (rulesLockedNote) {
        rulesLockedNote.classList.toggle('hidden', !viewState.server.rules.locked);
    }
}

/**
 * Read every control and send the whole selection.
 * Clamping here is a UX affordance only - the server clamps again and its
 * answer is what gets rendered.
 */
function sendRules() {
    if (viewState.server.rules.locked) {
        return;
    }

    const chosen = {};
    viewState.server.rules.catalogue.forEach(rule => {
        const input = rulesList.querySelector(`[data-rule-id="${rule.id}"]`);
        if (!input) {
            chosen[rule.id] = viewState.server.rules.selected[rule.id] ?? rule.default;
            return;
        }

        if (rule.type === 'int') {
            const parsed = parseInt(input.value, 10);
            const fallback = viewState.server.rules.selected[rule.id] ?? rule.default;
            chosen[rule.id] = Number.isNaN(parsed)
                ? fallback
                : Math.max(rule.minimum, Math.min(rule.maximum, parsed));
        } else {
            chosen[rule.id] = input.checked;
        }
    });

    emitGame('set_rules', { rules: chosen });
}

if (rulesList) {
    // One delegated listener for controls that are rebuilt whenever the
    // catalogue changes. `change` rather than `input` so a number is sent
    // once, not once per keystroke.
    rulesList.addEventListener('change', (event) => {
        if (!event.target.closest('[data-rule-id]')) {
            return;
        }
        sendRules();
    });

    // The focused control is skipped while rendering, so re-sync it on leave
    rulesList.addEventListener('focusout', (event) => {
        const input = event.target.closest('[data-rule-id]');
        const rule = viewState.server.rules.catalogue.find(entry => entry.id === input?.dataset.ruleId);
        if (rule) {
            applyRuleValue(rule);
        }
    });
}

/**
 * Show the rules the running game is actually using, non-default ones only.
 * Rendered from the board payload, which is what the engine reads.
 */
export function renderActiveRules() {
    if (!activeRulesPanel || !activeRulesDiv) {
        return;
    }

    const active = getBoard()?.rules;
    if (!active || viewState.server.rules.catalogue.length === 0) {
        activeRulesPanel.classList.add('hidden');
        return;
    }

    const parts = [];
    viewState.server.rules.catalogue.forEach(rule => {
        const value = active[rule.id];
        if (value === undefined || value === rule.default) {
            return;
        }
        if (rule.type === 'int') {
            parts.push(`${rule.name}: ${value}`);
        } else {
            parts.push(value ? rule.name : `${rule.name}: off`);
        }
    });

    activeRulesDiv.textContent = parts.length > 0 ? parts.join(' · ') : 'Base game rules';
    activeRulesPanel.classList.remove('hidden');
}
