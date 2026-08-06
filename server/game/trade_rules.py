"""Trading: player offers, bank and harbour trades, and the Harbormaster.

Split out of `game.py` for the same reason as `board.py`: `Game` had grown into
one class covering six unrelated concerns. A mixin rather than free functions
because every method here reads and writes Game state (hands, the bank, the
trade manager, the vertices that carry harbours), and threading all of it
through parameters would obscure the rules, which are the point.
"""

from game.results import refused
from game.validation import COMMODITY_TYPES

# What the merchant piece is worth at the bank, for the hex it stands on.
MERCHANT_TRADE_RATE = 2

# What a Merchant Fleet is worth, for the card type it named. A constant of its
# own rather than a shared 2: the two rules are unrelated and either could be
# house-ruled without the other.
MERCHANT_FLEET_TRADE_RATE = 2


def _move_cards(giver, taker, card_type: str, count: int):
    """Hand `count` cards of one type from one player to another.

    "Commodities may be traded with other players ... in all the same ways
    that resources may be traded" (`expansions.md` 329), so which pile the
    cards come out of is the players' business, not the trade's.
    """
    from_hand = giver.hand_for(card_type)
    to_hand = taker.hand_for(card_type)
    from_hand[card_type] = from_hand.get(card_type, 0) - count
    to_hand[card_type] = to_hand.get(card_type, 0) + count


class TradeRules:
    """Everything that moves cards between players, the bank and a harbour."""

    def best_trade_rate(self, player_name: str, offered: dict) -> int:
        """Cards the player must give per card received, given their harbours.

        A 2:1 harbour only helps with its own resource, the 3:1 harbour helps
        with anything, and without either it is the table's bank rate — 4:1 in
        the base game. A harbour never makes a trade worse, so a table playing
        at 3:1 or 2:1 keeps the better of the two.

        Commodities are the one exception: "Commodities may never be traded at
        a 2:1 resource-specific harbor, because those harbors only accept their
        own resource" (`expansions.md` 331). A generic harbour still takes them
        at 3:1 (line 330). One commodity anywhere in the offer is enough to
        withdraw every 2:1 rate, otherwise a wood harbour would launder paper
        by pairing it with wood in the same offer.

        A Merchant Fleet is read before that withdrawal rather than after it,
        because the card names "one chosen resource *or commodity*"
        (`expansions.md` 450): it is not a harbour, so line 331 does not touch
        it. It takes the whole offer or none of it, for the reason above — the
        fleet discounts the type it named, not everything travelling with it.
        """
        ports = self.get_player_ports(player_name)
        rate = self.rules['bank_trade_rate']
        if 'generic' in ports:
            rate = min(rate, self.rules['generic_harbour_rate'])

        fleet = self.merchant_fleet_types.get(player_name, ())
        if offered and all(card_type in fleet for card_type in offered):
            rate = min(rate, MERCHANT_FLEET_TRADE_RATE)

        if any(card_type in COMMODITY_TYPES for card_type in offered):
            return rate

        if any(resource in ports for resource in offered):
            rate = min(rate, self.rules['special_harbour_rate'])
        # "The player controlling the merchant may trade the resource type of
        # the hex the merchant stands on with the bank at a 2:1 rate" — a
        # harbour the player carries with them, so it is read here rather than
        # written into their port list.
        if self.merchant_holder == player_name and self.merchant_hex in self.hexes:
            if self.hexes[self.merchant_hex].type in offered:
                rate = min(rate, MERCHANT_TRADE_RATE)
        return rate

    def propose_trade(self, player_name: str, offered: dict, wanted: dict) -> dict:
        """Offer a trade to the table, or settle it against the bank.

        A request at or better than the player's harbour rate is not really an
        offer — it is a bank trade, so it completes immediately rather than
        waiting for a response nobody would withhold.
        """
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        moved = self.movement_phase_block()
        if moved is not None:
            return moved

        if not offered or not wanted:
            return refused('INVALID_PAYLOAD', 'A trade needs resources on both sides')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused(
                'NOT_YOUR_TURN', f'Only {current_name} can propose trades on their turn'
            )

        player = self.get_player(player_name)
        if player is None:
            return refused('INVALID_TARGET', 'Unknown player')

        for card_type, count in offered.items():
            available = player.hand_for(card_type).get(card_type, 0)
            if available < count:
                return refused(
                    'INSUFFICIENT_RESOURCES',
                    f'Not enough {card_type}: have {available}, offering {count}',
                )

        rate = self.best_trade_rate(player_name, offered)
        if sum(offered.values()) / sum(wanted.values()) < rate:
            offer = self.trade_manager.propose(player_name, offered, wanted)
            if not offer:
                return refused('TRADE_LIMIT', 'Maximum number of trade offers reached')
            return {'success': True, 'error': '', 'kind': 'offer', 'offer': offer}

        # Check the bank can cover the whole request before touching anything.
        # Mutating first and unwinding on failure previously left the player
        # holding whatever was granted before the shortfall. Commodities are not
        # checked because the bank holds no commodity supply — see
        # `_bank_gives`.
        for card_type, count in wanted.items():
            if card_type in COMMODITY_TYPES:
                continue
            if self.bank.resources.get(card_type, 0) < count:
                return refused('BANK_EMPTY', f'Bank does not have {count} {card_type}')

        for card_type, count in offered.items():
            self._bank_takes(player, card_type, count)

        for card_type, count in wanted.items():
            self._bank_gives(player, card_type, count)

        return {'success': True, 'error': '', 'kind': 'bank', 'rate_used': rate}

    def _bank_takes(self, player, card_type: str, count: int):
        """Move cards from a player to the bank.

        A commodity leaves play instead of joining a pile: the engine treats
        the commodity supply as unlimited everywhere — production mints them
        rather than drawing them, and a discarded one is simply gone
        (`robber_rules.discard`) — so `Bank` deliberately still tracks the five
        resources only, and old saves keep loading unchanged.
        """
        hand = player.hand_for(card_type)
        hand[card_type] = hand.get(card_type, 0) - count
        if card_type not in COMMODITY_TYPES:
            self.bank.return_resources(card_type, count)

    def _bank_gives(self, player, card_type: str, count: int):
        """Move cards from the bank to a player. See `_bank_takes`."""
        if card_type not in COMMODITY_TYPES:
            self.bank.take(card_type, count)
        hand = player.hand_for(card_type)
        hand[card_type] = hand.get(card_type, 0) + count

    def accept_trade(self, offer_id: int, player_name: str) -> dict:
        """Signal willingness to take an offer, if the cards are there."""
        offer = self.trade_manager.offers.get(offer_id)
        if not offer:
            return refused('TRADE_NOT_FOUND', 'Trade offer not found')

        player = self.get_player(player_name)
        if not player:
            return refused('INVALID_TARGET', 'Unknown player')

        hand = player.all_cards()
        for card_type, count in offer['wanted_resources'].items():
            if hand.get(card_type, 0) < count:
                return refused(
                    'INSUFFICIENT_RESOURCES', f'Not enough {card_type} to accept this trade'
                )

        if not self.trade_manager.accept(offer_id, player_name, hand):
            return refused('TRADE_FAILED', 'Could not accept trade')
        return {'success': True, 'error': ''}

    def decline_trade(self, offer_id: int, player_name: str) -> bool:
        """Decline a trade offer."""
        return self.trade_manager.decline(offer_id, player_name)

    def cancel_trade(self, offer_id: int, player_name: str) -> bool:
        """Cancel a trade offer (proposer only)."""
        return self.trade_manager.cancel(offer_id, player_name)

    def complete_trade(self, offer_id: int, proposer: str, selected_responder: str = None) -> dict:
        """Settle an accepted offer and move the cards."""
        settlement = self.trade_manager.complete(offer_id, proposer, selected_responder)
        if not settlement:
            return refused('TRADE_FAILED', 'Could not complete trade')

        if settlement['type'] == 'bank':
            self.execute_bank_trade(offer_id, proposer)
            return {'success': True, 'error': '', 'type': 'bank', 'responder': None}

        responder = settlement['responder']
        self.execute_trade_with_player(offer_id, proposer, responder)
        return {'success': True, 'error': '', 'type': 'player', 'responder': responder}

    def execute_trade_with_player(self, offer_id: int, proposer: str, responder: str):
        """Execute a player-to-player trade."""
        offer = self.trade_manager.offers.get(offer_id)
        if not offer or offer['status'] != 'completed':
            return False

        proposer_player = self.get_player(proposer)
        responder_player = self.get_player(responder)

        if not proposer_player or not responder_player:
            return False

        # Transfer offered cards FROM proposer TO responder
        for card_type, count in offer['offered_resources'].items():
            _move_cards(proposer_player, responder_player, card_type, count)

        # Transfer wanted cards FROM responder TO proposer
        for card_type, count in offer['wanted_resources'].items():
            _move_cards(responder_player, proposer_player, card_type, count)

        return True

    def execute_bank_trade(self, offer_id: int, proposer: str):
        """Execute a bank trade (4:1 or better ratio)."""
        offer = self.trade_manager.offers.get(offer_id)
        if not offer or offer['status'] != 'completed':
            return False

        proposer_player = self.get_player(proposer)
        if not proposer_player:
            return False

        # The offered cards have not left the proposer's hand yet on this path,
        # so `_bank_takes` does both halves.
        for card_type, count in offer['offered_resources'].items():
            self._bank_takes(proposer_player, card_type, count)

        for card_type, count in offer['wanted_resources'].items():
            self._bank_gives(proposer_player, card_type, count)

        return True

    def get_player_ports(self, player_name: str) -> dict:
        """Get all ports accessible to a player based on their settlements/cities."""
        player = self.get_player(player_name)
        if not player:
            return {}

        ports = {}
        for vertex_key in player.settlements + player.cities:
            vertex = self.vertices.get(vertex_key)
            if vertex and vertex.port:
                port_type = vertex.port.get("type")
                if port_type == "generic":
                    ports["generic"] = True
                elif port_type == "resource":
                    resource = vertex.port.get("resource")
                    ports[resource] = True

        return ports

    def update_harbormaster(self):
        """Recompute harbour points and who holds the Harbormaster card.

        Traders & Barbarians: a settlement on a harbour is 1 point, a city 2.
        The first player to reach 3 takes the card; it passes only when someone
        else has *more*, so a tie leaves it where it is.
        """
        if not self.rules['harbormaster']:
            return

        self.harbor_points = {}
        for player in self.players:
            points = 0
            for vertex_key in player.settlements:
                vertex = self.vertices.get(vertex_key)
                if vertex and vertex.port:
                    points += 1
            for vertex_key in player.cities:
                vertex = self.vertices.get(vertex_key)
                if vertex and vertex.port:
                    points += 2
            self.harbor_points[player.name] = points

        best = max(self.harbor_points.values(), default=0)
        if best < 3:
            self.harbormaster_holder = None
            return

        leaders = [name for name, pts in self.harbor_points.items() if pts == best]
        if self.harbormaster_holder in leaders:
            # Still tied for the lead, so the holder keeps it.
            return
        if len(leaders) == 1:
            self.harbormaster_holder = leaders[0]
