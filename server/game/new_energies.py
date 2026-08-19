"""CATAN: New Energies — power plants, the science economy, and energy.

The 2024 game by Klaus & Benjamin Teuber (CN3207 New Energies rules 240409,
the 3-4 player rules). One mixin on `Game`, the pattern the other scenario
modules use (see `oil_springs.py`, `cloth_for_catan.py`). Every method is gated
on the individual rule that governs it — never on the game's name — so a table
not playing New Energies is untouched.

The scenario is decomposed into individual switchable rules the way Cities &
Knights and Seafarers are. This module carries the first of them:

- `power_plants` — a city produces a `science` commodity as well as its
  resource (the production modifier in `modifiers.py`), and players build fossil
  and renewable power plants on the land hexes beside their towns and cities.
  A plant produces 1 energy when its hex produces, and energy is spent on the
  actions below. Fossil plants cost 1 science, renewable plants 3.

Science is a commodity (`validation.COMMODITY_TYPES`): a card held in hand,
counted toward the discard limit on a 7, and tradeable, exactly as the rulebook
describes it, differing from a resource only in type. Energy lives on
`Player.energy`, the way oil lives on `Player.oil`: a public currency, not a
card, capped at 5 and never discarded or stolen.

The global footprint track, the event-disc bag and the dual end condition are
the later rules of the scenario and land in their own chunks; this module is
science, the two plant types, and energy.
"""

from game.results import refused

# Per-player plant supplies (New Energies rulebook, 'Components'): 6 fossil fuel
# power plants and 9 renewable power plants each.
FOSSIL_PLANT_SUPPLY = 6
RENEWABLE_PLANT_SUPPLY = 9

# What a plant costs in science (New Energies rulebook, 'Build/buy': fossil fuel
# power plants cost 1 science, renewable power plants 3).
PLANT_SCIENCE_COST = {'fossil': 1, 'renewable': 3}

# A town may carry one power plant; a city up to three, each facing a different
# hex (rulebook, 'Power plants', p. 14).
PLANTS_PER_TOWN = 1
PLANTS_PER_CITY = 3

# "You may never have more than 5 energy. If you receive more than 5, ignore the
# extra energy." (rulebook, 'Production Phase', p. 11.)
MAX_ENERGY = 5

# "Return 2 energy to the supply to take 1 resource or science card of your
# choice." (rulebook, 'Energy uses', p. 15.)
ENERGY_PER_CARD = 2

# Demolishing a fossil fuel power plant costs 1 energy (rulebook, 'Demolish a
# fossil fuel power plant', p. 15), and only one may be demolished a turn.
ENERGY_PER_DEMOLISH = 1

# The local-footprint weight of each piece (rulebook, 'Local environmental
# footprint' p. 12 and the plant pages p. 15): a town +1, a city +2, a fossil
# plant +1, a renewable plant -1.
LF_PER_TOWN = 1
LF_PER_CITY = 2
LF_PER_FOSSIL = 1
LF_PER_RENEWABLE = -1

# The global-footprint track runs from 0 to 7 per player — 0 to 28 for four
# players, 0 to 21 for three (rulebook p. 13: the marker "remains there until the
# total LF ... drops below 28 for 4 players (21 for 3 players)"). The marker
# starts at 3 per player, which is where each seat's opening town and city put
# it. Both scale with the seat count, which is how a 3- and a 4-player game read
# off one track, so they are derived rather than two literals.
GF_MAX_PER_PLAYER = 7
GF_START_PER_PLAYER = 3

# The brown event discs the bag starts with (rulebook, 'Components' p. 2 and
# 'Event details' p. 10): 43 in all. Fixed whatever the player count.
BROWN_DISCS = {
    'climate_conference': 9,
    'environmental_pollution': 8,
    'air_pollution': 9,
    'production_increase': 9,
    'rain_and_flooding': 8,
}

# The green event discs — 9 per player, dealt face-down under the renewable-plant
# spaces and added to the bag as those plants are built (rulebook, 'Preparing
# your player board' p. 8). The 4-player game uses 36 (4 climate / 16
# sustainable / 16 government), the 3-player game 27 (3/12/12) — nine per player
# each way, which the per-player weights below reproduce for any seat count.
GREEN_DISCS_PER_PLAYER = {
    'climate_conference': 1,
    'sustainable_production': 4,
    'government_funding': 4,
}


class NewEnergiesRules:
    """Power plants, the science economy, and energy. The global footprint
    track, the event discs and the dual end condition are folded in by the
    later chunks of this mixin."""

    # --- Power plants ------------------------------------------------------

    def _plant_building(self, vertex_key: str):
        """The town or city standing at `vertex_key`, or None.

        A power plant is built in a cutout of a town or city and produces for
        its owner, so a plant is only ever valid beside one of their buildings.
        """
        vertex = self.vertices.get(vertex_key)
        if vertex is None or not vertex.building:
            return None
        return vertex.building

    def _plants_on_building(self, vertex_key: str) -> int:
        """How many power plants already sit in this building's cutouts."""
        return sum(1 for (vk, _hk) in self.power_plants if vk == vertex_key)

    def _plant_counts(self, player_name: str) -> dict:
        """This player's built plants by kind — {'fossil': n, 'renewable': m}."""
        counts = {'fossil': 0, 'renewable': 0}
        for plant in self.power_plants.values():
            if plant['player'] == player_name:
                counts[plant['kind']] += 1
        return counts

    def build_power_plant(self, player_name: str, vertex_key: str,
                          hex_key: str, kind: str, free: bool = False) -> dict:
        """Build a fossil or renewable power plant beside one of your buildings.

        A plant is placed on a numbered land hex adjacent to one of your towns
        or cities (rulebook, 'Power plants', p. 14): a town may host one, a city
        up to three, each facing a different hex. Only one plant may be built a
        turn — the `free` flag lets a triggered event (chunk 3) build one on top
        of that, as the rulebook's exception allows. Fossil plants cost 1
        science and renewable plants 3; the science is returned to the supply.

        The footprint the plant moves is the global-footprint chunk's; this
        places the piece and charges the science.
        """
        if not self.rules['power_plants']:
            return refused('RULE_OFF', 'Power plants are not in play')
        if kind not in PLANT_SCIENCE_COST:
            return refused('INVALID_PLANT', 'Choose a fossil or a renewable plant')

        block = self._new_energies_action_block(player_name)
        if block is not None:
            return block

        if not free and self.power_plant_built_this_turn:
            return refused('PLANT_ALREADY_BUILT',
                           'You may build only one power plant per turn')

        building = self._plant_building(vertex_key)
        if building is None or building.get('player') != player_name:
            return refused('INVALID_TARGET', 'Build a power plant beside your own building')

        vertex = self.vertices[vertex_key]
        if hex_key not in vertex.neighbors.get('hexes', []):
            return refused('INVALID_PLACEMENT', 'That hex does not touch this building')
        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None or hex_obj.number is None or hex_obj.type in ('ocean', 'desert'):
            return refused('INVALID_PLACEMENT',
                           'A power plant must stand on a land hex with a number')
        if (vertex_key, hex_key) in self.power_plants:
            return refused('OCCUPIED', 'A power plant already faces this hex here')

        limit = PLANTS_PER_CITY if building.get('type') == 'city' else PLANTS_PER_TOWN
        if self._plants_on_building(vertex_key) >= limit:
            return refused('NO_CUTOUT_LEFT',
                           f'This building already carries {limit} power plant(s)')

        counts = self._plant_counts(player_name)
        supply = FOSSIL_PLANT_SUPPLY if kind == 'fossil' else RENEWABLE_PLANT_SUPPLY
        if counts[kind] >= supply:
            return refused('NO_PLANTS_LEFT', f'You have built all your {kind} power plants')

        player = self.get_player(player_name)
        cost = PLANT_SCIENCE_COST[kind]
        if player.commodities.get('science', 0) < cost:
            return refused('INSUFFICIENT_RESOURCES', f'A {kind} power plant costs {cost} science')

        player.commodities['science'] = player.commodities.get('science', 0) - cost
        self.power_plants[(vertex_key, hex_key)] = {'player': player_name, 'kind': kind}
        if not free:
            self.power_plant_built_this_turn = True
        # Building a renewable reveals the green disc under its space and adds it
        # to the bag, so a table that invests in renewables gives the game more
        # turns (rulebook, 'Renewable power plants', p. 15). A no-op off events.
        if kind == 'renewable':
            self.add_green_disc_to_bag(player_name)

        return {'success': True, 'error': '', 'kind': kind,
                'vertex': vertex_key, 'hex': hex_key, 'science': player.commodities['science']}

    def _new_energies_action_block(self, player_name: str):
        """Shared turn checks for a during-your-turn New Energies action, or None."""
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'You cannot do that during setup')
        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} may act now')
        if self.get_player(player_name) is None:
            return refused('NO_SUCH_PLAYER', 'No such player')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        return None

    # --- The global footprint track ---------------------------------------

    def local_footprint(self, player_name: str) -> int:
        """One player's local footprint (LF) — the pollution they contribute.

        A town adds 1, a city 2, a fossil plant 1, a renewable plant subtracts 1
        (rulebook, 'Local environmental footprint', p. 12). Read live off the
        board and this player's plants, so it moves the instant a piece is built
        or demolished. Zero off the scenario, since a base game builds none of
        the plants and the caller gates on the rule.
        """
        player = self.get_player(player_name)
        if player is None:
            return 0
        counts = self._plant_counts(player_name)
        return (
            len(player.settlements) * LF_PER_TOWN
            + len(player.cities) * LF_PER_CITY
            + counts['fossil'] * LF_PER_FOSSIL
            + counts['renewable'] * LF_PER_RENEWABLE
        )

    def global_footprint_level(self) -> int:
        """The shared global footprint (GF): the table's local footprints summed.

        "Add the LF of all players together and track it on the global footprint
        track" (rulebook, p. 13). Derived from the live pieces rather than a
        running marker, which is exactly how the rulebook says to check it — "add
        up the visible + and - icons on all player boards" — and clamped to the
        track's ends (0 to 7 per player), where the physical marker also stops.
        """
        total = sum(self.local_footprint(player.name) for player in self.players)
        return max(0, min(total, GF_MAX_PER_PLAYER * len(self.players)))

    def demolish_fossil_plant(self, player_name: str, vertex_key: str,
                              hex_key: str) -> dict:
        """Demolish one of your fossil plants for 1 energy, lowering the footprint.

        "Once during your Action phase, you may demolish 1 fossil fuel power
        plant that you have already built. Pay 1 energy and return 1 fossil fuel
        power plant to your player board. Your LF decreases by one." (rulebook,
        p. 15.) The footprint is derived from the pieces, so removing the plant
        moves the global marker back on its own.
        """
        if not self.rules['global_footprint']:
            return refused('RULE_OFF', 'The footprint track is not in play')

        block = self._new_energies_action_block(player_name)
        if block is not None:
            return block

        if self.fossil_demolished_this_turn:
            return refused('ALREADY_DEMOLISHED',
                           'You may demolish only one fossil plant per turn')

        plant = self.power_plants.get((vertex_key, hex_key))
        if plant is None or plant['player'] != player_name or plant['kind'] != 'fossil':
            return refused('INVALID_TARGET', 'Choose one of your own fossil plants')

        player = self.get_player(player_name)
        if player.energy < ENERGY_PER_DEMOLISH:
            return refused('NOT_ENOUGH_ENERGY',
                           f'Demolishing costs {ENERGY_PER_DEMOLISH} energy')

        player.energy -= ENERGY_PER_DEMOLISH
        del self.power_plants[(vertex_key, hex_key)]
        self.fossil_demolished_this_turn = True
        return {'success': True, 'error': '', 'vertex': vertex_key, 'hex': hex_key,
                'energy': player.energy, 'global_footprint': self.global_footprint_level()}

    # --- The event-disc bag ------------------------------------------------

    def setup_event_discs(self):
        """Fill the bag with the 43 brown discs and deal each player their green.

        The brown discs go in the bag; the green discs sit face-down under a
        player's renewable-plant spaces (9 each) and enter the bag one at a time
        as those plants are built (rulebook, 'Preparing your player board' p. 8
        and 'Renewable power plants' p. 15). A no-op off the `event_discs` rule,
        so a table not drawing discs is untouched. Deterministic through the
        game's own generator.
        """
        if not self.rules['event_discs']:
            return
        bag = []
        for disc_type, count in BROWN_DISCS.items():
            bag.extend([disc_type] * count)
        self.rng.shuffle(bag)
        self.event_bag = bag

        for player in self.players:
            stack = []
            for disc_type, count in GREEN_DISCS_PER_PLAYER.items():
                stack.extend([disc_type] * count)
            self.rng.shuffle(stack)
            self.green_discs[player.name] = stack

    def add_green_disc_to_bag(self, player_name: str):
        """Reveal the green disc under a built renewable plant and bag it (p. 15).

        Called when a renewable plant is built. The disc's type was decided when
        the stacks were dealt, so which green event a renewable feeds is fixed at
        setup, not at build time. A no-op off the rule or when the stack is spent.
        """
        if not self.rules['event_discs']:
            return
        stack = self.green_discs.get(player_name)
        if stack:
            self.event_bag.append(stack.pop())

    def discs_to_draw(self, gf_level: int) -> int:
        """How many discs the event phase draws at this global-footprint level.

        The count is printed in bands on the physical global-footprint track and
        is NOT transcribed in the official rules text — the rulebook gives only
        two fixed points (the game starts drawing 1, and space 21 draws 2, p. 9)
        and the note that dropping the footprint below 6 draws extra discs
        (mostly green, a reward, p. 15). The bands below are the most defensible
        reading consistent with those anchors, scaled to the track's ends per
        seat count (0-28 for four players, 0-21 for three), and kept in this one
        function so a corrected reading is a one-line change:

        * below 6 (scaled): 2 — the low reward band the note describes;
        * the steady band: 1 — where the 12-/9-space start sits;
        * the elevated band: 2 — where space 21 sits;
        * the top band: 3 — approaching catastrophe.
        """
        players = len(self.players)
        low = round(6 * players / 4)
        elevated = round(15 * players / 4)
        top = round(24 * players / 4)
        if gf_level < low:
            return 2
        if gf_level >= top:
            return 3
        if gf_level >= elevated:
            return 2
        return 1

    def run_event_phase(self, player_name: str) -> dict:
        """Draw and resolve this turn's event discs (rulebook, 'Event Phase' p. 9).

        Draws the footprint-scaled number of discs and resolves each in turn.
        The draw count is fixed at the start of the phase — an event that moves
        the footprint mid-phase does not change how many more are drawn this turn
        (p. 9). If the bag empties while a disc is still owed, the game's second
        end condition fires: `bag_empty` is set, and the caller (chunk 4) scores
        by the fossil/renewable balance. A no-op off the rule and once the phase
        has already run this turn.
        """
        if not self.rules['event_discs'] or self.event_phase_done:
            return {'drawn': [], 'events': [], 'bag_empty': False}
        self.event_phase_done = True

        to_draw = self.discs_to_draw(self.global_footprint_level())
        drawn = []
        events = []
        bag_empty = False
        for _ in range(to_draw):
            if not self.event_bag:
                bag_empty = True
                break
            disc = self.event_bag.pop(self.rng.randrange(len(self.event_bag)))
            drawn.append(disc)
            events.append(self._resolve_event(disc, player_name))
        return {'drawn': drawn, 'events': events, 'bag_empty': bag_empty}

    # --- Event effects -----------------------------------------------------

    def _lf_extreme_players(self, highest: bool) -> list:
        """Players tied at the highest (or lowest) local footprint, or [].

        Ordered from the current player clockwise, which is the order the
        rulebook resolves a tie in (p. 17). Empty when every player ties, since
        "if all players tie, no action is taken" (p. 9).
        """
        lfs = {p.name: self.local_footprint(p.name) for p in self.players}
        target = max(lfs.values()) if highest else min(lfs.values())
        if all(value == target for value in lfs.values()):
            return []
        order = [p.name for p in self.players]
        start = self.current_player_index
        order = order[start:] + order[:start]
        return [name for name in order if lfs[name] == target]

    def _resolve_event(self, disc_type: str, active_player: str) -> dict:
        """Dispatch one drawn disc to its effect (rulebook, pp. 17, 20)."""
        handler = getattr(self, f'_event_{disc_type}', None)
        if handler is None:
            return {'event': disc_type, 'resolved': False}
        return handler(active_player)

    def _event_climate_conference(self, _active_player: str) -> dict:
        """Lowest LF may take a card of choice; highest LF must discard one (p. 17)."""
        takers = self._lf_extreme_players(highest=False)
        discarders = self._lf_extreme_players(highest=True)
        for name in takers:
            self._open_take_card(name)
        for name in discarders:
            self._open_discard_card(name)
        return {'event': 'climate_conference', 'resolved': True,
                'takers': takers, 'discarders': discarders}

    def _event_sustainable_production(self, _active_player: str) -> dict:
        """The players with the most renewable plants take a card of choice (p. 17)."""
        counts = {p.name: self._plant_counts(p.name)['renewable'] for p in self.players}
        most = max(counts.values())
        # Nobody has built one, or everybody ties: no action (p. 9).
        winners = [] if most == 0 or all(v == most for v in counts.values()) else [
            name for name in self._clockwise_names() if counts[name] == most
        ]
        for name in winners:
            self._open_take_card(name)
        return {'event': 'sustainable_production', 'resolved': True, 'takers': winners}

    def _event_government_funding(self, _active_player: str) -> dict:
        """The lowest-LF players each take 1 development card from the deck (p. 17)."""
        takers = self._lf_extreme_players(highest=False)
        granted = []
        for name in takers:
            card = self.bank.draw_dev_card()
            if card is None:
                break
            player = self.get_player(name)
            player.dev_cards[card]['count'] += 1
            player.dev_cards[card]['purchase_turn'] = self.turn_count
            granted.append(name)
        return {'event': 'government_funding', 'resolved': True, 'takers': granted}

    def _clockwise_names(self) -> list:
        """Player names from the current player clockwise."""
        order = [p.name for p in self.players]
        start = self.current_player_index
        return order[start:] + order[:start]

    def _open_take_card(self, player_name: str):
        """Ask a player which resource or science card to take from the supply."""
        self.open_choice('new_energies_take_card', player_name,
                         self.in_play_card_types())

    def _open_discard_card(self, player_name: str):
        """Ask a player which held card to discard to the supply."""
        player = self.get_player(player_name)
        held = sorted(card for card, count in player.all_cards().items() if count > 0)
        if held:
            self.open_choice('new_energies_discard_card', player_name, held)

    def _choice_new_energies_take_card(self, choice: dict, option: str) -> dict:
        """Grant the card a player chose off a New Energies event."""
        result = self._grant_event_card(choice['player'], option)
        return {'card': option, 'granted': result}

    def _choice_new_energies_discard_card(self, choice: dict, option: str) -> dict:
        """Discard the card a player chose off a New Energies event."""
        player = self.get_player(choice['player'])
        hand = player.hand_for(option)
        if hand.get(option, 0) > 0:
            hand[option] -= 1
            if option not in {'cloth', 'coin', 'paper', 'science'}:
                self.bank.return_resources(option, 1)
        return {'card': option}

    def _grant_event_card(self, player_name: str, card_type: str) -> bool:
        """Give one resource (from the bank) or science card to a player."""
        player = self.get_player(player_name)
        if card_type == 'science':
            player.commodities['science'] = player.commodities.get('science', 0) + 1
            return True
        if card_type in self.in_play_resource_types() and self.bank.take(card_type):
            player.resources[card_type] = player.resources.get(card_type, 0) + 1
            return True
        return False

    # --- Hazards -----------------------------------------------------------

    def clear_blocking_hazards(self, dice_total: int):
        """Remove the hazards this roll blocked with (rulebook, p. 11).

        A hazard is spent the turn it stops production — the hex whose number
        came up, or a building beside such a hex — so it is cleared here, at the
        end of the Production phase. Hazards on hexes and buildings the roll did
        not touch stay. A no-op when nothing is hazarded, which is every board
        off the scenario.
        """
        if not self.hazard_hexes and not self.hazard_buildings:
            return
        for hex_key in list(self.hazard_hexes):
            hex_obj = self.hexes.get(hex_key)
            if hex_obj is not None and hex_obj.number == dice_total:
                self.hazard_hexes.discard(hex_key)
        for vertex_key in list(self.hazard_buildings):
            if any(self.hexes.get(h) and self.hexes[h].number == dice_total
                   for h in self._building_hexes(vertex_key)):
                self.hazard_buildings.discard(vertex_key)

    def _building_hexes(self, vertex_key: str) -> list:
        """The numbered hexes a building touches."""
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return []
        return [h for h in vertex.neighbors.get('hexes', [])
                if self.hexes.get(h) and self.hexes[h].number]

    def _own_buildings(self, player_name: str, of_type=None) -> list:
        """This player's building vertices, optionally filtered to one type,
        sorted for a deterministic auto-pick."""
        found = []
        for vertex_key in sorted(self.vertices):
            building = self.vertices[vertex_key].building
            if not building or building.get('player') != player_name:
                continue
            if of_type is not None and building.get('type') != of_type:
                continue
            found.append(vertex_key)
        return found

    # --- Hazard events -----------------------------------------------------

    def _event_environmental_pollution(self, active_player: str) -> dict:
        """The active player rolls; hazard every hex showing that number (p. 17).

        A 7 is rerolled until a different number comes up. The hex under the
        environmental inspector (the robber piece in this scenario) is spared.
        """
        total = 7
        while total == 7:
            total = self.rng.randint(1, 6) + self.rng.randint(1, 6)
        hazarded = []
        for hex_key in sorted(self.hexes):
            hex_obj = self.hexes[hex_key]
            if hex_obj.number != total or hex_obj.type in ('ocean', 'desert'):
                continue
            if hex_key == self.robber_hex:
                continue
            self.hazard_hexes.add(hex_key)
            hazarded.append(hex_key)
        return {'event': 'environmental_pollution', 'resolved': True,
                'roll': total, 'hexes': hazarded}

    def _event_air_pollution(self, _active_player: str) -> dict:
        """Highest-LF players hazard one of their cities (a town if none) (p. 17)."""
        placed = {}
        for name in self._lf_extreme_players(highest=True):
            cities = [v for v in self._own_buildings(name, 'city')
                      if v not in self.hazard_buildings]
            towns = [v for v in self._own_buildings(name, 'settlement')
                     if v not in self.hazard_buildings]
            target = cities[0] if cities else (towns[0] if towns else None)
            if target is not None:
                self.hazard_buildings.add(target)
                placed[name] = target
        return {'event': 'air_pollution', 'resolved': True, 'hazards': placed}

    def _event_rain_and_flooding(self, _active_player: str) -> dict:
        """Every player hazards one of their towns or cities (p. 17)."""
        placed = {}
        for name in self._clockwise_names():
            buildings = [v for v in self._own_buildings(name)
                         if v not in self.hazard_buildings]
            if buildings:
                self.hazard_buildings.add(buildings[0])
                placed[name] = buildings[0]
        return {'event': 'rain_and_flooding', 'resolved': True, 'hazards': placed}

    def _event_production_increase(self, _active_player: str) -> dict:
        """Highest-LF players build a free fossil plant and take its hex's card (p. 17).

        "The player(s) with the highest LF may build 1 fossil fuel power plant
        for free. If they do, they also take 1 resource card from the hex where
        they placed their power plant (even if that hex currently has a hazard
        token on it). If they do not have a location to build the power plant,
        then nothing happens." Auto-placed at a deterministic legal cutout.
        """
        built = {}
        for name in self._lf_extreme_players(highest=True):
            placement = self._place_free_fossil_plant(name)
            if placement is None:
                continue
            _vertex, hex_key = placement
            resource = self.hexes[hex_key].type
            if self.bank.take(resource):
                player = self.get_player(name)
                player.resources[resource] = player.resources.get(resource, 0) + 1
            built[name] = hex_key
        return {'event': 'production_increase', 'resolved': True, 'plants': built}

    def _place_free_fossil_plant(self, player_name: str):
        """Place a free fossil plant at the first legal cutout, or None.

        A legal cutout is a numbered land hex beside one of the player's towns or
        cities, not already carrying that player's plant, within the building's
        plant limit and the fossil supply. Deterministic (sorted), so a seeded
        game replays identically.
        """
        if self._plant_counts(player_name)['fossil'] >= FOSSIL_PLANT_SUPPLY:
            return None
        for vertex_key in self._own_buildings(player_name):
            building = self.vertices[vertex_key].building
            limit = PLANTS_PER_CITY if building.get('type') == 'city' else PLANTS_PER_TOWN
            if self._plants_on_building(vertex_key) >= limit:
                continue
            for hex_key in sorted(self._building_hexes(vertex_key)):
                if (vertex_key, hex_key) in self.power_plants:
                    continue
                self.power_plants[(vertex_key, hex_key)] = {
                    'player': player_name, 'kind': 'fossil'}
                return vertex_key, hex_key
        return None

    # --- Energy production -------------------------------------------------

    def distribute_energy(self, dice_total: int) -> dict:
        """Produce energy for every power plant whose hex came up (p. 11).

        "Power plants produce 1 energy if they are on a hex that produces (i.e.,
        no hazard) and if the building the power plant is attached to receives
        resources." The building receives resources exactly when its hex
        produces, so a plant pays 1 energy when its hex's number is rolled and
        nothing blocks that hex — the robber here, and hazards once the event
        chunk lands. Energy is capped at 5 per player; any excess is ignored.
        Returns {player: energy gained}; empty on a 7, off the rule, and when no
        plant matched the roll.
        """
        if not self.rules['power_plants'] or dice_total == 7:
            return {}

        gained = {}
        for (vertex_key, hex_key), plant in self.power_plants.items():
            hex_obj = self.hexes.get(hex_key)
            if hex_obj is None or hex_obj.number != dice_total:
                continue
            if hex_key == self.robber_hex:
                continue
            # A hazard on the hex or on the building the plant is attached to
            # blocks its energy, exactly as it blocks that building's resources.
            if hex_key in self.hazard_hexes or vertex_key in self.hazard_buildings:
                continue
            player = self.get_player(plant['player'])
            if player is None or player.energy >= MAX_ENERGY:
                continue
            player.energy += 1
            gained[plant['player']] = gained.get(plant['player'], 0) + 1
        return {name: gained[name] for name in sorted(gained)}

    # --- Energy uses -------------------------------------------------------

    def spend_energy_for_card(self, player_name: str, card_type: str) -> dict:
        """Return 2 energy for 1 resource or science card of choice (p. 15).

        The energy is returned to the supply; a resource is drawn from the bank
        (which must have it), and science is minted like any commodity.
        """
        if not self.rules['power_plants']:
            return refused('RULE_OFF', 'Energy is not in play')

        block = self._new_energies_action_block(player_name)
        if block is not None:
            return block

        player = self.get_player(player_name)
        if player.energy < ENERGY_PER_CARD:
            return refused('NOT_ENOUGH_ENERGY', f'That costs {ENERGY_PER_CARD} energy')

        if card_type == 'science':
            player.commodities['science'] = player.commodities.get('science', 0) + 1
        elif card_type in self.in_play_resource_types():
            if not self.bank.take(card_type):
                return refused('BANK_EMPTY', f'The bank has no {card_type}')
            player.resources[card_type] = player.resources.get(card_type, 0) + 1
        else:
            return refused('INVALID_CARD', 'Choose a resource or a science card')

        player.energy -= ENERGY_PER_CARD
        return {'success': True, 'error': '', 'card': card_type, 'energy': player.energy}

    # --- The end of the game ----------------------------------------------

    def energy_balance(self, player_name: str) -> int:
        """A player's renewable-minus-fossil balance (rulebook, 'Winning' p. 16)."""
        counts = self._plant_counts(player_name)
        return counts['renewable'] - counts['fossil']

    def energy_balance_winner(self) -> dict:
        """Score the empty-bag end by the fossil/renewable balance (p. 16).

        "Only players who have built more renewable power plants than fossil fuel
        plants may win. The winner is the player with the greatest positive
        difference between the number of renewable and fossil fuel power plants.
        In the event of a tie, the player with the most points wins. If no one
        has built more renewable power plants than fossil fuel plants, then all
        players lose."

        Returns {'winner', 'reason', 'balance', 'victory_points'}: `winner` is
        None when everybody loses. A points tie after the balance tie is broken
        by seat order, deterministically, so a seeded game ends the same way.
        """
        eligible = [p.name for p in self.players if self.energy_balance(p.name) > 0]
        if not eligible:
            return {'winner': None, 'reason': 'bag_empty_all_lose',
                    'balance': None, 'victory_points': 0}

        def key(name):
            # Best balance first, then most points; seat order breaks the rest.
            return (self.energy_balance(name), self.victory_points_for(name))

        winner = max(eligible, key=key)
        return {'winner': winner, 'reason': 'bag_empty',
                'balance': self.energy_balance(winner),
                'victory_points': self.victory_points_for(winner)}

    def end_on_empty_bag(self) -> dict | None:
        """Finish the game when the bag has emptied, or None if it has not.

        The second end condition (rulebook, 'Empty bag?' p. 9 and 'Winning' p.
        16): the game ends the moment a disc is needed and the bag is empty.
        Gated on the balance-end rule, so a table that plays the discs without
        the empty-bag end (or without the scenario at all) is untouched.
        """
        if not self.rules['energy_end_balance']:
            return None
        self.game_state = 'finished'
        return self.energy_balance_winner()

    # --- Client state ------------------------------------------------------

    def new_energies_client_state(self, viewer=None) -> dict | None:
        """The New Energies panel's state, or None off the scenario.

        The plants on the board so the renderer can badge each hex-corner, every
        player's energy for the readout, and each player's remaining plant
        supply. The footprint track, the discs and the end condition are added
        by the later chunks.
        """
        if not self.rules['power_plants']:
            return None
        plants = {}
        for (vertex_key, hex_key), plant in self.power_plants.items():
            plants[f'{vertex_key}|{hex_key}'] = {
                'vertex': vertex_key, 'hex': hex_key,
                'player': plant['player'], 'kind': plant['kind'],
            }
        reserves = {}
        for player in self.players:
            counts = self._plant_counts(player.name)
            reserves[player.name] = {
                'fossil': FOSSIL_PLANT_SUPPLY - counts['fossil'],
                'renewable': RENEWABLE_PLANT_SUPPLY - counts['renewable'],
            }
        state = {
            'plants': plants,
            'energy': {player.name: player.energy for player in self.players},
            'plant_reserves': reserves,
            'max_energy': MAX_ENERGY,
            'plant_costs': dict(PLANT_SCIENCE_COST),
            'energy_per_card': ENERGY_PER_CARD,
            'built_this_turn': self.power_plant_built_this_turn,
        }
        # The global footprint track: the shared level, each player's local
        # footprint for the readout, the track's ends, and whether this turn's
        # once-only fossil demolition has been spent. Absent off the track rule,
        # so a table running power plants without the footprint sees no meter.
        if self.rules['global_footprint']:
            state['global_footprint'] = {
                'level': self.global_footprint_level(),
                'local': {player.name: self.local_footprint(player.name)
                          for player in self.players},
                'max': GF_MAX_PER_PLAYER * len(self.players),
                'start': GF_START_PER_PLAYER * len(self.players),
                'demolished_this_turn': self.fossil_demolished_this_turn,
            }
        # The event-disc bag: how many discs are left, how many green discs each
        # player still has to feed it, and how many this turn's footprint draws.
        # A count only — the disc identities are the bag's secret, the way the
        # dev deck's order is (knowing them turns a random draw into a certain
        # one). Absent off the event rule.
        if self.rules['event_discs']:
            state['events'] = {
                'bag': len(self.event_bag),
                'green_remaining': {name: len(stack)
                                    for name, stack in self.green_discs.items()},
                'draw_count': self.discs_to_draw(self.global_footprint_level()),
                'phase_done': self.event_phase_done,
            }
        # The hazard tokens events have placed: on hexes and on buildings. The
        # board badges these so a player can see which of their production is
        # blocked. Sorted for a stable payload.
        state['hazard_hexes'] = sorted(self.hazard_hexes)
        state['hazard_buildings'] = sorted(self.hazard_buildings)
        return state
