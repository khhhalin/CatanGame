// Player-to-player trade, and the two development cards that need a choice
// made in a dialog before the server can resolve them.

import { RESOURCE_ICONS } from './constants.js';
import { closeInventionModal, closeMonopolyModal, closeTradeModal, confirmInventionBtn, inventionModal, monopolyModal, myOffersDiv, proposeTradeBtn, submitTradeBtn, tradeModal, tradeOffersDiv } from './dom.js';
import { updateTradeTabBadge } from './event-log.js';
import { displayError } from './notices.js';
import { emitGame } from './socket.js';
import { getBoard, isMyTurn, viewState } from './state.js';

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
 * Show trade modal
 */
function showTradeModal() {
    if (!isMyTurn()) {
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
        name: viewState.identity.name,
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
