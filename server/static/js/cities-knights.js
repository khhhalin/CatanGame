import { COMMODITY_ICONS, COMMODITY_TYPES, RESOURCE_ICONS } from './constants.js';
import { barbarianChipValue, barbarianDefense, barbarianLastAttack, barbarianPanel, barbarianStatus, barbarianTrack, buildKnightBtn, buildWallBtn, devCardsPanel, gameBoard, gameScreen, improvementTracks, improvementsChipValue, improvementsPanel, knightHint, knightList, knightsChipValue, knightsPanel, moveKnightBtn, placeRoadBtn, placeSettlementBtn, progressCardsChipValue, progressCardsPanel, progressHandDiv, upgradeCityBtn } from './dom.js';
import { findMyPlayer } from './player-view.js';
import { syncSeaModeButtons } from './seafarers.js';
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
        expectPlacement('knight', () => Boolean(myKnightAt(vertexKey)));
        return;
    }

    if (viewState.selectedBuilding === 'city_wall') {
        const before = myWallCount();
        emitGame('build_city_wall', { name: viewState.identity.name, vertex: vertexKey });
        expectPlacement('city_wall', () => myWallCount() > before);
        return;
    }

    if (!viewState.knightMoveFrom) {
        viewState.knightMoveFrom = vertexKey;
        renderCitiesKnights();
        return;
    }

    const origin = viewState.knightMoveFrom;
    emitGame('move_knight', {
        name: viewState.identity.name,
        from_vertex: origin,
        to_vertex: vertexKey
    });
    viewState.knightMoveFrom = null;
    expectPlacement('knight_move', () => !myKnightAt(origin));
    renderCitiesKnights();
}

// ------------------------------------------------------- disarming a mode
//
// A build mode is deliberately left armed across board updates: a knight move
// takes two taps and someone else's trade landing between them must not disarm
// the board halfway through. The cost of that rule was the tester's bug - once
// a knight was actually placed the board stayed in knight-placement mode, and
// the next tap anywhere tried to build another one.
//
// So the mode survives every payload except the one that shows the placement it
// was armed for has landed. `settled` is that test, evaluated against the board
// the server has just sent.

let pendingCkPlacement = null;

/**
 * Remember what the tap just sent was meant to achieve.
 *
 * @param {string} mode - The armed mode, so a re-arm mid-flight is not undone
 * @param {Function} settled - Reads the current board; true once it has landed
 */
function expectPlacement(mode, settled) {
    pendingCkPlacement = { mode, settled };
}

/**
 * Drop the armed mode once the server's board shows the placement happened.
 * A refusal never gets here: the server rejects without broadcasting a board,
 * so the mode stays armed and the player can simply aim again.
 */
function clearSettledPlacement() {
    if (!pendingCkPlacement) {
        return;
    }
    // Re-arming a different mode before the answer came back replaces the
    // intent; honouring the old one would disarm the new one.
    if (viewState.selectedBuilding !== pendingCkPlacement.mode) {
        pendingCkPlacement = null;
        return;
    }
    if (!pendingCkPlacement.settled()) {
        return;
    }
    pendingCkPlacement = null;
    viewState.selectedBuilding = null;
    viewState.knightMoveFrom = null;
    gameBoard.classList.remove('placement-mode');
}

/**
 * This player's knight standing on a vertex, if any.
 */
export function myKnightAt(vertexKey) {
    const mine = getBoard()?.cities_knights?.knights?.[viewState.identity.name] || [];
    return mine.find(knight => knight.vertex === vertexKey) || null;
}

function myWallCount() {
    return getBoard()?.cities_knights?.city_walls?.[viewState.identity.name] || 0;
}

// --------------------------------------------------------- the last attack
//
// `resolve_barbarian_attack` runs synchronously inside `roll_dice` and picks
// the pillaged city itself; there is no pending-choice phase and no server
// event that asks a player to give one up. What the client can do - and did
// not - is say what happened. The result arrives once, on `barbarian_attack`,
// and no later payload repeats it, so it is latched here and restated in the
// barbarian panel until the next one lands.

let lastAttack = null;

/**
 * Record the outcome of a barbarian attack for the panel to restate.
 *
 * @param {object} data - The `barbarian_attack` payload
 */
export function noteBarbarianAttack(data) {
    lastAttack = data && typeof data === 'object' ? data : null;
    renderCitiesKnights();
}

/**
 * The last attack in one sentence, or '' if there has not been one.
 *
 * @returns {string}
 */
export function describeLastAttack() {
    if (!lastAttack) {
        return '';
    }
    const score = `⚔️${lastAttack.defence} vs 🏛️${lastAttack.attack}`;
    if (lastAttack.won) {
        const defenders = lastAttack.defenders || [];
        if (defenders.length === 0) {
            return `Last attack: repelled, ${score}, with nobody to reward`;
        }
        return defenders.length === 1
            ? `Last attack: repelled, ${score} — ${defenders[0]} took Defender of Catan`
            : `Last attack: repelled, ${score} — ${defenders.join(' and ')} tied and drew a card`;
    }
    const pillaged = lastAttack.pillaged || [];
    return pillaged.length > 0
        ? `Last attack: lost, ${score} — ${pillaged.join(', ')} lost a city`
        : `Last attack: lost, ${score} — no city could be pillaged`;
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

// What each per-knight action is called and what it costs, worded once: the
// Knights fold and the overlay a tap on the knight raises both use these, and
// a player who learns the label in one place must read the same one in the
// other.
// `formatCost` is a hoisted function declaration, so the costs above are read
// here rather than copied - a second copy of "1 sheep 1 ore" is exactly the
// kind of literal that drifts.
export const KNIGHT_ACTION_LABELS = {
    activate: `Activate · ${formatCost(KNIGHT_ACTIVATE_COST)}`,
    promote: `Promote · ${formatCost(KNIGHT_PROMOTE_COST)}`,
    move: 'Move',
};

/**
 * Whether one Cities & Knights rule is in play in the running game.
 *
 * The expansion used to be a single `cities_and_knights` flag; it is eight
 * separate rules now, and a table may take the knights without the improvement
 * tracks. So every panel below asks about its own rule rather than about "the
 * expansion", and reading the old flag would have hidden all of them for good.
 *
 * @param {string} ruleId - One of the expansion's rule ids
 */
export function ckRule(ruleId) {
    return getBoard()?.rules?.[ruleId] === true;
}

/**
 * Whether the running game keeps expansion state at all - the improvement
 * tracks, knights, walls, barbarian ship and progress decks. The server builds
 * that object when any rule needs it, so its presence is the honest test.
 */
export function ckEnabled() {
    return Boolean(getBoard()?.cities_knights);
}

/**
 * Whether a selection mode belongs to this expansion.
 *
 * The progress-card picking modes count: `updateGameUI` disarms every mode that
 * is not one of this expansion's or Seafarers' on each board update, and a card
 * being aimed has to survive somebody else's trade landing exactly as a
 * half-finished knight move does.
 */
export function isCkMode(mode) {
    return CK_MODES.includes(mode) || isProgressMode(mode);
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
 * Exported because every action in the client - build, upgrade, buy a card,
 * improve a city - greys out with a reason rather than failing on click, and
 * they must all word it the same way.
 *
 * @returns {string} - Empty when the cost is covered
 */
export function shortfallReason(held, cost) {
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
 * Why each of one knight's three actions is refused right now, or '' for the
 * ones that are legal.
 *
 * A copy of the engine's rules and only ever a copy - the server checks all of
 * it again - so it errs the way every other affordance here does: it greys an
 * action out and says why rather than letting the click fail. Shared by the
 * Knights fold and by the overlay a tap on the knight itself raises, because
 * two lists of reasons would disagree the first time one of them changed.
 *
 * @param {object} knight - A knight entry from `cities_knights.knights`
 * @returns {object} - {activate, promote, move}, each a reason or ''
 */
export function knightActionReasons(knight) {
    const player = findMyPlayer();
    const ck = getBoard()?.cities_knights;
    if (!player || !ck) {
        const none = 'No game is running';
        return { activate: none, promote: none, move: none };
    }

    const knights = ck.knights?.[player.name] || [];
    const resources = player.resources || {};
    const hasFortress = (ck.improvements?.[player.name]?.politics || 0) >= ABILITY_LEVEL;
    const blocked = ckRule('knights')
        ? ckTurnBlockReason()
        : 'Knights are not one of this table\'s rules';
    const rankCount = (rank) => knights.filter(other => other.rank === rank).length;

    let activate = blocked;
    if (!activate && knight.active) {
        activate = 'Already active';
    }
    if (!activate) {
        activate = shortfallReason(resources, KNIGHT_ACTIVATE_COST);
    }

    let promote = blocked;
    if (!promote && knight.rank >= MIGHTY_RANK) {
        promote = 'Already mighty';
    }
    if (!promote && knight.rank + 1 === MIGHTY_RANK && !hasFortress) {
        promote = 'Mighty knights need the Fortress (Politics 3)';
    }
    if (!promote && rankCount(knight.rank + 1) >= MAX_KNIGHTS_PER_RANK) {
        promote = `No ${KNIGHT_RANK_NAMES[knight.rank + 1].toLowerCase()} knight pieces left`;
    }
    if (!promote) {
        promote = shortfallReason(resources, KNIGHT_PROMOTE_COST);
    }

    // `can_act` is the engine's own answer and covers three separate refusals,
    // so the two a player can do something about are named apart from it.
    let move = blocked;
    if (!move && !knight.active) {
        move = 'Activate it first';
    }
    if (!move && !knight.can_act) {
        move = 'It cannot act again until your next turn';
    }

    return { activate, promote, move };
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

    // A Seafarers mode is a placement mode too: only one may ever be armed
    syncCkModeButtons();
    syncSeaModeButtons();
    renderCitiesKnights();
}

/**
 * Arm the knight move with this knight already picked up.
 *
 * The two-tap move is untouched by this: the overlay's Move button does
 * exactly what the first tap does - it holds the knight and sends nothing -
 * so the next tap is the second one either way.
 *
 * @param {string} vertexKey - Where the knight this player is moving stands
 */
export function startKnightMove(vertexKey) {
    if (viewState.selectedBuilding !== 'knight_move') {
        toggleCkMode('knight_move');
    }
    viewState.knightMoveFrom = vertexKey;
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

    // Arming anything else abandons a card that was waiting for a target. The
    // card is untouched: nothing was sent for it, so it is still in hand.
    if (!isProgressMode(viewState.selectedBuilding)) {
        viewState.progressPick = { card: null, picked: [] };
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

    gameScreen.classList.toggle('ck-on', enabled);

    // Each fold answers to its own rule: a table can take the knights and the
    // barbarians without the improvement tracks, and a fold for a rule nobody
    // picked is a line of the rail spent on nothing.
    //
    // Progress cards replace the development card deck outright - the server
    // refuses `buy_dev_card` when they are in play - so exactly one of the two
    // card folds is ever on screen.
    const progress = enabled && ckRule('progress_cards');
    devCardsPanel?.classList.toggle('hidden', progress);
    progressCardsPanel?.classList.toggle('hidden', !progress || !player);

    // The barbarian clock is public and matters to a spectator too; the other
    // two folds are one player's own board and have nothing to say without one.
    barbarianPanel?.classList.toggle('hidden', !enabled || !ckRule('barbarians'));
    improvementsPanel?.classList.toggle(
        'hidden', !enabled || !player || !ckRule('city_improvements')
    );
    knightsPanel?.classList.toggle(
        'hidden', !enabled || !player || !(ckRule('knights') || ckRule('city_walls'))
    );

    if (!enabled) {
        viewState.knightMoveFrom = null;
        pendingCkPlacement = null;
        lastAttack = null;
        return;
    }

    // Before anything renders: it decides whether a mode is still armed, and
    // every button below is drawn from that.
    clearSettledPlacement();

    if (ckRule('barbarians')) {
        renderBarbarianTrack();
    }

    if (player) {
        if (ckRule('city_improvements')) {
            renderImprovements(player);
        }
        renderKnights(player);
        if (ckRule('progress_cards')) {
            renderProgressHand(player);
        }
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

    if (barbarianLastAttack) {
        const summary = describeLastAttack();
        barbarianLastAttack.textContent = summary;
        const lost = summary && lastAttack?.won === false;
        barbarianLastAttack.className = summary
            ? (lost ? 'ck-note danger' : 'ck-note')
            : 'ck-note hidden';
    }

    // The folded line. The ship's position is the expansion's clock and the
    // knights-versus-cities comparison is the only thing anyone can do about
    // it, so both are on the chip and neither needs the panel opened.
    if (barbarianChipValue) {
        barbarianChipValue.textContent = `🚢 ${position}/${length} · ⚔️${strength} vs 🏛️${cities}`;
        barbarianChipValue.className = strength < cities
            ? 'fold-value danger'
            : `fold-value ${urgency}`;
    }
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

    // "Trade 0/5 · Politics 0/5 · Science 0/5" - the whole panel in one line,
    // which is all it is most of the time.
    if (improvementsChipValue) {
        improvementsChipValue.textContent = TRACK_ORDER
            .filter(track => tracks[track])
            .map(track => `${TRACK_LABELS[track]} ${levels[track] || 0}/${MAX_IMPROVEMENT_LEVEL}`)
            .join(' · ');
    }
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
    const turnBlock = ckTurnBlockReason();

    const rankCount = (rank) => knights.filter(knight => knight.rank === rank).length;

    // Build
    let buildReason = ckRule('knights') ? turnBlock : 'Knights are not one of this table\'s rules';
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
    let moveReason = ckRule('knights') ? turnBlock : 'Knights are not one of this table\'s rules';
    if (!moveReason && !knights.some(knight => knight.can_act)) {
        moveReason = 'No knight can act this turn';
    }
    moveKnightBtn.textContent = 'Move knight';
    moveKnightBtn.disabled = Boolean(moveReason);
    moveKnightBtn.title = moveReason || 'Tap the knight, then where it should go';

    // City wall
    let wallReason = ckRule('city_walls')
        ? turnBlock
        : 'City walls are not one of this table\'s rules';
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

        const reasons = knightActionReasons(knight);
        actions.appendChild(buildKnightActionButton(
            'activate', knight.vertex, KNIGHT_ACTION_LABELS.activate, reasons.activate
        ));
        actions.appendChild(buildKnightActionButton(
            'promote', knight.vertex, KNIGHT_ACTION_LABELS.promote, reasons.promote
        ));

        row.appendChild(actions);
        fragment.appendChild(row);
    });

    knightList.innerHTML = '';
    knightList.appendChild(fragment);

    // How many knights this player has, how many of them can still do anything
    // this turn, and how many walls are up.
    if (knightsChipValue) {
        const ready = knights.filter(knight => knight.active && knight.can_act).length;
        knightsChipValue.textContent =
            `⚔️ ${knights.length} · ${ready} ready · 🧱 ${walls}/${MAX_CITY_WALLS}`;
    }
}

// ---------------------------------------------------------- progress cards
//
// Cities & Knights replaces the development card deck with three progress card
// decks, drawn when the event die shows a city gate. The board payload carries
// this viewer's own hand by id, everyone else's as a count, plus the catalogue
// that names and describes each card - so nothing about a card is duplicated
// here.
//
// A card's `needs_target` says what the player must supply before the server
// can resolve it. Some of those are a choice from a short list and are offered
// inline; the rest are picked off the board, by arming one of the modes below
// and tapping - the same flow a knight or a city wall goes through.

const TARGET_CHOICES = {
    resource: ['wood', 'brick', 'sheep', 'wheat', 'ore'],
    commodity: COMMODITY_TYPES,
    improvement: TRACK_ORDER
};

// What a card that is picked on the board arms. Keyed by `needs_target`,
// because that is what the server validates the answer against.
const PROGRESS_MODES = {
    hex: 'progress_hex'
};

// The two shapes the server takes: a single key, or a list of them.
const LIST_TARGETS = ['knight', 'two_number_tokens'];

/**
 * Why this card cannot be offered for play at all, or ''.
 *
 * `target_chosen_later` is the server's own answer for the two cards that name
 * a target on the card and are handed none when they are played: Road
 * Building's roads go down afterwards through the free-road flow, and a
 * Merchant Fleet's card type is asked for as a pending choice. Both were greyed
 * out for want of a pick nothing was ever going to ask for.
 *
 * @param {object} card - Catalogue entry from the board payload
 * @returns {string}
 */
function missingTargetFlowReason(card) {
    if (card.target_chosen_later === true || card.needs_target === null) {
        return '';
    }
    const offered = Boolean(TARGET_CHOICES[card.needs_target])
        || Boolean(PROGRESS_MODES[card.needs_target]);
    return offered ? '' : 'Needs a target this client cannot ask for yet';
}

/**
 * Whether a card in the catalogue can be held but never played.
 *
 * Exposed on the debug hook because that is the only honest way to test it:
 * 26 of the 54 cards were dealt and unplayable for as long as this answered
 * true for them, and a test that listed the card ids itself would have gone on
 * passing when a new card joined them.
 *
 * @param {object} card - Catalogue entry from the board payload
 * @returns {boolean}
 */
export function progressCardHasNoFlow(card) {
    return Boolean(missingTargetFlowReason(card));
}

const DECK_ICONS = { science: '🟢', trade: '🟡', politics: '🔵' };

// ------------------------------------------------- picking a card's target
//
// A card whose target is on the board arms a placement mode and is played by
// the tap that follows, which is the flow every other piece in the game already
// uses: the tap pins a ghost, the ✓ sends it, and ✗ or Escape drops it. The
// card itself is held here until then, because nothing reaches the server
// before the pick is complete - so cancelling costs the player nothing, and a
// refused play leaves the card in hand exactly as a refused build leaves the
// resources.

/**
 * Whether a mode is one of the target-picking ones.
 */
export function isProgressMode(mode) {
    return Object.values(PROGRESS_MODES).includes(mode);
}

/**
 * The card a board pick is being made for, or null.
 */
export function progressPickCard() {
    return viewState.progressPick.card;
}

/**
 * The name of the card whose target is being picked, or ''.
 */
export function progressCardName() {
    return pickedCardEntry()?.name || '';
}

/**
 * The catalogue entry for the card being picked for, or null.
 */
function pickedCardEntry() {
    const card = progressPickCard();
    return card ? getBoard()?.cities_knights?.progress_cards?.[card] || null : null;
}

/**
 * Arm the board for one card's target, or disarm it if it is already armed.
 *
 * @param {string} cardId - Card id, which is what `play_progress_card` takes
 * @param {object} card - Its catalogue entry
 */
function toggleProgressPick(cardId, card) {
    const mode = PROGRESS_MODES[card.needs_target];
    if (!mode) {
        return;
    }
    const alreadyArmed = progressPickCard() === cardId && viewState.selectedBuilding === mode;
    // Set before toggling: `syncCkModeButtons` drops the pick whenever the
    // armed mode is not a picking one, which is what disarming has to do.
    viewState.progressPick = alreadyArmed ? { card: null, picked: [] }
        : { card: cardId, picked: [] };
    if (alreadyArmed) {
        toggleCkMode(mode);
        return;
    }
    if (viewState.selectedBuilding !== mode) {
        toggleCkMode(mode);
    } else {
        renderCitiesKnights();
    }
}

// How many targets a card takes, for the few that take more than one, and the
// fewest they will settle for.
const MULTI_PICK = {};

function picksFor(cardId) {
    return MULTI_PICK[cardId] || { max: 1, min: 1 };
}

/**
 * Whether this tap would finish the pick and send the card.
 * A card that takes more than one target records the earlier ones the way a
 * knight move records the knight it picked up - nothing is sent, so there is
 * nothing to confirm either.
 *
 * @param {string} key - Board key the tap snapped to
 * @returns {boolean}
 */
export function progressPickCompletes(key) {
    const cardId = progressPickCard();
    if (!cardId) {
        return false;
    }
    const picked = viewState.progressPick.picked;
    return !picked.includes(key) && picked.length + 1 >= picksFor(cardId).max;
}

/**
 * Record one pick, and send the card once the last one is in.
 *
 * @param {string} key - Board key the tap snapped to
 */
export function handleProgressTargetTap(key) {
    if (!progressPickCard()) {
        return;
    }
    const picked = viewState.progressPick.picked;
    const already = picked.indexOf(key);
    if (already >= 0) {
        // Tapping a pick again takes it back: the only way out of a
        // half-finished multi-target card that does not throw the card away.
        picked.splice(already, 1);
        renderCitiesKnights();
        return;
    }
    picked.push(key);
    if (picked.length >= picksFor(progressPickCard()).max) {
        sendProgressPick();
    } else {
        renderCitiesKnights();
    }
}

/**
 * Play the card with the targets picked so far.
 */
function sendProgressPick() {
    const cardId = progressPickCard();
    const card = pickedCardEntry();
    const picked = viewState.progressPick.picked;
    if (!cardId || !card || picked.length === 0) {
        return;
    }
    const mode = PROGRESS_MODES[card.needs_target];
    emitGame('play_progress_card', {
        name: viewState.identity.name,
        card: cardId,
        target: LIST_TARGETS.includes(card.needs_target) ? picked.slice() : picked[0]
    });
    // Settled once the card has left the hand. A refusal never broadcasts a
    // board, so the mode stays armed and the player can aim again - and the
    // card is still theirs, because the server only spends one it accepted.
    expectPlacement(mode, () => !(getBoard()?.cities_knights?.progress_hand || []).includes(cardId));
    viewState.progressPick.picked = [];
    renderCitiesKnights();
}

// What each card asks the player to tap. Worded per card rather than per
// target shape: "tap a hex" is true of both a Merchant and a Bishop and tells
// the player nothing about which hex either one wants.
const PICK_HINTS = {
    merchant: 'Tap a land hex touching one of your own buildings.',
    bishop: 'Tap the hex to move the robber to.'
};

/**
 * What the player is expected to tap for the card being played, if any.
 */
function progressPickHint() {
    const cardId = progressPickCard();
    if (!cardId) {
        return '';
    }
    return PICK_HINTS[cardId] || 'Tap the target on the board.';
}

/**
 * Which pick the player is on, for a card that takes more than one.
 *
 * @returns {string}
 */
function progressPickProgress() {
    const cardId = progressPickCard();
    const picks = picksFor(cardId);
    const chosen = viewState.progressPick.picked.length;
    return picks.max > 1 ? `pick ${chosen + 1} of ${picks.max}` : 'pick a target';
}

/**
 * The player's own progress cards, with what each one does and whether it can
 * be played right now.
 *
 * @param {object} player - Own player entry from the board payload
 */
function renderProgressHand(player) {
    if (!progressHandDiv) {
        return;
    }

    const ck = getBoard().cities_knights;
    const hand = ck.progress_hand || [];
    const catalogue = ck.progress_cards || {};
    const turnBlock = ckTurnBlockReason();
    const rolled = getBoard().has_rolled_dice === true;

    if (progressCardsChipValue) {
        const held = ck.progress_hand_counts?.[player.name] ?? hand.length;
        // The chip is the one part of this fold that is on screen while the
        // player is aiming at the board - the popover has to be out of the way
        // for that - so it is where a pick in progress is reported.
        const pick = pickedCardEntry();
        progressCardsChipValue.textContent = pick
            ? `🎴 ${pick.name} — ${progressPickProgress()}`
            : `🎴 ${held} held`;
    }

    const fragment = document.createDocumentFragment();

    if (hand.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'no-cards';
        empty.textContent = 'No progress cards. They are drawn on a city gate.';
        fragment.appendChild(empty);
    }

    hand.forEach(cardId => {
        const card = catalogue[cardId];
        if (!card) {
            return;
        }
        fragment.appendChild(buildProgressCardRow(cardId, card, turnBlock, rolled));
    });

    progressHandDiv.innerHTML = '';
    progressHandDiv.appendChild(fragment);
}

/**
 * One card: what it is, what it does, and how to play it.
 *
 * @param {string} cardId - Card id, which is what `play_progress_card` takes
 * @param {object} card - Catalogue entry from the board payload
 * @param {string} turnBlock - Why no action is possible at all, or ''
 * @param {boolean} rolled - Whether the dice are already up this turn
 * @returns {HTMLElement}
 */
function buildProgressCardRow(cardId, card, turnBlock, rolled) {
    const row = document.createElement('div');
    row.className = 'progress-card';

    const title = document.createElement('div');
    title.className = 'progress-card-title';
    title.textContent = `${DECK_ICONS[card.deck] || ''} ${card.name}`;
    row.appendChild(title);

    const summary = document.createElement('div');
    summary.className = 'ck-note';
    summary.textContent = card.summary;
    row.appendChild(summary);

    // The two timings the engine enforces: a "before the roll" card is dead for
    // the rest of the turn once the dice are up, and every other card needs
    // them up first.
    let reason = turnBlock;
    if (!reason && card.timing === 'before_roll' && rolled) {
        reason = 'Played before the dice, and they are already up';
    }
    if (!reason && card.timing !== 'before_roll' && !rolled) {
        reason = 'Roll the dice first';
    }
    if (!reason) {
        reason = missingTargetFlowReason(card);
    }

    const actions = document.createElement('div');
    actions.className = 'progress-card-actions';

    const choices = TARGET_CHOICES[card.needs_target];
    let select = null;
    if (choices) {
        select = document.createElement('select');
        select.className = 'progress-target';
        select.setAttribute('aria-label', `Target for ${card.name}`);
        choices.forEach(choice => {
            const option = document.createElement('option');
            option.value = choice;
            option.textContent = choice;
            select.appendChild(option);
        });
        select.disabled = Boolean(reason);
        actions.appendChild(select);
    }

    // A card picked on the board is played by the tap, not by this button: it
    // arms the board and says so, and pressing it again puts the card back.
    const boardMode = PROGRESS_MODES[card.needs_target];
    const aiming = boardMode && progressPickCard() === cardId;

    const play = document.createElement('button');
    play.type = 'button';
    play.className = 'progress-play';
    play.dataset.progressCard = cardId;
    play.dataset.progressAction = boardMode ? 'pick' : 'play';
    play.textContent = boardMode ? (aiming ? 'Cancel' : 'Pick on board') : 'Play';
    play.disabled = Boolean(reason);
    play.title = reason;
    actions.appendChild(play);

    row.appendChild(actions);

    const note = reason || (aiming ? progressPickHint() : '');
    if (note) {
        const line = document.createElement('div');
        line.className = 'ck-note';
        line.textContent = note;
        row.appendChild(line);
    }

    return row;
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
    if (isProgressMode(viewState.selectedBuilding)) {
        return progressPickHint();
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

progressHandDiv?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-progress-card]');
    if (!button || button.disabled) {
        return;
    }
    const cardId = button.dataset.progressCard;
    const card = getBoard()?.cities_knights?.progress_cards?.[cardId];
    if (!card) {
        return;
    }
    if (button.dataset.progressAction === 'pick') {
        toggleProgressPick(cardId, card);
        return;
    }
    const select = button.parentElement.querySelector('.progress-target');
    const payload = { name: viewState.identity.name, card: cardId };
    if (select) {
        payload.target = select.value;
    }
    emitGame('play_progress_card', payload);
});

buildKnightBtn?.addEventListener('click', () => toggleCkMode('knight'));
moveKnightBtn?.addEventListener('click', () => toggleCkMode('knight_move'));
buildWallBtn?.addEventListener('click', () => toggleCkMode('city_wall'));
