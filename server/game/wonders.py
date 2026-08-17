"""The Wonders of Catan: one Wonder per player, built four levels at a race.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 8 "The Wonders of Catan"
(pp. 26-29, wonder cards on p. 27). Each player may build one Wonder chosen from
five. A Wonder can only be *started* once its printed requirement is met, and
once a player starts one no other player may build the same Wonder. Every Wonder
has four levels; each level costs the resources printed on its card. You win by
finishing your Wonder (the fourth level), or — the alternate end — by holding ten
victory points with a strictly higher wonder level than every other player. A
settlement on one of the small islands is worth a special victory point.

One mixin on `Game`, the pattern the other scenario modules use. Every method is
gated on the individual rule that governs it — `wonders` for the whole
subsystem, `wonder_island_points` for the small-island bonus — so a table not
running the scenario is untouched and the base game is unchanged. Engine code
reads these rules directly; nothing branches on the scenario's name.

The five wonders, their per-level cost and the requirement to start, read off the
official wonder cards (p. 27):

- Cathedral    — 3 ore, 1 grain, 1 brick   — a city and at least 6 victory points
- Great Bridge — 1 wool, 1 grain, 3 lumber — a settlement at the strait (a purple
                                             marker on the board)
- Great Wall   — 1 grain, 3 brick, 1 lumber — settlements at the wasteland (the
                                             brown markers on the board)
- Monument     — 2 ore, 3 grain            — a city on a harbour and a trade route
                                             of at least 5 roads or ships
- Theater      — 3 wool, 1 brick, 1 lumber — two cities

The card art writes each cost as a stack of five resource icons; "Each level
costs the 5 resources indicated" (p. 26), so every one of the costs above totals
five cards.
"""

from game.results import refused

# The four levels a Wonder is built up through (Seafarers 2021, p. 26: "Each
# wonder is subdivided into four levels").
WONDER_LEVELS = 4

# The wasteland (Great Wall) requirement reads "Settlements" — plural — so it is
# met by building on at least two of the brown markers. The rulebook shows five
# brown markers on the board and does not name an exact count for the card, so
# the plainest reading of the plural is taken: two settlements at the wasteland.
GREAT_WALL_WASTELAND_SETTLEMENTS = 2

# The Monument's trade-route requirement (p. 27): "a trade route with at least 5
# consecutive, unbranched roads or ships."
MONUMENT_ROUTE_LENGTH = 5

# The Cathedral's victory-point requirement (p. 27): "1 city and at least 6
# victory points."
CATHEDRAL_VICTORY_POINTS = 6


# The five wonders. `cost` is the per-level price in resource cards (the box's
# five resources are wood/brick/sheep/wheat/ore in this engine); `requirement` is
# the human summary the client shows; the gate itself is code below, so the two
# never drift into disagreement.
WONDERS = {
    "cathedral": {
        "name": "Cathedral",
        "cost": {"ore": 3, "wheat": 1, "brick": 1},
        "requirement": "A city and at least 6 victory points",
    },
    "great_bridge": {
        "name": "Great Bridge",
        "cost": {"sheep": 1, "wheat": 1, "wood": 3},
        "requirement": "A settlement at the strait (a purple marker)",
    },
    "great_wall": {
        "name": "Great Wall",
        "cost": {"wheat": 1, "brick": 3, "wood": 1},
        "requirement": "Two settlements at the wasteland (brown markers)",
    },
    "monument": {
        "name": "Monument",
        "cost": {"ore": 2, "wheat": 3},
        "requirement": "A city on a harbour and a trade route of 5 roads or ships",
    },
    "theater": {
        "name": "Theater",
        "cost": {"sheep": 3, "brick": 1, "wood": 1},
        "requirement": "Two cities",
    },
}


class WonderRules:
    """Choosing a Wonder, building its levels, and the two ways it ends a game."""

    # --- Board setup -------------------------------------------------------

    def setup_wonders_board(self):
        """Read the map's marked intersections into the strait and wasteland sets.

        A no-op for a map that prints no markers, so every other board is
        unaffected. Derived from the map the way the cloth villages are, so the
        markers a Great Bridge and a Great Wall are built against are real
        intersections on the dealt board.
        """
        definition = self.map_definition
        if definition is None or not getattr(definition, "wonder_markers", ()):
            return
        for vertex_key, kind in definition.wonder_markers:
            if vertex_key not in self.vertices:
                continue
            if kind == "strait":
                self.wonder_strait.add(vertex_key)
            elif kind == "wasteland":
                self.wonder_wasteland.add(vertex_key)

    def is_wonder_marker(self, vertex_key: str) -> bool:
        """Whether this intersection is a marked strait or wasteland square.

        The colored squares (and the red exclamation points) may not carry a
        *starting* settlement (p. 26); read by the setup placement guard.
        """
        return vertex_key in self.wonder_strait or vertex_key in self.wonder_wasteland

    # --- Requirements ------------------------------------------------------

    def _player_has_building_at(self, player_name: str, vertex_keys) -> int:
        """How many of these intersections carry this player's own building."""
        count = 0
        for vertex_key in vertex_keys:
            vertex = self.vertices.get(vertex_key)
            if vertex and vertex.building and vertex.building.get("player") == player_name:
                count += 1
        return count

    def _player_has_city_on_harbour(self, player_name: str) -> bool:
        """Whether this player holds a city on a harbour intersection."""
        player = self.get_player(player_name)
        if player is None:
            return False
        for vertex_key in player.cities:
            vertex = self.vertices.get(vertex_key)
            if vertex is not None and vertex.port is not None:
                return True
        return False

    def wonder_requirement_met(self, player_name: str, wonder_id: str) -> bool:
        """Whether this player has met the printed requirement to start a Wonder.

        Checked only when a Wonder is started (its first level); once building
        has begun, later levels cost only resources (p. 26). Reads live game
        state — cities, victory points, marked settlements, the harbour and the
        trade-route length — so a requirement is the truth about the board.
        """
        player = self.get_player(player_name)
        if player is None:
            return False

        if wonder_id == "cathedral":
            return (len(player.cities) >= 1
                    and self.victory_points_for(player_name) >= CATHEDRAL_VICTORY_POINTS)
        if wonder_id == "theater":
            return len(player.cities) >= 2
        if wonder_id == "great_bridge":
            return self._player_has_building_at(player_name, self.wonder_strait) >= 1
        if wonder_id == "great_wall":
            return (self._player_has_building_at(player_name, self.wonder_wasteland)
                    >= GREAT_WALL_WASTELAND_SETTLEMENTS)
        if wonder_id == "monument":
            return (self._player_has_city_on_harbour(player_name)
                    and self.calculate_longest_road(player_name) >= MONUMENT_ROUTE_LENGTH)
        return False

    # --- Paying a level ----------------------------------------------------

    def _can_pay_wonder_cost(self, player_name: str, cost: dict) -> bool:
        player = self.get_player(player_name)
        if player is None:
            return False
        return all(player.resources.get(resource, 0) >= amount
                   for resource, amount in cost.items())

    def _pay_wonder_cost(self, player_name: str, cost: dict):
        """Hand a level's resources back to the bank. Assumes the player can pay."""
        player = self.get_player(player_name)
        for resource, amount in cost.items():
            player.resources[resource] -= amount
            self.bank.return_resources(resource, amount)

    # --- The build action --------------------------------------------------

    def wonder_level_of(self, player_name: str) -> int:
        """How many levels of their Wonder this player has finished (0-4)."""
        return self.wonder_level.get(player_name, 0)

    def finished_wonder(self, player_name: str) -> bool:
        """Whether this player has finished their Wonder to the fourth level."""
        return self.wonder_level_of(player_name) >= WONDER_LEVELS

    def build_wonder_level(self, player_name: str, wonder_id: str = None) -> dict:
        """Start or advance this player's Wonder by one level.

        On the first level `wonder_id` names the Wonder to start; it is refused
        unless the player has met its requirement, nobody else has taken it, and
        the player has not already started a different one. On later levels the
        Wonder is the one already started and `wonder_id`, if given, must match
        it. Every level charges its cost from the hand and returns it to the
        bank, exactly as `upgrade_city` does. Refused with a clear reason when
        the requirement, the cost, or the one-Wonder-per-player rule is not met.
        """
        if not self.rules["wonders"]:
            return refused("WONDERS_OFF", "This table is not playing the Wonders scenario")
        if self.must_move_robber:
            return refused("MUST_MOVE_ROBBER", "You must move the robber first")
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked
        moved = self.movement_phase_block()
        if moved is not None:
            return moved
        voting = self.camel_vote_block(player_name)
        if voting is not None:
            return voting
        if self.game_phase == "setup":
            return refused("WRONG_PHASE", "Cannot build a Wonder during setup phase")

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused("NOT_YOUR_TURN", f"Only {current_name} can build a Wonder")

        started = player_name in self.wonder_choice
        if started:
            existing = self.wonder_choice[player_name]
            if wonder_id is not None and wonder_id != existing:
                return refused("WONDER_CHOSEN",
                               f"You are already building the {WONDERS[existing]['name']}")
            wonder_id = existing
        else:
            if wonder_id not in WONDERS:
                return refused("INVALID_TARGET", "Choose one of the five wonders")
            if wonder_id in set(self.wonder_choice.values()):
                return refused("WONDER_TAKEN",
                               f"Another player is already building the "
                               f"{WONDERS[wonder_id]['name']}")
            if not self.wonder_requirement_met(player_name, wonder_id):
                return refused("WONDER_REQUIREMENT",
                               f"Not yet: {WONDERS[wonder_id]['requirement']}")

        if self.finished_wonder(player_name):
            return refused("WONDER_COMPLETE", "Your Wonder is already finished")

        cost = WONDERS[wonder_id]["cost"]
        if not self._can_pay_wonder_cost(player_name, cost):
            need = ", ".join(f"{amount} {resource}" for resource, amount in cost.items())
            return refused("INSUFFICIENT_RESOURCES", f"Not enough resources. Need: {need}")

        self._pay_wonder_cost(player_name, cost)
        if not started:
            self.wonder_choice[player_name] = wonder_id
            self.wonder_level[player_name] = 1
        else:
            self.wonder_level[player_name] += 1

        return {
            "success": True,
            "error": "",
            "wonder": wonder_id,
            "level": self.wonder_level[player_name],
            "finished": self.finished_wonder(player_name),
        }

    # --- Scoring and victory ----------------------------------------------

    def _on_small_island(self, vertex) -> bool:
        """Whether this intersection sits on a small island rather than the main
        land — a land hex the map does not call the main land."""
        for hex_key in vertex.neighbors.get("hexes", []):
            hex_obj = self.hexes.get(hex_key)
            if hex_obj is None or hex_obj.type == "ocean":
                continue
            if not self.is_main_land(hex_key):
                return True
        return False

    def wonder_island_victory_points(self, player_name: str) -> int:
        """A player's special points for settling the small islands.

        "If you build a settlement on one of the smaller islands, then you
        receive a special victory point ... It does not matter if other players
        have already built settlements on that island" (p. 27) — so it is a point
        for *each* of this player's buildings on a small island, not the first on
        a new one. A no-op without the rule. Read live off the board, so a point
        lands the moment a small-island settlement does.
        """
        if not self.rules["wonder_island_points"]:
            return 0
        player = self.get_player(player_name)
        if player is None:
            return 0
        total = 0
        for vertex_key in list(player.settlements) + list(player.cities):
            vertex = self.vertices.get(vertex_key)
            if vertex is not None and self._on_small_island(vertex):
                total += 1
        return total

    def wonder_victory(self, player_name: str, points: int, target: int) -> bool:
        """Whether this player has won under the Wonders scenario's two ends.

        You win if you finish your Wonder (the fourth level), or if you hold the
        table's target (10) in victory points and stand at a strictly higher
        wonder level than every other player (p. 28). A player who has not
        started a Wonder is at level 0, so "strictly higher" is real: reaching
        ten points is not enough on its own.
        """
        if self.finished_wonder(player_name):
            return True
        if points < target:
            return False
        my_level = self.wonder_level_of(player_name)
        return all(my_level > self.wonder_level_of(other.name)
                   for other in self.players if other.name != player_name)

    # --- Client state ------------------------------------------------------

    def wonders_client_state(self) -> dict:
        """Everything the Wonders panel renders, or None off the scenario.

        The catalogue (each Wonder's name, per-level cost and requirement), the
        number of levels, which Wonders are already taken, each player's chosen
        Wonder and level, and the marked intersections — enough for a client to
        show progress and offer a build without a second copy of any of it.
        """
        if not self.rules["wonders"]:
            return None
        return {
            "levels": WONDER_LEVELS,
            "catalogue": [
                {
                    "id": wonder_id,
                    "name": spec["name"],
                    "cost": spec["cost"],
                    "requirement": spec["requirement"],
                }
                for wonder_id, spec in WONDERS.items()
            ],
            "taken": sorted(set(self.wonder_choice.values())),
            "players": {
                player.name: {
                    "wonder": self.wonder_choice.get(player.name),
                    "level": self.wonder_level_of(player.name),
                }
                for player in self.players
            },
            "strait": sorted(self.wonder_strait),
            "wasteland": sorted(self.wonder_wasteland),
        }
