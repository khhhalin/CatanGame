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
        for (_vertex_key, hex_key), plant in self.power_plants.items():
            hex_obj = self.hexes.get(hex_key)
            if hex_obj is None or hex_obj.number != dice_total:
                continue
            if hex_key == self.robber_hex:
                continue
            if hex_key in self.hazard_hexes:
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
        return state
