"""Catan: Oil Springs — oil production, the disaster track, and sequestering.

The scenario by Erik Assadourian & Ty Hansen for Klaus Teuber's Settlers of
Catan (coilspringsgb_2015_web.pdf, the 3-4 player rules on pp. 1-2). One mixin
on `Game`, the pattern the other scenario modules use (see `cloth_for_catan.py`,
`fishing.py`). Every method is gated on the individual rule that governs it —
never on the scenario's name — so a table not running Oil Springs is untouched:

- `oil_tokens` — buildings on an oil spring produce oil (1/settlement, 2/city,
  3/metropolis) on the hex's number, capped at 4 held per player.
- `disaster_track` — using oil advances a shared track; every fifth oil used
  triggers a disaster at the end of the turn (a 7 floods the coasts, otherwise a
  hex is polluted and loses its number), and the board dies at five lost tokens.
- `oil_sequester_vp` — sequestering oil scores 1 VP per 3, and the first to
  sequester 3 takes the 1-VP Champion of the Environment token.
- `oil_metropolis` — 2 oil plus 1 brick/grain/ore upgrades a city into a 3-VP,
  flood-proof metropolis.

Oil lives on `Player.oil`, the way gold lives on `Player.gold`: a public
currency, not a resource card. The general supply, the disaster track and the
removed-token count live on the game and are read straight off it.
"""

from game.results import refused

# 3-4 player component counts (coilspringsgb_2015_web.pdf p. 1: "use 15 for
# 3-4 players"; "you may only hold a maximum of 4 oil").
OIL_SUPPLY = 15
MAX_OIL_HELD = 4

# The oil a building on an oil spring produces (p. 1): a settlement one, a city
# two, a metropolis three.
OIL_PER_SETTLEMENT = 1
OIL_PER_CITY = 2
OIL_PER_METROPOLIS = 3

# A disaster fires when the shared track reaches this, and no more oil may be
# used in a turn once it does ("For every five oil used ... a disaster", p. 2).
DISASTER_THRESHOLD = 5

# Converting oil pays two of one resource for one oil (p. 2, "convert 1 oil into
# 2 of the same ... resource").
RESOURCES_PER_OIL = 2

# The board dies when this many number tokens have been destroyed by pollution
# (p. 3, 3-4 player rules: "the fifth number token is removed").
BOARD_DEATH_REMOVED = 5


class OilSpringsRules:
    """Oil production and the general supply. The disaster track, sequestering
    and metropolises are folded in by the later chunks of this mixin."""

    # --- Board setup -------------------------------------------------------

    def setup_oil_springs(self):
        """Read the oil-spring hexes off the dealt board into game state.

        An oil spring is a hex whose metadata carries `oil_spring` — read the
        same way the Fishermen read their grounds off hex metadata. A no-op for
        a board that prints none, and off the `oil_tokens` rule, so every other
        board is unaffected.
        """
        if not self.rules['oil_tokens']:
            return
        springs = set()
        for hex_key, hex_obj in self.hexes.items():
            meta = getattr(hex_obj, 'meta', None)
            if meta is not None and getattr(meta, 'oil_spring', False):
                springs.add(hex_key)
        self.oil_spring_hexes = springs

    # --- Production --------------------------------------------------------

    def _oil_building_yield(self, vertex_key: str):
        """The oil a building on `vertex_key` produces, and its owner.

        Returns (player, count): a settlement one, a city two, and a metropolis
        three. (None, 0) for an empty vertex. A metropolis is a city the table
        has upgraded — recorded in `oil_metropolises` — so it is checked before
        the plain city.
        """
        vertex = self.vertices.get(vertex_key)
        if vertex is None or not vertex.building:
            return None, 0
        player = vertex.building.get('player')
        if not player:
            return None, 0
        btype = vertex.building.get('type')
        if vertex_key in self.oil_metropolises:
            return player, OIL_PER_METROPOLIS
        if btype == 'city':
            return player, OIL_PER_CITY
        if btype in ('settlement', 'harbor_settlement'):
            return player, OIL_PER_SETTLEMENT
        return None, 0

    def distribute_oil(self, dice_total: int, roller_name: str) -> dict:
        """Produce oil for every building on an oil spring whose number came up.

        Oil is handed out one token at a time, starting with the player who
        rolled and going clockwise, until everyone has what they produced or the
        supply is exhausted (p. 1). A player may never be pushed past the 4-oil
        hold cap, so any excess they produced is simply not taken. Returns
        {player: oil produced}; empty on a 7, off the rule, and on a board with
        no springs.
        """
        if not self.rules['oil_tokens'] or dice_total == 7:
            return {}
        if not self.oil_spring_hexes:
            return {}

        owed = {}
        for hex_key in self.oil_spring_hexes:
            hex_obj = self.hexes.get(hex_key)
            if hex_obj is None or hex_obj.number != dice_total:
                continue
            for vertex_key in self._oil_spring_vertices(hex_key):
                player, count = self._oil_building_yield(vertex_key)
                if player:
                    owed[player] = owed.get(player, 0) + count
        if not owed:
            return {}

        # Clockwise from the roller: rotate the seating so the roller is first.
        order = [player.name for player in self.players]
        if roller_name in order:
            start = order.index(roller_name)
            order = order[start:] + order[:start]

        produced = {}
        # One token at a time, round-robin, until nobody can take another —
        # either they are owed no more, are at the hold cap, or the supply is
        # spent.
        progress = True
        while progress and self.oil_supply > 0:
            progress = False
            for name in order:
                if self.oil_supply <= 0:
                    break
                if owed.get(name, 0) <= 0:
                    continue
                player = self.get_player(name)
                if player is None or player.oil >= MAX_OIL_HELD:
                    owed[name] = 0
                    continue
                player.oil += 1
                self.oil_supply -= 1
                owed[name] -= 1
                produced[name] = produced.get(name, 0) + 1
                progress = True
        return {name: produced[name] for name in sorted(produced)}

    def _oil_spring_vertices(self, hex_key: str) -> list:
        """The buildable intersections that touch this hex — its six corners that
        exist as vertices, the same walk the Fishermen use for a coastal hex."""
        hx, hy, hz = self._parse_key(hex_key)
        found = []
        for vx, vy, vz in self.VERTEX_DIRECTIONS:
            vertex_key = self._hex_key(hx + vx, hy + vy, hz + vz)
            if vertex_key in self.vertices:
                found.append(vertex_key)
        return found

    # --- Using oil: the disaster track ------------------------------------

    def convert_oil_to_resource(self, player_name: str, resource: str) -> dict:
        """Spend 1 oil for 2 of one resource, advancing the disaster track (p. 2).

        Way 1 of using oil: "convert 1 oil into 2 of the same, non-oil resource
        of your choice." Each conversion advances the shared track by one; once
        it reaches 5 no more oil may be used this turn, and a disaster resolves
        at the end of the turn. The oil spent goes back to the general supply.
        """
        if not self.rules['disaster_track']:
            return refused('RULE_OFF', 'Oil conversion is not in play')

        block = self._oil_action_block(player_name)
        if block is not None:
            return block

        player = self.get_player(player_name)
        if player.oil < 1:
            return refused('NO_OIL', 'You have no oil to use')
        if resource not in self.in_play_resource_types():
            return refused('INVALID_RESOURCE', 'Choose a resource the board deals')
        if self.disaster_track >= DISASTER_THRESHOLD:
            return refused(
                'DISASTER_IMMINENT',
                'No more oil can be used this turn — a disaster is about to strike',
            )
        if self.bank.resources.get(resource, 0) < RESOURCES_PER_OIL:
            return refused('BANK_EMPTY', f'The bank has too little {resource}')

        player.oil -= 1
        self.oil_supply += 1
        for _ in range(RESOURCES_PER_OIL):
            self.bank.take(resource)
        player.resources[resource] = player.resources.get(resource, 0) + RESOURCES_PER_OIL
        self._advance_disaster_track(1)
        return {'success': True, 'error': '', 'resource': resource,
                'oil': player.oil, 'disaster_track': self.disaster_track}

    def _oil_action_block(self, player_name: str):
        """Shared turn checks for a during-your-turn oil action, or None."""
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'You cannot use oil during setup')
        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} may use oil')
        if self.get_player(player_name) is None:
            return refused('NO_SUCH_PLAYER', 'No such player')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        return None

    def _advance_disaster_track(self, count: int):
        """Advance the shared track by `count` oil used and note the usage.

        The per-turn count feeds the sequester mutual-exclusion (chunk 3); the
        shared track is what triggers the disaster phase.
        """
        self.disaster_track += count
        self.oil_used_this_turn += count

    def oil_disaster_owed(self) -> bool:
        """Whether this turn's oil use owes a disaster at the turn's end."""
        return self.rules['disaster_track'] and self.disaster_track >= DISASTER_THRESHOLD

    # --- The disaster phase ------------------------------------------------

    def resolve_oil_disaster(self) -> dict:
        """Resolve one disaster at the end of a turn and reset the track (p. 2).

        Rolls two dice: a 7 floods the coasts, any other number pollutes a hex
        carrying it. Returns what happened — the roll, the kind, what was lost —
        plus a `game_over` if the board has died. Deterministic through the
        game's own generator, so a test can script the disaster roll.
        """
        die1 = self.rng.randint(1, 6)
        die2 = self.rng.randint(1, 6)
        total = die1 + die2

        if total == 7:
            detail = {'kind': 'flood', 'flooded': self._disaster_flood()}
        else:
            detail = {'kind': 'pollution', **self._disaster_pollution(total)}

        self.disaster_track = 0

        game_over = None
        if self.oil_numbers_removed >= BOARD_DEATH_REMOVED:
            self.game_state = 'finished'
            # No player truly wins; the Champion of the Environment takes a
            # Pyrrhic victory (p. 3). None when nobody has sequestered enough.
            game_over = {'winner': self.oil_champion, 'reason': 'board_dead',
                         'victory_points': self.victory_points_for(self.oil_champion)
                         if self.oil_champion else 0}

        return {'die1': die1, 'die2': die2, 'total': total,
                'numbers_removed': self.oil_numbers_removed,
                'game_over': game_over, **detail}

    def _disaster_flood(self) -> list:
        """Coastal flooding on a 7 (p. 2).

        Every settlement bordering a sea hex is removed and returned to its
        owner's supply; every coastal city is reduced to a settlement. A
        metropolis is flood-proof, and roads are never touched. Returns the list
        of {vertex, player, was, now} changes, sorted for a stable payload.
        """
        changes = []
        for vertex_key in sorted(self.vertices):
            vertex = self.vertices[vertex_key]
            if not vertex.building:
                continue
            if not self._borders_sea(vertex_key):
                continue
            if vertex_key in self.oil_metropolises:
                continue
            player_name = vertex.building.get('player')
            player = self.get_player(player_name)
            was = vertex.building.get('type')
            if was == 'city':
                if player and vertex_key in player.cities:
                    player.cities.remove(vertex_key)
                    player.settlements.append(vertex_key)
                vertex.building = {'type': 'settlement', 'player': player_name}
                changes.append({'vertex': vertex_key, 'player': player_name,
                                'was': 'city', 'now': 'settlement'})
            elif was in ('settlement', 'harbor_settlement'):
                if player and vertex_key in player.settlements:
                    player.settlements.remove(vertex_key)
                if player and vertex_key in getattr(player, 'harbor_settlements', []):
                    player.harbor_settlements.remove(vertex_key)
                vertex.building = None
                changes.append({'vertex': vertex_key, 'player': player_name,
                                'was': was, 'now': None})
        return changes

    def _borders_sea(self, vertex_key: str) -> bool:
        """Whether this intersection is a corner of an open-sea hex.

        A vertex only lists its *land* hexes in its neighbours, so the coast is
        read the other way round — from the sea hexes' corners, the same walk the
        Fishermen use — and cached, since the board's water never moves.
        """
        return vertex_key in self._sea_coast_vertices()

    def _sea_coast_vertices(self) -> set:
        """The intersections that are a corner of an ocean hex, cached."""
        cached = getattr(self, '_oil_coast_cache', None)
        if cached is not None:
            return cached
        coast = set()
        for hex_key, hex_obj in self.hexes.items():
            if hex_obj.type != 'ocean':
                continue
            coast.update(self._oil_spring_vertices(hex_key))
        self._oil_coast_cache = coast
        return coast

    def _disaster_pollution(self, total: int) -> dict:
        """Industrial pollution on a non-7 roll (p. 2).

        A hex carrying the rolled number is struck. If more than one shares it,
        one is chosen at random; if the number is on no hex any more, nothing
        happens. An oil spring loses 3 oil from the general supply (unrecoverable)
        and keeps its number; any other hex loses its number token for good, and
        the fifth token lost dies the board.
        """
        candidates = sorted(
            key for key, hex_obj in self.hexes.items()
            if hex_obj.number == total and hex_obj.type != 'ocean'
        )
        if not candidates:
            return {'hex': None, 'polluted': False}

        target = candidates[0] if len(candidates) == 1 else self.rng.choice(candidates)
        if target in self.oil_spring_hexes:
            lost = min(3, self.oil_supply)
            self.oil_supply -= lost
            return {'hex': target, 'oil_spring': True, 'oil_lost': lost,
                    'polluted': False}

        self.hexes[target].number = None
        self.oil_numbers_removed += 1
        return {'hex': target, 'oil_spring': False, 'polluted': True}

    # --- Sequestering oil --------------------------------------------------

    def sequester_oil(self, player_name: str) -> dict:
        """Flip one oil out of the game for environmental credit (p. 2).

        An alternative to using oil: forgo one, one per turn, and it leaves the
        game for good (it is not returned to the supply). It does not advance the
        disaster track, and because it is not "usage" it cannot be mixed with
        using oil in the same turn. Every three sequestered score a victory
        point, and reaching three first (or overtaking the holder) takes the
        Champion of the Environment token.
        """
        if not self.rules['oil_sequester_vp']:
            return refused('RULE_OFF', 'Sequestering oil is not in play')

        block = self._oil_action_block(player_name)
        if block is not None:
            return block

        player = self.get_player(player_name)
        if player.oil < 1:
            return refused('NO_OIL', 'You have no oil to sequester')
        if self.oil_sequestered_this_turn:
            return refused('ALREADY_SEQUESTERED', 'You may sequester only one oil per turn')
        if self.oil_used_this_turn > 0:
            return refused('OIL_ALREADY_USED', 'You cannot sequester after using oil this turn')

        player.oil -= 1  # out of the game for good — not back to the supply
        self.oil_sequestered[player_name] = self.oil_sequestered.get(player_name, 0) + 1
        self.oil_sequestered_this_turn = True
        self._update_oil_champion(player_name)
        return {'success': True, 'error': '', 'oil': player.oil,
                'sequestered': self.oil_sequestered[player_name],
                'champion': self.oil_champion}

    def _update_oil_champion(self, player_name: str):
        """Award or move the Champion of the Environment token (p. 2).

        The first player to reach three sequestered oil gains it; thereafter it
        moves to anyone who sequesters strictly more than the current holder.
        """
        seq = self.oil_sequestered.get(player_name, 0)
        if seq < 3:
            return
        if self.oil_champion is None:
            self.oil_champion = player_name
        elif player_name != self.oil_champion \
                and seq > self.oil_sequestered.get(self.oil_champion, 0):
            self.oil_champion = player_name

    def oil_sequester_victory_points(self, player_name: str) -> int:
        """This player's oil victory points: one per three sequestered, plus one
        for holding the Champion of the Environment token (p. 2)."""
        if not self.rules['oil_sequester_vp']:
            return 0
        points = self.oil_sequestered.get(player_name, 0) // 3
        if self.oil_champion == player_name:
            points += 1
        return points

    # --- Metropolises ------------------------------------------------------

    def build_oil_metropolis(self, player_name: str, vertex_key: str) -> dict:
        """Upgrade one of your cities into a flood-proof metropolis (p. 2).

        Costs 1 brick, 1 grain, 1 ore and 2 oil, and the oil used advances the
        disaster track by two like any other use. A metropolis produces three of
        its resource, is worth 3 victory points, and is immune to coastal
        flooding.
        """
        if not self.rules['oil_metropolis']:
            return refused('RULE_OFF', 'Metropolises are not in play')

        block = self._oil_action_block(player_name)
        if block is not None:
            return block

        player = self.get_player(player_name)
        vertex = self.vertices.get(vertex_key)
        if vertex is None or not vertex.building \
                or vertex.building.get('player') != player_name \
                or vertex.building.get('type') != 'city':
            return refused('INVALID_TARGET', 'Choose one of your own cities')
        if vertex_key in self.oil_metropolises:
            return refused('ALREADY_METROPOLIS', 'That city is already a metropolis')
        if player.oil < 2:
            return refused('NOT_ENOUGH_OIL', 'A metropolis costs 2 oil')
        if self.rules['disaster_track'] \
                and self.disaster_track + 2 > DISASTER_THRESHOLD:
            return refused(
                'DISASTER_IMMINENT',
                'Using 2 oil now would push the disaster track past 5',
            )
        cost = {'brick': 1, 'wheat': 1, 'ore': 1}
        for resource, amount in cost.items():
            if player.resources.get(resource, 0) < amount:
                return refused('INSUFFICIENT_RESOURCES',
                               'A metropolis costs 1 brick, 1 grain and 1 ore')

        for resource, amount in cost.items():
            player.resources[resource] -= amount
            self.bank.return_resources(resource, amount)
        player.oil -= 2
        self.oil_supply += 2  # oil used to build returns to the supply (p. 2)
        self.oil_metropolises[vertex_key] = player_name
        self._advance_disaster_track(2)
        return {'success': True, 'error': '', 'vertex': vertex_key,
                'oil': player.oil, 'disaster_track': self.disaster_track}

    def oil_metropolis_victory_points(self, player_name: str) -> int:
        """The extra victory point each of this player's metropolises adds.

        A metropolis is worth 3 and the city under it already scores 2, so each
        adds one on top of what the city scored (p. 2). A no-op without the rule.
        """
        if not self.rules['oil_metropolis']:
            return 0
        return sum(1 for owner in self.oil_metropolises.values()
                   if owner == player_name)

    # --- Client state ------------------------------------------------------

    def oil_client_state(self) -> dict | None:
        """The oil/disaster panel's state, or None off the scenario.

        The springs so the board can badge them, each player's oil for the
        readout, and the shared supply. The disaster track and sequester totals
        are added by the later chunks.
        """
        if not self.rules['oil_tokens']:
            return None
        return {
            'springs': sorted(self.oil_spring_hexes),
            'supply': self.oil_supply,
            'oil': {player.name: player.oil for player in self.players},
            # The shared disaster track (0-5) and how many number tokens
            # pollution has destroyed toward the board's death at five.
            'disaster_track': self.disaster_track,
            'numbers_removed': self.oil_numbers_removed,
            'board_death_at': BOARD_DEATH_REMOVED,
            # Sequestering: each player's total and who holds the Champion token.
            'sequestered': dict(self.oil_sequestered),
            'champion': self.oil_champion,
            # The upgraded cities (vertex -> owner), so the client can badge a
            # metropolis and know it is flood-proof.
            'metropolises': dict(self.oil_metropolises),
            # Whether this turn's player still has an oil action open — used oil
            # and sequestering are mutually exclusive within a turn.
            'used_oil_this_turn': self.oil_used_this_turn,
            'sequestered_this_turn': self.oil_sequestered_this_turn,
        }
