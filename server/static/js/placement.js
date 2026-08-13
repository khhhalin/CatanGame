// Hover, then confirm: the two steps between "I am pointing at that spot" and
// "put a piece there".
//
// Every placement in the game - settlement, road, city, knight, knight move,
// city wall and the robber - goes through here. A click no longer sends
// anything; it pins a ghost and offers a ✓ and an ✗ over the board. Only ✓
// emits, and it emits exactly what the click used to.
//
// The one escape hatch is YOLO mode: a personal, per-browser preference that
// puts the click back in charge. It is deliberately not a house rule - it
// changes nothing anyone else can see, so it never goes near the server or the
// rules registry, and it lives in localStorage where the rest of the table
// cannot reach it.

import { markDirty } from './board.js';
import { moveBarbarianKnight, selectBarbarianKnightToMove } from './barbarian_attack.js';
import { ckEnabled, handleCkVertexTap, handleProgressTargetTap, isProgressMode, progressCardName, progressPickCompletes } from './cities-knights.js';
import { handleEpBoardTap, isEpBoardMode } from './ep.js';
import { boardCanvas, gameBoard, placementAnnounce, placementConfirm, placementConfirmNo, placementConfirmYes, yoloToggle } from './dom.js';
import { displayError } from './notices.js';
import { emitGame } from './socket.js';
import { handleShipEdgeTap, selectShipToMove } from './seafarers.js';
import { getBoard, getGamePhase, isMyTurn, mustMoveRobber, viewState } from './state.js';

// Personal preference, so a name that cannot collide with a table setting.
const YOLO_STORAGE_KEY = 'catan.yoloMode';

// Confirming must never move the board, so the control is an overlay pinned
// over the canvas. These keep it clear of the target it describes and inside
// the board box, which clips.
const CONFIRM_OFFSET_Y = 34;
const CONFIRM_MARGIN = 6;

// What the ✓/✗ is asking about, said out loud. The board itself is one canvas
// with a single label, so a pin on it is invisible to assistive tech and the
// kind of piece is the only part of the target worth naming - "vertex V12"
// tells a player nothing they can act on.
const PLACEMENT_NOUNS = {
    settlement: 'Settlement',
    road: 'Road',
    city: 'City',
    robber: 'Robber',
    city_wall: 'City wall',
    knight: 'Knight',
    knight_move: 'Knight move',
    ship: 'Ship',
    ship_move: 'Ship move',
    barbarian_knight_move: 'Knight move',
    pirate: 'Pirate',
    bridge: 'Bridge',
};

// Which part of the board each kind snaps to. The renderer keeps the same two
// lists for drawing; both are short and both would be wrong in the same way if
// a kind were added to one and not the other.
const EDGE_KINDS = ['road', 'ship', 'ship_move', 'progress_road', 'bridge',
    'barbarian_knight', 'barbarian_knight_move'];
const HEX_KINDS = ['robber', 'pirate', 'progress_hex', 'progress_tokens'];

// What the announcement last said, so aiming at the same spot twice does not
// repeat itself into the live region.
let lastAnnounced = '';

// Where focus was before the confirmation took it, so dismissing gives it back
// rather than dropping it on the body - which would send the next Tab to the
// top of the page.
let focusBeforeConfirm = null;

let yoloMode = readYoloPreference();

/**
 * Read the stored preference. Off unless it says otherwise: confirming is the
 * default, and a browser with storage denied gets the safe half of that.
 *
 * @returns {boolean}
 */
function readYoloPreference() {
    try {
        return window.localStorage.getItem(YOLO_STORAGE_KEY) === '1';
    } catch {
        return false;
    }
}

/**
 * Remember the preference for this browser.
 *
 * @param {boolean} enabled - Whether clicks should place immediately
 */
function writeYoloPreference(enabled) {
    try {
        window.localStorage.setItem(YOLO_STORAGE_KEY, enabled ? '1' : '0');
    } catch {
        // Private mode or storage disabled: the setting still applies to this
        // page, it just will not outlive it.
    }
}

/**
 * What a click on the board would be an attempt to place right now, or null.
 *
 * The robber is the odd one out: there is no button to arm it, the server
 * simply says a 7 is outstanding, so the mode is that flag.
 *
 * @returns {string|null} - Placement kind
 */
function currentPlacementKind() {
    if (!getBoard() || !isMyTurn()) {
        return null;
    }
    if (mustMoveRobber()) {
        return 'robber';
    }
    if (!viewState.selectedBuilding) {
        return null;
    }
    // The Explorers & Pirates board gestures (mission and cargo) draw no ghost
    // and offer no ✓ — each is handled ahead of this pipeline, inferring its
    // action from the target, so none is a placement kind here.
    if (isEpBoardMode(viewState.selectedBuilding)) {
        return null;
    }
    // Setup only accepts the piece the server is asking for next - except that
    // "a player who places a starting settlement on the coast may place a ship
    // instead of a road next to that settlement", so where the server asks for
    // a road a ship answers just as well.
    if (getGamePhase() === 'setup') {
        const wanted = getBoard().setup_action || 'settlement';
        const answers = viewState.selectedBuilding === wanted
            || (viewState.selectedBuilding === 'ship' && wanted === 'road');
        if (!answers) {
            return null;
        }
    }
    return viewState.selectedBuilding;
}

/**
 * Which armed mode a pinned target belongs to.
 *
 * The pirate is the one placement nothing arms: with the rule on, a 7 lets the
 * roller move either piece and the hex they aim at decides which. So a pending
 * pirate belongs to the robber mode, and without this the ✓ retires itself the
 * frame after it appears.
 *
 * @param {string} kind - Placement kind of a pinned or hovered target
 * @returns {string} - The mode that produced it
 */
function armedKindOf(kind) {
    return kind === 'pirate' ? 'robber' : kind;
}

/**
 * What the tap at this key is actually a move of.
 *
 * @param {string} kind - The armed mode
 * @param {string} key - Board key the pointer snapped to
 * @returns {string} - Placement kind
 */
function resolveKind(kind, key) {
    // A 7 lets the roller aim the pirate at a sea hex instead of the robber, in
    // two separate rules: Seafarers' `pirate`, and Explorers & Pirates'
    // `pirate_ship_instead_of_robber` (which replaces the robber outright). They
    // are mutually exclusive, so either one turns a sea-hex robber tap into a
    // pirate; `commit` picks the matching handler.
    const rules = getBoard()?.rules || {};
    const pirateOnSeven = rules.pirate === true || rules.pirate_ship_instead_of_robber === true;
    if (kind === 'robber' && pirateOnSeven && getBoard().hexes[key]?.type === 'ocean') {
        return 'pirate';
    }
    return kind;
}

/**
 * The board key a pointer at this client position would snap to, or null.
 *
 * @param {string} kind - Placement kind
 * @param {number} clientX - Pointer clientX
 * @param {number} clientY - Pointer clientY
 * @returns {string|null} - Board key
 */
function snapToTarget(kind, clientX, clientY) {
    const board = getBoard();
    const position = window.BoardRenderer.clientToBoard(boardCanvas, clientX, clientY);
    if (HEX_KINDS.includes(kind)) {
        return window.BoardRenderer.findNearestHex(board, position.x, position.y);
    }
    if (EDGE_KINDS.includes(kind)) {
        return window.BoardRenderer.findNearestEdge(board, position.x, position.y);
    }
    return window.BoardRenderer.findNearestVertex(board, position.x, position.y);
}

// --------------------------------------------------------------- legality
//
// A client-side copy of the rules, and only ever a copy: the server checks all
// of it again and its answer is what the board is drawn from. It exists so a
// player can see "not allowed" before the round trip, so it errs towards
// permissive - a ghost that says "blocked" where the server would have agreed
// is a lie the player cannot argue with.

/**
 * Every knight on the board, whoever owns it, keyed by vertex.
 *
 * @returns {object} - {vertexKey: {owner, knight}}
 */
function knightsByVertex() {
    const knights = {};
    const owners = getBoard()?.cities_knights?.knights || {};
    for (const [owner, list] of Object.entries(owners)) {
        for (const knight of list || []) {
            knights[knight.vertex] = { owner, knight };
        }
    }
    return knights;
}

/**
 * Whether this vertex has a building on one of its neighbours - Catan's
 * distance rule, which applies whoever owns the neighbour.
 */
function respectsDistanceRule(board, vertexKey) {
    const vertex = board.vertices[vertexKey];
    return !(vertex.neighbors.vertices || [])
        .some(neighbour => board.vertices[neighbour]?.building);
}

function touchesOwnRoad(board, vertexKey, me) {
    return (board.vertices[vertexKey].neighbors.edges || [])
        .some(edgeKey => board.edges[edgeKey]?.road?.player === me);
}

/**
 * Whether a road here would touch the player's own network - their roads and
 * their buildings both, as the engine has it.
 */
function roadConnects(board, edgeKey, me) {
    const ends = board.edges[edgeKey].neighbors.vertices || [];
    return ends.some(vertexKey => {
        const vertex = board.vertices[vertexKey];
        if (!vertex) {
            return false;
        }
        if (vertex.building?.player === me) {
            return true;
        }
        return (vertex.neighbors.edges || []).some(
            other => other !== edgeKey && board.edges[other]?.road?.player === me
        );
    });
}

/**
 * Whether a ship could go here, as far as the client can tell.
 *
 * `edge.sea` is the server's own answer to "may a ship ever lie on this side",
 * sent on every edge in every game. It is read rather than re-derived on
 * purpose: working the geometry out again in JavaScript would be a second
 * implementation of a rule, and the two would drift.
 *
 * @param {object} board - Board payload
 * @param {string} edgeKey - Hex side being aimed at
 * @param {string} me - This player's name
 * @param {string|null} ignoring - A side being moved off, which must not hold
 *                                 its own destination up
 * @returns {boolean}
 */
function shipCanLie(board, edgeKey, me, ignoring) {
    const edge = board.edges[edgeKey];
    if (!edge || edge.sea !== true || edge.ship || edge.road) {
        return false;
    }
    // The pirate blocks every side of the hex it sits on.
    if (board.pirate_hex && (edge.neighbors.hexes || []).includes(board.pirate_hex)) {
        return false;
    }

    const ends = edge.neighbors.vertices || [];
    if (getGamePhase() === 'setup') {
        // The setup ship must touch the settlement just placed, and which one
        // that was is not in the payload - the same approximation the setup
        // road makes.
        return ends.some(key => board.vertices[key]?.building?.player === me);
    }
    // Own ships and own buildings only: a road at the same intersection does
    // not extend a shipping route.
    return ends.some(vertexKey => {
        const vertex = board.vertices[vertexKey];
        if (!vertex) {
            return false;
        }
        if (vertex.building?.player === me) {
            return true;
        }
        return (vertex.neighbors.edges || []).some(
            other => other !== edgeKey && other !== ignoring
                && board.edges[other]?.ship?.player === me
        );
    });
}

// The number tokens the Inventor may not move, and the rank a knight cannot be
// promoted past. Both are the engine's rules, copied here only to grey a ghost.
const PROTECTED_TOKENS = [2, 6, 8, 12];
const MIGHTY_RANK = 3;

/**
 * Every city on the board that already carries a wall.
 */
function walledVertices(board) {
    return Object.values(board.cities_knights?.city_wall_vertices || {}).flat();
}

/**
 * Whether a hex has one of this player's buildings on it.
 */
function touchesOwnBuilding(board, hexKey, me) {
    return Object.values(board.vertices).some(
        vertex => vertex.building?.player === me
            && (vertex.neighbors.hexes || []).includes(hexKey)
    );
}

/**
 * Whether the card being aimed would be refused this target.
 *
 * One branch per card and not per target shape: a Merchant and a Bishop both
 * take a hex and want very different ones, and a ghost that says "allowed"
 * where the server refuses is the half of this that a player cannot argue with.
 *
 * @param {object} board - Board payload
 * @param {string} key - Board key the pointer snapped to
 * @param {string} me - This player's name
 * @returns {boolean}
 */
function progressTargetIsBlocked(board, key, me) {
    // Aiming at something already picked takes that pick back, which is never
    // illegal.
    if (viewState.progressPick.picked.includes(key)) {
        return false;
    }

    const vertex = board.vertices[key];
    const standing = knightsByVertex()[key];

    switch (viewState.progressPick.card) {
        case 'merchant':
            return board.hexes[key]?.type === 'ocean'
                || !touchesOwnBuilding(board, key, me);
        case 'bishop':
            return board.hexes[key]?.type === 'ocean';
        case 'inventor':
            // The board's best and worst numbers stay where they are.
            return !board.hexes[key]?.number
                || PROTECTED_TOKENS.includes(board.hexes[key].number);
        case 'medicine':
            return vertex?.building?.player !== me
                || vertex?.building?.type !== 'settlement';
        case 'engineer':
            return vertex?.building?.player !== me
                || vertex?.building?.type !== 'city'
                || walledVertices(board).includes(key);
        case 'smith':
            // Mighty knights also need the Fortress, which is the engine's to
            // check: a ghost that says no where the server would agree is a
            // refusal the player cannot argue with.
            return standing?.owner !== me || standing?.knight.rank >= MIGHTY_RANK;
        case 'intrigue':
            return !standing || standing.owner === me
                || !touchesOwnRoad(board, key, me);
        case 'diplomat':
            // Whether the road has a free end is the engine's answer and worth
            // a round trip; that there is a road at all is not.
            return !board.edges[key]?.road;
        default:
            return false;
    }
}

/**
 * Whether the server would refuse this placement, as far as the client can
 * tell.
 *
 * @param {string} kind - Placement kind
 * @param {string} key - Board key the pointer snapped to
 * @returns {boolean} - True when the placement is known to be illegal
 */
function isBlocked(kind, key) {
    const board = getBoard();
    const me = viewState.identity.name;
    const inSetup = getGamePhase() === 'setup';

    if (kind === 'robber') {
        return board.hexes[key]?.type === 'ocean';
    }

    if (isProgressMode(kind)) {
        return progressTargetIsBlocked(board, key, me);
    }

    if (kind === 'pirate') {
        return board.hexes[key]?.type !== 'ocean' || key === board.pirate_hex;
    }

    if (kind === 'ship') {
        return !shipCanLie(board, key, me, null);
    }

    if (kind === 'ship_move') {
        // First tap picks the ship up, second lays it down, so which one is
        // being previewed depends on whether an origin is already held.
        if (!viewState.shipMoveFrom) {
            const ship = board.edges[key]?.ship;
            return ship?.player !== me || ship?.built_turn === board.turn_count;
        }
        return !shipCanLie(board, key, me, viewState.shipMoveFrom);
    }

    if (kind === 'road') {
        if (board.edges[key]?.road) {
            return true;
        }
        // A normal road may never sit on a river-crossing bridge site.
        if ((board.bridge_sites || []).includes(key)) {
            return true;
        }
        // The setup road must touch the settlement just placed, and which one
        // that was is not in the payload. Own buildings is the closest the
        // client can get without guessing.
        return inSetup
            ? !(board.edges[key].neighbors.vertices || [])
                .some(vertexKey => board.vertices[vertexKey]?.building?.player === me)
            : !roadConnects(board, key, me);
    }

    if (kind === 'bridge') {
        const edge = board.edges[key];
        // A bridge only spans a bridge site, only on an empty side, and only
        // when it joins the player's own network. The server re-checks the cost
        // and the per-player cap; the client errs permissive on both.
        if (!edge || !(board.bridge_sites || []).includes(key)) {
            return true;
        }
        if (edge.road || edge.ship) {
            return true;
        }
        return !roadConnects(board, key, me);
    }

    if (kind === 'barbarian_knight') {
        // A knight goes where a pending Knighthood/Swift Knight card allows: a
        // Knighthood on a free castle path, a Swift Knight on any free path. The
        // server re-checks the pending card and the knight supply; the client
        // errs permissive.
        const tb = board.tb || {};
        if (!board.edges[key] || (tb.knights || {})[key]) {
            return true;
        }
        const card = tb.pending_card?.card;
        if (card === 'knighthood') {
            return !(tb.castle_paths || []).includes(key);
        }
        return false;
    }

    if (kind === 'barbarian_knight_move') {
        // First tap picks one of your own knights up, second lays it down, so
        // which one is being previewed depends on whether an origin is held. The
        // server re-checks the reach and the pending card; the client errs
        // permissive on the distance, refusing only a landing it can see is taken.
        const knights = (board.tb || {}).knights || {};
        if (!viewState.barbarianKnightMoveFrom) {
            return knights[key] !== me;
        }
        return !board.edges[key] || Boolean(knights[key]);
    }

    const vertex = board.vertices[key];
    if (!vertex) {
        return true;
    }

    if (kind === 'settlement') {
        if (vertex.building || !respectsDistanceRule(board, key)) {
            return true;
        }
        return !inSetup && !touchesOwnRoad(board, key, me);
    }

    if (kind === 'city') {
        return vertex.building?.player !== me || vertex.building?.type !== 'settlement';
    }

    if (!ckEnabled()) {
        return true;
    }

    const standing = knightsByVertex();

    if (kind === 'city_wall') {
        return vertex.building?.player !== me || vertex.building?.type !== 'city';
    }

    if (kind === 'knight') {
        return Boolean(vertex.building) || Boolean(standing[key])
            || !touchesOwnRoad(board, key, me);
    }

    if (kind === 'knight_move') {
        // First tap picks the knight up, second puts it down, so which one is
        // being previewed depends on whether an origin is already held.
        if (!viewState.knightMoveFrom) {
            return standing[key]?.owner !== me || !standing[key]?.knight.can_act;
        }
        return Boolean(vertex.building) || Boolean(standing[key]);
    }

    return false;
}

// ----------------------------------------------------------------- hovering

/**
 * Record where the pointer is, for the render loop to hit-test.
 *
 * Bookkeeping only: pointermove fires far more often than the display
 * refreshes, and the snap and the redraw both belong to a frame.
 *
 * @param {number} clientX - Pointer clientX
 * @param {number} clientY - Pointer clientY
 */
export function samplePointer(clientX, clientY) {
    viewState.placement.sample = { x: clientX, y: clientY };
}

/**
 * Forget where the pointer was - the cursor left the board, or a gesture began.
 */
export function clearHover() {
    viewState.placement.sample = null;
    if (viewState.placement.hover) {
        viewState.placement.hover = null;
        markDirty();
    }
}

/**
 * The ghost to draw this frame: the pinned selection if there is one, the
 * hovered target otherwise.
 *
 * @returns {object|null} - {kind, key, blocked, color}
 */
export function currentPreview() {
    const target = viewState.placement.pending || viewState.placement.hover;
    // A ship picked up, or the first of a progress card's two targets: both are
    // held rather than sent, and the only place a player can see which one they
    // chose is where it is on the board.
    const held = viewState.shipMoveFrom || viewState.progressPick.picked[0] || null;
    if (!target && !held) {
        return null;
    }
    const mine = getBoard()?.players?.find(player => player.name === viewState.identity.name);
    if (!target) {
        return { kind: viewState.selectedBuilding, key: null, blocked: false,
                 color: mine?.color || null, from: held };
    }
    return { ...target, color: mine?.color || null, from: held };
}

/**
 * Re-derive the hover ghost, retire a stale selection, and keep the confirm
 * control over its target. Called once per frame from the render loop.
 */
export function updatePlacement() {
    const kind = currentPlacementKind();

    // A turn change, a piece that landed, or a disarmed button: whatever the
    // selection was for is gone, so it must not stay pinned to the board.
    if (viewState.placement.pending
        && armedKindOf(viewState.placement.pending.kind) !== kind) {
        viewState.placement.pending = null;
        markDirty();
    }

    updateHover(kind);
    syncConfirmControl();
}

/**
 * Recompute the hovered target from the last pointer sample.
 * Redraws only when the snapped target actually changed - a pointer crossing a
 * hex fires hundreds of moves and means one new ghost.
 *
 * @param {string|null} kind - Placement kind currently armed
 */
function updateHover(kind) {
    const sample = viewState.placement.sample;
    const previous = viewState.placement.hover;

    if (!kind || !sample || !getBoard()) {
        if (previous) {
            viewState.placement.hover = null;
            markDirty();
        }
        return;
    }

    const key = snapToTarget(kind, sample.x, sample.y);
    const aimed = key ? resolveKind(kind, key) : null;
    const next = key ? { kind: aimed, key, blocked: isBlocked(aimed, key) } : null;

    const same = Boolean(next) === Boolean(previous)
        && (!next || (next.key === previous.key && next.kind === previous.kind
                      && next.blocked === previous.blocked));
    if (same) {
        return;
    }

    viewState.placement.hover = next;
    markDirty();
}

// -------------------------------------------------------------- confirming

/**
 * Handle a tap on the board: place it outright in YOLO mode, otherwise pin the
 * target and ask.
 *
 * @param {number} clientX - Pointer clientX of the tap
 * @param {number} clientY - Pointer clientY of the tap
 * @returns {boolean} - Whether the tap was a placement attempt at all
 */
export function handlePlacementTap(clientX, clientY) {
    // The Explorers & Pirates board gestures (mission and cargo) do not go
    // through the ghost/confirm pipeline — each infers its action from the
    // target, so there is nothing to preview. Handle them first, on my turn —
    // but never over an outstanding 7, where the tap owes the robber or pirate.
    if (isEpBoardMode(viewState.selectedBuilding) && isMyTurn() && !mustMoveRobber()) {
        return handleEpBoardTap(clientX, clientY);
    }

    const kind = currentPlacementKind();
    if (!kind) {
        return false;
    }

    const key = snapToTarget(kind, clientX, clientY);
    if (!key) {
        return false;
    }

    // Picking the knight up is a selection, not a placement: nothing is sent
    // and there is nothing to undo, so there is nothing to confirm either.
    if (kind === 'knight_move' && !viewState.knightMoveFrom) {
        handleCkVertexTap(key);
        markDirty();
        return true;
    }

    // Picking a ship up is the same: it is the *second* tap that moves it.
    if (kind === 'ship_move' && !viewState.shipMoveFrom) {
        selectShipToMove(key);
        markDirty();
        return true;
    }

    // And picking a barbarian knight up: the second tap sends the move.
    if (kind === 'barbarian_knight_move' && !viewState.barbarianKnightMoveFrom) {
        selectBarbarianKnightToMove(key);
        markDirty();
        return true;
    }

    // And so is every pick of a progress card's target but the last: an
    // Inventor's first number token is recorded and nothing is sent, so there
    // is nothing to confirm. Tapping a pick again takes it back the same way.
    // A target the client can see is illegal is pinned instead, because
    // recording it silently is the one way a player could not tell.
    if (isProgressMode(kind) && !progressPickCompletes(key) && !isBlocked(kind, key)) {
        handleProgressTargetTap(key);
        markDirty();
        return true;
    }

    const aimed = resolveKind(kind, key);

    // Explorers & Pirates resolves a 7 only on the sea: the pirate ship replaces
    // the robber, so a land tap has no move to make. A sea tap became 'pirate'
    // above; a still-'robber' tap is on land, so cue the player rather than pin a
    // ✓ that would only draw a refusal. (Seafarers' own pirate leaves the robber
    // in play, so its land taps are real and this never fires there.)
    if (aimed === 'robber' && getBoard()?.rules?.pirate_ship_instead_of_robber === true) {
        displayError('The pirate ship sails — place it on a sea hex.');
        return true;
    }

    if (yoloMode) {
        commit({ kind: aimed, key });
        return true;
    }

    // Aiming somewhere else with a confirmation up moves the selection. It
    // must not commit the old one - a click is never a ✓.
    viewState.placement.pending = { kind: aimed, key, blocked: isBlocked(aimed, key) };
    markDirty();
    return true;
}

/**
 * Send the placement. This is the emit the click used to do, unchanged.
 *
 * @param {object} target - {kind, key}
 */
function commit(target) {
    const name = viewState.identity.name;

    if (target.kind === 'robber') {
        emitGame('move_robber', { name, hex: target.key });
    } else if (target.kind === 'pirate') {
        // Sent *instead of* move_robber, and answered with the same
        // `choose_victim` the robber raises. The Explorers & Pirates pirate is a
        // different piece and handler from the Seafarers one, told apart by which
        // rule armed it — the two never share a table.
        const event = getBoard()?.rules?.pirate_ship_instead_of_robber === true
            ? 'place_pirate_ship'
            : 'move_pirate';
        emitGame(event, { name, hex: target.key });
    } else if (target.kind === 'ship' || target.kind === 'ship_move') {
        handleShipEdgeTap(target.key);
    } else if (target.kind === 'settlement') {
        emitGame('place_settlement', { name, vertex: target.key });
    } else if (target.kind === 'road') {
        emitGame('place_road', { name, edge: target.key });
    } else if (target.kind === 'bridge') {
        emitGame('build_bridge', { name, edge: target.key });
    } else if (target.kind === 'barbarian_knight') {
        emitGame('place_barbarian_knight', { name, edge: target.key });
    } else if (target.kind === 'barbarian_knight_move') {
        moveBarbarianKnight(target.key);
    } else if (target.kind === 'city') {
        emitGame('upgrade_city', { name, vertex: target.key });
    } else if (isProgressMode(target.kind)) {
        handleProgressTargetTap(target.key);
    } else {
        handleCkVertexTap(target.key);
    }

    viewState.placement.pending = null;
    markDirty();
}

/**
 * Commit whatever is pinned, if anything.
 *
 * @returns {boolean} - Whether there was something to confirm
 */
export function confirmPending() {
    const pending = viewState.placement.pending;
    if (!pending) {
        return false;
    }
    commit(pending);
    return true;
}

/**
 * Drop the selection and leave the build mode armed, so the next click picks
 * again rather than the player having to re-arm the button.
 *
 * @returns {boolean} - Whether there was something to cancel
 */
export function cancelPending() {
    if (!viewState.placement.pending) {
        return false;
    }
    viewState.placement.pending = null;
    markDirty();
    return true;
}

/**
 * Show, hide and position the ✓/✗ control.
 *
 * It is absolutely positioned inside the board box and never in flow: an
 * element that took a row of its own would resize the canvas and move the
 * camera under the very click it is asking about.
 */
function syncConfirmControl() {
    if (!placementConfirm) {
        return;
    }

    const pending = viewState.placement.pending;
    if (!pending) {
        hideConfirmControl();
        return;
    }

    const point = anchorFor(pending);
    if (!point) {
        hideConfirmControl();
        return;
    }

    const box = gameBoard.getBoundingClientRect();
    const width = placementConfirm.offsetWidth || 72;
    const height = placementConfirm.offsetHeight || 32;
    const left = Math.min(
        Math.max(point.x - box.left, width / 2 + CONFIRM_MARGIN),
        box.width - width / 2 - CONFIRM_MARGIN
    );
    // Above the target by default; below it when there is no room above. The
    // element is centred on `left` by a CSS transform, so only `top` is a real
    // edge here.
    const above = point.y - box.top - CONFIRM_OFFSET_Y - height;
    const top = above < CONFIRM_MARGIN ? point.y - box.top + CONFIRM_OFFSET_Y : above;

    placementConfirm.style.left = `${Math.round(left)}px`;
    placementConfirm.style.top = `${Math.round(top)}px`;

    const wasShowing = !placementConfirm.classList.contains('hidden');
    placementConfirm.classList.remove('hidden');
    announcePending(pending);
    if (!wasShowing) {
        takeConfirmFocus();
    }
}

/**
 * Put the pending placement into the live region.
 *
 * Re-aiming replaces the selection rather than raising a second one, so the
 * text is repeated only when it actually changed - otherwise every hover-sized
 * re-render would read the same sentence out again.
 *
 * @param {object} pending - {kind, key, blocked}
 */
function announcePending(pending) {
    if (!placementAnnounce) {
        return;
    }
    // A card names itself: "Merchant selected" says which of the two cards that
    // take a hex is about to be played, where "Hex selected" says nothing.
    const noun = isProgressMode(pending.kind)
        ? (progressCardName() || 'Progress card')
        : (PLACEMENT_NOUNS[pending.kind] || 'Placement');
    // Blocked is otherwise carried only by the ghost's colour, which is exactly
    // the half of the message a screen reader cannot get at.
    const status = pending.blocked
        ? `${noun} selected, but not allowed here.`
        : `${noun} selected.`;
    const message = `${status} Press Enter to confirm, or Escape to cancel.`;
    if (message === lastAnnounced) {
        return;
    }
    lastAnnounced = message;
    placementAnnounce.textContent = message;
}

/**
 * Move focus onto ✓ as the confirmation appears.
 *
 * Deliberately conditional. Focus is the player's, not ours: someone part-way
 * through a chat message must not have their next keystroke land on a button
 * that places a settlement. Everywhere else - the canvas, a build button,
 * nothing at all - taking it is what makes the confirmation reachable without
 * a mouse, and Enter/Escape then mean the obvious thing.
 */
function takeConfirmFocus() {
    const active = document.activeElement;
    const typing = active instanceof HTMLElement
        && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName);
    if (typing || !placementConfirmYes) {
        return;
    }
    focusBeforeConfirm = active;
    placementConfirmYes.focus();
}

/**
 * Hide the ✓/✗ and hand focus back to whatever had it.
 *
 * Without the hand-back, answering the confirmation leaves focus on a button
 * that no longer exists on screen, and the next Tab starts again from the top
 * of the document.
 */
function hideConfirmControl() {
    if (placementConfirm.classList.contains('hidden')) {
        return;
    }
    const returning = placementConfirm.contains(document.activeElement);
    placementConfirm.classList.add('hidden');
    lastAnnounced = '';
    if (placementAnnounce) {
        placementAnnounce.textContent = '';
    }
    if (returning) {
        // The canvas is the fallback because it is where the placement came
        // from and it is focusable in its own right.
        const target = focusBeforeConfirm?.isConnected ? focusBeforeConfirm : boardCanvas;
        target?.focus();
    }
    focusBeforeConfirm = null;
}

/**
 * Where on screen the pinned target sits.
 *
 * @param {object} pending - {kind, key}
 * @returns {object|null} - {x, y} in client coordinates
 */
function anchorFor(pending) {
    const layout = window.BoardRenderer.computeLayout(getBoard());
    let position = null;
    if (HEX_KINDS.includes(pending.kind)) {
        position = layout.hexPositions[pending.key];
    } else if (EDGE_KINDS.includes(pending.kind)) {
        const edge = layout.edgePositions[pending.key];
        position = edge ? { x: edge.centerX, y: edge.centerY } : null;
    } else {
        position = layout.vertexPositions[pending.key];
    }
    if (!position) {
        return null;
    }
    return window.BoardRenderer.boardToClient(
        boardCanvas, position.x + layout.offsetX, position.y + layout.offsetY
    );
}

placementConfirmYes?.addEventListener('click', () => {
    confirmPending();
});

placementConfirmNo?.addEventListener('click', () => {
    cancelPending();
});

// Enter and Escape reach the whole document so they work wherever the focus
// landed - the canvas, the ✓, or nothing at all. Typing in the chat box is the
// one place Enter means something else.
document.addEventListener('keydown', (event) => {
    if (!viewState.placement.pending) {
        return;
    }
    const typing = event.target instanceof HTMLElement
        && ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName);

    if (event.key === 'Escape' && cancelPending()) {
        event.preventDefault();
        return;
    }
    if (event.key === 'Enter' && !typing && confirmPending()) {
        event.preventDefault();
    }
});

if (yoloToggle) {
    yoloToggle.checked = yoloMode;
    yoloToggle.addEventListener('change', () => {
        yoloMode = yoloToggle.checked;
        writeYoloPreference(yoloMode);
        // Turning it on mid-selection is an answer to the question on screen
        if (yoloMode) {
            confirmPending();
        }
    });
}
