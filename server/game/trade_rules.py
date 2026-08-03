"""Trading: player offers, bank and harbour trades, and the Harbormaster.

Split out of `game.py` for the same reason as `board.py`: `Game` had grown into
one class covering six unrelated concerns. A mixin rather than free functions
because every method here reads and writes Game state (hands, the bank, the
trade manager, the vertices that carry harbours), and threading all of it
through parameters would obscure the rules, which are the point.
"""

from game.results import refused


class TradeRules:
    """Everything that moves cards between players, the bank and a harbour."""

    def best_trade_rate(self, player_name: str, offered: dict) -> int:
        """Cards the player must give per card received, given their harbours.

        A 2:1 harbour only helps with its own resource, the 3:1 harbour helps
        with anything, and without either it is the table's bank rate — 4:1 in
        the base game. A harbour never makes a trade worse, so a table playing
        at 3:1 or 2:1 keeps the better of the two.
        """
        ports = self.get_player_ports(player_name)
        rate = min(self.rules['bank_trade_rate'], 3) if 'generic' in ports \
            else self.rules['bank_trade_rate']
        if any(resource in ports for resource in offered):
            rate = min(rate, 2)
        return rate

    def propose_trade(self, player_name: str, offered: dict, wanted: dict) -> dict:
        """Offer a trade to the table, or settle it against the bank.

        A request at or better than the player's harbour rate is not really an
        offer — it is a bank trade, so it completes immediately rather than
        waiting for a response nobody would withhold.
        """
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')

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

        for resource, count in offered.items():
            available = player.resources.get(resource, 0)
            if available < count:
                return refused(
                    'INSUFFICIENT_RESOURCES',
                    f'Not enough {resource}: have {available}, offering {count}',
                )

        rate = self.best_trade_rate(player_name, offered)
        if sum(offered.values()) / sum(wanted.values()) < rate:
            offer = self.trade_manager.propose(player_name, offered, wanted)
            if not offer:
                return refused('TRADE_LIMIT', 'Maximum number of trade offers reached')
            return {'success': True, 'error': '', 'kind': 'offer', 'offer': offer}

        # Check the bank can cover the whole request before touching anything.
        # Mutating first and unwinding on failure previously left the player
        # holding whatever was granted before the shortfall.
        for resource, count in wanted.items():
            if self.bank.resources.get(resource, 0) < count:
                return refused('BANK_EMPTY', f'Bank does not have {count} {resource}')

        for resource, count in offered.items():
            player.resources[resource] = player.resources.get(resource, 0) - count
            self.bank.return_resources(resource, count)

        for resource, count in wanted.items():
            self.bank.take(resource, count)
            player.resources[resource] = player.resources.get(resource, 0) + count

        return {'success': True, 'error': '', 'kind': 'bank', 'rate_used': rate}

    def accept_trade(self, offer_id: int, player_name: str) -> dict:
        """Signal willingness to take an offer, if the cards are there."""
        offer = self.trade_manager.offers.get(offer_id)
        if not offer:
            return refused('TRADE_NOT_FOUND', 'Trade offer not found')

        player = self.get_player(player_name)
        if not player:
            return refused('INVALID_TARGET', 'Unknown player')

        for resource, count in offer['wanted_resources'].items():
            if player.resources.get(resource, 0) < count:
                return refused(
                    'INSUFFICIENT_RESOURCES', f'Not enough {resource} to accept this trade'
                )

        if not self.trade_manager.accept(offer_id, player_name, player.resources):
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

        # Transfer offered resources FROM proposer TO responder
        for resource, count in offer['offered_resources'].items():
            proposer_player.resources[resource] = proposer_player.resources.get(resource, 0) - count
            responder_player.resources[resource] = (
                responder_player.resources.get(resource, 0) + count
            )

        # Transfer wanted resources FROM responder TO proposer
        for resource, count in offer['wanted_resources'].items():
            responder_player.resources[resource] = (
                responder_player.resources.get(resource, 0) - count
            )
            proposer_player.resources[resource] = proposer_player.resources.get(resource, 0) + count

        return True

    def execute_bank_trade(self, offer_id: int, proposer: str):
        """Execute a bank trade (4:1 or better ratio)."""
        offer = self.trade_manager.offers.get(offer_id)
        if not offer or offer['status'] != 'completed':
            return False

        proposer_player = self.get_player(proposer)
        if not proposer_player:
            return False

        # Transfer offered resources to bank
        for resource, count in offer['offered_resources'].items():
            for _ in range(count):
                self.bank.return_resources(resource)

        # Transfer wanted resources from bank to player
        for resource, count in offer['wanted_resources'].items():
            for _ in range(count):
                self.bank.take(resource)
            proposer_player.resources[resource] = proposer_player.resources.get(resource, 0) + count

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
