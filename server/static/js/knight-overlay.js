// A knight's own actions, offered at the knight.
//
// Activating and promoting used to live only in the Knights fold, one list of
// buttons for every knight on the board, each identified by a vertex key the
// player never sees. The tester asked for the obvious thing instead: tap the
// knight, get its actions. So a tap on a knight this player owns raises a small
// overlay over that piece with Activate, Promote and Move on it - the illegal
// ones greyed with the reason in `title`, exactly as every other unaffordable
// action in this client is presented.
//
// Two things it must not disturb, both learned the hard way:
//
//   - The overlay is absolutely positioned inside the board box, like the ✓/✗
//     in placement.js. Nothing here may take a row of its own: an element in
//     flow beside the board resizes the drawing buffer and re-fits the camera,
//     and a click already in flight lands somewhere else.
//   - The two-tap knight move. This is consulted only after placement.js has
//     declined the tap, so with the move armed the first tap still picks the
//     knight up and still sends nothing. The overlay's own Move button does the
//     same thing by another route.

import { markDirty } from './board.js';
import { KNIGHT_ACTION_LABELS, ckEnabled, knightActionReasons, myKnightAt, startKnightMove } from './cities-knights.js';
import { boardCanvas, gameBoard, knightActionButtons, knightActions } from './dom.js';
import { emitGame } from './socket.js';
import { getBoard, viewState } from './state.js';

// Clear of the shield the renderer draws, and inside the board box, which
// clips. Same job as the confirm control's offsets and deliberately the same
// shape of solution.
const OVERLAY_OFFSET_Y = 30;
const OVERLAY_MARGIN = 6;

// Which knight the player has open, by vertex key. Null when nothing is open,
// which is also how "no overlay is drawn" is stored - there is no second flag
// to get out of step with this one.
let openVertex = null;

/**
 * Handle a tap on the board that was not a placement.
 *
 * @param {number} clientX - Pointer clientX of the tap
 * @param {number} clientY - Pointer clientY of the tap
 * @returns {boolean} - Whether the tap opened or closed the overlay
 */
export function handleKnightTap(clientX, clientY) {
    if (!ckEnabled() || !getBoard()) {
        return false;
    }

    const position = window.BoardRenderer.clientToBoard(boardCanvas, clientX, clientY);
    const key = window.BoardRenderer.findNearestVertex(getBoard(), position.x, position.y);
    const knight = key ? myKnightAt(key) : null;

    // A tap that missed every knight of this player's is a dismissal, so the
    // overlay behaves like every other transient thing on the board.
    if (!knight) {
        return closeOverlay();
    }

    // Tapping the open one again closes it: with no other control on the
    // overlay, the piece itself is the toggle.
    if (openVertex === key) {
        return closeOverlay();
    }

    openVertex = key;
    markDirty();
    renderOverlay();
    return true;
}

/**
 * Put the overlay away, if it is up.
 *
 * @returns {boolean} - Whether there was one to put away
 */
export function closeOverlay() {
    if (openVertex === null) {
        return false;
    }
    openVertex = null;
    hide();
    markDirty();
    return true;
}

/**
 * Keep the overlay over its knight, and retire it when the knight is gone.
 *
 * Called once per frame from the render loop, like the confirm control: the
 * camera can pan and zoom under an open overlay, and a knight can be taken off
 * the board by somebody else's turn.
 */
export function updateKnightOverlay() {
    if (openVertex === null) {
        return;
    }
    // Arming a build mode makes the board about placing a piece, not about the
    // knight standing there, and leaving both up would make the next tap
    // ambiguous.
    if (!ckEnabled() || !myKnightAt(openVertex) || viewState.selectedBuilding) {
        closeOverlay();
        return;
    }
    renderOverlay();
}

/**
 * Fill the buttons for the open knight and place the overlay over it.
 */
function renderOverlay() {
    if (!knightActions || openVertex === null) {
        return;
    }

    const knight = myKnightAt(openVertex);
    if (!knight) {
        return;
    }

    const reasons = knightActionReasons(knight);
    for (const button of knightActionButtons) {
        const action = button.dataset.knightOverlay;
        const reason = reasons[action] || '';
        button.textContent = KNIGHT_ACTION_LABELS[action];
        button.disabled = Boolean(reason);
        // The reason a player cannot do something, in the same place the rest
        // of this client puts it. Never blank: an enabled button says what it
        // is about to do instead.
        button.title = reason || `${KNIGHT_ACTION_LABELS[action]} this knight`;
    }

    const point = anchorFor(openVertex);
    if (!point) {
        hide();
        return;
    }

    const box = gameBoard.getBoundingClientRect();
    const width = knightActions.offsetWidth || 220;
    const height = knightActions.offsetHeight || 32;
    const left = Math.min(
        Math.max(point.x - box.left, width / 2 + OVERLAY_MARGIN),
        box.width - width / 2 - OVERLAY_MARGIN
    );
    // Above the knight where there is room, below it where there is not. The
    // element is centred on `left` by a CSS transform, so only `top` is a real
    // edge here.
    const above = point.y - box.top - OVERLAY_OFFSET_Y - height;
    const top = above < OVERLAY_MARGIN ? point.y - box.top + OVERLAY_OFFSET_Y : above;

    knightActions.style.left = `${Math.round(left)}px`;
    knightActions.style.top = `${Math.round(top)}px`;
    knightActions.classList.remove('hidden');
}

function hide() {
    knightActions?.classList.add('hidden');
}

/**
 * Where on screen the knight's intersection sits.
 *
 * @param {string} vertexKey - Vertex the open knight stands on
 * @returns {object|null} - {x, y} in client coordinates
 */
function anchorFor(vertexKey) {
    const layout = window.BoardRenderer.computeLayout(getBoard());
    const position = layout.vertexPositions[vertexKey];
    if (!position) {
        return null;
    }
    return window.BoardRenderer.boardToClient(
        boardCanvas, position.x + layout.offsetX, position.y + layout.offsetY
    );
}

// One delegated listener for three static buttons. Every action closes the
// overlay: the answer to "what can this knight do" changes the moment one of
// them is taken, and a stale list of three is worse than none.
knightActions?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-knight-overlay]');
    if (!button || button.disabled || openVertex === null) {
        return;
    }
    const vertex = openVertex;
    const action = button.dataset.knightOverlay;
    closeOverlay();

    if (action === 'move') {
        // Picking the knight up, which is what the first tap of a move does.
        // Nothing is sent until the second tap is confirmed.
        startKnightMove(vertex);
        return;
    }
    emitGame(action === 'promote' ? 'promote_knight' : 'activate_knight', {
        name: viewState.identity.name, vertex
    });
});

// Escape dismisses it, as it dismisses the placement confirmation. Registered
// on the document so it works wherever focus landed; placement.js returns early
// when nothing is pinned, so the two never both answer one press.
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !viewState.placement.pending && closeOverlay()) {
        event.preventDefault();
    }
});
