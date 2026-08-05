// The game console and the panels around the board: whose turn it is, the
// player's own hand, the bank, development cards, and the two dialogs a roll
// of seven opens.

import { isCkMode, shortfallReason, syncCkModeButtons } from './cities-knights.js';
import { COMMODITY_TYPES, RESOURCE_ICONS } from './constants.js';
import { getContrastColor } from './contrast.js';
import { renderDevCards } from './dev-cards.js';
import { activeRulesChipValue, buyDevCardBtn, colorPicker, discardAmountSpan, discardCommodityRow, discardModal, endGameBtn, gameBoard, gameConsole, nextTurnBtn, placeRoadBtn, placeSettlementBtn, proposeTradeBtn, robberIndicator, rollDiceBtn, submitDiscardBtn, upgradeCityBtn, victimList, victimModal } from './dom.js';
import { renderBank, renderDialogHands, renderResourcePanel } from './hand.js';
import { displayError } from './notices.js';
import { findMyPlayer } from './player-view.js';
import { repositionPopover } from './popovers.js';
import { renderGameSidebar, renderTurnIndicator } from './scoreboard.js';
import { isSeaMode, syncSeaModeButtons } from './seafarers.js';
import { emitGame } from './socket.js';
import { getBoard, getCurrentPlayer, getDiscardAmount, getGamePhase, getRobberVictims, getRole, hasRolledDice, isMyTurn, mustChooseVictim, mustMoveRobber, viewState } from './state.js';

// Names that used to be defined here and now live in their own modules. They
// are re-exported so this module's public surface is unchanged: net.js imports
// nine of them from here, and a browser test reaches renderGameSidebar through
// a dynamic `import('/static/js/panels.js')`. New callers should import from
// the owning module.
export { renderDevCards };
export { findMyPlayer };
export { renderBank, renderDialogHands, renderResourcePanel };
export { renderGameSidebar, renderTurnIndicator };

// Everything a 7 counts, which is what a discard may name. The five resources
// and - on a table that plays them - the three commodities: the engine takes
// both (`clean_card_counts`), and a hand that is over the limit on commodities
// alone must be able to pay.
const DISCARDABLE_CARDS = ['wood', 'brick', 'sheep', 'wheat', 'ore', ...COMMODITY_TYPES];

// Mirrors server/data/costs.json. Duplicated here only to grey a button out and
// say why before the round trip - the server checks all of it again and the
// board is drawn from its answer, never from this.
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

    renderDialogHands();
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
