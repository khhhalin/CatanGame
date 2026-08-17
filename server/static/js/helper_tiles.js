// CATAN - The Helpers panel: the tile you hold and its one-shot advantage, an
// Activate affordance carrying whatever the tile needs, and the display of
// tiles you can exchange into. Read from `board.helpers` — the display pile,
// every player's held tile and the tile catalogue ride on the board payload's
// own `helpers_client_state`. Mirrors pirate_islands.js: one render on every
// board update that hides the whole panel on a table not playing the scenario.
//
// The exchange-or-flip that follows a use is a pending choice, drawn by the
// shared choices.js dialog, not here. No rule logic lives here beyond erring
// permissive: the button offers the action and the server checks the tile, the
// turn and the board before it does anything.

import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

function el(id) {
    return document.getElementById(id);
}

/** The helper subsystem's client state, or null off the scenario. */
function helperState(board) {
    return board?.rules?.helper_tiles ? (board.helpers || null) : null;
}

/**
 * Render the Helpers panel from the board, hidden whole on a table without the
 * scenario. Called on every board update.
 */
export function renderHelperTiles() {
    const panel = el('right-helpers');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const state = helperState(board);
    panel.classList.toggle('hidden', !state);
    if (!state) {
        return;
    }
    const me = viewState.identity.name;
    const held = (state.held || {})[me] || null;
    const tile = held ? (state.catalogue || {})[held.tile] : null;
    renderHeld(state, held, tile);
    renderActions(state, held, tile);
    renderDisplay(state);
}

/** The tile in front of you: name, advantage, which side is up, and its text. */
function renderHeld(state, held, tile) {
    const box = el('helper-held');
    if (!box) {
        return;
    }
    box.textContent = '';
    if (!held || !tile) {
        box.textContent = 'No helper tile in front of you.';
        return;
    }
    const title = document.createElement('div');
    title.className = 'helper-title';
    title.textContent = `${tile.name} — ${tile.title}`;
    box.appendChild(title);

    const side = document.createElement('span');
    side.className = `helper-side helper-side-${held.side}`;
    side.textContent = held.side === 'sun' ? '☀ Sun' : '☽ Moon';
    box.appendChild(side);

    const summary = document.createElement('div');
    summary.className = 'helper-summary';
    summary.textContent = tile.summary;
    box.appendChild(summary);
}

/**
 * The Activate control, plus one resource picker per resource the tile asks for.
 * Whatever the pickers hold rides along as params; the server ignores any it
 * does not need this time (the robber's hex may already fix Kaja's resource).
 */
function renderActions(state, held, tile) {
    const actions = el('helper-actions');
    if (!actions) {
        return;
    }
    actions.textContent = '';
    if (!held || !tile) {
        return;
    }
    const used = (state.used_this_turn || []).includes(viewState.identity.name);
    // Each tile builds the inputs its advantage needs and returns a collector
    // that reads them into an activation payload. The bespoke ones (Asla,
    // Stina, Diara, Carla, Gregor) know their own shape; the rest fall back to
    // the resource/player pickers their `needs` list describes.
    const collect = (CUSTOM_FORMS[held.tile] || genericForm)(tile, actions);

    const activate = document.createElement('button');
    activate.type = 'button';
    activate.className = 'ep-action-btn helper-activate';
    activate.textContent = used ? 'Helper used this turn' : 'Activate';
    activate.disabled = used || !canActOffTurn(tile);
    activate.addEventListener('click', () => {
        emitGame('activate_helper', { tile: held.tile, params: collect() });
    });
    actions.appendChild(activate);
}

/** The five resources, and the build choices Gregor offers. */
const RESOURCES = ['wood', 'brick', 'sheep', 'wheat', 'ore'];

/** Resource/player pickers driven by the tile's `needs` list. */
function genericForm(tile, actions) {
    const resourcePickers = [];
    const playerPickers = [];
    (tile.needs || []).forEach((need, index) => {
        if (need === 'resource') {
            const picker = resourcePicker(`res-${index}`);
            resourcePickers.push(picker);
            actions.appendChild(picker);
        } else if (need === 'player') {
            const picker = playerPicker(`plr-${index}`);
            if (picker) {
                playerPickers.push(picker);
                actions.appendChild(picker);
            }
        }
    });
    return () => {
        const params = {};
        if (resourcePickers.length === 1) {
            params.resource = resourcePickers[0].value;
        } else if (resourcePickers.length > 1) {
            params.resources = resourcePickers.map(picker => picker.value);
        }
        if (playerPickers.length === 1) {
            params.target = playerPickers[0].value;
        } else if (playerPickers.length > 1) {
            params.targets = playerPickers.map(picker => picker.value);
        }
        return params;
    };
}

/** Bespoke parameter forms for the multi-input advantages. */
const CUSTOM_FORMS = {
    // Asla: a resource to request, and up to two (player, give-back) pairs.
    asla(tile, actions) {
        const request = resourcePicker('asla-req');
        actions.appendChild(labelled('Request', request));
        const rows = [1, 2].map(n => {
            const target = playerPicker(`asla-tgt-${n}`);
            const back = resourcePicker(`asla-back-${n}`);
            const use = checkbox(`asla-use-${n}`, n === 1);
            if (target) {
                actions.appendChild(labelled(`From #${n}`, target));
                actions.appendChild(labelled('give back', back));
                actions.appendChild(labelled('use', use));
            }
            return { target, back, use };
        });
        return () => {
            const targets = [];
            const returns = [];
            rows.forEach(row => {
                if (row.target && row.use.checked) {
                    targets.push(row.target.value);
                    returns.push(row.back.value);
                }
            });
            return { resource: request.value, targets, returns };
        };
    },
    // Stina: a resource to spend, and up to three 2:1 receipts.
    stina(tile, actions) {
        const give = resourcePicker('stina-give');
        actions.appendChild(labelled('Spend', give));
        const receives = [1, 2, 3].map(n => {
            const pick = resourcePicker(`stina-get-${n}`);
            const use = checkbox(`stina-use-${n}`, n === 1);
            actions.appendChild(labelled(`get ${n}`, pick));
            actions.appendChild(labelled('on', use));
            return { pick, use };
        });
        return () => ({
            resource_out: give.value,
            resources: receives.filter(r => r.use.checked).map(r => r.pick.value),
        });
    },
    // Diara: an optional single-resource substitution on the card's cost.
    diara(tile, actions) {
        const from = document.createElement('select');
        from.className = 'helper-resource';
        [['', '(no swap)'], ['wheat', 'wheat'], ['sheep', 'sheep'], ['ore', 'ore']]
            .forEach(([value, text]) => {
                const option = document.createElement('option');
                option.value = value;
                option.textContent = text;
                from.appendChild(option);
            });
        const withRes = resourcePicker('diara-with');
        actions.appendChild(labelled('Swap', from));
        actions.appendChild(labelled('for', withRes));
        return () => (from.value
            ? { substitute_from: from.value, substitute_with: withRes.value }
            : {});
    },
    // Carla: which of your unplayed development cards to swap away.
    carla(tile, actions) {
        const select = document.createElement('select');
        select.className = 'helper-resource';
        const me = (getBoard().players || []).find(p => p.name === viewState.identity.name);
        const dev = (me && me.dev_cards) || {};
        Object.keys(dev).forEach(type => {
            if ((dev[type].count || 0) > 0) {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = type;
                select.appendChild(option);
            }
        });
        actions.appendChild(labelled('Swap away', select));
        return () => ({ dev_card: select.value });
    },
    // Yngvi: which base card to drop and what to pay. The road's edge is not
    // typed here - activating opens a pending choice and the player taps the
    // ringed path on the board, which resolves through the shared choices path.
    yngvi(tile, actions) {
        const drop = document.createElement('select');
        drop.className = 'helper-resource';
        [['wood', 'lumber'], ['brick', 'brick']].forEach(([value, text]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = text;
            drop.appendChild(option);
        });
        const pay = resourcePicker('yngvi-pay');
        actions.appendChild(labelled('Drop', drop));
        actions.appendChild(labelled('pay', pay));
        return () => ({ drop: drop.value, resource: pay.value });
    },
    // Hogni: no inputs. Activating opens a board choice of your end roads to
    // lift, then a second of where to lay it - both answered by tapping the
    // ringed path on the board.
    hogni() {
        return () => ({});
    },
    // Gregor: which building to raise. The intersection is not typed - activating
    // opens a pending choice and the player taps the ringed spot on the board.
    gregor(tile, actions) {
        const build = document.createElement('select');
        build.className = 'helper-resource';
        build.id = 'gregor-build';
        [['settlement', 'settlement'], ['city', 'city']].forEach(([value, text]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = text;
            build.appendChild(option);
        });
        actions.appendChild(labelled('Build', build));
        return () => ({ build: build.value });
    },
};

/** Wrap a control with a short inline label. */
function labelled(text, control) {
    const wrap = document.createElement('label');
    wrap.className = 'helper-field';
    wrap.append(`${text} `, control);
    return wrap;
}

/** A checkbox, defaulting on or off. */
function checkbox(id, checked) {
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.id = id;
    box.checked = checked;
    return box;
}

/** Whether the seat may even attempt this tile now (own turn, bar exceptions). */
function canActOffTurn(tile) {
    // Resource compensation and protection from the 7 fire on any player's roll;
    // everything else is own-turn only. The server has the final say either way.
    if (tile.when === 'after_production' || tile.when === 'on_seven') {
        return true;
    }
    return isMyTurn();
}

/** A five-way resource dropdown, defaulting to wood. */
function resourcePicker(id) {
    const select = document.createElement('select');
    select.className = 'helper-resource';
    select.id = id;
    RESOURCES.forEach(resource => {
        const option = document.createElement('option');
        option.value = resource;
        option.textContent = resource;
        select.appendChild(option);
    });
    return select;
}

/** A dropdown of the other seats, or null when there are none. */
function playerPicker(id) {
    const me = viewState.identity.name;
    const others = ((getBoard().players || []).map(p => p.name)).filter(name => name !== me);
    if (!others.length) {
        return null;
    }
    const select = document.createElement('select');
    select.className = 'helper-player';
    select.id = id;
    others.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        select.appendChild(option);
    });
    return select;
}

/** The display: the tiles a player could exchange into, named. */
function renderDisplay(state) {
    const box = el('helper-display');
    if (!box) {
        return;
    }
    box.textContent = '';
    const pile = state.pile || [];
    const label = document.createElement('div');
    label.className = 'helper-display-label';
    label.textContent = pile.length
        ? `Display: ${pile.map(id => (state.catalogue[id] || {}).name || id).join(', ')}`
        : 'Display empty';
    box.appendChild(label);
}
