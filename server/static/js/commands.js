// The command bar: a combobox over the chat input.
//
// Typing "/" raises the list, every further character filters it fuzzily, and
// ↑/↓/Enter/Escape work the list without focus ever leaving the field being
// typed in - which is the whole reason this is a combobox with
// `aria-activedescendant` and not a menu that steals focus.
//
// Two things it must never break. Ordinary chat: a message that merely
// *contains* a slash is chat, and Enter with nothing selected sends the text.
// And the catalogue: every name, argument hint and summary comes from the
// server, so a command added there appears here with no change to this file.

import { chatInput, commandBar, commandList } from './dom.js';
import { emitGame } from './socket.js';

// The catalogue exactly as the server last sent it, and what the server calls
// a command. The prefix is not hardcoded for the same reason the ids are not.
const catalogue = { commands: [], prefix: '/' };

// Which filtered row is active, as an index into `shown`. -1 is "the player is
// typing, nothing is picked" - and Enter in that state sends what they typed.
let shown = [];
let activeIndex = -1;

/**
 * Record a catalogue from the server and redraw if the bar is open.
 *
 * @param {object} data - A `commands_changed` payload
 */
export function setCommandCatalogue(data) {
    if (!data || !Array.isArray(data.commands)) {
        console.warn('Ignoring malformed commands_changed payload:', data);
        return;
    }
    catalogue.commands = data.commands;
    if (typeof data.prefix === 'string' && data.prefix) {
        catalogue.prefix = data.prefix;
    }
    if (isOpen()) {
        refresh();
    }
}

/**
 * The catalogue exactly as the server sent it.
 * Exposed for the debug hook: a test that wrote its own command list could not
 * notice the bar failing to render one the server offers.
 */
export function getCommandCatalogue() {
    return { commands: catalogue.commands, prefix: catalogue.prefix };
}

/**
 * Whether a typed line is meant as a command at all.
 * Only a line that *starts* with the prefix: "back in 5 w/ coffee" is chat.
 *
 * @param {string} text
 * @returns {boolean}
 */
export function isCommandLine(text) {
    return typeof text === 'string' && text.trimStart().startsWith(catalogue.prefix);
}

/**
 * The command name typed so far - the first word after the prefix.
 */
function typedName(text) {
    return text.trimStart().slice(catalogue.prefix.length).split(' ')[0];
}

/**
 * Whether any argument has been typed after the command name.
 */
function hasTypedArguments(text) {
    return text.trimStart().slice(catalogue.prefix.length).trimEnd().includes(' ');
}

/**
 * Score one command against what has been typed, fzf-style.
 *
 * A query matches when its characters appear in order anywhere in the name, so
 * "adr" finds "add_resource". A run of adjacent characters and a match at the
 * start score better, which is what puts the command somebody meant at the top
 * rather than the one that happens to sort first.
 *
 * @param {string} name - The command id
 * @param {string} query - What has been typed after the prefix
 * @returns {number} - Higher is better; -1 for no match
 */
export function fuzzyScore(name, query) {
    if (!query) {
        return 0;
    }
    const haystack = name.toLowerCase();
    const needle = query.toLowerCase();

    let score = 0;
    let at = 0;
    let previous = -2;
    for (const character of needle) {
        const found = haystack.indexOf(character, at);
        if (found === -1) {
            return -1;
        }
        score += found === previous + 1 ? 8 : 1;
        if (found === 0) {
            score += 4;
        }
        previous = found;
        at = found + 1;
    }
    // A short name matching the same query is the better match: "/give" beats
    // "/set_dice" for "ie".
    return score - haystack.length * 0.1;
}

/**
 * The commands matching what has been typed, best first.
 */
function matches(query) {
    return catalogue.commands
        .map(command => ({ command, score: fuzzyScore(command.id, query) }))
        .filter(entry => entry.score >= 0)
        // Stable within a score band: the catalogue's own order is the server's
        // and the reporting commands come first in it.
        .sort((left, right) => right.score - left.score)
        .map(entry => entry.command);
}

function isOpen() {
    return commandBar !== null && !commandBar.classList.contains('hidden');
}

/**
 * Build one row. Name, argument hint and summary - and, for a command this
 * table cannot run, the reason, because a row that silently does nothing when
 * picked is worse than no row.
 */
function buildRow(command, index) {
    const row = document.createElement('li');
    row.className = 'command-item';
    row.id = `command-option-${index}`;
    row.setAttribute('role', 'option');
    row.setAttribute('aria-selected', 'false');
    row.dataset.commandId = command.id;
    if (!command.available) {
        row.classList.add('command-unavailable');
    }

    const name = document.createElement('span');
    name.className = 'command-name';
    name.textContent = command.name;
    row.appendChild(name);

    if (command.args) {
        const args = document.createElement('span');
        args.className = 'command-args';
        args.textContent = command.args;
        row.appendChild(args);
    }

    const summary = document.createElement('span');
    summary.className = 'command-summary';
    // The reason travels in the same sentence rather than as a colour: a row
    // that is only dimmed says nothing to a screen reader, and nothing at all
    // about *why*.
    summary.textContent = command.available
        ? command.summary
        : `${command.summary} — unavailable: ${command.unavailable}`;
    row.appendChild(summary);

    return row;
}

/**
 * Redraw the list from the current input value.
 */
function refresh() {
    if (!commandList || !chatInput) {
        return;
    }
    shown = matches(typedName(chatInput.value));

    commandList.replaceChildren();
    shown.forEach((command, index) => commandList.appendChild(buildRow(command, index)));

    if (shown.length === 0) {
        close();
        return;
    }
    if (activeIndex >= shown.length) {
        activeIndex = shown.length - 1;
    }
    paintActive();
}

/**
 * Mark the active row for both the eye and the screen reader.
 */
function paintActive() {
    if (!commandList || !chatInput) {
        return;
    }
    const rows = Array.from(commandList.children);
    rows.forEach((row, index) => {
        const active = index === activeIndex;
        row.classList.toggle('is-active', active);
        row.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    const active = rows[activeIndex];
    if (active) {
        chatInput.setAttribute('aria-activedescendant', active.id);
        active.scrollIntoView({ block: 'nearest' });
    } else {
        chatInput.removeAttribute('aria-activedescendant');
    }
}

function open() {
    if (!commandBar || !chatInput) {
        return;
    }
    commandBar.classList.remove('hidden');
    chatInput.setAttribute('aria-expanded', 'true');
}

/**
 * Put the bar away and forget the selection. Called on Escape, on a sent
 * message, and whenever the line stops being a command.
 */
export function close() {
    if (!commandBar || !chatInput) {
        return;
    }
    commandBar.classList.add('hidden');
    chatInput.setAttribute('aria-expanded', 'false');
    chatInput.removeAttribute('aria-activedescendant');
    activeIndex = -1;
    shown = [];
}

/**
 * Open, close or refilter the bar after the input changed.
 */
export function updateCommandBar() {
    if (!chatInput) {
        return;
    }
    if (!isCommandLine(chatInput.value)) {
        close();
        return;
    }
    // Typing changes what matches, so the previous pick is no longer meaningful
    // - and Enter must send the line rather than run a command nobody chose.
    activeIndex = -1;
    open();
    refresh();
}

function move(step) {
    if (shown.length === 0) {
        return;
    }
    // From "nothing picked", ↓ takes the best match and ↑ the last one.
    if (activeIndex === -1) {
        activeIndex = step > 0 ? 0 : shown.length - 1;
    } else {
        activeIndex = (activeIndex + step + shown.length) % shown.length;
    }
    paintActive();
}

/**
 * Send a command line to the server. The server parses it - the client never
 * decides which command it just ran.
 *
 * @param {string} text - The whole typed line, prefix and all
 * @returns {boolean} - Whether it was sent
 */
export function runCommand(text) {
    if (!emitGame('run_command', { text })) {
        return false;
    }
    close();
    return true;
}

/**
 * Act on the active row.
 *
 * A command that takes arguments and has none typed is *completed* rather than
 * run: sending it would earn nothing but the server's usage message. One that
 * takes no arguments runs on the spot, which is what "picking one runs it"
 * means for /help.
 *
 * @returns {boolean} - Whether this handled the key, so chat must not also send
 */
export function acceptActive() {
    const command = shown[activeIndex];
    if (!command || !chatInput) {
        return false;
    }

    if (command.args && !hasTypedArguments(chatInput.value)) {
        chatInput.value = `${command.name} `;
        close();
        return true;
    }

    const typed = chatInput.value.trim();
    const line = hasTypedArguments(typed)
        ? `${command.name} ${typed.slice(typed.indexOf(' ') + 1).trim()}`
        : command.name;
    if (runCommand(line)) {
        chatInput.value = '';
    }
    return true;
}

/**
 * Keyboard for the list. Returns true when the key belonged to the bar, so the
 * chat form's own handling is skipped for exactly those keys and no others.
 *
 * @param {KeyboardEvent} event
 * @returns {boolean}
 */
export function handleCommandKey(event) {
    if (!isOpen()) {
        return false;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        move(event.key === 'ArrowDown' ? 1 : -1);
        return true;
    }
    if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return true;
    }
    if (event.key === 'Enter' && activeIndex !== -1) {
        event.preventDefault();
        return acceptActive();
    }
    return false;
}

if (commandList) {
    commandList.addEventListener('mousedown', (event) => {
        // mousedown, not click: clicking takes focus off the input, and the
        // blur handler would put the list away before the click landed.
        event.preventDefault();
        const row = event.target.closest('[role="option"]');
        if (!row) {
            return;
        }
        activeIndex = Array.from(commandList.children).indexOf(row);
        paintActive();
        acceptActive();
        chatInput?.focus();
    });
}

if (chatInput) {
    chatInput.addEventListener('input', updateCommandBar);
    // Before the form's submit handler, and only for the keys the list owns:
    // Enter with nothing picked falls straight through to sending the line.
    chatInput.addEventListener('keydown', handleCommandKey);
    chatInput.addEventListener('blur', () => {
        // Left open, the list would hang over the log after the player clicked
        // away from a half-typed command.
        close();
    });
}
