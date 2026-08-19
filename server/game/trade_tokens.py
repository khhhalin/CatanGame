"""Catan for Two: the Trade Token catch-up economy.

Source [OFFICIAL]: Traders & Barbarians 2020 rulebook, "Catan for Two", pp. 6-7
(catan-t_b_2020_rule_book_200820.pdf).

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. The tokens (physical "Catan chits") drive catch-up: each player opens
with five, earns more by building near the desert or the coast or by sacrificing
a played knight, and spends them on two token-actions whose price is asymmetric —
1 token for the player who is behind or level on victory points, 2 for the one
ahead. Everything here is gated on `rules['trade_tokens']`.
"""

from game.results import refused

# Rulebook "Preparation": each player receives 5 trade tokens at the start.
STARTING_TRADE_TOKENS = 5


class TradeTokenRules:
    """The trade-token pool: starting hand, earn triggers and token-actions."""

    def seed_trade_tokens(self):
        """Give every real seat its opening five tokens. No-op off the rule."""
        if not self.rules["trade_tokens"]:
            return
        for player in self.players:
            player.trade_tokens = STARTING_TRADE_TOKENS

    # --- Earning -----------------------------------------------------------

    def grant_settlement_trade_tokens(self, player_name: str, vertex_key: str) -> int:
        """Award the tokens a new settlement earns, and return how many.

        Rulebook "Replenishing Trade Tokens": a settlement adjacent to the desert
        earns 2, one on the coast earns 1, and one adjacent to *both* the desert
        and the coast earns 3 (not 2+1). Applies during set-up and in play alike,
        and only to a settlement (a city earns nothing). Neutral colours never
        earn — `get_player` cannot find them, so this is a no-op for their pieces.
        """
        if not self.rules["trade_tokens"]:
            return 0
        player = self.get_player(player_name)
        if player is None:
            return 0
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return 0
        desert = self._vertex_adjacent_to_desert(vertex)
        coast = self._vertex_is_coastal(vertex)
        if desert and coast:
            earned = 3
        elif desert:
            earned = 2
        elif coast:
            earned = 1
        else:
            earned = 0
        player.trade_tokens += earned
        return earned

    def _vertex_adjacent_to_desert(self, vertex) -> bool:
        """Whether an intersection touches the desert hex."""
        return any(
            hex_key in self.hexes and self.hexes[hex_key].type == "desert"
            for hex_key in vertex.neighbors.get("hexes", [])
        )

    def _vertex_is_coastal(self, vertex) -> bool:
        """Whether an intersection sits on the coast.

        A vertex lists only its *land* hexes (board.py), so an inland
        intersection touches three and a coastal one touches one or two, the rest
        being open sea. Fewer than three land hexes therefore means the coast.
        """
        land = vertex.neighbors.get("hexes", [])
        return 0 < len(land) < 3

    def discard_knight_for_trade_tokens(self, player_name: str) -> dict:
        """Sacrifice one face-up (played) knight for 2 trade tokens.

        Rulebook "Replenishing Trade Tokens": "Once during your turn, you may
        discard one of your face-up knight cards and take 2 trade tokens in
        exchange." Discarding one may cost the player the Largest Army, so the
        army holder is recomputed. Once per turn, and only the current player.
        """
        problem = self._trade_token_actor_block(player_name)
        if problem is not None:
            return problem
        if self.trade_token_knight_discarded:
            return refused(
                "ALREADY_DISCARDED", "You have already traded a knight for tokens this turn"
            )
        player = self.get_player(player_name)
        if player.knights_played < 1:
            return refused("NO_KNIGHT", "You have no face-up knight to discard")
        player.knights_played -= 1
        player.trade_tokens += 2
        self.trade_token_knight_discarded = True
        # Losing a knight can hand the Largest Army to someone else, or to no one.
        self.update_largest_army()
        return {"success": True, "error": "", "trade_tokens": player.trade_tokens}

    # --- Spending ----------------------------------------------------------

    def trade_token_cost(self, player_name: str) -> int:
        """What a token-action costs this player: 1 if behind or level, else 2.

        Rulebook: "If your victory point total is fewer than or equal to your
        opponent's total, you must pay 1 trade token to take an action.
        Otherwise, an action costs you 2 trade tokens." Read off the public
        totals, so an unplayed VP card in hand never tips the leader check.
        """
        my_points = self.public_victory_points(player_name)
        opponents = [player for player in self.players if player.name != player_name]
        opponent_points = max(
            (self.public_victory_points(opponent.name) for opponent in opponents),
            default=0,
        )
        return 1 if my_points <= opponent_points else 2

    def _trade_token_actor_block(self, player_name: str):
        """Shared guard for every token action: on, in play, current, and real."""
        if not self.rules["trade_tokens"]:
            return refused("RULE_OFF", "This table is not playing with trade tokens")
        if self.game_phase != "playing":
            return refused("WRONG_PHASE", "Trade tokens can only be spent in play")
        current = self.current_player_name()
        if current != player_name:
            return refused("NOT_YOUR_TURN", f"Only {current} can spend trade tokens")
        if self.get_player(player_name) is None:
            return refused("INVALID_TARGET", "Unknown player")
        return None

    def _charge_trade_tokens(self, player_name: str):
        """Check the cost is affordable and deduct it; None on success else a refusal."""
        player = self.get_player(player_name)
        cost = self.trade_token_cost(player_name)
        if player.trade_tokens < cost:
            return refused(
                "NOT_ENOUGH_TOKENS", f"That action costs {cost} trade tokens"
            )
        player.trade_tokens -= cost
        return None

    def spend_trade_tokens_forced_trade(self, player_name: str, give_cards: dict) -> dict:
        """Token-action "Forced Trade".

        Rulebook: "You draw 2 random cards from your opponent's hand; in
        exchange, you give your opponent 2 cards of your choice from your own
        hand. If your opponent only has 1 card, you can take it, but still must
        give that opponent 2 cards in exchange." `give_cards` is the two the
        actor hands over ({resource: count} summing to 2, from their own hand).
        """
        problem = self._trade_token_actor_block(player_name)
        if problem is not None:
            return problem
        player = self.get_player(player_name)
        opponents = [other for other in self.players if other.name != player_name]
        if len(opponents) != 1:
            return refused("NO_OPPONENT", "Forced Trade needs exactly one opponent")
        opponent = opponents[0]

        if not isinstance(give_cards, dict):
            return refused("INVALID_TARGET", "Name the two cards you are giving")
        if any((not isinstance(count, int)) or count < 0 for count in give_cards.values()):
            return refused("INVALID_TARGET", "Card counts must be non-negative whole numbers")
        if sum(give_cards.values()) != 2:
            return refused("WRONG_COUNT", "You must give exactly 2 cards in exchange")
        # The actor must hold what they promise, out of their own hand as it
        # stands *before* the draw, so a card drawn from the opponent cannot be
        # handed straight back.
        for resource, count in give_cards.items():
            if player.resources.get(resource, 0) < count:
                return refused("INSUFFICIENT_RESOURCES", "You do not hold those cards")

        charged = self._charge_trade_tokens(player_name)
        if charged is not None:
            return charged

        # Draw up to two random cards from the opponent (fewer only if the
        # opponent runs out), reusing the robber's steal so the draw is random.
        drawn = []
        for _ in range(2):
            stolen = self.steal_resource(opponent.name, player_name)
            if stolen is None:
                break
            drawn.append(stolen)

        # Hand over the two chosen cards.
        for resource, count in give_cards.items():
            if count == 0:
                continue
            player.resources[resource] -= count
            if player.resources[resource] == 0:
                del player.resources[resource]
            opponent.resources[resource] = opponent.resources.get(resource, 0) + count

        return {
            "success": True,
            "error": "",
            "drawn": sorted(drawn),
            "given": {resource: count for resource, count in give_cards.items() if count},
            "trade_tokens": player.trade_tokens,
        }

    def spend_trade_tokens_move_robber(self, player_name: str) -> dict:
        """Token-action "Move Robber": send the robber to the desert hex.

        Rulebook: "You may move the robber to the desert hex." Parks the robber
        off a producing hex — no steal, since the desert pays nobody.
        """
        problem = self._trade_token_actor_block(player_name)
        if problem is not None:
            return problem
        desert = self._desert_hex_key()
        if desert is None:
            return refused("NO_DESERT", "This board has no desert to move the robber to")
        if self.robber_hex == desert:
            return refused("ROBBER_IN_DESERT", "The robber is already in the desert")

        charged = self._charge_trade_tokens(player_name)
        if charged is not None:
            return charged

        self.robber_hex = desert
        player = self.get_player(player_name)
        return {"success": True, "error": "", "trade_tokens": player.trade_tokens}
