// ------------------------------------------------------------- client state
//
// One object, in two halves.
//
// `server` is the last thing the server said, kept verbatim. Every question the
// server already answers - whose turn it is, whether the dice are up, whether
// the robber or a discard is pending, whether a game is running at all - is
// asked of that half at read time, through the helpers below. Mirroring those
// answers into local flags is what shipped a wedged lobby: a `game_state`
// snapshot that meant "no game is running" was read as "a game started", and
// nothing ever put the flag back.
//
// The rest is genuinely local. Which build button is armed, which knight was
// tapped first, how far the log has been read: the server has no opinion on
// any of it, and no payload can correct it.
export const viewState = {
    server: {
        // The board payload. Null is what "no game is running" means.
        board: null,
        // Who the server seats, and how many it takes to start.
        roster: { players: [], observers: [], minPlayers: 2, maxPlayers: 4 },
        // The lobby rule set, exactly as the server last broadcast it. The
        // client never writes to `selected` itself - a change is emitted and
        // re-read from the `rules_changed` reply, so every table member sees
        // the same thing.
        // `presets` are named sets of individual rules, not modes: picking one
        // ticks its rules and nothing records that it was used.
        rules: { catalogue: [], presets: [], selected: {}, locked: false }
    },

    // What this tab asked to join as. The name is what the player typed; the
    // role and colour are a request, and the roster above is the answer.
    identity: { name: null, requestedRole: null, color: null },

    // 'settlement', 'road', 'city'; with Cities & Knights on - 'knight',
    // 'knight_move' and 'city_wall'; with Seafarers on - 'ship' and
    // 'ship_move'. All of them mean the same thing: the next tap on the board
    // is an intent, not a pan.
    selectedBuilding: null,

    // First half of a knight move. A move is two taps, so the origin has to
    // survive between them.
    knightMoveFrom: null,

    // The same for a ship move: the side the ship was picked up from.
    shipMoveFrom: null,

    // The progress card whose target is being picked on the board, and the
    // targets picked for it so far. Nothing is sent until the last one is in,
    // so a card here is still in the player's hand and cancelling costs them
    // nothing.
    progressPick: { card: null, picked: [] },

    // What the pointer is over, and what a click has offered up for a ✓.
    // Both are `{kind, key, blocked}` or null. `sample` is the raw pointer
    // position, written by pointermove and consumed by the render loop - doing
    // the hit test in the handler would run it far more often than the display
    // can show the result.
    placement: { hover: null, pending: null, sample: null },

    // The gesture in progress on the board, used to tell a tap from a pan.
    pointerDown: null,

    // `game_won` is a one-shot notice that no later payload repeats, so the
    // win has to be latched to stop the turn countdown.
    winnerAnnounced: false,

    // Render loop state - socket handlers set state and mark dirty, never draw.
    render: { dirty: false, highlightNumber: null },

    // `highestId` is what a reconnecting client asks to catch up from, and it
    // is also how a duplicate entry is recognised and dropped.
    log: { highestId: 0 },

    // Rebuilding the rule rows destroys focus and the caret, so they are only
    // rebuilt when the catalogue's shape changes.
    renderedRulesSignature: '',

    // Countdown display only - the server owns expiry. The last `timer` reading
    // it sent, and when it arrived: which clock is running, how much of it is
    // left and how long it was. Null until the first payload says.
    timers: { phase: null, remaining: null, limit: null, updatedAt: Date.now(), handle: null },

    // The once-per-second trade offer countdown.
    tradeTimerHandle: null
};

// ------------------------------------------------ questions the server answers
//
// Each of these reads the stored payload afresh. None of their results may be
// cached in anything that outlives one function call: a cache is a mirror, and
// a mirror is what this section exists to make unnecessary.

/**
 * The board exactly as the server last sent it, or null when no game is on.
 */
export function getBoard() {
    return viewState.server.board;
}

/**
 * What one build costs at this table, or null when the server has not priced it.
 *
 * The prices are the server's, sent with the board and already through every
 * cost modifier the table's rules switched on. The client had its own copy of
 * `server/data/costs.json` until it was deleted: a house rule that changed a
 * price moved the engine's number and not the client's, so the button greyed
 * itself out against a price nobody was charging.
 *
 * @param {string} kind - A build type, as `data/costs.json` names it
 * @returns {object|null} - {resource: amount}
 */
export function getBuildCost(kind) {
    return viewState.server.board?.costs?.[kind] || null;
}

/**
 * Whether there is a game to interact with.
 * A board payload exists for exactly as long as one does - the lobby snapshot
 * and `game_ended` both clear it - and a declared winner ends interaction too.
 */
export function isGameRunning() {
    return viewState.server.board !== null && !viewState.winnerAnnounced;
}

/**
 * 'setup' or 'playing', defaulting to 'playing' the way the payload does.
 */
export function getGamePhase() {
    return viewState.server.board?.game_phase || 'playing';
}

/**
 * Whose turn the server says it is, or null.
 */
export function getCurrentPlayer() {
    return viewState.server.board?.current_player || null;
}

/**
 * Whether the seat this tab is playing is the one on turn.
 */
export function isMyTurn() {
    const me = viewState.identity.name;
    return me !== null && me === getCurrentPlayer();
}

/**
 * Whether the dice are already up this turn.
 */
export function hasRolledDice() {
    return viewState.server.board?.has_rolled_dice === true;
}

/**
 * Whether a 7 has left the robber waiting to be placed.
 */
export function mustMoveRobber() {
    return viewState.server.board?.must_move_robber === true;
}

/**
 * Whether the robber's new hex still needs a victim picked.
 */
export function mustChooseVictim() {
    return viewState.server.board?.must_choose_victim === true;
}

/**
 * Who the robber's hex exposes, as the server worked it out.
 */
export function getRobberVictims() {
    return viewState.server.board?.robber_victims || [];
}

/**
 * How many cards this player owes the bank, or 0.
 */
export function getDiscardAmount() {
    return viewState.server.board?.players_needing_discard?.[viewState.identity.name] || 0;
}

/**
 * The role the server has this player in.
 * Falls back to what the join box asked for until a roster has arrived - a
 * seat is the server's to grant, not the client's to assume.
 */
export function getRole() {
    const roster = viewState.server.roster;
    const me = viewState.identity.name;
    if (roster.players.includes(me)) {
        return 'player';
    }
    if (roster.observers.includes(me)) {
        return 'observer';
    }
    return viewState.identity.requestedRole;
}

/**
 * Record the roster the server just broadcast.
 * The lobby sends user objects and a running game sends bare names, so both
 * shapes are flattened to names here rather than at every read.
 *
 * @param {Array} players - Player names, or user objects carrying `name`
 * @param {Array} observers - The same, for observers
 * @param {number} [minPlayers] - Minimum needed to start, when the payload says
 * @param {number} [maxPlayers] - Seats at this table, when the payload says
 */
export function setRoster(players, observers, minPlayers, maxPlayers) {
    const nameOf = (entry) => (typeof entry === 'string' ? entry : entry?.name);
    viewState.server.roster.players = (players || []).map(nameOf);
    viewState.server.roster.observers = (observers || []).map(nameOf);
    if (typeof minPlayers === 'number') {
        viewState.server.roster.minPlayers = minPlayers;
    }
    // The cap is a rule the table can raise for a 5-6 player board, so the
    // lobby heading reads it from here rather than from a "/4" in the markup.
    if (typeof maxPlayers === 'number') {
        viewState.server.roster.maxPlayers = maxPlayers;
    }
}

/**
 * Fold a partial server message into the stored snapshot.
 *
 * `turn_changed` and `choose_victim` settle facts a moment before the board
 * broadcast that repeats them. Writing them here rather than into a parallel
 * flag keeps one answer to every server-owned question, and the next full board
 * payload replaces the object wholesale.
 *
 * @param {object} facts - Board fields the message settled
 */
export function applyBoardFacts(facts) {
    if (viewState.server.board) {
        Object.assign(viewState.server.board, facts);
    }
}
