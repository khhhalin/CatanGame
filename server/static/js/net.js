// Everything the server says, in one place.
//
// A handler here validates the payload, hands it to the store, and asks the
// panels to redraw. Nothing else in the client registers a socket listener, so
// the full set of server events is this file's table of contents.

import { markDirty, setHighlight } from './board.js';
import { noteBuild, renderChangelog } from './changelog.js';
import { renderPendingChoices } from './choices.js';
import { describeLastAttack, noteBarbarianAttack, renderCitiesKnights } from './cities-knights.js';
import { setCommandCatalogue } from './commands.js';
import { colorPicker, diceDisplay, discardModal, gameScreen, rollDiceBtn, userScreen, victimModal } from './dom.js';
import { appendCommandResult, appendLogEntries, checkLogGap, requestLogCatchUp, updateChatAvailability } from './event-log.js';
import { handleNameTaken, renderActiveRules, renderDiceSet, renderRulesPanel, renderUserList, returnToLobby, updateStartButton } from './lobby.js';
import { displayError, logToGameConsole, showNotice } from './notices.js';
import { offerVictimChoice, openDiscardModal, renderBank, renderDevCards, renderGameSidebar, renderResourcePanel, updateButtonColors, updateConsoleVisibility, updateGameUI } from './panels.js';
import { renderExplorersAndPirates } from './ep.js';
import { renderFishermen } from './fish.js';
import { renderRivers } from './rivers.js';
import { renderCaravans } from './caravans.js';
import { renderWonders } from './wonders.js';
import { renderBarbarianAttack } from './barbarian_attack.js';
import { renderPirateIslands } from './pirate_islands.js';
import { renderOil } from './oil.js';
import { renderFrenemies } from './frenemies.js';
import { renderHelperTiles } from './helper_tiles.js';
import { renderTbMain } from './tb_main.js';
import { renderSeafarers } from './seafarers.js';
import { forgetPlacements, notePlacements, playTurnSound } from './sound.js';
import { setConnectionStatus, socket, socketAvailable } from './socket.js';
import { applyBoardFacts, getBoard, getCurrentPlayer, getRole, isMyTurn, setRoster, viewState } from './state.js';
import { noteServerClocks, updateTimers } from './timers.js';
import { renderTradeOffers, showInventionModal, showMonopolyModal } from './trade.js';

// Socket event handlers

socket.on('rules_changed', (data) => {
    if (!data || !Array.isArray(data.catalogue) || typeof data.selected !== 'object') {
        console.warn('Ignoring malformed rules_changed payload:', data);
        return;
    }

    viewState.server.rules.catalogue = data.catalogue;
    viewState.server.rules.presets = Array.isArray(data.presets) ? data.presets : [];
    viewState.server.rules.exclusions = Array.isArray(data.exclusions) ? data.exclusions : [];
    viewState.server.rules.selected = data.selected || {};
    viewState.server.rules.locked = data.locked === true;
    renderRulesPanel();
    renderActiveRules();
    renderDiceSet();
});

// The command bar renders from this and knows no command name of its own, for
// the same reason the rules picker renders from the rule catalogue.
socket.on('commands_changed', (data) => {
    setCommandCatalogue(data);
});

// One command's reply, to the socket that typed it. Rendered into the log as a
// private line - it is an answer, not history.
socket.on('command_result', (data) => {
    if (!data || !Array.isArray(data.lines)) {
        console.warn('Ignoring malformed command_result payload:', data);
        return;
    }
    appendCommandResult(data.lines);
});

// The changelog and the build that served it. Asked for on every connect, in
// the lobby as well as in a game: a tester who has not joined yet still has to
// be able to read which build they are looking at.
socket.on('changelog', (data) => {
    renderChangelog(data);
});

socket.on('user_list', (data) => {
    setRoster(data.players, data.observers, data.min_players, data.max_players);
    renderUserList();
    updateStartButton();
});

socket.on('game_started', (data) => {
    noteBuild(data.build);
    // The board payload is what every later question is answered from, so it
    // goes in before anything renders. The roster decides whether this tab is
    // playing or watching - the server seats people, the client does not.
    viewState.server.board = data.board;
    viewState.winnerAnnounced = false;
    setRoster(data.players, data.observers);
    userScreen.classList.add('hidden');
    gameScreen.classList.remove('hidden');
    setHighlight(null);
    // The first payload of a game is the state to start from, not a board's
    // worth of placements to announce.
    forgetPlacements();
    notePlacements(data.board);

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
    
    // Two physical dice are on screen for every seat from the first frame -
    // resting until the roll that fills them.
    showRestingDice();

    // Enable dice button for the first player
    if (isMyTurn()) {
        rollDiceBtn.disabled = false;
        rollDiceBtn.textContent = 'Roll Dice';
    }

    // Render dev cards
    renderDevCards();

    // Commodities, improvements, knights and the barbarian clock - or nothing
    // at all, in a base game
    renderCitiesKnights();
    renderSeafarers();
    renderExplorersAndPirates();
    renderFishermen();
    renderRivers();
    renderCaravans();
    renderWonders();
    renderBarbarianAttack();
    renderPirateIslands();
    renderOil();
    renderFrenemies();
    renderHelperTiles();
    renderTbMain();
    renderPendingChoices();

    // Show what the table agreed to before the game began
    renderActiveRules();
    renderDiceSet();

    console.log('Game started! Player order:', data.players);
    console.log('Current player:', data.current_player);
});

socket.on('game_state', (data) => {
    noteBuild(data.build);
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
    // A join into a running game arrives here, not through `game_started`.
    // Without this baseline the next piece anyone placed would be the payload
    // that set it, and it would go down in silence.
    forgetPlacements();
    notePlacements(data.board);
    setRoster(data.players, data.observers);
    userScreen.classList.add('hidden');
    gameScreen.classList.remove('hidden');
    renderGameSidebar({ players: data.players });
    updateConsoleVisibility();

    if (data.board) {
        setHighlight(null);
        // The faces of the last roll are not in the snapshot, so a reconnect
        // returns the dice to rest rather than leaving the slot empty.
        showRestingDice();
        renderResourcePanel();
        renderBank();
        renderDevCards();
        renderActiveRules();
        renderDiceSet();
        renderCitiesKnights();
        renderSeafarers();
        renderExplorersAndPirates();
    renderFishermen();
    renderRivers();
    renderCaravans();
    renderWonders();
    renderBarbarianAttack();
    renderPirateIslands();
    renderOil();
    renderFrenemies();
    renderHelperTiles();
    renderTbMain();
        // A reload or a reconnect in the middle of a question: the snapshot
        // carries the open choice, so the player is asked again rather than
        // returning to a table that has silently stopped.
        renderPendingChoices();
    }

    // Set color picker to current user's color
    const currentPlayerData = data.board?.players?.find(p => p.name === viewState.identity.name);
    if (currentPlayerData?.color) {
        colorPicker.value = currentPlayerData.color;
    }
    
    // Update button colors
    updateButtonColors();
    updateGameUI(data.board);
    updateTimers(data.board);
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
    renderSeafarers();
    renderExplorersAndPirates();
    renderFishermen();
    renderRivers();
    renderCaravans();
    renderWonders();
    renderBarbarianAttack();
    renderPirateIslands();
    renderOil();
    renderFrenemies();
    renderHelperTiles();
    renderTbMain();
    console.log('Turn changed. Current player:', data.current_player);

    // `turn_changed` carries the fresh clocks a fraction before the board
    // broadcast that repeats them, so record them the moment they land.
    noteServerClocks(data);
    updateTimers();

    // A new turn has not rolled yet: reset every seat's dice to rest.
    showRestingDice();

    // Play sound if it's now my turn
    if (isMyTurn() && !wasMyTurn) {
        playTurnSound();
    }

    // Enable dice button for the current player
    if (isMyTurn()) {
        rollDiceBtn.disabled = false;
        rollDiceBtn.textContent = 'Roll Dice';
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

// Pip positions for each face on a 30x30 die, on a 9/15/21 three-by-three grid.
// A real die shows dots, not a printed number, so a rolled face is drawn as its
// pips rather than written out.
const DIE_PIPS = {
    1: [[15, 15]],
    2: [[9, 9], [21, 21]],
    3: [[9, 9], [15, 15], [21, 21]],
    4: [[9, 9], [21, 9], [9, 21], [21, 21]],
    5: [[9, 9], [21, 9], [15, 15], [9, 21], [21, 21]],
    6: [[9, 9], [21, 9], [9, 15], [21, 15], [9, 21], [21, 21]],
};

// One physical die as an SVG: ivory rounded face, dark pips laid out for the
// value. `data-value` and the label carry the number for tests and readers a
// glance at the dots cannot serve.
function dieSvg(value) {
    const pips = (DIE_PIPS[value] || [])
        .map(([cx, cy]) => `<circle class="pip" cx="${cx}" cy="${cy}" r="2.4" />`)
        .join('');
    return `<svg class="die" data-value="${value}" viewBox="0 0 30 30" width="30" height="30" `
        + `role="img" aria-label="${value}">`
        + `<rect x="1.5" y="1.5" width="27" height="27" rx="7" />${pips}</svg>`;
}

// The physical dice never leave the footer: an empty dice slot was read as the
// dice having vanished. Before a roll they rest on a default pair; a real roll
// overwrites them, and a new turn returns them to rest. `.resting` marks the
// pair as pre-roll so a spectator does not read it as the number just rolled.
const RESTING_FACES = [4, 3];

function showRestingDice() {
    diceDisplay.innerHTML = RESTING_FACES.map(dieSvg).join('');
    diceDisplay.classList.add('resting');
}

socket.on('dice_rolled', (data) => {
    console.log(`Player ${data.player} rolled ${data.dice1} + ${data.dice2} = ${data.total}`);
    diceDisplay.innerHTML = dieSvg(data.dice1) + dieSvg(data.dice2);
    diceDisplay.classList.remove('resting');
    rollDiceBtn.disabled = true;
    rollDiceBtn.textContent = `Rolled: ${data.total}`;
    
    // Highlight hexes matching the rolled number
    setHighlight(data.total);

    // Clear highlight after 2 seconds
    setTimeout(() => setHighlight(null), 2000);
});

socket.on('board_updated', (data) => {
    console.log('Board updated');
    // Every board payload names the build that served it, so a tab open across
    // a deploy is told by the next thing it is sent rather than by the tester
    // thinking to check.
    noteBuild(data.build);
    // Before the payload is stored, so what changed is still answerable.
    notePlacements(data.board);
    viewState.server.board = data.board;
    setHighlight(data.highlight || null);
    renderResourcePanel();
    renderBank();
    renderTradeOffers();
    renderDevCards();
    // The scoreboard used to be redrawn only by `turn_changed`, so points,
    // road lengths, knight counts and the two bonus holders all sat stale
    // until somebody ended a turn - the same defect the tester reported for
    // the barbarian counter. Anything derived from the payload is redrawn when
    // the payload arrives.
    renderGameSidebar({ players: data.board.players });
    updateGameUI(data.board);
    updateButtonColors();
    updateTimers(data.board);
    renderActiveRules();
    // Redrawn on every board payload, not only at the start: the deck it names
    // shrinks by one with each roll.
    renderDiceSet();
    renderCitiesKnights();
    renderSeafarers();
    renderExplorersAndPirates();
    renderFishermen();
    renderRivers();
    renderCaravans();
    renderWonders();
    renderBarbarianAttack();
    renderPirateIslands();
    renderOil();
    renderFrenemies();
    renderHelperTiles();
    renderTbMain();
    renderPendingChoices();
    checkLogGap(data);

    // Clear highlight after 2 seconds if there was one
    if (data.highlight) {
        setTimeout(() => setHighlight(null), 2000);
    }
});

// Cities & Knights rolls an event die on every roll, not only when the
// barbarians move. It arrives before the board broadcast that carries the same
// position, so the track is redrawn twice - the point is that neither redraw
// waits for a turn boundary, which is what made the counter look frozen.
socket.on('event_die', (data) => {
    if (!data || typeof data !== 'object') {
        console.warn('Ignoring malformed event_die payload:', data);
        return;
    }
    if (data.barbarian && typeof data.position === 'number') {
        applyBoardFacts({
            cities_knights: {
                ...(getBoard()?.cities_knights || {}),
                barbarian_position: data.position,
                barbarian_track_length: data.track_length
            }
        });
    }
    renderCitiesKnights();
    renderSeafarers();
    renderExplorersAndPirates();
    renderFishermen();
    renderRivers();
    renderCaravans();
    renderWonders();
    renderBarbarianAttack();
    renderPirateIslands();
    renderOil();
    renderFrenemies();
    renderHelperTiles();
    renderTbMain();
});

// The attack is resolved server-side inside `roll_dice` - there is no phase in
// which a player is asked which city to give up, and the engine picks the
// weakest defender itself. So the only honest thing the client can do is say
// what happened, loudly, and go on restating it in the barbarian panel: this
// message arrives once and no later payload repeats it.
socket.on('barbarian_attack', (data) => {
    noteBarbarianAttack(data);
    const summary = describeLastAttack();
    if (summary) {
        showNotice(summary, data?.won ? 'success' : 'error');
    }
});

// The chooser's own sockets only, and it arrives a fraction before the board
// broadcast that carries the same question redacted for everyone else. The
// panel is drawn from that payload, not from here - this is the nudge, because
// a question that opens while the player is reading the log is otherwise
// silent. Nothing is read out of the event: doing so would give the panel a
// second source that a reload could not reproduce.
socket.on('choice_required', (data) => {
    if (!data || typeof data !== 'object') {
        console.warn('Ignoring malformed choice_required payload:', data);
        return;
    }
    showNotice(`It is your decision: ${data.prompt || 'the game is waiting on you'}.`, 'info');
});

socket.on('choice_resolved', (data) => {
    console.log('Choice resolved:', data);
});

socket.on('progress_card_played', (data) => {
    console.log('Progress card played:', data);
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
    // Cloth for Catan can end with the villages traded out rather than a race to
    // the target, so the banner says which happened when the server names it.
    const reason = data.reason === 'villages_depleted'
        ? ' - the villages traded out their cloth' : '';
    showNotice(`GAME OVER! ${data.player} wins with ${data.victory_points} victory points!${reason}`, 'success', true);
    // A one-shot notice that no later payload repeats, so the win is latched
    // here - it is what stops the turn countdown.
    viewState.winnerAnnounced = true;
});

socket.on('game_ended', (data) => {
    forgetPlacements();
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
        victimModal.classList.remove('hidden');
        // Opens the picker, or - with a single candidate - answers it outright
        // rather than making the player click the only button on offer.
        offerVictimChoice();
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
    // Before the rejoin and outside the `if` below: a socket with no seat is
    // exactly the tab that has been sitting on an old build, and it is entitled
    // to know which build it just reconnected to.
    socket.emit('request_changelog');
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

// Map editor events
socket.on('map_list', (data) => {
    if (!data?.maps) return;
    viewState.server.mapList = data.maps;
    document.dispatchEvent(new CustomEvent('map-list-updated'));
});

socket.on('map_saved', () => {
    showNotice('Map saved', 'success');
});

socket.on('map_deleted', () => {
    showNotice('Map deleted', 'info');
});

socket.on('registry_imported', (data) => {
    showNotice('Registry imported', 'success');
    document.dispatchEvent(new CustomEvent('registry-imported', { detail: data }));
});

socket.on('map_preview', (data) => {
    document.dispatchEvent(new CustomEvent('map-preview-received', { detail: data }));
});

socket.on('map_data', (data) => {
    document.dispatchEvent(new CustomEvent('map-data-received', { detail: data }));
});

if (!socketAvailable) {
    // The template's own onerror banner explains this one to the player
    console.error('Socket.IO library is unavailable - the client cannot connect.');
    setConnectionStatus('offline', 'Offline');
    document.getElementById('cdn-error')?.classList.remove('hidden');
} else {
    setConnectionStatus('connecting', 'Connecting…');
}
