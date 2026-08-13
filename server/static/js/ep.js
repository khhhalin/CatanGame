// Explorers & Pirates panel: the mission tracks and their lead cards, the token
// supplies, and each player's gold and village advantages, all read from
// `board.ep`. Mirrors cities-knights.js — one render, called on every board
// update, that hides the whole panel on a table not playing the expansion.

import { markDirty } from './board.js';
import { boardCanvas, epBuildCrewBtn, epBuildSettlerBtn, epBuildShipBtn, epBuyGoldBtn, epFoundSettlementBtn, epGold, epGoldPick, epLoadCargoBtn, epMissionBtn, epMissions, epMoveShipBtn, epPanel, epPlayers, epRollFishBtn, epSellGoldBtn, epSupply, epUnloadCargoBtn, gameBoard, moveShipBtn, placeRoadBtn, placeSettlementBtn, upgradeCityBtn } from './dom.js';
import { resourceName, resourceTile } from './icons.js';
import { displayError } from './notices.js';
import { findMyPlayer } from './player-view.js';
import { armShipMode, formatCost, SHIP_COST, turnBlockReason } from './seafarers.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn, resourceOrder, viewState } from './state.js';

const MISSION_LABELS = {
    pirate_lairs: 'Pirate Lairs',
    fish: 'Fish for Catan',
    spices: 'Spices for Catan',
};

const SUPPLY_LABELS = {
    fish_haul: 'Fish hauls',
    spice_sack: 'Spice sacks',
    lair_token: 'Lair tokens',
};

const ADVANTAGE_LABELS = {
    swift_voyage: 'Swift Voyage',
    pirate_bonus: 'Pirate Bonus',
    fast_gold: 'Fast Gold',
};

// Which gold trade the resource pick is currently choosing for, or null.
let goldPickMode = null;

/** A small dot in a player's colour. */
function colorDot(color) {
    const dot = document.createElement('span');
    dot.className = 'ep-dot';
    dot.style.background = color || '#888888';
    return dot;
}

/**
 * Render the Explorers & Pirates panel from the board, and hide it whole on a
 * table without the expansion (no `ep` state). Called on every board update.
 */
export function renderExplorersAndPirates() {
    if (!epPanel) {
        return;
    }
    const board = getBoard();
    const ep = board?.ep;
    epPanel.classList.toggle('hidden', !ep);
    if (!ep) {
        return;
    }

    const colors = {};
    for (const player of board.players || []) {
        colors[player.name] = player.color;
    }
    renderActions(board);
    renderGold(board);
    renderMissions(ep, colors);
    renderSupply(ep);
    renderPlayers(board, ep, colors);
}

/**
 * The action strip: the ship controls (Build/Move arm the board gestures) and
 * the non-spatial actions (Roll for fish). Each button is hidden when its rule
 * is off and disabled with a reason when it cannot be taken; the ship modes
 * light up while armed. Gold sell/buy — which needs a resource pick — is a
 * later addition.
 */
function renderActions(board) {
    const rules = board.rules || {};
    const me = findMyPlayer();

    if (epBuildShipBtn && epMoveShipBtn) {
        const showShips = rules.transport_ships === true;
        epBuildShipBtn.classList.toggle('hidden', !showShips);
        epMoveShipBtn.classList.toggle('hidden', !showShips);
        if (showShips && me) {
            // The transport ship costs the Seafarers ship's wood+sheep; show it
            // on the button the way the Seafarers panel does, so the price is
            // visible before the tap. innerHTML because the cost is resource tiles.
            epBuildShipBtn.innerHTML = `Build ship · ${formatCost(SHIP_COST)}`;
            // The server checks the harbour and the cost; the client only gates
            // on whose turn it is, and errs permissive.
            const blocked = turnBlockReason();
            epBuildShipBtn.disabled = Boolean(blocked);
            epBuildShipBtn.title = blocked || 'Then tap a sea side beside a harbor settlement';
            epBuildShipBtn.classList.toggle('active', viewState.selectedBuilding === 'ship');

            const ships = me.ships || [];
            let moveReason = blocked;
            if (!moveReason && ships.length === 0) {
                moveReason = 'You have no ships to move';
            } else if (!moveReason && board.ship_moved_this_turn === true) {
                moveReason = 'You have already moved a ship this turn';
            }
            epMoveShipBtn.disabled = Boolean(moveReason);
            epMoveShipBtn.title = moveReason || 'Tap your ship, then the sea side to move it to';
            epMoveShipBtn.classList.toggle('active', viewState.selectedBuilding === 'ship_move');
        }
    }

    renderCargoActions(board, me);

    if (epMissionBtn) {
        // The mission gesture needs a transport ship to act with and at least one
        // mission whose destinations it can reach. Its own tap infers which
        // action from the target hex and the ship's hold.
        const showMission = rules.transport_ships === true
            && (rules.mission_fish === true || rules.mission_spices === true
                || rules.mission_pirate_lairs === true);
        epMissionBtn.classList.toggle('hidden', !showMission);
        if (showMission) {
            const blocked = turnBlockReason();
            epMissionBtn.disabled = Boolean(blocked);
            epMissionBtn.title = blocked
                || 'Tap your transport ship, then a shoal, village, lair or Council dock';
            epMissionBtn.classList.toggle('active', viewState.selectedBuilding === 'mission');
        }
    }

    if (epRollFishBtn) {
        const showFish = rules.mission_fish === true;
        epRollFishBtn.classList.toggle('hidden', !showFish);
        if (showFish) {
            const blocked = !isMyTurn() ? 'Not your turn' : turnBlockReason();
            epRollFishBtn.disabled = Boolean(blocked);
            epRollFishBtn.title = blocked || 'Roll a die to try to place a fish haul on a matching shoal';
        }
    }
}

/**
 * The cargo controls: build a crew or settler, shuttle pieces to/from a hold,
 * and found a settlement from a settler ship. Each is hidden when its rule is
 * off and disabled off-turn; the crew and settler buttons show their price the
 * way the ship button does. The load/unload/found gestures ride on the same
 * transport-ship rule the ship controls do.
 *
 * @param {object} board - Board payload
 * @param {object|null} me - Own player entry, or null
 */
function renderCargoActions(board, me) {
    const rules = board.rules || {};
    const costs = board.costs || {};
    const blocked = turnBlockReason();
    const sel = viewState.selectedBuilding;

    const priceButton = (button, ruleOn, mode, cost, hint) => {
        if (!button) {
            return;
        }
        button.classList.toggle('hidden', !ruleOn);
        if (!ruleOn || !me) {
            return;
        }
        const label = button.dataset.label || button.textContent;
        button.dataset.label = label;
        // innerHTML because the cost is resource tiles; the label is trusted.
        button.innerHTML = cost ? `${label} · ${formatCost(cost)}` : label;
        button.disabled = Boolean(blocked);
        button.title = blocked || hint;
        button.classList.toggle('active', sel === mode);
    };

    // Crews and settlers each answer to their own rule; both ride on transport
    // ships (their dependency), so the shuttle and found controls follow the
    // ship rule.
    priceButton(epBuildCrewBtn, rules.crews === true, 'build_crew', costs.crew,
        'Then tap your transport ship at a harbour, or a harbour settlement');
    priceButton(epBuildSettlerBtn, rules.cargo_settlers === true, 'build_settler', costs.settler,
        'Then tap your transport ship at a harbour, or a harbour settlement');

    const showShuttle = rules.transport_ships === true;
    for (const [button, mode, hint] of [
        [epLoadCargoBtn, 'load_cargo', 'Tap your transport ship beside a harbour to load a basin piece'],
        [epUnloadCargoBtn, 'unload_cargo', 'Tap your transport ship beside a harbour to unload a hold piece'],
    ]) {
        if (!button) {
            continue;
        }
        button.classList.toggle('hidden', !showShuttle);
        if (showShuttle && me) {
            button.disabled = Boolean(blocked);
            button.title = blocked || hint;
            button.classList.toggle('active', sel === mode);
        }
    }

    if (epFoundSettlementBtn) {
        const showFound = rules.cargo_settlers === true;
        epFoundSettlementBtn.classList.toggle('hidden', !showFound);
        if (showFound && me) {
            epFoundSettlementBtn.disabled = Boolean(blocked);
            epFoundSettlementBtn.title = blocked
                || 'Tap your settler ship, then the coastal corner to found at';
            epFoundSettlementBtn.classList.toggle('active', sel === 'found_settlement');
        }
    }
}

// ---------------------------------------------------------- mission gestures
//
// A mission action is one gesture: tap a transport ship, then tap the hex it
// should act on. The target's type and the ship's hold say which action it is —
// a shoal with a haul is a catch, a Council dock under a laden ship is a
// delivery, a village or a lair is a crew errand — so the player learns one
// gesture, not five buttons. The server re-checks every rule; the inference
// here only picks which handler to call and errs toward asking (a wrong guess
// is a refusal, and the mode stays armed to try again).

/**
 * Arm the mission gesture, disarming every other board mode the way the ship
 * and knight buttons disarm each other. Called by the strip's Mission button.
 */
export function armMissionMode() {
    const armed = viewState.selectedBuilding === 'mission';
    viewState.selectedBuilding = armed ? null : 'mission';
    viewState.missionShipFrom = null;
    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn, epBuildShipBtn, epMoveShipBtn]
        .forEach(button => button?.classList.remove('active'));
    gameBoard?.classList.toggle('placement-mode', Boolean(viewState.selectedBuilding));
    renderExplorersAndPirates();
}

/**
 * The mission action a ship on `shipEdge` would take against `hexKey`, or null
 * if that target is not one this ship can act on. Reads the same board fields
 * the server does: the mission destination maps in `board.ep` and the ship's
 * own cargo (a Council dock is any hex carrying `meta.docks`).
 *
 * @param {object} board - Board payload
 * @param {string} shipEdge - The edge the transport ship sits on
 * @param {string} hexKey - The hex tapped as the target
 * @returns {{event: string, payload: object}|null}
 */
export function inferMissionAction(board, shipEdge, hexKey) {
    const ep = board.ep || {};
    const cargo = board.edges?.[shipEdge]?.ship?.cargo || [];
    const carries = type => cargo.some(piece => piece.type === type);

    // A Council-of-Catan hex is any hex with docks; a laden ship delivers there.
    if (board.hexes?.[hexKey]?.meta?.docks?.length) {
        if (carries('fish_haul')) {
            return { event: 'deliver_fish', payload: { ship_edge: shipEdge, council_hex: hexKey } };
        }
        if (carries('spice_sack')) {
            return { event: 'deliver_spices', payload: { ship_edge: shipEdge, council_hex: hexKey } };
        }
        return null;
    }
    if (ep.fish_shoals && hexKey in ep.fish_shoals) {
        return { event: 'catch_fish', payload: { ship_edge: shipEdge, shoal_hex: hexKey } };
    }
    if (ep.spice_hexes && hexKey in ep.spice_hexes) {
        return { event: 'befriend_spice_village', payload: { ship_edge: shipEdge, spice_hex: hexKey } };
    }
    if (ep.lairs && hexKey in ep.lairs) {
        // A captured lair is where surviving crews are picked back up; an
        // uncaptured one is where crews are landed to fight for it.
        const event = ep.lairs[hexKey].captured ? 'pickup_crews_from_lair' : 'land_crews_on_lair';
        return { event, payload: { ship_edge: shipEdge, lair_hex: hexKey } };
    }
    return null;
}

/**
 * Handle a board tap while the mission gesture is armed. First tap picks one of
 * this player's transport ships up; the second names the target hex and emits
 * the inferred action. Called from placement.js before the ordinary placement
 * pipeline, and always consumes the tap (returns true).
 *
 * @param {number} clientX - Pointer clientX of the tap
 * @param {number} clientY - Pointer clientY of the tap
 * @returns {boolean} - Always true: a mission-mode tap is never a pan
 */
export function handleMissionTap(clientX, clientY) {
    const board = getBoard();
    const name = viewState.identity.name;
    const position = window.BoardRenderer.clientToBoard(boardCanvas, clientX, clientY);

    if (!viewState.missionShipFrom) {
        const edgeKey = window.BoardRenderer.findNearestEdge(board, position.x, position.y);
        const ship = edgeKey ? board?.edges?.[edgeKey]?.ship : null;
        if (!ship || ship.player !== name || ship.kind !== 'transport') {
            displayError('Tap one of your transport ships to act with.');
            return true;
        }
        viewState.missionShipFrom = edgeKey;
        markDirty();
        return true;
    }

    const hexKey = window.BoardRenderer.findNearestHex(board, position.x, position.y);
    const action = hexKey ? inferMissionAction(board, viewState.missionShipFrom, hexKey) : null;
    if (!action) {
        displayError('Your ship cannot act on that hex — aim at a shoal, village, lair or Council dock it points at.');
        return true;
    }
    emitGame(action.event, { name, ...action.payload });
    viewState.missionShipFrom = null;
    markDirty();
    return true;
}

// ------------------------------------------------------------ cargo gestures
//
// The crew→ship→mission chain, made reachable through the strip. A crew or
// settler is built onto a transport ship's hold (or a harbour settlement's
// basin); pieces are shuttled between the two; and a settler ship founds a free
// settlement at a coastal corner. Each is a board mode armed like the mission
// gesture and handled ahead of the placement pipeline — none draws a ghost, so
// none is a placement kind. The server re-checks every rule; the client only
// picks the target and errs toward asking.

const EP_CARGO_MODES = ['build_crew', 'build_settler', 'load_cargo', 'unload_cargo',
    'found_settlement'];

/** Whether a mode is one of this strip's own board gestures (cargo or mission). */
export function isEpBoardMode(mode) {
    return mode === 'mission' || EP_CARGO_MODES.includes(mode);
}

/**
 * Arm one of the strip's cargo board modes, disarming every other board mode
 * the way the mission and ship buttons do.
 *
 * @param {string} mode - One of EP_CARGO_MODES
 */
export function armEpCargoMode(mode) {
    const armed = viewState.selectedBuilding === mode;
    viewState.selectedBuilding = armed ? null : mode;
    viewState.missionShipFrom = null;
    viewState.foundShipFrom = null;
    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn, epBuildShipBtn, epMoveShipBtn]
        .forEach(button => button?.classList.remove('active'));
    gameBoard?.classList.toggle('placement-mode', Boolean(viewState.selectedBuilding));
    renderExplorersAndPirates();
}

/**
 * Dispatch a board tap while one of the strip's board gestures is armed.
 * Returns true (the tap is always consumed) or false when no EP mode is armed.
 *
 * @param {number} clientX - Pointer clientX of the tap
 * @param {number} clientY - Pointer clientY of the tap
 * @returns {boolean}
 */
export function handleEpBoardTap(clientX, clientY) {
    const mode = viewState.selectedBuilding;
    if (mode === 'mission') {
        return handleMissionTap(clientX, clientY);
    }
    if (mode === 'build_crew' || mode === 'build_settler') {
        return handleBuildCargoTap(clientX, clientY, mode);
    }
    if (mode === 'load_cargo' || mode === 'unload_cargo') {
        return handleShuttleTap(clientX, clientY, mode);
    }
    if (mode === 'found_settlement') {
        return handleFoundSettlementTap(clientX, clientY);
    }
    return false;
}

/** My own harbour settlement at one end of this edge, or null. */
function adjacentHarbor(board, edgeKey, name) {
    const ends = board.edges?.[edgeKey]?.neighbors?.vertices || [];
    for (const vertexKey of ends) {
        const building = board.vertices?.[vertexKey]?.building;
        if (building?.type === 'harbor_settlement' && building.player === name) {
            return vertexKey;
        }
    }
    return null;
}

/**
 * Build a crew or settler: onto the tapped transport ship's hold, or — when the
 * tap lands on one of my harbour settlements and not a ship — into its basin.
 * The ship path is checked first because it is the mission-critical one; a
 * player aiming a piece into a basin taps the settlement itself.
 */
function handleBuildCargoTap(clientX, clientY, mode) {
    const board = getBoard();
    const name = viewState.identity.name;
    const position = window.BoardRenderer.clientToBoard(boardCanvas, clientX, clientY);
    const event = mode === 'build_crew' ? 'build_crew' : 'build_settler';
    const noun = mode === 'build_crew' ? 'crew' : 'settler';

    const edgeKey = window.BoardRenderer.findNearestEdge(board, position.x, position.y);
    const ship = edgeKey ? board?.edges?.[edgeKey]?.ship : null;
    if (ship && ship.player === name && ship.kind === 'transport'
        && adjacentHarbor(board, edgeKey, name)) {
        emitGame(event, { name, into: 'hold', key: edgeKey });
        return true;
    }

    const vertexKey = window.BoardRenderer.findNearestVertex(board, position.x, position.y);
    const building = vertexKey ? board?.vertices?.[vertexKey]?.building : null;
    if (building?.type === 'harbor_settlement' && building.player === name) {
        emitGame(event, { name, into: 'basin', key: vertexKey });
        return true;
    }

    displayError(`Build a ${noun} onto your transport ship at a harbour, or into a harbour settlement.`);
    return true;
}

/**
 * Shuttle a piece between a harbour basin and an adjacent ship's hold: load
 * moves the first basin piece aboard, unload returns the last hold piece to the
 * basin. Tap the ship; its adjacent harbour is where the piece comes from or
 * goes to.
 */
function handleShuttleTap(clientX, clientY, mode) {
    const board = getBoard();
    const name = viewState.identity.name;
    const position = window.BoardRenderer.clientToBoard(boardCanvas, clientX, clientY);
    const edgeKey = window.BoardRenderer.findNearestEdge(board, position.x, position.y);
    const ship = edgeKey ? board?.edges?.[edgeKey]?.ship : null;
    if (!ship || ship.player !== name || ship.kind !== 'transport') {
        displayError('Tap one of your transport ships beside a harbour settlement.');
        return true;
    }
    const harborKey = adjacentHarbor(board, edgeKey, name);
    if (!harborKey) {
        displayError('That ship is not beside one of your harbour settlements.');
        return true;
    }

    if (mode === 'load_cargo') {
        const basin = board.vertices[harborKey].building.basin || [];
        if (basin.length === 0) {
            displayError('That harbour settlement has no cargo in its basin to load.');
            return true;
        }
        emitGame('load_transport_ship', { name, edge: edgeKey, basin_index: 0 });
    } else {
        const cargo = ship.cargo || [];
        if (cargo.length === 0) {
            displayError('That ship has nothing in its hold to unload.');
            return true;
        }
        emitGame('unload_transport_ship', { name, edge: edgeKey, cargo_index: cargo.length - 1 });
    }
    return true;
}

/**
 * Found a settlement from a settler ship: two taps. The first picks up one of my
 * transport ships carrying a settler; the second names the coastal corner it
 * founds at. The server checks the ship points at the corner and the distance
 * rule; the client only carries the ship between the taps.
 */
function handleFoundSettlementTap(clientX, clientY) {
    const board = getBoard();
    const name = viewState.identity.name;
    const position = window.BoardRenderer.clientToBoard(boardCanvas, clientX, clientY);

    if (!viewState.foundShipFrom) {
        const edgeKey = window.BoardRenderer.findNearestEdge(board, position.x, position.y);
        const ship = edgeKey ? board?.edges?.[edgeKey]?.ship : null;
        const carriesSettler = (ship?.cargo || []).some(piece => piece.type === 'settler');
        if (!ship || ship.player !== name || ship.kind !== 'transport' || !carriesSettler) {
            displayError('Tap one of your transport ships carrying a settler.');
            return true;
        }
        viewState.foundShipFrom = edgeKey;
        markDirty();
        return true;
    }

    const vertexKey = window.BoardRenderer.findNearestVertex(board, position.x, position.y);
    if (!vertexKey) {
        displayError('Tap the coastal corner to found the settlement at.');
        return true;
    }
    emitGame('found_settlement_from_ship',
             { name, edge: viewState.foundShipFrom, vertex: vertexKey });
    viewState.foundShipFrom = null;
    markDirty();
    return true;
}

/**
 * The gold trades: two buttons that each reveal a resource pick, hidden whole on
 * a table not playing gold and disabled off-turn. The pick row is rebuilt every
 * render so a mid-trade board update does not leave stale buttons behind.
 */
function renderGold(board) {
    if (!epGold) {
        return;
    }
    const show = board.rules?.gold === true;
    epGold.classList.toggle('hidden', !show);
    if (!show) {
        goldPickMode = null;
        return;
    }
    const blocked = turnBlockReason();
    for (const button of [epSellGoldBtn, epBuyGoldBtn]) {
        if (button) {
            button.disabled = Boolean(blocked);
            button.title = blocked || '';
        }
    }
    if (epSellGoldBtn) {
        epSellGoldBtn.classList.toggle('active', goldPickMode === 'sell');
    }
    if (epBuyGoldBtn) {
        epBuyGoldBtn.classList.toggle('active', goldPickMode === 'buy');
    }
    renderGoldPick();
}

/** The five resource tiles, or nothing when no trade is being chosen for. */
function renderGoldPick() {
    if (!epGoldPick) {
        return;
    }
    epGoldPick.classList.toggle('hidden', goldPickMode === null);
    if (goldPickMode === null) {
        epGoldPick.replaceChildren();
        return;
    }
    const event = goldPickMode === 'sell' ? 'sell_resources_for_gold' : 'buy_resource_with_gold';
    const frag = document.createDocumentFragment();
    for (const resource of resourceOrder()) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'ep-gold-res';
        button.dataset.resource = resource;
        button.dataset.event = event;
        // resourceTile is trusted markup from icons.js, not user input.
        button.innerHTML = resourceTile(resource, { label: resourceName(resource) });
        frag.appendChild(button);
    }
    epGoldPick.replaceChildren(frag);
}

function toggleGoldMode(mode) {
    goldPickMode = goldPickMode === mode ? null : mode;
    renderExplorersAndPirates();
}

function renderMissions(ep, colors) {
    const frag = document.createDocumentFragment();
    for (const mission of ep.missions || []) {
        const row = document.createElement('div');
        row.className = 'ep-mission';

        const name = document.createElement('span');
        name.className = 'ep-mission-name';
        name.textContent = MISSION_LABELS[mission] || mission;
        row.appendChild(name);

        const markers = document.createElement('div');
        markers.className = 'ep-markers';
        const leader = ep.lead_cards?.[mission] || null;
        const length = ep.track_lengths?.[mission] || 0;
        for (const [player, tracks] of Object.entries(ep.markers || {})) {
            const at = tracks[mission] || 0;
            // Names are built with textContent, never interpolated: a player
            // named with markup would otherwise render as HTML in the panel.
            const chip = document.createElement('span');
            chip.className = 'ep-marker';
            chip.appendChild(colorDot(colors[player]));
            const value = document.createElement('span');
            value.textContent = length ? `${at}/${length}` : String(at);
            chip.appendChild(value);
            if (player === leader) {
                const star = document.createElement('span');
                star.className = 'ep-lead';
                star.textContent = '★';
                star.title = 'Holds the mission lead card (1 VP)';
                chip.appendChild(star);
            }
            markers.appendChild(chip);
        }
        row.appendChild(markers);
        frag.appendChild(row);
    }
    epMissions.replaceChildren(frag);
}

function renderSupply(ep) {
    const frag = document.createDocumentFragment();
    for (const [token, label] of Object.entries(SUPPLY_LABELS)) {
        const count = ep.token_supply?.[token];
        if (count === undefined) {
            continue;
        }
        const item = document.createElement('span');
        item.className = 'ep-supply-item';
        const value = document.createElement('strong');
        value.textContent = String(count);
        item.appendChild(value);
        item.appendChild(document.createTextNode(` ${label}`));
        frag.appendChild(item);
    }
    epSupply.replaceChildren(frag);
}

function renderPlayers(board, ep, colors) {
    const frag = document.createDocumentFragment();
    for (const player of board.players || []) {
        const advantages = ep.village_advantages?.[player.name] || [];
        const gold = player.gold || 0;
        // A player with nothing to say — no gold, no advantage — is left out so
        // the panel stays quiet until the expansion's economy is in play.
        if (gold === 0 && advantages.length === 0) {
            continue;
        }
        const row = document.createElement('div');
        row.className = 'ep-player';
        row.appendChild(colorDot(colors[player.name]));

        const name = document.createElement('span');
        name.className = 'ep-player-name';
        name.textContent = player.name;
        row.appendChild(name);

        const parts = [];
        if (gold) {
            parts.push(`${gold} gold`);
        }
        for (const advantage of advantages) {
            parts.push(ADVANTAGE_LABELS[advantage] || advantage);
        }
        const detail = document.createElement('span');
        detail.className = 'ep-player-detail';
        detail.textContent = parts.join(' · ');
        row.appendChild(detail);

        frag.appendChild(row);
    }
    epPlayers.replaceChildren(frag);
}

// The button listeners, registered once; the render above only sets each
// button's state. Build/Move arm the shared ship board modes (the board tap
// then does the work); Roll for fish is a direct action.
epBuildShipBtn?.addEventListener('click', () => armShipMode('ship'));
epMoveShipBtn?.addEventListener('click', () => armShipMode('ship_move'));
epBuildCrewBtn?.addEventListener('click', () => armEpCargoMode('build_crew'));
epBuildSettlerBtn?.addEventListener('click', () => armEpCargoMode('build_settler'));
epLoadCargoBtn?.addEventListener('click', () => armEpCargoMode('load_cargo'));
epUnloadCargoBtn?.addEventListener('click', () => armEpCargoMode('unload_cargo'));
epFoundSettlementBtn?.addEventListener('click', () => armEpCargoMode('found_settlement'));
epMissionBtn?.addEventListener('click', () => armMissionMode());
epRollFishBtn?.addEventListener('click', () => {
    emitGame('roll_fish_haul', { name: viewState.identity.name });
});

epSellGoldBtn?.addEventListener('click', () => toggleGoldMode('sell'));
epBuyGoldBtn?.addEventListener('click', () => toggleGoldMode('buy'));
// One listener for the whole pick row; the tile clicked names the resource and
// the trade it belongs to, so the row can be rebuilt without rewiring.
epGoldPick?.addEventListener('click', event => {
    const button = event.target.closest('.ep-gold-res');
    if (!button) {
        return;
    }
    emitGame(button.dataset.event, {
        name: viewState.identity.name,
        resource: button.dataset.resource,
    });
    goldPickMode = null;
    renderExplorersAndPirates();
});
