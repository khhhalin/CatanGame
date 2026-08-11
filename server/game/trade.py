import time


class TradeManager:
    """Manages trade offers between players."""

    def __init__(
        self,
        offer_expiry_seconds: int = 10,
        max_offers_per_player: int = 5,
        bank_trade_ratio: int = 4,
    ):
        self.offer_expiry_seconds = offer_expiry_seconds
        self.max_offers_per_player = max_offers_per_player
        self.bank_trade_ratio = bank_trade_ratio
        self.offers = {}
        self.offer_counter = 0

    def propose(
        self, proposer: str, offered_resources: dict, wanted_resources: dict
    ) -> dict | None:
        """Create a new trade offer.

        Returns offer dict if successful, None if max offers reached.
        """
        if len(self._get_player_offers(proposer)) >= self.max_offers_per_player:
            return None

        self.offer_counter += 1
        offer_id = self.offer_counter

        offer = {
            'id': offer_id,
            'proposer': proposer,
            'offered_resources': offered_resources,
            'wanted_resources': wanted_resources,
            'created_at': time.time(),
            'accepted_by': {},  # player_name -> True
            'status': 'active',
        }

        self.offers[offer_id] = offer
        return offer

    def cancel_all_active(self) -> None:
        """Drop every open offer.

        Only the player whose turn it is can hold an offer, so turn end calls
        this to clear that player's offers as their turn passes — an offer is
        good only while its maker is on. Without a clock (the physical-game
        default), this is the one thing that takes an untaken offer off the
        table.
        """
        for offer in self.offers.values():
            if offer['status'] == 'active':
                offer['status'] = 'cancelled'

    def has_expired(self, offer: dict) -> bool:
        """Whether this offer's clock has run out, and mark it if it has.

        An expiry of 0 is no clock at all: the table asked for the physical
        game, where an offer stays on the table until it is taken or picked
        back up.
        """
        if offer['status'] != 'active' or not self.offer_expiry_seconds:
            return False
        if time.time() - offer['created_at'] <= self.offer_expiry_seconds:
            return False
        offer['status'] = 'expired'
        return True

    def accept(self, offer_id: int, player_name: str, player_resources: dict) -> bool:
        """Player accepts a trade offer.

        Returns True if accepted, False if invalid or insufficient resources.
        """
        if offer_id not in self.offers:
            return False

        offer = self.offers[offer_id]
        # Checked here and in `complete`, not only where the offers are listed:
        # an offer whose countdown has reached 0 on every screen at the table
        # still moved cards whenever no board update had pruned it first.
        if self.has_expired(offer):
            return False
        if offer['status'] != 'active':
            return False

        # Check if player has wanted resources
        for resource, count in offer['wanted_resources'].items():
            if player_resources.get(resource, 0) < count:
                return False

        offer['accepted_by'][player_name] = True
        return True

    def decline(self, offer_id: int, player_name: str) -> bool:
        """Player explicitly declines a trade offer."""
        if offer_id not in self.offers:
            return False

        offer = self.offers[offer_id]
        if offer['status'] != 'active':
            return False

        # Mark as declined (but keep in list for proposer to see)
        offer['accepted_by'][player_name] = False
        return True

    def cancel(self, offer_id: int, player_name: str) -> bool:
        """Proposer cancels their offer."""
        if offer_id not in self.offers:
            return False

        offer = self.offers[offer_id]
        if offer['proposer'] != player_name:
            return False

        offer['status'] = 'cancelled'
        return True

    def complete(self, offer_id: int, proposer: str, selected_responder: str | None) -> dict | None:
        """Complete a trade between proposer and selected responder.

        If selected_responder is None and offer is 4:1 or better, trade with bank.
        """
        if offer_id not in self.offers:
            return None

        offer = self.offers[offer_id]
        if offer['proposer'] != proposer:
            return None

        if self.has_expired(offer):
            return None

        if offer['status'] != 'active':
            return None

        # Check if can trade with bank (4:1 ratio or better)
        if self._is_bank_trade_offer(offer):
            offer['status'] = 'completed'
            return {'type': 'bank', 'offer': offer}

        # Must select a responder
        if not selected_responder:
            return None

        if (
            selected_responder not in offer['accepted_by']
            or not offer['accepted_by'][selected_responder]
        ):
            return None

        offer['status'] = 'completed'
        offer['completed_with'] = selected_responder

        return {'type': 'player', 'offer': offer, 'responder': selected_responder}

    def _is_bank_trade_offer(self, offer: dict) -> bool:
        """Check if offer can be traded with bank (4:1 ratio or better)."""
        offered_total = sum(offer['offered_resources'].values())
        wanted_total = sum(offer['wanted_resources'].values())

        if wanted_total == 0:
            return False

        ratio = offered_total / wanted_total
        return ratio >= self.bank_trade_ratio

    def _get_player_offers(self, player_name: str) -> list:
        """Get all active offers made by a player."""
        return [
            o
            for o in self.offers.values()
            if o['proposer'] == player_name and o['status'] == 'active'
        ]

    def get_active_offers(self, exclude_proposer: str = None) -> list:
        """Get all active offers, optionally excluding a player's own offers."""
        offers = []

        for _offer_id, offer in self.offers.items():
            if offer['status'] == 'active':
                if self.has_expired(offer):
                    continue

                if exclude_proposer and offer['proposer'] == exclude_proposer:
                    continue

                offers.append(offer)

        return offers

    def get_my_offers(self, player_name: str) -> list:
        """Get all active offers made by a specific player."""
        offers = []

        for _offer_id, offer in self.offers.items():
            if offer['proposer'] == player_name and offer['status'] == 'active':
                if self.has_expired(offer):
                    continue
                offers.append(offer)

        return offers

    def get_all_active(self) -> list:
        """Get all active offers (including expired ones for cleanup)."""
        return [o for o in self.offers.values() if o['status'] == 'active']

    def cleanup_expired(self):
        """Mark every offer whose clock has run out as expired."""
        for _offer_id, offer in self.offers.items():
            self.has_expired(offer)
