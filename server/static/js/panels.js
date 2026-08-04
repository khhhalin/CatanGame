// The game console and the panels around the board: whose turn it is, the
// player's own hand, the bank, development cards, and the two dialogs a roll
// of seven opens.

import { ckEnabled, isCkMode, shortfallReason, syncCkModeButtons } from './cities-knights.js';
import { COMMODITY_ICONS, COMMODITY_TYPES, RESOURCE_ICONS } from './constants.js';
import { activeRulesChipValue, awardSummary, bankChipValue, bankDisplay, buyDevCardBtn, colorPicker, devCardsChipValue, devDeckRemaining, discardAmountSpan, discardCommodityRow, discardHandNote, discardModal, endGameBtn, gameBoard, gameConsole, gamePlayersList, myDevCardsDiv, nextTurnBtn, placeRoadBtn, placeSettlementBtn, proposeTradeBtn, resourceDisplay, robberIndicator, rollDiceBtn, submitDiscardBtn, turnIndicator, upgradeCityBtn, victimList, victimModal } from './dom.js';
import { displayError } from './notices.js';
import { repositionPopover } from './popovers.js';
import { isSeaMode, seaRule, syncSeaModeButtons } from './seafarers.js';
import { emitGame } from './socket.js';
import { getBoard, getCurrentPlayer, getDiscardAmount, getGamePhase, getRobberVictims, getRole, hasRolledDice, isMyTurn, mustChooseVictim, mustMoveRobber, viewState } from './state.js';

// Mirrors server/data/costs.json. Duplicated here only to grey a button out and
// say why before the round trip - the server checks all of it again and the
// board is drawn from its answer, never from this.
// Everything a 7 counts, which is what a discard may name. The five resources
// and - on a table that plays them - the three commodities: the engine takes
// both (`clean_card_counts`), and a hand that is over the limit on commodities
// alone must be able to pay.
const DISCARDABLE_CARDS = ['wood', 'brick', 'sheep', 'wheat', 'ore', ...COMMODITY_TYPES];

const CARD_ICONS = { ...RESOURCE_ICONS, ...COMMODITY_ICONS };

const BUILD_COSTS = {
    settlement: { wood: 1, brick: 1, wheat: 1, sheep: 1 },
    road: { wood: 1, brick: 1 },
    city: { wheat: 2, ore: 3 },
    dev_card: { wheat: 1, sheep: 1, ore: 1 }
};

/**
 * Handle Next Turn button click
 */
nextTurnBtn.addEventListener('click', () => {
    if (!hasRolledDice()) {
        displayError('You must roll the dice before advancing to the next turn!');
        return;
    }
    emitGame('next_turn', { name: viewState.identity.name });
});

/**
 * Handle End Game button click.
 * This ends the match for the whole table and cannot be undone, so it is
 * gated behind a confirm - the only blocking prompt in the client.
 */
endGameBtn.addEventListener('click', () => {
    if (!window.confirm('End the game for everyone and return to the lobby?')) {
        return;
    }
    emitGame('end_game');
});

/**
 * Handle Roll Dice button click
 */
rollDiceBtn.addEventListener('click', () => {
    emitGame('roll_dice', { name: viewState.identity.name });
});

/**
 * Handle color picker change - emit set_color event
 */
colorPicker.addEventListener('change', () => {
    viewState.identity.color = colorPicker.value;
    emitGame('set_color', { name: viewState.identity.name, color: colorPicker.value });
});

/**
 * Handle Place Settlement button click - toggle settlement placement mode
 */
placeSettlementBtn.addEventListener('click', () => {
    // Don't allow manual toggle during setup phase
    if (getGamePhase() === 'setup') {
        return;
    }
    
    if (viewState.selectedBuilding === 'settlement') {
        // Deselect
        viewState.selectedBuilding = null;
        placeSettlementBtn.classList.remove('active');
        gameBoard.classList.remove('placement-mode');
    } else {
        // Select settlement
        viewState.selectedBuilding = 'settlement';
        placeSettlementBtn.classList.add('active');
        placeRoadBtn.classList.remove('active');
        upgradeCityBtn.classList.remove('active');
        gameBoard.classList.add('placement-mode');
    }
    // A Cities & Knights or Seafarers mode is a placement mode too: only one
    // may be armed
    syncCkModeButtons();
    syncSeaModeButtons();
});

/**
 * Handle Place Road button click - toggle road placement mode
 */
placeRoadBtn.addEventListener('click', () => {
    // Don't allow manual toggle during setup phase
    if (getGamePhase() === 'setup') {
        return;
    }
    
    if (viewState.selectedBuilding === 'road') {
        // Deselect
        viewState.selectedBuilding = null;
        placeRoadBtn.classList.remove('active');
        gameBoard.classList.remove('placement-mode');
    } else {
        // Select road
        viewState.selectedBuilding = 'road';
        placeRoadBtn.classList.add('active');
        placeSettlementBtn.classList.remove('active');
        upgradeCityBtn.classList.remove('active');
        gameBoard.classList.add('placement-mode');
    }
    // A Cities & Knights or Seafarers mode is a placement mode too: only one
    // may be armed
    syncCkModeButtons();
    syncSeaModeButtons();
});

/**
 * Handle Upgrade City button click - toggle city upgrade mode
 */
upgradeCityBtn.addEventListener('click', () => {
    // Don't allow during setup phase
    if (getGamePhase() === 'setup') {
        return;
    }
    
    if (viewState.selectedBuilding === 'city') {
        // Deselect
        viewState.selectedBuilding = null;
        upgradeCityBtn.classList.remove('active');
        gameBoard.classList.remove('placement-mode');
    } else {
        // Select city upgrade
        viewState.selectedBuilding = 'city';
        upgradeCityBtn.classList.add('active');
        placeSettlementBtn.classList.remove('active');
        placeRoadBtn.classList.remove('active');
        gameBoard.classList.add('placement-mode');
    }
    // A Cities & Knights or Seafarers mode is a placement mode too: only one
    // may be armed
    syncCkModeButtons();
    syncSeaModeButtons();
});

/**
 * Handle Buy Development Card button click
 */
buyDevCardBtn.addEventListener('click', () => {
    if (!getBoard()) {
        return;
    }
    
    if (getGamePhase() === 'setup') {
        displayError('Cannot buy development cards during setup');
        return;
    }
    
    if (mustMoveRobber()) {
        displayError('You must move the robber first');
        return;
    }
    
    if (!isMyTurn()) {
        displayError('It is not your turn');
        return;
    }
    
    emitGame('buy_dev_card', { name: viewState.identity.name });
});

/**
 * Render game sidebar (players only - no observers in game)
 */
export function renderGameSidebar(data) {
    gamePlayersList.innerHTML = '';

    // Handle both array of strings and array of player objects
    const players = data.players.map(p => typeof p === 'string' ? p : p.name);

    // Get longest road and largest army data from board
    const longestRoadHolder = getBoard()?.longest_road_holder || null;
    const largestArmyHolder = getBoard()?.largest_army_holder || null;
    const longestRoadLengths = getBoard()?.longest_road_length || {};
    const knightsPlayed = getBoard()?.knights_played || {};

    // Harbour points only exist when the table switched the rule on
    const harbormasterOn = getBoard()?.rules?.harbormaster === true;
    const harbormasterHolder = getBoard()?.harbormaster_holder || null;
    const harborPoints = getBoard()?.harbor_points || {};

    // Island points are already inside victory_points. They are broken out here
    // because a settlement that scores three points instead of one otherwise
    // looks like an arithmetic error on everyone else's scoreboard.
    const islandsOn = seaRule('island_victory_points');
    const islandPointsByPlayer = getBoard()?.island_points || {};

    players.forEach(name => {
        const li = document.createElement('li');
        
        // Get player data for points
        const playerData = getBoard()?.players?.find(p => p.name === name);
        const points = playerData?.victory_points || 0;
        
        // Get road length and knights played
        const roadLength = longestRoadLengths[name] || 0;
        const knights = knightsPlayed[name] || 0;
        
        // Add indicators for longest road and largest army
        const roadIndicator = name === longestRoadHolder ? ' 👑' : '';
        const armyIndicator = name === largestArmyHolder ? ' 🛡️' : '';

        // Same treatment as longest road / largest army, but only when on
        const harborIndicator = harbormasterOn && name === harbormasterHolder ? ' ⚓' : '';
        const harborSegment = harbormasterOn ? ` · Hb ${harborPoints[name] || 0}` : '';
        const islandSegment = islandsOn ? ` · 🏝️${islandPointsByPlayer[name] || 0}` : '';

        // Hands are hidden: the server sends counts only, for every player
        const resourceCount = playerData?.resource_count ?? 0;
        const devCardCount = playerData?.dev_card_count ?? 0;

        // Commodities are a second hand to keep track of, and they count
        // towards the discard limit, so they belong beside the card count
        const commoditySegment = ckEnabled()
            ? `, 🧺${playerData?.commodity_count ?? 0} com`
            : '';

        // Two lines rather than one long one: the name and the score are what
        // the eye goes to, and burying them in a run of abbreviations is what
        // made this list unreadable at rail width. Built rather than
        // interpolated - a player named with markup would otherwise be parsed
        // as HTML on everyone else's scoreboard.
        const head = document.createElement('div');
        head.className = 'score-head';

        const who = document.createElement('span');
        who.className = 'score-name';
        who.textContent = `${name}${roadIndicator}${armyIndicator}${harborIndicator}`;

        const score = document.createElement('span');
        score.className = 'score-points';
        score.textContent = `${points} pts`;

        head.appendChild(who);
        head.appendChild(score);

        const meta = document.createElement('div');
        meta.className = 'score-meta';
        meta.textContent = `Rd ${roadLength} · Kn ${knights}${harborSegment}${islandSegment}`
            + ` · 🎴${resourceCount}${commoditySegment} · 📜${devCardCount}`;

        li.appendChild(head);
        li.appendChild(meta);

        // Color each player with their own color
        if (playerData?.color) {
            li.style.backgroundColor = playerData.color;
            li.style.color = getContrastColor(playerData.color);
        }

        // Whose turn it is, as a ring rather than a border: a border width that
        // appears and disappears would resize the panel under the rest of the
        // rail on every turn change.
        if (name === getCurrentPlayer()) {
            li.classList.add('current-turn');
        }

        gamePlayersList.appendChild(li);
    });

    renderAwardSummary();
    renderTurnIndicator();
}

/**
 * Who currently holds each bonus, and on what.
 *
 * Longest Road and the Harbormaster were in the payload and nowhere on screen:
 * a player could take either one off someone without either of them being told.
 * Stated here in full - holder and the number that decides it - rather than as
 * a badge beside a name, because the interesting question is usually "who is
 * about to take it", which needs the runners-up too.
 */
function renderAwardSummary() {
    if (!awardSummary) {
        return;
    }

    const board = getBoard();
    if (!board) {
        awardSummary.textContent = '';
        return;
    }

    const roadLengths = board.longest_road_length || {};
    const knights = board.knights_played || {};
    const harborPoints = board.harbor_points || {};

    // The number that would take the bonus, whoever is holding it now
    const best = (scores) => Math.max(0, ...Object.values(scores).map(Number));

    // The threshold the engine is actually applying, never a copy of the base
    // game's number: a table that lowered the minimum to 2 was told "needs 5".
    const needs = (ruleId) => {
        const minimum = Number(board.rules?.[ruleId]);
        return Number.isFinite(minimum) ? `, needs ${minimum}` : '';
    };

    // Seafarers plays for the Longest Trade Route *instead of* the Longest
    // Road, and roads and ships both count toward it - so a route that was
    // mostly ships was being reported as "10 roads". The rulebook counts it in
    // segments (expansions.md 77-84).
    const tradeRoute = board.rules?.longest_trade_route === true;

    const rows = [
        {
            icon: '👑',
            name: tradeRoute ? 'Longest Trade Route' : 'Longest Road',
            holder: board.longest_road_holder,
            value: board.longest_road_holder
                ? `${roadLengths[board.longest_road_holder] || 0} `
                  + (tradeRoute ? 'segments' : 'roads')
                : `best ${best(roadLengths)}${needs('longest_road_minimum')}`
        },
        {
            icon: '🛡️',
            name: 'Largest Army',
            holder: board.largest_army_holder,
            value: board.largest_army_holder
                ? `${knights[board.largest_army_holder] || 0} knights`
                : `best ${best(knights)}${needs('largest_army_minimum')}`
        }
    ];

    // Only when the table switched the rule on: an award nobody is playing for
    // is noise on a panel that must stay short enough never to scroll.
    if (board.rules?.harbormaster === true) {
        rows.push({
            icon: '⚓',
            name: 'Harbormaster',
            holder: board.harbormaster_holder,
            value: board.harbormaster_holder
                ? `${harborPoints[board.harbormaster_holder] || 0} harbour pts`
                : `best ${best(harborPoints)}, needs 3`
        });
    }

    // The merchant is worth a victory point for as long as its owner keeps it,
    // and it changes hands the moment somebody else plays the card. Listed only
    // once one is on the board: an award nobody is playing for is a row this
    // panel cannot spare.
    if (board.merchant_holder) {
        rows.push({
            icon: '🏪',
            name: 'Merchant',
            holder: board.merchant_holder,
            value: '1 pt'
        });
    }

    const fragment = document.createDocumentFragment();
    rows.forEach(row => {
        const line = document.createElement('div');
        line.className = row.holder ? 'award-row held' : 'award-row';

        const label = document.createElement('span');
        label.className = 'award-name';
        label.textContent = `${row.icon} ${row.name}`;

        // Built rather than interpolated: a player named with markup would
        // otherwise be parsed as HTML on everyone else's scoreboard.
        const holder = document.createElement('span');
        holder.className = 'award-holder';
        holder.textContent = row.holder
            ? `${row.holder} · ${row.value}`
            : `unclaimed · ${row.value}`;

        line.appendChild(label);
        line.appendChild(holder);
        fragment.appendChild(line);
    });

    awardSummary.innerHTML = '';
    awardSummary.appendChild(fragment);
}

/**
 * Say whose turn it is in words, in the console beside the actions it gates.
 * "Waiting for Kalina…" on the Next Turn button was the only statement of it,
 * and it is the wrong place to look for the answer to "can I do anything".
 */
export function renderTurnIndicator() {
    if (!turnIndicator) {
        return;
    }
    const current = getCurrentPlayer();
    if (!current) {
        turnIndicator.textContent = '—';
        turnIndicator.className = 'turn-indicator';
        return;
    }
    const setup = getGamePhase() === 'setup' ? ' · setup' : '';
    turnIndicator.textContent = isMyTurn()
        ? `Your turn${setup}`
        : `${current}'s turn${setup}`;
    turnIndicator.className = isMyTurn() ? 'turn-indicator mine' : 'turn-indicator';
}

/**
 * Convert `#rrggbb` to [r, g, b], or null if it is not a hex colour.
 *
 * Player colours reach us from an `<input type="color">`, so they are always
 * this form in practice - but they arrive over the wire from another client,
 * and a caller must not have to trust that.
 *
 * @param {string} hexColor - A `#rrggbb` colour
 * @returns {number[]|null} - Channels 0-255, or null
 */
function parseHexColor(hexColor) {
    const match = /^#([0-9a-f]{6})$/i.exec(String(hexColor).trim());
    if (!match) {
        return null;
    }
    const value = parseInt(match[1], 16);
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

/**
 * WCAG relative luminance of an [r, g, b] triple.
 *
 * @param {number[]} rgb - Channels 0-255
 * @returns {number} - Luminance 0-1
 */
function relativeLuminance(rgb) {
    const [r, g, b] = rgb.map(channel => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * WCAG contrast ratio between two [r, g, b] triples, 1 to 21.
 *
 * @param {number[]} first - Channels 0-255
 * @param {number[]} second - Channels 0-255
 * @returns {number} - Ratio, order-independent
 */
function contrastRatio(first, second) {
    const light = Math.max(relativeLuminance(first), relativeLuminance(second));
    const dark = Math.min(relativeLuminance(first), relativeLuminance(second));
    return (light + 0.05) / (dark + 0.05);
}

/**
 * Black or white for text on `hexColor` - whichever a player can actually read.
 *
 * This used to threshold a YIQ brightness average at 0.5 and offer a navy
 * (#2c3e50) as its dark option. Both halves were wrong. YIQ approximates
 * perceived brightness, not WCAG contrast, so the threshold landed on the wrong
 * side for saturated hues; and the navy throws away four points of ratio for no
 * reason, because nothing is more readable on a light fill than black. Together
 * they put white on #e74c3c at 3.82:1 and the navy on #3498db at 3.48:1 - two
 * of the four shipped player colours failing AA on the scoreboard row and the
 * build buttons.
 *
 * Measuring both candidates and taking the winner is exact rather than
 * approximate, and it is the only approach that holds when the colour is
 * arbitrary: these come from a colour picker, so no palette audit can cover
 * them.
 *
 * @param {string} hexColor - Background colour, `#rrggbb`
 * @returns {string} - `#000000` or `#ffffff`
 */
function getContrastColor(hexColor) {
    const rgb = parseHexColor(hexColor);
    // White on an unreadable colour is no worse than the old behaviour, and a
    // malformed colour must not throw inside a render pass.
    if (!rgb) {
        return '#ffffff';
    }
    const onBlack = contrastRatio(rgb, [0, 0, 0]);
    const onWhite = contrastRatio(rgb, [255, 255, 255]);
    return onBlack >= onWhite ? '#000000' : '#ffffff';
}

/**
 * Find this socket's own player entry in the board data.
 * Only that entry carries populated `resources` and `dev_cards`; every other
 * player is sent as counts only.
 *
 * @returns {object|null} - Own player entry, or null (e.g. for observers)
 */
export function findMyPlayer() {
    const players = getBoard()?.players || [];
    return players.find(p => p.is_you) || players.find(p => p.name === viewState.identity.name) || null;
}

/**
 * Render resource panel - shows current user's resources
 */
export function renderResourcePanel() {
    if (!getBoard() || !getBoard().players) {
        return;
    }

    const player = findMyPlayer();
    if (!player) {
        return;
    }

    const resourceIcons = {
        wood: '🌲',
        brick: '🧱',
        sheep: '🐑',
        wheat: '🌾',
        ore: '🪨'
    };
    const resourceNames = {
        wood: 'Wood',
        brick: 'Brick',
        sheep: 'Sheep',
        wheat: 'Wheat',
        ore: 'Ore'
    };
    
    const resources = player.resources || {};
    
    const allResourceTypes = ['wood', 'brick', 'sheep', 'wheat', 'ore'];
    
    let html = '';
    for (const type of allResourceTypes) {
        const count = resources[type] || 0;
        html += `<div class="resource res-${type}">${resourceIcons[type]}${count}</div>`;
    }

    // Commodities sit in the same row as the resources: they are spent, traded
    // and discarded like them, and a separate box implied they were not.
    if (ckEnabled()) {
        const commodities = player.commodities || {};
        for (const type of COMMODITY_TYPES) {
            const count = commodities[type] || 0;
            html += `<div class="resource commodity com-${type}" title="${type}">`
                + `${COMMODITY_ICONS[type]}${count}</div>`;
        }
    }

    resourceDisplay.innerHTML = html;
}

/**
 * Render bank panel - shows bank resources as percentage
 */
export function renderBank() {
    if (!getBoard() || !getBoard().bank) {
        return;
    }
    
    const bank = getBoard().bank;
    const resourceIcons = {
        wood: '🌲',
        brick: '🧱',
        sheep: '🐑',
        wheat: '🌾',
        ore: '🪨'
    };
    const resourceNames = {
        wood: 'Wood',
        brick: 'Brick',
        sheep: 'Sheep',
        wheat: 'Wheat',
        ore: 'Ore'
    };
    
    const RESOURCE_LIMIT = 19;

    let html = '';
    for (const [type, count] of Object.entries(bank)) {
        const percentage = Math.round((count / RESOURCE_LIMIT) * 100 / 25) * 25;
        html += `<div class="bank-resource bank-${type}">${resourceIcons[type]}${percentage}%</div>`;
    }

    bankDisplay.innerHTML = html;

    // The one number worth reading without opening the panel: whether anything
    // has actually run out, because that is what changes what a trade is worth.
    if (bankChipValue) {
        const empty = Object.entries(bank)
            .filter(([, count]) => count === 0)
            .map(([type]) => RESOURCE_ICONS[type] || type);
        const total = Object.values(bank).reduce((sum, count) => sum + count, 0);
        bankChipValue.textContent = empty.length > 0
            ? `${total} cards · out: ${empty.join('')}`
            : `${total} cards`;
    }
}

/**
 * Render development cards panel - shows as buttons with conditional styling
 */
export function renderDevCards() {
    if (!getBoard()) {
        return;
    }
    
    renderDevDeckRemaining();

    const player = findMyPlayer();
    if (!player || !player.dev_cards) {
        myDevCardsDiv.innerHTML = '<div class="no-cards">No development cards</div>';
        renderDevCardsChip(0);
        return;
    }

    const cardIcons = {
        knight: '⚔️ Knight',
        two_roads: '🛤️ Two Roads',
        invention: '💡 Invention',
        monopoly: '💰 Monopoly',
        victory_point: '🏆 Victory'
    };
    
    const cardNames = {
        knight: 'knight',
        two_roads: 'two_roads',
        invention: 'invention',
        monopoly: 'monopoly',
        victory_point: 'victory_point'
    };
    
    const currentTurn = getBoard().turn_count !== undefined ? getBoard().turn_count : 0;
    const playerColor = player.color || '#3498db';
    
    let cardsHtml = '<div class="your-cards">Your Cards:</div>';
    const hasCards = Object.values(player.dev_cards).some(card => card.count > 0);
    
    if (!hasCards) {
        cardsHtml += '<div class="no-cards">No cards yet</div>';
    } else {
        for (const [cardType, cardData] of Object.entries(player.dev_cards)) {
            if (cardData.count > 0) {
                // Knight can be played without rolling dice (just needs turn delay)
                const needsDice = cardType !== 'knight';
                const cardCanPlay = isMyTurn() && 
                    (!needsDice || hasRolledDice()) &&
                    (cardData.purchase_turn === null || currentTurn - cardData.purchase_turn >= 1);
                
                const disabled = cardCanPlay ? '' : 'disabled';
                const btnClass = cardCanPlay ? 'dev-card-btn playable' : 'dev-card-btn';
                const style = cardCanPlay ? `background-color: ${playerColor};` : '';
                
                cardsHtml += `<button class="${btnClass}" data-card-type="${cardNames[cardType]}" ${disabled} style="${style}">${cardIcons[cardType]} (${cardData.count})</button>`;
            }
        }
    }
    
    myDevCardsDiv.innerHTML = cardsHtml;

    renderDevCardsChip(
        Object.values(player.dev_cards).reduce((total, card) => total + card.count, 0)
    );
}

/**
 * The folded summary: how many cards this player holds, and how many are left
 * to buy. Both are things a player checks constantly and neither is worth a
 * panel of its own.
 *
 * @param {number} held - Cards in this player's own hand
 */
function renderDevCardsChip(held) {
    if (!devCardsChipValue) {
        return;
    }
    const remaining = getBoard()?.dev_cards_remaining ?? 0;
    devCardsChipValue.textContent = `📜 ${held} held · ${remaining} in deck`;
}

/**
 * Show how many development cards are left in the deck.
 * The composition of the deck is hidden information - only the count is sent.
 */
function renderDevDeckRemaining() {
    if (!devDeckRemaining) {
        return;
    }
    const remaining = getBoard()?.dev_cards_remaining ?? 0;
    devDeckRemaining.textContent = `Deck: ${remaining} left`;
}

// One delegated listener - the card buttons are replaced on every server event
myDevCardsDiv.addEventListener('click', (event) => {
    const button = event.target.closest('[data-card-type]');
    if (!button || button.disabled) {
        return;
    }
    handlePlayDevCard(button.getAttribute('data-card-type'));
});

/**
 * Handle playing a development card
 */
function handlePlayDevCard(cardType) {
    if (!getBoard()) {
        return;
    }
    
    if (getGamePhase() === 'setup') {
        displayError('Cannot play development cards during setup');
        return;
    }
    
    if (mustMoveRobber()) {
        displayError('You must move the robber first');
        return;
    }
    
    if (!isMyTurn()) {
        displayError('It is not your turn');
        return;
    }
    
    // Check if player has this card
    const player = findMyPlayer();
    if (!player || !player.dev_cards || (player.dev_cards[cardType]?.count || 0) <= 0) {
        displayError('You do not have this card');
        return;
    }

    // No card-specific branching here by design: what a card does is the
    // server's ruling, and the client only names which one was played.
    emitGame('play_dev_card', { name: viewState.identity.name, card_type: cardType });
}

/**
 * Open the discard dialog for a fresh discard.
 * The inputs are zeroed here and nowhere else, so a board update that arrives
 * while the dialog is open cannot reset what has been typed into it.
 *
 * @param {number} amount - Cards the server says this player owes the bank
 */
export function openDiscardModal(amount) {
    discardAmountSpan.textContent = amount;
    DISCARDABLE_CARDS.forEach(card => {
        const input = document.getElementById(`discard-${card}`);
        if (input) {
            input.value = 0;
        }
    });

    // Only the tables that play commodities have any to hand back. Read off
    // the running game's rules rather than off "is this Cities & Knights":
    // commodities is a switch of its own and a table may take it alone.
    const commodities = getBoard()?.rules?.commodities === true;
    discardCommodityRow?.classList.toggle('hidden', !commodities);

    renderDiscardHand(commodities);
    discardModal.classList.add('show');
}

/**
 * Say what is in hand, in the dialog that is asking for some of it back.
 *
 * The dialog covers the hand panel, so without this the numbers have to be
 * typed from memory - and a player who guesses wrong is told only that the
 * total was wrong, never which card they do not have.
 *
 * @param {boolean} commodities - Whether the table plays commodities
 */
function renderDiscardHand(commodities) {
    if (!discardHandNote) {
        return;
    }
    const player = findMyPlayer();
    const held = { ...(player?.resources || {}) };
    if (commodities) {
        Object.assign(held, player?.commodities || {});
    }
    const parts = Object.entries(held)
        .filter(([, count]) => count > 0)
        .map(([card, count]) => `${count}${CARD_ICONS[card] || card}`);
    discardHandNote.textContent = parts.length > 0
        ? `In hand: ${parts.join(' ')}`
        : '';
}

/**
 * Update game UI based on phase (setup vs playing)
 */
export function updateGameUI(boardData) {
    const setupIndicator = document.getElementById('setup-indicator');
    const setupPlayerName = document.getElementById('setup-player-name');
    const setupActionText = document.getElementById('setup-action-text');
    const freeRoadsIndicator = document.getElementById('free-roads-indicator');
    const freeRoadsText = document.getElementById('free-roads-text');
    const rollDiceBtn = document.getElementById('roll-dice-btn');
    const placeSettlementBtn = document.getElementById('place-settlement-btn');
    const placeRoadBtn = document.getElementById('place-road-btn');
    const upgradeCityBtn = document.getElementById('upgrade-city-btn');
    const nextTurnBtn = document.getElementById('next-turn-btn');
    
    if (!boardData) return;
    
    const gamePhase = boardData.game_phase || 'playing';
    
    // Whose turn it is, whether the robber is pending and who owes the bank
    // cards are all read back out of this same payload where they are needed,
    // so nothing is copied out of it here.
    if (mustChooseVictim() && isMyTurn()) {
        offerVictimChoice();
    } else {
        autoVictimSent = false;
    }

    // The dialog's own visibility is the record of whether it has already been
    // opened for this discard - reopening it on every board update would wipe
    // the numbers the player is halfway through typing.
    const owedCards = getDiscardAmount();
    if (owedCards > 0 && !discardModal.classList.contains('show')) {
        openDiscardModal(owedCards);
    }
    
    // If must move robber, show a persistent hint - this runs on every board
    // update while the flag is set, so it must not be a popup
    if (robberIndicator) {
        if (mustMoveRobber() && isMyTurn()) {
            robberIndicator.classList.remove('hidden');
        } else {
            robberIndicator.classList.add('hidden');
        }
    }
    
    // Update free roads indicator
    const freeRoadsRemaining = boardData.free_roads_remaining || 0;
    if (freeRoadsRemaining > 0 && isMyTurn()) {
        freeRoadsIndicator.classList.remove('hidden');
        freeRoadsText.textContent = `Free Roads: ${freeRoadsRemaining} remaining`;
    } else {
        freeRoadsIndicator.classList.add('hidden');
    }
    
    if (gamePhase === 'setup') {
        // During setup, auto-select building type based on setup_action
        const setupAction = boardData.setup_action || 'settlement';
        
        if (isMyTurn()) {
            // Auto-select the required building type. A ship the player armed
            // themselves survives, because the rulebook lets one replace the
            // starting road beside a coastal settlement.
            viewState.selectedBuilding =
                (setupAction === 'road' && viewState.selectedBuilding === 'ship')
                    ? 'ship'
                    : setupAction;
            gameBoard.classList.add('placement-mode');
            
            // Update button states
            if (setupAction === 'settlement') {
                placeSettlementBtn.classList.add('active');
                placeRoadBtn.classList.remove('active');
                upgradeCityBtn.classList.remove('active');
            } else {
                placeRoadBtn.classList.add('active');
                placeSettlementBtn.classList.remove('active');
                upgradeCityBtn.classList.remove('active');
            }
        } else {
            // Not my turn - clear selection
            viewState.selectedBuilding = null;
            gameBoard.classList.remove('placement-mode');
            placeSettlementBtn.classList.remove('active');
            placeRoadBtn.classList.remove('active');
            upgradeCityBtn.classList.remove('active');
        }
        
        // Show setup indicator
        setupIndicator.classList.remove('hidden');
        
        // Get current player info
        const currentPlayerName = boardData.current_player || '';
        
        // The name inherits --on-status from the pill rather than wearing the
        // player's own colour. That colour is player-picked and the pill is a
        // saturated amber (--warn), which put the pair at 2.06:1 light and
        // 1.65:1 dark - the worst contrast on the screen, on the one line that
        // says whose turn it is during setup. Nothing readable can be promised
        // when both sides are fixed and one of them is arbitrary.
        setupPlayerName.textContent = currentPlayerName;

        const actionText = setupAction === 'road' ? 'placing road' : 'placing settlement';
        setupActionText.textContent = actionText;
    } else {
        // Normal play - restore button visibility and selection state.
        // A Cities & Knights mode is left armed: a knight move takes two taps
        // and someone else's trade landing between them would otherwise disarm
        // the board halfway through it.
        if (!isCkMode(viewState.selectedBuilding) && !isSeaMode(viewState.selectedBuilding)) {
            viewState.selectedBuilding = null;
            gameBoard.classList.remove('placement-mode');
        }
        placeSettlementBtn.classList.remove('active');
        placeRoadBtn.classList.remove('active');
        upgradeCityBtn.classList.remove('active');

        // Hide setup indicator
        setupIndicator.classList.add('hidden');
    }

    // Derive the dice button from board state rather than leaving it to
    // whichever event happened to fire. It used to be enabled only by
    // `game_started` and `turn_changed`; the setup-to-playing transition fires
    // neither, so the first player to act after setup could never roll and the
    // game simply stopped.
    rollDiceBtn.disabled = gamePhase === 'setup' || !isMyTurn() || hasRolledDice();
    if (!hasRolledDice()) {
        rollDiceBtn.textContent = 'Roll Dice';
    }

    updateAffordability();
    renderTurnIndicator();
    syncCkModeButtons();
    syncSeaModeButtons();

    // A payload can change how tall an open popover's contents are; it is
    // pinned in viewport coordinates, so it has to be re-pinned rather than
    // left hanging off the bottom of the screen.
    repositionPopover();
}

/**
 * Why an action cannot be taken right now, in one sentence, or ''.
 *
 * Every action in the client answers this question the same way and then greys
 * itself out with the answer in its `title`. The tester's complaint was that
 * half of them let you click and then showed an error instead - two different
 * languages for the same fact, and the clickable half wasted a round trip to
 * be told something the client already knew.
 *
 * @param {string} kind - Key into BUILD_COSTS
 * @returns {string} - Empty when the action is available
 */
function buildBlockReason(kind) {
    if (!getBoard()) {
        return 'No game is running';
    }
    const missing = missingFromThisTableReason(kind);
    if (missing) {
        return missing;
    }
    if (getGamePhase() === 'setup') {
        return 'Not during setup';
    }
    if (!isMyTurn()) {
        return `It is ${getCurrentPlayer()}'s turn`;
    }
    if (mustMoveRobber()) {
        return 'You must move the robber first';
    }
    if (getDiscardAmount() > 0) {
        return 'You must discard first';
    }
    return shortfallReason(findMyPlayer()?.resources, BUILD_COSTS[kind]);
}

/**
 * Why the table this player is at has no such action at all, or ''.
 *
 * Kept apart from the turn and cost checks because a house rule does not stand
 * down during setup the way they do: progress cards replace the development
 * deck outright, and the server answers `buy_dev_card` with
 * DEV_CARDS_NOT_IN_PLAY for the whole game. The tester's report was being
 * offered the button and then refused by the server - the one pattern this
 * client has already agreed not to use.
 *
 * @param {string} kind - Key into BUILD_COSTS
 * @returns {string} - Empty when the table does play it
 */
function missingFromThisTableReason(kind) {
    if (kind === 'dev_card' && getBoard()?.rules?.progress_cards === true) {
        return 'This table uses progress cards, not development cards';
    }
    return '';
}

/**
 * Grey out every action the player cannot take, with the reason on hover.
 *
 * The setup phase is the one exception: the server dictates what goes down
 * next, `updateGameUI` arms the matching button for the player, and the pieces
 * are free - so a disabled build button there would be a lie.
 */
function updateAffordability() {
    const inSetup = getGamePhase() === 'setup';

    const gate = (button, kind, hint) => {
        if (!button) {
            return;
        }
        const missing = missingFromThisTableReason(kind);
        if (inSetup && !missing) {
            button.disabled = false;
            button.title = hint;
            return;
        }
        const reason = buildBlockReason(kind);
        button.disabled = Boolean(reason);
        button.title = reason || hint;
    };

    gate(placeSettlementBtn, 'settlement', 'Then tap an intersection on the board');
    gate(placeRoadBtn, 'road', 'Then tap an edge on the board');
    // A free road from Two Roads is paid for already, so the cost check has to
    // stand down for as long as the server says one is owed.
    if (!inSetup && (getBoard()?.free_roads_remaining || 0) > 0 && isMyTurn()) {
        placeRoadBtn.disabled = false;
        placeRoadBtn.title = 'Free road - then tap an edge on the board';
    }
    gate(upgradeCityBtn, 'city', 'Then tap one of your own settlements');
    gate(buyDevCardBtn, 'dev_card', `Costs ${formatBuildCost(BUILD_COSTS.dev_card)}`);
}

/**
 * Render a cost as "1🌾 1🐑 1🪨", the way the Cities & Knights buttons do.
 *
 * @param {object} cost - {resource: amount}
 * @returns {string}
 */
function formatBuildCost(cost) {
    return Object.entries(cost)
        .map(([resource, amount]) => `${amount}${RESOURCE_ICONS[resource] || resource}`)
        .join(' ');
}

/**
 * Update console visibility and button states based on current turn
 */
export function updateConsoleVisibility() {
    // Affordability first: updateButtonColors only paints a button it finds
    // enabled, so the disabled flags have to be settled before it runs.
    updateAffordability();
    updateButtonColors();
    renderTurnIndicator();

    // Greyed with the reason on it, not hidden. A control that vanishes and
    // comes back is the third language this client spoke for "you cannot do
    // that" - alongside greying out and erroring on click - and the tester's
    // complaint was that there were three.
    if (proposeTradeBtn) {
        const reason = getRole() === 'observer'
            ? 'Observers cannot trade'
            : (isMyTurn() ? '' : `It is ${getCurrentPlayer()}'s turn`);
        proposeTradeBtn.disabled = Boolean(reason);
        proposeTradeBtn.title = reason || 'Offer resources to the other players';
    }


    if (getRole() === 'observer') {
        gameConsole.classList.add('hidden');
    } else if (isMyTurn()) {
        gameConsole.classList.remove('hidden');
        nextTurnBtn.disabled = false;
        nextTurnBtn.textContent = `Next Turn`;
        colorPicker.style.display = 'inline-block';
        placeSettlementBtn.style.display = 'inline-block';
        placeRoadBtn.style.display = 'inline-block';
        upgradeCityBtn.style.display = 'inline-block';
    } else {
        gameConsole.classList.remove('hidden');
        nextTurnBtn.disabled = true;
        nextTurnBtn.textContent = `Waiting for ${getCurrentPlayer()}...`;
        colorPicker.style.display = 'inline-block';
        placeSettlementBtn.style.display = 'inline-block';
        placeRoadBtn.style.display = 'inline-block';
        upgradeCityBtn.style.display = 'inline-block';
    }
    
    // Reset building selection when turn changes
    viewState.selectedBuilding = null;
    placeSettlementBtn.classList.remove('active');
    placeRoadBtn.classList.remove('active');
    upgradeCityBtn.classList.remove('active');
    viewState.shipMoveFrom = null;
    gameBoard.classList.remove('placement-mode');
    syncCkModeButtons();
    syncSeaModeButtons();
}

/**
 * Paint the available actions in the current user's colour.
 *
 * The colour is only ever used as a *fill*, with getContrastColor picking the
 * ink. It used to tint the page heading as text too, which is the one thing an
 * arbitrary player colour cannot safely do: #3498db on --bg is 2.78:1, below
 * even the large-text threshold, and there is no ink to choose because the
 * player's colour *is* the foreground. Identity is carried by the scoreboard
 * row and the pieces on the board, both of which are fills.
 */
export function updateButtonColors() {
    const buttons = [rollDiceBtn, placeSettlementBtn, placeRoadBtn, upgradeCityBtn, nextTurnBtn];
    const currentUserData = getBoard()?.players?.find(p => p.name === viewState.identity.name);
    const playerColor = currentUserData?.color || '#e67e22';

    // Only an *available* action wears the player's colour. Anything else has
    // its inline paint removed so the stylesheet's disabled treatment applies:
    // the old code inlined #7f8c8d with white text, which is 2.9:1 and fails
    // AA, and an inline colour beats every rule a theme can write.
    buttons.forEach(btn => {
        if (isMyTurn() && !btn.disabled) {
            btn.style.backgroundColor = playerColor;
            btn.style.color = getContrastColor(playerColor);
        } else {
            btn.style.backgroundColor = '';
            btn.style.color = '';
        }
    });
}

// Whether the single-candidate answer has already gone. Reset by updateGameUI
// as soon as the server says nothing is pending.
let autoVictimSent = false;

/**
 * Ask who to rob - but only when there is actually a question.
 *
 * A dialog offering one button is not a choice, it is a click the player has to
 * make to carry on. With a single candidate the answer is settled here and the
 * modal never opens.
 */
export function offerVictimChoice() {
    const victims = getRobberVictims();

    if (victims.length === 1) {
        // This runs on every board payload while the flag is up, and the flag
        // stays up until the server has answered, so the send is latched. It is
        // cleared again the moment nothing is pending.
        if (!autoVictimSent) {
            autoVictimSent = true;
            emitGame('choose_robber_victim', { name: viewState.identity.name, victim: victims[0] });
        }
        victimModal.classList.remove('show');
        return;
    }

    if (victims.length === 0) {
        // Nothing to steal. The dialog has no way to close itself, so opening
        // it would strand the turn.
        victimModal.classList.remove('show');
        return;
    }

    renderVictimList();
    victimModal.classList.add('show');
}

export function renderVictimList() {
    victimList.innerHTML = '';
    
    const players = getBoard()?.players || [];
    
    getRobberVictims().forEach(victimName => {
        const player = players.find(p => p.name === victimName);
        const color = player?.color || '#cccccc';
        
        const item = document.createElement('div');
        item.className = 'victim-item';
        item.dataset.victim = victimName;

        // Built rather than interpolated: a player named with markup would
        // otherwise be parsed as HTML in everyone else's robber dialog.
        const swatch = document.createElement('div');
        swatch.className = 'victim-color';
        swatch.style.backgroundColor = color;
        item.appendChild(swatch);
        item.appendChild(document.createTextNode(victimName));

        victimList.appendChild(item);
    });
}

// One delegated listener - the victim list is rebuilt on every robber move
victimList.addEventListener('click', (event) => {
    const item = event.target.closest('[data-victim]');
    if (!item) {
        return;
    }
    emitGame('choose_robber_victim', { name: viewState.identity.name, victim: item.dataset.victim });
    victimModal.classList.remove('show');
});

submitDiscardBtn.addEventListener('click', () => {
    // Every card the limit counts, not the five resources: a commodity typed
    // into a row the submit ignored was the shape of the tester's report.
    const resources = {};
    DISCARDABLE_CARDS.forEach(card => {
        const input = document.getElementById(`discard-${card}`);
        resources[card] = input ? (parseInt(input.value) || 0) : 0;
    });

    const total = Object.values(resources).reduce((sum, count) => sum + count, 0);

    if (total !== getDiscardAmount()) {
        displayError(`You must discard exactly ${getDiscardAmount()} cards`);
        return;
    }
    
    emitGame('discard_resources', { name: viewState.identity.name, resources: resources });
});
