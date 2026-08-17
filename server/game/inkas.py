"""Catan Histories: Rise of the Inkas — the rise-and-decline of three tribes.

One mixin on `Game`, the pattern the other scenario modules use. Every method is
gated on the individual rule that governs it, never on the expansion name, so a
table not running the scenario is untouched and the base game is unchanged:

- ``tribe_decline`` governs the whole tribe machinery — the apex trigger, the
  decline (roads removed, buildings covered with thickets), the lockdown of a
  declined network (no expansion, no upgrade), and founding the next tribe.
- ``overbuild_ruins`` governs the one placement exception: an active tribe may
  build a settlement over a declining (thicket-covered) settlement or city.
- ``third_tribe_victory`` governs the end: the race is won by the first player to
  bring their third tribe to its cultural apex, not by a plain point threshold.

The mechanic (Catan: Rise of the Inkas rulebook, Teuber 2018, "The Tribes" pp.
7-8, and Game End p. 8):

You develop three successive tribes. Each settlement placed is worth 1 culture
point, a city 2 (the settlement's 1 plus 1 on the upgrade). When a tribe reaches
its cultural apex it declines: you remove all your roads, cover that tribe's
settlements and cities with thickets — they still produce but can never expand or
upgrade — and found the next tribe by placing one free settlement elsewhere. Any
active tribe (yours or an opponent's) may later build over a thicket-covered
building. The first player to reach their **third** tribe's apex wins.

The cultural goals are stated verbatim in the rulebook (p. 7): the 1st and 2nd
tribes each decline at **4** culture points ("either 2 settlements and 1 city or
4 settlements"), and the 3rd tribe wins at **3** ("either 1 settlement and 1 city
or 3 settlements") — 11 culture markers in all (Game Summary p. 2, Game End p. 8).
These thresholds are OFFICIAL, not fan-sourced.
"""

# Cultural goal per tribe (Rise of the Inkas rulebook p. 7, Game End p. 8).
# Reaching a tribe's goal triggers its decline (tribes 1-2) or wins the game
# (tribe 3). The 11-marker total the game ends on is 4 + 4 + 3.
TRIBE_GOALS = {1: 4, 2: 4, 3: 3}
FINAL_TRIBE = 3

# The two starting settlements each place 1 culture marker (rulebook p. 4), so a
# player begins the game with this many culture points in their first tribe.
STARTING_CULTURE_POINTS = 2


class InkasRules:
    """Tribe apex, decline, founding, overbuild and the third-tribe win."""

    # --- Reading the board -------------------------------------------------

    def _building_culture_value(self, building: dict) -> int:
        """A building's culture points: a settlement 1, a city 2 (rulebook p. 7)."""
        return 2 if building.get('type') == 'city' else 1

    def tribe_culture_points(self, player_name: str, tribe_number: int) -> int:
        """Culture points a player has standing on the board for one tribe.

        Read live off the board — every settlement (1) and city (2) this player
        owns tagged with `tribe_number` — so it is the truth about what is built
        rather than a cached counter that could drift. Thicket-covered ruins of a
        past tribe carry an earlier tag and so are not counted for a later tribe.
        """
        total = 0
        for vertex in self.vertices.values():
            building = vertex.building
            if building is None:
                continue
            if building.get('player') != player_name:
                continue
            if building.get('tribe') != tribe_number:
                continue
            total += self._building_culture_value(building)
        return total

    def active_tribe_culture(self, player_name: str) -> int:
        """Culture points in the player's current (active) tribe."""
        player = self.get_player(player_name)
        if player is None:
            return 0
        return self.tribe_culture_points(player_name, player.tribe)

    def is_ruin(self, vertex_key: str) -> bool:
        """Whether a thicket-covered (declining) building stands here."""
        vertex = self.vertices.get(vertex_key)
        return vertex is not None and vertex.building is not None \
            and bool(vertex.building.get('ruined'))

    def tag_building_tribe(self, player_name: str, vertex_key: str) -> None:
        """Tag a just-placed building with its owner's active tribe.

        Called by `place_settlement`/`upgrade_city` for every build, gated on
        `tribe_decline`. The tag is what lets a tribe's apex be measured and its
        pieces covered on decline; a city keeps the tag its settlement already
        carried. Also advances the owner's cumulative culture-marker count, which
        the panel shows and the 11-marker total is read from. A no-op off the
        rule, so the building dict stays exactly as the base game writes it.
        """
        if not self.rules['tribe_decline']:
            return
        vertex = self.vertices.get(vertex_key)
        if vertex is None or vertex.building is None:
            return
        player = self.get_player(player_name)
        if player is None:
            return
        vertex.building.setdefault('tribe', player.tribe)
        player.culture_points += 1

    # --- The apex trigger --------------------------------------------------

    def founding_required(self, player_name: str) -> bool:
        """Whether this player owes a free founding settlement before acting."""
        return self.rules['tribe_decline'] and self.founding_player == player_name

    def check_tribe_transition(self, player_name: str) -> dict | None:
        """After a build, decline the tribe if it has just reached its apex.

        Gated on `tribe_decline`. The 1st and 2nd tribes decline at their goal
        (rulebook p. 7); reaching the 3rd tribe's goal is the win, handled by
        `claim_victory`, so this returns None for it and never declines a third
        tribe. Returns a summary of the decline for the log, or None when the
        active tribe has not reached its goal.
        """
        if not self.rules['tribe_decline']:
            return None
        player = self.get_player(player_name)
        if player is None or player.tribe >= FINAL_TRIBE:
            return None
        if self.active_tribe_culture(player_name) < TRIBE_GOALS[player.tribe]:
            return None
        return self.decline_tribe(player_name)

    # --- Decline -----------------------------------------------------------

    def decline_tribe(self, player_name: str) -> dict:
        """Send the player's active tribe into decline and found the next.

        The rulebook's exact order (p. 7): remove all the player's roads (and the
        Longest Trade Route with them, which `update_longest_road` reassigns);
        then, from the second decline on, clear away any thicket-covered pieces
        left from the tribe two eras back (p. 7, "remove any settlements/city
        belonging to your 1st tribe that remain"); then cover this tribe's own
        settlements and cities with thickets. The tribe counter advances and the
        player owes a free founding settlement (`founding_player`).
        """
        player = self.get_player(player_name)
        declining_tribe = player.tribe

        # Roads: remove every one of this player's roads from the board and hand
        # them back (p. 7). Return to supply is just dropping them from the
        # player's list, which is what the piece limit counts against.
        removed_roads = list(player.roads)
        for edge_key in removed_roads:
            edge = self.edges.get(edge_key)
            if edge is not None and edge.road is not None \
                    and edge.road.get('player') == player_name:
                edge.road = None
        player.roads = [e for e in player.roads if e not in removed_roads]

        # Clear the ruins of the tribe two eras back before covering this one
        # (p. 7). Return each old piece and its thicket to the supply.
        cleared = self._clear_old_ruins(player_name, declining_tribe)

        # Cover this tribe's settlements and cities with thickets: they stay on
        # the board and keep producing, but are marked declining.
        covered = 0
        for vertex in self.vertices.values():
            building = vertex.building
            if building is None or building.get('player') != player_name:
                continue
            if building.get('tribe') != declining_tribe:
                continue
            building['ruined'] = True
            covered += 1

        player.tribe = declining_tribe + 1
        self.founding_player = player_name

        # The Longest Trade Route follows the roads that are now gone (p. 7); the
        # base recompute reassigns it to whoever now holds the longest route.
        self.update_longest_road()

        return {
            'player': player_name,
            'declined_tribe': declining_tribe,
            'new_tribe': player.tribe,
            'roads_removed': len(removed_roads),
            'buildings_covered': covered,
            'old_ruins_cleared': cleared,
        }

    def _clear_old_ruins(self, player_name: str, declining_tribe: int) -> int:
        """Remove this player's ruins from tribes before the one now declining.

        Only bites from the second decline on (a first-tribe decline has no
        earlier ruins). Each cleared piece is dropped from the board and from the
        owner's settlement/city list so its piece returns to supply.
        """
        player = self.get_player(player_name)
        cleared = 0
        for vertex_key, vertex in self.vertices.items():
            building = vertex.building
            if building is None or building.get('player') != player_name:
                continue
            if building.get('tribe', declining_tribe) >= declining_tribe:
                continue
            vertex.building = None
            if vertex_key in player.settlements:
                player.settlements.remove(vertex_key)
            if vertex_key in player.cities:
                player.cities.remove(vertex_key)
            cleared += 1
        return cleared

    # --- Founding the next tribe -------------------------------------------

    def place_founding_settlement(self, player_name: str, vertex_key: str) -> dict:
        """Place the free founding settlement that starts a new tribe (p. 8).

        Free (no road, no starting cards), placed on any unoccupied intersection
        that respects the distance rule against both active and declining
        buildings, is not itself a thicket-covered ruin, and is not a settlement
        site of an active tribe — an intersection beside a road, which since every
        road on the board belongs to an active tribe is exactly "beside any road"
        (p. 8, condition B). The founding settlement is tagged the new tribe and
        adds its culture marker. Refusals mirror the base placement's codes.
        """
        from game.results import refused

        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return refused('INVALID_TARGET', 'Invalid vertex')
        if vertex.building is not None:
            return refused('OCCUPIED', 'A founding settlement cannot go on an existing building')
        if not vertex.neighbors['hexes']:
            return refused('INVALID_PLACEMENT', 'A settlement must stand on the coast or inland')
        if not self._respects_distance_rule(vertex_key):
            return refused('INVALID_PLACEMENT',
                           'Founding settlement must keep its distance from other buildings')
        if self._beside_any_road(vertex_key):
            return refused('INVALID_PLACEMENT',
                           "A founding settlement cannot go on an active tribe's road network")

        player = self.get_player(player_name)
        vertex.building = {'type': 'settlement', 'player': player_name, 'tribe': player.tribe}
        player.settlements.append(vertex_key)
        player.culture_points += 1
        self.track_settlement(player_name, vertex_key)
        self.update_harbormaster()

        # The founding is complete; the player no longer owes one. The turn ends
        # here per the rulebook (p. 8) — the table passes the dice on.
        self.founding_player = None
        return {'success': True, 'error': '', 'building_type': 'settlement', 'founding': True}

    def _beside_any_road(self, vertex_key: str) -> bool:
        """Whether any player's road touches this intersection.

        Every road on the board belongs to an active tribe (a declining tribe's
        roads were removed), so this is the rulebook's "settlement site of an
        active tribe" test for a founding placement (p. 8, condition B).
        """
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return False
        for edge_key in vertex.neighbors.get('edges', []):
            edge = self.edges.get(edge_key)
            if edge is not None and edge.road is not None:
                return True
        return False

    # --- Lockdown of a declining network -----------------------------------

    def road_only_from_ruin(self, player_name: str, edge_key: str) -> bool:
        """Whether this road would extend only from a declining building.

        A declining tribe may not expand (rulebook p. 7, "No further
        Expansion"), and a road may be built up to but not past a thicket-covered
        settlement. The base `_road_connects` treats any of the player's own
        buildings as an anchor; this catches the case where the *only* anchor is
        a ruin — an active road or an active building next to the edge makes it a
        legal extension of the live network instead.
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return False
        anchored_on_ruin = False
        for vertex_key in edge.neighbors.get('vertices', []):
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            building = vertex.building
            if building is not None and building.get('player') == player_name:
                if building.get('ruined'):
                    anchored_on_ruin = True
                else:
                    return False  # an active building here: a legal live anchor
            for connected_key in vertex.neighbors.get('edges', []):
                if connected_key == edge_key:
                    continue
                connected = self.edges.get(connected_key)
                if connected is not None and connected.road is not None \
                        and connected.road.get('player') == player_name:
                    return False  # a live road here: a legal extension
        return anchored_on_ruin

    def tribe_has_city(self, player_name: str, tribe_number: int) -> bool:
        """Whether the player already has a city in this tribe.

        The rulebook allows only one city per tribe (p. 6, "A player may only
        build 1 city for each tribe"). Read live off the board.
        """
        for vertex in self.vertices.values():
            building = vertex.building
            if building is None or building.get('player') != player_name:
                continue
            if building.get('type') == 'city' and building.get('tribe') == tribe_number:
                return True
        return False

    # --- Overbuilding a ruin ------------------------------------------------

    def overbuild_ruin(self, player_name: str, vertex_key: str) -> dict:
        """Replace a declining building with the active player's settlement (p. 7).

        The active tribe builds a road up to the ruin, pays a settlement's cost,
        and removes the thicket-covered piece — returning the old settlement/city
        and its thicket to its owner's supply — then stands its own settlement
        there. Gated by the caller on `overbuild_ruins`; this assumes the vertex
        already carries a ruin.
        """
        from game.results import refused

        vertex = self.vertices.get(vertex_key)
        old = vertex.building
        old_owner_name = old.get('player')
        if old_owner_name == player_name:
            # The rulebook lets a player overbuild their own ruin too, but there
            # is never a reason to and it would let a declined tribe re-expand by
            # the back door; refuse it rather than silently allow it.
            return refused('INVALID_TARGET', 'Overbuild an opponent\'s ruin, not your own')
        if not self._touches_own_route(player_name, vertex_key):
            return refused('INVALID_PLACEMENT',
                           'You must have a road reaching the ruin to build over it')
        if not self.can_afford(player_name, 'settlement'):
            return refused('INSUFFICIENT_RESOURCES', self._cost_message('settlement'))
        self.deduct_cost(player_name, 'settlement')

        # Return the old piece and its thicket to its owner's supply.
        old_owner = self.get_player(old_owner_name)
        if old_owner is not None:
            if vertex_key in old_owner.settlements:
                old_owner.settlements.remove(vertex_key)
            if vertex_key in old_owner.cities:
                old_owner.cities.remove(vertex_key)

        player = self.get_player(player_name)
        vertex.building = {'type': 'settlement', 'player': player_name, 'tribe': player.tribe}
        player.settlements.append(vertex_key)
        player.culture_points += 1
        self.track_settlement(player_name, vertex_key)
        self.update_harbormaster()
        self.update_longest_road()
        return {
            'success': True, 'error': '', 'building_type': 'settlement',
            'overbuilt': True, 'former_owner': old_owner_name,
        }

    # --- The end -----------------------------------------------------------

    def inka_victory(self, player_name: str) -> bool:
        """Whether this player has brought their third tribe to its apex (p. 8).

        The whole win condition when `third_tribe_victory` is on: the plain point
        threshold is gated out, and the race is won by the first player to reach
        the third tribe's cultural goal.
        """
        player = self.get_player(player_name)
        if player is None or player.tribe != FINAL_TRIBE:
            return False
        return self.tribe_culture_points(player_name, FINAL_TRIBE) >= TRIBE_GOALS[FINAL_TRIBE]

    # --- Client ------------------------------------------------------------

    def inkas_client_state(self) -> dict | None:
        """Per-player tribe, culture markers and who owes a founding settlement.

        None off the scenario, so nothing changes for a base table. The client
        reads it for the Inkas panel and the founding affordance; the thicket
        markers themselves ride on each vertex's `building.ruined` flag.
        """
        if not self.rules['tribe_decline']:
            return None
        return {
            'goals': {str(tribe): goal for tribe, goal in TRIBE_GOALS.items()},
            'founding_player': self.founding_player,
            'players': {
                player.name: {
                    'tribe': player.tribe,
                    'culture_points': player.culture_points,
                    'active_tribe_culture': self.active_tribe_culture(player.name),
                }
                for player in self.players
            },
        }
