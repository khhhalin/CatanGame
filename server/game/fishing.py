"""The Fishermen of Catan: fish-token production, the spend ladder, and the old
boot.

One mixin on `Game`, the pattern `cities_knights_rules.py` and the E&P mission
mixins use. Every method is gated on the individual rule that governs it —
`fishing_grounds`, `lake_hex`, `fish_tokens`, `old_boot` — so a table not running
the Fishermen scenario is untouched and the base game is byte-for-byte unchanged.

The mechanics (expansions.md 489-526):

- A fishing ground pays 1 fish to each adjacent settlement and 2 to each
  adjacent city when its number (4/5/6/8/9/10) is rolled; the lake pays the same
  on a 2/3/11/12. Fish are drawn face down from the supply, and if the supply is
  short of the whole table's demand that turn, nobody draws (`distribute_fish`).
- Fish are spent by total for a benefit: 2 sends the robber off the board, 3
  steals a random card, 4 takes a bank card, 5 builds a free road, 7 draws a free
  development card. No change is given — spent tokens over the price are lost
  (`spend_fish`).
- The old boot, drawn from the supply, raises its holder's personal winning
  threshold by 1 (`personal_target_delta`) and is passed after the roll to a
  player with as many points or more (`pass_old_boot`); the sole leader keeps it.
"""

from game.results import refused

# benefit id -> the fish total it costs (expansions.md 511-515).
FISH_BENEFITS = {
    'robber_off': 2,
    'steal': 3,
    'bank_card': 4,
    'free_road': 5,
    'free_dev': 7,
}

# The lake pays fish on any of these (expansions.md 500); a fishing ground pays
# on the single number printed on it, held in the game's fishing state.
LAKE_NUMBERS = (2, 3, 11, 12)


class FishingRules:
    """Fish production, the spend ladder, and the old boot."""

    # --- Board setup -------------------------------------------------------

    def setup_fishing_board(self):
        """Read the fishing grounds and the lake off the dealt board into TB
        state, so production never re-derives the board geometry each roll.

        A fishing ground is a sea (frame) hex carrying a `fishing_ground` number
        in its metadata; the coastal intersections it pays are exactly the
        vertices it shares with the island — the sea hex's own corners that a
        land hex also owns, which is what makes them buildable. The lake is the
        single hex the map dealt as `lake` terrain.
        """
        if self.tb is None:
            return

        if self.rules['fishing_grounds']:
            grounds = []
            for hex_key, hex_obj in sorted(self.hexes.items()):
                meta = getattr(hex_obj, 'meta', None)
                number = getattr(meta, 'fishing_ground', None) if meta else None
                if number is None:
                    continue
                grounds.append({
                    'hex': hex_key,
                    'number': number,
                    'vertices': self._coastal_vertices(hex_key),
                })
            # A table may run fewer grounds than the board prints; the extras are
            # left off (the frame simply carries no tile there). Board order is
            # sorted, so which grounds survive a lower count is deterministic.
            self.tb.fishing_grounds = grounds[:self.rules['fishing_ground_count']]

        if self.rules['lake_hex']:
            for hex_key, hex_obj in sorted(self.hexes.items()):
                if hex_obj.type == 'lake':
                    self.tb.lake_hex = hex_key
                    break

    def _coastal_vertices(self, hex_key: str) -> list:
        """The island intersections a frame hex touches: its own six corners that
        exist as buildable vertices (vertices are created only where land is)."""
        hx, hy, hz = self._parse_key(hex_key)
        found = []
        for vx, vy, vz in self.VERTEX_DIRECTIONS:
            vertex_key = self._hex_key(hx + vx, hy + vy, hz + vz)
            if vertex_key in self.vertices:
                found.append(vertex_key)
        return found

    def draw_setup_fish(self, player_name: str, vertex_key: str) -> int:
        """Draw the 1 fish a second setup settlement beside a fishing ground takes
        (497). Returns the number actually drawn (0 or 1).

        A no-op without both the token supply and the grounds, and off a coastal
        vertex a ground pays. The caller gates on this being the player's second
        setup placement; the lake and the boot have no set-up draw of their own.
        """
        if self.tb is None:
            return 0
        if not (self.rules['fish_tokens'] and self.rules['fishing_grounds']):
            return 0
        borders = any(vertex_key in ground['vertices']
                      for ground in self.tb.fishing_grounds)
        if not borders:
            return 0
        token = self.tb.draw_to_hand(player_name, self.rules['max_fish_held'])
        return 1 if isinstance(token, int) else 0

    # --- Production --------------------------------------------------------

    def _fish_demand(self, dice_total: int) -> list:
        """Who would draw how many fish this roll, before the supply is checked.

        A list of (player_name, count) — one entry per producing building, count
        1 for a settlement and 2 for a city — so the total is the whole table's
        demand and the "nobody if short" rule can weigh it against the supply.
        """
        demand = []

        def building_yield(vertex_key):
            vertex = self.vertices.get(vertex_key)
            if vertex is None or not vertex.building:
                return None, 0
            btype = vertex.building.get('type')
            player = vertex.building.get('player')
            if not player:
                return None, 0
            if btype == 'city':
                return player, 2
            if btype in ('settlement', 'harbor_settlement'):
                return player, 1
            return None, 0

        if self.rules['fishing_grounds']:
            for ground in self.tb.fishing_grounds:
                if ground['number'] != dice_total:
                    continue
                for vertex_key in ground['vertices']:
                    player, count = building_yield(vertex_key)
                    if player:
                        demand.append((player, count))

        if self.rules['lake_hex'] and self.tb.lake_hex and dice_total in LAKE_NUMBERS:
            lake = self.hexes.get(self.tb.lake_hex)
            if lake is not None:
                for vertex_key, vertex in self.vertices.items():
                    if self.tb.lake_hex in vertex.neighbors.get('hexes', []):
                        player, count = building_yield(vertex_key)
                        if player:
                            demand.append((player, count))

        return demand

    def distribute_fish(self, dice_total: int) -> dict:
        """Draw fish for every producing building on a matching roll.

        Returns {player: fish tokens drawn}. Empty when no fishing source
        matched — or when the supply could not cover the whole table's demand,
        in which case "nobody receives any fish tokens that turn" (515).
        """
        if self.tb is None or dice_total == 7:
            return {}
        if not (self.rules['fishing_grounds'] or self.rules['lake_hex']):
            return {}

        demand = self._fish_demand(dice_total)
        if not demand:
            return {}

        needed = sum(count for _, count in demand)
        if self.tb.available() < needed:
            # Short supply: nobody draws (expansions.md 515).
            self.production_modifiers.add('fish_supply_short')
            return {}

        cap = self.rules['max_fish_held']
        drawn = {}
        for player_name, count in demand:
            for _ in range(count):
                token = self.tb.draw_to_hand(player_name, cap)
                if isinstance(token, int):
                    drawn[player_name] = drawn.get(player_name, 0) + 1
        return {name: drawn[name] for name in sorted(drawn)}

    # --- The spend ladder --------------------------------------------------

    def spend_fish(self, player_name: str, benefit: str, tokens: list,
                   target: str = None, resource: str = None) -> dict:
        """Spend fish tokens for one benefit on your turn.

        `tokens` is the multiset of fish values being spent (e.g. [1, 1, 2] for a
        4-fish benefit). Their total must reach the benefit's price; any excess
        is lost, no change is given (521). Each benefit is validated before a
        single token is spent, so a refused action never eats fish.
        """
        if not self.rules['fish_tokens']:
            return refused('FISH_TOKENS_OFF', 'Fish tokens are not in play')
        if self.tb is None:
            return refused('FISH_TOKENS_OFF', 'Fish tokens are not in play')
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'Cannot spend fish during setup')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} may spend fish')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        price = FISH_BENEFITS.get(benefit)
        if price is None:
            return refused('INVALID_PAYLOAD', f'No such fish benefit: {benefit!r}')

        if not isinstance(tokens, list) or not tokens \
                or any(not isinstance(t, int) or isinstance(t, bool) or t not in (1, 2, 3)
                       for t in tokens):
            return refused('INVALID_PAYLOAD', 'Spend a list of fish tokens (1, 2 or 3)')
        if sum(tokens) < price:
            return refused(
                'NOT_ENOUGH_FISH',
                f'{benefit} costs {price} fish; you offered {sum(tokens)}',
            )

        # Every token must be held — check without removing, so a refusal below
        # leaves the hand intact.
        working = list(self.tb.hand(player_name))
        for token in tokens:
            if token in working:
                working.remove(token)
            else:
                return refused('NOT_ENOUGH_FISH', 'You do not hold those fish tokens')

        # Validate the benefit's own preconditions before spending.
        applied = self._prepare_fish_benefit(player_name, benefit, target, resource)
        if not applied['success']:
            return applied

        # All checks passed: spend the tokens and grant the benefit.
        self.tb.spend(player_name, tokens)
        result = self._grant_fish_benefit(player_name, benefit, applied)
        result['spent'] = list(tokens)
        return result

    def _prepare_fish_benefit(self, player_name, benefit, target, resource) -> dict:
        """Validate a benefit's preconditions without changing state.

        Returns a success dict (carrying whatever `_grant_fish_benefit` needs) or
        a refusal — checked before any token is spent."""
        if benefit == 'steal':
            if target == player_name or self.get_player(target) is None:
                return refused('INVALID_TARGET', 'Choose another player to steal from')
            return {'success': True, 'error': '', 'target': target}
        if benefit == 'bank_card':
            if resource not in self.in_play_resource_types():
                return refused('INVALID_TARGET', 'Choose a resource the board deals')
            if self.bank.resources.get(resource, 0) <= 0:
                return refused('BANK_EMPTY', f'The bank has no {resource} left')
            return {'success': True, 'error': '', 'resource': resource}
        if benefit == 'free_dev':
            if not self.dev_deck_in_play():
                return refused('DEV_CARDS_NOT_IN_PLAY', 'Development cards are not in play')
            if self.bank.total_dev_cards_remaining() <= 0:
                return refused('ACTION_FAILED', 'No development cards left')
            return {'success': True, 'error': ''}
        return {'success': True, 'error': ''}

    def _grant_fish_benefit(self, player_name, benefit, prepared) -> dict:
        """Apply a benefit whose preconditions `_prepare_fish_benefit` cleared."""
        if benefit == 'robber_off':
            # Send the robber off the board without stealing (511). It re-enters
            # on the next 7 or knight, exactly as it started.
            self.robber_hex = None
            self.must_move_robber = False
            self.must_choose_victim = False
            return {'success': True, 'error': '', 'benefit': benefit}
        if benefit == 'steal':
            stolen = self.steal_resource(prepared['target'], player_name)
            return {'success': True, 'error': '', 'benefit': benefit,
                    'target': prepared['target'], 'stolen': stolen}
        if benefit == 'bank_card':
            self.give_resource(player_name, prepared['resource'])
            return {'success': True, 'error': '', 'benefit': benefit,
                    'resource': prepared['resource']}
        if benefit == 'free_road':
            self.free_roads_remaining += 1
            return {'success': True, 'error': '', 'benefit': benefit,
                    'free_roads': self.free_roads_remaining}
        if benefit == 'free_dev':
            card_type = self.bank.draw_dev_card()
            player = self.get_player(player_name)
            player.dev_cards[card_type]['count'] += 1
            # Bought this turn, so it cannot be played the same turn if the table
            # holds cards a turn — the same terms as a purchased card.
            player.dev_cards[card_type]['purchase_turn'] = self.turn_count
            return {'success': True, 'error': '', 'benefit': benefit,
                    'card_type': card_type}
        return {'success': True, 'error': '', 'benefit': benefit}

    # --- The old boot ------------------------------------------------------

    def personal_target_delta(self, player_name: str) -> int:
        """How much this player's own winning threshold is raised.

        The old boot adds 1 to its holder's target (518); nobody else's, and only
        while the rule is on. Read by the win check, so a table without the boot
        wins on the shared target unchanged.
        """
        if self.rules['old_boot'] and self.tb is not None \
                and self.tb.old_boot_holder == player_name:
            return 1
        return 0

    def pass_old_boot(self, player_name: str, target: str) -> dict:
        """Hand the old boot to another player after rolling (519-520).

        Refused unless the giver holds the boot, has rolled this turn, and the
        target has as many victory points as the giver or more. The sole points
        leader must keep it.
        """
        if not self.rules['old_boot'] or self.tb is None:
            return refused('OLD_BOOT_OFF', 'The old boot is not in play')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} may pass the boot')
        if self.tb.old_boot_holder != player_name:
            return refused('NOT_BOOT_HOLDER', 'You do not hold the old boot')
        if not self.has_rolled_dice:
            return refused('WRONG_PHASE', 'Pass the boot after you have rolled')
        if self.get_player(target) is None or target == player_name:
            return refused('INVALID_TARGET', 'Choose another player to take the boot')

        my_points = self.victory_points_for(player_name)
        their_points = self.victory_points_for(target)
        if their_points < my_points:
            return refused(
                'BOOT_STAYS',
                'The boot only passes to a player with as many points as you or more',
            )

        self.tb.give_boot(target)
        return {'success': True, 'error': '', 'target': target}
