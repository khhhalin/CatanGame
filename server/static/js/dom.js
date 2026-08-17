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
export const playerLimit = document.getElementById('player-limit');
const rolePlayer = document.getElementById('role-player');
const roleObserver = document.getElementById('role-observer');
export const joinColorPicker = document.getElementById('join-color-picker');
export const startGameBtn = document.getElementById('start-game-btn');
export const startReasonEl = document.getElementById('start-reason');
export const rulesList = document.getElementById('rules-list');
export const rulePresets = document.getElementById('rule-presets');
export const rulesLockedNote = document.getElementById('rules-locked-note');
// The scenario picker's detail panel: a map thumbnail, the rules the chosen
// scenario turns on, its description, and the rulebook it comes from.
export const scenarioDetail = document.getElementById('scenario-detail');
export const scenarioPreviewCanvas = document.getElementById('scenario-preview-canvas');
export const scenarioPreviewStatus = document.getElementById('scenario-preview-status');
export const scenarioDetailName = document.getElementById('scenario-detail-name');
export const scenarioDetailSummary = document.getElementById('scenario-detail-summary');
export const scenarioDetailRules = document.getElementById('scenario-detail-rules');
export const scenarioDetailSource = document.getElementById('scenario-detail-source');
export const activeRulesPanel = document.getElementById('active-rules-panel');
export const activeRulesDiv = document.getElementById('active-rules');
export const gamePlayersList = document.getElementById('game-players');
export const awardSummary = document.getElementById('award-summary');
export const turnIndicator = document.getElementById('turn-indicator');
export const gameConsole = document.getElementById('game-console');
// The tray's live read-out: the idle hint, or which build the gathered
// materials make. trade.js writes it as the materials shelf changes.
export const trayNote = document.getElementById('tray-note');
export const gameBoard = document.getElementById('game-board');
export const nextTurnBtn = document.getElementById('next-turn-btn');
export const endGameBtn = document.getElementById('end-game-btn');
// The wrapper the turn controls (Next Turn, End Game) now share in the dice
// footer. panels.js hides the pair for an observer through it.
export const turnControls = document.getElementById('turn-controls');
export const colorPicker = document.getElementById('color-picker');
export const placeSettlementBtn = document.getElementById('place-settlement-btn');
export const placeRoadBtn = document.getElementById('place-road-btn');
export const upgradeCityBtn = document.getElementById('upgrade-city-btn');
export const rollDiceBtn = document.getElementById('roll-dice-btn');
export const diceDisplay = document.getElementById('dice-display');
export const diceSetEl = document.getElementById('dice-set');
export const resourceDisplay = document.getElementById('resource-display');
export const bankDisplay = document.getElementById('bank-display');
export const buildCosts = document.getElementById('build-costs');
// The empty slot the foundation left in the bottom tray, above the hand, for
// the trade zone (trade.js builds the offer-builder into it).
export const trayTrade = document.querySelector('.tray-trade');
const tradePanel = document.getElementById('trade-panel');
export const proposeTradeBtn = document.getElementById('propose-trade-btn');
export const tradeOffersDiv = document.getElementById('trade-offers');
export const myOffersDiv = document.getElementById('my-offers');
export const incomingOffers = document.getElementById('incoming-offers');

// Explorers & Pirates panel (right rail), hidden until the table plays it.
export const epPanel = document.getElementById('right-ep');
export const epMissions = document.getElementById('ep-missions');
export const epSupply = document.getElementById('ep-supply');
export const epPlayers = document.getElementById('ep-players');
export const epBuildShipBtn = document.getElementById('ep-build-ship');
export const epMoveShipBtn = document.getElementById('ep-move-ship');
export const epBuildCrewBtn = document.getElementById('ep-build-crew');
export const epBuildSettlerBtn = document.getElementById('ep-build-settler');
export const epLoadCargoBtn = document.getElementById('ep-load-cargo');
export const epUnloadCargoBtn = document.getElementById('ep-unload-cargo');
export const epFoundSettlementBtn = document.getElementById('ep-found-settlement');
export const epMissionBtn = document.getElementById('ep-mission');
export const epRollFishBtn = document.getElementById('ep-roll-fish');
export const epGold = document.getElementById('ep-gold');
export const epSellGoldBtn = document.getElementById('ep-sell-gold');
export const epBuyGoldBtn = document.getElementById('ep-buy-gold');
export const epGoldPick = document.getElementById('ep-gold-pick');
export const tradeModal = document.getElementById('trade-modal');
export const closeTradeModal = document.getElementById('close-trade-modal');
export const submitTradeBtn = document.getElementById('submit-trade-btn');
// What the bank will actually pay this player, and what the numbers they have
// typed will do. See trade.js: the bank takes 4:1 from anyone, so a harbour is
// only worth having if the player can see they hold one.
export const tradeBankRates = document.getElementById('trade-bank-rates');
export const tradeVerdict = document.getElementById('trade-verdict');
// The commodity halves of the two trade rows, shown only when the table plays
// commodities - they trade exactly as resources do.
export const tradeGiveCommodities = document.getElementById('trade-give-commodities');
export const tradeWantCommodities = document.getElementById('trade-want-commodities');
export const tradeSendAnywayBtn = document.getElementById('trade-send-anyway');
export const tradeClearBtn = document.getElementById('trade-clear-btn');
export const diceTimerEl = document.getElementById('dice-timer');
export const roundTimerEl = document.getElementById('round-timer');
export const devCardsPanel = document.getElementById('dev-cards-panel');
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
export const robberText = document.getElementById('robber-text');
export const devDeckRemaining = document.getElementById('dev-deck-remaining');
export const boardCanvas = document.getElementById('board-canvas');

// The ✓/✗ a click raises before a piece is placed, and the personal setting
// that skips it. All three overlay or sit beside the board without ever being
// in flow above it.
export const placementConfirm = document.getElementById('placement-confirm');
export const placementConfirmYes = document.getElementById('placement-confirm-yes');
export const placementConfirmNo = document.getElementById('placement-confirm-no');
export const yoloToggle = document.getElementById('yolo-mode-toggle');
// Silences the placement cues and the turn sound. See sound.js.
export const muteToggle = document.getElementById('mute-toggle');
// The ✓/✗ is raised by a canvas click, which announces nothing on its own.
export const placementAnnounce = document.getElementById('placement-announce');

// Cities & Knights. These panels exist in the template but stay hidden unless
// the running game has the expansion switched on.
export const barbarianPanel = document.getElementById('barbarian-panel');
export const barbarianTrack = document.getElementById('barbarian-track');
export const barbarianStatus = document.getElementById('barbarian-status');
export const barbarianDefense = document.getElementById('barbarian-defense');
export const barbarianLastAttack = document.getElementById('barbarian-last-attack');
export const improvementsPanel = document.getElementById('improvements-panel');
export const improvementTracks = document.getElementById('improvement-tracks');
export const knightsPanel = document.getElementById('knights-panel');
export const knightList = document.getElementById('knight-list');
export const knightHint = document.getElementById('knight-hint');
export const buildKnightBtn = document.getElementById('build-knight-btn');
export const moveKnightBtn = document.getElementById('move-knight-btn');
export const buildWallBtn = document.getElementById('build-wall-btn');
// The actions a tap on your own knight raises, over the piece itself. Like the
// ✓/✗, it overlays the board and is never in flow above it - see
// knight-overlay.js.
export const knightActions = document.getElementById('knight-actions');
export const knightActionButtons = knightActions
    ? Array.from(knightActions.querySelectorAll('[data-knight-overlay]'))
    : [];

// Seafarers. Like the panels above, this one exists in the template but stays
// hidden unless the running game has ships switched on.
export const seafarersPanel = document.getElementById('seafarers-panel');
export const seafarersChipValue = document.getElementById('seafarers-chip-value');
export const buildShipBtn = document.getElementById('build-ship-btn');
export const moveShipBtn = document.getElementById('move-ship-btn');
export const shipHint = document.getElementById('ship-hint');
export const islandPoints = document.getElementById('island-points');

// The chip each folded subject collapses to. Its `-value` span is the summary
// line the player reads without opening anything.
export const barbarianChipValue = document.getElementById('barbarian-chip-value');
export const improvementsChipValue = document.getElementById('improvements-chip-value');
export const knightsChipValue = document.getElementById('knights-chip-value');
export const devCardsChipValue = document.getElementById('dev-cards-chip-value');
export const bankChipValue = document.getElementById('bank-chip-value');
export const costsChipValue = document.getElementById('costs-chip-value');
export const progressCardsPanel = document.getElementById('progress-cards-panel');
export const progressCardsChipValue = document.getElementById('progress-cards-chip-value');
export const progressHandDiv = document.getElementById('progress-hand');
export const activeRulesChipValue = document.getElementById('active-rules-chip-value');

// The pending-choice phase. The panel is the chooser's own question and its
// answers; the indicator is what everyone else is told while the table waits.
// Both overlay the board rather than taking a row of their own - see
// `.board-status` for why anything that resizes the board box is a bug.
export const choicePanel = document.getElementById('choice-panel');
export const choicePrompt = document.getElementById('choice-prompt');
export const choiceContext = document.getElementById('choice-context');
export const choiceOptions = document.getElementById('choice-options');
export const choiceIndicator = document.getElementById('choice-indicator');
export const choiceWaitingText = document.getElementById('choice-waiting-text');

// Discard and victim modal elements
export const discardModal = document.getElementById('discard-modal');
export const victimModal = document.getElementById('victim-modal');
export const victimList = document.getElementById('victim-list');
export const submitDiscardBtn = document.getElementById('submit-discard-btn');
export const discardAmountSpan = document.getElementById('discard-amount');
// Commodities count toward the limit a 7 enforces, so the dialog has a row for
// them - shown only when the table plays them.
export const discardCommodityRow = document.getElementById('discard-commodities');
// Oil counts toward the limit a 7 enforces too, so the dialog has a row for it -
// shown only on an Oil Springs table where the player is actually holding oil.
export const discardOilRow = document.getElementById('discard-oil-row');
// Both dialogs cover the aside the hand panel lives in, so each carries its own
// copy of the hand. panels.js fills the `.resource-display` inside them.
export const discardHandNote = document.getElementById('discard-hand');
export const tradeHandNote = document.getElementById('trade-hand');

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

// The command bar: a listbox over the chat input, filled from the server's
// command catalogue.
export const commandBar = document.getElementById('command-bar');
export const commandList = document.getElementById('command-list');

// Turn sound - preload
export const turnSound = new Audio('/static/audio/turn.wav');
turnSound.preload = 'auto';

// Map editor
export const mapsBtn               = document.getElementById('maps-btn');
export const editorScreen          = document.getElementById('map-editor-screen');
export const editorCanvas          = document.getElementById('editor-canvas');
export const editorPaintBtn        = document.getElementById('editor-paint-btn');
export const editorInspectBtn      = document.getElementById('editor-inspect-btn');
export const editorNullItem        = document.getElementById('editor-null-item');
export const editorRegionList      = document.getElementById('editor-region-list');
export const editorAddRegionBtn    = document.getElementById('editor-add-region-btn');
export const editorRegionPopover   = document.getElementById('editor-region-popover');
export const editorInspectPopover  = document.getElementById('editor-inspect-popover');
export const editorInspectAnchor   = document.getElementById('editor-inspect-anchor');
export const editorClearBtn        = document.getElementById('editor-clear-btn');
export const editorPreviewBtn      = document.getElementById('editor-preview-btn');
export const editorSaveBtn         = document.getElementById('editor-save-btn');
export const editorSavePopover     = document.getElementById('editor-save-popover');
export const editorDoneBtn         = document.getElementById('editor-done-btn');
export const editorStatusEl        = document.getElementById('editor-status');
export const editorResourcesImportBtn   = document.getElementById('editor-resources-import-btn');
export const editorResourcesImportInput = document.getElementById('editor-resources-import-input');
export const editorBuildingsImportBtn   = document.getElementById('editor-buildings-import-btn');
export const editorBuildingsImportInput = document.getElementById('editor-buildings-import-input');
export const editorMapNameInput    = document.getElementById('editor-map-name');
export const editorHarbourCounters = document.getElementById('editor-harbour-counters');
export const editorSaveConfirmBtn  = document.getElementById('editor-save-confirm-btn');
export const editorSaveCopyBtn     = document.getElementById('editor-save-copy-btn');
export const editorMapListEl       = document.getElementById('editor-map-list');
export const editorRadiusSelect    = document.getElementById('editor-radius-select');
