"""The robber: moving it, stealing, and the discard a 7 forces.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. It stays a mixin because every method reads Game state — the board, the
hands, and the pending-choice flags the socket handlers drive the UI from.
"""

import logging

from game import tiles
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

        # All discarding happens before the robber is moved, so an unpaid
        # discard anywhere at the table holds it back. The mover is rarely the
        # player who owes one, which is why this is not a per-player check.
        if self.players_needing_discard:
            owed = ', '.join(sorted(self.players_needing_discard))
            return refused('MUST_DISCARD', f'{owed} must discard before the robber moves')

        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None:
            return refused('INVALID_TARGET', 'Invalid hex')
        if tiles.is_sea(hex_obj.type):
            return refused('INVALID_TARGET', 'Cannot place robber on ocean')

        # The robber is *moved*, so the hex it already stands on is not an
        # answer: leaving it put keeps its neighbours blocked and costs the
        # roller nothing. `_auto_robber_hex` has always excluded it; only the
        # player-driven path let it through.
        if hex_key == self.robber_hex:
            return refused(
                'ROBBER_MUST_MOVE',
                'The robber must be moved to a different hex than the one it is on',
            )

        # Two different rules can refuse a hex, and telling a player the wrong
        # one is worse than saying nothing: they go looking for a rule that is
        # not even in play.
        refusal = self.robber_refusal(hex_key)
        if refusal is not None:
            return refused(*refusal)

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
        # The E&P pirate ship takes 1 gold from an empty-handed victim instead
        # of a card (expansions.md 943). Guarded on the rule and on gold, so the
        # base-game robber and the Seafarers pirate are unchanged.
        if (stolen is None and self.rules['pirate_ship_instead_of_robber']
                and self.rules['gold']):
            stolen = self._steal_gold_fallback(victim_name, player_name)
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

    def auto_resolve_robber(self, player_name: str = None) -> dict:
        """Finish an abandoned robber move on the current player's behalf.

        The turn watchdog calls this when the round timer expires with the
        robber still pending. Resolving beats skipping: every build, trade and
        turn advance is gated on `must_move_robber`, so an unmoved robber does
        not merely delay the table, it freezes it — and leaving the flag set
        means the absent player's next click moves the robber during someone
        else's turn and ends *that* turn instead.

        Returns {'player', 'hex', 'victim', 'stolen'} describing what was done.
        """
        acting = player_name or self.players[self.current_player_index].name
        outcome = {'player': acting, 'hex': None, 'victim': None, 'stolen': None}

        # The robber is refused while anyone still owes a discard, so anything
        # left owing is settled first: a resolution the blocking rule can refuse
        # would leave the table stuck exactly where this method exists to help.
        for owing in list(self.players_needing_discard):
            logger.info("discard still owed by %s at robber timeout; discarding", owing)
            self.auto_discard(owing)

        if self.must_move_robber:
            target = self._auto_robber_hex(acting)
            if target is None:
                # No land hex is legal (Friendly Robber with no desert). Nothing
                # can be resolved, so release the block rather than stall.
                self.must_move_robber = False
            elif self.move_robber(acting, target)['success']:
                outcome['hex'] = target

        if self.must_choose_victim:
            if self.robber_victims:
                victim = self.rng.choice(self.robber_victims)
                result = self.steal_from_victim(acting, victim)
                if result['success']:
                    outcome['victim'] = victim
                    outcome['stolen'] = result['stolen']
            else:
                self.must_choose_victim = False

        return outcome

    def auto_discard(self, player_name: str) -> dict:
        """Discard at random for a player who let their discard clock run out.

        Which cards go is chosen by the server, not the player: the alternative
        is a table that waits forever on someone who has closed their laptop.
        Every card in the hand is equally likely — a fixed order would let a
        player game the timeout by holding what they want kept behind what the
        server always takes first.
        """
        if player_name not in self.players_needing_discard:
            return {}

        player = self.get_player(player_name)
        if player is None:
            return {}

        # Sorted, so the draw depends on what is in the hand and not on the
        # order the cards were collected in: the same seed and the same hand
        # must always cost the same cards, however that hand was filled.
        hand = []
        for card_type, count in sorted(
            list(player.resources.items()) + list(player.commodities.items())
        ):
            hand.extend([card_type] * count)

        required = min(self.players_needing_discard[player_name], len(hand))
        chosen = {}
        for card_type in self.rng.sample(hand, required):
            chosen[card_type] = chosen.get(card_type, 0) + 1

        # The required amount is derived from the hand size, so it can only fall
        # short if the hand shrank underneath us; take what is there and clear
        # the obligation either way.
        if not self.discard_resources(player_name, chosen):
            self.players_needing_discard.pop(player_name, None)
            return {}
        return chosen

    def _hexes_touching(self, player_name: str) -> set:
        """Every hex this player has a building on a corner of."""
        touched = set()
        for vertex in self.vertices.values():
            if not vertex.building or vertex.building.get('player') != player_name:
                continue
            touched.update(vertex.neighbors.get('hexes', []))
        return touched

    def _auto_robber_hex(self, acting: str = None) -> str | None:
        """Where the robber goes when nobody picked. Never back where it sits.

        The busiest hex that costs the timed-out player nothing: "busiest" is
        the pip count, the dots on the number token, which is how often the hex
        pays and so how much blocking it takes off the table. Picking at random
        was as likely to land on the absent player's own best hex as on
        anybody's, so a missed click blockaded the player who missed it.

        Ties are broken with the game's own rng, so a seeded game resolves a
        timeout the same way every replay. If every legal hex touches one of
        their buildings there is no harmless choice, and the busiest of those
        is taken instead — the robber has to go somewhere.
        """
        legal = [
            key
            for key, hex_obj in self.hexes.items()
            if hex_obj.type != 'ocean' and key != self.robber_hex and self.robber_is_allowed(key)
        ]
        if not legal:
            return self.friendly_robber_fallback()

        acting = acting or self.players[self.current_player_index].name
        harmless = [key for key in legal if key not in self._hexes_touching(acting)]
        candidates = harmless or legal

        best = max(self._hex_pips(key) for key in candidates)
        return self.rng.choice([key for key in candidates if self._hex_pips(key) == best])

    def _hex_pips(self, hex_key: str) -> int:
        """The dots on a hex's number token: 5 for a 6 or an 8, 0 for none."""
        number = self.hexes[hex_key].number
        if number is None:
            return 0
        return 6 - abs(7 - number)

    def robber_refusal(self, hex_key: str):
        """Why this hex is closed to the robber, or None if it is open.

        `robber_is_allowed` answers yes-or-no, which is all the automatic
        resolver needs. A player needs the reason, and there are two of them.
        """
        if hex_key not in self.hexes:
            return 'INVALID_TARGET', 'That is not a hex on this board'

        if (not self.rules['robber_may_return_to_desert']
                and self.hexes[hex_key].type == 'desert'):
            return (
                'ROBBER_NOT_ON_DESERT',
                'This table keeps the robber off the desert. Pick a hex that '
                'produces something.',
            )

        if not self.robber_is_allowed(hex_key):
            return (
                'FRIENDLY_ROBBER',
                'Friendly Robber: that hex touches a settlement of a player on '
                '2 victory points. Pick another hex.',
            )

        return None

    def robber_is_allowed(self, hex_key: str) -> bool:
        """Whether the robber may be moved onto this hex.

        Two rules can refuse one. "Robber may sit on the desert", turned off,
        keeps it on producing land where it costs somebody something. Friendly
        Robber (Traders & Barbarians) puts a hex touching a settlement of a
        player on only 2 victory points off limits, so the player who is
        furthest behind cannot be kicked while they are down.
        """
        if hex_key not in self.hexes:
            return False

        if not self.rules['robber_may_return_to_desert']:
            if self.hexes[hex_key].type == 'desert':
                return False

        if not self.rules['friendly_robber']:
            return True

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

        The rule sends it to the desert in that case — unless the table has
        also barred the desert, which leaves nowhere at all and is answered
        with None rather than a hex the watchdog would then be refused.
        """
        if not self.rules['robber_may_return_to_desert']:
            return None

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
            if self.rules['city_walls'] and self.ck is not None:
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
