"""Cities & Knights actions, on top of the base game.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. `game.cities_knights` holds the expansion's own state and cost tables;
this module is the part that has to reach into the board and the players, so it
is a mixin on Game rather than methods on CitiesKnights.
"""

from game import cities_knights as ck_module
from game import progress_cards
from game import rules as rules_module
from game.validation import COMMODITY_TYPES, RESOURCE_TYPES


class CitiesKnightsRules:
    """Improvements, knights, city walls, the barbarians, and progress cards.

    Each action below is gated on its own house rule, not on the expansion as
    a whole: a table that agreed to knights and barbarians without commodities
    gets exactly that, and asking for an improvement is refused by name.
    """

    def _rule_is_off(self, rule_id: str) -> dict | None:
        """A refusal naming the rule that would have to be on, or None."""
        if self.rules[rule_id] and self.ck is not None:
            return None
        name = rules_module.RULES_BY_ID[rule_id]['name']
        return {'success': False, 'error': f'"{name}" is not one of this table\'s rules'}

    def buy_improvement(self, player_name: str, track: str, discount: int = 0) -> dict:
        """Buy the next level on a city improvement track.

        `discount` knocks commodities off the price — the Crane progress card
        is the only thing that passes it.

        Returns {'success': bool, 'error': str, 'level': int,
                 'metropolis': bool, 'took_from': str|None}.
        """
        refusal = self._rule_is_off('city_improvements')
        if refusal is not None:
            return refusal
        if track not in ck_module.IMPROVEMENT_TRACKS:
            return {'success': False, 'error': 'Unknown improvement track'}

        player = self.get_player(player_name)
        if player is None:
            return {'success': False, 'error': 'Unknown player'}

        # You need a city to improve. The rulebook is explicit, and without the
        # check a player with only settlements could buy the whole track.
        if not player.cities:
            return {'success': False, 'error': 'You need a city to build improvements'}

        cost = self.ck.next_improvement_cost(player_name, track)
        if cost is None:
            return {'success': False, 'error': 'That track is already at level 5'}

        commodity, amount = cost
        amount = max(0, amount - discount)
        if player.commodities.get(commodity, 0) < amount:
            return {
                'success': False,
                'error': f'Need {amount} {commodity} to reach level '
                f'{self.ck.level(player_name, track) + 1}',
            }

        player.commodities[commodity] -= amount
        self.ck.improvements[player_name][track] += 1
        new_level = self.ck.improvements[player_name][track]

        # Claiming a metropolis needs a city that is not already one. A table
        # that took the tracks without the metropolis rule buys levels for
        # their abilities alone, and level 4 awards nothing.
        took_from = None
        gained_metropolis = False
        if self.rules['metropolis'] and new_level >= ck_module.METROPOLIS_LEVEL:
            free_city = next((v for v in player.cities if not self.ck.is_metropolis(v)), None)
            if free_city or self.ck.metropolis[track] == player_name:
                took_from = self.ck.claim_metropolis(player_name, track, free_city)
                gained_metropolis = self.ck.metropolis[track] == player_name

        return {
            'success': True,
            'error': '',
            'level': new_level,
            'metropolis': gained_metropolis,
            'took_from': took_from,
        }

    def build_knight(self, player_name: str, vertex_key: str) -> dict:
        """Place a new, inactive basic knight.

        A knight must sit on a vacant intersection touching one of the owner's
        roads. The settlement distance rule does not apply to knights.
        """
        refusal = self._rule_is_off('knights')
        if refusal is not None:
            return refusal

        player = self.get_player(player_name)
        vertex = self.vertices.get(vertex_key)
        if player is None or vertex is None:
            return {'success': False, 'error': 'Invalid target'}

        if vertex.building is not None:
            return {'success': False, 'error': 'There is a building there'}

        owner, _ = self.ck.knight_at(vertex_key)
        if owner is not None:
            return {'success': False, 'error': 'There is already a knight there'}

        if not self._touches_own_road(player_name, vertex_key):
            return {'success': False, 'error': 'A knight must be placed on one of your roads'}

        if not self.ck.can_build_knight(player_name, ck_module.BASIC):
            return {'success': False, 'error': 'You have no basic knight pieces left'}

        if not self._can_pay(player, ck_module.KNIGHT_BUILD_COST):
            return {'success': False, 'error': 'A knight costs 1 sheep and 1 ore'}

        self._pay(player, ck_module.KNIGHT_BUILD_COST)
        self.ck.knights_of(player_name).append(ck_module.Knight(vertex_key))
        return {'success': True, 'error': ''}

    def activate_knight(self, player_name: str, vertex_key: str) -> dict:
        """Pay grain to make a knight active. It may not act this turn."""
        refusal = self._rule_is_off('knights')
        if refusal is not None:
            return refusal

        player = self.get_player(player_name)
        owner, knight = self.ck.knight_at(vertex_key)
        if knight is None or owner != player_name:
            return {'success': False, 'error': 'You have no knight there'}
        if knight.active:
            return {'success': False, 'error': 'That knight is already active'}
        if not self._can_pay(player, ck_module.KNIGHT_ACTIVATE_COST):
            return {'success': False, 'error': 'Activating a knight costs 1 wheat'}

        self._pay(player, ck_module.KNIGHT_ACTIVATE_COST)
        knight.active = True
        # A knight may be built and activated on the same turn, but never acts
        # on the turn it was activated.
        knight.activated_this_turn = True
        return {'success': True, 'error': ''}

    def promote_knight(self, player_name: str, vertex_key: str) -> dict:
        """Raise a knight one rank. Mighty needs the Fortress."""
        refusal = self._rule_is_off('knights')
        if refusal is not None:
            return refusal

        player = self.get_player(player_name)
        owner, knight = self.ck.knight_at(vertex_key)
        if knight is None or owner != player_name:
            return {'success': False, 'error': 'You have no knight there'}

        allowed, reason = self.ck.can_promote(player_name, knight)
        if not allowed:
            return {'success': False, 'error': reason}
        if not self._can_pay(player, ck_module.KNIGHT_PROMOTE_COST):
            return {'success': False, 'error': 'Promoting a knight costs 1 sheep and 1 ore'}

        self._pay(player, ck_module.KNIGHT_PROMOTE_COST)
        knight.rank += 1
        return {'success': True, 'error': ''}

    def move_knight(self, player_name: str, from_vertex: str, to_vertex: str) -> dict:
        """Move an active knight along the owner's roads, displacing if stronger."""
        refusal = self._rule_is_off('knights')
        if refusal is not None:
            return refusal

        owner, knight = self.ck.knight_at(from_vertex)
        if knight is None or owner != player_name:
            return {'success': False, 'error': 'You have no knight there'}
        if not knight.can_act():
            if knight.activated_this_turn:
                return {'success': False, 'error': 'A knight cannot act the turn it is activated'}
            if not knight.active:
                return {'success': False, 'error': 'That knight is not active'}
            return {'success': False, 'error': 'That knight has already acted this turn'}

        target = self.vertices.get(to_vertex)
        if target is None:
            return {'success': False, 'error': 'Invalid target'}
        if target.building is not None:
            return {'success': False, 'error': 'There is a building there'}
        if not self._touches_own_road(player_name, to_vertex):
            return {'success': False, 'error': 'A knight moves along your own roads'}

        other_owner, other_knight = self.ck.knight_at(to_vertex)
        displaced = None
        if other_knight is not None:
            if other_owner == player_name:
                return {'success': False, 'error': 'Your own knight is standing there'}
            if knight.rank <= other_knight.rank:
                return {
                    'success': False,
                    'error': 'You can only displace a knight weaker than yours',
                }
            new_home = self._displacement_target(other_owner, to_vertex)
            if new_home is None:
                # Nowhere legal to retreat to, so the knight is removed.
                self.ck.knights_of(other_owner).remove(other_knight)
            else:
                other_knight.vertex = new_home
            displaced = other_owner

        knight.vertex = to_vertex
        knight.spend_action()
        return {'success': True, 'error': '', 'displaced': displaced}

    def _displacement_target(self, owner: str, from_vertex: str):
        """A vacant intersection connected to `owner`'s roads, next to where the
        displaced knight stood."""
        vertex = self.vertices.get(from_vertex)
        if vertex is None:
            return None
        for candidate in vertex.neighbors.get('vertices', []):
            neighbour = self.vertices.get(candidate)
            if neighbour is None or neighbour.building is not None:
                continue
            if self.ck.knight_at(candidate)[1] is not None:
                continue
            if self._touches_own_road(owner, candidate):
                return candidate
        return None

    def _can_pay(self, player, cost: dict) -> bool:
        return all(player.resources.get(res, 0) >= amount for res, amount in cost.items())

    def _pay(self, player, cost: dict):
        for res, amount in cost.items():
            player.resources[res] = player.resources.get(res, 0) - amount
            self.bank.return_resources(res, amount)

    def build_city_wall(self, player_name: str, vertex_key: str) -> dict:
        """Two brick for +2 hand limit on a 7. Max three per player."""
        refusal = self._rule_is_off('city_walls')
        if refusal is not None:
            return refusal

        player = self.get_player(player_name)
        if player is None or vertex_key not in player.cities:
            return {'success': False, 'error': 'You have no city there'}
        if self.ck.city_walls.get(player_name, 0) >= self.ck.max_city_walls:
            return {
                'success': False,
                'error': f'You have used all {self.ck.max_city_walls} city walls',
            }
        if not self._can_pay(player, ck_module.CITY_WALL_COST):
            return {'success': False, 'error': 'A city wall costs 2 brick'}

        self._pay(player, ck_module.CITY_WALL_COST)
        self.ck.city_walls[player_name] = self.ck.city_walls.get(player_name, 0) + 1
        return {'success': True, 'error': ''}

    def roll_event_die(self) -> str:
        """One of three barbarian faces or a discipline's city gate."""
        return self.rng.choice(ck_module.EVENT_FACES)

    def resolve_barbarian_attack(self) -> dict:
        """Compare Catan's active knights against the barbarians.

        Attack strength is the number of cities and metropolises on the board;
        defence is the total strength of every active knight. Ties defend
        successfully — the rule is "greater than or equal".
        """
        attack = sum(len(p.cities) for p in self.players)
        defence = self.ck.total_knight_strength()

        contributions = {p.name: self.ck.total_knight_strength(p.name) for p in self.players}

        result = {
            'attack': attack,
            'defence': defence,
            'won': defence >= attack,
            'contributions': contributions,
            'defenders': [],
            'pillaged': [],
        }

        if result['won']:
            best = max(contributions.values(), default=0)
            if best > 0:
                winners = [n for n, v in contributions.items() if v == best]
                result['defenders'] = winners
                if len(winners) == 1:
                    # A sole top defender takes a Defender of Catan card, worth
                    # 1 victory point (expansions.md 414, 483).
                    self.ck.defender_cards[winners[0]] = (
                        self.ck.defender_cards.get(winners[0], 0) + 1
                    )
                else:
                    # Tied defenders each draw a progress card of their choice
                    # from any deck. There is no mechanism for "of their
                    # choice" yet, so the deck is picked at random rather than
                    # the draw being skipped entirely.
                    result['draws'] = {}
                    for winner in winners:
                        deck_name = self.rng.choice(progress_cards.DECKS)
                        drawn = self._grant_progress_card(winner, deck_name)
                        if drawn:
                            result['draws'][winner] = drawn
        else:
            # The weakest defenders each lose a city. A player with no cities,
            # or whose only cities are metropolises, is untouched.
            eligible = {
                name: strength
                for name, strength in contributions.items()
                if self._has_pillageable_city(name)
            }
            if eligible:
                worst = min(eligible.values())
                for name, strength in eligible.items():
                    if strength == worst:
                        if self._pillage_city(name):
                            result['pillaged'].append(name)

        self.ck.deactivate_all()
        self.ck.reset_barbarians()
        return result

    def _has_pillageable_city(self, player_name: str) -> bool:
        player = self.get_player(player_name)
        if player is None:
            return False
        return any(not self.ck.is_metropolis(v) for v in player.cities)

    def _pillage_city(self, player_name: str) -> bool:
        """Turn one city back into a settlement. A metropolis is never taken."""
        player = self.get_player(player_name)
        target = next((v for v in player.cities if not self.ck.is_metropolis(v)), None)
        if target is None:
            return False

        player.cities.remove(target)
        player.settlements.append(target)
        vertex = self.vertices.get(target)
        if vertex and vertex.building:
            vertex.building['type'] = 'settlement'

        # A wall on the pillaged city is destroyed with it.
        if self.ck.city_walls.get(player_name, 0) > 0:
            self.ck.city_walls[player_name] -= 1
        return True

    def _resolve_event_die(self, red_die: int) -> dict:
        """Roll the C&K event die and act on it.

        Three of its six faces advance the barbarian ship; the other three open
        a city gate for one discipline, which is what lets players draw progress
        cards (the red production die decides who qualifies).
        """
        face = self.roll_event_die()
        self.ck.last_event = face
        self.ck.last_red_die = red_die

        outcome = {
            'face': face,
            'red_die': red_die,
            'barbarian': face == ck_module.EVENT_BARBARIAN,
            'arrived': False,
            'position': self.ck.barbarian_position,
            'attack': None,
            'draws': {},
        }
        if not outcome['barbarian']:
            outcome['draws'] = self._deal_progress_cards(face, red_die)
            return outcome

        outcome['arrived'] = self.ck.advance_barbarians()
        outcome['position'] = self.ck.barbarian_position
        if outcome['arrived']:
            outcome['attack'] = self.resolve_barbarian_attack()
        return outcome

    # --- Progress cards ----------------------------------------------------

    def _deal_progress_cards(self, deck_name: str, red_die: int) -> dict:
        """Deal on a city gate face. Returns {player: card id} for who drew.

        Every player qualifies, not only the active one: eligibility is the
        player's own improvement level against the red production die, which is
        why the die value is threaded through from the roll.
        """
        draws = {}
        for player in self.players:
            level = self.ck.level(player.name, deck_name)
            if red_die > progress_cards.draw_threshold(level):
                continue
            drawn = self._grant_progress_card(player.name, deck_name)
            if drawn:
                draws[player.name] = drawn
        return draws

    def _grant_progress_card(self, player_name: str, deck_name: str) -> str | None:
        """Put one card from a deck into a player's hand. Returns its id.

        A card worth a victory point is revealed the moment it is drawn: it
        scores at once and never takes a place in hand. Everything else is
        refused if the player is already at the four-card limit, and goes back
        under the deck rather than out of the game.
        """
        card_id = self.ck.draw_progress_card(deck_name, self.rng)
        if card_id is None:
            return None

        card = progress_cards.CARDS_BY_ID[card_id]
        if card['victory_points']:
            player = self.get_player(player_name)
            if player is not None:
                # `Player.victory_points` is exactly this: cards already
                # revealed rather than held, so the total picks it up with no
                # change to the scoring code.
                player.victory_points += card['victory_points']
            return card_id

        if self.ck.hand_is_full(player_name):
            self.ck.return_progress_card(deck_name, card_id)
            return None

        self.ck.hand_of(player_name).append(card_id)
        return card_id

    def play_progress_card(self, player_name: str, card_id: str, target=None) -> dict:
        """Play a progress card the player is holding.

        `target` is whatever the card's `needs_target` calls for; the handler
        checks its shape, and the per-card method below checks it against the
        board.
        """
        refusal = self._rule_is_off('progress_cards')
        if refusal is not None:
            return refusal

        card = progress_cards.CARDS_BY_ID.get(card_id)
        if card is None:
            return {'success': False, 'error': 'Unknown progress card'}

        hand = self.ck.hand_of(player_name)
        if card_id not in hand:
            return {'success': False, 'error': 'You are not holding that card'}

        if card['timing'] == progress_cards.TIMING_BEFORE_ROLL:
            if self.has_rolled_dice:
                return {'success': False, 'error': f"{card['name']} is played before the dice"}
        elif not self.has_rolled_dice:
            return {'success': False, 'error': 'Roll the dice before playing a progress card'}

        resolve = getattr(self, f'_progress_{card_id}', None)
        if resolve is None:
            return {'success': False, 'error': f"{card['name']} is not implemented yet"}

        result = resolve(player_name, target)
        if not result['success']:
            result.setdefault('error', 'That card cannot be played')
            return result

        # Spent cards go back under their own deck. C&K keeps a discard pile and
        # reshuffles it when a deck runs out; the bottom of the deck is the same
        # thing without a second pile to track.
        hand.remove(card_id)
        self.ck.return_progress_card(card['deck'], card_id)
        result.setdefault('error', '')
        result['card'] = card_id
        return result

    # Each card below returns {'success': bool, 'error': str, ...}. A card that
    # would do nothing may not be played — but only where the no-op is visible
    # from the player's own board. Refusing a monopoly because nobody holds the
    # named card would tell the player what the table is hiding.

    def _progress_road_building(self, player_name: str, target) -> dict:
        self.free_roads_remaining += 2
        return {'success': True, 'free_roads': self.free_roads_remaining}

    def _progress_irrigation(self, player_name: str, target) -> dict:
        return self._terrain_bounty(player_name, 'wheat')

    def _progress_mining(self, player_name: str, target) -> dict:
        return self._terrain_bounty(player_name, 'ore')

    def _terrain_bounty(self, player_name: str, terrain: str) -> dict:
        """Two cards of `terrain` per building next to a hex of that type.

        Per building, not per adjacency: a settlement wedged between two fields
        still pays twice, not four times.
        """
        player = self.get_player(player_name)
        if player is None:
            return {'success': False, 'error': 'Unknown player'}

        qualifying = 0
        for vertex_key in player.settlements + player.cities:
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            if any(
                self.hexes.get(hex_key) is not None and self.hexes[hex_key].type == terrain
                for hex_key in vertex.neighbors.get('hexes', [])
            ):
                qualifying += 1

        if not qualifying:
            return {'success': False, 'error': f'You have no building next to a {terrain} hex'}

        gained = 0
        for _ in range(qualifying * 2):
            if self.bank.take(terrain):
                player.resources[terrain] = player.resources.get(terrain, 0) + 1
                gained += 1
        return {'success': True, 'gained': {terrain: gained}}

    def _progress_warlord(self, player_name: str, target) -> dict:
        idle = [k for k in self.ck.knights_of(player_name) if not k.active]
        if not idle:
            return {'success': False, 'error': 'All of your knights are already active'}

        for knight in idle:
            knight.active = True
            # Exactly as if grain had been paid: a knight never acts on the
            # turn it wakes up.
            knight.activated_this_turn = True
        return {'success': True, 'activated': len(idle)}

    def _progress_resource_monopoly(self, player_name: str, target) -> dict:
        """Two of one resource from every other player, or all they hold."""
        return self._monopoly(player_name, target, RESOURCE_TYPES, 'resources', amount=2)

    def _progress_trade_monopoly(self, player_name: str, target) -> dict:
        """One of one commodity from every other player."""
        return self._monopoly(player_name, target, COMMODITY_TYPES, 'commodities', amount=1)

    def _monopoly(self, player_name: str, target, allowed, hand_attr: str, amount: int) -> dict:
        if target not in allowed:
            return {'success': False, 'error': 'Name one of: ' + ', '.join(allowed)}

        player = self.get_player(player_name)
        if player is None:
            return {'success': False, 'error': 'Unknown player'}

        mine = getattr(player, hand_attr)
        taken = {}
        for other in self.players:
            if other.name == player_name:
                continue
            theirs = getattr(other, hand_attr)
            moved = min(amount, theirs.get(target, 0))
            if not moved:
                continue
            theirs[target] = theirs[target] - moved
            mine[target] = mine.get(target, 0) + moved
            taken[other.name] = moved

        return {'success': True, 'card_type': target, 'taken': taken}

    def _progress_smith(self, player_name: str, target) -> dict:
        """Promote up to two of the player's own knights, free.

        Applied one at a time: the piece supply is checked per promotion, so
        validating both against the state before either happened would let a
        player end up with three strong knights.
        """
        vertices = list(target or [])
        if not 1 <= len(vertices) <= 2:
            return {'success': False, 'error': 'Choose one or two of your own knights'}

        promoted = []
        for vertex_key in vertices:
            owner, knight = self.ck.knight_at(vertex_key)
            if knight is None or owner != player_name:
                break
            allowed, _reason = self.ck.can_promote(player_name, knight)
            if not allowed:
                break
            knight.rank += 1
            promoted.append(vertex_key)

        if not promoted:
            return {'success': False, 'error': 'None of those knights can be promoted'}
        return {'success': True, 'promoted': promoted}

    def _progress_engineer(self, player_name: str, target) -> dict:
        """One city wall, free."""
        player = self.get_player(player_name)
        if player is None or target not in player.cities:
            return {'success': False, 'error': 'You have no city there'}
        if self.ck.city_walls.get(player_name, 0) >= self.ck.max_city_walls:
            return {
                'success': False,
                'error': f'You have used all {self.ck.max_city_walls} city walls',
            }

        self.ck.city_walls[player_name] = self.ck.city_walls.get(player_name, 0) + 1
        return {'success': True, 'vertex': target}

    def _progress_medicine(self, player_name: str, target) -> dict:
        """Upgrade a settlement for 2 ore and 1 grain instead of the usual cost."""
        cost = {'ore': 2, 'wheat': 1}
        player = self.get_player(player_name)
        vertex = self.vertices.get(target)
        if player is None or vertex is None or target not in player.settlements:
            return {'success': False, 'error': 'You have no settlement there'}
        if not self.has_piece_available(player_name, 'city'):
            return {'success': False, 'error': f'You have used all {self.MAX_CITIES} cities'}
        if not self._can_pay(player, cost):
            return {'success': False, 'error': 'Medicine still costs 2 ore and 1 wheat'}

        self._pay(player, cost)
        vertex.building = {'type': 'city', 'player': player_name}
        player.settlements.remove(target)
        player.cities.append(target)
        self.update_harbormaster()
        return {'success': True, 'vertex': target}

    def _progress_crane(self, player_name: str, target) -> dict:
        """One city improvement for one commodity less than the list price."""
        return self.buy_improvement(player_name, target, discount=1)

    def _progress_inventor(self, player_name: str, target) -> dict:
        """Swap two number tokens. The board's best and worst numbers are safe."""
        protected = {2, 6, 8, 12}
        keys = list(target or [])
        if len(keys) != 2 or keys[0] == keys[1]:
            return {'success': False, 'error': 'Choose two different number tokens'}

        chosen = [self.hexes.get(key) for key in keys]
        if any(hex_obj is None or hex_obj.number is None for hex_obj in chosen):
            return {'success': False, 'error': 'Both hexes must carry a number token'}
        if any(hex_obj.number in protected for hex_obj in chosen):
            return {'success': False, 'error': 'The 2, 6, 8 and 12 tokens cannot be moved'}

        chosen[0].number, chosen[1].number = chosen[1].number, chosen[0].number
        return {'success': True, 'swapped': keys}

    def _progress_intrigue(self, player_name: str, target) -> dict:
        """Displace an opponent's knight next to one of your roads.

        No stronger knight needed — that is the whole point of the card.
        """
        vertex_key = target[0] if isinstance(target, list) else target
        owner, knight = self.ck.knight_at(vertex_key)
        if knight is None or owner == player_name:
            return {'success': False, 'error': "That is not an opponent's knight"}
        if not self._touches_own_road(player_name, vertex_key):
            return {'success': False, 'error': 'That knight is not next to one of your roads'}

        new_home = self._displacement_target(owner, vertex_key)
        if new_home is None:
            self.ck.knights_of(owner).remove(knight)
        else:
            knight.vertex = new_home
        return {'success': True, 'displaced': owner}

    def _progress_bishop(self, player_name: str, target) -> dict:
        """Move the robber, then steal from everyone it now touches."""
        hex_obj = self.hexes.get(target)
        if hex_obj is None or hex_obj.type == 'ocean':
            return {'success': False, 'error': 'The robber goes on a land hex'}
        if not self.robber_is_allowed(target):
            return {'success': False, 'error': 'Friendly Robber: pick another hex'}

        self.robber_hex = target
        stolen = {}
        for victim in self.get_robber_victims():
            if victim == player_name:
                continue
            card = self.steal_resource(victim, player_name)
            if card:
                stolen[victim] = card
        return {'success': True, 'hex': target, 'stolen': stolen}

    def _progress_saboteur(self, player_name: str, target) -> dict:
        """Everyone level with the player or ahead discards half their hand.

        The player themselves is excluded: "as many victory points" is trivially
        true of yourself, and the card is not meant to cost its owner anything.
        """
        threshold = self.victory_points_for(player_name)
        hit = {}
        for other in self.players:
            if other.name == player_name:
                continue
            if self.victory_points_for(other.name) < threshold:
                continue
            owed = other.total_cards() // 2
            if owed:
                self.players_needing_discard[other.name] = owed
                hit[other.name] = owed

        return {'success': True, 'discards': hit}
