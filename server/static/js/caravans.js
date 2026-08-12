// The Caravans panel: how many camels are on the board, and the voting round
// when one is open. Read from `board.tb` — camels, caravan chains and the open
// vote all ride on the Traders & Barbarians state payload. Mirrors rivers.js:
// one render on every board update that hides the whole panel on a table not
// playing the scenario.
//
// The placement itself is a pending choice, drawn by choices.js like every other
// one — this panel is only the bid. No rule logic lives here beyond erring
// permissive: the server checks the hand, the votes and the legal paths, and its
// answer is what the board is drawn from.

import { emitGame } from './socket.js';
import { getBoard, viewState } from './state.js';

// This player's pending bid — wool and grain counts — reset when a new vote
// opens or theirs is submitted.
let bid = { sheep: 0, wheat: 0 };
let bidForVote = null;

function el(id) {
    return document.getElementById(id);
}

/** Whether the table is playing the Caravans. */
function caravansInPlay(board) {
    return Boolean(board?.rules?.caravans);
}

/**
 * Render the Caravans panel from the board, hidden whole on a table without the
 * scenario. Called on every board update.
 */
export function renderCaravans() {
    const panel = el('right-caravans');
    if (!panel) {
        return;
    }
    const board = getBoard();
    const show = caravansInPlay(board);
    panel.classList.toggle('hidden', !show);
    if (!show) {
        return;
    }
    renderStatus(board);
    renderVote(board);
}

function renderStatus(board) {
    const status = el('caravans-status');
    if (!status) {
        return;
    }
    const tb = board.tb || {};
    const camels = Object.keys(tb.camels || {}).length;
    const chains = (tb.caravans || []).length;
    status.textContent = '';
    const item = document.createElement('span');
    item.className = 'ep-supply-item';
    item.innerHTML = `Camels <strong>${camels}</strong>`;
    status.appendChild(item);
    const caravanItem = document.createElement('span');
    caravanItem.className = 'ep-supply-item';
    caravanItem.innerHTML = `Caravans <strong>${chains}</strong> / 3`;
    status.appendChild(caravanItem);
}

function renderVote(board) {
    const wrap = el('caravans-vote');
    if (!wrap) {
        return;
    }
    const vote = (board.tb || {}).camel_vote;
    wrap.classList.toggle('hidden', !vote);
    if (!vote) {
        bidForVote = null;
        return;
    }
    // A fresh vote resets any half-built bid from the last one.
    const signature = `${vote.finisher}|${(vote.pending || []).join(',')}`;
    if (bidForVote === null) {
        bidForVote = signature;
        bid = { sheep: 0, wheat: 0 };
    }

    wrap.textContent = '';
    const heading = document.createElement('div');
    heading.className = 'choice-hint';
    heading.textContent = 'A camel is being placed — bid wool and grain for a say.';
    wrap.appendChild(heading);

    // Each player's standing bid, so the table sees the votes as they come in.
    const tally = document.createElement('div');
    tally.className = 'ep-players';
    for (const player of board.players || []) {
        const cards = (vote.bids || {})[player.name];
        const row = document.createElement('div');
        row.className = 'ep-player-row';
        if (cards === undefined) {
            row.textContent = `${player.name}: yet to bid`;
        } else {
            row.textContent = `${player.name}: ${cards.length} vote(s)`;
        }
        tally.appendChild(row);
    }
    wrap.appendChild(tally);

    const me = viewState.identity.name;
    if ((vote.pending || []).includes(me)) {
        wrap.appendChild(bidForm(board));
    } else {
        const done = document.createElement('div');
        done.className = 'choice-hint';
        const waiting = (vote.pending || []);
        done.textContent = waiting.length
            ? `Waiting for ${waiting.join(', ')} to bid.`
            : 'Bids are in — placing the camel.';
        wrap.appendChild(done);
    }
}

/** The wool/grain steppers and the Bid / Pass buttons. */
function bidForm(board) {
    const me = (board.players || []).find(p => p.is_you) || {};
    const held = me.resources || {};
    const form = document.createElement('div');
    form.className = 'ep-actions';

    for (const resource of ['sheep', 'wheat']) {
        const label = resource === 'sheep' ? 'Wool' : 'Grain';
        const stepper = document.createElement('div');
        stepper.className = 'ep-supply-item';
        stepper.innerHTML = `${label}: <strong id="caravans-${resource}">${bid[resource]}</strong>`;

        const minus = document.createElement('button');
        minus.type = 'button';
        minus.className = 'ep-action-btn';
        minus.textContent = '−';
        minus.disabled = bid[resource] <= 0;
        minus.addEventListener('click', () => { bid[resource] -= 1; renderCaravans(); });

        const plus = document.createElement('button');
        plus.type = 'button';
        plus.className = 'ep-action-btn';
        plus.textContent = '+';
        plus.disabled = bid[resource] >= (held[resource] || 0);
        plus.addEventListener('click', () => { bid[resource] += 1; renderCaravans(); });

        stepper.appendChild(minus);
        stepper.appendChild(plus);
        form.appendChild(stepper);
    }

    const bidBtn = document.createElement('button');
    bidBtn.type = 'button';
    bidBtn.className = 'ep-action-btn';
    bidBtn.id = 'caravans-bid';
    bidBtn.textContent = 'Bid';
    bidBtn.disabled = bid.sheep + bid.wheat === 0;
    bidBtn.addEventListener('click', () => submitBid());
    form.appendChild(bidBtn);

    const passBtn = document.createElement('button');
    passBtn.type = 'button';
    passBtn.className = 'ep-action-btn';
    passBtn.id = 'caravans-pass';
    passBtn.textContent = 'Pass';
    passBtn.addEventListener('click', () => submitBid(true));
    form.appendChild(passBtn);

    return form;
}

function submitBid(pass = false) {
    const cards = [];
    if (!pass) {
        for (let i = 0; i < bid.sheep; i += 1) {
            cards.push('sheep');
        }
        for (let i = 0; i < bid.wheat; i += 1) {
            cards.push('wheat');
        }
    }
    emitGame('bid_camel', { cards });
    bid = { sheep: 0, wheat: 0 };
}
