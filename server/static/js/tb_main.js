// The Traders & Barbarians main-scenario panel: the wagon run at a glance — the
// commodity you carry, where it must go, how much you have delivered, your
// baggage-train card and this turn's movement points — plus the gestures the
// scenario needs: move your wagon, boost it with grain, upgrade the baggage
// train, buy a wagon-deck card, and move a barbarian after a 7 or a Knight card.
// Read from `board.tb`, where all the wagon state rides. Mirrors the other
// scenario panels: one render on every board update that hides the panel whole
// on a table not playing the scenario.
//
// No rule logic lives here beyond erring permissive: the server checks the
// movement points, the point costs, the delivery match and the barbarian move,
// and its answer is what the board is drawn from. The wagon and barbarian
// gestures are self-contained here — an armed mode listens for a board tap and
// snaps it to the nearest intersection or path with the shared BoardRenderer
// helpers — rather than joining the base placement pipeline.

import { boardCanvas } from './dom.js';
import { markDirty } from './board.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn } from './state.js';

// The armed board gesture: 'wagon', 'barbarian', 'drive', or null. `barbFrom`
// holds the barbarian path a two-tap gesture has picked up, awaiting the free
// path to move (or drive) it to.
let mode = null;
let barbFrom = null;

function el(id) {
    return document.getElementById(id);
}

/** Whether the table is playing the main scenario. */
function tbMainInPlay(board) {
    return Boolean(board?.rules?.trade_caravans);
}

function me(board) {
    return (board.players || []).find(p => p.is_you) || {};
}

/**
 * Render the main-scenario panel from the board, hidden whole on a table without
 * the scenario. Called on every board update.
 */
export function renderTbMain() {
    const panel = el('right-tb-main');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const show = tbMainInPlay(board);
    panel.classList.toggle('hidden', !show);
    if (!show) {
        mode = null;
        barbFrom = null;
        return;
    }
    renderStatus(board);
    renderActions(board);
}

function renderStatus(board) {
    const status = el('tb-main-status');
    if (!status) {
        return;
    }
    const tb = board.tb || {};
    const name = me(board).name;
    const carried = (tb.carried_commodity || {})[name];
    const level = (tb.baggage_level || {})[name] || 1;
    const delivered = (tb.delivered_counts || {})[name] || 0;
    const vpCards = (tb.td_vp_counts || {})[name] || 0;

    const items = [
        ['Carrying', carried || '—'],
        ['Delivered', delivered],
        ['Baggage card', level],
        ['Points left', board.wagon_points_left ?? '—'],
        ['VP cards', vpCards],
        ['Cards left', tb.td_deck_remaining ?? 0],
    ];
    status.textContent = '';
    for (const [label, value] of items) {
        const item = document.createElement('span');
        item.className = 'ep-supply-item';
        item.innerHTML = `${label} <strong>${value}</strong>`;
        status.appendChild(item);
    }
}

function renderActions(board) {
    const mine = isMyTurn();
    const tb = board.tb || {};
    const name = me(board).name;
    const owesBarbarian = board.must_move_barbarian === name
        || ((tb.td_pending || {}).player === name);

    setButton('tb-move-wagon', mine, mode === 'wagon');
    setButton('tb-boost-wagon', mine, false);
    setButton('tb-upgrade-baggage', mine && Boolean(board.rules.baggage_train), false);
    setButton('tb-buy-card', mine && Boolean(board.rules.trade_dev_deck), false);

    const barbBtn = el('tb-move-barbarian');
    if (barbBtn) {
        barbBtn.classList.toggle('hidden', !owesBarbarian && mode !== 'barbarian');
        barbBtn.disabled = !mine;
        barbBtn.classList.toggle('active', mode === 'barbarian');
    }

    // The voluntary drive-off: offered whenever the roaming barbarians are in
    // play, enabled on the driver's own turn. The server decides eligibility —
    // the baggage level, the wagon's adjacency and the once-per-turn limit — and
    // refuses when it is not met, surfaced like any other rejected gesture.
    const driveBtn = el('tb-drive-barbarian');
    if (driveBtn) {
        driveBtn.classList.toggle('hidden', !board.rules.roaming_barbarians);
        driveBtn.disabled = !mine;
        driveBtn.classList.toggle('active', mode === 'drive');
    }

    const hint = el('tb-main-hint');
    if (hint) {
        let text = '';
        if (mode === 'wagon') {
            text = 'Tap an adjacent intersection to move your wagon.';
        } else if (mode === 'barbarian') {
            text = barbFrom
                ? 'Tap a free path to move the barbarian to.'
                : 'Tap the barbarian to move, then a free path.';
        } else if (mode === 'drive') {
            text = barbFrom
                ? 'Tap a free path to drive the barbarian to.'
                : 'Tap the barbarian beside your wagon, then a free path.';
        } else if (owesBarbarian) {
            text = 'You rolled a 7 — move a barbarian.';
        }
        hint.classList.toggle('hidden', !text);
        hint.textContent = text;
    }
}

function setButton(id, enabled, active) {
    const button = el(id);
    if (!button) {
        return;
    }
    button.disabled = !enabled;
    button.classList.toggle('active', Boolean(active));
}

function armMode(next) {
    mode = mode === next ? null : next;
    barbFrom = null;
    markDirty();
    renderTbMain();
}

/** A board tap while a move mode is armed: snap it and emit the move. */
function onBoardTap(event) {
    if (!mode || !window.BoardRenderer) {
        return;
    }
    const board = getBoard();
    if (!board) {
        return;
    }
    // An armed wagon/barbarian gesture consumes the tap, so the base placement
    // pipeline does not also read it.
    event.stopPropagation();
    const point = window.BoardRenderer.clientToBoard(boardCanvas, event.clientX, event.clientY);
    if (mode === 'wagon') {
        const vertex = window.BoardRenderer.findNearestVertex(board, point.x, point.y);
        if (vertex) {
            emitGame('move_wagon', { to: vertex });
        }
        return;
    }
    if (mode === 'barbarian' || mode === 'drive') {
        const edge = window.BoardRenderer.findNearestEdge(board, point.x, point.y);
        if (!edge) {
            return;
        }
        const barbarians = new Set((board.tb || {}).path_barbarians || []);
        if (!barbFrom) {
            if (barbarians.has(edge)) {
                barbFrom = edge;
                renderTbMain();
            }
            return;
        }
        if (mode === 'drive') {
            emitGame('drive_off_barbarian', { barbarian: barbFrom, to: edge });
        } else {
            emitGame('move_path_barbarian', { from: barbFrom, to: edge });
        }
        barbFrom = null;
        mode = null;
    }
}

el('tb-move-wagon')?.addEventListener('click', () => armMode('wagon'));
el('tb-move-barbarian')?.addEventListener('click', () => armMode('barbarian'));
el('tb-drive-barbarian')?.addEventListener('click', () => armMode('drive'));
el('tb-boost-wagon')?.addEventListener('click', () => emitGame('boost_wagon', {}));
el('tb-upgrade-baggage')?.addEventListener('click', () => emitGame('upgrade_baggage_train', {}));
el('tb-buy-card')?.addEventListener('click', () => emitGame('buy_trade_card', {}));
boardCanvas?.addEventListener('click', onBoardTap, true);
