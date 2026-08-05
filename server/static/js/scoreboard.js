// The scoreboard rail: one row per player, the awards panel under it, and the
// line in the console that says whose turn it is.
//
// Everything here renders from the board payload and writes nothing back. What
// is never here is anyone's hand - the server sends counts for every player and
// the contents of one's own only.

import { getContrastColor } from './contrast.js';
import { awardSummary, gamePlayersList, turnIndicator } from './dom.js';
import { seaRule } from './seafarers.js';
import { getBoard, getCurrentPlayer, getGamePhase, isMyTurn } from './state.js';

/**
 * One counter on a scoreboard row: an icon, a number, and what it means.
 *
 * The icon carries no meaning on its own, so every chip states it twice - in
 * `title` for a pointer and in `aria-label` for a screen reader, which would
 * otherwise be read the emoji itself. Deliberately unpainted: the row already
 * wears the player's own colour with WCAG-picked ink, and a chip background of
 * its own would be a second contrast pair to defend on an arbitrary hue.
 *
 * @param {string} icon - The glyph
 * @param {number} value - The count
 * @param {string} label - What it counts, in words
 * @returns {HTMLElement}
 */
function scoreChip(icon, value, label) {
    const chip = document.createElement('span');
    chip.className = 'score-chip';
    chip.textContent = `${icon}${value}`;
    chip.title = `${value} ${label}`;
    chip.setAttribute('aria-label', `${value} ${label}`);
    return chip;
}

/**
 * The awards one player holds, as badges beside their name.
 *
 * The award panel underneath says who holds what and on what number; this is
 * the other half of the same question - looking at a row and knowing whether
 * that player is the one holding it.
 *
 * @param {object} board - The board payload
 * @param {string} name - The player
 * @returns {Array} - [{icon, label}]
 */
function awardsHeldBy(board, name) {
    const held = [];
    if (board.longest_road_holder === name) {
        held.push({
            icon: '👑',
            label: board.rules?.longest_trade_route === true
                ? 'holds the Longest Trade Route'
                : 'holds the Longest Road'
        });
    }
    if (board.largest_army_holder === name) {
        held.push({ icon: '🛡️', label: 'holds the Largest Army' });
    }
    if (board.rules?.harbormaster === true && board.harbormaster_holder === name) {
        held.push({ icon: '⚓', label: 'holds the Harbormaster' });
    }
    if (board.merchant_holder === name) {
        held.push({ icon: '🏪', label: 'holds the Merchant' });
    }
    return held;
}

/**
 * Everything one player's row states, in the order it is read.
 *
 * Only what the table is playing: a chip for a rule nobody picked is a line of
 * a rail that must never scroll, spent on a zero that can never change. What is
 * *not* here is anyone's hand - the server sends counts for every player and
 * the contents of one's own only, so a count is all this can ever draw.
 *
 * @param {object} board - The board payload
 * @param {object} entry - That player's entry in `board.players`
 * @returns {Array} - [{icon, value, label}]
 */
function scoreChipsFor(board, entry) {
    const ck = board.cities_knights;
    const name = entry.name;
    const chips = [
        { icon: '🎴', value: entry.resource_count ?? 0, label: 'resource cards in hand' }
    ];

    if (board.rules?.commodities === true) {
        chips.push({
            icon: '🧺', value: entry.commodity_count ?? 0,
            label: 'commodity cards in hand'
        });
    }

    // Progress cards replace the development deck outright, so a row shows
    // whichever hidden hand this table actually deals.
    if (board.rules?.progress_cards === true) {
        chips.push({
            icon: '🃏', value: ck?.progress_hand_counts?.[name] ?? 0,
            label: 'progress cards in hand'
        });
    } else {
        chips.push({
            icon: '🃏', value: entry.dev_card_count ?? 0,
            label: 'development cards in hand'
        });
    }

    chips.push(
        { icon: '🏠', value: (entry.settlements || []).length, label: 'settlements' },
        { icon: '🏛️', value: (entry.cities || []).length, label: 'cities' },
        { icon: '🛣️', value: (entry.roads || []).length, label: 'roads' }
    );

    if (board.rules?.ships === true) {
        chips.push({ icon: '🚢', value: (entry.ships || []).length, label: 'ships' });
    }

    // Two different things wear a sword. With the expansion's knights on, the
    // number that matters is how many are standing on the board; without them
    // it is how many knight cards have been played, which is what Largest Army
    // counts. Never both - they are not the same game.
    if (board.rules?.knights === true) {
        chips.push({
            icon: '⚔️', value: (ck?.knights?.[name] || []).length,
            label: 'knights on the board'
        });
    } else {
        chips.push({
            icon: '⚔️', value: board.knights_played?.[name] || 0,
            label: 'knights played'
        });
    }

    if (board.rules?.city_walls === true) {
        chips.push({
            icon: '🧱', value: ck?.city_walls?.[name] || 0, label: 'city walls'
        });
    }

    chips.push({
        icon: '🛤️', value: board.longest_road_length?.[name] || 0,
        label: board.rules?.longest_trade_route === true
            ? 'segments in their longest trade route'
            : 'roads in their longest road'
    });

    if (board.rules?.harbormaster === true) {
        chips.push({
            icon: '⚓', value: board.harbor_points?.[name] || 0, label: 'harbour points'
        });
    }

    // Island points are already inside the score. They are broken out because a
    // settlement that scores three points instead of one otherwise looks like
    // an arithmetic error on everyone else's scoreboard.
    if (seaRule('island_victory_points')) {
        chips.push({
            icon: '🏝️', value: board.island_points?.[name] || 0,
            label: 'points from islands'
        });
    }

    return chips;
}

/**
 * Render game sidebar (players only - no observers in game)
 *
 * The tester's complaint was that the whole table's state should be readable
 * without opening anything, and that the row it replaced - `Rd 0 · Kn 0 · 🃏0 ·
 * 🏺0 com · 📜0` - was a run of abbreviations that named none of the pieces on
 * the board. Every row now states the score, both hands as counts, every kind
 * of piece the table plays with, the knights, and the awards that player holds.
 *
 * Which chips appear is decided by the rules and never by the numbers: a row
 * that dropped its zeroes would change height under the player as the game
 * went on, and the rail it sits in must never scroll.
 */
export function renderGameSidebar(data) {
    gamePlayersList.innerHTML = '';

    // Handle both array of strings and array of player objects
    const players = data.players.map(p => typeof p === 'string' ? p : p.name);
    const board = getBoard() || {};

    players.forEach(name => {
        const li = document.createElement('li');
        const playerData = board.players?.find(p => p.name === name) || { name };

        // Built rather than interpolated throughout - a player named with
        // markup would otherwise be parsed as HTML on everyone else's
        // scoreboard.
        const head = document.createElement('div');
        head.className = 'score-head';

        const who = document.createElement('span');
        who.className = 'score-name';
        who.textContent = name;
        head.appendChild(who);

        awardsHeldBy(board, name).forEach(award => {
            const badge = document.createElement('span');
            badge.className = 'score-badge';
            badge.textContent = award.icon;
            badge.title = `${name} ${award.label}`;
            badge.setAttribute('aria-label', `${name} ${award.label}`);
            head.appendChild(badge);
        });

        const score = document.createElement('span');
        score.className = 'score-points';
        score.textContent = `${playerData.victory_points || 0} pts`;
        head.appendChild(score);

        const chips = document.createElement('div');
        chips.className = 'score-chips';
        scoreChipsFor(board, playerData).forEach(chip => {
            chips.appendChild(scoreChip(chip.icon, chip.value, chip.label));
        });

        li.appendChild(head);
        li.appendChild(chips);

        // Color each player with their own color
        if (playerData.color) {
            li.style.backgroundColor = playerData.color;
            li.style.color = getContrastColor(playerData.color);
        }

        // Whose turn it is, as a ring rather than a border: a border width that
        // appears and disappears would resize the panel under the rest of the
        // rail on every turn change.
        if (name === getCurrentPlayer()) {
            li.classList.add('current-turn');
        }

        gamePlayersList.appendChild(li);
    });

    renderAwardSummary();
    renderTurnIndicator();
}

/**
 * Who currently holds each bonus, and on what.
 *
 * Longest Road and the Harbormaster were in the payload and nowhere on screen:
 * a player could take either one off someone without either of them being told.
 * Stated here in full - holder and the number that decides it - rather than as
 * a badge beside a name, because the interesting question is usually "who is
 * about to take it", which needs the runners-up too.
 */
function renderAwardSummary() {
    if (!awardSummary) {
        return;
    }

    const board = getBoard();
    if (!board) {
        awardSummary.textContent = '';
        return;
    }

    const roadLengths = board.longest_road_length || {};
    const knights = board.knights_played || {};
    const harborPoints = board.harbor_points || {};

    // The number that would take the bonus, whoever is holding it now
    const best = (scores) => Math.max(0, ...Object.values(scores).map(Number));

    // The threshold the engine is actually applying, never a copy of the base
    // game's number: a table that lowered the minimum to 2 was told "needs 5".
    const needs = (ruleId) => {
        const minimum = Number(board.rules?.[ruleId]);
        return Number.isFinite(minimum) ? `, needs ${minimum}` : '';
    };

    // Seafarers plays for the Longest Trade Route *instead of* the Longest
    // Road, and roads and ships both count toward it - so a route that was
    // mostly ships was being reported as "10 roads". The rulebook counts it in
    // segments (expansions.md 77-84).
    const tradeRoute = board.rules?.longest_trade_route === true;

    const rows = [
        {
            icon: '👑',
            name: tradeRoute ? 'Longest Trade Route' : 'Longest Road',
            holder: board.longest_road_holder,
            value: board.longest_road_holder
                ? `${roadLengths[board.longest_road_holder] || 0} `
                  + (tradeRoute ? 'segments' : 'roads')
                : `best ${best(roadLengths)}${needs('longest_road_minimum')}`
        },
        {
            icon: '🛡️',
            name: 'Largest Army',
            holder: board.largest_army_holder,
            value: board.largest_army_holder
                ? `${knights[board.largest_army_holder] || 0} knights`
                : `best ${best(knights)}${needs('largest_army_minimum')}`
        }
    ];

    // Only when the table switched the rule on: an award nobody is playing for
    // is noise on a panel that must stay short enough never to scroll.
    if (board.rules?.harbormaster === true) {
        rows.push({
            icon: '⚓',
            name: 'Harbormaster',
            holder: board.harbormaster_holder,
            value: board.harbormaster_holder
                ? `${harborPoints[board.harbormaster_holder] || 0} harbour pts`
                : `best ${best(harborPoints)}, needs 3`
        });
    }

    // The merchant is worth a victory point for as long as its owner keeps it,
    // and it changes hands the moment somebody else plays the card. Listed only
    // once one is on the board: an award nobody is playing for is a row this
    // panel cannot spare.
    if (board.merchant_holder) {
        rows.push({
            icon: '🏪',
            name: 'Merchant',
            holder: board.merchant_holder,
            value: '1 pt'
        });
    }

    const fragment = document.createDocumentFragment();
    rows.forEach(row => {
        const line = document.createElement('div');
        line.className = row.holder ? 'award-row held' : 'award-row';

        const label = document.createElement('span');
        label.className = 'award-name';
        label.textContent = `${row.icon} ${row.name}`;

        // Built rather than interpolated: a player named with markup would
        // otherwise be parsed as HTML on everyone else's scoreboard.
        const holder = document.createElement('span');
        holder.className = 'award-holder';
        holder.textContent = row.holder
            ? `${row.holder} · ${row.value}`
            : `unclaimed · ${row.value}`;

        line.appendChild(label);
        line.appendChild(holder);
        fragment.appendChild(line);
    });

    awardSummary.innerHTML = '';
    awardSummary.appendChild(fragment);
}

/**
 * Say whose turn it is in words, in the console beside the actions it gates.
 * "Waiting for Kalina…" on the Next Turn button was the only statement of it,
 * and it is the wrong place to look for the answer to "can I do anything".
 */
export function renderTurnIndicator() {
    if (!turnIndicator) {
        return;
    }
    const current = getCurrentPlayer();
    if (!current) {
        turnIndicator.textContent = '—';
        turnIndicator.className = 'turn-indicator';
        return;
    }
    const setup = getGamePhase() === 'setup' ? ' · setup' : '';
    turnIndicator.textContent = isMyTurn()
        ? `Your turn${setup}`
        : `${current}'s turn${setup}`;
    turnIndicator.className = isMyTurn() ? 'turn-indicator mine' : 'turn-indicator';
}
