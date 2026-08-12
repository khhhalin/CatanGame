// The Rivers of Catan panel: gold coins (this player's total, and who holds the
// Wealthiest / Poor Settler tiles), the coin buy/sell, and the Build bridge
// gesture. Read from `board` — coins live on each player, bridge sites on the
// board. Mirrors fish.js: one render on every board update that hides the whole
// panel on a table not playing the scenario.
//
// No rule logic lives here beyond erring permissive: the server checks the cost,
// the harbour rate, the connection and the per-player bridge cap, and its answer
// is what the board is drawn from.

import { gameBoard, placeRoadBtn, placeSettlementBtn, upgradeCityBtn } from './dom.js';
import { markDirty } from './board.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

// Which coin action's resource pick is open, or null.
let pickFor = null;

function el(id) {
    return document.getElementById(id);
}

/** Whether the table is playing any Rivers of Catan rule. */
function riversInPlay(board) {
    const rules = board?.rules || {};
    return Boolean(rules.gold_coins || rules.river_gold || rules.bridges
        || rules.wealthiest_settler || rules.poor_settler);
}

/** The sole player with the most coins, or null on a tie (Wealthiest Settler). */
function wealthiest(players) {
    const withCoins = players.filter(p => (p.gold || 0) > 0);
    if (!withCoins.length) {
        return null;
    }
    const top = Math.max(...players.map(p => p.gold || 0));
    const leaders = players.filter(p => (p.gold || 0) === top);
    return leaders.length === 1 ? leaders[0].name : null;
}

/** Everyone tied for the fewest coins, but only when someone has more (Poor
 * Settler); a level table puts no tile out. */
function poorest(players) {
    const totals = players.map(p => p.gold || 0);
    const fewest = Math.min(...totals);
    if (fewest === Math.max(...totals)) {
        return [];
    }
    return players.filter(p => (p.gold || 0) === fewest).map(p => p.name);
}

/**
 * Render the Rivers panel from the board, hidden whole on a table without the
 * scenario. Called on every board update.
 */
export function renderRivers() {
    const panel = el('right-rivers');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const show = riversInPlay(board);
    panel.classList.toggle('hidden', !show);
    if (!show) {
        return;
    }
    renderCoins(board);
    renderPlayers(board);
    renderActions(board);
    renderPick(board);
}

function renderCoins(board) {
    const coins = el('rivers-coins');
    coins.textContent = '';
    const me = (board.players || []).find(p => p.is_you);
    const mine = document.createElement('span');
    mine.className = 'ep-supply-item';
    mine.innerHTML = `Your coins <strong>${me?.gold || 0}</strong>`;
    coins.appendChild(mine);

    if (board.rules?.wealthiest_settler) {
        const name = wealthiest(board.players || []);
        const tile = document.createElement('span');
        tile.className = 'ep-supply-item';
        tile.innerHTML = `Wealthiest <strong>${name || '—'}</strong>`;
        coins.appendChild(tile);
    }
    if (board.rules?.poor_settler) {
        const names = poorest(board.players || []);
        const tile = document.createElement('span');
        tile.className = 'ep-supply-item';
        tile.innerHTML = `Poorest <strong>${names.length ? names.join(', ') : '—'}</strong>`;
        coins.appendChild(tile);
    }
}

function renderPlayers(board) {
    const list = el('rivers-players');
    list.textContent = '';
    for (const player of board.players || []) {
        if (!(player.gold > 0)) {
            continue;
        }
        const row = document.createElement('div');
        row.className = 'ep-player-row';
        row.textContent = `${player.name}: ${player.gold} gold`;
        list.appendChild(row);
    }
}

function renderActions(board) {
    const mine = isMyTurn();
    const me = (board.players || []).find(p => p.is_you);

    const bridgeBtn = el('rivers-build-bridge');
    if (bridgeBtn) {
        bridgeBtn.classList.toggle('hidden', board.rules?.bridges !== true);
        bridgeBtn.disabled = !mine;
        bridgeBtn.title = mine
            ? 'Then tap a river-crossing site to span it'
            : 'Not your turn';
        bridgeBtn.classList.toggle('active', viewState.selectedBuilding === 'bridge');
    }

    const canSpend = board.rules?.gold_coins === true;
    for (const id of ['rivers-sell-coin', 'rivers-buy-resource']) {
        const button = el(id);
        if (!button) {
            continue;
        }
        button.classList.toggle('hidden', !canSpend);
        button.disabled = !mine;
    }
    // Buying a resource needs 2 coins in hand.
    const buyBtn = el('rivers-buy-resource');
    if (buyBtn && canSpend) {
        buyBtn.disabled = !mine || (me?.gold || 0) < 2;
    }
    if (!mine) {
        closePick();
    }
    el('rivers-sell-coin')?.classList.toggle('active', pickFor === 'sell');
    el('rivers-buy-resource')?.classList.toggle('active', pickFor === 'buy');
}

function renderPick(board) {
    const pick = el('rivers-pick');
    pick.textContent = '';
    pick.classList.toggle('hidden', pickFor === null);
    if (pickFor === null) {
        return;
    }
    for (const resource of board.resource_types || []) {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'ep-action-btn fish-pick-opt';
        chip.dataset.resource = resource;
        chip.textContent = resource;
        chip.addEventListener('click', () => fireCoin(resource));
        pick.appendChild(chip);
    }
}

function closePick() {
    pickFor = null;
    const pick = el('rivers-pick');
    if (pick) {
        pick.classList.add('hidden');
        pick.textContent = '';
    }
}

function fireCoin(resource) {
    const event = pickFor === 'sell'
        ? 'sell_resources_for_coins'
        : 'buy_resource_with_coins';
    emitGame(event, { resource });
    closePick();
    renderRivers();
}

/** Arm (or disarm) the bridge gesture, clearing the other board build modes so
 * exactly one is ever selected. Then a tap on a bridge site builds it. */
function armBridgeMode() {
    viewState.selectedBuilding = viewState.selectedBuilding === 'bridge' ? null : 'bridge';
    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn]
        .forEach(button => button?.classList.remove('active'));
    gameBoard?.classList.toggle('placement-mode', Boolean(viewState.selectedBuilding));
    closePick();
    markDirty();
    renderRivers();
}

function togglePick(mode) {
    pickFor = pickFor === mode ? null : mode;
    renderRivers();
}

el('rivers-build-bridge')?.addEventListener('click', armBridgeMode);
el('rivers-sell-coin')?.addEventListener('click', () => togglePick('sell'));
el('rivers-buy-resource')?.addEventListener('click', () => togglePick('buy'));
