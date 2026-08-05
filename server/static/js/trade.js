// Player-to-player trade, and the two development cards that need a choice
// made in a dialog before the server can resolve them.

import { COMMODITY_TYPES } from './constants.js';
import { closeInventionModal, closeMonopolyModal, closeTradeModal, confirmInventionBtn, inventionModal, monopolyModal, myOffersDiv, proposeTradeBtn, submitTradeBtn, tradeBankRates, tradeClearBtn, tradeGiveCommodities, tradeModal, tradeOffersDiv, tradeSendAnywayBtn, tradeVerdict, tradeWantCommodities } from './dom.js';
import { updateTradeTabBadge } from './event-log.js';
import { resourceTile } from './icons.js';
import { displayError } from './notices.js';
import { renderDialogHands } from './panels.js';
import { findMyPlayer } from './player-view.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

/**
 * How long an offer stays open, in seconds, as the table set it. The countdown
 * here is display only - the server refuses an accept or a completion past this
 * deadline - and 0 is the table asking for no clock at all.
 *
 * @returns {number}
 */
function tradeOfferSeconds() {
    return getBoard()?.rules?.trade_offer_seconds ?? 10;
}

const TRADE_RESOURCES = ['wood', 'brick', 'sheep', 'wheat', 'ore'];

// Everything the trade handler accepts. Commodities trade exactly as resources
// do - `propose_trade` runs both sides through `clean_card_counts` - so the
// dialog offers all eight on a table that plays them, and the five resources
// on one that does not.
const TRADE_CARDS = [...TRADE_RESOURCES, ...COMMODITY_TYPES];

// The accessible name for a card's tile, whose colour is otherwise the only
// thing identifying it beside a bare count or rate.
const CARD_NAMES = {
    wood: 'Wood', brick: 'Brick', sheep: 'Sheep', wheat: 'Wheat', ore: 'Ore',
    cloth: 'Cloth', coin: 'Coin', paper: 'Paper',
};

/**
 * Whether the running game deals cloth, coin and paper at all.
 */
function commoditiesInPlay() {
    return getBoard()?.rules?.commodities === true;
}

/**
 * The card types the dialog is currently offering, which is what its inputs
 * are read and reset over.
 */
function tradableCards() {
    return commoditiesInPlay() ? TRADE_CARDS : TRADE_RESOURCES;
}

// What the merchant is worth at the bank for the hex it stands on. Duplicated
// from MERCHANT_TRADE_RATE in server/game/trade_rules.py, like the build costs
// in cities-knights.js: it only shapes a hint, and the server's answer is what
// the trade is settled at.
const MERCHANT_TRADE_RATE = 2;

// ------------------------------------------------------------- harbour rates
//
// The bank will take 4:1 from anybody - "the 4:1 trade is always possible, even
// if you do not have a settlement on a harbor" - so the engine is right to
// accept one from a player holding a 3:1 harbour. It is the interface that owed
// them a warning, and did not: the tester built a harbour, kept typing 4, and
// gave the bank a free card every time.
//
// Everything needed to work the rate out is already in the board payload - the
// player's own settlements and cities, the harbour on each vertex, the table's
// three rate rules and where the merchant stands - so this mirrors the engine's
// `best_trade_rate` rather than asking for a new field. The server recomputes
// it and its answer is what the trade settles at; this only decides what the
// player is told before they press the button.

/**
 * The harbours this player's buildings stand on.
 *
 * @returns {object} - {generic: true} and/or {resource: true} per 2:1 harbour
 */
function myPorts() {
    const board = getBoard();
    const me = findMyPlayer();
    if (!board || !me) {
        return {};
    }
    const ports = {};
    for (const key of [...(me.settlements || []), ...(me.cities || [])]) {
        const port = board.vertices?.[key]?.port;
        if (!port) {
            continue;
        }
        if (port.type === 'generic') {
            ports.generic = true;
        } else if (port.type === 'resource' && port.resource) {
            ports[port.resource] = true;
        }
    }
    return ports;
}

/**
 * Cards this player must give per card received, for one bundle of resources.
 *
 * Mirrors `TradeRules.best_trade_rate`: a 2:1 harbour only helps with its own
 * resource, a 3:1 helps with anything, and a harbour never makes a trade worse.
 *
 * @param {Array<string>} offered - Resource ids the player is giving
 * @returns {number}
 */
function bestTradeRate(offered) {
    const board = getBoard();
    const rules = board?.rules || {};
    const ports = myPorts();
    let rate = rules.bank_trade_rate ?? 4;
    if (ports.generic) {
        rate = Math.min(rate, rules.generic_harbour_rate ?? 3);
    }
    // "Commodities may never be traded at a 2:1 resource-specific harbor"
    // (expansions.md 331) - and one commodity anywhere in the offer withdraws
    // every 2:1 rate, or a wood harbour would launder paper alongside wood.
    if (offered.some(card => COMMODITY_TYPES.includes(card))) {
        return rate;
    }
    if (offered.some(resource => ports[resource])) {
        rate = Math.min(rate, rules.special_harbour_rate ?? 2);
    }
    // The merchant is a harbour its holder carries with them, for the hex it
    // stands on only.
    if (board?.merchant_holder === viewState.identity.name) {
        const standingOn = board.hexes?.[board.merchant_hex]?.type;
        if (standingOn && offered.includes(standingOn)) {
            rate = Math.min(rate, MERCHANT_TRADE_RATE);
        }
    }
    return rate;
}

/**
 * Format a resource bundle as a count and its coloured tile per card, skipping
 * empty entries. Returns HTML - the cards are known ids and integer counts, so
 * a caller sets it with innerHTML; anything server-named goes via textContent.
 *
 * @param {object} resources - {resource: amount}
 * @returns {string}
 */
function formatTradeBundle(resources) {
    return Object.entries(resources || {})
        .filter(([, count]) => count > 0)
        .map(([card, count]) =>
            `${count} ${resourceTile(card, { label: CARD_NAMES[card] || card })}`)
        .join('  ');
}

/**
 * The shell of one offer card: header with an optional proposer name, the
 * countdown, and the resources. The caller appends its own action row.
 *
 * The proposer's name lands via textContent - a player named
 * `<img src=x onerror=…>` has to read as literal text. The bundles are card
 * ids and integer counts the server cleaned, so their tiles are set as HTML.
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
    give.innerHTML = giveText;
    resources.appendChild(give);

    const arrow = document.createElement('span');
    arrow.textContent = '→';
    resources.appendChild(arrow);

    const want = document.createElement('span');
    want.className = 'want';
    want.innerHTML = wantText;
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
export function renderTradeOffers() {
    if (!getBoard() || !getBoard().trades) {
        tradeOffersDiv.replaceChildren();
        myOffersDiv.replaceChildren();
        updateTradeTabBadge(0);
        return;
    }

    const activeTrades = getBoard().trades.active || [];
    const allPlayers = getBoard().players || [];

    // Active offers (other players' offers - responder view)
    const otherOffers = activeTrades.filter(t => t.proposer !== viewState.identity.name);
    const offersFragment = document.createDocumentFragment();

    if (otherOffers.length > 0) {
        const heading = document.createElement('h4');
        heading.textContent = 'Active Offers:';
        offersFragment.appendChild(heading);

        for (const offer of otherOffers) {
            const accepted = offer.accepted_by || {};
            const hasAcceptedMe = accepted[viewState.identity.name] === true;

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
    const myOfferList = getBoard().trades.my_offers?.[viewState.identity.name] || [];
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
                if (player.name === viewState.identity.name) continue;
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
    if (!getBoard()) {
        return;
    }

    const timers = document.querySelectorAll('.trade-timer');
    if (timers.length === 0) {
        return;
    }

    const limit = tradeOfferSeconds();
    if (!limit) {
        // No clock at this table: an offer stands until it is taken or
        // cancelled, so a countdown - stuck at 0 or otherwise - would be a
        // deadline nothing enforces.
        timers.forEach(timer => { timer.textContent = ''; });
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
        const remaining = Math.max(0, limit - Math.floor(elapsed));

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

/**
 * Start the once-per-second countdown. Idempotent: a second call keeps the
 * interval already running rather than stacking a second one, which would
 * double the `refresh_board` emits an expiring offer produces.
 */
function startTradeTimers() {
    if (viewState.tradeTimerHandle !== null) {
        return;
    }
    viewState.tradeTimerHandle = setInterval(updateTradeTimers, 1000);
}

startTradeTimers();

/**
 * Read the two rows of number inputs.
 *
 * @returns {object} - {offered, wanted} as {resource: count}, empties dropped
 */
function readTradeInputs() {
    const offered = {};
    const wanted = {};

    tradableCards().forEach(card => {
        const giveCount = parseInt(document.getElementById(`give-${card}`).value) || 0;
        const wantCount = parseInt(document.getElementById(`want-${card}`).value) || 0;
        if (giveCount > 0) offered[card] = giveCount;
        if (wantCount > 0) wanted[card] = wantCount;
    });

    return { offered, wanted };
}

// --------------------------------------------------------------- steppers
//
// "in trade tab its hard to click the small arrows". A number field's spinner
// is drawn inside the field and splits its height between up and down, so no
// field short enough to keep this dialog on a phone can carry an arrow worth
// aiming at - 40px of field is 20px of arrow, and only where the browser
// paints one at all. These are real buttons either side of the field instead,
// at the field's own height, and the native spinner is hidden once they exist.

// What the button does to the offer, for a screen reader: there are sixteen of
// these in one dialog and "increase" names none of them.
const STEP_VERBS = { give: 'give', want: 'ask for' };

/**
 * How many of one card this player is holding.
 *
 * The give side's real ceiling: the fields were capped at 10 for every card,
 * so the dialog let a player build an offer of ore they did not have and only
 * the server ever said no.
 *
 * @param {string} card - Resource or commodity id
 * @returns {number}
 */
function heldCount(card) {
    const me = findMyPlayer();
    if (!me) {
        return 0;
    }
    return COMMODITY_TYPES.includes(card)
        ? (me.commodities?.[card] || 0)
        : (me.resources?.[card] || 0);
}

/**
 * Move one field by one card, inside the bounds the field itself carries.
 *
 * The field's own `min` and `max` are the limit - `applyHandLimits` keeps the
 * give side's `max` on the hand - so the ceiling lives in one place and a
 * stepper cannot disagree with what typing the same number would do.
 *
 * @param {HTMLInputElement} input - The field to change
 * @param {number} delta - +1 or -1
 */
function stepField(input, delta) {
    const current = parseInt(input.value) || 0;
    const stepped = Math.min(Number(input.max), Math.max(Number(input.min), current + delta));
    if (stepped === current) {
        return;
    }
    input.value = String(stepped);
    // Everything a keystroke sets off - the verdict, the standing overpay
    // offer, the buttons' own bounds - hangs off the delegated `input`
    // listener below, so a step goes through the same door.
    input.dispatchEvent(new Event('input', { bubbles: true }));
}

/**
 * One - or + button for a field.
 *
 * @param {HTMLInputElement} input - The field it steps
 * @param {number} delta - +1 or -1
 * @param {string} card - Resource or commodity id, for the accessible name
 * @param {string} side - 'give' or 'want', likewise
 * @returns {HTMLButtonElement}
 */
function buildStepButton(input, delta, card, side) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'trade-step';
    button.dataset.step = String(delta);
    button.textContent = delta < 0 ? '−' : '+';
    button.setAttribute(
        'aria-label',
        `${delta < 0 ? 'One less' : 'One more'} ${card} to ${STEP_VERBS[side]}`
    );
    button.addEventListener('click', () => stepField(input, delta));
    return button;
}

/**
 * Put a stepper around every trade field, once, at load.
 *
 * The class on the dialog is what hides the native spinner: without the
 * script the fields keep the arrows they came with rather than losing both.
 */
function buildTradeSteppers() {
    for (const side of Object.keys(STEP_VERBS)) {
        for (const card of TRADE_CARDS) {
            const input = document.getElementById(`${side}-${card}`);
            if (!input) {
                continue;
            }
            const stepper = document.createElement('div');
            stepper.className = 'trade-stepper';
            input.replaceWith(stepper);
            stepper.append(
                buildStepButton(input, -1, card, side),
                input,
                buildStepButton(input, 1, card, side)
            );
        }
    }
    tradeModal?.classList.add('has-steppers');
}

/**
 * Grey out each button that would step past its field's bounds.
 *
 * Disabled and not hidden: a button that disappears at zero reflows the row
 * under the finger that just pressed it, which is how the same thumb ends up
 * on the wrong resource.
 */
function refreshStepBounds() {
    for (const stepper of tradeModal?.querySelectorAll('.trade-stepper') || []) {
        const input = stepper.querySelector('input');
        const value = parseInt(input.value) || 0;
        for (const button of stepper.querySelectorAll('.trade-step')) {
            button.disabled = Number(button.dataset.step) < 0
                ? value <= Number(input.min)
                : value >= Number(input.max);
        }
    }
}

/**
 * Cap the give side at the cards this player is holding.
 *
 * Read on open rather than fixed in the markup: a hand changes every roll, and
 * only the give side is bounded by it - asking for eight wheat nobody has is a
 * trade the table is allowed to refuse.
 */
function applyHandLimits() {
    for (const card of TRADE_CARDS) {
        const input = document.getElementById(`give-${card}`);
        const held = heldCount(card);
        input.max = String(held);
        if ((parseInt(input.value) || 0) > held) {
            input.value = String(held);
        }
    }
}

/**
 * Put every field in the dialog back to zero.
 *
 * @returns {void}
 */
function clearTradeInputs() {
    // Every one of them, not only the ones currently shown: a number left in a
    // hidden commodity row would be sent by the next trade on a table that
    // switched them off.
    TRADE_CARDS.forEach(card => {
        document.getElementById(`give-${card}`).value = 0;
        document.getElementById(`want-${card}`).value = 0;
    });
    clearOverpayOffer();
    refreshStepBounds();
    renderTradeVerdict();
}

/**
 * One chip per resource, saying what the bank charges this player for it.
 *
 * Rendered on open rather than once at boot: a harbour built this turn changes
 * every number here, and a rate strip that is out of date is worse than none.
 */
function renderBankRates() {
    if (!tradeBankRates) {
        return;
    }
    const baseRate = getBoard()?.rules?.bank_trade_rate ?? 4;
    const fragment = document.createDocumentFragment();

    const label = document.createElement('span');
    label.className = 'trade-rates-label';
    label.textContent = 'Your bank rate:';
    fragment.appendChild(label);

    for (const card of tradableCards()) {
        const rate = bestTradeRate([card]);
        const chip = document.createElement('span');
        chip.className = 'trade-rate-chip';
        chip.dataset.resource = card;
        // A harbour is only worth having if the player can see they hold one,
        // so the ones better than the table's flat rate are marked as such.
        chip.classList.toggle('is-harbour', rate < baseRate);
        // The name rather than a tile here: this strip is a dense horizontal
        // row of eight chips, and a 30px tile in each tips the dialog past a
        // phone's height (test_browser_trade_panel). A compact tile variant is
        // the missing piece - reported alongside this change.
        chip.textContent = `${CARD_NAMES[card] || card} ${rate}:1`;
        fragment.appendChild(chip);
    }

    tradeBankRates.replaceChildren(fragment);
}

/**
 * What the numbers currently typed would do, and whether they waste cards.
 *
 * @returns {object} - {kind, rate, given, asked, overpay} where kind is
 *                     'empty', 'offer' (goes to the table) or 'bank'
 */
function describeTrade() {
    const { offered, wanted } = readTradeInputs();
    const given = Object.values(offered).reduce((sum, count) => sum + count, 0);
    const asked = Object.values(wanted).reduce((sum, count) => sum + count, 0);

    if (!given || !asked) {
        return { kind: 'empty', rate: 0, given, asked, overpay: 0 };
    }

    const rate = bestTradeRate(Object.keys(offered));
    // Same test the engine applies: at or better than the player's rate it is
    // not an offer at all, it is a bank trade that settles immediately.
    if (given / asked < rate) {
        return { kind: 'offer', rate, given, asked, overpay: 0, offered, wanted };
    }
    return { kind: 'bank', rate, given, asked, overpay: given - rate * asked,
             offered, wanted };
}

/**
 * Say what will happen, in words, under the inputs.
 */
function renderTradeVerdict() {
    if (!tradeVerdict) {
        return;
    }
    const verdict = describeTrade();
    tradeVerdict.classList.remove('is-warning', 'is-bank');

    if (verdict.kind === 'empty') {
        tradeVerdict.textContent = 'Put cards on both sides.';
        return;
    }
    if (verdict.kind === 'offer') {
        // Tiles, so innerHTML - the bundles are cleaned card ids and counts.
        tradeVerdict.innerHTML =
            `Goes to the table: ${formatTradeBundle(verdict.offered)} `
            + `→ ${formatTradeBundle(verdict.wanted)}.`;
        return;
    }
    if (verdict.overpay > 0) {
        tradeVerdict.classList.add('is-warning');
        tradeVerdict.textContent =
            `The bank takes this at ${verdict.rate}:1, so `
            + `${verdict.overpay} extra card${verdict.overpay === 1 ? '' : 's'} `
            + 'would go to it for nothing.';
        return;
    }
    tradeVerdict.classList.add('is-bank');
    tradeVerdict.textContent = `Trades with the bank at ${verdict.rate}:1, straight away.`;
}

/**
 * Lower the give side to exactly the player's own rate.
 *
 * Only ever reached from the Propose button, and always announced: a dialog
 * that quietly changed what somebody typed would be a worse trap than the one
 * this is here to close.
 *
 * @param {object} verdict - A 'bank' verdict with overpay > 0
 * @returns {boolean} - Whether the inputs could be lowered
 */
function applyBestRate(verdict) {
    const resources = Object.keys(verdict.offered);
    // Only for a single-resource offer: spreading the saving over a mixed
    // bundle means choosing which resource the player keeps, which is their
    // decision and not this dialog's.
    if (resources.length !== 1) {
        return false;
    }
    const fair = verdict.rate * verdict.asked;
    if (fair < 1) {
        return false;
    }
    document.getElementById(`give-${resources[0]}`).value = String(fair);
    return true;
}

/**
 * Show trade modal
 */
function showTradeModal() {
    if (!isMyTurn()) {
        displayError('You can only propose trades on your turn');
        return;
    }
    tradeModal.classList.remove('hidden');
    tradeModal.classList.add('show');
    const commodities = commoditiesInPlay();
    tradeGiveCommodities?.classList.toggle('hidden', !commodities);
    tradeWantCommodities?.classList.toggle('hidden', !commodities);
    // This dialog covers the hand panel, and what is in hand is half of what
    // decides an offer. Board updates keep it live from here on.
    renderDialogHands();
    renderBankRates();
    applyHandLimits();
    refreshStepBounds();
    renderTradeVerdict();
}

/**
 * Hide trade modal
 */
function hideTradeModal() {
    tradeModal.classList.remove('show');
    tradeModal.classList.add('hidden');
    clearTradeInputs();
}

// The numbers a player asked to send that were lowered for them, kept so the
// "send it anyway" button can put back exactly what they typed.
let overpayOffer = null;

function clearOverpayOffer() {
    overpayOffer = null;
    tradeSendAnywayBtn?.classList.add('hidden');
}

/**
 * Send a trade to the server and close the dialog.
 */
function sendTrade(offered, wanted) {
    emitGame('propose_trade', {
        name: viewState.identity.name,
        offered: offered,
        wanted: wanted
    });

    hideTradeModal();
}

/**
 * Submit trade proposal.
 *
 * A bank trade worse than the player's own harbour rate is stopped once: the
 * give side is lowered to the rate they are entitled to, the change is stated,
 * and pressing Propose again sends the corrected numbers. Overpaying stays
 * possible - the rulebook allows it - but only from the button that says so.
 */
function submitTrade() {
    const { offered, wanted } = readTradeInputs();

    if (Object.keys(offered).length === 0 || Object.keys(wanted).length === 0) {
        displayError('Please specify resources to give and want');
        return;
    }

    const verdict = describeTrade();
    if (verdict.kind === 'bank' && verdict.overpay > 0 && applyBestRate(verdict)) {
        overpayOffer = { offered, wanted };
        tradeSendAnywayBtn.textContent =
            `Give the bank ${verdict.given} anyway`;
        tradeSendAnywayBtn.classList.remove('hidden');
        refreshStepBounds();
        renderTradeVerdict();
        if (tradeVerdict) {
            tradeVerdict.classList.add('is-warning');
            tradeVerdict.textContent =
                `Lowered to ${verdict.rate}, your rate for this trade — `
                + `${verdict.overpay} card${verdict.overpay === 1 ? '' : 's'} `
                + 'kept. Press Propose to send it.';
        }
        return;
    }

    sendTrade(offered, wanted);
}

/**
 * Accept a trade offer
 */
function acceptTrade(offerId) {
    emitGame('accept_trade', {
        name: viewState.identity.name,
        offer_id: offerId
    });
}

/**
 * Decline a trade offer
 */
function declineTrade(offerId) {
    emitGame('decline_trade', {
        name: viewState.identity.name,
        offer_id: offerId
    });
}

/**
 * Show invention modal (for Invention/Year of Plenty card)
 */
export function showInventionModal() {
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
        name: viewState.identity.name,
        resources: selected
    });
    
    hideInventionModal();
}

/**
 * Show monopoly modal (for Monopoly card)
 */
export function showMonopolyModal() {
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
        name: viewState.identity.name,
        resource_type: resourceType
    });
    
    hideMonopolyModal();
}

/**
 * Cancel your trade offer
 */
function cancelTrade(offerId) {
    emitGame('cancel_trade', {
        name: viewState.identity.name,
        offer_id: offerId
    });
}

/**
 * Complete trade with selected player
 */
function completeTrade(offerId, responder) {
    emitGame('complete_trade', {
        name: viewState.identity.name,
        offer_id: offerId,
        selected_responder: responder
    });
}

// Trade modal event listeners
if (proposeTradeBtn) proposeTradeBtn.addEventListener('click', showTradeModal);
if (closeTradeModal) closeTradeModal.addEventListener('click', hideTradeModal);
if (submitTradeBtn) submitTradeBtn.addEventListener('click', submitTrade);

// One delegated listener rather than ten: every number input in the dialog
// changes what the verdict has to say, including the ones the code above
// rewrites, and a stale verdict under a corrected number is the same trap.
if (tradeModal) {
    tradeModal.addEventListener('input', (event) => {
        if (event.target.matches('input[type="number"]')) {
            // Typing past a correction is a new trade, so the old numbers stop
            // being on offer.
            clearOverpayOffer();
            refreshStepBounds();
            renderTradeVerdict();
        }
    });
}

buildTradeSteppers();

if (tradeClearBtn) tradeClearBtn.addEventListener('click', clearTradeInputs);

if (tradeSendAnywayBtn) {
    tradeSendAnywayBtn.addEventListener('click', () => {
        if (overpayOffer) {
            sendTrade(overpayOffer.offered, overpayOffer.wanted);
        }
    });
}
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
