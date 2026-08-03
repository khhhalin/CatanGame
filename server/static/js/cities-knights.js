import { COMMODITY_ICONS, RESOURCE_ICONS } from './constants.js';
import { barbarianDefense, barbarianPanel, barbarianStatus, barbarianTrack, buildKnightBtn, buildWallBtn, gameBoard, gameScreen, improvementTracks, improvementsPanel, knightHint, knightList, knightsPanel, moveKnightBtn, placeRoadBtn, placeSettlementBtn, upgradeCityBtn } from './dom.js';
import { findMyPlayer } from './panels.js';
import { emitGame } from './socket.js';
import { getBoard, getGamePhase, isMyTurn, viewState } from './state.js';

// --------------------------------------------------------- Cities & Knights
//
// Everything in this section renders from `board.cities_knights` and shows
// nothing at all unless `board.rules.cities_and_knights` is on, so a base game
// looks exactly as it did before the expansion existed.
//
// The costs below are duplicated from server/game/cities_knights.py. They exist
// only to grey out a button and say why before the round trip - the server
// checks all of them again and its answer is what the board is drawn from.


/**
 * The board half of the Cities & Knights actions.
 * Building a knight or a wall is one tap; moving is two, so the first tap only
 * records where the knight is standing and the second one sends the move.
 *
 * @param {string} vertexKey - Vertex the player tapped
 */
export function handleCkVertexTap(vertexKey) {
    // The panels are hidden in a base game, but a stale armed mode must not
    // survive into one either
    if (!ckEnabled()) {
        viewState.selectedBuilding = null;
        return;
    }

    if (viewState.selectedBuilding === 'knight') {
        emitGame('build_knight', { name: viewState.identity.name, vertex: vertexKey });
        return;
    }

    if (viewState.selectedBuilding === 'city_wall') {
        emitGame('build_city_wall', { name: viewState.identity.name, vertex: vertexKey });
        return;
    }

    if (!viewState.knightMoveFrom) {
        viewState.knightMoveFrom = vertexKey;
        renderCitiesKnights();
        return;
    }

    emitGame('move_knight', {
        name: viewState.identity.name,
        from_vertex: viewState.knightMoveFrom,
        to_vertex: vertexKey
    });
    viewState.knightMoveFrom = null;
    renderCitiesKnights();
}

const TRACK_ORDER = ['trade', 'politics', 'science'];
const TRACK_LABELS = { trade: 'Trade', politics: 'Politics', science: 'Science' };

const KNIGHT_RANK_NAMES = { 1: 'Basic', 2: 'Strong', 3: 'Mighty' };
const KNIGHT_BUILD_COST = { sheep: 1, ore: 1 };
const KNIGHT_ACTIVATE_COST = { wheat: 1 };
const KNIGHT_PROMOTE_COST = { sheep: 1, ore: 1 };
const CITY_WALL_COST = { brick: 2 };
const MAX_CITY_WALLS = 3;
const MAX_KNIGHTS_PER_RANK = 2;
const MAX_IMPROVEMENT_LEVEL = 5;
const ABILITY_LEVEL = 3;
const MIGHTY_RANK = 3;

// The board modes this section adds to the settlement/road/city set
const CK_MODES = ['knight', 'knight_move', 'city_wall'];

/**
 * Whether the running game has Cities & Knights and has sent its state.
 */
export function ckEnabled() {
    return getBoard()?.rules?.cities_and_knights === true
        && Boolean(getBoard()?.cities_knights);
}

/**
 * Whether a selection mode belongs to this expansion.
 */
export function isCkMode(mode) {
    return CK_MODES.includes(mode);
}

/**
 * Render a cost as "1🐑 1🪨".
 *
 * @param {object} cost - {resource: amount}
 * @returns {string}
 */
function formatCost(cost) {
    return Object.entries(cost)
        .map(([resource, amount]) => `${amount}${RESOURCE_ICONS[resource] || resource}`)
        .join(' ');
}

/**
 * Whether a hand covers a cost.
 *
 * @param {object} held - {resource: amount} the player holds
 * @param {object} cost - {resource: amount} required
 */
function canAfford(held, cost) {
    return Object.entries(cost).every(([resource, amount]) => (held?.[resource] || 0) >= amount);
}

/**
 * Name the first resource a player is short of, for a disabled button's reason.
 *
 * @returns {string} - Empty when the cost is covered
 */
function shortfallReason(held, cost) {
    for (const [resource, amount] of Object.entries(cost)) {
        const have = held?.[resource] || 0;
        if (have < amount) {
            return `Need ${amount} ${resource}, you have ${have}`;
        }
    }
    return '';
}

/**
 * Why no Cities & Knights action can be taken at all right now, if so.
 * Every action shares these two, so the per-action checks stay to their rule.
 *
 * @returns {string} - Empty when the player may act
 */
function ckTurnBlockReason() {
    if (getGamePhase() === 'setup') {
        return 'Not during setup';
    }
    if (!isMyTurn()) {
        return 'Not your turn';
    }
    return '';
}

/**
 * Arm or disarm one of this expansion's board modes.
 * Same single-mode rule as the settlement/road/city buttons: arming one of
 * these disarms those, and vice versa.
 *
 * @param {string} mode - One of CK_MODES
 */
function toggleCkMode(mode) {
    if (!ckEnabled()) {
        return;
    }
    viewState.selectedBuilding = viewState.selectedBuilding === mode ? null : mode;
    viewState.knightMoveFrom = null;

    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn].forEach(button => {
        button.classList.remove('active');
    });
    gameBoard.classList.toggle('placement-mode', Boolean(viewState.selectedBuilding));

    syncCkModeButtons();
    renderCitiesKnights();
}

/**
 * Show which of this expansion's board modes is armed, if any.
 * Called from the base placement buttons too, so exactly one mode ever looks
 * selected.
 */
export function syncCkModeButtons() {
    if (!buildKnightBtn || !moveKnightBtn || !buildWallBtn) {
        return;
    }
    buildKnightBtn.classList.toggle('active', viewState.selectedBuilding === 'knight');
    moveKnightBtn.classList.toggle('active', viewState.selectedBuilding === 'knight_move');
    buildWallBtn.classList.toggle('active', viewState.selectedBuilding === 'city_wall');

    if (viewState.selectedBuilding !== 'knight_move') {
        viewState.knightMoveFrom = null;
    }
}

/**
 * Render every Cities & Knights panel, or hide them all.
 * This is the only entry point: it is safe to call with no board, in the base
 * game, or as an observer.
 */
export function renderCitiesKnights() {
    const enabled = ckEnabled();
    const player = enabled ? findMyPlayer() : null;

    // Three more panels do not fit the rail's base-game width
    gameScreen.classList.toggle('ck-on', enabled);

    barbarianPanel?.classList.toggle('hidden', !enabled);
    // The barbarian clock is public and matters to a spectator too; the other
    // two panels are one player's own board and have nothing to say without one.
    improvementsPanel?.classList.toggle('hidden', !enabled || !player);
    knightsPanel?.classList.toggle('hidden', !enabled || !player);

    if (!enabled) {
        viewState.knightMoveFrom = null;
        return;
    }

    renderBarbarianTrack();

    if (player) {
        renderImprovements(player);
        renderKnights(player);
    }
    syncCkModeButtons();
}

/**
 * The barbarian ship's progress towards Catan - the expansion's clock.
 * Deliberately loud near the end: a table that does not see the attack coming
 * loses cities to it.
 */
function renderBarbarianTrack() {
    if (!barbarianTrack || !barbarianStatus || !barbarianDefense) {
        return;
    }

    const ck = getBoard().cities_knights;
    const length = ck.barbarian_track_length || 7;
    const position = Math.max(0, Math.min(length, ck.barbarian_position || 0));
    const stepsLeft = length - position;
    const urgency = stepsLeft <= 1 ? 'danger' : stepsLeft <= 2 ? 'warning' : '';

    const pips = document.createDocumentFragment();
    for (let step = 1; step <= length; step += 1) {
        const pip = document.createElement('span');
        pip.className = step <= position ? 'barbarian-pip filled' : 'barbarian-pip';
        pips.appendChild(pip);
    }
    barbarianTrack.innerHTML = '';
    barbarianTrack.appendChild(pips);
    barbarianTrack.className = `barbarian-track ${urgency}`;
    barbarianTrack.setAttribute(
        'aria-label',
        `Barbarian ship at space ${position} of ${length}`
    );

    barbarianStatus.className = `barbarian-status ${urgency}`;
    barbarianStatus.textContent = stepsLeft <= 0
        ? `${position}/${length} — the barbarians are landing`
        : `${position}/${length} — ${stepsLeft} barbarian roll${stepsLeft === 1 ? '' : 's'} away`;

    // Defence is the whole table's active knights against every city on the
    // board, so it is worth stating even on someone else's turn.
    const players = getBoard().players || [];
    const strength = Object.values(ck.knights || {}).reduce((total, knights) => (
        total + (knights || []).reduce((sum, knight) => sum + (knight.active ? knight.rank : 0), 0)
    ), 0);
    const cities = players.reduce((total, entry) => total + (entry.cities?.length || 0), 0);

    const notes = [`Knights ${strength} vs ${cities} cities`];
    if (strength < cities) {
        notes.push('cities will be pillaged');
    }
    if (!ck.barbarians_have_attacked) {
        notes.push('the robber stays put until the first attack');
    }
    // Worth 1 victory point each and invisible everywhere else in the UI
    const defenderCards = ck.defender_cards?.[viewState.identity.name] || 0;
    if (defenderCards > 0) {
        notes.push(`🛡️ ${defenderCards} Defender of Catan`);
    }
    barbarianDefense.className = strength < cities ? 'ck-note danger' : 'ck-note';
    barbarianDefense.textContent = notes.join(' · ');
}

/**
 * The three city improvement tracks, with what the next level costs.
 * Level N costs N commodities of the track's own type, so the next level always
 * costs one more than the last.
 *
 * @param {object} player - Own player entry from the board payload
 */
function renderImprovements(player) {
    if (!improvementTracks) {
        return;
    }

    const ck = getBoard().cities_knights;
    const tracks = ck.tracks || {};
    const levels = ck.improvements?.[player.name] || {};
    const commodities = player.commodities || {};
    const hasCity = (player.cities || []).length > 0;
    const turnBlock = ckTurnBlockReason();

    const fragment = document.createDocumentFragment();

    TRACK_ORDER.forEach(track => {
        const spec = tracks[track];
        if (!spec) {
            return;
        }

        const names = Array.isArray(spec.levels) ? spec.levels : [];
        const commodity = spec.commodity;
        const icon = COMMODITY_ICONS[commodity] || '';
        const level = levels[track] || 0;
        const held = commodities[commodity] || 0;
        const nextCost = level + 1;

        const row = document.createElement('div');
        row.className = 'improvement-row';

        const head = document.createElement('div');
        head.className = 'improvement-head';

        const label = document.createElement('span');
        label.className = `improvement-name track-${track}`;
        label.textContent = `${icon} ${TRACK_LABELS[track] || track}`;

        const levelBadge = document.createElement('span');
        levelBadge.className = 'improvement-level';
        levelBadge.textContent = `${level}/${MAX_IMPROVEMENT_LEVEL}`;

        head.appendChild(label);
        head.appendChild(levelBadge);
        row.appendChild(head);

        const built = document.createElement('div');
        built.className = 'improvement-built';
        built.textContent = level > 0 ? names[level - 1] || `Level ${level}` : 'Nothing built yet';
        row.appendChild(built);

        // The level-3 building is the one that grants an ability, so say which
        // ability it is rather than leaving the player to count rows.
        if (level >= ABILITY_LEVEL && names[ABILITY_LEVEL - 1]) {
            const ability = document.createElement('div');
            ability.className = 'ck-badge ability';
            ability.textContent = `✔ ${names[ABILITY_LEVEL - 1]} in use`;
            row.appendChild(ability);
        }

        const holder = ck.metropolis?.[track];
        if (holder) {
            const metropolis = document.createElement('div');
            const mine = holder === player.name;
            metropolis.className = mine ? 'ck-badge metropolis' : 'ck-note';
            metropolis.textContent = mine
                ? `🏛️ ${TRACK_LABELS[track] || track} metropolis is yours`
                : `🏛️ metropolis held by ${holder}`;
            row.appendChild(metropolis);
        }

        let reason = '';
        if (level >= MAX_IMPROVEMENT_LEVEL) {
            reason = 'This track is complete';
        } else if (turnBlock) {
            reason = turnBlock;
        } else if (!hasCity) {
            reason = 'You need a city to improve';
        } else if (held < nextCost) {
            reason = `Need ${nextCost} ${commodity}, you have ${held}`;
        }

        const buy = document.createElement('button');
        buy.type = 'button';
        buy.className = 'ck-buy';
        buy.dataset.track = track;
        buy.disabled = Boolean(reason);
        buy.title = reason;
        buy.textContent = level >= MAX_IMPROVEMENT_LEVEL
            ? 'Complete'
            : `Buy ${names[level] || `level ${nextCost}`} · ${nextCost}${icon}`;
        row.appendChild(buy);

        if (reason) {
            const note = document.createElement('div');
            note.className = 'ck-note';
            note.textContent = reason;
            row.appendChild(note);
        }

        fragment.appendChild(row);
    });

    improvementTracks.innerHTML = '';
    improvementTracks.appendChild(fragment);
}

/**
 * The player's own knights, the three actions that need a board tap, and the
 * city walls that share the same tap flow.
 *
 * @param {object} player - Own player entry from the board payload
 */
function renderKnights(player) {
    if (!knightList || !buildKnightBtn || !moveKnightBtn || !buildWallBtn) {
        return;
    }

    const ck = getBoard().cities_knights;
    const knights = ck.knights?.[player.name] || [];
    const resources = player.resources || {};
    const walls = ck.city_walls?.[player.name] || 0;
    const hasFortress = (ck.improvements?.[player.name]?.politics || 0) >= ABILITY_LEVEL;
    const turnBlock = ckTurnBlockReason();

    const rankCount = (rank) => knights.filter(knight => knight.rank === rank).length;

    // Build
    let buildReason = turnBlock;
    if (!buildReason && rankCount(1) >= MAX_KNIGHTS_PER_RANK) {
        buildReason = 'No basic knight pieces left';
    }
    if (!buildReason) {
        buildReason = shortfallReason(resources, KNIGHT_BUILD_COST);
    }
    buildKnightBtn.textContent = `Build knight · ${formatCost(KNIGHT_BUILD_COST)}`;
    buildKnightBtn.disabled = Boolean(buildReason);
    buildKnightBtn.title = buildReason || 'Then tap a vacant intersection on one of your roads';

    // Move
    let moveReason = turnBlock;
    if (!moveReason && !knights.some(knight => knight.can_act)) {
        moveReason = 'No knight can act this turn';
    }
    moveKnightBtn.textContent = 'Move knight';
    moveKnightBtn.disabled = Boolean(moveReason);
    moveKnightBtn.title = moveReason || 'Tap the knight, then where it should go';

    // City wall
    let wallReason = turnBlock;
    if (!wallReason && walls >= MAX_CITY_WALLS) {
        wallReason = `All ${MAX_CITY_WALLS} walls are built`;
    }
    if (!wallReason) {
        wallReason = shortfallReason(resources, CITY_WALL_COST);
    }
    buildWallBtn.textContent =
        `City wall ${walls}/${MAX_CITY_WALLS} · ${formatCost(CITY_WALL_COST)}`;
    buildWallBtn.disabled = Boolean(wallReason);
    buildWallBtn.title = wallReason || 'Then tap one of your cities';

    if (knightHint) {
        knightHint.textContent = ckModeHint();
        knightHint.classList.toggle('hidden', !isCkMode(viewState.selectedBuilding));
    }

    const fragment = document.createDocumentFragment();

    if (knights.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'no-cards';
        empty.textContent = 'No knights on the board';
        fragment.appendChild(empty);
    }

    knights.forEach(knight => {
        const row = document.createElement('div');
        row.className = knight.vertex === viewState.knightMoveFrom ? 'knight-row selected' : 'knight-row';

        const title = document.createElement('div');
        title.className = 'knight-title';

        const name = document.createElement('span');
        name.className = `knight-rank rank-${knight.rank}`;
        name.textContent = `⚔️ ${KNIGHT_RANK_NAMES[knight.rank] || `Rank ${knight.rank}`}`;

        const state = document.createElement('span');
        state.className = knight.active ? 'knight-state active' : 'knight-state idle';
        state.textContent = knight.active
            ? (knight.can_act ? 'Active' : 'Active · spent')
            : 'Inactive';

        title.appendChild(name);
        title.appendChild(state);
        row.appendChild(title);

        const actions = document.createElement('div');
        actions.className = 'knight-buttons';

        let activateReason = turnBlock;
        if (!activateReason && knight.active) {
            activateReason = 'Already active';
        }
        if (!activateReason) {
            activateReason = shortfallReason(resources, KNIGHT_ACTIVATE_COST);
        }
        actions.appendChild(buildKnightActionButton(
            'activate', knight.vertex,
            `Activate · ${formatCost(KNIGHT_ACTIVATE_COST)}`, activateReason
        ));

        let promoteReason = turnBlock;
        if (!promoteReason && knight.rank >= MIGHTY_RANK) {
            promoteReason = 'Already mighty';
        }
        if (!promoteReason && knight.rank + 1 === MIGHTY_RANK && !hasFortress) {
            promoteReason = 'Mighty knights need the Fortress (Politics 3)';
        }
        if (!promoteReason && rankCount(knight.rank + 1) >= MAX_KNIGHTS_PER_RANK) {
            const nextRank = KNIGHT_RANK_NAMES[knight.rank + 1].toLowerCase();
            promoteReason = `No ${nextRank} knight pieces left`;
        }
        if (!promoteReason) {
            promoteReason = shortfallReason(resources, KNIGHT_PROMOTE_COST);
        }
        actions.appendChild(buildKnightActionButton(
            'promote', knight.vertex,
            `Promote · ${formatCost(KNIGHT_PROMOTE_COST)}`, promoteReason
        ));

        row.appendChild(actions);
        fragment.appendChild(row);
    });

    knightList.innerHTML = '';
    knightList.appendChild(fragment);
}

/**
 * One per-knight button. The vertex travels in a data attribute so the list can
 * be rebuilt on every board update without touching its listener.
 *
 * @param {string} action - 'activate' or 'promote'
 * @param {string} vertex - Vertex the knight stands on
 * @param {string} label - Button text, including the cost
 * @param {string} reason - Why it is disabled, or empty
 * @returns {HTMLButtonElement}
 */
function buildKnightActionButton(action, vertex, label, reason) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ck-knight-action';
    button.dataset.knightAction = action;
    button.dataset.vertex = vertex;
    button.textContent = label;
    button.disabled = Boolean(reason);
    button.title = reason;
    return button;
}

/**
 * What the player is expected to tap next, for the armed mode.
 */
function ckModeHint() {
    if (viewState.selectedBuilding === 'knight') {
        return 'Tap a vacant intersection touching one of your roads.';
    }
    if (viewState.selectedBuilding === 'city_wall') {
        return 'Tap one of your cities.';
    }
    if (viewState.selectedBuilding === 'knight_move') {
        return viewState.knightMoveFrom
            ? 'Now tap the intersection to move it to.'
            : 'Tap the knight you want to move.';
    }
    return '';
}

// Delegated listeners, registered once: both lists are rebuilt from scratch on
// every board update, which orphans anything bound to their old nodes.
improvementTracks?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-track]');
    if (!button || button.disabled) {
        return;
    }
    emitGame('buy_improvement', { name: viewState.identity.name, track: button.dataset.track });
});

knightList?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-knight-action]');
    if (!button || button.disabled) {
        return;
    }
    const eventName = button.dataset.knightAction === 'promote'
        ? 'promote_knight'
        : 'activate_knight';
    emitGame(eventName, { name: viewState.identity.name, vertex: button.dataset.vertex });
});

buildKnightBtn?.addEventListener('click', () => toggleCkMode('knight'));
moveKnightBtn?.addEventListener('click', () => toggleCkMode('knight_move'));
buildWallBtn?.addEventListener('click', () => toggleCkMode('city_wall'));
