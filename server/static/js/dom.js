// Every element the client touches, looked up once.
//
// These are the page, not state: the template guarantees them, they never
// change, and a module that needs one imports it by name rather than reaching
// for `document` again in the middle of a render.

// DOM elements
export const gameTitle = document.getElementById('game-title');

// DOM elements
export const joinScreen = document.getElementById('join-screen');
export const userScreen = document.getElementById('user-screen');
export const gameScreen = document.getElementById('game-screen');
export const usernameInput = document.getElementById('username');
export const joinBtn = document.getElementById('join-btn');
export const playerList = document.getElementById('players');
export const observerList = document.getElementById('observers');
export const playerCount = document.getElementById('player-count');
const rolePlayer = document.getElementById('role-player');
const roleObserver = document.getElementById('role-observer');
export const joinColorPicker = document.getElementById('join-color-picker');
export const startGameBtn = document.getElementById('start-game-btn');
export const startReasonEl = document.getElementById('start-reason');
export const rulesList = document.getElementById('rules-list');
export const rulesLockedNote = document.getElementById('rules-locked-note');
export const activeRulesPanel = document.getElementById('active-rules-panel');
export const activeRulesDiv = document.getElementById('active-rules');
export const gamePlayersList = document.getElementById('game-players');
export const gameConsole = document.getElementById('game-console');
export const gameBoard = document.getElementById('game-board');
export const nextTurnBtn = document.getElementById('next-turn-btn');
export const endGameBtn = document.getElementById('end-game-btn');
export const colorPicker = document.getElementById('color-picker');
export const placeSettlementBtn = document.getElementById('place-settlement-btn');
export const placeRoadBtn = document.getElementById('place-road-btn');
export const upgradeCityBtn = document.getElementById('upgrade-city-btn');
export const rollDiceBtn = document.getElementById('roll-dice-btn');
export const diceDisplay = document.getElementById('dice-display');
export const resourceDisplay = document.getElementById('resource-display');
export const bankDisplay = document.getElementById('bank-display');
const tradePanel = document.getElementById('trade-panel');
export const proposeTradeBtn = document.getElementById('propose-trade-btn');
export const tradeOffersDiv = document.getElementById('trade-offers');
export const myOffersDiv = document.getElementById('my-offers');
export const tradeModal = document.getElementById('trade-modal');
export const closeTradeModal = document.getElementById('close-trade-modal');
export const submitTradeBtn = document.getElementById('submit-trade-btn');
export const diceTimerEl = document.getElementById('dice-timer');
export const roundTimerEl = document.getElementById('round-timer');
export const buyDevCardBtn = document.getElementById('buy-dev-card-btn');
export const myDevCardsDiv = document.getElementById('my-dev-cards');
export const inventionModal = document.getElementById('invention-modal');
export const closeInventionModal = document.getElementById('close-invention-modal');
export const confirmInventionBtn = document.getElementById('confirm-invention-btn');
export const monopolyModal = document.getElementById('monopoly-modal');
export const closeMonopolyModal = document.getElementById('close-monopoly-modal');

// Notice, connection status and inline hint elements
export const noticeRegion = document.getElementById('notice-region');
export const connectionStatus = document.getElementById('connection-status');
export const robberIndicator = document.getElementById('robber-indicator');
export const devDeckRemaining = document.getElementById('dev-deck-remaining');
export const boardCanvas = document.getElementById('board-canvas');

// Cities & Knights. These panels exist in the template but stay hidden unless
// the running game has the expansion switched on.
export const barbarianPanel = document.getElementById('barbarian-panel');
export const barbarianTrack = document.getElementById('barbarian-track');
export const barbarianStatus = document.getElementById('barbarian-status');
export const barbarianDefense = document.getElementById('barbarian-defense');
export const improvementsPanel = document.getElementById('improvements-panel');
export const improvementTracks = document.getElementById('improvement-tracks');
export const knightsPanel = document.getElementById('knights-panel');
export const knightList = document.getElementById('knight-list');
export const knightHint = document.getElementById('knight-hint');
export const buildKnightBtn = document.getElementById('build-knight-btn');
export const moveKnightBtn = document.getElementById('move-knight-btn');
export const buildWallBtn = document.getElementById('build-wall-btn');

// Discard and victim modal elements
export const discardModal = document.getElementById('discard-modal');
export const victimModal = document.getElementById('victim-modal');
export const victimList = document.getElementById('victim-list');
export const submitDiscardBtn = document.getElementById('submit-discard-btn');
export const discardAmountSpan = document.getElementById('discard-amount');

// Side panel tabs - the log and the trade panel share one box
export const sideTabs = document.getElementById('side-tabs');
export const logTabBtn = document.getElementById('tab-log');
export const tradeTabBtn = document.getElementById('tab-trade');
export const tradeTabBadge = document.getElementById('trade-tab-badge');
export const logTabBadge = document.getElementById('log-tab-badge');

// Chat and event log elements
export const logEntriesDiv = document.getElementById('log-entries');
export const logJumpBtn = document.getElementById('log-jump-btn');
export const chatForm = document.getElementById('chat-form');
export const chatInput = document.getElementById('chat-input');
export const chatSendBtn = document.getElementById('chat-send-btn');

// Turn sound - preload
export const turnSound = new Audio('/static/audio/turn.wav');
turnSound.preload = 'auto';
