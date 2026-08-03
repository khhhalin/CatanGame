"""Cities & Knights actions, on top of the base game.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. `game.cities_knights` holds the expansion's own state and cost tables;
this module is the part that has to reach into the board and the players, so it
is a mixin on Game rather than methods on CitiesKnights.
"""

from game import cities_knights as ck_module


class CitiesKnightsRules:
    """Improvements, knights, city walls, and the barbarian attack."""

    def buy_improvement(self, player_name: str, track: str) -> dict:
        """Buy the next level on a city improvement track.

        Returns {'success': bool, 'error': str, 'level': int,
                 'metropolis': bool, 'took_from': str|None}.
        """
        if not self.ck:
            return {'success': False, 'error': 'Cities & Knights is not enabled'}
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
        if player.commodities.get(commodity, 0) < amount:
            return {
                'success': False,
                'error': f'Need {amount} {commodity} to reach level '
                f'{self.ck.level(player_name, track) + 1}',
            }

        player.commodities[commodity] -= amount
        self.ck.improvements[player_name][track] += 1
        new_level = self.ck.improvements[player_name][track]

        # Claiming a metropolis needs a city that is not already one.
        took_from = None
        gained_metropolis = False
        if new_level >= ck_module.METROPOLIS_LEVEL:
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
        if not self.ck:
            return {'success': False, 'error': 'Cities & Knights is not enabled'}

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
        if not self.ck:
            return {'success': False, 'error': 'Cities & Knights is not enabled'}

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
        if not self.ck:
            return {'success': False, 'error': 'Cities & Knights is not enabled'}

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
        if not self.ck:
            return {'success': False, 'error': 'Cities & Knights is not enabled'}

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
        if not self.ck:
            return {'success': False, 'error': 'Cities & Knights is not enabled'}

        player = self.get_player(player_name)
        if player is None or vertex_key not in player.cities:
            return {'success': False, 'error': 'You have no city there'}
        if self.ck.city_walls.get(player_name, 0) >= ck_module.MAX_CITY_WALLS:
            return {'success': False, 'error': 'You have used all three city walls'}
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
                    # A sole top defender takes a Defender of Catan card.
                    # Ties instead each draw a progress card, which the caller
                    # handles once progress cards exist.
                    self.ck.defender_cards[winners[0]] = (
                        self.ck.defender_cards.get(winners[0], 0) + 1
                    )
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
        }
        if not outcome['barbarian']:
            return outcome

        outcome['arrived'] = self.ck.advance_barbarians()
        outcome['position'] = self.ck.barbarian_position
        if outcome['arrived']:
            outcome['attack'] = self.resolve_barbarian_attack()
        return outcome
