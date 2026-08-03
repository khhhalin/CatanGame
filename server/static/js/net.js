// Everything the server says, in one place.
//
// A handler here validates the payload, hands it to the store, and asks the
// panels to redraw. Nothing else in the client registers a socket listener, so
// the full set of server events is this file's table of contents.

import { markDirty, setHighlight } from './board.js';
import { renderCitiesKnights } from './cities-knights.js';
import { colorPicker, diceDisplay, discardModal, gameScreen, rollDiceBtn, turnSound, userScreen, victimModal } from './dom.js';
import { appendLogEntries, checkLogGap, requestLogCatchUp, updateChatAvailability } from './event-log.js';
import { handleNameTaken, renderActiveRules, renderRulesPanel, renderUserList, returnToLobby, updateStartButton } from './lobby.js';
import { displayError, logToGameConsole, showNotice } from './notices.js';
import { openDiscardModal, renderBank, renderDevCards, renderGameSidebar, renderResourcePanel, renderVictimList, updateButtonColors, updateConsoleVisibility, updateGameUI } from './panels.js';
import { setConnectionStatus, socket, socketAvailable } from './socket.js';
import { applyBoardFacts, getBoard, getCurrentPlayer, getRole, isMyTurn, setRoster, viewState } from './state.js';
import { startTimerInterval, updateTimers } from './timers.js';
import { renderTradeOffers, showInventionModal, showMonopolyModal } from './trade.js';

// Socket event handlers

socket.on('rules_changed', (data) => {
    if (!data || !Array.isArray(data.catalogue) || typeof data.selected !== 'object') {
        console.warn('Ignoring malformed rules_changed payload:', data);
        return;
    }

    viewState.server.rules.catalogue = data.catalogue;
    viewState.server.rules.selected = data.selected || {};
    viewState.server.rules.locked = data.locked === true;
    renderRulesPanel();
    renderActiveRules();
});

socket.on('user_list', (data) => {
    setRoster(data.players, data.observers, data.min_players);
    renderUserList();
    updateStartButton();
});

socket.on('game_started', (data) => {
    // The board payload is what every later question is answered from, so it
    // goes in before anything renders. The roster decides whether this tab is
    // playing or watching - the server seats people, the client does not.
    viewState.server.board = data.board;
    viewState.winnerAnnounced = false;
    setRoster(data.players, data.observers);
    userScreen.classList.add('hidden');
    gameScreen.classList.remove('hidden');
    setHighlight(null);

    renderGameSidebar({ players: data.board.players });
    updateConsoleVisibility();
    
    // Set color picker to current user's color
    const currentPlayerData = data.board?.players?.find(p => p.name === viewState.identity.name);
    if (currentPlayerData?.color) {
        colorPicker.value = currentPlayerData.color;
    }
    
    // Render resource panel
    renderResourcePanel();
    
    // Render bank
    renderBank();
    
    // Update UI based on game phase
    updateGameUI(data.board);
    
    // Update button colors
    updateButtonColors();
    
    // Update timers
    updateTimers(data.board);
    
    // Enable dice button for the first player
    if (isMyTurn()) {
        rollDiceBtn.disabled = false;
        rollDiceBtn.textContent = 'Roll Dice';
        diceDisplay.innerHTML = '';
    }
    
    // Render dev cards
    renderDevCards();

    // Commodities, improvements, knights and the barbarian clock - or nothing
    // at all, in a base game
    renderCitiesKnights();

    // Show what the table agreed to before the game began
    renderActiveRules();

    console.log('Game started! Player order:', data.players);
    console.log('Current player:', data.current_player);
});

socket.on('game_state', (data) => {
    // The server answers every join with a snapshot, including "no game is
    // running" so a client that reconnects in the lobby is not left blank.
    // That snapshot used to be read as "a game started", because a local flag
    // was set from the arrival of the message rather than from what it said,
    // and nothing ever put it back - the lobby stayed wedged with the Start
    // Game button hidden. There is no such flag to get wrong now: no board
    // payload is what "no game" means.
    if (!data.in_game) {
        viewState.server.board = null;
        viewState.winnerAnnounced = false;
        gameScreen.classList.add('hidden');
        userScreen.classList.remove('hidden');
        updateStartButton();
        return;
    }

    viewState.server.board = data.board;
    viewState.winnerAnnounced = false;
    setRoster(data.players, data.observers);
    userScreen.classList.add('hidden');
    gameScreen.classList.remove('hidden');
    renderGameSidebar({ players: data.players });
    updateConsoleVisibility();

    if (data.board) {
        setHighlight(null);
        renderResourcePanel();
        renderBank();
        renderDevCards();
        renderActiveRules();
        renderCitiesKnights();
    }

    // Set color picker to current user's color
    const currentPlayerData = data.board?.players?.find(p => p.name === viewState.identity.name);
    if (currentPlayerData?.color) {
        colorPicker.value = currentPlayerData.color;
    }
    
    // Update button colors
    updateButtonColors();
    checkLogGap(data);

    console.log('Reconnected to game. Current player:', data.current_player);
});

socket.on('turn_changed', (data) => {
    const wasMyTurn = isMyTurn();
    // This lands a fraction of a second before the board broadcast that
    // repeats the same two facts. Folding them into the stored payload keeps
    // one answer to "whose turn is it" instead of opening a second one.
    applyBoardFacts({
        current_player: data.current_player,
        has_rolled_dice: data.has_rolled_dice === true
    });
    setRoster(data.players, data.observers);
    renderGameSidebar({ players: data.players });
    updateConsoleVisibility();
    renderResourcePanel();
    // Whose turn it is decides what every Cities & Knights button says
    renderCitiesKnights();
    console.log('Turn changed. Current player:', data.current_player);

    // Update timers from server data
    if (data.dice_roll_time !== undefined) {
        viewState.timers.diceSeconds = data.dice_roll_time;
        viewState.timers.roundSeconds = data.round_time;
        viewState.timers.updatedAt = Date.now();
        startTimerInterval();
    }
    
    // Play sound if it's now my turn
    if (isMyTurn() && !wasMyTurn) {
        turnSound.play().catch(e => console.log('Could not play sound:', e));
    }
    
    // Enable dice button for the current player
    if (isMyTurn()) {
        rollDiceBtn.disabled = false;
        rollDiceBtn.textContent = 'Roll Dice';
        diceDisplay.innerHTML = '';
    }
});

socket.on('player_color_changed', (data) => {
    console.log(`Player ${data.name} changed color to ${data.color}`);
    if (data.name === viewState.identity.name) {
        colorPicker.value = data.color;
    }
    // Update the player's colour in the stored board before re-rendering
    if (getBoard() && getBoard().players) {
        for (const player of getBoard().players) {
            if (player.name === data.name) {
                player.color = data.color;
                break;
            }
        }
    }
    // Re-render board with updated player colors
    markDirty();
    // Update buttons and sidebar with new color
    updateButtonColors();
    if (getCurrentPlayer()) {
        renderGameSidebar({ players: getBoard()?.players?.map(p => p.name) || [] });
    }
});

socket.on('dice_rolled', (data) => {
    console.log(`Player ${data.player} rolled ${data.dice1} + ${data.dice2} = ${data.total}`);
    diceDisplay.innerHTML = `<span class="die">${data.dice1}</span><span class="die">${data.dice2}</span>`;
    rollDiceBtn.disabled = true;
    rollDiceBtn.textContent = `Rolled: ${data.total}`;
    
    // Highlight hexes matching the rolled number
    setHighlight(data.total);

    // Clear highlight after 2 seconds
    setTimeout(() => setHighlight(null), 2000);
});

socket.on('board_updated', (data) => {
    console.log('Board updated');
    viewState.server.board = data.board;
    setHighlight(data.highlight || null);
    renderResourcePanel();
    renderBank();
    renderTradeOffers();
    renderDevCards();
    updateGameUI(data.board);
    updateButtonColors();
    updateTimers(data.board);
    renderActiveRules();
    renderCitiesKnights();
    checkLogGap(data);

    // Clear highlight after 2 seconds if there was one
    if (data.highlight) {
        setTimeout(() => setHighlight(null), 2000);
    }
});

socket.on('dev_card_bought', (data) => {
    console.log('Development card bought:', data);
});

socket.on('dev_card_played', (data) => {
    console.log('Development card played:', data);
    if (data.card_type === 'invention' && data.needs_resources && data.player === viewState.identity.name) {
        showInventionModal();
    }
    if (data.card_type === 'monopoly' && data.needs_resource && data.player === viewState.identity.name) {
        showMonopolyModal();
    }
});

socket.on('game_won', (data) => {
    console.log('Game won:', data);
    showNotice(`🎉 GAME OVER! ${data.player} wins with ${data.victory_points} victory points!`, 'success', true);
    // A one-shot notice that no later payload repeats, so the win is latched
    // here - it is what stops the turn countdown.
    viewState.winnerAnnounced = true;
});

socket.on('game_ended', (data) => {
    // The server follows this with a fresh user_list and rules_changed, so the
    // lobby - including the rules panel - comes back unlocked on its own
    returnToLobby();
    showNotice(`Game ended by ${data?.by || 'a player'}.`, 'info');
});

socket.on('trade_proposed', (data) => {
    console.log('Trade proposed:', data.offer);
    if (getBoard() && getBoard().trades) {
        getBoard().trades.active.push(data.offer);
    }
    renderTradeOffers();
});

socket.on('trade_accepted', (data) => {
    console.log('Trade accepted:', data);
    renderTradeOffers();
});

socket.on('trade_declined', (data) => {
    console.log('Trade declined:', data);
    renderTradeOffers();
});

socket.on('trade_cancelled', (data) => {
    console.log('Trade cancelled:', data);
    renderTradeOffers();
});

socket.on('trade_completed', (data) => {
    console.log('Trade completed:', data);
    renderTradeOffers();
});

socket.on('discard_required', (data) => {
    console.log('Discard required:', data);
    if (data.player === viewState.identity.name) {
        openDiscardModal(data.amount);
    }
});

socket.on('discard_completed', (data) => {
    console.log('Discard completed:', data);
    if (data.player === viewState.identity.name) {
        discardModal.classList.remove('show');
    }
});

socket.on('choose_victim', (data) => {
    console.log('Choose victim event received:', data);

    if (isMyTurn()) {
        // Sent immediately before the board broadcast carrying the same two
        // fields, so fold it in rather than keeping a second copy.
        applyBoardFacts({
            must_choose_victim: true,
            robber_victims: data.victims || []
        });
        renderVictimList();
        victimModal.classList.remove('hidden');
        victimModal.classList.add('show');
    } else {
        console.log('Not current player, skipping modal');
    }
});

socket.on('resource_stolen', (data) => {
    console.log('Resource stolen:', data);
    if (data.victim === viewState.identity.name) {
        showNotice(`Player ${data.player} stole 1 ${data.resource} from you!`, 'info');
    } else {
        logToGameConsole(`Player ${data.player} stole 1 ${data.resource} from ${data.victim}`);
    }
});

socket.on('event_logged', (data) => {
    if (!data || typeof data !== 'object') {
        console.warn('Ignoring malformed event_logged payload:', data);
        return;
    }
    appendLogEntries([data.entry]);
});

socket.on('log_history', (data) => {
    if (!data || !Array.isArray(data.entries)) {
        console.warn('Ignoring malformed log_history payload:', data);
        return;
    }
    appendLogEntries(data.entries);
});

socket.on('error', (data) => {
    // `code` is machine-readable, `message` is what the player reads
    console.warn('Server rejected action:', data.code || 'UNKNOWN', data.message);

    if (data.code === 'NAME_TAKEN') {
        handleNameTaken(data.message);
        return;
    }

    displayError(data.message || 'The server rejected that action.');
});

// Connection lifecycle

socket.on('connect', () => {
    setConnectionStatus('connected', 'Connected');
    updateChatAvailability();
    if (viewState.identity.name) {
        // Re-join on every reconnect - the server replies with a full snapshot.
        // takeover: true because this IS the same player reclaiming their own
        // seat; the server may still be holding the dropped socket's binding.
        socket.emit('join', {
            name: viewState.identity.name, role: getRole(), color: viewState.identity.color, takeover: true
        });
        socket.emit('request_rules');
        // After the rejoin, so the socket is back in the lobby by the time the
        // server handles it. Only what we missed comes back.
        requestLogCatchUp();
    }
});

socket.on('disconnect', (reason) => {
    setConnectionStatus('offline', 'Disconnected - reconnecting…');
    updateChatAvailability();
    displayError('Connection lost. Trying to reconnect…');

    // Neither side reconnects automatically after an explicit disconnect
    if (reason === 'io server disconnect' || reason === 'io client disconnect') {
        setConnectionStatus('offline', 'Disconnected');
        socket.connect();
    }
});

socket.on('connect_error', (error) => {
    console.error('Socket connection error:', error);
    setConnectionStatus('offline', 'Connection problem - retrying…');
    updateChatAvailability();
});

if (!socketAvailable) {
    // The template's own onerror banner explains this one to the player
    console.error('Socket.IO library is unavailable - the client cannot connect.');
    setConnectionStatus('offline', 'Offline');
    document.getElementById('cdn-error')?.classList.remove('hidden');
} else {
    setConnectionStatus('connecting', 'Connecting…');
}
