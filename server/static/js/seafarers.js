// Seafarers: ships, moving them, the pirate and the islands they reach.
//
// Everything here renders from the board payload and shows nothing at all
// unless `board.rules.ships` is on, so a base game looks exactly as it did
// before the expansion existed.
//
// Two things are deliberately *not* in this file:
//
//   - Where a ship may lie. `edges[key].sea` is the server's own answer, sent
//     on every edge of every game, and placement.js reads it. A second copy of
//     that geometry in JavaScript is a rule waiting to disagree with the one
//     the server enforces.
//   - The pirate as a mode. Nothing arms it: with the rule on, a 7 lets the
//     roller move either piece, and the hex they aim at is what decides which.
//     placement.js resolves that at the moment of the tap.
//
// The cost below is duplicated from server/data/costs.json for the same reason
// the Cities & Knights costs are - to grey a button out and say why before the
// round trip. The server checks it again and the board is drawn from its
// answer, never from this.

import { resourceTile, statusIcon } from './icons.js';
import { buildShipBtn, gameBoard, islandPoints, moveShipBtn, placeRoadBtn, placeSettlementBtn, robberText, seafarersChipValue, seafarersPanel, shipHint, upgradeCityBtn } from './dom.js';
import { displayError } from './notices.js';
import { findMyPlayer } from './player-view.js';
import { emitGame } from './socket.js';
import { getBoard, getGamePhase, isMyTurn, mustMoveRobber, viewState } from './state.js';

const SHIP_COST = { wood: 1, sheep: 1 };

// The board modes this section adds to the settlement/road/city set.
const SEA_MODES = ['ship', 'ship_move'];

/**
 * Whether one Seafarers rule is in play in the running game.
 *
 * Asked rule by rule rather than "is Seafarers on", the same way the Cities &
 * Knights panels do: a table may take ships without the pirate, or ships
 * without ship movement, and every control below answers to its own rule.
 *
 * @param {string} ruleId - One of the expansion's rule ids
 * @returns {boolean}
 */
export function seaRule(ruleId) {
    return getBoard()?.rules?.[ruleId] === true;
}

/**
 * Whether the running game has a sea to sail at all. Ships are the foundation:
 * without them the board has no sea edges and nothing else here means anything.
 */
export function seaEnabled() {
    // Explorers & Pirates transport ships build and move on the sea exactly as
    // Seafarers ships do, so they share this whole interaction — the two rules
    // are mutually exclusive (`sea_ship_model`), so only ever one is on.
    return seaRule('ships') || seaRule('transport_ships');
}

/**
 * Whether a selection mode belongs to this expansion.
 *
 * @param {string} mode - A `viewState.selectedBuilding` value
 * @returns {boolean}
 */
export function isSeaMode(mode) {
    return SEA_MODES.includes(mode);
}

/**
 * Render a cost as its resource tiles, e.g. one wood tile then one sheep tile.
 *
 * @param {object} cost - {resource: amount}
 * @returns {string} HTML (resource tiles), so the caller must use innerHTML.
 */
function formatCost(cost) {
    return Object.entries(cost)
        .map(([resource, amount]) => `${amount}${resourceTile(resource, { label: resource })}`)
        .join(' ');
}

/**
 * Name the first resource the player is short of, or ''.
 *
 * @param {object} held - {resource: amount} the player holds
 * @param {object} cost - {resource: amount} required
 * @returns {string}
 */
function shortfall(held, cost) {
    for (const [resource, amount] of Object.entries(cost)) {
        const have = held?.[resource] || 0;
        if (have < amount) {
            return `Need ${amount} ${resource}, you have ${have}`;
        }
    }
    return '';
}

// ------------------------------------------------------------ the board taps

/**
 * First tap of a ship move: pick a ship up.
 *
 * Refused rather than recorded when it is not a ship this player may move. The
 * knight equivalent records whatever was tapped, which is survivable because a
 * knight is visible in a list; a ship move whose origin is an empty stretch of
 * water simply does nothing on the second tap and looks broken.
 *
 * @param {string} edgeKey - The hex side tapped
 */
export function selectShipToMove(edgeKey) {
    const board = getBoard();
    const ship = board?.edges?.[edgeKey]?.ship;
    if (ship?.player !== viewState.identity.name) {
        displayError('Tap one of your own ships to move it.');
        return;
    }
    if (ship.built_turn === board.turn_count) {
        displayError('A ship cannot be moved on the turn it was built.');
        return;
    }
    viewState.shipMoveFrom = edgeKey;
    renderSeafarers();
}

/**
 * The confirmed tap: build a ship here, or finish a move onto here.
 *
 * @param {string} edgeKey - The hex side confirmed
 */
export function handleShipEdgeTap(edgeKey) {
    if (!seaEnabled()) {
        viewState.selectedBuilding = null;
        return;
    }

    const name = viewState.identity.name;
    // The one difference between the two ship models: which action the tap
    // sends. Everything else — the modes, the two-tap move, the ghosts — is one.
    const transport = seaRule('transport_ships');

    if (viewState.selectedBuilding === 'ship_move') {
        const origin = viewState.shipMoveFrom;
        if (!origin) {
            selectShipToMove(edgeKey);
            return;
        }
        viewState.shipMoveFrom = null;
        emitGame(transport ? 'move_transport_ship' : 'move_ship',
                 { name, from_edge: origin, to_edge: edgeKey });
        expectShipPlacement('ship_move', () => !myShipAt(origin));
        renderSeafarers();
        return;
    }

    const before = myShips().length;
    emitGame(transport ? 'build_transport_ship' : 'build_ship', { name, edge: edgeKey });
    expectShipPlacement('ship', () => myShips().length > before);
}

// ------------------------------------------------------- disarming a mode
//
// The same rule the Cities & Knights modes follow, and for the same reason: a
// ship move takes two taps and someone else's trade landing between them must
// not disarm the board halfway through. So the mode survives every payload
// except the one that shows the placement it was armed for has landed.

let pendingSeaPlacement = null;

/**
 * Remember what the tap just sent was meant to achieve.
 *
 * @param {string} mode - The armed mode, so a re-arm mid-flight is not undone
 * @param {Function} settled - Reads the current board; true once it has landed
 */
function expectShipPlacement(mode, settled) {
    pendingSeaPlacement = { mode, settled };
}

/**
 * Drop the armed mode once the server's board shows the placement happened.
 * A refusal never gets here: the server rejects without broadcasting a board,
 * so the mode stays armed and the player can simply aim again.
 */
function clearSettledPlacement() {
    if (!pendingSeaPlacement) {
        return;
    }
    if (viewState.selectedBuilding !== pendingSeaPlacement.mode) {
        pendingSeaPlacement = null;
        return;
    }
    if (!pendingSeaPlacement.settled()) {
        return;
    }
    pendingSeaPlacement = null;
    viewState.selectedBuilding = null;
    viewState.shipMoveFrom = null;
    gameBoard.classList.remove('placement-mode');
}

/**
 * The edge keys this player has ships on, as the server lists them.
 *
 * @returns {string[]}
 */
function myShips() {
    return findMyPlayer()?.ships || [];
}

function myShipAt(edgeKey) {
    return getBoard()?.edges?.[edgeKey]?.ship?.player === viewState.identity.name;
}

// ------------------------------------------------------------- the controls

/**
 * Arm or disarm one of this expansion's board modes.
 * Same single-mode rule as every other placement button: arming one of these
 * disarms the rest.
 *
 * @param {string} mode - One of SEA_MODES
 */
/**
 * Arm one of the ship board modes from outside this module — the E&P strip's
 * Build/Move ship buttons use it, since transport ships share these modes.
 *
 * @param {string} mode - 'ship' or 'ship_move'
 */
export function armShipMode(mode) {
    toggleSeaMode(mode);
}

function toggleSeaMode(mode) {
    if (!seaEnabled()) {
        return;
    }
    viewState.selectedBuilding = viewState.selectedBuilding === mode ? null : mode;
    viewState.shipMoveFrom = null;

    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn].forEach(button => {
        button?.classList.remove('active');
    });
    gameBoard.classList.toggle('placement-mode', Boolean(viewState.selectedBuilding));

    renderSeafarers();
}

/**
 * Show which of this expansion's board modes is armed, if any.
 * Called from the other placement buttons too, so exactly one mode ever looks
 * selected.
 */
export function syncSeaModeButtons() {
    if (!buildShipBtn || !moveShipBtn) {
        return;
    }
    buildShipBtn.classList.toggle('active', viewState.selectedBuilding === 'ship');
    moveShipBtn.classList.toggle('active', viewState.selectedBuilding === 'ship_move');

    if (viewState.selectedBuilding !== 'ship_move') {
        viewState.shipMoveFrom = null;
    }
}

/**
 * Why no Seafarers action can be taken at all right now, if so.
 *
 * @returns {string} - Empty when the player may act
 */
export function turnBlockReason() {
    if (!isMyTurn()) {
        return 'Not your turn';
    }
    if (mustMoveRobber()) {
        return 'You must move the robber first';
    }
    return '';
}

/**
 * Render the Seafarers panel, or hide it.
 * This is the only entry point: it is safe to call with no board, in a base
 * game, or as an observer.
 */
export function renderSeafarers() {
    const enabled = seaEnabled();
    const player = enabled ? findMyPlayer() : null;

    // The panel itself is Seafarers' own — its label, island points and ship
    // buttons. A transport table shares the ship *interaction* (seaEnabled) but
    // draws its ship controls in the E&P strip instead (ep.js), so the panel
    // stays hidden there.
    const seafarersOwn = seaRule('ships');
    seafarersPanel?.classList.toggle('hidden', !seafarersOwn || !player);

    // The hint under the robber belongs to the pirate rule, not to the panel:
    // it is read by the one player who has just rolled a 7, whether or not
    // they ever open a fold.
    if (robberText) {
        robberText.textContent = seaRule('pirate')
            ? 'Move the robber: tap a land hex, or a sea hex to sail the pirate there.'
            : 'Move the robber: tap a hex on the board.';
    }

    if (!enabled) {
        viewState.shipMoveFrom = null;
        pendingSeaPlacement = null;
        return;
    }

    // Before anything renders: it decides whether a mode is still armed, and
    // every button below is drawn from that.
    clearSettledPlacement();

    if (player && seafarersOwn) {
        renderShipActions(player);
        renderIslandPoints();
    }
    syncSeaModeButtons();
}

/**
 * The two board actions, greyed with their reason, and what to tap next.
 *
 * @param {object} player - Own player entry from the board payload
 */
function renderShipActions(player) {
    if (!buildShipBtn || !moveShipBtn) {
        return;
    }

    const board = getBoard();
    const ships = player.ships || [];
    const maxShips = board.rules?.max_ships ?? 15;
    const inSetup = getGamePhase() === 'setup';
    const freeRoad = (board.free_roads_remaining || 0) > 0;

    // Build. Setup is the one phase where a ship is free and the server dictates
    // when it may go down, so the cost check stands down there exactly as it
    // does for the starting road.
    let buildReason = '';
    if (inSetup) {
        if (!isMyTurn()) {
            buildReason = 'Not your turn';
        } else if ((board.setup_action || 'settlement') !== 'road') {
            buildReason = 'Place your settlement first';
        }
    } else {
        buildReason = turnBlockReason();
    }
    if (!buildReason && ships.length >= maxShips) {
        buildReason = `You have used all ${maxShips} ships`;
    }
    if (!buildReason && !inSetup && !freeRoad) {
        buildReason = shortfall(player.resources, SHIP_COST);
    }

    buildShipBtn.innerHTML = `Build ship · ${formatCost(SHIP_COST)}`;
    buildShipBtn.disabled = Boolean(buildReason);
    buildShipBtn.title = buildReason
        || (inSetup ? 'A ship may replace your starting road: tap a sea side of your settlement'
                    : 'Then tap a sea side on the board');

    // Move. `ship_moved_this_turn` is the rulebook's one-per-turn limit, and it
    // is stated here rather than left to a refusal after the tap.
    // Transport ships move as part of their own rule; a Seafarers table needs
    // `ship_movement` on top of plain ships.
    let moveReason = (seaRule('ship_movement') || seaRule('transport_ships'))
        ? turnBlockReason()
        : 'Moving ships is not one of this table\'s rules';
    if (!moveReason && inSetup) {
        moveReason = 'Not during setup';
    }
    if (!moveReason && board.ship_moved_this_turn === true) {
        moveReason = 'You have already moved a ship this turn';
    }
    if (!moveReason && ships.length === 0) {
        moveReason = 'You have no ships on the board';
    }

    moveShipBtn.textContent = 'Move ship';
    moveShipBtn.disabled = Boolean(moveReason);
    moveShipBtn.title = moveReason || 'Tap the ship, then the sea side to move it to';

    if (shipHint) {
        shipHint.textContent = modeHint();
        shipHint.classList.toggle('hidden', !isSeaMode(viewState.selectedBuilding));
    }

    // How many ships are out, how many are left in the box, and whether this
    // turn's one move has been spent - the whole panel in one line.
    if (seafarersChipValue) {
        const moved = board.ship_moved_this_turn === true;
        const movement = seaRule('ship_movement')
            ? ` · ${moved ? 'move spent' : 'move ready'}`
            : '';
        seafarersChipValue.innerHTML =
            `${statusIcon('ship', { label: 'Ships' })} ${ships.length}/${maxShips}${movement}`;
    }
}

/**
 * The special points each player has scored for reaching a new island.
 *
 * They are already inside `victory_points`, so this is not the score - it is
 * the breakdown, which is the only place a player can see that somebody just
 * took two points for landing somewhere.
 */
function renderIslandPoints() {
    if (!islandPoints) {
        return;
    }
    if (!seaRule('island_victory_points')) {
        islandPoints.textContent = '';
        islandPoints.classList.add('hidden');
        return;
    }

    const scored = getBoard().island_points || {};
    const perIsland = getBoard().rules?.island_points_per_island ?? 2;
    const names = (getBoard().players || [])
        .filter(player => (scored[player.name] || 0) > 0)
        .map(player => `${player.name} ${scored[player.name]}`);

    const summary = names.length > 0
        ? `New islands: ${names.join(' · ')}`
        : `${perIsland} points for your first settlement on a new island`;
    // Built, not interpolated: player names reach `summary`, so the island
    // glyph goes in its own span and the names stay in a text node.
    islandPoints.textContent = '';
    const marker = document.createElement('span');
    marker.innerHTML = statusIcon('island');
    islandPoints.append(marker, ` ${summary}`);
    islandPoints.classList.remove('hidden');
}

/**
 * What the player is expected to tap next, for the armed mode.
 *
 * @returns {string}
 */
function modeHint() {
    if (viewState.selectedBuilding === 'ship') {
        return 'Tap a sea side leaving one of your ships or coastal settlements.';
    }
    if (viewState.selectedBuilding === 'ship_move') {
        return viewState.shipMoveFrom
            ? 'Now tap the sea side to move it to.'
            : 'Tap the ship you want to move.';
    }
    return '';
}

buildShipBtn?.addEventListener('click', () => toggleSeaMode('ship'));
moveShipBtn?.addEventListener('click', () => toggleSeaMode('ship_move'));
