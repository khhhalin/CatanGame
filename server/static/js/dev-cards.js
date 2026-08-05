// The development-card fold: the player's own cards as buttons, the two counts
// on the folded chip, and playing one.
//
// The click handler is a single delegated listener registered when this module
// is first evaluated, because the card buttons are replaced on every server
// event. panels.js imports this module at the top for that side effect.

import { devCardsChipValue, devDeckRemaining, myDevCardsDiv } from './dom.js';
import { icon, statusIcon } from './icons.js';
import { displayError } from './notices.js';
import { findMyPlayer } from './player-view.js';
import { emitGame } from './socket.js';
import { getBoard, getGamePhase, hasRolledDice, isMyTurn, mustMoveRobber, viewState } from './state.js';

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
        renderDevCardsChip(0);
        return;
    }

    // knight -> sword, two_roads -> road, victory_point -> crown all have a
    // matching line icon; Invention and Monopoly have no dedicated glyph in the
    // set, so they fall back to the generic dev-card icon and lean on the label.
    const cardIcons = {
        knight: `${statusIcon('knight')} Knight`,
        two_roads: `${statusIcon('road')} Two Roads`,
        invention: `${icon('dev')} Invention`,
        monopoly: `${icon('dev')} Monopoly`,
        victory_point: `${statusIcon('crown')} Victory`
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

    renderDevCardsChip(
        Object.values(player.dev_cards).reduce((total, card) => total + card.count, 0)
    );
}

/**
 * The folded summary: how many cards this player holds, and how many are left
 * to buy. Both are things a player checks constantly and neither is worth a
 * panel of its own.
 *
 * @param {number} held - Cards in this player's own hand
 */
function renderDevCardsChip(held) {
    if (!devCardsChipValue) {
        return;
    }
    const remaining = getBoard()?.dev_cards_remaining ?? 0;
    devCardsChipValue.innerHTML = `${statusIcon('dev')} ${held} held · ${remaining} in deck`;
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

    // No card-specific branching here by design: what a card does is the
    // server's ruling, and the client only names which one was played.
    emitGame('play_dev_card', { name: viewState.identity.name, card_type: cardType });
}
