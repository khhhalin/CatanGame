// The board: one render loop, and the taps and gestures that reach it.

import { handleCkVertexTap } from './cities-knights.js';
import { boardCanvas } from './dom.js';
import { displayError } from './notices.js';
import { emitGame } from './socket.js';
import { getBoard, getGamePhase, isMyTurn, mustMoveRobber, viewState } from './state.js';

/**
 * Mark the board as needing a redraw on the next animation frame.
 */
export function markDirty() {
    viewState.render.dirty = true;
}

/**
 * Mark the board dirty and set the dice-number highlight for the next frames.
 *
 * @param {number|null} number - Dice total to highlight, or null to clear
 */
export function setHighlight(number) {
    viewState.render.highlightNumber = number;
    markDirty();
}

/**
 * The single render loop for the lifetime of the page.
 */
function frame() {
    if (viewState.render.dirty) {
        viewState.render.dirty = false;
        try {
            if (getBoard() && window.BoardRenderer) {
                window.BoardRenderer.render(getBoard(), 'board-canvas', viewState.render.highlightNumber);
                updateBoardLabel();
            }
        } catch (error) {
            // A throw here would leave the loop scheduled but the board frozen
            console.error('Board render failed:', error);
            displayError('The board could not be drawn. Try reloading the page.');
        }
    }
    requestAnimationFrame(frame);
}

requestAnimationFrame(frame);

/**
 * Keep the canvas accessible name in step with what is drawn.
 */
function updateBoardLabel() {
    if (!boardCanvas || !getBoard()) {
        return;
    }
    const phase = getBoard().game_phase || 'playing';
    const turnHolder = getBoard().current_player || 'nobody';
    boardCanvas.setAttribute('aria-label',
        `Catan board, ${phase} phase. Current turn: ${turnHolder}.`);
}

// Pointer tracking for the board - a tap places, a drag does not
const TAP_MOVE_LIMIT_PX = 10;
const TAP_TIME_LIMIT_MS = 700;

/**
 * Handle a tap on the board - place building at tapped position
 *
 * @param {PointerEvent} event - The pointerup event that ended the tap
 */
function handleBoardTap(event) {
    if (!getBoard()) {
        return;
    }

    // That gesture moved the view, it was not a tap. The movement threshold
    // below misses a slow pan that ends near where it started.
    if (window.BoardRenderer?.wasPanning?.()) {
        return;
    }

    const position = window.BoardRenderer.clientToBoard(boardCanvas, event.clientX, event.clientY);

    // Handle robber movement while the robber is still pending
    if (mustMoveRobber() && isMyTurn()) {
        const hexKey = window.BoardRenderer.findNearestHex(getBoard(), position.x, position.y);
        if (hexKey) {
            console.log('Moving robber to:', hexKey);
            emitGame('move_robber', {
                name: viewState.identity.name,
                hex: hexKey
            });
        }
        return;
    }

    if (!viewState.selectedBuilding || !isMyTurn()) {
        return;
    }

    // During setup phase, ensure selected building matches setup_action
    if (getGamePhase() === 'setup') {
        const setupAction = getBoard().setup_action || 'settlement';
        if (viewState.selectedBuilding !== setupAction) {
            return;
        }
    }

    if (viewState.selectedBuilding === 'settlement') {
        // Find nearest vertex
        const vertexKey = window.BoardRenderer.findNearestVertex(getBoard(), position.x, position.y);
        if (vertexKey) {
            console.log('Placing settlement at:', vertexKey);
            emitGame('place_settlement', {
                name: viewState.identity.name,
                vertex: vertexKey
            });
        }
    } else if (viewState.selectedBuilding === 'road') {
        // Find nearest edge
        const edgeKey = window.BoardRenderer.findNearestEdge(getBoard(), position.x, position.y);
        if (edgeKey) {
            console.log('Placing road at:', edgeKey);
            emitGame('place_road', {
                name: viewState.identity.name,
                edge: edgeKey
            });
        }
    } else if (viewState.selectedBuilding === 'city') {
        // Find nearest vertex to upgrade to city
        const vertexKey = window.BoardRenderer.findNearestVertex(getBoard(), position.x, position.y);
        if (vertexKey) {
            console.log('Upgrading to city at:', vertexKey);
            emitGame('upgrade_city', {
                name: viewState.identity.name,
                vertex: vertexKey
            });
        }
    } else if (viewState.selectedBuilding === 'knight' || viewState.selectedBuilding === 'city_wall'
               || viewState.selectedBuilding === 'knight_move') {
        const vertexKey = window.BoardRenderer.findNearestVertex(getBoard(), position.x, position.y);
        if (vertexKey) {
            handleCkVertexTap(vertexKey);
        }
    }
}

boardCanvas.addEventListener('pointerdown', (event) => {
    viewState.pointerDown = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        time: Date.now()
    };
    // Capture so the matching pointerup arrives even if the finger leaves the canvas
    boardCanvas.setPointerCapture(event.pointerId);
});

boardCanvas.addEventListener('pointerup', (event) => {
    if (!viewState.pointerDown || viewState.pointerDown.pointerId !== event.pointerId) {
        return;
    }

    const movedX = Math.abs(event.clientX - viewState.pointerDown.x);
    const movedY = Math.abs(event.clientY - viewState.pointerDown.y);
    const elapsed = Date.now() - viewState.pointerDown.time;
    viewState.pointerDown = null;

    if (movedX <= TAP_MOVE_LIMIT_PX && movedY <= TAP_MOVE_LIMIT_PX && elapsed <= TAP_TIME_LIMIT_MS) {
        handleBoardTap(event);
    }
});

boardCanvas.addEventListener('pointercancel', () => {
    viewState.pointerDown = null;
});

// Zoom and pan. Registered after the tap listeners above on purpose: the
// renderer clears its `panning` flag on pointerup, and the tap handler has to
// still see it. The call is idempotent; the renderer never draws, it marks the
// frame dirty through this callback and the one render loop picks it up.
window.BoardRenderer?.attachCameraControls?.(boardCanvas, markDirty);

/**
 * Zoom about the middle of the visible board, in CSS pixels.
 *
 * @param {number} factor - Multiplier for the current scale
 */
function zoomFromButton(factor) {
    const rect = boardCanvas.getBoundingClientRect();
    window.BoardRenderer?.zoomAt?.(factor, rect.width / 2, rect.height / 2);
    markDirty();
}

document.getElementById('zoom-in-btn')?.addEventListener('click', () => zoomFromButton(1.2));
document.getElementById('zoom-out-btn')?.addEventListener('click', () => zoomFromButton(1 / 1.2));
document.getElementById('zoom-fit-btn')?.addEventListener('click', () => {
    window.BoardRenderer?.fitToView?.();
    markDirty();
});

// Resize handling - the buffer must be re-sized for the new box, but drawing
// belongs to the render loop, so only mark dirty here
window.addEventListener('resize', markDirty);

// devicePixelRatio can change without a resize event (moving to another monitor)
if (window.matchMedia) {
    window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`)
        .addEventListener('change', markDirty);
}
