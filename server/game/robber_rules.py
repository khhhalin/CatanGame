"""The robber: moving it, stealing, and the discard a 7 forces.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. It stays a mixin because every method reads Game state — the board, the
hands, and the pending-choice flags the socket handlers drive the UI from.
"""

import logging

from game.results import refused
from game.validation import CARD_TYPES, COMMODITY_TYPES

logger = logging.getLogger(__name__)


class RobberRules:
    """Robber placement, theft, and the half-hand discard on a 7."""

    def move_robber(self, player_name: str, hex_key: str) -> dict:
        """Move the robber onto a land hex and work out who can be robbed.

        Returns {'success', 'error', 'code', 'victims'}; a non-empty victim
        list means the mover still owes a choice.
        """
        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot move robber during setup')

        if not self.must_move_robber:
            return refused('WRONG_PHASE', 'You do not need to move the robber')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can move the robber')

        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None:
            return refused('INVALID_TARGET', 'Invalid hex')
        if hex_obj.type == 'ocean':
            return refused('INVALID_TARGET', 'Cannot place robber on ocean')

        # Friendly Robber, when enabled, protects anyone still on 2 victory points.
        if not self.robber_is_allowed(hex_key):
            return refused(
                'FRIENDLY_ROBBER',
                'Friendly Robber: that hex touches a settlement of a player on '
                '2 victory points. Pick another hex.',
            )

        self.robber_hex = hex_key
        self.must_move_robber = False

        # Nobody robs themselves, so the mover never appears in their own list.
        victims = [victim for victim in self.get_robber_victims() if victim != player_name]
        if victims:
            self.must_choose_victim = True
            self.robber_victims = victims

        return {'success': True, 'error': '', 'victims': victims}

    def steal_from_victim(self, player_name: str, victim_name: str) -> dict:
        """Take one random card from a player the robber is sitting on.

        Returns {'success', 'error', 'code', 'stolen'}; 'stolen' is None when
        the victim's hand was empty, which is a legal outcome, not a refusal.
        """
        if not self.must_choose_victim:
            return refused('WRONG_PHASE', 'No victim selection required')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can choose victim')

        if victim_name not in self.robber_victims:
            return refused('INVALID_TARGET', 'Invalid victim selection')

        stolen = self.steal_resource(victim_name, player_name)
        self.must_choose_victim = False
        self.robber_victims = []
        return {'success': True, 'error': '', 'stolen': stolen}

    def discard(self, player_name: str, resources: dict) -> dict:
        """Hand back half a hand that was over the limit when a 7 came up.

        `resources` may name commodities as well: they count toward the limit
        that forced the discard, so refusing them would leave a player who is
        over the limit on cloth, coin and paper unable to comply at all.
        """
        if player_name not in self.players_needing_discard:
            return refused('WRONG_PHASE', 'You do not need to discard')

        if not self.discard_resources(player_name, resources):
            return refused('INVALID_PAYLOAD', 'Invalid discard amount or resources')

        return {'success': True, 'error': ''}

    def robber_is_allowed(self, hex_key: str) -> bool:
        """Whether the robber may be moved onto this hex.

        Friendly Robber (Traders & Barbarians): a hex touching a settlement of
        a player on only 2 victory points is off limits, so the player who is
        furthest behind cannot be kicked while they are down.
        """
        if not self.rules['friendly_robber']:
            return True

        if hex_key not in self.hexes:
            return False

        # A Hex only knows its neighbouring hexes, so walk the vertices and ask
        # each one which hexes it touches — the same direction get_robber_victims
        # uses.
        for vertex in self.vertices.values():
            if not vertex.building:
                continue
            if hex_key not in vertex.neighbors.get('hexes', []):
                continue
            owner = self.get_player(vertex.building.get('player'))
            if owner is None:
                continue
            points = owner.get_victory_points(self.longest_road_holder, self.largest_army_holder)
            if points <= 2:
                return False
        return True

    def friendly_robber_fallback(self) -> str | None:
        """Where the robber goes when Friendly Robber leaves nowhere legal.

        The rule sends it to the desert in that case.
        """
        for key, hex_obj in self.hexes.items():
            if hex_obj.type == 'desert':
                return key
        return None

    def check_discard_required(self):
        """Check which players need to discard half their resources (7 rolled)."""
        self.players_needing_discard = {}

        base_limit = self.rules['max_hand_before_discard']
        for player in self.players:
            # Commodities count toward the limit; each city wall raises it by 2.
            total_cards = player.total_cards()
            limit = base_limit
            if self.ck:
                limit += self.ck.city_wall_bonus(player.name)
            if total_cards > limit:
                discard_amount = total_cards // 2
                self.players_needing_discard[player.name] = discard_amount

        if self.players_needing_discard:
            logger.debug(f"Players needing to discard: {self.players_needing_discard}")

    def discard_resources(self, player_name: str, resources: dict) -> bool:
        """Process a resource and commodity discard from a player.

        Args:
            player_name: Name of player discarding
            resources: Dict of card_type -> count to discard. Commodities are
                accepted alongside resources because they count toward the
                hand limit that triggered the discard.

        Returns:
            bool: True if discard was successful
        """
        if player_name not in self.players_needing_discard:
            return False

        player = self.get_player(player_name)
        if not player:
            return False

        # Caller is expected to have run this through validation.clean_card_counts,
        # but re-check here so the engine is safe to call directly from a test or
        # a future handler: a negative count would pass the `current < count`
        # check below and then *add* cards when subtracted.
        for card_type, count in resources.items():
            if card_type not in CARD_TYPES:
                return False
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                return False

        required = self.players_needing_discard[player_name]
        discard_total = sum(resources.values())

        if discard_total != required:
            return False

        for card_type, count in resources.items():
            hand = player.commodities if card_type in COMMODITY_TYPES else player.resources
            if hand.get(card_type, 0) < count:
                return False

        for card_type, count in resources.items():
            if card_type in COMMODITY_TYPES:
                player.commodities[card_type] = player.commodities.get(card_type, 0) - count
                # The bank tracks the five resources only; C&K's commodity
                # supply is unlimited, so a discarded commodity just leaves play.
                continue
            player.resources[card_type] = player.resources.get(card_type, 0) - count
            self.bank.return_resources(card_type, count)

        del self.players_needing_discard[player_name]
        logger.debug(f"Player {player_name} discarded {resources}")
        return True

    def get_robber_victims(self) -> list:
        """Get list of players with settlements/cities adjacent to robber hex.

        Returns:
            list: List of player names who can be stolen from
        """
        if not self.robber_hex or self.robber_hex not in self.hexes:
            return []

        victim_names = set()

        for _vertex_key, vertex in self.vertices.items():
            if not vertex.building:
                continue
            if vertex.building.get('type') not in ('settlement', 'city'):
                continue

            if self.robber_hex in vertex.neighbors.get('hexes', []):
                player_name = vertex.building.get('player')
                if player_name:
                    victim_names.add(player_name)

        return list(victim_names)

    def steal_resource(
        self, victim_name: str, thief_name: str, resource_type: str = None
    ) -> str | None:
        """Steal a random resource from a victim and give to thief.

        Args:
            victim_name: Name of player to steal from
            thief_name: Name of player to receive stolen resource
            resource_type: If provided, steal this specific type (for UI choice)

        Returns:
            str: Resource type stolen, or None if no resources to steal
        """
        victim = self.get_player(victim_name)
        if not victim:
            return None

        thief = self.get_player(thief_name)
        if not thief:
            return None

        available_resources = [r for r, count in victim.resources.items() if count > 0]
        if not available_resources:
            return None

        if resource_type and resource_type in available_resources:
            stolen = resource_type
        else:
            stolen = self.rng.choice(available_resources)

        victim.resources[stolen] = victim.resources[stolen] - 1
        thief.resources[stolen] = thief.resources.get(stolen, 0) + 1
        return stolen
