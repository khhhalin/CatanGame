import json
import logging
import os
import random

from game import cities_knights as ck_module
from game import rules as rules_module
from game.bank import Bank
from game.board import BoardBuilder
from game.player import Player
from game.trade import TradeManager
from game.validation import RESOURCE_TYPES

logger = logging.getLogger(__name__)


def _refused(code: str, error: str) -> dict:
    """A refused action, in the shape every engine action returns.

    The machine-readable code travels next to the prose because clients switch
    on the code while only the message is ever shown to a player.
    """
    return {'success': False, 'error': error, 'code': code}


class Game(BoardBuilder):
    """
    Represents a Catan game session.

    Manages players, turn order, game state, and the board layout.
    The board is generated using a cube coordinate system (see hex.md).

    Attributes:
        players (list): List of Player objects in turn order.
        observers (list): List of observer names.
        current_player_index (int): Index of current player in players list.
        game_state (str): "waiting" or "started".
        hex_radius (int): Radius for land hexes (2 = standard 19-hex Catan).
        edge_radius (int): Radius for ocean tiles (3 = one ring around land).
        hexes (dict): Map of hex key -> Hex object.
        vertices (dict): Map of vertex key -> Vertex object.
        edges (dict): Map of edge key -> Edge object.
    """

    # Predefined colors for up to 4 players
    PLAYER_COLORS = ['#e74c3c', '#3498db', '#f39c12', '#9b59b6']

    # Direction vectors for generating neighbors (from hex.md)
    # Used to find adjacent hexes from any given hex

    # Vertex direction vectors from hex center (from hex.md)
    # Used to find the 6 vertices surrounding each hex

    # Edge direction vectors from hex center (from hex.md)
    # Used to find the 6 edges surrounding each hex

    # Per-player piece supply defaults, as in the physical game. Without these
    # a player who can pay simply keeps building, and victory points scale with
    # the settlement and city lists. The lobby can override them per game, so
    # read self.MAX_* (the instance attribute), never the class constant.
    MAX_SETTLEMENTS = 5
    MAX_CITIES = 4
    MAX_ROADS = 15

    def __init__(
        self,
        player_names: list,
        observers: list,
        player_colors: dict = None,
        rng: random.Random = None,
        config=None,
        rules: dict = None,
    ):
        # Injected so tests can replay a game exactly; production passes nothing
        # and gets a real, non-reconstructable source.
        self.rng = rng or random.SystemRandom()

        # Optional rules chosen in the lobby. Fixed for the whole game — a rule
        # that changed mid-game would invalidate decisions already made.
        self.rules = rules_module.coerce(rules or {})

        # Create Player objects with colors
        if player_colors is None:
            player_colors = {}

        # Initialize bank from the chosen rules
        self.bank = Bank(
            resource_limit=self.rules['bank_resource_limit'],
            rng=self.rng,
            dev_card_deck=rules_module.dev_card_deck(self.rules),
        )

        self.players = []
        for i, name in enumerate(player_names):
            color = player_colors.get(name) or (
                self.PLAYER_COLORS[i] if i < len(self.PLAYER_COLORS) else '#ffffff'
            )
            player = Player(name, color)
            # No starting resources - players get resources from dice rolls
            self.players.append(player)

        self.observers = observers
        self.current_player_index = 0
        self.game_state = "waiting"

        # Setup phase variables
        self.game_phase = "setup"  # "setup" or "playing"
        self.setup_turn = 0  # 0-7 for 8 setup turns
        self.setup_action = "settlement"  # "settlement" or "road"
        self.last_setup_settlement = None  # vertex key of last placed settlement
        # player_name -> settlement vertex keys, in placement order (the
        # second one grants the starting resources)
        self.player_settlements = {}

        # Board configuration
        # hex_radius=2 gives us 19 land hexes (standard Catan)
        # edge_radius=3 adds one ring of ocean tiles around the land
        self.hex_radius = 2
        self.edge_radius = 3

        # Robber
        self.robber_hex = None  # Hex key where robber is located
        self.must_move_robber = False  # Set to true when 7 is rolled
        self.must_choose_victim = False  # Set to true when need to pick victim
        self.robber_victims = []  # List of players with settlements near robber hex

        # Discard half mechanic
        self.players_needing_discard = {}  # player_name -> amount to discard

        # Timer settings (in seconds)
        self.dice_roll_time_limit = getattr(config, 'DICE_ROLL_SECONDS', 15)
        self.round_time_limit = getattr(config, 'ROUND_SECONDS', 120)

        # Harbormaster adds a 2-point card, so the official variant raises the
        # target by one to keep the game the same length.
        self.victory_points_to_win = self.rules['victory_target']
        if self.rules['harbormaster']:
            self.victory_points_to_win += 1
        # C&K is a longer game and sets its own target, overriding the lobby's.
        if self.rules['cities_and_knights']:
            self.victory_points_to_win = 13

        # Harbormaster: holder of the special card, or None.
        self.harbormaster_holder = None
        self.harbor_points = {}  # player name -> harbour points

        # Cities & Knights lives behind one attribute: None in the base game,
        # so every C&K branch is a single `if self.ck` check.
        # Piece supplies, overridable from the lobby.
        self.MAX_SETTLEMENTS = self.rules['max_settlements']
        self.MAX_CITIES = self.rules['max_cities']
        self.MAX_ROADS = self.rules['max_roads']

        self.ck = ck_module.CitiesKnights() if self.rules['cities_and_knights'] else None
        if self.ck:
            for player in self.players:
                self.ck.register(player.name)
        self.turn_start_time = None  # timestamp when turn started
        self.dice_rolled_time = None  # timestamp when dice was rolled
        self.has_rolled_dice = False  # whether player has rolled in current turn

        # Game turn counter
        self.turn_count = 0  # Increments after each player's turn ends

        # Free roads from Two Roads development card
        self.free_roads_remaining = 0  # Number of free roads player can place

        # Pending development card effects. A card grants the *right* to a
        # follow-up action; without recording who earned it, the follow-up
        # events (use_invention, use_monopoly) are free actions anyone can call.
        self.pending_invention = None  # player name owed 2 resources of choice
        self.pending_monopoly = None  # player name owed a monopoly declaration

        # Incremented on every accepted mutation so clients can discard a stale
        # or duplicated snapshot instead of silently rewinding the board.
        self.state_version = 0

        # Longest Road and Largest Army
        self.longest_road_holder = None  # Player name with longest road
        self.largest_army_holder = None  # Player name with largest army
        self.longest_road_length = {}  # player_name -> longest road length
        self.knights_played = {}  # player_name -> knight cards played

        # Load building costs from JSON file
        costs_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'costs.json')
        with open(costs_file) as f:
            self.building_costs = json.load(f)

        # Board data structures
        self.hexes = {}  # key -> Hex object
        self.vertices = {}  # key -> Vertex object
        self.edges = {}  # key -> Edge object

        # Generate the complete board
        self._generate_board()

        # Trade manager
        self.trade_manager = TradeManager()

    def has_piece_available(self, player_name: str, piece: str) -> bool:
        """Whether the player still has an unplaced piece of this type.

        A settlement upgraded to a city returns the settlement piece, which is
        why cities are counted separately rather than deducted from settlements.
        """
        player = self.get_player(player_name)
        if not player:
            return False
        if piece == 'settlement':
            return len(player.settlements) < self.MAX_SETTLEMENTS
        if piece == 'city':
            return len(player.cities) < self.MAX_CITIES
        if piece == 'road':
            return len(player.roads) < self.MAX_ROADS
        return False

    def check_invariants(self) -> list:
        """Return a list of violated game invariants; empty means healthy.

        These catch rule bugs that per-action precondition checks miss — an
        action that validated fine but left the board in a state the physical
        game cannot represent.
        """
        problems = []
        for player in self.players:
            for resource_type, count in player.resources.items():
                if count < 0:
                    problems.append(f"{player.name} holds {count} {resource_type}")
            if len(player.settlements) > self.MAX_SETTLEMENTS:
                problems.append(f"{player.name} has {len(player.settlements)} settlements")
            if len(player.cities) > self.MAX_CITIES:
                problems.append(f"{player.name} has {len(player.cities)} cities")
            if len(player.roads) > self.MAX_ROADS:
                problems.append(f"{player.name} has {len(player.roads)} roads")

        for resource_type, count in self.bank.resources.items():
            if count < 0:
                problems.append(f"bank holds {count} {resource_type}")
            if count > self.bank.resource_limit:
                problems.append(f"bank holds {count} {resource_type}, over the limit")

        return problems

    def add_observer(self, name: str):
        """Add an observer to the game."""
        if name not in self.observers:
            self.observers.append(name)

    def remove_observer(self, name: str):
        """Remove an observer from the game."""
        if name in self.observers:
            self.observers.remove(name)

    def is_player(self, name: str) -> bool:
        """Check if a name is a player in this game."""
        return any(p.name == name for p in self.players)

    def get_player(self, name: str) -> Player | None:
        """Get Player object by name."""
        for p in self.players:
            if p.name == name:
                return p
        return None

    def set_player_color(self, name: str, color: str) -> bool:
        """Set or update a player's color. Returns True if successful."""
        player = self.get_player(name)
        if player:
            player.set_color(color)
            return True
        return False

    def get_player_names(self) -> list:
        """Get list of player names (for compatibility)."""
        return [p.name for p in self.players]

    def track_settlement(self, player_name: str, vertex_key: str):
        """Track a settlement placement for starter resources."""
        if player_name not in self.player_settlements:
            self.player_settlements[player_name] = []
        self.player_settlements[player_name].append(vertex_key)

    def _get_setup_player_index(self) -> int:
        """Get player index based on setup turn order.

        Setup order: 0,1,2,3,3,2,1,0 (A->B->C->D->D->C->B->A)
        """
        num_players = len(self.players)
        if self.setup_turn < num_players:
            # First round: forward (0,1,2,3)
            return self.setup_turn
        else:
            # Second round: reverse (3,2,1,0)
            return (2 * num_players - 1) - self.setup_turn

    def setup_building_type(self) -> str:
        """What the current setup placement builds.

        Cities & Knights replaces the second starting settlement with a city,
        so a player begins with one settlement and one city rather than two
        settlements. Everything else about setup is unchanged.
        """
        if self.ck and self.setup_turn >= len(self.players):
            return 'city'
        return 'settlement'

    def _advance_setup_turn(self):
        """Advance to next setup turn. Returns True if setup complete."""
        self.setup_turn += 1
        self.setup_action = "settlement"
        self.last_setup_settlement = None

        num_players = len(self.players)
        if self.setup_turn >= num_players * 2:
            # Setup complete - distribute starter resources from second settlements
            logger.debug("=== Distributing starter resources from second settlements ===")
            for player in self.players:
                settlements = self.player_settlements.get(player.name, [])
                if len(settlements) >= 2:
                    # Second settlement is at index 1
                    second_settlement = settlements[1]
                    self.distribute_from_settlement(second_settlement, player.name)

            self.game_phase = "playing"
            self.current_player_index = 0
            logger.debug("=== Setup complete! Starting normal play. ===")
            return True
        return False

    def best_trade_rate(self, player_name: str, offered: dict) -> int:
        """Cards the player must give per card received, given their harbours.

        A 2:1 harbour only helps with its own resource, the 3:1 harbour helps
        with anything, and without either it is the standard 4:1.
        """
        ports = self.get_player_ports(player_name)
        rate = 3 if 'generic' in ports else 4
        if any(resource in ports for resource in offered):
            rate = min(rate, 2)
        return rate

    def propose_trade(self, player_name: str, offered: dict, wanted: dict) -> dict:
        """Offer a trade to the table, or settle it against the bank.

        A request at or better than the player's harbour rate is not really an
        offer — it is a bank trade, so it completes immediately rather than
        waiting for a response nobody would withhold.
        """
        if self.must_move_robber:
            return _refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        if not offered or not wanted:
            return _refused('INVALID_PAYLOAD', 'A trade needs resources on both sides')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return _refused(
                'NOT_YOUR_TURN', f'Only {current_name} can propose trades on their turn'
            )

        player = self.get_player(player_name)
        if player is None:
            return _refused('INVALID_TARGET', 'Unknown player')

        for resource, count in offered.items():
            available = player.resources.get(resource, 0)
            if available < count:
                return _refused(
                    'INSUFFICIENT_RESOURCES',
                    f'Not enough {resource}: have {available}, offering {count}',
                )

        rate = self.best_trade_rate(player_name, offered)
        if sum(offered.values()) / sum(wanted.values()) < rate:
            offer = self.trade_manager.propose(player_name, offered, wanted)
            if not offer:
                return _refused('TRADE_LIMIT', 'Maximum number of trade offers reached')
            return {'success': True, 'error': '', 'kind': 'offer', 'offer': offer}

        # Check the bank can cover the whole request before touching anything.
        # Mutating first and unwinding on failure previously left the player
        # holding whatever was granted before the shortfall.
        for resource, count in wanted.items():
            if self.bank.resources.get(resource, 0) < count:
                return _refused('BANK_EMPTY', f'Bank does not have {count} {resource}')

        for resource, count in offered.items():
            player.resources[resource] = player.resources.get(resource, 0) - count
            self.bank.return_resources(resource, count)

        for resource, count in wanted.items():
            self.bank.take(resource, count)
            player.resources[resource] = player.resources.get(resource, 0) + count

        return {'success': True, 'error': '', 'kind': 'bank', 'rate_used': rate}

    def accept_trade(self, offer_id: int, player_name: str) -> dict:
        """Signal willingness to take an offer, if the cards are there."""
        offer = self.trade_manager.offers.get(offer_id)
        if not offer:
            return _refused('TRADE_NOT_FOUND', 'Trade offer not found')

        player = self.get_player(player_name)
        if not player:
            return _refused('INVALID_TARGET', 'Unknown player')

        for resource, count in offer['wanted_resources'].items():
            if player.resources.get(resource, 0) < count:
                return _refused(
                    'INSUFFICIENT_RESOURCES', f'Not enough {resource} to accept this trade'
                )

        if not self.trade_manager.accept(offer_id, player_name, player.resources):
            return _refused('TRADE_FAILED', 'Could not accept trade')
        return {'success': True, 'error': ''}

    def decline_trade(self, offer_id: int, player_name: str) -> bool:
        """Decline a trade offer."""
        return self.trade_manager.decline(offer_id, player_name)

    def cancel_trade(self, offer_id: int, player_name: str) -> bool:
        """Cancel a trade offer (proposer only)."""
        return self.trade_manager.cancel(offer_id, player_name)

    def complete_trade(self, offer_id: int, proposer: str, selected_responder: str = None) -> dict:
        """Settle an accepted offer and move the cards."""
        settlement = self.trade_manager.complete(offer_id, proposer, selected_responder)
        if not settlement:
            return _refused('TRADE_FAILED', 'Could not complete trade')

        if settlement['type'] == 'bank':
            self.execute_bank_trade(offer_id, proposer)
            return {'success': True, 'error': '', 'type': 'bank', 'responder': None}

        responder = settlement['responder']
        self.execute_trade_with_player(offer_id, proposer, responder)
        return {'success': True, 'error': '', 'type': 'player', 'responder': responder}

    def execute_trade_with_player(self, offer_id: int, proposer: str, responder: str):
        """Execute a player-to-player trade."""
        offer = self.trade_manager.offers.get(offer_id)
        if not offer or offer['status'] != 'completed':
            return False

        proposer_player = self.get_player(proposer)
        responder_player = self.get_player(responder)

        if not proposer_player or not responder_player:
            return False

        # Transfer offered resources FROM proposer TO responder
        for resource, count in offer['offered_resources'].items():
            proposer_player.resources[resource] = proposer_player.resources.get(resource, 0) - count
            responder_player.resources[resource] = (
                responder_player.resources.get(resource, 0) + count
            )

        # Transfer wanted resources FROM responder TO proposer
        for resource, count in offer['wanted_resources'].items():
            responder_player.resources[resource] = (
                responder_player.resources.get(resource, 0) - count
            )
            proposer_player.resources[resource] = proposer_player.resources.get(resource, 0) + count

        return True

    def execute_bank_trade(self, offer_id: int, proposer: str):
        """Execute a bank trade (4:1 or better ratio)."""
        offer = self.trade_manager.offers.get(offer_id)
        if not offer or offer['status'] != 'completed':
            return False

        proposer_player = self.get_player(proposer)
        if not proposer_player:
            return False

        # Transfer offered resources to bank
        for resource, count in offer['offered_resources'].items():
            for _ in range(count):
                self.bank.return_resources(resource)

        # Transfer wanted resources from bank to player
        for resource, count in offer['wanted_resources'].items():
            for _ in range(count):
                self.bank.take(resource)
            proposer_player.resources[resource] = proposer_player.resources.get(resource, 0) + count

        return True

    def get_player_ports(self, player_name: str) -> dict:
        """Get all ports accessible to a player based on their settlements/cities."""
        player = self.get_player(player_name)
        if not player:
            return {}

        ports = {}
        for vertex_key in player.settlements + player.cities:
            vertex = self.vertices.get(vertex_key)
            if vertex and vertex.port:
                port_type = vertex.port.get("type")
                if port_type == "generic":
                    ports["generic"] = True
                elif port_type == "resource":
                    resource = vertex.port.get("resource")
                    ports[resource] = True

        return ports

    def update_harbormaster(self):
        """Recompute harbour points and who holds the Harbormaster card.

        Traders & Barbarians: a settlement on a harbour is 1 point, a city 2.
        The first player to reach 3 takes the card; it passes only when someone
        else has *more*, so a tie leaves it where it is.
        """
        if not self.rules['harbormaster']:
            return

        self.harbor_points = {}
        for player in self.players:
            points = 0
            for vertex_key in player.settlements:
                vertex = self.vertices.get(vertex_key)
                if vertex and vertex.port:
                    points += 1
            for vertex_key in player.cities:
                vertex = self.vertices.get(vertex_key)
                if vertex and vertex.port:
                    points += 2
            self.harbor_points[player.name] = points

        best = max(self.harbor_points.values(), default=0)
        if best < 3:
            self.harbormaster_holder = None
            return

        leaders = [name for name, pts in self.harbor_points.items() if pts == best]
        if self.harbormaster_holder in leaders:
            # Still tied for the lead, so the holder keeps it.
            return
        if len(leaders) == 1:
            self.harbormaster_holder = leaders[0]

    # --- Base game actions -------------------------------------------------

    def current_player_name(self) -> str:
        """Whose turn it is, following the snaking order during setup."""
        if self.game_phase == "setup":
            return self.players[self._get_setup_player_index()].name
        return self.players[self.current_player_index].name

    def claim_victory(self, player_name: str) -> int | None:
        """The winning total if this player has just won, otherwise None.

        Marks the game finished, so a caller only has to announce it. Every
        action that can end the game asks here rather than comparing totals
        itself, which is how a new scoring rule stays in one place.
        """
        points = self.victory_points_for(player_name)
        if points < self.victory_points_to_win:
            return None
        self.game_state = "finished"
        return points

    def _cost_message(self, building_type: str) -> str:
        cost = self.get_cost(building_type)
        cost_str = ', '.join(f"{v} {k}" for k, v in cost.items())
        return f'Not enough resources. Need: {cost_str}'

    def _respects_distance_rule(self, vertex_key: str) -> bool:
        """Catan's distance rule: no building on an adjacent intersection,
        whoever owns it."""
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return False
        for neighbour_key in vertex.neighbors.get('vertices', []):
            neighbour = self.vertices.get(neighbour_key)
            if neighbour is not None and neighbour.building is not None:
                return False
        return True

    def _road_connects(self, player_name: str, edge_key: str) -> bool:
        """Whether a road at this edge would touch the player's own network."""
        edge = self.edges.get(edge_key)
        if edge is None:
            return False
        for vertex_key in edge.neighbors.get('vertices', []):
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            for connected_key in vertex.neighbors.get('edges', []):
                if connected_key == edge_key:
                    continue
                connected = self.edges.get(connected_key)
                if connected and connected.road and connected.road.get('player') == player_name:
                    return True
        return False

    def place_settlement(self, player_name: str, vertex_key: str) -> dict:
        """Place a settlement, free during setup and paid for afterwards.

        Returns {'success', 'error', 'code', 'building_type'} — Cities &
        Knights makes the second setup placement a city, so the caller is told
        what actually went down rather than assuming.
        """
        if self.must_move_robber:
            return _refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        in_setup = self.game_phase == "setup"
        current_name = self.current_player_name()
        if current_name != player_name:
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can place buildings')

        # Setup alternates settlement then road. Without this check a player can
        # keep placing free settlements for the whole of their setup turn.
        if in_setup and self.setup_action != "settlement":
            return _refused('WRONG_PHASE', 'You must place a road next')

        # In C&K setup the second placement is a city, so check that supply instead.
        building_type = self.setup_building_type() if in_setup else 'settlement'
        if not self.has_piece_available(player_name, building_type):
            limit = self.MAX_CITIES if building_type == 'city' else self.MAX_SETTLEMENTS
            return _refused('NO_PIECES_LEFT', f'You have used all {limit} {building_type}s')

        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return _refused('INVALID_TARGET', 'Invalid vertex')
        if vertex.building is not None:
            return _refused('OCCUPIED', 'This location already has a building')
        if not self._respects_distance_rule(vertex_key):
            return _refused(
                'INVALID_PLACEMENT', 'Cannot place settlement next to another settlement'
            )

        if not in_setup:
            if not self._touches_own_road(player_name, vertex_key):
                return _refused(
                    'INVALID_PLACEMENT', 'Settlement must be connected to your own road'
                )
            if not self.can_afford(player_name, 'settlement'):
                return _refused('INSUFFICIENT_RESOURCES', self._cost_message('settlement'))
            self.deduct_cost(player_name, 'settlement')

        vertex.building = {'type': building_type, 'player': player_name}

        player = self.get_player(player_name)
        if player:
            if building_type == 'city':
                player.cities.append(vertex_key)
            else:
                player.settlements.append(vertex_key)

        # Recorded for the starter resources the second placement grants.
        self.track_settlement(player_name, vertex_key)
        self.update_harbormaster()

        if in_setup:
            self.last_setup_settlement = vertex_key
        self.setup_action = "road" if in_setup else "settlement"

        return {'success': True, 'error': '', 'building_type': building_type}

    def build_road(self, player_name: str, edge_key: str) -> dict:
        """Build a road, free during setup and paid for afterwards.

        Returns {'success', 'error', 'code', 'used_free_road'} — a Two Roads
        card pays for the placement instead of the player's hand.
        """
        if self.must_move_robber:
            return _refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        in_setup = self.game_phase == "setup"
        current_name = self.current_player_name()
        if current_name != player_name:
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can place buildings')

        if in_setup and self.setup_action != "road":
            return _refused('WRONG_PHASE', 'You must place a settlement first')

        if not self.has_piece_available(player_name, 'road'):
            return _refused('NO_PIECES_LEFT', f'You have used all {self.MAX_ROADS} roads')

        edge = self.edges.get(edge_key)
        if edge is None:
            return _refused('INVALID_TARGET', 'Invalid edge')
        if edge.road is not None:
            return _refused('OCCUPIED', 'This location already has a road')

        used_free_road = False
        if in_setup:
            # The setup road must touch the settlement just placed. This is
            # unconditional — guarding it on last_setup_settlement being set
            # meant a road emitted before any settlement could land anywhere.
            if not self.last_setup_settlement:
                return _refused('WRONG_PHASE', 'You must place a settlement first')
            if self.last_setup_settlement not in edge.neighbors.get('vertices', []):
                return _refused('INVALID_PLACEMENT', 'Road must be connected to your settlement')
        else:
            if not self._road_connects(player_name, edge_key):
                return _refused('INVALID_PLACEMENT', 'Road must be connected to your own road')
            if self.free_roads_remaining > 0:
                self.free_roads_remaining -= 1
                used_free_road = True
            elif not self.can_afford(player_name, 'road'):
                return _refused('INSUFFICIENT_RESOURCES', self._cost_message('road'))
            else:
                self.deduct_cost(player_name, 'road')

        edge.road = {'player': player_name}

        # Track the road on the player too, so the piece limit and any
        # piece-count invariant have something to count.
        owner = self.get_player(player_name)
        if owner is not None and edge_key not in owner.roads:
            owner.roads.append(edge_key)

        if in_setup:
            self._advance_setup_turn()
        else:
            self.update_longest_road()

        return {'success': True, 'error': '', 'used_free_road': used_free_road}

    def upgrade_city(self, player_name: str, vertex_key: str) -> dict:
        """Turn one of the player's own settlements into a city."""
        if self.must_move_robber:
            return _refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        if self.game_phase == "setup":
            return _refused('WRONG_PHASE', 'Cannot upgrade to city during setup phase')

        current_name = self.current_player_name()
        if current_name != player_name:
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can upgrade buildings')

        if not self.has_piece_available(player_name, 'city'):
            return _refused('NO_PIECES_LEFT', f'You have used all {self.MAX_CITIES} cities')

        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return _refused('INVALID_TARGET', 'Invalid vertex')
        if vertex.building is None:
            return _refused('INVALID_TARGET', 'No building at this location')
        if vertex.building.get('type') != 'settlement':
            return _refused('INVALID_TARGET', 'Can only upgrade settlements to cities')
        if vertex.building.get('player') != player_name:
            return _refused('NOT_YOUR_PIECE', 'Can only upgrade your own settlements')

        if not self.can_afford(player_name, 'city'):
            return _refused('INSUFFICIENT_RESOURCES', self._cost_message('city'))
        self.deduct_cost(player_name, 'city')

        vertex.building = {'type': 'city', 'player': player_name}

        player = self.get_player(player_name)
        if player and vertex_key in player.settlements:
            player.settlements.remove(vertex_key)
            player.cities.append(vertex_key)

        self.update_harbormaster()
        return {'success': True, 'error': ''}

    def move_robber(self, player_name: str, hex_key: str) -> dict:
        """Move the robber onto a land hex and work out who can be robbed.

        Returns {'success', 'error', 'code', 'victims'}; a non-empty victim
        list means the mover still owes a choice.
        """
        if self.game_phase == "setup":
            return _refused('WRONG_PHASE', 'Cannot move robber during setup')

        if not self.must_move_robber:
            return _refused('WRONG_PHASE', 'You do not need to move the robber')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can move the robber')

        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None:
            return _refused('INVALID_TARGET', 'Invalid hex')
        if hex_obj.type == 'ocean':
            return _refused('INVALID_TARGET', 'Cannot place robber on ocean')

        # Friendly Robber, when enabled, protects anyone still on 2 victory points.
        if not self.robber_is_allowed(hex_key):
            return _refused(
                'FRIENDLY_ROBBER',
                'Friendly Robber: that hex touches a settlement of a player on '
                '2 victory points. Pick another hex.',
            )

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
            return _refused('WRONG_PHASE', 'No victim selection required')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can choose victim')

        if victim_name not in self.robber_victims:
            return _refused('INVALID_TARGET', 'Invalid victim selection')

        stolen = self.steal_resource(victim_name, player_name)
        self.must_choose_victim = False
        self.robber_victims = []
        return {'success': True, 'error': '', 'stolen': stolen}

    def discard(self, player_name: str, resources: dict) -> dict:
        """Hand back half a hand that was over the limit when a 7 came up."""
        if player_name not in self.players_needing_discard:
            return _refused('WRONG_PHASE', 'You do not need to discard')

        if not self.discard_resources(player_name, resources):
            return _refused('INVALID_PAYLOAD', 'Invalid discard amount or resources')

        return {'success': True, 'error': ''}

    # --- Cities & Knights actions -----------------------------------------

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

    def _touches_own_road(self, player_name: str, vertex_key: str) -> bool:
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return False
        for edge_key in vertex.neighbors.get('edges', []):
            edge = self.edges.get(edge_key)
            if edge and edge.road and edge.road.get('player') == player_name:
                return True
        return False

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

    def victory_points_for(self, player_name: str) -> int:
        """A player's total, including anything the optional rules award.

        Single entry point so a new scoring rule is added in one place rather
        than in every handler that checks for a win.
        """
        player = self.get_player(player_name)
        if player is None:
            return 0

        points = player.get_victory_points(self.longest_road_holder, self.largest_army_holder)
        if self.rules['harbormaster'] and self.harbormaster_holder == player_name:
            points += 2

        if self.ck:
            # A metropolis makes its city worth 4 instead of 2, so it adds 2 on
            # top of what the city already scored.
            points += 2 * self.ck.metropolis_count(player_name)
            points += self.ck.defender_cards.get(player_name, 0)

        return points

    def robber_is_allowed(self, hex_key: str) -> bool:
        """Whether the robber may be moved onto this hex.

        Friendly Robber (Traders & Barbarians): a hex touching a settlement of
        a player on only 2 victory points is off limits, so the player who is
        furthest behind cannot be kicked while they are down.
        """
        if not self.rules['friendly_robber']:
            return True

        if hex_key not in self.hexes:
            return False

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

        The rule sends it to the desert in that case.
        """
        for key, hex_obj in self.hexes.items():
            if hex_obj.type == 'desert':
                return key
        return None

    def get_board_data(self, viewer: str = None) -> dict:
        """
        Serialize board data for sending to client.

        Args:
            viewer: Name of the player this payload is for. Their own hand is
                included in full; every other player is reduced to card counts.
                Passing None redacts every hand, which is what observers get.

        Returns:
            dict: Board data including hexes, vertices, and edges
        """
        hexes = {}
        for key, hex_obj in self.hexes.items():
            hexes[key] = {
                'type': hex_obj.type,
                'number': hex_obj.number,
                'neighbors': hex_obj.neighbors,
            }

        vertices = {}
        for key, vertex_obj in self.vertices.items():
            vertex_data = {'building': vertex_obj.building, 'neighbors': vertex_obj.neighbors}
            if vertex_obj.port:
                vertex_data['port'] = vertex_obj.port
            vertices[key] = vertex_data

        edges = {}
        for key, edge_obj in self.edges.items():
            edges[key] = {'road': edge_obj.road, 'neighbors': edge_obj.neighbors}

        # Clean up expired trades
        self.trade_manager.cleanup_expired()

        # Build my_offers for each player
        my_offers = {}
        for player in self.players:
            my_offers[player.name] = self.trade_manager.get_my_offers(player.name)

        return {
            'hexes': hexes,
            'vertices': vertices,
            'edges': edges,
            'players': [
                p.to_dict(self.longest_road_holder, self.largest_army_holder, viewer)
                for p in self.players
            ],
            'bank': self.bank.get_all(),
            'rules': self.rules,
            'cities_knights': self.ck.to_dict(viewer) if self.ck else None,
            'harbormaster_holder': self.harbormaster_holder,
            'harbor_points': self.harbor_points,
            # Only the total: the per-type breakdown is the deck order, and
            # knowing what is left turns a probabilistic draw into a certain one.
            'dev_cards_remaining': self.bank.total_dev_cards_remaining(),
            'state_version': self.state_version,
            'trades': {'active': self.trade_manager.get_all_active(), 'my_offers': my_offers},
            'game_phase': self.game_phase,
            'setup_action': self.setup_action,
            'current_player': self.players[self._get_setup_player_index()].name
            if self.game_phase == "setup"
            else self.players[self.current_player_index].name,
            'robber_hex': self.robber_hex,
            'must_move_robber': self.must_move_robber,
            'must_choose_victim': self.must_choose_victim,
            'robber_victims': self.robber_victims,
            'players_needing_discard': self.players_needing_discard,
            'dice_roll_time': self.get_dice_roll_time_remaining(),
            'round_time': self.get_round_time_remaining(),
            'has_rolled_dice': self.has_rolled_dice,
            'turn_count': self.turn_count,
            'free_roads_remaining': self.free_roads_remaining,
            'longest_road_holder': self.longest_road_holder,
            'largest_army_holder': self.largest_army_holder,
            'longest_road_length': self.longest_road_length,
            'knights_played': {p.name: p.knights_played for p in self.players},
        }

    def distribute_resources(self, dice_total: int):
        """Distribute resources to players based on dice roll.

        Each settlement adjacent to a hex with matching number receives 1 resource.
        Skips distribution for 7 (robber not implemented).

        Args:
            dice_total: The sum of the two dice rolled
        """
        if dice_total == 7:
            return

        gained_resources = {}

        for _vertex_key, vertex in self.vertices.items():
            if not vertex.building or vertex.building.get('type') not in ('settlement', 'city'):
                continue

            building_type = vertex.building.get('type')
            resource_amount = 2 if building_type == 'city' else 1

            player_name = vertex.building.get('player')
            if not player_name:
                continue

            player = self.get_player(player_name)
            if not player:
                continue

            for hex_key in vertex.neighbors.get('hexes', []):
                if hex_key not in self.hexes:
                    continue

                hex_obj = self.hexes[hex_key]
                # Skip robber hex and non-matching numbers
                if hex_key == self.robber_hex:
                    continue
                if hex_obj.number != dice_total or hex_obj.type in ('desert', 'ocean'):
                    continue

                # Cities & Knights: a city on pasture, mountain or forest yields
                # one resource plus one commodity instead of two resources.
                # Fields and hills have no commodity, so a city there still
                # produces two, exactly as in the base game.
                commodity = None
                if self.ck and building_type == 'city':
                    commodity = ck_module.COMMODITY_FROM_TERRAIN.get(hex_obj.type)

                take_resources = 1 if commodity else resource_amount

                for _ in range(take_resources):
                    if self.bank.take(hex_obj.type):
                        player.resources[hex_obj.type] = player.resources.get(hex_obj.type, 0) + 1

                        if player_name not in gained_resources:
                            gained_resources[player_name] = {}
                        gained_resources[player_name][hex_obj.type] = (
                            gained_resources[player_name].get(hex_obj.type, 0) + 1
                        )

                if commodity:
                    player.commodities[commodity] = player.commodities.get(commodity, 0) + 1
                    gained_resources.setdefault(player_name, {})
                    gained_resources[player_name][commodity] = (
                        gained_resources[player_name].get(commodity, 0) + 1
                    )

        if gained_resources:
            logger.debug(f"Resources distributed (rolled {dice_total}):")
            for player_name, resources in gained_resources.items():
                resource_str = ', '.join(
                    f"+{count} {resource}" for resource, count in resources.items()
                )
                logger.debug(f"  {player_name}: {resource_str}")
            logger.debug(f"  Bank: {self.bank}")

    def distribute_from_settlement(self, vertex_key: str, player_name: str):
        """Give resources from a specific settlement's adjacent hexes (for starter resources)."""
        vertex = self.vertices.get(vertex_key)
        if not vertex:
            return

        player = self.get_player(player_name)
        if not player:
            return

        gained = {}

        is_city = bool(vertex.building) and vertex.building.get('type') == 'city'

        for hex_key in vertex.neighbors.get('hexes', []):
            hex_obj = self.hexes.get(hex_key)
            if hex_obj and hex_obj.type not in ('desert', 'ocean'):
                if self.bank.take(hex_obj.type):
                    player.resources[hex_obj.type] = player.resources.get(hex_obj.type, 0) + 1
                    gained[hex_obj.type] = gained.get(hex_obj.type, 0) + 1

                # C&K: the starting city yields "one resource and, where
                # applicable, one commodity" from each adjacent hex — one of
                # each, not the doubled production of a normal city turn.
                if self.ck and is_city:
                    commodity = ck_module.COMMODITY_FROM_TERRAIN.get(hex_obj.type)
                    if commodity:
                        player.commodities[commodity] = player.commodities.get(commodity, 0) + 1
                        gained[commodity] = gained.get(commodity, 0) + 1

        if gained:
            logger.debug(f"Starter resources for {player_name} from {vertex_key}: {gained}")

    def check_discard_required(self):
        """Check which players need to discard half their resources (7 rolled)."""
        self.players_needing_discard = {}

        base_limit = self.rules['max_hand_before_discard']
        for player in self.players:
            # Commodities count toward the limit; each city wall raises it by 2.
            total_cards = player.total_cards()
            limit = base_limit
            if self.ck:
                limit += self.ck.city_wall_bonus(player.name)
            if total_cards > limit:
                discard_amount = total_cards // 2
                self.players_needing_discard[player.name] = discard_amount

        if self.players_needing_discard:
            logger.debug(f"Players needing to discard: {self.players_needing_discard}")

    def discard_resources(self, player_name: str, resources: dict) -> bool:
        """Process resource discard from a player.

        Args:
            player_name: Name of player discarding
            resources: Dict of resource_type -> count to discard

        Returns:
            bool: True if discard was successful
        """
        if player_name not in self.players_needing_discard:
            return False

        player = self.get_player(player_name)
        if not player:
            return False

        # Caller is expected to have run this through validation.clean_resource_counts,
        # but re-check here so the engine is safe to call directly from a test or
        # a future handler: a negative count would pass the `current < count`
        # check below and then *add* cards when subtracted.
        for resource_type, count in resources.items():
            if resource_type not in RESOURCE_TYPES:
                return False
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                return False

        required = self.players_needing_discard[player_name]
        discard_total = sum(resources.values())

        if discard_total != required:
            return False

        for resource_type, count in resources.items():
            current = player.resources.get(resource_type, 0)
            if current < count:
                return False

        for resource_type, count in resources.items():
            player.resources[resource_type] = player.resources.get(resource_type, 0) - count
            self.bank.return_resources(resource_type, count)

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

    def give_resource(self, player_name: str, resource_type: str) -> bool:
        """Give a resource to a player.

        Args:
            player_name: Name of player to receive resource
            resource_type: Resource type to give

        Returns:
            bool: True if resource was given
        """
        player = self.get_player(player_name)
        if not player:
            return False

        if self.bank.take(resource_type):
            player.resources[resource_type] = player.resources.get(resource_type, 0) + 1
            return True
        return False

    def get_cost(self, building_type: str) -> dict:
        """Get the cost for a building type."""
        return self.building_costs.get(building_type, {})

    def can_afford(self, player_name: str, building_type: str) -> bool:
        """Check if player can afford the building cost."""
        player = self.get_player(player_name)
        if not player:
            return False

        cost = self.get_cost(building_type)
        for resource, amount in cost.items():
            if player.resources.get(resource, 0) < amount:
                return False
        return True

    def deduct_cost(self, player_name: str, building_type: str) -> bool:
        """Deduct a building cost and return the cards to the bank.

        Returns True if the player could pay.
        """
        player = self.get_player(player_name)
        if not player:
            return False

        if not self.can_afford(player_name, building_type):
            return False

        cost = self.get_cost(building_type)
        for resource, amount in cost.items():
            player.resources[resource] -= amount
            self.bank.return_resources(resource, amount)
        return True

    def buy_dev_card(self, player_name: str) -> dict:
        """Buy a development card from the bank. Returns result dict."""
        if self.game_phase == "setup":
            return _refused('WRONG_PHASE', 'Cannot buy development cards during setup')

        if self.must_move_robber:
            return _refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can buy development cards')

        player = self.get_player(player_name)
        if not player:
            return _refused('ACTION_FAILED', 'Player not found')

        if not self.can_afford(player_name, 'knight'):
            return _refused('ACTION_FAILED', 'Cannot afford development card')

        card_type = self.bank.draw_dev_card()
        if not card_type:
            return _refused('ACTION_FAILED', 'No development cards left')

        if not self.deduct_cost(player_name, 'knight'):
            self.bank.return_dev_card(card_type)
            return _refused('ACTION_FAILED', 'Failed to deduct cost')

        player.dev_cards[card_type]['count'] += 1
        player.dev_cards[card_type]['purchase_turn'] = self.turn_count
        return {'success': True, 'error': '', 'card_type': card_type}

    def get_dev_cards_for_player(self, player_name: str) -> dict:
        """Get development cards for a specific player."""
        player = self.get_player(player_name)
        if not player:
            return {}
        return player.dev_cards.copy()

    def use_invention(self, player_name: str, resources: dict) -> dict:
        """Redeem the two cards an Invention card promised.

        Returns {'success', 'error', 'code', 'taken'} — 'taken' can be short of
        what was asked for if the bank ran out mid-grant.
        """
        # The card grants the right to this follow-up; without the pending flag
        # anyone could call it at any time and drain the bank.
        if self.pending_invention != player_name:
            return _refused('NO_PENDING_INVENTION', 'You have not played an Invention card')

        if sum(resources.values()) != 2:
            return _refused('INVALID_PAYLOAD', 'Invention gives exactly 2 resources')

        player = self.get_player(player_name)
        if not player:
            return _refused('INVALID_TARGET', 'Unknown player')

        taken = {}
        for resource_type, count in resources.items():
            for _ in range(count):
                if self.bank.take(resource_type):
                    player.resources[resource_type] = player.resources.get(resource_type, 0) + 1
                    taken[resource_type] = taken.get(resource_type, 0) + 1

        self.pending_invention = None
        return {'success': True, 'error': '', 'taken': taken}

    def use_monopoly(self, player_name: str, resource_type: str) -> dict:
        """Use monopoly card - steal ALL of specified resource from all other players."""
        if self.pending_monopoly != player_name:
            return _refused('NO_PENDING_MONOPOLY', 'You have not played a Monopoly card')

        # Spent the moment it is redeemed, however the redemption turns out —
        # a failed declaration must not leave a second one available.
        self.pending_monopoly = None

        player = self.get_player(player_name)
        if not player:
            return _refused('ACTION_REJECTED', 'Player not found')

        if resource_type not in self.bank.resources:
            return _refused('ACTION_REJECTED', 'Invalid resource type')

        stolen_count = 0
        stolen_from = []

        for other_player in self.players:
            if other_player.name == player_name:
                continue

            other_resources = other_player.resources.get(resource_type, 0)
            if other_resources > 0:
                other_player.resources[resource_type] = 0
                player.resources[resource_type] = (
                    player.resources.get(resource_type, 0) + other_resources
                )
                stolen_count += other_resources
                stolen_from.append(f"{other_player.name}({other_resources})")

        logger.debug(
            "Player %s used Monopoly on %s: stole %s from %s",
            player_name, resource_type, stolen_count, stolen_from
        )
        return {
            'success': True,
            'error': '',
            'stolen_count': stolen_count,
            'stolen_from': stolen_from,
        }

    def can_play_dev_card(self, player_name: str, card_type: str) -> tuple:
        """Check if player can play a development card. Returns (can_play: bool, error: str)."""
        player = self.get_player(player_name)
        if not player:
            return (False, 'Player not found')

        card_data = player.dev_cards.get(card_type)
        if not card_data or card_data['count'] <= 0:
            return (False, 'You do not have this card')

        if not self.has_rolled_dice and card_type != 'knight':
            return (False, 'You must roll the dice first')

        if (
            card_data['purchase_turn'] is not None
            and self.turn_count - card_data['purchase_turn'] < 1
        ):
            return (False, 'Cannot play card in the same turn it was purchased')

        return (True, '')

    def play_dev_card(self, player_name: str, card_type: str) -> dict:
        """Play a development card and apply its effect.

        Returns the usual pair plus 'needs_resources' (Invention),
        'needs_resource' (Monopoly), 'must_move_robber' (Knight) and 'won':
        each card leaves the table owing a different follow-up, and the caller
        has to know which one without re-deciding it.
        """
        if self.game_phase == "setup":
            return _refused('WRONG_PHASE', 'Cannot play development cards during setup')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can play development cards')

        # A Knight may be played while the robber is still owed — that is how a
        # player reassigns it. Nothing else may.
        if card_type != 'knight' and self.must_move_robber:
            return _refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        can_play, error = self.can_play_dev_card(player_name, card_type)
        if not can_play:
            return _refused('ACTION_REJECTED', error)

        player = self.get_player(player_name)
        player.dev_cards[card_type]['count'] -= 1

        result = {
            'success': True,
            'error': '',
            'card_type': card_type,
            'needs_resources': False,
            'needs_resource': False,
            'must_move_robber': False,
            'won': False,
            'victory_points': 0,
        }

        if card_type == 'knight':
            self.must_move_robber = True
            player.knights_played += 1
            self.update_largest_army()
            result['must_move_robber'] = True
        elif card_type == 'victory_point':
            player.victory_points += 1
            points = self.claim_victory(player_name)
            if points is not None:
                result['won'] = True
                result['victory_points'] = points
        elif card_type == 'invention':
            # Record who is owed the follow-up. Without this, use_invention is a
            # free action any client can call without ever holding the card.
            self.pending_invention = player_name
            result['needs_resources'] = True
        elif card_type == 'two_roads':
            self.free_roads_remaining = 2
        elif card_type == 'monopoly':
            self.pending_monopoly = player_name
            result['needs_resource'] = True

        logger.debug("Player %s played %s", player_name, card_type)
        return result

    def start(self):
        """Start the game and shuffle player order."""
        self.rng.shuffle(self.players)
        self.game_state = "started"
        self.start_turn()
        logger.debug("\n=== Game started! ===")
        logger.debug(f"Player order: {self.players}")
        logger.debug(f"Current player: {self.players[self.current_player_index]}")
        logger.debug("=====================\n")

    def start_turn(self):
        """Start a new turn and reset timers."""
        import time

        self.turn_start_time = time.time()
        self.dice_rolled_time = None
        self.has_rolled_dice = False
        self.free_roads_remaining = 0  # Reset free roads at start of turn

    def advance_turn(self, player_name: str) -> dict:
        """End the current turn at a player's request."""
        if self.must_move_robber:
            return _refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        if self.must_choose_victim:
            return _refused('MUST_CHOOSE_VICTIM', 'You must choose a victim to steal from')

        if player_name in self.players_needing_discard:
            return _refused('MUST_DISCARD', 'You must discard resources first')

        if self.game_phase == "setup":
            return _refused('WRONG_PHASE', 'Cannot skip turn during setup phase')

        # The seat's own player normally ends the turn. Once the round timer has
        # run out anyone may advance it, so an absent player cannot stall the table.
        current_name = self.players[self.current_player_index].name
        if player_name != current_name and not self.is_round_expired():
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can advance the turn')

        return {'success': True, 'error': '', 'current_player': self.force_advance_turn()}

    def force_advance_turn(self) -> str:
        """Move to the next player and reset the per-turn state, unconditionally.

        The turn watchdog uses this: a turn that has timed out ends whether or
        not the player whose turn it was is still at the table.
        """
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        self.turn_count += 1

        # A new turn clears any follow-up the previous player never used, so an
        # unspent Invention cannot be redeemed two turns later.
        self.pending_invention = None
        self.pending_monopoly = None
        self.free_roads_remaining = 0

        self.start_turn()
        if self.ck:
            # Clears each knight's per-turn flags. Without it a knight that acts
            # once stays spent for the rest of the game.
            self.ck.start_turn()

        return self.players[self.current_player_index].name

    def roll_dice(self, player_name: str) -> dict:
        """Roll for the current player, resolve the roll, and pay production.

        Returns the usual pair plus 'dice1', 'dice2', 'total', 'discards' and
        'event' — the last being the Cities & Knights event die outcome, or
        None in the base game.
        """
        if self.game_phase == "setup":
            return _refused('WRONG_PHASE', 'Cannot roll dice during setup phase')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return _refused('NOT_YOUR_TURN', f'Only {current_name} can roll dice')

        if self.has_rolled_dice:
            return _refused('ALREADY_ROLLED', 'You have already rolled this turn')

        # Rolled through the game's own generator so a test can script the
        # sequence and so production uses a source that cannot be reconstructed
        # from observed outcomes.
        dice1 = self.rng.randint(1, 6)
        dice2 = self.rng.randint(1, 6)
        total = dice1 + dice2

        self.set_dice_rolled()

        # Cities & Knights rolls a third die, and it is resolved *before*
        # production. Without this the barbarian ship never moves and knights
        # have nothing to defend against.
        event = self._resolve_event_die(dice2) if self.ck else None

        if total == 7:
            # C&K: until the barbarians have attacked once, a 7 does not move
            # the robber — but the discard rule still applies.
            if not self.ck or self.ck.barbarians_have_attacked:
                self.must_move_robber = True
            self.check_discard_required()

        # A 7 produces nothing; distribute_resources knows that itself.
        self.distribute_resources(total)

        return {
            'success': True,
            'error': '',
            'dice1': dice1,
            'dice2': dice2,
            'total': total,
            'event': event,
            'discards': dict(self.players_needing_discard),
        }

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

    def get_dice_roll_time_remaining(self) -> int:
        """Get seconds remaining for dice roll."""
        import time

        if self.turn_start_time is None or self.has_rolled_dice:
            return self.dice_roll_time_limit
        elapsed = time.time() - self.turn_start_time
        return max(0, self.dice_roll_time_limit - int(elapsed))

    def get_round_time_remaining(self) -> int:
        """Get seconds remaining for round (starts after dice roll)."""
        import time

        if self.turn_start_time is None:
            return self.round_time_limit
        # If dice not rolled yet, return full time (will be shown as "-")
        if not self.has_rolled_dice:
            return self.round_time_limit
        # Calculate from dice roll time
        if self.dice_rolled_time is None:
            return self.round_time_limit
        elapsed = time.time() - self.dice_rolled_time
        return max(0, self.round_time_limit - int(elapsed))

    def is_dice_roll_expired(self) -> bool:
        """Check if dice roll time has expired."""
        if self.has_rolled_dice:
            return False
        return self.get_dice_roll_time_remaining() <= 0

    def is_round_expired(self) -> bool:
        """Check if round time has expired."""
        return self.get_round_time_remaining() <= 0

    def set_dice_rolled(self):
        """Mark that dice has been rolled."""
        import time

        self.has_rolled_dice = True
        self.dice_rolled_time = time.time()

    def calculate_longest_road(self, player_name: str) -> int:
        """Calculate longest road for a player, respecting road blocks."""
        player = self.get_player(player_name)
        if not player:
            return 0

        player_roads = [
            edge_key
            for edge_key, edge in self.edges.items()
            if edge.road and edge.road.get('player') == player_name
        ]

        if not player_roads:
            return 0

        def has_other_player_building(vertex_key):
            """Check if vertex has another player's building."""
            vertex = self.vertices.get(vertex_key)
            if vertex and vertex.building:
                building_player = vertex.building.get('player')
                if building_player and building_player != player_name:
                    return True
            return False

        def find_road_endpoints():
            """Find vertices that are endpoints of player's roads (have exactly 1 road connected).
            Also filter out vertices blocked by other player's buildings."""
            vertex_road_count = {}
            for edge_key in player_roads:
                edge = self.edges[edge_key]
                for vertex_key in edge.neighbors.get('vertices', []):
                    vertex_road_count[vertex_key] = vertex_road_count.get(vertex_key, 0) + 1

            # Endpoints have exactly 1 road AND no other player's building at the start
            return [
                v
                for v, count in vertex_road_count.items()
                if count == 1 and not has_other_player_building(v)
            ]

        def dfs(vertex_key, visited_edges):
            """DFS to find longest path from current vertex."""
            max_length = len(visited_edges)

            # Get all connected edges
            vertex = self.vertices.get(vertex_key)
            if not vertex:
                return max_length

            for edge_key in vertex.neighbors.get('edges', []):
                if edge_key in visited_edges:
                    continue

                # Check if this is player's road
                edge = self.edges.get(edge_key)
                if not edge or not edge.road or edge.road.get('player') != player_name:
                    continue

                # Find the next vertex
                edge_vertices = edge.neighbors.get('vertices', [])
                next_vertex = None
                for v in edge_vertices:
                    if v != vertex_key:
                        next_vertex = v
                        break

                if not next_vertex:
                    continue

                # Check if blocked by other player's building at the next vertex
                if has_other_player_building(next_vertex):
                    # Blocked - can't pass through another player's building
                    # But can count the road leading TO it
                    max_length = max(max_length, len(visited_edges) + 1)
                    continue

                # Continue through empty vertices or player's own buildings
                result = dfs(next_vertex, visited_edges + [edge_key])
                max_length = max(max_length, result)

            return max_length

        # Find longest path from each valid endpoint
        endpoints = find_road_endpoints()

        # If no valid endpoints (all blocked), try finding any starting point
        if not endpoints:
            for edge_key in player_roads:
                edge = self.edges[edge_key]
                for v in edge.neighbors.get('vertices', []):
                    if not has_other_player_building(v):
                        endpoints.append(v)
                        break
                if endpoints:
                    break

        max_length = 0
        for endpoint in endpoints:
            length = dfs(endpoint, [])
            max_length = max(max_length, length)

        return max_length

    def update_longest_road(self):
        """Update longest road holder after road placement."""
        max_length = 0
        longest_holder = None

        for player in self.players:
            length = self.calculate_longest_road(player.name)
            self.longest_road_length[player.name] = length

            if length > max_length:
                max_length = length
                longest_holder = player.name

        # Only update once someone reaches the minimum (5 in the base game)
        if max_length >= self.rules['longest_road_minimum']:
            if self.longest_road_holder != longest_holder:
                old_holder = self.longest_road_holder
                self.longest_road_holder = longest_holder
                if longest_holder:
                    logger.debug(
                        "Longest Road! %s now has %s roads (took from %s)",
                        longest_holder, max_length, old_holder
                    )

    def update_largest_army(self):
        """Update largest army holder after playing knight."""
        max_knights = 0
        army_holder = None

        for player in self.players:
            knights = player.knights_played
            self.knights_played[player.name] = knights

            if knights > max_knights:
                max_knights = knights
                army_holder = player.name

        # Only update once someone reaches the minimum (3 in the base game)
        if max_knights >= self.rules['largest_army_minimum']:
            if self.largest_army_holder != army_holder:
                old_holder = self.largest_army_holder
                self.largest_army_holder = army_holder
                if army_holder:
                    logger.debug(
                        "Largest Army! %s now has %s knights (took from %s)",
                        army_holder, max_knights, old_holder
                    )
