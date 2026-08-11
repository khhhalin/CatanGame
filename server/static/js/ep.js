// Explorers & Pirates panel: the mission tracks and their lead cards, the token
// supplies, and each player's gold and village advantages, all read from
// `board.ep`. Mirrors cities-knights.js — one render, called on every board
// update, that hides the whole panel on a table not playing the expansion.

import { epBuildShipBtn, epMissions, epMoveShipBtn, epPanel, epPlayers, epRollFishBtn, epSupply } from './dom.js';
import { findMyPlayer } from './player-view.js';
import { armShipMode, formatCost, SHIP_COST, turnBlockReason } from './seafarers.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

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
epRollFishBtn?.addEventListener('click', () => {
    emitGame('roll_fish_haul', { name: viewState.identity.name });
});
