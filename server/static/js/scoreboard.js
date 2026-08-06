// The scoreboard rail: one card per player, the titles panel under it, and the
// line in the console that says whose turn it is.
//
// Everything here renders from the board payload and writes nothing back. What
// is never here is anyone's hand - the server sends counts for every player and
// the contents of one's own only.
//
// Every glyph is a line icon from the shared set (icons.js): the design rule is
// that filled coloured tiles are things a player holds and monochrome line
// icons are facts about a player, and a scoreboard states only facts - pieces,
// hand counts and awards. No emoji, no per-panel SVG.

import { awardSummary, gamePlayersList, turnIndicator } from './dom.js';
import { statusIcon } from './icons.js';
import { getBoard, getCurrentPlayer, getGamePhase, isMyTurn } from './state.js';

/**
 * One piece-counter chip: a line icon, its count, and what it counts.
 *
 * The icon is decorative here - the count is the value and the icon only hints
 * which fact it is - so the chip carries its own accessible name in `title` for
 * a pointer and `aria-label` for a screen reader, which would otherwise be
 * handed a lone number with nothing to say what it counts. A count of zero is
 * greyed rather than dropped: a row that lost its zeroes would change height
 * under the player as the game went on, and the rail must never scroll.
 *
 * @param {string} concept - a STATUS_ICON key naming the piece
 * @param {number} value - the count
 * @param {string} label - what it counts, in words
 * @returns {HTMLElement}
 */
function scoreChip(concept, value, label) {
    const chip = document.createElement('span');
    chip.className = value === 0 ? 'chip zero' : 'chip';
    chip.innerHTML = statusIcon(concept);
    const count = document.createElement('b');
    count.className = 'num';
    count.textContent = value;
    chip.appendChild(count);
    chip.title = `${value} ${label}`;
    chip.setAttribute('aria-label', `${value} ${label}`);
    return chip;
}

/**
 * Every counter one player's card states, in the order it is read.
 *
 * Only what the table is playing: a chip for a rule nobody picked is a line of
 * a rail that must never scroll, spent on a zero that can never change. What is
 * *not* here is anyone's hand - the server sends counts for every player and
 * the contents of one's own only, so a count is all this can ever draw.
 *
 * @param {object} board - The board payload
 * @param {object} entry - That player's entry in `board.players`
 * @returns {Array} - [{concept, value, label}]
 */
function scoreChipsFor(board, entry) {
    const ck = board.cities_knights;
    const name = entry.name;

    // The compact card shows one row, matching the mockup's base game:
    // settlement, city, road, then the resource hand. The development-card count
    // is off the card - it is a hidden hand a player reads in the Details fold,
    // not a piece - which keeps a base game's row to one line. Commodities stay
    // on: a table playing them needs that count on the scoreboard too.
    const chips = [
        { concept: 'settlement', value: (entry.settlements || []).length, label: 'settlements' },
        { concept: 'city', value: (entry.cities || []).length, label: 'cities' },
        { concept: 'road', value: (entry.roads || []).length, label: 'roads' },
        { concept: 'resource', value: entry.resource_count ?? 0, label: 'resource cards in hand' }
    ];

    if (board.rules?.commodities === true) {
        chips.push({
            concept: 'commodity', value: entry.commodity_count ?? 0,
            label: 'commodity cards in hand'
        });
    }

    if (board.rules?.ships === true) {
        chips.push({ concept: 'ship', value: (entry.ships || []).length, label: 'ships' });
    }

    // Two different things wear a sword. With the expansion's knights on, the
    // number that matters is how many are standing on the board; without them
    // it is how many knight cards have been played, which is what Largest Army
    // counts. Never both - they are not the same game.
    if (board.rules?.knights === true) {
        chips.push({
            concept: 'knight', value: (ck?.knights?.[name] || []).length,
            label: 'knights on the board'
        });
    } else {
        chips.push({
            concept: 'knight', value: board.knights_played?.[name] || 0,
            label: 'knights played'
        });
    }

    if (board.rules?.city_walls === true) {
        chips.push({
            concept: 'city_wall', value: ck?.city_walls?.[name] || 0, label: 'city walls'
        });
    }

    // The card counts pieces and hands; a title's progress - a longest road's
    // length, harbour points, the holder of each - is award news and lives in
    // the titles panel below, not as a chip here. Keeping it off the card is
    // what lets a full four-player, every-expansion table fit the rail without
    // scrolling, and it is the line the design draws: pieces on the card,
    // titles in the pills.
    return chips;
}

/**
 * Render game sidebar (players only - no observers in game)
 *
 * One card per player: a swatch in the player's own colour (the same colour as
 * their pieces on the board), their name, the word "turn" when it is theirs,
 * their score large and right-aligned, then a wrapping row of named piece
 * counters. The tester's complaint was that the whole table's state should be
 * readable without opening anything, and that the row it replaced - a run of
 * abbreviations that named none of the pieces - could not be. Every card now
 * states the score, both hands as counts, and every kind of piece the table
 * plays with. Which counters appear is decided by the rules and never by the
 * numbers, so a card never changes height as the game goes on.
 */
export function renderGameSidebar(data) {
    gamePlayersList.innerHTML = '';

    // Handle both array of strings and array of player objects
    const players = data.players.map(p => typeof p === 'string' ? p : p.name);
    const board = getBoard() || {};

    players.forEach(name => {
        const playerData = board.players?.find(p => p.name === name) || { name };

        // Built rather than interpolated throughout - a player named with
        // markup would otherwise be parsed as HTML on everyone else's
        // scoreboard.
        const card = document.createElement('li');
        card.className = playerData.is_you ? 'pcard me' : 'pcard';

        const head = document.createElement('div');
        head.className = 'pcard-head';

        const swatch = document.createElement('span');
        swatch.className = 'swatch';
        if (playerData.color) {
            swatch.style.background = playerData.color;
        }
        head.appendChild(swatch);

        const who = document.createElement('span');
        who.className = 'pname';
        who.textContent = name;
        head.appendChild(who);

        // Whose turn it is, in a word rather than a fill: the seat on turn
        // changes every turn, and a background that appears and disappears
        // would resize the card under the rest of the rail on every change.
        if (name === getCurrentPlayer()) {
            const turn = document.createElement('span');
            turn.className = 'pturn';
            turn.textContent = '· turn';
            head.appendChild(turn);
        }

        const score = document.createElement('span');
        score.className = 'pvp';
        const points = document.createElement('b');
        points.className = 'num';
        points.textContent = playerData.victory_points || 0;
        const unit = document.createElement('small');
        unit.textContent = 'pts';
        score.appendChild(points);
        score.appendChild(unit);
        head.appendChild(score);

        const chips = document.createElement('div');
        chips.className = 'chips';
        scoreChipsFor(board, playerData).forEach(chip => {
            chips.appendChild(scoreChip(chip.concept, chip.value, chip.label));
        });

        card.appendChild(head);
        card.appendChild(chips);
        gamePlayersList.appendChild(card);
    });

    renderAwardSummary();
    renderTurnIndicator();
}

/**
 * One title pill: a line icon, the title's name, and who holds it on what.
 *
 * Status-token colours, so a held title carries the same warn/good/accent hue
 * as the rest of the game; a title nobody holds stays neutral rather than
 * dropping off the list, since "unclaimed, best so far" is as much a fact worth
 * reading as a holder. The name lives in the `<b>`, so the icon beside it is
 * decorative and left to the screen reader as such.
 *
 * @param {string} concept - a STATUS_ICON key for the glyph
 * @param {string} modifier - '' | 'lead' | 'road' | 'army' for the pill colour
 * @param {string} title - the title's name
 * @param {string} whoText - holder and value, or the unclaimed line
 * @param {boolean} numeric - whether `whoText` carries a number to align
 * @returns {HTMLElement}
 */
function awardPill(concept, modifier, title, whoText, numeric) {
    const pill = document.createElement('span');
    pill.className = modifier ? `award ${modifier}` : 'award';
    pill.innerHTML = statusIcon(concept);

    const name = document.createElement('b');
    name.textContent = title;
    pill.appendChild(name);

    // Built rather than interpolated: a player named with markup would
    // otherwise be parsed as HTML on everyone else's scoreboard.
    const holder = document.createElement('span');
    holder.className = numeric ? 'who num' : 'who';
    holder.textContent = whoText;
    pill.appendChild(holder);

    return pill;
}

/**
 * Who currently holds each title on the table, as pills.
 *
 * Longest Road and the Harbormaster were in the payload and nowhere on screen:
 * a player could take either one off someone without either of them being told.
 * Each is stated in full - holder and the number that decides it - because the
 * interesting question is usually "who is about to take it", which needs the
 * runners-up too.
 */
function renderAwardSummary() {
    if (!awardSummary) {
        return;
    }

    const board = getBoard();
    if (!board) {
        awardSummary.innerHTML = '';
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
        return Number.isFinite(minimum) ? ` · needs ${minimum}` : '';
    };

    // The unclaimed line: the leading count and the threshold, kept short
    // enough that the pill does not wrap onto a second line in the rail's
    // width - a title nobody holds is worth a line, not two.
    const openLine = (scores, ruleId) => `best ${best(scores)}${needs(ruleId)}`;

    // Seafarers plays for the Longest Trade Route *instead of* the Longest
    // Road, and roads and ships both count toward it - so a route that was
    // mostly ships was being reported as "10 roads". The rulebook counts it in
    // segments (expansions.md 77-84).
    const tradeRoute = board.rules?.longest_trade_route === true;

    const pills = [];

    // Who leads on victory points, as a crown - the one title read straight off
    // the score. Shown only when a single player is strictly ahead: a tie has
    // no leader, and an all-zero opening has none worth naming.
    const scores = (board.players || []).map(p => ({ name: p.name, vp: p.victory_points || 0 }));
    const topScore = Math.max(0, ...scores.map(s => s.vp));
    const leaders = scores.filter(s => s.vp === topScore);
    if (topScore > 0 && leaders.length === 1) {
        pills.push(awardPill('leader', 'lead', 'Leader', leaders[0].name, false));
    }

    pills.push(awardPill(
        'longest_road', 'road',
        tradeRoute ? 'Longest Trade Route' : 'Longest Road',
        board.longest_road_holder
            ? `${board.longest_road_holder} · ${roadLengths[board.longest_road_holder] || 0} `
              + (tradeRoute ? 'segments' : 'roads')
            : openLine(roadLengths, 'longest_road_minimum'),
        true
    ));

    pills.push(awardPill(
        'largest_army', 'army', 'Largest Army',
        board.largest_army_holder
            ? `${board.largest_army_holder} · ${knights[board.largest_army_holder] || 0} knights`
            : openLine(knights, 'largest_army_minimum'),
        true
    ));

    // Only when the table switched the rule on: a title nobody is playing for
    // is noise on a panel that must stay short enough never to scroll.
    if (board.rules?.harbormaster === true) {
        pills.push(awardPill(
            'harbormaster', '', 'Harbormaster',
            board.harbormaster_holder
                ? `${board.harbormaster_holder} · ${harborPoints[board.harbormaster_holder] || 0} harbour pts`
                : `best ${best(harborPoints)} · needs 3`,
            true
        ));
    }

    // The merchant is worth a victory point for as long as its owner keeps it,
    // and it changes hands the moment somebody else plays the card. Listed only
    // once one is on the board: a title nobody holds is a pill this panel cannot
    // spare.
    if (board.merchant_holder) {
        pills.push(awardPill('merchant', '', 'Merchant',
            `${board.merchant_holder} · 1 pt`, false));
    }

    const wrap = document.createElement('div');
    wrap.className = 'awards';
    pills.forEach(pill => wrap.appendChild(pill));

    awardSummary.innerHTML = '';
    awardSummary.appendChild(wrap);
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
