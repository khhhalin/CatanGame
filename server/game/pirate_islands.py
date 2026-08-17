"""The Pirate Islands: a roaming enemy fleet, warships, and fortresses to recapture.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 7 "The Pirate Islands"
(pp. 20-22). Pirates hold four fortresses on the western islands and a neutral
pirate fleet circles the two central desert islands clockwise, threatening the
players' coasts. The scenario's moving parts, each gated on the individual rule
that governs it so a table not playing it is untouched:

- ``pirate_fleet`` — the neutral fleet. "Every time you roll the dice (before
  anything else), the pirate fleet moves a number of hexes equal to the lower of
  the two die results" (p. 22), clockwise along a printed track. "If the pirate
  fleet ends its move on a hex that is adjacent to one of your settlements/cities,
  you are attacked immediately — even before resource production or the
  resolution of a '7' roll." The pirate's strength is the die it moved; yours is
  your warships. Stronger pirate: "you lose 1 Resource Card and another Resource
  Card for each of your cities", drawn at random. Stronger you: "you receive a
  Resource Card of your choice." Equal: nothing. There is no robber (p. 22).

- ``pirate_warships`` — "When you reveal a Knight Card ... you can convert the
  respective hindmost ... 'normal' ship of your route into a warship" (p. 20).
  Modelled as a count of the player's ships turned on their side: revealing a
  Knight spends the card and raises the count, the number that fights the fleet
  and the fortresses.

- ``pirate_fortresses`` — the four western fortresses and their conquest (fortress
  combat and the recapture-plus-10-VP win live alongside the fleet here; see
  ``attack_pirate_fortress`` and ``pirate_islands_victory``).

One mixin on ``Game``, the pattern the other scenario modules (Wonders, Cloth)
use: engine code reads these rules by id, and nothing branches on the scenario's
name. State lives on the ``Game`` directly (fleet position, fortresses, warship
counts), exactly as the cloth and wonder state does.
"""

from game.results import refused

# Each fortress starts as a settlement of a player's colour standing on three
# Catan chits (Seafarers 2021, Scenario 7, p. 20). Clearing all three recaptures
# the settlement.
FORTRESS_CHITS = 3

# The recapture-and-10-VP win (p. 22). The target the lobby sets is the 10; this
# names the two halves so the win path reads them, not a bare literal.
PIRATE_WIN_VICTORY_POINTS = 10

# The five resource cards a repelled fleet lets the winner take one of, in a fixed
# order so a pending choice offers them the same way every game.
REPEL_REWARD_RESOURCES = ('wood', 'brick', 'sheep', 'wheat', 'ore')


class PirateIslandsRules:
    """The fleet, warships and fortresses of The Pirate Islands scenario."""

    # --- Board setup -------------------------------------------------------

    def setup_pirate_islands(self):
        """Read the map's fleet track and fortresses into scenario state.

        A no-op for a map that prints no fleet, so every other board is
        untouched. The track and the fortress intersections are read off the map
        definition; the fortresses are handed to the players in seat order — the
        physical game matches a fortress to the player of that colour, and this
        engine assigns colours by seat, so fortress *i* becomes the *i*-th
        player's own-colour fortress. A fortress with no player to own it (fewer
        players than fortresses, e.g. the "white" fortress in a three-player game)
        is left unowned and can never be the win condition for anybody.
        """
        definition = self.map_definition
        if definition is None or not getattr(definition, 'pirate_fleet_track', ()):
            return

        self.pirate_fleet_track = list(definition.pirate_fleet_track)
        start = definition.pirate_fleet_start
        if start in self.pirate_fleet_track:
            self.pirate_fleet_index = self.pirate_fleet_track.index(start)
        else:
            self.pirate_fleet_index = 0

        for vertex_key, index in getattr(definition, 'pirate_fortresses', ()):
            if vertex_key not in self.vertices:
                continue
            owner = self.players[index].name if index < len(self.players) else None
            self.pirate_fortresses[vertex_key] = {
                'index': index,
                'owner': owner,
                'chits': FORTRESS_CHITS,
                'captured': False,
            }

    # --- The fleet ---------------------------------------------------------

    def pirate_fleet_hex(self):
        """The hex the fleet is sitting on, or None off the scenario."""
        if not self.pirate_fleet_track:
            return None
        return self.pirate_fleet_track[self.pirate_fleet_index]

    def advance_pirate_fleet(self, steps: int) -> str:
        """Sail the fleet ``steps`` hexes clockwise along its track and land it.

        The track is a closed loop of adjacent hexes, so a move of N steps is N
        hops and wraps at the end. Returns the hex the fleet lands on.
        """
        count = len(self.pirate_fleet_track)
        self.pirate_fleet_index = (self.pirate_fleet_index + steps) % count
        return self.pirate_fleet_hex()

    def hex_corner_keys(self, hex_key: str) -> list:
        """The six intersection keys around a hex centre.

        A vertex lists only its *land* hexes, so a sea hex the fleet lands on is
        never found in a building's neighbours; its coast is found the other way
        round — the hex's own six corners, and which of them carry a building.
        """
        coords = tuple(int(part) for part in hex_key.split(','))
        return [
            f'{coords[0] + dx},{coords[1] + dy},{coords[2] + dz}'
            for dx, dy, dz in self.VERTEX_DIRECTIONS
        ]

    def _players_on_coast_of(self, hex_key: str) -> list:
        """Players holding a settlement or city on a corner of this hex, in seat order.

        A building is adjacent to the hex when it stands on one of the hex's six
        corners — the coast the fleet raids.
        """
        corners = set(self.hex_corner_keys(hex_key))
        found = []
        for player in self.players:
            if any(vertex_key in corners
                   for vertex_key in list(player.settlements) + list(player.cities)):
                found.append(player.name)
        return found

    def resolve_pirate_fleet_attack(self, landed_hex: str, pirate_strength: int) -> list:
        """Resolve the fleet's raid on every coast it landed beside.

        The pirate's strength is the die it moved (``pirate_strength``); each
        attacked player's strength is their warships. One outcome dict per
        attacked player, in seat order:

        - pirate stronger: 1 resource plus 1 per city drawn at random and returned
          to the bank ('lost' names them);
        - player stronger: the player owes a pending choice to take a resource of
          their choice ('reward' is True);
        - equal: nothing ('outcome' is 'tie').
        """
        outcomes = []
        for player_name in self._players_on_coast_of(landed_hex):
            warships = self.player_warships.get(player_name, 0)
            if pirate_strength > warships:
                lost = self._raid_random_cards(player_name)
                outcomes.append({
                    'player': player_name, 'outcome': 'raided',
                    'pirate_strength': pirate_strength, 'warships': warships,
                    'lost': lost,
                })
            elif warships > pirate_strength:
                self.open_choice(
                    'pirate_repel_reward', player_name,
                    list(REPEL_REWARD_RESOURCES), hex=landed_hex)
                outcomes.append({
                    'player': player_name, 'outcome': 'repelled',
                    'pirate_strength': pirate_strength, 'warships': warships,
                    'reward': True,
                })
            else:
                outcomes.append({
                    'player': player_name, 'outcome': 'tie',
                    'pirate_strength': pirate_strength, 'warships': warships,
                })
        return outcomes

    def _raid_random_cards(self, player_name: str) -> dict:
        """Draw 1 resource plus 1 per city at random from a hand, back to the bank.

        Returns the discarded cards as a ``{resource: count}`` dict. The draw is
        seeded through the game's own RNG (``rng.sample`` over the flattened hand,
        sorted for determinism) exactly as the discard-on-7 does, so a seeded game
        replays the same raid.
        """
        player = self.get_player(player_name)
        if player is None:
            return {}
        to_lose = 1 + len(player.cities)

        hand = []
        for resource, count in sorted(player.resources.items()):
            hand.extend([resource] * count)
        drawn = self.rng.sample(hand, min(to_lose, len(hand)))

        lost = {}
        for resource in drawn:
            player.resources[resource] -= 1
            self.bank.return_resources(resource, 1)
            lost[resource] = lost.get(resource, 0) + 1
        return lost

    def _choice_pirate_repel_reward(self, choice: dict, option: str) -> dict:
        """Hand the winner of a repelled raid the resource of choice they picked."""
        given = option if self.give_resource(choice['player'], option) else None
        return {'resource': given}

    # --- Warships ----------------------------------------------------------

    def build_warship(self, player_name: str) -> dict:
        """Convert one of this player's ships into a warship by revealing a Knight.

        "When you reveal a Knight Card ... you can convert the ... hindmost
        'normal' ship of your route into a warship" (p. 20). The Knight is spent
        (and set aside — Largest Army is not used in this scenario) and the
        warship count rises. Refused unless the table is playing the rule, it is
        the player's turn, they hold a playable Knight, and they still have a
        plain ship left to turn on its side.
        """
        if not self.rules['pirate_warships']:
            return refused('WARSHIPS_OFF', 'This table is not playing the Pirate Islands scenario')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'Cannot build a warship during setup phase')

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can build a warship')

        can_play, error = self.can_play_dev_card(player_name, 'knight')
        if not can_play:
            return refused('ACTION_REJECTED', error)

        player = self.get_player(player_name)
        already = self.player_warships.get(player_name, 0)
        if len(player.ships) - already <= 0:
            return refused('NO_SHIP_TO_CONVERT', 'You have no plain ship to turn into a warship')

        player.dev_cards['knight']['count'] -= 1
        self.player_warships[player_name] = already + 1
        return {
            'success': True, 'error': '',
            'warships': self.player_warships[player_name],
        }

    # --- Client state ------------------------------------------------------

    def pirate_islands_client_state(self) -> dict:
        """Everything the Pirate Islands panel renders, or None off the scenario.

        The fleet's track and where it sits, each fortress (its owner, chits left
        and whether it is recaptured), and each player's warship count — enough for
        a client to draw the fleet and fortresses and offer the scenario's actions
        without a second copy of any of it.
        """
        if not self.rules['pirate_fleet'] and not self.rules['pirate_fortresses']:
            return None
        return {
            'track': list(self.pirate_fleet_track),
            'fleet_hex': self.pirate_fleet_hex(),
            'fortresses': [
                {
                    'vertex': vertex_key,
                    'index': fort['index'],
                    'owner': fort['owner'],
                    'chits': fort['chits'],
                    'captured': fort['captured'],
                }
                for vertex_key, fort in sorted(self.pirate_fortresses.items())
            ],
            'warships': dict(sorted(self.player_warships.items())),
        }
