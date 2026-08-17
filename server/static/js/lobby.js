// The join screen, the lobby roster, and the house-rules picker.

import { setHighlight } from './board.js';
import { renderCitiesKnights } from './cities-knights.js';
import { activeRulesChipValue, activeRulesDiv, activeRulesPanel, diceDisplay, diceSetEl, discardModal, gameBoard, gameScreen, inventionModal, joinBtn, joinColorPicker, joinScreen, mapsBtn, monopolyModal, observerList, placeRoadBtn, placeSettlementBtn, playerCount, playerLimit, playerList, robberIndicator, rollDiceBtn, rulePresets, rulesList, rulesLockedNote, scenarioDetail, scenarioDetailName, scenarioDetailRules, scenarioDetailSource, scenarioDetailSummary, scenarioPreviewCanvas, scenarioPreviewStatus, startGameBtn, startReasonEl, tradeModal, upgradeCityBtn, userScreen, usernameInput, victimModal } from './dom.js';
import { enterEditor } from './map-editor.js';
import { requestLogCatchUp } from './event-log.js';
import { displayError, showNotice } from './notices.js';
import { emitGame, socket } from './socket.js';
import { getBoard, getRole, isGameRunning, viewState } from './state.js';

// This browser's last seat, so a reload mid-game does not ask the player to
// remember how they spelled their own name. Personal and local, like the YOLO
// preference in placement.js: it reaches no other tab and no server.
const NAME_STORAGE_KEY = 'catan.playerName';

/**
 * Remember the name this browser last joined under.
 *
 * @param {string} name - The name that was just sent to the server
 */
function rememberName(name) {
    try {
        window.localStorage.setItem(NAME_STORAGE_KEY, name);
    } catch {
        // Private mode or storage denied: joining still works, it just will
        // not be pre-filled next time.
    }
}

/**
 * Pre-fill the join box with the last name used in this browser.
 */
function restoreRememberedName() {
    if (!usernameInput || usernameInput.value) {
        return;
    }
    try {
        usernameInput.value = window.localStorage.getItem(NAME_STORAGE_KEY) || '';
    } catch {
        // Nothing to restore; the player types it as before.
    }
}

/**
 * Handle join button click - connect to game
 */
function join(takeover = false) {
    const name = usernameInput.value.trim();
    if (!name) {
        displayError('Please enter a name');
        return;
    }
    rememberName(name);

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

// Wrapped, not passed straight in: a listener is handed the MouseEvent, which
// arrives as `takeover` and is truthy, so every Join click claimed a seat
// somebody else was holding and `handleNameTaken` never ran. The Enter path
// below always called `join()` with no argument and was never affected, which
// is what made this survive so long.
joinBtn.addEventListener('click', () => join());

restoreRememberedName();

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

mapsBtn.addEventListener('click', () => {
    if (viewState.server.rules?.locked) return;
    enterEditor();
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
    // The next game is a fresh agreement; the last one's dice must not linger
    // over the lobby's own.
    diceSetEl?.classList.add('hidden');
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
    playerLimit.textContent = roster.maxPlayers;

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
 * The exclusion group a rule belongs to, or null.
 * Exclusion groups cut across the section groups above (a base-game variant and
 * an expansion rule can be rivals), so they decorate rows in place rather than
 * re-sectioning the picker.
 */
function exclusionGroupFor(ruleId) {
    return (viewState.server.rules.exclusions || []).find(
        group => group.rules.includes(ruleId)) || null;
}

/**
 * The display name of a rule from the catalogue, or its id as a fallback.
 */
function ruleName(ruleId) {
    const rule = viewState.server.rules.catalogue.find(entry => entry.id === ruleId);
    return rule ? rule.name : ruleId;
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

    // A choice needs a control that can express more than two states. It used
    // to fall through to the checkbox branch, which left the beginner and large
    // maps unselectable - the picker showed a tick nobody could interpret.
    const input = document.createElement(rule.type === 'choice' ? 'select' : 'input');
    input.id = `rule-${rule.id}`;
    input.dataset.ruleId = rule.id;
    input.dataset.ruleType = rule.type;
    if (rule.type === 'choice') {
        input.className = 'rule-choice';
        (rule.options || []).forEach(option => {
            const item = document.createElement('option');
            item.value = option.id;
            item.textContent = option.name;
            item.title = option.summary || '';
            input.appendChild(item);
        });
    } else if (rule.type === 'int') {
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

    // An excluding rule carries a badge and a note so a player reads why one of
    // the pair will untick before ever ticking it, and so an auto-uncheck has a
    // place on the row to say why it happened.
    const exclusion = exclusionGroupFor(rule.id);
    if (exclusion) {
        const badge = document.createElement('span');
        badge.className = 'rule-exclusion-badge';
        badge.textContent = 'exclusive';
        badge.title = exclusion.reason;
        label.appendChild(document.createTextNode(' '));
        label.appendChild(badge);
        input.setAttribute('aria-describedby', `rule-exclusion-${rule.id}`);
    }
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

    if (exclusion) {
        const note = document.createElement('div');
        note.className = 'rule-exclusion';
        note.id = `rule-exclusion-${rule.id}`;
        note.dataset.reason = exclusion.reason;
        note.textContent = exclusion.reason;
        row.appendChild(note);
    }
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
    if (rule.type === 'choice' || rule.type === 'int') {
        input.value = value;
    } else {
        input.checked = Boolean(value);
    }
}

// The scenario the picker is showing the detail panel for, and a token that
// tells a preview reply apart from a stale one for a scenario clicked since.
// Personal to this browser: picking a scenario is a shared decision (it sends
// `set_rules`), but which one this player is *looking at* is not.
let selectedScenarioId = null;
let previewToken = 0;
// The token whose board has actually painted, so a timeout can tell a preview
// that arrived from one still in flight.
let paintedToken = 0;
// If a preview never comes back — the server refused it, or the round trip was
// lost — the loading state settles to a placeholder rather than spinning
// forever. Long enough for a real reply, short enough not to look hung.
const PREVIEW_TIMEOUT_MS = 6000;

/**
 * The first sentence of a scenario's summary, for the one-line list blurb.
 * The full summary is the detail panel's description; the row shows only its
 * opening so a scannable list stays one line per scenario.
 */
function firstSentence(text) {
    if (!text) {
        return '';
    }
    const end = text.search(/\.\s|\.$/);
    return end === -1 ? text : text.slice(0, end + 1);
}

/**
 * Render the scenario list the server offers.
 *
 * The catalogue is past thirty switches now that Cities & Knights is eight
 * separate rules rather than one. Reading all of them to reach a published rule
 * set is the kind of thing nobody does, so each preset is one row in a
 * scrollable list - and because a preset only ticks individual rules, every one
 * of them stays separately switchable in the list below.
 */
function renderRulePresets() {
    if (!rulePresets) {
        return;
    }

    const presets = viewState.server.rules.presets;
    rulePresets.classList.toggle('hidden', presets.length === 0);

    const fragment = document.createDocumentFragment();
    presets.forEach(preset => {
        // A button, kept id'd `preset-<id>` and role=option: it is one clickable
        // row per rule set, and picking it applies that preset exactly as the
        // shortcut buttons did before the list wrapped them.
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'scenario-row';
        row.id = `preset-${preset.id}`;
        row.dataset.presetId = preset.id;
        row.setAttribute('role', 'option');
        row.setAttribute('aria-selected', String(preset.id === selectedScenarioId));
        row.disabled = viewState.server.rules.locked;

        const name = document.createElement('span');
        name.className = 'scenario-row-name';
        name.textContent = preset.name;

        const blurb = document.createElement('span');
        blurb.className = 'scenario-row-blurb';
        blurb.textContent = firstSentence(preset.summary);

        row.appendChild(name);
        row.appendChild(blurb);
        fragment.appendChild(row);
    });

    rulePresets.innerHTML = '';
    rulePresets.appendChild(fragment);

    // A scenario picked before a re-render (a rule broadcast rebuilds the list)
    // keeps its detail panel; one that vanished from the list clears it.
    if (selectedScenarioId && !presets.some(p => p.id === selectedScenarioId)) {
        selectedScenarioId = null;
        clearScenarioDetail();
    }
}

/**
 * The non-default rules a rule set turns on, as readable "Name: value" lines.
 * Read against the catalogue the server sent, so a rule added server-side is
 * described the day it appears and never restated from a copy here.
 *
 * @param {object} source - A rules dict (a preset's, or a running board's)
 * @returns {Array<string>} - One label per rule that differs from its default
 */
function describeRuleChanges(source) {
    const parts = [];
    viewState.server.rules.catalogue.forEach(rule => {
        const value = source[rule.id];
        if (value === undefined || value === rule.default) {
            return;
        }
        if (rule.type === 'choice') {
            const option = (rule.options || []).find(entry => entry.id === value);
            parts.push(`${rule.name}: ${option ? option.name : value}`);
        } else if (rule.type === 'int') {
            parts.push(`${rule.name}: ${value}`);
        } else {
            parts.push(value ? rule.name : `${rule.name}: off`);
        }
    });
    return parts;
}

/**
 * Empty the detail panel back to its "pick a scenario" resting state.
 */
function clearScenarioDetail() {
    if (!scenarioDetail) {
        return;
    }
    scenarioDetailName.textContent = '';
    scenarioDetailSummary.textContent = '';
    scenarioDetailRules.innerHTML = '';
    scenarioDetailSource.textContent = '';
    scenarioDetailSource.classList.add('hidden');
    showPreviewStatus('Pick a scenario to preview its map.');
}

/**
 * Show a message over the preview canvas (loading, or a placeholder on failure)
 * and blank the canvas so no earlier scenario's board lingers under it.
 */
function showPreviewStatus(message) {
    if (!scenarioPreviewStatus) {
        return;
    }
    scenarioPreviewStatus.textContent = message;
    scenarioPreviewStatus.classList.remove('hidden');
    const ctx = scenarioPreviewCanvas?.getContext('2d');
    if (ctx) {
        ctx.clearRect(0, 0, scenarioPreviewCanvas.width, scenarioPreviewCanvas.height);
    }
}

/**
 * Fill the detail panel for the scenario just picked: its rules-turned-on list,
 * its description, and the rulebook it comes from. The map preview is a server
 * round trip and lands separately.
 */
function renderScenarioDetail(preset) {
    if (!scenarioDetail) {
        return;
    }
    scenarioDetailName.textContent = preset.name;
    scenarioDetailSummary.textContent = preset.summary || '';

    scenarioDetailRules.innerHTML = '';
    const changes = describeRuleChanges(preset.rules || {});
    if (changes.length === 0) {
        const none = document.createElement('span');
        none.className = 'scenario-rule-chip scenario-rule-chip-none';
        none.textContent = 'Base game rules';
        scenarioDetailRules.appendChild(none);
    } else {
        changes.forEach(label => {
            const chip = document.createElement('span');
            chip.className = 'scenario-rule-chip';
            chip.textContent = label;
            scenarioDetailRules.appendChild(chip);
        });
    }

    if (preset.source) {
        scenarioDetailSource.textContent = `Rulebook: ${preset.source}`;
        scenarioDetailSource.classList.remove('hidden');
    } else {
        scenarioDetailSource.textContent = '';
        scenarioDetailSource.classList.add('hidden');
    }
}

/**
 * Ask the server to deal this scenario's board and paint the thumbnail.
 *
 * Reuses the server's `preview_map` deal path (a real `Game`, one board back),
 * so what the picker shows is the board the table will play. The reply is
 * matched to the token below: click faster than the round trip and only the
 * board for the scenario still selected is drawn.
 */
function requestScenarioPreview(preset) {
    const token = ++previewToken;
    showPreviewStatus('Dealing the board…');
    emitGame('preview_scenario', { preset: preset.id });

    window.setTimeout(() => {
        // Still the latest request and its board never painted: the server
        // refused it or the reply was lost. Say so without breaking the lobby.
        if (token === previewToken && paintedToken !== token) {
            showPreviewStatus('Preview unavailable — the rest of the scenario still applies.');
        }
    }, PREVIEW_TIMEOUT_MS);
}

/**
 * Select a scenario: apply its preset, show its detail, request its preview.
 */
function selectScenario(presetId) {
    const preset = viewState.server.rules.presets.find(entry => entry.id === presetId);
    if (!preset) {
        return;
    }
    selectedScenarioId = presetId;

    // The server owns what a preset means: it is sent by id and the reply is the
    // rule set that came back, so the client keeps no copy of either. This is
    // the same path the shortcut buttons used.
    emitGame('set_rules', { preset: presetId });

    rulePresets.querySelectorAll('[data-preset-id]').forEach(row => {
        row.setAttribute('aria-selected', String(row.dataset.presetId === presetId));
    });
    renderScenarioDetail(preset);
    requestScenarioPreview(preset);
}

if (rulePresets) {
    rulePresets.addEventListener('click', (event) => {
        const row = event.target.closest('[data-preset-id]');
        if (!row || row.disabled) {
            return;
        }
        selectScenario(row.dataset.presetId);
    });
}

document.addEventListener('scenario-preview-received', (event) => {
    const { preset, board } = event.detail || {};
    // A reply for a scenario clicked away from is stale; only the board for the
    // row still selected is painted.
    if (!board || preset !== selectedScenarioId) {
        return;
    }
    scenarioPreviewStatus.classList.add('hidden');
    try {
        window.BoardRenderer.render(board, 'scenario-preview-canvas', null, null, [], null);
        paintedToken = previewToken;
    } catch (error) {
        console.error('Scenario preview render failed:', error);
        showPreviewStatus('Preview unavailable — the rest of the scenario still applies.');
    }
});

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
        .map(rule => {
            const base = `${rule.id}:${rule.type}:${ruleGroupId(rule)}`;
            return rule.type === 'choice'
                ? base + ':' + (rule.options || []).map(o => o.id).join(',')
                : base;
        })
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

    renderRulePresets();
    viewState.server.rules.catalogue.forEach(applyRuleValue);
    syncBoardMapVisibility();

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

        if (rule.type === 'choice') {
            chosen[rule.id] = input.value;
        } else if (rule.type === 'int') {
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
    syncBoardMapVisibility();
}

function syncBoardMapVisibility() {
    const layoutInput = rulesList?.querySelector('[data-rule-id="board_layout"]');
    const mapRow = rulesList?.querySelector('[data-rule-id="board_map"]')?.closest('.rule-row');
    if (!mapRow) return;
    const isCustom = layoutInput
        ? layoutInput.value === 'custom'
        : (viewState.server.rules.selected.board_layout ?? 'random') === 'custom';
    mapRow.classList.toggle('hidden', !isCustom);
}

/**
 * Untick every other member of the group the just-ticked rule belongs to.
 * Removal, not addition: it takes nothing the table cannot re-tick, and it
 * removes the box that was about to be silently ignored anyway. The reason is
 * surfaced on the row that unchecked and in the notice channel — never silent.
 *
 * @param {string} tickedId - The rule the player just switched on
 */
function autoUncheckRivals(tickedId) {
    const group = exclusionGroupFor(tickedId);
    if (!group) {
        return;
    }
    const tickedName = ruleName(tickedId);
    group.rules.forEach(rivalId => {
        if (rivalId === tickedId) {
            return;
        }
        const rival = rulesList.querySelector(`[data-rule-id="${rivalId}"]`);
        if (!rival || rival.type !== 'checkbox' || !rival.checked) {
            return;
        }
        rival.checked = false;
        const message = `Unchecked because ${tickedName} replaces it`;
        const note = rulesList.querySelector(`#rule-exclusion-${rivalId}`);
        if (note) {
            note.textContent = message;
            note.classList.add('rule-exclusion-fired');
            // Restore the standing reason once the player has read why.
            setTimeout(() => {
                note.classList.remove('rule-exclusion-fired');
                note.textContent = note.dataset.reason;
            }, EXCLUSION_NOTICE_MS);
        }
        showNotice(`${ruleName(rivalId)}: ${message}`, 'info');
    });
}

// How long the row's "unchecked because…" note stays before it settles back to
// the standing reason. Long enough to read, short enough not to linger.
const EXCLUSION_NOTICE_MS = 6000;

// Every call sends the *whole* selection, so coalescing rapid changes loses
// nothing — the last one carries the others. Without this, ticking a row of
// rules fires one full emit each: the server rate-limits the burst, the player
// gets a stack of "Slow down" toasts over their hand, and the event log fills
// with a dozen identical "changed the house rules" lines.
const RULE_SEND_DELAY_MS = 250;

let pendingRuleSend = null;

function queueRuleSend() {
    clearTimeout(pendingRuleSend);
    pendingRuleSend = setTimeout(() => {
        pendingRuleSend = null;
        sendRules();
    }, RULE_SEND_DELAY_MS);
}

if (rulesList) {
    // One delegated listener for controls that are rebuilt whenever the
    // catalogue changes. `change` rather than `input` so a number is sent
    // once, not once per keystroke.
    rulesList.addEventListener('change', (event) => {
        const input = event.target.closest('[data-rule-id]');
        if (!input) {
            return;
        }
        // Ticking one member of an exclusion group unchecks its rivals live, so
        // the whole selection sent below is already coherent and the server does
        // not have to refuse it. The uncheck is never silent: the row that just
        // lost its tick says why, and the notice channel repeats it.
        if (input.type === 'checkbox' && input.checked) {
            autoUncheckRivals(input.dataset.ruleId);
        }
        queueRuleSend();
    });

    // The focused control is skipped while rendering, so re-sync it on leave.
    // Not while a send is queued, though: server state is a step behind until
    // it lands, so re-syncing then reverts the tick the player just made —
    // which is exactly what happens when they run down a list of rules.
    rulesList.addEventListener('focusout', (event) => {
        if (pendingRuleSend !== null) {
            return;
        }
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

    const parts = describeRuleChanges(active);

    activeRulesDiv.textContent = parts.length > 0 ? parts.join(' · ') : 'Base game rules';
    activeRulesPanel.classList.remove('hidden');

    // Folded, the interesting fact is only how far this table is from the base
    // game; the list itself is one click away.
    if (activeRulesChipValue) {
        activeRulesChipValue.textContent = parts.length > 0
            ? `${parts.length} changed`
            : 'Base game';
    }
}

// The rule that decides what the dice may show. Named once, here, because this
// is the only place the client says anything about the dice themselves; what
// the set *contains* is the server's business and is never restated in JS.
const DICE_SET_RULE = 'dice_set';

/**
 * Say which dice the table is playing with, beside the two faces they land on.
 *
 * The option's own name, from the catalogue - never the id, which is what the
 * running game's rules dict carries. Silent for the standard pair: a rule that
 * changes nothing has nothing to explain.
 */
export function renderDiceSet() {
    if (!diceSetEl) {
        return;
    }

    const active = getBoard()?.rules;
    const rule = viewState.server.rules.catalogue.find(entry => entry.id === DICE_SET_RULE);
    const chosen = active?.[DICE_SET_RULE];
    const option = (rule?.options || []).find(entry => entry.id === chosen);

    if (!rule || chosen === undefined || chosen === rule.default) {
        diceSetEl.classList.add('hidden');
        diceSetEl.textContent = '';
        diceSetEl.removeAttribute('title');
        return;
    }

    // How much of the deck is left, when the table deals its rolls rather than
    // rolling them. The count is the server's - `dice_deck_remaining` in the
    // board payload - because how large the set is and how much of it has gone
    // are both answers only the engine holds. Absent, the set is still named.
    const left = getBoard()?.dice_deck_remaining;
    const remaining = Number.isInteger(left) ? ` · ${left} left` : '';

    diceSetEl.textContent = `${option ? option.name : chosen}${remaining}`;
    diceSetEl.title = option?.summary || rule.summary || '';
    diceSetEl.classList.remove('hidden');
}
