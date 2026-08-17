// The Wonders of Catan panel: the five Wonders with their per-level cost and
// start requirement, which are already taken, each player's chosen Wonder and
// level, and a Build affordance on the one this seat may raise. Read from
// `board.wonders` — the catalogue and every player's progress ride on the board
// payload's own `wonders_client_state`. Mirrors caravans.js: one render on every
// board update that hides the whole panel on a table not playing the scenario.
//
// No rule logic lives here beyond erring permissive: the Build button offers the
// action, and the server checks the requirement, the cost and the one-Wonder
// rules before it does anything. Its answer is what the board is drawn from.

import { resourceTile } from './icons.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

function el(id) {
    return document.getElementById(id);
}

/** The Wonders scenario's client state, or null off the scenario. */
function wondersState(board) {
    return board?.rules?.wonders ? (board.wonders || null) : null;
}

/**
 * Render the Wonders panel from the board, hidden whole on a table without the
 * scenario. Called on every board update.
 */
export function renderWonders() {
    const panel = el('right-wonders');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const state = wondersState(board);
    panel.classList.toggle('hidden', !state);
    if (!state) {
        return;
    }
    renderStatus(state);
    renderCatalogue(board, state);
}

/** The heading line: your Wonder and how far it has risen, or an invitation. */
function renderStatus(state) {
    const status = el('wonders-status');
    if (!status) {
        return;
    }
    const me = viewState.identity.name;
    const mine = (state.players || {})[me] || {};
    status.textContent = '';
    const item = document.createElement('span');
    item.className = 'ep-supply-item';
    if (mine.wonder) {
        const spec = (state.catalogue || []).find(w => w.id === mine.wonder);
        const name = spec ? spec.name : mine.wonder;
        item.innerHTML = `Your Wonder <strong>${name}</strong> — level `
            + `<strong>${mine.level}</strong> / ${state.levels}`;
    } else {
        item.innerHTML = 'Choose a Wonder to raise';
    }
    status.appendChild(item);
}

/** One row per Wonder: name, per-level cost, requirement, who holds it, Build. */
function renderCatalogue(board, state) {
    const list = el('wonders-list');
    if (!list) {
        return;
    }
    const me = viewState.identity.name;
    const players = state.players || {};
    const mine = players[me] || {};
    const taken = new Set(state.taken || []);
    // Who is building each Wonder and how high, for the "taken by" note.
    const builderOf = {};
    for (const [name, progress] of Object.entries(players)) {
        if (progress.wonder) {
            builderOf[progress.wonder] = { name, level: progress.level };
        }
    }

    list.textContent = '';
    for (const wonder of state.catalogue || []) {
        list.appendChild(wonderRow(board, state, wonder, {
            me, mine, taken, builder: builderOf[wonder.id] || null,
        }));
    }
}

function wonderRow(board, state, wonder, ctx) {
    const row = document.createElement('div');
    row.className = 'ep-player-row wonders-row';

    const name = document.createElement('div');
    name.className = 'wonders-name';
    name.textContent = wonder.name;
    row.appendChild(name);

    // The five cards printed as a stack of resource icons: the per-level cost.
    const cost = document.createElement('div');
    cost.className = 'wonders-cost';
    cost.innerHTML = costTiles(wonder.cost);
    row.appendChild(cost);

    const req = document.createElement('div');
    req.className = 'choice-hint wonders-req';
    req.textContent = wonder.requirement;
    row.appendChild(req);

    const holder = document.createElement('div');
    holder.className = 'wonders-holder';
    if (ctx.builder) {
        const you = ctx.builder.name === ctx.me ? ' (you)' : '';
        holder.textContent = `${ctx.builder.name}${you} — level ${ctx.builder.level}`
            + ` / ${state.levels}`;
    } else {
        holder.textContent = 'unclaimed';
    }
    row.appendChild(holder);

    const build = buildButton(state, wonder, ctx);
    if (build) {
        row.appendChild(build);
    }
    return row;
}

/** Repeat each resource's tile as many times as the level costs it. */
function costTiles(cost) {
    let html = '';
    for (const [resource, amount] of Object.entries(cost || {})) {
        for (let i = 0; i < amount; i += 1) {
            html += resourceTile(resource);
        }
    }
    return html;
}

/**
 * The Build button, shown only when this seat may act on this Wonder: it is the
 * one they have started, or — having started none — one nobody else holds. The
 * server still checks the requirement and the cost, so this errs permissive.
 */
function buildButton(state, wonder, ctx) {
    const started = ctx.mine.wonder || null;
    const actionable = started ? started === wonder.id : !ctx.taken.has(wonder.id);
    if (!actionable) {
        return null;
    }
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ep-action-btn wonders-build';
    btn.dataset.wonder = wonder.id;
    const finished = ctx.mine.level >= state.levels && started === wonder.id;
    btn.textContent = started === wonder.id ? 'Raise a level' : 'Start';
    btn.disabled = !isMyTurn() || finished;
    btn.addEventListener('click', () => emitGame('build_wonder_level', { wonder: wonder.id }));
    return btn;
}
