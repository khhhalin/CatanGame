/**
 * Stand-in socket used when the Socket.IO library failed to load (blocked CDN).
 * Keeps the rest of the file free of null checks - every emit is refused and
 * reported through the same notice region as any other error.
 */
function createOfflineSocket() {
    return {
        connected: false,
        on: () => {},
        emit: () => {}
    };
}

const socketAvailable = typeof io === 'function';
const socket = socketAvailable ? io() : createOfflineSocket();

// Game state variables
let currentUser = null;
// Lobby size and the minimum needed to start, both from the server so the
// button can say what is missing rather than silently disappearing.
let lobbyPlayerCount = 0;
let minPlayersToStart = 2;
let currentRole = null;
let currentColor = null;
let gameStarted = false;
let currentPlayer = null;
// 'settlement', 'road', 'city', or - with Cities & Knights on - 'knight',
// 'knight_move' and 'city_wall'. All of them mean the same thing: the next tap
// on the board is an intent, not a pan.
let selectedBuilding = null;
// First half of a knight move. A move is two taps, so the origin has to
// survive between them.
let knightMoveFrom = null;
let mustMoveRobber = false;  // true when player must move robber after rolling 7
let hasRolledDice = false;

// DOM elements
const gameTitle = document.getElementById('game-title');

// DOM elements
const joinScreen = document.getElementById('join-screen');
const userScreen = document.getElementById('user-screen');
const gameScreen = document.getElementById('game-screen');
const usernameInput = document.getElementById('username');
const joinBtn = document.getElementById('join-btn');
const playerList = document.getElementById('players');
const observerList = document.getElementById('observers');
const playerCount = document.getElementById('player-count');
const rolePlayer = document.getElementById('role-player');
const roleObserver = document.getElementById('role-observer');
const joinColorPicker = document.getElementById('join-color-picker');
const startGameBtn = document.getElementById('start-game-btn');
const startReasonEl = document.getElementById('start-reason');
const rulesList = document.getElementById('rules-list');
const rulesLockedNote = document.getElementById('rules-locked-note');
const activeRulesPanel = document.getElementById('active-rules-panel');
const activeRulesDiv = document.getElementById('active-rules');
const gamePlayersList = document.getElementById('game-players');
const gameConsole = document.getElementById('game-console');
const gameBoard = document.getElementById('game-board');
const nextTurnBtn = document.getElementById('next-turn-btn');
const endGameBtn = document.getElementById('end-game-btn');
const colorPicker = document.getElementById('color-picker');
const placeSettlementBtn = document.getElementById('place-settlement-btn');
const placeRoadBtn = document.getElementById('place-road-btn');
const upgradeCityBtn = document.getElementById('upgrade-city-btn');
const rollDiceBtn = document.getElementById('roll-dice-btn');
const diceDisplay = document.getElementById('dice-display');
const resourceDisplay = document.getElementById('resource-display');
const bankDisplay = document.getElementById('bank-display');
const tradePanel = document.getElementById('trade-panel');
const proposeTradeBtn = document.getElementById('propose-trade-btn');
const tradeOffersDiv = document.getElementById('trade-offers');
const myOffersDiv = document.getElementById('my-offers');
const tradeModal = document.getElementById('trade-modal');
const closeTradeModal = document.getElementById('close-trade-modal');
const submitTradeBtn = document.getElementById('submit-trade-btn');
const diceTimerEl = document.getElementById('dice-timer');
const roundTimerEl = document.getElementById('round-timer');
const buyDevCardBtn = document.getElementById('buy-dev-card-btn');
const myDevCardsDiv = document.getElementById('my-dev-cards');
const inventionModal = document.getElementById('invention-modal');
const closeInventionModal = document.getElementById('close-invention-modal');
const confirmInventionBtn = document.getElementById('confirm-invention-btn');
const monopolyModal = document.getElementById('monopoly-modal');
const closeMonopolyModal = document.getElementById('close-monopoly-modal');

// Notice, connection status and inline hint elements
const noticeRegion = document.getElementById('notice-region');
const connectionStatus = document.getElementById('connection-status');
const robberIndicator = document.getElementById('robber-indicator');
const devDeckRemaining = document.getElementById('dev-deck-remaining');
const boardCanvas = document.getElementById('board-canvas');

// Cities & Knights. These panels exist in the template but stay hidden unless
// the running game has the expansion switched on.
const barbarianPanel = document.getElementById('barbarian-panel');
const barbarianTrack = document.getElementById('barbarian-track');
const barbarianStatus = document.getElementById('barbarian-status');
const barbarianDefense = document.getElementById('barbarian-defense');
const improvementsPanel = document.getElementById('improvements-panel');
const improvementTracks = document.getElementById('improvement-tracks');
const knightsPanel = document.getElementById('knights-panel');
const knightList = document.getElementById('knight-list');
const knightHint = document.getElementById('knight-hint');
const buildKnightBtn = document.getElementById('build-knight-btn');
const moveKnightBtn = document.getElementById('move-knight-btn');
const buildWallBtn = document.getElementById('build-wall-btn');

// Discard and victim modal elements
const discardModal = document.getElementById('discard-modal');
const victimModal = document.getElementById('victim-modal');
const victimList = document.getElementById('victim-list');
const submitDiscardBtn = document.getElementById('submit-discard-btn');
const discardAmountSpan = document.getElementById('discard-amount');

// Side panel tabs - the log and the trade panel share one box
const sideTabs = document.getElementById('side-tabs');
const logTabBtn = document.getElementById('tab-log');
const tradeTabBtn = document.getElementById('tab-trade');
const tradeTabBadge = document.getElementById('trade-tab-badge');
const logTabBadge = document.getElementById('log-tab-badge');

// Chat and event log elements
const logEntriesDiv = document.getElementById('log-entries');
const logJumpBtn = document.getElementById('log-jump-btn');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');

// Turn sound - preload
const turnSound = new Audio('/static/audio/turn.wav');
turnSound.preload = 'auto';

// Timer tracking
let lastDiceTime = 15;
let lastRoundTime = 120;
let lastUpdateTime = Date.now();
let diceTimerInterval = null;

// Store current board data for click handling
let currentBoardData = null;

// The lobby rule set, exactly as the server last broadcast it. The client
// never writes to `selected` itself - a change is emitted and re-read from
// the `rules_changed` reply, so every table member sees the same thing.
let rulesCatalogue = [];
let rulesSelected = {};
let rulesLocked = false;
let renderedRulesSignature = '';

// Discard and victim selection state
let mustDiscard = false;
let discardAmount = 0;
let mustChooseVictim = false;
let robberVictims = [];

// Render loop state - socket handlers set state and mark dirty, never draw
let renderDirty = false;
let highlightNumber = null;

// Event log state. `highestLogId` is what a reconnecting client asks to catch
// up from, and it is also how a duplicate entry is recognised and dropped.
let highestLogId = 0;

const NOTICE_TIMEOUT_MS = 6000;

/**
 * Show a non-blocking notice in the live region.
 * This is the only error/notification surface in the client - nothing here
 * blocks the render loop or covers the board.
 *
 * @param {string} message - Human-readable text to show
 * @param {string} level - 'error', 'info' or 'success'
 * @param {boolean} sticky - Keep the notice until the next one replaces it
 */
function showNotice(message, level = 'info', sticky = false) {
    console.log(`[notice:${level}]`, message);
    if (!noticeRegion) {
        return;
    }

    const notice = document.createElement('div');
    notice.className = `notice notice-${level}`;
    notice.textContent = message;
    noticeRegion.appendChild(notice);

    if (!sticky) {
        setTimeout(() => notice.remove(), NOTICE_TIMEOUT_MS);
    }
}

/**
 * Show a recoverable error to the player.
 */
function displayError(message) {
    showNotice(message, 'error');
}

/**
 * Append a line to the running game log.
 * Kept separate from displayError so ordinary events do not read as failures.
 */
function logToGameConsole(message) {
    showNotice(message, 'info');
}

/**
 * Emit a command to the server, refusing to do so while disconnected.
 * Socket.IO drops emits from a disconnected socket silently, which the player
 * experiences as the game ignoring them.
 *
 * @param {string} event - Socket.IO event name
 * @param {object} payload - Event payload
 * @returns {boolean} - Whether the emit was sent
 */
function emitGame(event, payload) {
    if (!socket.connected) {
        displayError('Not connected to the server - your action was not sent.');
        return false;
    }
    socket.emit(event, payload);
    return true;
}

/**
 * Mark the board as needing a redraw on the next animation frame.
 */
function markDirty() {
    renderDirty = true;
}

/**
 * Mark the board dirty and set the dice-number highlight for the next frames.
 *
 * @param {number|null} number - Dice total to highlight, or null to clear
 */
function setHighlight(number) {
    highlightNumber = number;
    markDirty();
}

/**
 * The single render loop for the lifetime of the page.
 */
function frame() {
    if (renderDirty) {
        renderDirty = false;
        try {
            if (currentBoardData && window.BoardRenderer) {
                window.BoardRenderer.render(currentBoardData, 'board-canvas', highlightNumber);
                updateBoardLabel();
            }
        } catch (error) {
            // A throw here would leave the loop scheduled but the board frozen
            console.error('Board render failed:', error);
            displayError('The board could not be drawn. Try reloading the page.');
        }
    }
    requestAnimationFrame(frame);
}

requestAnimationFrame(frame);

/**
 * Keep the canvas accessible name in step with what is drawn.
 */
function updateBoardLabel() {
    if (!boardCanvas || !currentBoardData) {
        return;
    }
    const phase = currentBoardData.game_phase || 'playing';
    const turnHolder = currentBoardData.current_player || 'nobody';
    boardCanvas.setAttribute('aria-label',
        `Catan board, ${phase} phase. Current turn: ${turnHolder}.`);
}

/**
 * Handle join button click - connect to game
 */
function join(takeover = false) {
    const name = usernameInput.value.trim();
    if (!name) {
        displayError('Please enter a name');
        return;
    }

    const role = document.querySelector('input[name="role"]:checked').value;
    const color = joinColorPicker.value;

    currentUser = name;
    currentRole = role;
    currentColor = color;

    if (socket.connected) {
        socket.emit('join', { name: name, role: role, color: color, takeover: takeover });
        // A late arrival must see the rules the table already agreed on, and
        // the history of what has happened so far
        socket.emit('request_rules');
        requestLogCatchUp();
    } else {
        // The connect handler re-sends the join once the socket is up
        showNotice('Connecting to the server - you will be joined automatically.', 'info');
    }

    joinScreen.classList.add('hidden');
    userScreen.classList.remove('hidden');
    updateStartButton();
}

/**
 * Someone is already connected under this name. Offer to take their seat -
 * covering for a player who stepped away is intended, joining as them by
 * accident is not.
 */
function handleNameTaken(message) {
    const name = usernameInput.value.trim();

    // Back to the join screen until this is resolved.
    currentUser = null;
    userScreen.classList.add('hidden');
    joinScreen.classList.remove('hidden');

    if (window.confirm(`${message}\n\nTake over ${name}'s seat and play as them?`)) {
        join(true);
    } else {
        usernameInput.value = '';
        usernameInput.focus();
    }
}

joinBtn.addEventListener('click', join);

usernameInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        join();
    }
});

/**
 * Handle Start Game button click
 */
startGameBtn.addEventListener('click', () => {
    emitGame('start_game');
});

/**
 * Handle Next Turn button click
 */
nextTurnBtn.addEventListener('click', () => {
    if (!hasRolledDice) {
        displayError('You must roll the dice before advancing to the next turn!');
        return;
    }
    emitGame('next_turn', { name: currentUser });
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
    emitGame('roll_dice', { name: currentUser });
});

/**
 * Handle color picker change - emit set_color event
 */
colorPicker.addEventListener('change', () => {
    currentColor = colorPicker.value;
    emitGame('set_color', { name: currentUser, color: colorPicker.value });
});

/**
 * Handle Place Settlement button click - toggle settlement placement mode
 */
placeSettlementBtn.addEventListener('click', () => {
    // Don't allow manual toggle during setup phase
    if (currentBoardData?.game_phase === 'setup') {
        return;
    }
    
    if (selectedBuilding === 'settlement') {
        // Deselect
        selectedBuilding = null;
        placeSettlementBtn.classList.remove('active');
        gameBoard.classList.remove('placement-mode');
    } else {
        // Select settlement
        selectedBuilding = 'settlement';
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
    if (currentBoardData?.game_phase === 'setup') {
        return;
    }
    
    if (selectedBuilding === 'road') {
        // Deselect
        selectedBuilding = null;
        placeRoadBtn.classList.remove('active');
        gameBoard.classList.remove('placement-mode');
    } else {
        // Select road
        selectedBuilding = 'road';
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
    if (currentBoardData?.game_phase === 'setup') {
        return;
    }
    
    if (selectedBuilding === 'city') {
        // Deselect
        selectedBuilding = null;
        upgradeCityBtn.classList.remove('active');
        gameBoard.classList.remove('placement-mode');
    } else {
        // Select city upgrade
        selectedBuilding = 'city';
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
    if (!currentBoardData) {
        return;
    }
    
    if (currentBoardData.game_phase === 'setup') {
        displayError('Cannot buy development cards during setup');
        return;
    }
    
    if (mustMoveRobber) {
        displayError('You must move the robber first');
        return;
    }
    
    if (currentUser !== currentPlayer) {
        displayError('It is not your turn');
        return;
    }
    
    emitGame('buy_dev_card', { name: currentUser });
});

// Pointer tracking for the board - a tap places, a drag does not
const TAP_MOVE_LIMIT_PX = 10;
const TAP_TIME_LIMIT_MS = 700;
let pointerDownState = null;

/**
 * Handle a tap on the board - place building at tapped position
 *
 * @param {PointerEvent} event - The pointerup event that ended the tap
 */
function handleBoardTap(event) {
    if (!currentBoardData) {
        return;
    }

    // That gesture moved the view, it was not a tap. The movement threshold
    // below misses a slow pan that ends near where it started.
    if (window.BoardRenderer?.wasPanning?.()) {
        return;
    }

    const position = window.BoardRenderer.clientToBoard(boardCanvas, event.clientX, event.clientY);

    // Handle robber movement when mustMoveRobber is true
    if (mustMoveRobber && currentUser === currentPlayer) {
        const hexKey = window.BoardRenderer.findNearestHex(currentBoardData, position.x, position.y);
        if (hexKey) {
            console.log('Moving robber to:', hexKey);
            emitGame('move_robber', {
                name: currentUser,
                hex: hexKey
            });
        }
        return;
    }

    if (!selectedBuilding || currentUser !== currentPlayer) {
        return;
    }

    // During setup phase, ensure selected building matches setup_action
    if (currentBoardData?.game_phase === 'setup') {
        const setupAction = currentBoardData.setup_action || 'settlement';
        if (selectedBuilding !== setupAction) {
            return;
        }
    }

    if (selectedBuilding === 'settlement') {
        // Find nearest vertex
        const vertexKey = window.BoardRenderer.findNearestVertex(currentBoardData, position.x, position.y);
        if (vertexKey) {
            console.log('Placing settlement at:', vertexKey);
            emitGame('place_settlement', {
                name: currentUser,
                vertex: vertexKey
            });
        }
    } else if (selectedBuilding === 'road') {
        // Find nearest edge
        const edgeKey = window.BoardRenderer.findNearestEdge(currentBoardData, position.x, position.y);
        if (edgeKey) {
            console.log('Placing road at:', edgeKey);
            emitGame('place_road', {
                name: currentUser,
                edge: edgeKey
            });
        }
    } else if (selectedBuilding === 'city') {
        // Find nearest vertex to upgrade to city
        const vertexKey = window.BoardRenderer.findNearestVertex(currentBoardData, position.x, position.y);
        if (vertexKey) {
            console.log('Upgrading to city at:', vertexKey);
            emitGame('upgrade_city', {
                name: currentUser,
                vertex: vertexKey
            });
        }
    } else if (selectedBuilding === 'knight' || selectedBuilding === 'city_wall'
               || selectedBuilding === 'knight_move') {
        const vertexKey = window.BoardRenderer.findNearestVertex(currentBoardData, position.x, position.y);
        if (vertexKey) {
            handleCkVertexTap(vertexKey);
        }
    }
}

/**
 * The board half of the Cities & Knights actions.
 * Building a knight or a wall is one tap; moving is two, so the first tap only
 * records where the knight is standing and the second one sends the move.
 *
 * @param {string} vertexKey - Vertex the player tapped
 */
function handleCkVertexTap(vertexKey) {
    // The panels are hidden in a base game, but a stale armed mode must not
    // survive into one either
    if (!ckEnabled()) {
        selectedBuilding = null;
        return;
    }

    if (selectedBuilding === 'knight') {
        emitGame('build_knight', { name: currentUser, vertex: vertexKey });
        return;
    }

    if (selectedBuilding === 'city_wall') {
        emitGame('build_city_wall', { name: currentUser, vertex: vertexKey });
        return;
    }

    if (!knightMoveFrom) {
        knightMoveFrom = vertexKey;
        renderCitiesKnights();
        return;
    }

    emitGame('move_knight', {
        name: currentUser,
        from_vertex: knightMoveFrom,
        to_vertex: vertexKey
    });
    knightMoveFrom = null;
    renderCitiesKnights();
}

boardCanvas.addEventListener('pointerdown', (event) => {
    pointerDownState = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        time: Date.now()
    };
    // Capture so the matching pointerup arrives even if the finger leaves the canvas
    boardCanvas.setPointerCapture(event.pointerId);
});

boardCanvas.addEventListener('pointerup', (event) => {
    if (!pointerDownState || pointerDownState.pointerId !== event.pointerId) {
        return;
    }

    const movedX = Math.abs(event.clientX - pointerDownState.x);
    const movedY = Math.abs(event.clientY - pointerDownState.y);
    const elapsed = Date.now() - pointerDownState.time;
    pointerDownState = null;

    if (movedX <= TAP_MOVE_LIMIT_PX && movedY <= TAP_MOVE_LIMIT_PX && elapsed <= TAP_TIME_LIMIT_MS) {
        handleBoardTap(event);
    }
});

boardCanvas.addEventListener('pointercancel', () => {
    pointerDownState = null;
});

// Zoom and pan. Registered after the tap listeners above on purpose: the
// renderer clears its `panning` flag on pointerup, and the tap handler has to
// still see it. The call is idempotent; the renderer never draws, it marks the
// frame dirty through this callback and the one render loop picks it up.
window.BoardRenderer?.attachCameraControls?.(boardCanvas, markDirty);

/**
 * Zoom about the middle of the visible board, in CSS pixels.
 *
 * @param {number} factor - Multiplier for the current scale
 */
function zoomFromButton(factor) {
    const rect = boardCanvas.getBoundingClientRect();
    window.BoardRenderer?.zoomAt?.(factor, rect.width / 2, rect.height / 2);
    markDirty();
}

document.getElementById('zoom-in-btn')?.addEventListener('click', () => zoomFromButton(1.2));
document.getElementById('zoom-out-btn')?.addEventListener('click', () => zoomFromButton(1 / 1.2));
document.getElementById('zoom-fit-btn')?.addEventListener('click', () => {
    window.BoardRenderer?.fitToView?.();
    markDirty();
});

/**
 * Update Start Game button visibility based on game state
 */
function updateStartButton() {
    // Hiding the button outright made "why can I not start?" unanswerable.
    // Show it whenever a game is not running and say what is missing instead.
    if (gameStarted) {
        startGameBtn.classList.add('hidden');
        return;
    }

    startGameBtn.classList.remove('hidden');

    let reason = '';
    if (currentRole !== 'player') {
        reason = 'Observers cannot start the game - rejoin as a player.';
    } else if (lobbyPlayerCount < minPlayersToStart) {
        reason = `Waiting for players (${lobbyPlayerCount}/${minPlayersToStart}).`;
    }

    startGameBtn.disabled = Boolean(reason);
    startGameBtn.title = reason;
    if (startReasonEl) {
        startReasonEl.textContent = reason;
        startReasonEl.classList.toggle('hidden', !reason);
    }
}

/**
 * Drop back to the lobby after a game ends.
 * Everything game_started/game_state set has to be cleared: a leftover flag or
 * a running timer would otherwise apply to a game that no longer exists. The
 * player keeps their seat, so currentUser and currentRole are left alone.
 */
function returnToLobby() {
    gameStarted = false;
    currentPlayer = null;
    currentBoardData = null;
    hasRolledDice = false;
    mustMoveRobber = false;
    mustChooseVictim = false;
    robberVictims = [];
    mustDiscard = false;
    discardAmount = 0;
    selectedBuilding = null;

    if (diceTimerInterval) {
        clearInterval(diceTimerInterval);
        diceTimerInterval = null;
    }

    setHighlight(null);

    [tradeModal, discardModal, victimModal, inventionModal, monopolyModal].forEach(modal => {
        modal?.classList.remove('show');
    });

    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn].forEach(button => {
        button.classList.remove('active');
    });
    gameBoard.classList.remove('placement-mode');
    robberIndicator?.classList.add('hidden');
    activeRulesPanel?.classList.add('hidden');
    knightMoveFrom = null;
    renderCitiesKnights();
    diceDisplay.innerHTML = '';
    rollDiceBtn.disabled = false;
    rollDiceBtn.textContent = 'Roll Dice';

    gameScreen.classList.add('hidden');
    userScreen.classList.remove('hidden');
    updateStartButton();
}

/**
 * Render user list in lobby
 */
function renderUserList(data) {
    playerList.innerHTML = '';
    observerList.innerHTML = '';
    playerCount.textContent = data.players.length;
    lobbyPlayerCount = data.players.length;
    if (typeof data.min_players === 'number') {
        minPlayersToStart = data.min_players;
    }

    data.players.forEach(user => {
        const li = document.createElement('li');
        li.textContent = user.name;
        if (user.name === currentUser) {
            li.classList.add('current-user');
        }
        playerList.appendChild(li);
    });

    data.observers.forEach(user => {
        const li = document.createElement('li');
        li.textContent = user.name;
        if (user.name === currentUser) {
            li.classList.add('current-user');
        }
        observerList.appendChild(li);
    });
}

// The sections the lobby splits the catalogue into, in display order, keyed by
// the `group` the server tags each rule with. Core is the box's fixed numbers -
// collapsed by default, because expansions and variants are what a table
// actually picks. A group the server invents later still shows up, under
// "Other", rather than silently vanishing from the picker.
const RULE_GROUPS = [
    {
        id: 'expansion',
        label: 'Expansions',
        hint: 'Whole published rule sets.',
        open: true
    },
    {
        id: 'variant',
        label: 'Variants',
        hint: 'Single published house rules.',
        open: true
    },
    {
        id: 'core',
        label: 'Base game numbers',
        hint: 'Piece supplies, deck composition, bank size - the numbers printed on the box.',
        open: false
    },
    {
        id: 'other',
        label: 'Other',
        hint: 'Rules this client has no section for yet.',
        open: true
    }
];

/**
 * Which section a catalogue entry belongs in.
 *
 * @param {object} rule - Catalogue entry
 * @returns {string} - A group id that RULE_GROUPS definitely contains
 */
function ruleGroupId(rule) {
    return RULE_GROUPS.some(group => group.id === rule.group) ? rule.group : 'other';
}

/**
 * Build the controls for one rule of the server's catalogue.
 * Nothing about the rule set is hardcoded here - a rule added server-side
 * shows up as soon as it is in the catalogue.
 *
 * @param {object} rule - Catalogue entry: {id, type, default, name, source, summary}
 * @returns {HTMLElement} - The row, not yet attached
 */
function buildRuleRow(rule) {
    const row = document.createElement('div');
    row.className = 'rule-row';

    const label = document.createElement('label');
    label.className = 'rule-label';
    label.setAttribute('for', `rule-${rule.id}`);
    label.textContent = rule.name;

    const input = document.createElement('input');
    input.id = `rule-${rule.id}`;
    input.dataset.ruleId = rule.id;
    input.dataset.ruleType = rule.type;
    if (rule.type === 'int') {
        input.type = 'number';
        input.className = 'rule-number';
        input.min = rule.minimum;
        input.max = rule.maximum;
    } else {
        input.type = 'checkbox';
        input.className = 'rule-toggle';
    }

    const head = document.createElement('div');
    head.className = 'rule-head';
    head.appendChild(label);
    head.appendChild(input);

    const source = document.createElement('div');
    source.className = 'rule-source';
    source.textContent = rule.source || '';

    const summary = document.createElement('div');
    summary.className = 'rule-summary';
    summary.textContent = rule.summary || '';

    row.appendChild(head);
    row.appendChild(source);
    row.appendChild(summary);
    return row;
}

/**
 * Build one collapsible section of the picker.
 * <details> rather than a scripted toggle: it collapses, remembers nothing the
 * client has to track, and is keyboard and screen-reader operable for free.
 *
 * @param {object} group - An entry of RULE_GROUPS
 * @param {Array<object>} rules - The catalogue entries in that group
 * @returns {HTMLElement} - The section, not yet attached
 */
function buildRuleGroup(group, rules) {
    const section = document.createElement('details');
    section.className = 'rule-group';
    section.dataset.group = group.id;
    section.open = group.open;

    const summary = document.createElement('summary');
    const label = document.createElement('span');
    label.textContent = group.label;
    const count = document.createElement('span');
    count.className = 'rule-group-count';
    count.textContent = rules.length === 1 ? '1 rule' : `${rules.length} rules`;
    summary.appendChild(label);
    summary.appendChild(count);

    const hint = document.createElement('p');
    hint.className = 'rule-group-hint';
    hint.textContent = group.hint;

    const body = document.createElement('div');
    body.className = 'rule-group-body';
    rules.forEach(rule => body.appendChild(buildRuleRow(rule)));

    section.appendChild(summary);
    section.appendChild(hint);
    section.appendChild(body);
    return section;
}

/**
 * Push the server's value for one rule onto its control.
 * The focused control is left alone so that a broadcast triggered by someone
 * else's change does not yank the number out from under the typist; it is
 * re-synced on focusout.
 */
function applyRuleValue(rule) {
    const input = rulesList.querySelector(`[data-rule-id="${rule.id}"]`);
    if (!input) {
        return;
    }

    input.disabled = rulesLocked;

    if (input === document.activeElement) {
        return;
    }

    const value = rulesSelected[rule.id] ?? rule.default;
    if (rule.type === 'int') {
        input.value = value;
    } else {
        input.checked = Boolean(value);
    }
}

/**
 * Render the lobby rules panel from the server's catalogue and selection.
 * The rows are rebuilt only when the catalogue itself changes, so a value
 * broadcast does not destroy focus or the caret in a number field.
 */
function renderRulesPanel() {
    if (!rulesList) {
        return;
    }

    // The group is part of the signature: a rule that moves section has to
    // rebuild the DOM, exactly like one that changes type.
    const signature = rulesCatalogue
        .map(rule => `${rule.id}:${rule.type}:${ruleGroupId(rule)}`)
        .join('|');
    if (signature !== renderedRulesSignature) {
        const fragment = document.createDocumentFragment();
        RULE_GROUPS.forEach(group => {
            const rules = rulesCatalogue.filter(rule => ruleGroupId(rule) === group.id);
            if (rules.length > 0) {
                fragment.appendChild(buildRuleGroup(group, rules));
            }
        });
        rulesList.innerHTML = '';
        rulesList.appendChild(fragment);
        renderedRulesSignature = signature;
    }

    rulesCatalogue.forEach(applyRuleValue);

    if (rulesLockedNote) {
        rulesLockedNote.classList.toggle('hidden', !rulesLocked);
    }
}

/**
 * Read every control and send the whole selection.
 * Clamping here is a UX affordance only - the server clamps again and its
 * answer is what gets rendered.
 */
function sendRules() {
    if (rulesLocked) {
        return;
    }

    const chosen = {};
    rulesCatalogue.forEach(rule => {
        const input = rulesList.querySelector(`[data-rule-id="${rule.id}"]`);
        if (!input) {
            chosen[rule.id] = rulesSelected[rule.id] ?? rule.default;
            return;
        }

        if (rule.type === 'int') {
            const parsed = parseInt(input.value, 10);
            const fallback = rulesSelected[rule.id] ?? rule.default;
            chosen[rule.id] = Number.isNaN(parsed)
                ? fallback
                : Math.max(rule.minimum, Math.min(rule.maximum, parsed));
        } else {
            chosen[rule.id] = input.checked;
        }
    });

    emitGame('set_rules', { rules: chosen });
}

if (rulesList) {
    // One delegated listener for controls that are rebuilt whenever the
    // catalogue changes. `change` rather than `input` so a number is sent
    // once, not once per keystroke.
    rulesList.addEventListener('change', (event) => {
        if (!event.target.closest('[data-rule-id]')) {
            return;
        }
        sendRules();
    });

    // The focused control is skipped while rendering, so re-sync it on leave
    rulesList.addEventListener('focusout', (event) => {
        const input = event.target.closest('[data-rule-id]');
        const rule = rulesCatalogue.find(entry => entry.id === input?.dataset.ruleId);
        if (rule) {
            applyRuleValue(rule);
        }
    });
}

/**
 * Show the rules the running game is actually using, non-default ones only.
 * Rendered from the board payload, which is what the engine reads.
 */
function renderActiveRules() {
    if (!activeRulesPanel || !activeRulesDiv) {
        return;
    }

    const active = currentBoardData?.rules;
    if (!active || rulesCatalogue.length === 0) {
        activeRulesPanel.classList.add('hidden');
        return;
    }

    const parts = [];
    rulesCatalogue.forEach(rule => {
        const value = active[rule.id];
        if (value === undefined || value === rule.default) {
            return;
        }
        if (rule.type === 'int') {
            parts.push(`${rule.name}: ${value}`);
        } else {
            parts.push(value ? rule.name : `${rule.name}: off`);
        }
    });

    activeRulesDiv.textContent = parts.length > 0 ? parts.join(' · ') : 'Base game rules';
    activeRulesPanel.classList.remove('hidden');
}

/**
 * Render game sidebar (players only - no observers in game)
 */
function renderGameSidebar(data) {
    gamePlayersList.innerHTML = '';

    // Handle both array of strings and array of player objects
    const players = data.players.map(p => typeof p === 'string' ? p : p.name);

    // Get longest road and largest army data from board
    const longestRoadHolder = currentBoardData?.longest_road_holder || null;
    const largestArmyHolder = currentBoardData?.largest_army_holder || null;
    const longestRoadLengths = currentBoardData?.longest_road_length || {};
    const knightsPlayed = currentBoardData?.knights_played || {};

    // Harbour points only exist when the table switched the rule on
    const harbormasterOn = currentBoardData?.rules?.harbormaster === true;
    const harbormasterHolder = currentBoardData?.harbormaster_holder || null;
    const harborPoints = currentBoardData?.harbor_points || {};

    players.forEach(name => {
        const li = document.createElement('li');
        
        // Get player data for points
        const playerData = currentBoardData?.players?.find(p => p.name === name);
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
        if (name === currentPlayer) {
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
function findMyPlayer() {
    const players = currentBoardData?.players || [];
    return players.find(p => p.is_you) || players.find(p => p.name === currentUser) || null;
}

/**
 * Render resource panel - shows current user's resources
 */
function renderResourcePanel() {
    if (!currentBoardData || !currentBoardData.players) {
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
function renderBank() {
    if (!currentBoardData || !currentBoardData.bank) {
        return;
    }
    
    const bank = currentBoardData.bank;
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
function renderDevCards() {
    if (!currentBoardData) {
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
    
    const isMyTurn = currentUser === currentPlayer;
    const hasRolledDice = currentBoardData.has_rolled_dice === true;
    const currentTurn = currentBoardData.turn_count !== undefined ? currentBoardData.turn_count : 0;
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
                const cardCanPlay = isMyTurn && 
                    (!needsDice || hasRolledDice) &&
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
    const remaining = currentBoardData?.dev_cards_remaining ?? 0;
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
    if (!currentBoardData) {
        return;
    }
    
    if (currentBoardData.game_phase === 'setup') {
        displayError('Cannot play development cards during setup');
        return;
    }
    
    if (mustMoveRobber) {
        displayError('You must move the robber first');
        return;
    }
    
    if (currentUser !== currentPlayer) {
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
    emitGame('play_dev_card', { name: currentUser, card_type: cardType });
}

// --------------------------------------------------------- Cities & Knights
//
// Everything in this section renders from `board.cities_knights` and shows
// nothing at all unless `board.rules.cities_and_knights` is on, so a base game
// looks exactly as it did before the expansion existed.
//
// The costs below are duplicated from server/game/cities_knights.py. They exist
// only to grey out a button and say why before the round trip - the server
// checks all of them again and its answer is what the board is drawn from.

const COMMODITY_TYPES = ['cloth', 'coin', 'paper'];
const COMMODITY_ICONS = { cloth: '🧵', coin: '🪙', paper: '📜' };
const RESOURCE_ICONS = { wood: '🌲', brick: '🧱', sheep: '🐑', wheat: '🌾', ore: '🪨' };

const TRACK_ORDER = ['trade', 'politics', 'science'];
const TRACK_LABELS = { trade: 'Trade', politics: 'Politics', science: 'Science' };

const KNIGHT_RANK_NAMES = { 1: 'Basic', 2: 'Strong', 3: 'Mighty' };
const KNIGHT_BUILD_COST = { sheep: 1, ore: 1 };
const KNIGHT_ACTIVATE_COST = { wheat: 1 };
const KNIGHT_PROMOTE_COST = { sheep: 1, ore: 1 };
const CITY_WALL_COST = { brick: 2 };
const MAX_CITY_WALLS = 3;
const MAX_KNIGHTS_PER_RANK = 2;
const MAX_IMPROVEMENT_LEVEL = 5;
const ABILITY_LEVEL = 3;
const MIGHTY_RANK = 3;

// The board modes this section adds to the settlement/road/city set
const CK_MODES = ['knight', 'knight_move', 'city_wall'];

/**
 * Whether the running game has Cities & Knights and has sent its state.
 */
function ckEnabled() {
    return currentBoardData?.rules?.cities_and_knights === true
        && Boolean(currentBoardData?.cities_knights);
}

/**
 * Whether a selection mode belongs to this expansion.
 */
function isCkMode(mode) {
    return CK_MODES.includes(mode);
}

/**
 * Render a cost as "1🐑 1🪨".
 *
 * @param {object} cost - {resource: amount}
 * @returns {string}
 */
function formatCost(cost) {
    return Object.entries(cost)
        .map(([resource, amount]) => `${amount}${RESOURCE_ICONS[resource] || resource}`)
        .join(' ');
}

/**
 * Whether a hand covers a cost.
 *
 * @param {object} held - {resource: amount} the player holds
 * @param {object} cost - {resource: amount} required
 */
function canAfford(held, cost) {
    return Object.entries(cost).every(([resource, amount]) => (held?.[resource] || 0) >= amount);
}

/**
 * Name the first resource a player is short of, for a disabled button's reason.
 *
 * @returns {string} - Empty when the cost is covered
 */
function shortfallReason(held, cost) {
    for (const [resource, amount] of Object.entries(cost)) {
        const have = held?.[resource] || 0;
        if (have < amount) {
            return `Need ${amount} ${resource}, you have ${have}`;
        }
    }
    return '';
}

/**
 * Why no Cities & Knights action can be taken at all right now, if so.
 * Every action shares these two, so the per-action checks stay to their rule.
 *
 * @returns {string} - Empty when the player may act
 */
function ckTurnBlockReason() {
    if (currentBoardData?.game_phase === 'setup') {
        return 'Not during setup';
    }
    if (currentUser !== currentPlayer) {
        return 'Not your turn';
    }
    return '';
}

/**
 * Arm or disarm one of this expansion's board modes.
 * Same single-mode rule as the settlement/road/city buttons: arming one of
 * these disarms those, and vice versa.
 *
 * @param {string} mode - One of CK_MODES
 */
function toggleCkMode(mode) {
    if (!ckEnabled()) {
        return;
    }
    selectedBuilding = selectedBuilding === mode ? null : mode;
    knightMoveFrom = null;

    [placeSettlementBtn, placeRoadBtn, upgradeCityBtn].forEach(button => {
        button.classList.remove('active');
    });
    gameBoard.classList.toggle('placement-mode', Boolean(selectedBuilding));

    syncCkModeButtons();
    renderCitiesKnights();
}

/**
 * Show which of this expansion's board modes is armed, if any.
 * Called from the base placement buttons too, so exactly one mode ever looks
 * selected.
 */
function syncCkModeButtons() {
    if (!buildKnightBtn || !moveKnightBtn || !buildWallBtn) {
        return;
    }
    buildKnightBtn.classList.toggle('active', selectedBuilding === 'knight');
    moveKnightBtn.classList.toggle('active', selectedBuilding === 'knight_move');
    buildWallBtn.classList.toggle('active', selectedBuilding === 'city_wall');

    if (selectedBuilding !== 'knight_move') {
        knightMoveFrom = null;
    }
}

/**
 * Render every Cities & Knights panel, or hide them all.
 * This is the only entry point: it is safe to call with no board, in the base
 * game, or as an observer.
 */
function renderCitiesKnights() {
    const enabled = ckEnabled();
    const player = enabled ? findMyPlayer() : null;

    // Three more panels do not fit the rail's base-game width
    gameScreen.classList.toggle('ck-on', enabled);

    barbarianPanel?.classList.toggle('hidden', !enabled);
    // The barbarian clock is public and matters to a spectator too; the other
    // two panels are one player's own board and have nothing to say without one.
    improvementsPanel?.classList.toggle('hidden', !enabled || !player);
    knightsPanel?.classList.toggle('hidden', !enabled || !player);

    if (!enabled) {
        knightMoveFrom = null;
        return;
    }

    renderBarbarianTrack();

    if (player) {
        renderImprovements(player);
        renderKnights(player);
    }
    syncCkModeButtons();
}

/**
 * The barbarian ship's progress towards Catan - the expansion's clock.
 * Deliberately loud near the end: a table that does not see the attack coming
 * loses cities to it.
 */
function renderBarbarianTrack() {
    if (!barbarianTrack || !barbarianStatus || !barbarianDefense) {
        return;
    }

    const ck = currentBoardData.cities_knights;
    const length = ck.barbarian_track_length || 7;
    const position = Math.max(0, Math.min(length, ck.barbarian_position || 0));
    const stepsLeft = length - position;
    const urgency = stepsLeft <= 1 ? 'danger' : stepsLeft <= 2 ? 'warning' : '';

    const pips = document.createDocumentFragment();
    for (let step = 1; step <= length; step += 1) {
        const pip = document.createElement('span');
        pip.className = step <= position ? 'barbarian-pip filled' : 'barbarian-pip';
        pips.appendChild(pip);
    }
    barbarianTrack.innerHTML = '';
    barbarianTrack.appendChild(pips);
    barbarianTrack.className = `barbarian-track ${urgency}`;
    barbarianTrack.setAttribute(
        'aria-label',
        `Barbarian ship at space ${position} of ${length}`
    );

    barbarianStatus.className = `barbarian-status ${urgency}`;
    barbarianStatus.textContent = stepsLeft <= 0
        ? `${position}/${length} — the barbarians are landing`
        : `${position}/${length} — ${stepsLeft} barbarian roll${stepsLeft === 1 ? '' : 's'} away`;

    // Defence is the whole table's active knights against every city on the
    // board, so it is worth stating even on someone else's turn.
    const players = currentBoardData.players || [];
    const strength = Object.values(ck.knights || {}).reduce((total, knights) => (
        total + (knights || []).reduce((sum, knight) => sum + (knight.active ? knight.rank : 0), 0)
    ), 0);
    const cities = players.reduce((total, entry) => total + (entry.cities?.length || 0), 0);

    const notes = [`Knights ${strength} vs ${cities} cities`];
    if (strength < cities) {
        notes.push('cities will be pillaged');
    }
    if (!ck.barbarians_have_attacked) {
        notes.push('the robber stays put until the first attack');
    }
    // Worth 1 victory point each and invisible everywhere else in the UI
    const defenderCards = ck.defender_cards?.[currentUser] || 0;
    if (defenderCards > 0) {
        notes.push(`🛡️ ${defenderCards} Defender of Catan`);
    }
    barbarianDefense.className = strength < cities ? 'ck-note danger' : 'ck-note';
    barbarianDefense.textContent = notes.join(' · ');
}

/**
 * The three city improvement tracks, with what the next level costs.
 * Level N costs N commodities of the track's own type, so the next level always
 * costs one more than the last.
 *
 * @param {object} player - Own player entry from the board payload
 */
function renderImprovements(player) {
    if (!improvementTracks) {
        return;
    }

    const ck = currentBoardData.cities_knights;
    const tracks = ck.tracks || {};
    const levels = ck.improvements?.[player.name] || {};
    const commodities = player.commodities || {};
    const hasCity = (player.cities || []).length > 0;
    const turnBlock = ckTurnBlockReason();

    const fragment = document.createDocumentFragment();

    TRACK_ORDER.forEach(track => {
        const spec = tracks[track];
        if (!spec) {
            return;
        }

        const names = Array.isArray(spec.levels) ? spec.levels : [];
        const commodity = spec.commodity;
        const icon = COMMODITY_ICONS[commodity] || '';
        const level = levels[track] || 0;
        const held = commodities[commodity] || 0;
        const nextCost = level + 1;

        const row = document.createElement('div');
        row.className = 'improvement-row';

        const head = document.createElement('div');
        head.className = 'improvement-head';

        const label = document.createElement('span');
        label.className = `improvement-name track-${track}`;
        label.textContent = `${icon} ${TRACK_LABELS[track] || track}`;

        const levelBadge = document.createElement('span');
        levelBadge.className = 'improvement-level';
        levelBadge.textContent = `${level}/${MAX_IMPROVEMENT_LEVEL}`;

        head.appendChild(label);
        head.appendChild(levelBadge);
        row.appendChild(head);

        const built = document.createElement('div');
        built.className = 'improvement-built';
        built.textContent = level > 0 ? names[level - 1] || `Level ${level}` : 'Nothing built yet';
        row.appendChild(built);

        // The level-3 building is the one that grants an ability, so say which
        // ability it is rather than leaving the player to count rows.
        if (level >= ABILITY_LEVEL && names[ABILITY_LEVEL - 1]) {
            const ability = document.createElement('div');
            ability.className = 'ck-badge ability';
            ability.textContent = `✔ ${names[ABILITY_LEVEL - 1]} in use`;
            row.appendChild(ability);
        }

        const holder = ck.metropolis?.[track];
        if (holder) {
            const metropolis = document.createElement('div');
            const mine = holder === player.name;
            metropolis.className = mine ? 'ck-badge metropolis' : 'ck-note';
            metropolis.textContent = mine
                ? `🏛️ ${TRACK_LABELS[track] || track} metropolis is yours`
                : `🏛️ metropolis held by ${holder}`;
            row.appendChild(metropolis);
        }

        let reason = '';
        if (level >= MAX_IMPROVEMENT_LEVEL) {
            reason = 'This track is complete';
        } else if (turnBlock) {
            reason = turnBlock;
        } else if (!hasCity) {
            reason = 'You need a city to improve';
        } else if (held < nextCost) {
            reason = `Need ${nextCost} ${commodity}, you have ${held}`;
        }

        const buy = document.createElement('button');
        buy.type = 'button';
        buy.className = 'ck-buy';
        buy.dataset.track = track;
        buy.disabled = Boolean(reason);
        buy.title = reason;
        buy.textContent = level >= MAX_IMPROVEMENT_LEVEL
            ? 'Complete'
            : `Buy ${names[level] || `level ${nextCost}`} · ${nextCost}${icon}`;
        row.appendChild(buy);

        if (reason) {
            const note = document.createElement('div');
            note.className = 'ck-note';
            note.textContent = reason;
            row.appendChild(note);
        }

        fragment.appendChild(row);
    });

    improvementTracks.innerHTML = '';
    improvementTracks.appendChild(fragment);
}

/**
 * The player's own knights, the three actions that need a board tap, and the
 * city walls that share the same tap flow.
 *
 * @param {object} player - Own player entry from the board payload
 */
function renderKnights(player) {
    if (!knightList || !buildKnightBtn || !moveKnightBtn || !buildWallBtn) {
        return;
    }

    const ck = currentBoardData.cities_knights;
    const knights = ck.knights?.[player.name] || [];
    const resources = player.resources || {};
    const walls = ck.city_walls?.[player.name] || 0;
    const hasFortress = (ck.improvements?.[player.name]?.politics || 0) >= ABILITY_LEVEL;
    const turnBlock = ckTurnBlockReason();

    const rankCount = (rank) => knights.filter(knight => knight.rank === rank).length;

    // Build
    let buildReason = turnBlock;
    if (!buildReason && rankCount(1) >= MAX_KNIGHTS_PER_RANK) {
        buildReason = 'No basic knight pieces left';
    }
    if (!buildReason) {
        buildReason = shortfallReason(resources, KNIGHT_BUILD_COST);
    }
    buildKnightBtn.textContent = `Build knight · ${formatCost(KNIGHT_BUILD_COST)}`;
    buildKnightBtn.disabled = Boolean(buildReason);
    buildKnightBtn.title = buildReason || 'Then tap a vacant intersection on one of your roads';

    // Move
    let moveReason = turnBlock;
    if (!moveReason && !knights.some(knight => knight.can_act)) {
        moveReason = 'No knight can act this turn';
    }
    moveKnightBtn.textContent = 'Move knight';
    moveKnightBtn.disabled = Boolean(moveReason);
    moveKnightBtn.title = moveReason || 'Tap the knight, then where it should go';

    // City wall
    let wallReason = turnBlock;
    if (!wallReason && walls >= MAX_CITY_WALLS) {
        wallReason = `All ${MAX_CITY_WALLS} walls are built`;
    }
    if (!wallReason) {
        wallReason = shortfallReason(resources, CITY_WALL_COST);
    }
    buildWallBtn.textContent =
        `City wall ${walls}/${MAX_CITY_WALLS} · ${formatCost(CITY_WALL_COST)}`;
    buildWallBtn.disabled = Boolean(wallReason);
    buildWallBtn.title = wallReason || 'Then tap one of your cities';

    if (knightHint) {
        knightHint.textContent = ckModeHint();
        knightHint.classList.toggle('hidden', !isCkMode(selectedBuilding));
    }

    const fragment = document.createDocumentFragment();

    if (knights.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'no-cards';
        empty.textContent = 'No knights on the board';
        fragment.appendChild(empty);
    }

    knights.forEach(knight => {
        const row = document.createElement('div');
        row.className = knight.vertex === knightMoveFrom ? 'knight-row selected' : 'knight-row';

        const title = document.createElement('div');
        title.className = 'knight-title';

        const name = document.createElement('span');
        name.className = `knight-rank rank-${knight.rank}`;
        name.textContent = `⚔️ ${KNIGHT_RANK_NAMES[knight.rank] || `Rank ${knight.rank}`}`;

        const state = document.createElement('span');
        state.className = knight.active ? 'knight-state active' : 'knight-state idle';
        state.textContent = knight.active
            ? (knight.can_act ? 'Active' : 'Active · spent')
            : 'Inactive';

        title.appendChild(name);
        title.appendChild(state);
        row.appendChild(title);

        const actions = document.createElement('div');
        actions.className = 'knight-buttons';

        let activateReason = turnBlock;
        if (!activateReason && knight.active) {
            activateReason = 'Already active';
        }
        if (!activateReason) {
            activateReason = shortfallReason(resources, KNIGHT_ACTIVATE_COST);
        }
        actions.appendChild(buildKnightActionButton(
            'activate', knight.vertex,
            `Activate · ${formatCost(KNIGHT_ACTIVATE_COST)}`, activateReason
        ));

        let promoteReason = turnBlock;
        if (!promoteReason && knight.rank >= MIGHTY_RANK) {
            promoteReason = 'Already mighty';
        }
        if (!promoteReason && knight.rank + 1 === MIGHTY_RANK && !hasFortress) {
            promoteReason = 'Mighty knights need the Fortress (Politics 3)';
        }
        if (!promoteReason && rankCount(knight.rank + 1) >= MAX_KNIGHTS_PER_RANK) {
            const nextRank = KNIGHT_RANK_NAMES[knight.rank + 1].toLowerCase();
            promoteReason = `No ${nextRank} knight pieces left`;
        }
        if (!promoteReason) {
            promoteReason = shortfallReason(resources, KNIGHT_PROMOTE_COST);
        }
        actions.appendChild(buildKnightActionButton(
            'promote', knight.vertex,
            `Promote · ${formatCost(KNIGHT_PROMOTE_COST)}`, promoteReason
        ));

        row.appendChild(actions);
        fragment.appendChild(row);
    });

    knightList.innerHTML = '';
    knightList.appendChild(fragment);
}

/**
 * One per-knight button. The vertex travels in a data attribute so the list can
 * be rebuilt on every board update without touching its listener.
 *
 * @param {string} action - 'activate' or 'promote'
 * @param {string} vertex - Vertex the knight stands on
 * @param {string} label - Button text, including the cost
 * @param {string} reason - Why it is disabled, or empty
 * @returns {HTMLButtonElement}
 */
function buildKnightActionButton(action, vertex, label, reason) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ck-knight-action';
    button.dataset.knightAction = action;
    button.dataset.vertex = vertex;
    button.textContent = label;
    button.disabled = Boolean(reason);
    button.title = reason;
    return button;
}

/**
 * What the player is expected to tap next, for the armed mode.
 */
function ckModeHint() {
    if (selectedBuilding === 'knight') {
        return 'Tap a vacant intersection touching one of your roads.';
    }
    if (selectedBuilding === 'city_wall') {
        return 'Tap one of your cities.';
    }
    if (selectedBuilding === 'knight_move') {
        return knightMoveFrom
            ? 'Now tap the intersection to move it to.'
            : 'Tap the knight you want to move.';
    }
    return '';
}

// Delegated listeners, registered once: both lists are rebuilt from scratch on
// every board update, which orphans anything bound to their old nodes.
improvementTracks?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-track]');
    if (!button || button.disabled) {
        return;
    }
    emitGame('buy_improvement', { name: currentUser, track: button.dataset.track });
});

knightList?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-knight-action]');
    if (!button || button.disabled) {
        return;
    }
    const eventName = button.dataset.knightAction === 'promote'
        ? 'promote_knight'
        : 'activate_knight';
    emitGame(eventName, { name: currentUser, vertex: button.dataset.vertex });
});

buildKnightBtn?.addEventListener('click', () => toggleCkMode('knight'));
moveKnightBtn?.addEventListener('click', () => toggleCkMode('knight_move'));
buildWallBtn?.addEventListener('click', () => toggleCkMode('city_wall'));

/**
 * Update game UI based on phase (setup vs playing)
 */
function updateGameUI(boardData) {
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
    
    // Update currentPlayer variable from board data
    if (boardData.current_player) {
        currentPlayer = boardData.current_player;
    }
    
    // Update mustMoveRobber flag
    mustMoveRobber = boardData.must_move_robber || false;
    mustChooseVictim = boardData.must_choose_victim || false;
    robberVictims = boardData.robber_victims || [];
    
    // Handle victim modal from board data
    if (mustChooseVictim && currentUser === currentPlayer) {
        renderVictimList();
        victimModal.classList.add('show');
    }
    
    // Update discard state from board data
    const playersNeedingDiscard = boardData.players_needing_discard || {};
    if (playersNeedingDiscard[currentUser] !== undefined && !mustDiscard) {
        mustDiscard = true;
        discardAmount = playersNeedingDiscard[currentUser];
        discardAmountSpan.textContent = discardAmount;
        
        document.getElementById('discard-wood').value = 0;
        document.getElementById('discard-brick').value = 0;
        document.getElementById('discard-sheep').value = 0;
        document.getElementById('discard-wheat').value = 0;
        document.getElementById('discard-ore').value = 0;
        
        discardModal.classList.add('show');
    }
    
    // If must move robber, show a persistent hint - this runs on every board
    // update while the flag is set, so it must not be a popup
    if (robberIndicator) {
        if (mustMoveRobber && currentUser === currentPlayer) {
            robberIndicator.classList.remove('hidden');
        } else {
            robberIndicator.classList.add('hidden');
        }
    }
    
    // Update free roads indicator
    const freeRoadsRemaining = boardData.free_roads_remaining || 0;
    if (freeRoadsRemaining > 0 && currentUser === currentPlayer) {
        freeRoadsIndicator.classList.remove('hidden');
        freeRoadsText.textContent = `Free Roads: ${freeRoadsRemaining} remaining`;
    } else {
        freeRoadsIndicator.classList.add('hidden');
    }
    
    if (gamePhase === 'setup') {
        // During setup, auto-select building type based on setup_action
        const setupAction = boardData.setup_action || 'settlement';
        const isMyTurn = currentUser === currentPlayer;
        
        if (isMyTurn) {
            // Auto-select the required building type
            selectedBuilding = setupAction;
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
            selectedBuilding = null;
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
        if (!isCkMode(selectedBuilding)) {
            selectedBuilding = null;
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
    const myTurnNow = currentUser === currentPlayer;
    const alreadyRolled = boardData.has_rolled_dice === true;
    rollDiceBtn.disabled = gamePhase === 'setup' || !myTurnNow || alreadyRolled;
    if (!alreadyRolled) {
        rollDiceBtn.textContent = 'Roll Dice';
    }

    syncCkModeButtons();
}

/**
 * How long an offer stays open, in seconds. Mirrors the server's trade timeout;
 * the countdown here is display only and the server decides when an offer dies.
 */
const TRADE_OFFER_SECONDS = 10;

/**
 * Format a resource bundle as "2🌲 1🧱 ", skipping empty entries.
 *
 * @param {object} resources - {resource: amount}
 * @returns {string}
 */
function formatTradeBundle(resources) {
    return Object.entries(resources || {})
        .filter(([, count]) => count > 0)
        .map(([resource, count]) => `${count}${RESOURCE_ICONS[resource] || resource}`)
        .join(' ');
}

/**
 * The shell of one offer card: header with an optional proposer name, the
 * countdown, and the resources. The caller appends its own action row.
 *
 * Everything server-supplied lands via textContent - a player named
 * `<img src=x onerror=…>` has to read as literal text here.
 *
 * @param {object} offer - One entry from `trades.active` or `trades.my_offers`
 * @param {string} giveText - What this viewer gives
 * @param {string} wantText - What this viewer gets
 * @param {string} proposerName - Name to show, or '' for one's own offer
 * @param {string} proposerColor - Colour for that name
 * @returns {HTMLElement}
 */
function buildTradeOfferCard(offer, giveText, wantText, proposerName, proposerColor) {
    const card = document.createElement('div');
    card.className = 'trade-offer';
    card.dataset.offerId = String(offer.id);
    card.dataset.created = String(offer.created_at);

    const header = document.createElement('div');
    header.className = 'trade-offer-header';

    if (proposerName) {
        const who = document.createElement('span');
        who.className = 'trade-offer-player';
        who.textContent = proposerName;
        who.style.color = proposerColor;
        header.appendChild(who);
    }

    const timer = document.createElement('span');
    timer.className = 'trade-timer';
    header.appendChild(timer);
    card.appendChild(header);

    const resources = document.createElement('div');
    resources.className = 'trade-offer-resources';

    const give = document.createElement('span');
    give.className = 'give';
    give.textContent = giveText;
    resources.appendChild(give);

    const arrow = document.createElement('span');
    arrow.textContent = '→';
    resources.appendChild(arrow);

    const want = document.createElement('span');
    want.className = 'want';
    want.textContent = wantText;
    resources.appendChild(want);

    card.appendChild(resources);
    return card;
}

/**
 * One action button. The offer id - and for a completion, the responder -
 * travel in data attributes so the delegated listener needs nothing else and
 * the list can be rebuilt freely.
 *
 * @param {string} action - Value for the delegated dispatch
 * @param {number} offerId - Offer the click applies to
 * @param {string} label - Button text
 * @returns {HTMLButtonElement}
 */
function buildTradeActionButton(action, offerId, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.action = action;
    button.dataset.offerId = String(offerId);
    button.textContent = label;
    return button;
}

/**
 * Render trade offers panel
 */
function renderTradeOffers() {
    if (!currentBoardData || !currentBoardData.trades) {
        tradeOffersDiv.replaceChildren();
        myOffersDiv.replaceChildren();
        updateTradeTabBadge(0);
        return;
    }

    const activeTrades = currentBoardData.trades.active || [];
    const allPlayers = currentBoardData.players || [];

    // Active offers (other players' offers - responder view)
    const otherOffers = activeTrades.filter(t => t.proposer !== currentUser);
    const offersFragment = document.createDocumentFragment();

    if (otherOffers.length > 0) {
        const heading = document.createElement('h4');
        heading.textContent = 'Active Offers:';
        offersFragment.appendChild(heading);

        for (const offer of otherOffers) {
            const accepted = offer.accepted_by || {};
            const hasAcceptedMe = accepted[currentUser] === true;

            // For the responder the sides are mirrored: the proposer's wanted
            // resources are what this player would hand over.
            const proposer = allPlayers.find(p => p.name === offer.proposer);
            const card = buildTradeOfferCard(
                offer,
                `You give: ${formatTradeBundle(offer.wanted_resources)}`,
                `You get: ${formatTradeBundle(offer.offered_resources)}`,
                offer.proposer,
                proposer?.color || '#e74c3c'
            );

            const actions = document.createElement('div');
            actions.className = 'trade-offer-actions';

            const acceptBtn = buildTradeActionButton(
                'accept', offer.id, hasAcceptedMe ? 'Accepted' : 'Accept'
            );
            acceptBtn.classList.add('accept-btn');
            acceptBtn.classList.toggle('is-accepted', hasAcceptedMe);
            actions.appendChild(acceptBtn);

            const declineBtn = buildTradeActionButton('decline', offer.id, 'Deny');
            declineBtn.classList.add('decline-btn');
            actions.appendChild(declineBtn);

            card.appendChild(actions);
            offersFragment.appendChild(card);
        }
    }

    tradeOffersDiv.replaceChildren(offersFragment);

    // My offers (own offers - proposer view)
    const myOfferList = currentBoardData.trades.my_offers?.[currentUser] || [];
    const myOffersFragment = document.createDocumentFragment();

    if (myOfferList.length > 0) {
        const heading = document.createElement('h4');
        heading.textContent = 'Your Offers:';
        myOffersFragment.appendChild(heading);

        for (const offer of myOfferList) {
            const accepted = offer.accepted_by || {};
            const card = buildTradeOfferCard(
                offer,
                formatTradeBundle(offer.offered_resources),
                formatTradeBundle(offer.wanted_resources),
                '',
                ''
            );

            // One button per opponent: grey until they accept, then their own
            // colour, and clicking it completes the trade with them.
            const actions = document.createElement('div');
            actions.className = 'trade-offer-actions';

            for (const player of allPlayers) {
                if (player.name === currentUser) continue;
                const hasAccepted = accepted[player.name] === true;
                const button = buildTradeActionButton('complete', offer.id, player.name);
                button.classList.add('accepted-player');
                button.dataset.responder = player.name;
                if (hasAccepted) {
                    button.classList.add('is-accepted');
                    button.style.backgroundColor = player.color || '';
                }
                actions.appendChild(button);
            }

            card.appendChild(actions);
            myOffersFragment.appendChild(card);
        }
    }

    myOffersDiv.replaceChildren(myOffersFragment);

    updateTradeTabBadge(otherOffers.length + myOfferList.length);
}

/**
 * Act on a click anywhere in either offer list.
 *
 * Both lists are rebuilt from scratch on every board update, which orphans any
 * listener bound to their buttons - hence one delegated listener per container,
 * registered once below rather than inside the render.
 *
 * @param {Event} event - Click from one of the offer containers
 */
function handleTradeAction(event) {
    const button = event.target.closest('[data-action]');
    if (!button || button.disabled) {
        return;
    }

    const offerId = Number(button.dataset.offerId);
    if (!Number.isInteger(offerId)) {
        return;
    }

    switch (button.dataset.action) {
        case 'accept':
            acceptTrade(offerId);
            break;
        case 'decline':
            declineTrade(offerId);
            break;
        case 'complete':
            completeTrade(offerId, button.dataset.responder);
            break;
        default:
            break;
    }
}

tradeOffersDiv?.addEventListener('click', handleTradeAction);
myOffersDiv?.addEventListener('click', handleTradeAction);

/**
 * Update trade offer timers
 */
function updateTradeTimers() {
    if (!currentBoardData) {
        return;
    }

    const timers = document.querySelectorAll('.trade-timer');
    if (timers.length === 0) {
        return;
    }

    const currentTime = Date.now() / 1000;
    let needsRefresh = false;

    timers.forEach(timer => {
        const offerEl = timer.closest('.trade-offer');
        if (!offerEl) return;

        const createdAt = parseFloat(offerEl.dataset.created);
        if (isNaN(createdAt)) return;

        const elapsed = currentTime - createdAt;
        const remaining = Math.max(0, TRADE_OFFER_SECONDS - Math.floor(elapsed));

        timer.textContent = `${remaining}s`;

        if (remaining === 0) {
            needsRefresh = true;
        }
    });

    // Refresh board if any offer expired - the server prunes it and sends the
    // list back without it.
    if (needsRefresh) {
        emitGame('refresh_board');
    }
}

let tradeTimerHandle = null;

/**
 * Start the once-per-second countdown. Idempotent: a second call keeps the
 * interval already running rather than stacking a second one, which would
 * double the `refresh_board` emits an expiring offer produces.
 */
function startTradeTimers() {
    if (tradeTimerHandle !== null) {
        return;
    }
    tradeTimerHandle = setInterval(updateTradeTimers, 1000);
}

startTradeTimers();

/**
 * Show trade modal
 */
function showTradeModal() {
    if (!currentUser || currentUser !== currentPlayer) {
        displayError('You can only propose trades on your turn');
        return;
    }
    tradeModal.classList.remove('hidden');
    tradeModal.classList.add('show');
}

/**
 * Hide trade modal
 */
function hideTradeModal() {
    tradeModal.classList.remove('show');
    tradeModal.classList.add('hidden');
    // Reset inputs
    ['wood', 'brick', 'sheep', 'wheat', 'ore'].forEach(res => {
        document.getElementById(`give-${res}`).value = 0;
        document.getElementById(`want-${res}`).value = 0;
    });
}

/**
 * Submit trade proposal
 */
function submitTrade() {
    const offered = {};
    const wanted = {};
    
    ['wood', 'brick', 'sheep', 'wheat', 'ore'].forEach(res => {
        const giveCount = parseInt(document.getElementById(`give-${res}`).value) || 0;
        const wantCount = parseInt(document.getElementById(`want-${res}`).value) || 0;
        if (giveCount > 0) offered[res] = giveCount;
        if (wantCount > 0) wanted[res] = wantCount;
    });
    
    if (Object.keys(offered).length === 0 || Object.keys(wanted).length === 0) {
        displayError('Please specify resources to give and want');
        return;
    }
    
    emitGame('propose_trade', {
        name: currentUser,
        offered: offered,
        wanted: wanted
    });
    
    hideTradeModal();
}

/**
 * Accept a trade offer
 */
function acceptTrade(offerId) {
    emitGame('accept_trade', {
        name: currentUser,
        offer_id: offerId
    });
}

/**
 * Decline a trade offer
 */
function declineTrade(offerId) {
    emitGame('decline_trade', {
        name: currentUser,
        offer_id: offerId
    });
}

/**
 * Show invention modal (for Invention/Year of Plenty card)
 */
function showInventionModal() {
    inventionModal.classList.remove('hidden');
    inventionModal.classList.add('show');
    // Reset inputs
    ['wood', 'brick', 'sheep', 'wheat', 'ore'].forEach(res => {
        document.getElementById(`invention-${res}`).value = 0;
    });
}

/**
 * Hide invention modal
 */
function hideInventionModal() {
    inventionModal.classList.remove('show');
    inventionModal.classList.add('hidden');
}

/**
 * Confirm invention card selection - get 2 resources
 */
function confirmInvention() {
    const selected = {};
    let total = 0;
    
    ['wood', 'brick', 'sheep', 'wheat', 'ore'].forEach(res => {
        const count = parseInt(document.getElementById(`invention-${res}`).value) || 0;
        if (count > 0) {
            selected[res] = count;
            total += count;
        }
    });
    
    if (total !== 2) {
        displayError('Please select exactly 2 resources');
        return;
    }
    
    emitGame('use_invention', {
        name: currentUser,
        resources: selected
    });
    
    hideInventionModal();
}

/**
 * Show monopoly modal (for Monopoly card)
 */
function showMonopolyModal() {
    monopolyModal.classList.remove('hidden');
    monopolyModal.classList.add('show');
}

/**
 * Hide monopoly modal
 */
function hideMonopolyModal() {
    monopolyModal.classList.remove('show');
    monopolyModal.classList.add('hidden');
}

/**
 * Confirm monopoly - steal resource from all players
 */
function confirmMonopoly(resourceType) {
    emitGame('use_monopoly', {
        name: currentUser,
        resource_type: resourceType
    });
    
    hideMonopolyModal();
}

/**
 * Cancel your trade offer
 */
function cancelTrade(offerId) {
    emitGame('cancel_trade', {
        name: currentUser,
        offer_id: offerId
    });
}

/**
 * Complete trade with selected player
 */
function completeTrade(offerId, responder) {
    emitGame('complete_trade', {
        name: currentUser,
        offer_id: offerId,
        selected_responder: responder
    });
}

// Trade modal event listeners
if (proposeTradeBtn) proposeTradeBtn.addEventListener('click', showTradeModal);
if (closeTradeModal) closeTradeModal.addEventListener('click', hideTradeModal);
if (submitTradeBtn) submitTradeBtn.addEventListener('click', submitTrade);
if (tradeModal) tradeModal.addEventListener('click', (e) => {
    if (e.target === tradeModal) hideTradeModal();
});

// Invention modal event listeners
if (closeInventionModal) closeInventionModal.addEventListener('click', hideInventionModal);
if (inventionModal) inventionModal.addEventListener('click', (e) => {
    if (e.target === inventionModal) hideInventionModal();
});
if (confirmInventionBtn) confirmInventionBtn.addEventListener('click', confirmInvention);

// Monopoly modal event listeners
if (closeMonopolyModal) closeMonopolyModal.addEventListener('click', hideMonopolyModal);
if (monopolyModal) monopolyModal.addEventListener('click', (e) => {
    if (e.target === monopolyModal) hideMonopolyModal();
});
document.querySelectorAll('.monopoly-res-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const resourceType = e.target.getAttribute('data-resource');
        confirmMonopoly(resourceType);
    });
});

/**
 * Update console visibility and button states based on current turn
 */
function updateConsoleVisibility() {
    // Update button colors based on current player
    updateButtonColors();
    
    // Show/hide trade button based on turn
    if (currentRole !== 'observer' && currentUser === currentPlayer) {
        proposeTradeBtn.style.display = 'inline-block';
    } else {
        proposeTradeBtn.style.display = 'none';
    }
    
    if (currentRole === 'observer') {
        gameConsole.classList.add('hidden');
    } else if (currentUser === currentPlayer) {
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
        nextTurnBtn.textContent = `Waiting for ${currentPlayer}...`;
        colorPicker.style.display = 'inline-block';
        placeSettlementBtn.style.display = 'inline-block';
        placeRoadBtn.style.display = 'inline-block';
        upgradeCityBtn.style.display = 'inline-block';
    }
    
    // Reset building selection when turn changes
    selectedBuilding = null;
    placeSettlementBtn.classList.remove('active');
    placeRoadBtn.classList.remove('active');
    upgradeCityBtn.classList.remove('active');
    gameBoard.classList.remove('placement-mode');
    syncCkModeButtons();
}

/**
 * Update button colors and title based on current user
 */
function updateButtonColors() {
    const buttons = [rollDiceBtn, placeSettlementBtn, placeRoadBtn, upgradeCityBtn, nextTurnBtn];
    const currentUserData = currentBoardData?.players?.find(p => p.name === currentUser);
    const playerColor = currentUserData?.color || '#e67e22';
    const textColor = getContrastColor(playerColor);
    
    // Use player's color only when it's their turn, otherwise use default
    const isMyTurn = currentUser === currentPlayer;
    const activeColor = isMyTurn ? playerColor : '#7f8c8d';
    const activeTextColor = isMyTurn ? textColor : '#ffffff';
    
    buttons.forEach(btn => {
        btn.style.backgroundColor = activeColor;
        btn.style.color = activeTextColor;
    });
    
    // Update title color
    if (gameTitle) {
        gameTitle.style.color = playerColor;
    }
}

/**
 * Update timer displays based on board data
 */
function updateTimers(boardData) {
    if (!boardData || !diceTimerEl || !roundTimerEl) return;
    
    // Only show timers in playing phase
    if (boardData.game_phase === 'setup') {
        diceTimerEl.textContent = 'Dice: -';
        roundTimerEl.textContent = 'Round: -';
        if (diceTimerInterval) clearInterval(diceTimerInterval);
        return;
    }
    
    lastDiceTime = boardData.dice_roll_time || 15;
    lastRoundTime = boardData.round_time || 120;
    lastUpdateTime = Date.now();
    const hasRolled = boardData.has_rolled_dice;
    
    // Dice timer - only show if hasn't rolled yet
    if (hasRolled) {
        diceTimerEl.textContent = 'Dice: -';
        diceTimerEl.className = 'timer';
    } else {
        diceTimerEl.textContent = `Dice: ${lastDiceTime}s`;
        diceTimerEl.className = 'timer' + (lastDiceTime <= 5 ? ' danger' : lastDiceTime <= 10 ? ' warning' : '');
    }
    
    // Round timer - only show after dice rolled
    if (hasRolled) {
        roundTimerEl.textContent = `Round: ${lastRoundTime}s`;
        roundTimerEl.className = 'timer' + (lastRoundTime <= 30 ? ' danger' : lastRoundTime <= 60 ? ' warning' : '');
    } else {
        roundTimerEl.textContent = 'Round: -';
        roundTimerEl.className = 'timer';
    }
    
    // Start timer interval if it's player's turn and playing phase
    if (boardData.game_phase === 'playing' && currentPlayer === currentUser) {
        startTimerInterval();
    } else {
        if (diceTimerInterval) clearInterval(diceTimerInterval);
    }
}

function startTimerInterval() {
    if (diceTimerInterval) clearInterval(diceTimerInterval);
    
    diceTimerInterval = setInterval(() => {
        if (!gameStarted || currentPlayer !== currentUser || currentBoardData?.game_phase === 'setup') {
            clearInterval(diceTimerInterval);
            return;
        }
        
        const elapsed = Math.floor((Date.now() - lastUpdateTime) / 1000);
        
        // Calculate current times
        const currentDiceTime = Math.max(0, lastDiceTime - elapsed);
        const currentRoundTime = Math.max(0, lastRoundTime - elapsed);
        const hasRolled = currentBoardData?.has_rolled_dice;

        // Display only: the server owns turn expiry. A client-side auto-emit
        // here would play the turn from a backgrounded tab.

        // Update dice timer display
        if (hasRolled) {
            diceTimerEl.textContent = 'Dice: -';
            diceTimerEl.className = 'timer';
        } else {
            diceTimerEl.textContent = `Dice: ${currentDiceTime}s`;
            diceTimerEl.className = 'timer' + (currentDiceTime <= 5 ? ' danger' : currentDiceTime <= 10 ? ' warning' : '');
        }
        
        // Update round timer display (only after dice rolled)
        if (hasRolled) {
            roundTimerEl.textContent = `Round: ${currentRoundTime}s`;
            roundTimerEl.className = 'timer' + (currentRoundTime <= 30 ? ' danger' : currentRoundTime <= 60 ? ' warning' : '');
        } else {
            roundTimerEl.textContent = 'Round: -';
            roundTimerEl.className = 'timer';
        }
    }, 1000);
}

// Chat and event log
//
// One list holds chat and system events interleaved. Every entry is built with
// createElement + textContent: a player name or message containing markup must
// render as literal text, and innerHTML anywhere in here would execute it.

// Mirrors KINDS in server/game/event_log.py. An entry whose kind is not in this
// list still renders, tagged as a plain game event - a kind straight from the
// wire must never reach a class name unchecked.
const LOG_KINDS = [
    'chat', 'dice', 'build', 'trade', 'robber', 'dev_card', 'turn', 'game', 'rules'
];

// How far from the bottom still counts as "reading the newest entries".
const LOG_BOTTOM_SLACK_PX = 24;

/**
 * Format a server timestamp as a short local HH:MM:SS.
 *
 * @param {number} at - Epoch seconds, as generated by the server
 * @returns {string}
 */
function formatLogTime(at) {
    const date = new Date(at * 1000);
    if (Number.isNaN(date.getTime())) {
        return '--:--:--';
    }
    const pad = (value) => String(value).padStart(2, '0');
    return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

/**
 * Guard the shape of one entry before it reaches the DOM.
 */
function isValidLogEntry(entry) {
    return Boolean(entry)
        && typeof entry === 'object'
        && Number.isInteger(entry.id)
        && typeof entry.at === 'number'
        && typeof entry.kind === 'string'
        && typeof entry.text === 'string';
}

/**
 * Whether the player is looking at the newest entries rather than history.
 */
function isLogScrolledToBottom() {
    if (!logEntriesDiv) {
        return true;
    }
    const distance = logEntriesDiv.scrollHeight
        - logEntriesDiv.scrollTop
        - logEntriesDiv.clientHeight;
    return distance <= LOG_BOTTOM_SLACK_PX;
}

/**
 * Jump to the newest entry and drop the "new messages" affordance.
 */
function scrollLogToBottom() {
    if (!logEntriesDiv) {
        return;
    }
    logEntriesDiv.scrollTop = logEntriesDiv.scrollHeight;
    logJumpBtn?.classList.add('hidden');
}

/**
 * Build the DOM for one log entry.
 *
 * @param {object} entry - A validated entry from the server
 * @returns {HTMLElement}
 */
function buildLogEntryNode(entry) {
    const kind = LOG_KINDS.includes(entry.kind) ? entry.kind : 'game';
    const row = document.createElement('div');
    row.className = `log-entry log-kind-${kind} ${kind === 'chat' ? 'log-chat' : 'log-system'}`;
    row.dataset.logId = String(entry.id);

    const time = document.createElement('span');
    time.className = 'log-time';
    time.textContent = formatLogTime(entry.at);
    row.appendChild(time);

    // Only chat is attributed here; a system entry's text already names the
    // player it is about ("Alice rolled 7").
    if (kind === 'chat' && typeof entry.player === 'string' && entry.player) {
        const who = document.createElement('span');
        who.className = 'log-player';
        who.textContent = `${entry.player}:`;
        row.appendChild(who);
    }

    const text = document.createElement('span');
    text.className = 'log-text';
    text.textContent = entry.text;
    row.appendChild(text);

    return row;
}

/**
 * Append entries to the log, skipping anything already shown.
 *
 * Ids are monotonic, so an entry at or below the highest id we have rendered
 * is a duplicate from a reconnect catch-up and is dropped rather than shown
 * twice.
 *
 * @param {Array<object>} entries - Entries in chronological order
 */
function appendLogEntries(entries) {
    if (!logEntriesDiv || !Array.isArray(entries)) {
        return;
    }

    const fragment = document.createDocumentFragment();
    let appended = 0;

    for (const entry of entries) {
        if (!isValidLogEntry(entry)) {
            console.warn('Ignoring malformed log entry:', entry);
            continue;
        }
        if (entry.id <= highestLogId) {
            continue;
        }
        highestLogId = entry.id;
        fragment.appendChild(buildLogEntryNode(entry));
        appended += 1;
    }

    if (appended === 0) {
        return;
    }

    // Read the scroll position before writing: appending changes scrollHeight,
    // after which everyone looks scrolled up.
    const wasAtBottom = isLogScrolledToBottom();
    logEntriesDiv.appendChild(fragment);

    if (wasAtBottom) {
        scrollLogToBottom();
    } else {
        // Someone is reading history - offer the jump instead of yanking them.
        logJumpBtn?.classList.remove('hidden');
    }

    // An entry that lands while the trade tab is showing would otherwise be
    // silent, which reads as "chat does not work"
    if (logTabBadge && logTabBtn?.getAttribute('aria-selected') !== 'true') {
        logTabBadge.classList.remove('hidden');
    }
}

/**
 * Ask the server for everything logged since the newest entry we hold.
 * Safe to call on every connect: an already-current client gets an empty list.
 */
function requestLogCatchUp() {
    if (!socket.connected) {
        return;
    }
    socket.emit('request_log', { after_id: highestLogId });
}

/**
 * Notice from a board payload that we missed entries, and fetch the gap.
 *
 * @param {object} data - A `board_updated` or `game_state` payload
 */
function checkLogGap(data) {
    const lastId = data?.log_last_id ?? data?.board?.log_last_id;
    if (Number.isInteger(lastId) && lastId > highestLogId) {
        requestLogCatchUp();
    }
}

/**
 * Chat is unusable while the socket is down - say so rather than dropping
 * messages silently.
 */
function updateChatAvailability() {
    const online = socket.connected === true;
    if (chatInput) {
        chatInput.disabled = !online;
        chatInput.placeholder = online ? 'Say something…' : 'Reconnecting…';
    }
    if (chatSendBtn) {
        chatSendBtn.disabled = !online;
    }
}

/**
 * Send whatever is in the chat box. The server sanitizes and may still refuse;
 * the trim here only avoids a round trip for an empty box.
 */
function sendChatMessage() {
    if (!chatInput) {
        return;
    }
    const text = chatInput.value.trim();
    if (!text) {
        return;
    }
    if (!emitGame('chat_message', { text: text })) {
        return;
    }
    chatInput.value = '';
}

if (chatForm) {
    chatForm.addEventListener('submit', (event) => {
        // Enter in the input submits the form; without this the page reloads.
        event.preventDefault();
        sendChatMessage();
    });
}

if (logJumpBtn) {
    logJumpBtn.addEventListener('click', scrollLogToBottom);
}

if (logEntriesDiv) {
    logEntriesDiv.addEventListener('scroll', () => {
        if (isLogScrolledToBottom()) {
            logJumpBtn?.classList.add('hidden');
        }
    }, { passive: true });
}

updateChatAvailability();

// Side panel tabs
//
// The log and the trade panel are both long, variable-length lists that are
// only sometimes read, so they share one box instead of costing two columns.
// Nothing about either panel's content changes here - only which one is shown.

/**
 * Show one tab's panel and hide the others.
 *
 * @param {HTMLElement} tab - The tab button to select
 */
function selectSideTab(tab) {
    if (!sideTabs || !tab) {
        return;
    }

    sideTabs.querySelectorAll('[role="tab"]').forEach(button => {
        const selected = button === tab;
        button.setAttribute('aria-selected', selected ? 'true' : 'false');
        const panel = document.getElementById(button.getAttribute('aria-controls'));
        if (panel) {
            panel.hidden = !selected;
        }
    });

    if (tab === tradeTabBtn) {
        tradeTabBadge?.classList.add('hidden');
    }
    if (tab === logTabBtn) {
        logTabBadge?.classList.add('hidden');
        // A hidden panel has no scroll height, so the log has to be pinned to
        // the newest entry once it is on screen again
        scrollLogToBottom();
    }
}

/**
 * Flag the trade tab when there are offers to look at and it is not showing.
 * Without this, tabbing away from trade would hide an offer that expires in
 * ten seconds.
 *
 * @param {number} count - Offers currently listed in the trade panel
 */
function updateTradeTabBadge(count) {
    if (!tradeTabBadge || !tradeTabBtn) {
        return;
    }
    const showing = tradeTabBtn.getAttribute('aria-selected') === 'true';
    tradeTabBadge.classList.toggle('hidden', count === 0 || showing);
}

if (sideTabs) {
    sideTabs.addEventListener('click', (event) => {
        const tab = event.target.closest('[role="tab"]');
        if (tab) {
            selectSideTab(tab);
        }
    });

    // Arrow keys move between tabs - the expected behaviour for a tablist
    sideTabs.addEventListener('keydown', (event) => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
            return;
        }
        const tabs = Array.from(sideTabs.querySelectorAll('[role="tab"]'));
        const index = tabs.indexOf(event.target.closest('[role="tab"]'));
        if (index === -1) {
            return;
        }
        const step = event.key === 'ArrowRight' ? 1 : -1;
        const next = tabs[(index + step + tabs.length) % tabs.length];
        selectSideTab(next);
        next.focus();
    });
}

// Socket event handlers

socket.on('rules_changed', (data) => {
    if (!data || !Array.isArray(data.catalogue) || typeof data.selected !== 'object') {
        console.warn('Ignoring malformed rules_changed payload:', data);
        return;
    }

    rulesCatalogue = data.catalogue;
    rulesSelected = data.selected || {};
    rulesLocked = data.locked === true;
    renderRulesPanel();
    renderActiveRules();
});

socket.on('user_list', (data) => {
    renderUserList(data);
    updateStartButton();
});

socket.on('game_started', (data) => {
    gameStarted = true;
    currentPlayer = data.current_player;
    currentRole = 'player';
    hasRolledDice = false;
    userScreen.classList.add('hidden');
    gameScreen.classList.remove('hidden');
    
    // Store board data first so renderGameSidebar can access player colors
    currentBoardData = data.board;
    setHighlight(null);

    renderGameSidebar({ players: data.board.players });
    updateConsoleVisibility();
    
    // Set color picker to current user's color
    const currentPlayerData = data.board?.players?.find(p => p.name === currentUser);
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
    if (currentPlayer === currentUser) {
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
    // Without this guard that snapshot flipped gameStarted to true and then
    // threw on the missing players list, which left the lobby wedged with the
    // Start Game button hidden.
    if (!data.in_game) {
        gameStarted = false;
        currentPlayer = null;
        currentBoardData = null;
        gameScreen.classList.add('hidden');
        userScreen.classList.remove('hidden');
        updateStartButton();
        return;
    }

    gameStarted = true;
    currentPlayer = data.current_player;
    if (data.players.includes(currentUser)) {
        currentRole = 'player';
    } else {
        currentRole = 'observer';
    }
    userScreen.classList.add('hidden');
    gameScreen.classList.remove('hidden');
    renderGameSidebar({ players: data.players });
    updateConsoleVisibility();
    
    // Store board data and render
    currentBoardData = data.board;
    if (data.board) {
        setHighlight(null);
        renderResourcePanel();
        renderBank();
        renderDevCards();
        renderActiveRules();
        renderCitiesKnights();
    }

    // Set color picker to current user's color
    const currentPlayerData = data.board?.players?.find(p => p.name === currentUser);
    if (currentPlayerData?.color) {
        colorPicker.value = currentPlayerData.color;
    }
    
    // Update button colors
    updateButtonColors();
    checkLogGap(data);

    console.log('Reconnected to game. Current player:', data.current_player);
});

socket.on('turn_changed', (data) => {
    const wasMyTurn = currentPlayer === currentUser;
    currentPlayer = data.current_player;
    renderGameSidebar({ players: data.players });
    updateConsoleVisibility();
    renderResourcePanel();
    // Whose turn it is decides what every Cities & Knights button says
    renderCitiesKnights();
    console.log('Turn changed. Current player:', data.current_player);
    hasRolledDice = false;
    
    // Update timers from server data
    if (data.dice_roll_time !== undefined) {
        lastDiceTime = data.dice_roll_time;
        lastRoundTime = data.round_time;
        lastUpdateTime = Date.now();
        currentBoardData = currentBoardData || {};
        currentBoardData.has_rolled_dice = data.has_rolled_dice;
        startTimerInterval();
    }
    
    // Play sound if it's now my turn
    if (currentPlayer === currentUser && !wasMyTurn) {
        turnSound.play().catch(e => console.log('Could not play sound:', e));
    }
    
    // Enable dice button for the current player
    if (currentPlayer === currentUser) {
        rollDiceBtn.disabled = false;
        rollDiceBtn.textContent = 'Roll Dice';
        diceDisplay.innerHTML = '';
    }
});

socket.on('player_color_changed', (data) => {
    console.log(`Player ${data.name} changed color to ${data.color}`);
    if (data.name === currentUser) {
        colorPicker.value = data.color;
    }
    // Update player color in currentBoardData before re-rendering
    if (currentBoardData && currentBoardData.players) {
        for (const player of currentBoardData.players) {
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
    if (currentPlayer) {
        renderGameSidebar({ players: currentBoardData?.players?.map(p => p.name) || [] });
    }
});

socket.on('dice_rolled', (data) => {
    console.log(`Player ${data.player} rolled ${data.dice1} + ${data.dice2} = ${data.total}`);
    diceDisplay.innerHTML = `<span class="die">${data.dice1}</span><span class="die">${data.dice2}</span>`;
    rollDiceBtn.disabled = true;
    rollDiceBtn.textContent = `Rolled: ${data.total}`;
    hasRolledDice = true;
    
    // Highlight hexes matching the rolled number
    setHighlight(data.total);

    // Clear highlight after 2 seconds
    setTimeout(() => setHighlight(null), 2000);
});

socket.on('board_updated', (data) => {
    console.log('Board updated');
    currentBoardData = data.board;
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
    if (data.card_type === 'invention' && data.needs_resources && data.player === currentUser) {
        showInventionModal();
    }
    if (data.card_type === 'monopoly' && data.needs_resource && data.player === currentUser) {
        showMonopolyModal();
    }
});

socket.on('game_won', (data) => {
    console.log('Game won:', data);
    showNotice(`🎉 GAME OVER! ${data.player} wins with ${data.victory_points} victory points!`, 'success', true);
    // Optionally disable game interactions
    gameStarted = false;
});

socket.on('game_ended', (data) => {
    // The server follows this with a fresh user_list and rules_changed, so the
    // lobby - including the rules panel - comes back unlocked on its own
    returnToLobby();
    showNotice(`Game ended by ${data?.by || 'a player'}.`, 'info');
});

socket.on('trade_proposed', (data) => {
    console.log('Trade proposed:', data.offer);
    if (currentBoardData && currentBoardData.trades) {
        currentBoardData.trades.active.push(data.offer);
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
    if (data.player === currentUser) {
        mustDiscard = true;
        discardAmount = data.amount;
        discardAmountSpan.textContent = discardAmount;
        
        // Reset discard inputs
        document.getElementById('discard-wood').value = 0;
        document.getElementById('discard-brick').value = 0;
        document.getElementById('discard-sheep').value = 0;
        document.getElementById('discard-wheat').value = 0;
        document.getElementById('discard-ore').value = 0;
        
        discardModal.classList.add('show');
    }
});

socket.on('discard_completed', (data) => {
    console.log('Discard completed:', data);
    if (data.player === currentUser) {
        mustDiscard = false;
        discardAmount = 0;
        discardModal.classList.remove('show');
    }
});

socket.on('choose_victim', (data) => {
    console.log('Choose victim event received:', data);
    console.log('currentUser:', currentUser, 'currentPlayer:', currentPlayer);
    
    if (currentUser === currentPlayer) {
        mustChooseVictim = true;
        robberVictims = data.victims || [];
        console.log('Should show modal now, victims:', robberVictims);
        
        renderVictimList();
        victimModal.classList.remove('hidden');
        victimModal.classList.add('show');
    } else {
        console.log('Not current player, skipping modal');
    }
});

socket.on('resource_stolen', (data) => {
    console.log('Resource stolen:', data);
    if (data.victim === currentUser) {
        showNotice(`Player ${data.player} stole 1 ${data.resource} from you!`, 'info');
    } else {
        logToGameConsole(`Player ${data.player} stole 1 ${data.resource} from ${data.victim}`);
    }
});

function renderVictimList() {
    victimList.innerHTML = '';
    
    const players = currentBoardData?.players || [];
    
    robberVictims.forEach(victimName => {
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
    emitGame('choose_robber_victim', { name: currentUser, victim: item.dataset.victim });
    victimModal.classList.remove('show');
    mustChooseVictim = false;
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
    
    if (total !== discardAmount) {
        displayError(`You must discard exactly ${discardAmount} cards`);
        return;
    }
    
    emitGame('discard_resources', { name: currentUser, resources: resources });
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

/**
 * Update the visible connection indicator.
 *
 * @param {string} state - 'connected', 'connecting' or 'offline'
 * @param {string} label - Text to show
 */
function setConnectionStatus(state, label) {
    if (!connectionStatus) {
        return;
    }
    connectionStatus.className = `connection-status connection-${state}`;
    connectionStatus.textContent = label;
}

socket.on('connect', () => {
    setConnectionStatus('connected', 'Connected');
    updateChatAvailability();
    if (currentUser) {
        // Re-join on every reconnect - the server replies with a full snapshot.
        // takeover: true because this IS the same player reclaiming their own
        // seat; the server may still be holding the dropped socket's binding.
        socket.emit('join', {
            name: currentUser, role: currentRole, color: currentColor, takeover: true
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

// Resize handling - the buffer must be re-sized for the new box, but drawing
// belongs to the render loop, so only mark dirty here
window.addEventListener('resize', markDirty);

// devicePixelRatio can change without a resize event (moving to another monitor)
if (window.matchMedia) {
    window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`)
        .addEventListener('change', markDirty);
}

// Last-resort nets: an exception in a handler or a rejected promise otherwise
// leaves the player with a frozen board and no explanation
window.addEventListener('error', (event) => {
    console.error('Uncaught error:', event.error || event.message);
    displayError('Something went wrong. Reload the page if the game stops responding.');
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled rejection:', event.reason);
    displayError('Something went wrong. Reload the page if the game stops responding.');
});

if (!socketAvailable) {
    // The template's own onerror banner explains this one to the player
    console.error('Socket.IO library is unavailable - the client cannot connect.');
    setConnectionStatus('offline', 'Offline');
    document.getElementById('cdn-error')?.classList.remove('hidden');
} else {
    setConnectionStatus('connecting', 'Connecting…');
}

// Read-only debug hook. Part IV of coding-rules.md asks for a way to dump the
// client's state on demand: reproducing a bug from one snapshot is far cheaper
// than reproducing it from a sequence of clicks, and the browser playthrough
// tests need to know which vertices are legal before they can click one.
window.__catanDebug = {
    getBoard: () => currentBoardData,
    getUser: () => currentUser,
    getRole: () => currentRole,
    getCurrentPlayer: () => currentPlayer,
    isGameStarted: () => gameStarted,
};
