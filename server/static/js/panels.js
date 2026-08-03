// The game console and the panels around the board: whose turn it is, the
// player's own hand, the bank, development cards, and the two dialogs a roll
// of seven opens.

import { ckEnabled, isCkMode, syncCkModeButtons } from './cities-knights.js';
import { COMMODITY_ICONS, COMMODITY_TYPES } from './constants.js';
import { bankDisplay, buyDevCardBtn, colorPicker, devDeckRemaining, discardAmountSpan, discardModal, endGameBtn, gameBoard, gameConsole, gamePlayersList, gameTitle, myDevCardsDiv, nextTurnBtn, placeRoadBtn, placeSettlementBtn, proposeTradeBtn, resourceDisplay, robberIndicator, rollDiceBtn, submitDiscardBtn, upgradeCityBtn, victimList, victimModal } from './dom.js';
import { displayError } from './notices.js';
import { emitGame } from './socket.js';
import { getBoard, getCurrentPlayer, getDiscardAmount, getGamePhase, getRobberVictims, getRole, hasRolledDice, isMyTurn, mustChooseVictim, mustMoveRobber, viewState } from './state.js';

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
    // A Cities & Knights mode is a placement mode too: only one may be armed
    syncCkModeButtons();
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
    // A Cities & Knights mode is a placement mode too: only one may be armed
    syncCkModeButtons();
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
    // A Cities & Knights mode is a placement mode too: only one may be armed
    syncCkModeButtons();
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
        const harborIndicator = name === harbormasterHolder ? ' ⚓' : '';
        const harborSegment = harbormasterOn
            ? ` Hb:${harborPoints[name] || 0}${harborIndicator}`
            : '';

        // Hands are hidden: the server sends counts only, for every player
        const resourceCount = playerData?.resource_count ?? 0;
        const devCardCount = playerData?.dev_card_count ?? 0;

        // Commodities are a second hand to keep track of, and they count
        // towards the discard limit, so they belong beside the card count
        const commoditySegment = ckEnabled()
            ? `, 🧺${playerData?.commodity_count ?? 0} com`
            : '';

        li.textContent = `${name} (${points} pts) | Rd:${roadLength}${roadIndicator} Kn:${knights}${armyIndicator}${harborSegment} | 🎴${resourceCount} cards${commoditySegment}, 📜${devCardCount} dev`;
        
        // Color each player with their own color
        if (playerData?.color) {
            li.style.backgroundColor = playerData.color;
            li.style.color = getContrastColor(playerData.color);
        }
        
        // Highlight current player with border
        if (name === getCurrentPlayer()) {
            li.classList.add('current-turn');
            li.style.border = '3px solid white';
            li.style.boxShadow = '0 0 10px rgba(255,255,255,0.5)';
        }
        
        gamePlayersList.appendChild(li);
    });
}

/**
 * Get contrasting text color (black or white) based on background color
 */
function getContrastColor(hexColor) {
    const r = parseInt(hexColor.slice(1, 3), 16);
    const g = parseInt(hexColor.slice(3, 5), 16);
    const b = parseInt(hexColor.slice(5, 7), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.5 ? '#2c3e50' : '#ffffff';
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

    // TODO: Implement card-specific logic
    console.log('Playing development card:', cardType);
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
    ['wood', 'brick', 'sheep', 'wheat', 'ore'].forEach(resource => {
        document.getElementById(`discard-${resource}`).value = 0;
    });
    discardModal.classList.add('show');
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
        renderVictimList();
        victimModal.classList.add('show');
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
            // Auto-select the required building type
            viewState.selectedBuilding = setupAction;
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
        
        // Find player color
        const player = boardData.players?.find(p => p.name === currentPlayerName);
        const playerColor = player?.color || '#e74c3c';
        
        setupPlayerName.textContent = currentPlayerName;
        setupPlayerName.style.color = playerColor;
        
        const actionText = setupAction === 'road' ? 'placing road' : 'placing settlement';
        setupActionText.textContent = actionText;
    } else {
        // Normal play - restore button visibility and selection state.
        // A Cities & Knights mode is left armed: a knight move takes two taps
        // and someone else's trade landing between them would otherwise disarm
        // the board halfway through it.
        if (!isCkMode(viewState.selectedBuilding)) {
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

    syncCkModeButtons();
}

/**
 * Update console visibility and button states based on current turn
 */
export function updateConsoleVisibility() {
    // Update button colors based on current player
    updateButtonColors();
    
    // Show/hide trade button based on turn
    if (getRole() !== 'observer' && isMyTurn()) {
        proposeTradeBtn.style.display = 'inline-block';
    } else {
        proposeTradeBtn.style.display = 'none';
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
    gameBoard.classList.remove('placement-mode');
    syncCkModeButtons();
}

/**
 * Update button colors and title based on current user
 */
export function updateButtonColors() {
    const buttons = [rollDiceBtn, placeSettlementBtn, placeRoadBtn, upgradeCityBtn, nextTurnBtn];
    const currentUserData = getBoard()?.players?.find(p => p.name === viewState.identity.name);
    const playerColor = currentUserData?.color || '#e67e22';
    const textColor = getContrastColor(playerColor);
    
    // Use player's color only when it's their turn, otherwise use default
    const activeColor = isMyTurn() ? playerColor : '#7f8c8d';
    const activeTextColor = isMyTurn() ? textColor : '#ffffff';
    
    buttons.forEach(btn => {
        btn.style.backgroundColor = activeColor;
        btn.style.color = activeTextColor;
    });
    
    // Update title color
    if (gameTitle) {
        gameTitle.style.color = playerColor;
    }
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
    const resources = {
        wood: parseInt(document.getElementById('discard-wood').value) || 0,
        brick: parseInt(document.getElementById('discard-brick').value) || 0,
        sheep: parseInt(document.getElementById('discard-sheep').value) || 0,
        wheat: parseInt(document.getElementById('discard-wheat').value) || 0,
        ore: parseInt(document.getElementById('discard-ore').value) || 0
    };
    
    const total = resources.wood + resources.brick + resources.sheep + resources.wheat + resources.ore;
    
    if (total !== getDiscardAmount()) {
        displayError(`You must discard exactly ${getDiscardAmount()} cards`);
        return;
    }
    
    emitGame('discard_resources', { name: viewState.identity.name, resources: resources });
});
