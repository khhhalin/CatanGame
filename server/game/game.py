import json
import logging
import os
import random

from game import cities_knights as ck_module
from game import modifiers as modifiers_module
from game import rules as rules_module
from game.bank import Bank
from game.board import BoardBuilder
from game.cities_knights_rules import CitiesKnightsRules
from game.dev_card_rules import DevCardRules
from game.pending_choice import PendingChoiceRules
from game.player import Player
from game.results import refused
from game.robber_rules import RobberRules
from game.seafarers import SeafarersRules
from game.trade import TradeManager
from game.trade_rules import TradeRules
from game.turn_clock import TurnClock

logger = logging.getLogger(__name__)

class Game(BoardBuilder, TradeRules, RobberRules, SeafarersRules, DevCardRules,
           CitiesKnightsRules, PendingChoiceRules, TurnClock):
    """
    Represents a Catan game session.

    Manages players, turn order, game state, and the board layout.
    The board is generated using a cube coordinate system (see hex.md).

    Attributes:
        players (list): List of Player objects in turn order.
        observers (list): List of observer names.
        current_player_index (int): Index of current player in players list.
        game_state (str): "waiting" or "started".
        board_layout (dict): The selected map from `board.LAYOUTS` — which
                             tiles the island is made of and what the box holds
                             for a board that size.
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
    MAX_SHIPS = 15

    def __init__(
        self,
        player_names: list,
        observers: list,
        player_colors: dict = None,
        rng: random.Random = None,
        config=None,
        rules: dict = None,
        map_definition=None,
    ):
        # Injected so tests can replay a game exactly; production passes nothing
        # and gets a real, non-reconstructable source.
        self.rng = rng or random.SystemRandom()

        # A parsed map file, or None for one of the built-in layouts. Held on
        # the game rather than looked up by id, because the file on disk can be
        # edited or deleted while this game is being played and the board would
        # then no longer be the one anybody agreed to.
        self.map_definition = map_definition

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

        # Robber
        self.robber_hex = None  # Hex key where robber is located
        # Seafarers. The pirate starts beside the board rather than on it, and
        # enters play the first time somebody moves it.
        self.pirate_hex = None
        self.ship_moved_this_turn = False
        # Which islands each player has a building on, and what the special
        # points for reaching a new one have added up to.
        self.player_islands = {}
        self.island_points = {}
        self.must_move_robber = False  # Set to true when 7 is rolled
        self.must_choose_victim = False  # Set to true when need to pick victim
        self.robber_victims = []  # List of players with settlements near robber hex

        # Discard half mechanic
        self.players_needing_discard = {}  # player_name -> amount to discard

        # Timer settings (in seconds)
        self.dice_roll_time_limit = getattr(config, 'DICE_ROLL_SECONDS', 15)
        self.round_time_limit = getattr(config, 'ROUND_SECONDS', 120)
        # How long a player has to answer a pending choice before the server
        # answers it for them. Shorter than a round: the whole table is frozen
        # while one player decides, and often it is not even their turn.
        self.choice_time_limit = getattr(config, 'CHOICE_SECONDS', 30)

        # Decisions the engine has stopped to ask for — see
        # `game/pending_choice.py`. Each entry names the kind of decision, the
        # player who owes it and the options they may pick from.
        self.pending_choices = []

        # Which house rules changed a production value while the last roll was
        # resolved. A player who collects 1 where they expected 2 is otherwise
        # told nothing, and reports it as a bug — the C&K starting commodity
        # was reported exactly that way.
        self.production_modifiers = set()

        # Exactly what the table set, and nothing else. Rules that suit a
        # different length say so in the catalogue (`suggests_victory_target`)
        # and the preset that ticks them sets it, so the lobby can see and
        # change the number. Adding to it here instead rewrote an explicit
        # choice — a table that asked for 10 got 11, or 13, with no clue why.
        self.victory_points_to_win = self.rules['victory_target']

        # Harbormaster: holder of the special card, or None.
        self.harbormaster_holder = None
        self.harbor_points = {}  # player name -> harbour points

        # Piece supplies, overridable from the lobby.
        self.MAX_SETTLEMENTS = self.rules['max_settlements']
        self.MAX_CITIES = self.rules['max_cities']
        self.MAX_ROADS = self.rules['max_roads']
        self.MAX_SHIPS = self.rules['max_ships']

        # Somewhere to keep improvement tracks, knights, walls, the barbarian
        # ship and the progress decks — built when any rule needs it. Its
        # presence is not a rule: what actually happens is decided by the
        # individual rule that governs it.
        self.ck = None
        if rules_module.needs_expansion_state(self.rules):
            self.ck = ck_module.CitiesKnights(
                barbarian_track_length=self.rules['barbarian_track_length'],
                progress_hand_limit=self.rules['progress_hand_limit'],
                max_city_walls=self.rules['max_city_walls'],
            )
            for player in self.players:
                self.ck.register(player.name)
        # What is left of the shuffled dice deck, when the table plays with
        # one. Empty means the next roll deals a fresh 36.
        self.dice_deck = []
        # The two production faces an Alchemist has already decided, or None.
        self.pending_dice = None

        # The merchant piece: which land hex it stands on and who put it there.
        # Only a Merchant progress card ever moves it.
        self.merchant_hex = None
        self.merchant_holder = None

        # Merchant Fleet: {player: [card types they trade at 2:1 with the bank
        # until their turn ends]}. Keyed by player because the rate is one
        # player's, not the table's — a single "chosen type" field would hand
        # the discount to whoever traded next.
        self.merchant_fleet_types = {}

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
        # The hexes a custom map calls its main land; None means "all of it",
        # which is every built-in layout.
        self.main_hex_keys = None

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
        if piece == 'ship':
            return len(player.ships) < self.MAX_SHIPS
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
            if len(player.ships) > self.MAX_SHIPS:
                problems.append(f"{player.name} has {len(player.ships)} ships")

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

        With "start with a city" on, the second starting settlement is a city
        instead, so a player begins with one settlement and one city rather
        than two settlements. Everything else about setup is unchanged.
        """
        if self.rules['setup_second_city'] and self.setup_turn >= len(self.players):
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
        """Whether a road at this edge would touch the player's own network.

        A player's network is their roads *and* their buildings: the rulebook
        lets a road start at one of your own settlements or cities, and looking
        only for an adjacent road refused that placement outright.

        An opponent holds any intersection they have built on, so the network
        does not run through it — the base-game rule a knight is modelled on
        (expansions.md 389 for the knight). Without this the engine was
        inconsistent: a knight blocked a road and the settlement the rule is
        named after did not.
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return False
        for vertex_key in edge.neighbors.get('vertices', []):
            vertex = self.vertices.get(vertex_key)
            if vertex is None or self.knight_blocks(player_name, vertex_key):
                continue
            if vertex.building:
                # Their intersection, their block; yours is what a road starts
                # from. Either way the walk stops here.
                if vertex.building.get('player') != player_name:
                    continue
                return True
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
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        in_setup = self.game_phase == "setup"
        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can place buildings')

        # Setup alternates settlement then road. Without this check a player can
        # keep placing free settlements for the whole of their setup turn.
        if in_setup and self.setup_action != "settlement":
            return refused('WRONG_PHASE', 'You must place a road next')

        # In C&K setup the second placement is a city, so check that supply instead.
        building_type = self.setup_building_type() if in_setup else 'settlement'
        if not self.has_piece_available(player_name, building_type):
            limit = self.MAX_CITIES if building_type == 'city' else self.MAX_SETTLEMENTS
            return refused('NO_PIECES_LEFT', f'You have used all {limit} {building_type}s')

        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return refused('INVALID_TARGET', 'Invalid vertex')
        # With ships in play the graph reaches out over the water, so the
        # intersections a shipping route turns on exist as well. A building
        # belongs to the land, and a vertex lists land hexes only, so an
        # intersection touching none of them is out at sea.
        if not vertex.neighbors['hexes']:
            return refused('INVALID_PLACEMENT', 'A settlement must stand on the coast or inland')
        # The scenario setup restriction, when the table asked for it: you start
        # at home and sail to the far islands, rather than starting on one. Only
        # the *starting* settlements — nothing stops you settling there later,
        # which is the game this rule belongs to.
        if in_setup and self.rules['start_on_main_land'] and not any(
            self.is_main_land(hex_key) for hex_key in vertex.neighbors['hexes']
        ):
            return refused(
                'INVALID_PLACEMENT', 'Starting settlements go on the main land'
            )
        if vertex.building is not None:
            return refused('OCCUPIED', 'This location already has a building')
        if self.knight_holds(vertex_key):
            return refused('OCCUPIED', 'A knight is standing here')
        if not self._respects_distance_rule(vertex_key):
            return refused(
                'INVALID_PLACEMENT', 'Cannot place settlement next to another settlement'
            )

        if not in_setup:
            if not self._touches_own_route(player_name, vertex_key):
                return refused(
                    'INVALID_PLACEMENT',
                    'Settlement must be connected to your own road or shipping route'
                    if self.rules['ships']
                    else 'Settlement must be connected to your own road',
                )
            if not self.can_afford(player_name, 'settlement'):
                return refused('INSUFFICIENT_RESOURCES', self._cost_message('settlement'))
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
        # The islands a player starts on are theirs already, so setup records
        # them without scoring them.
        island_points = self.record_island_settlement(
            player_name, vertex_key, award=not in_setup
        )

        if in_setup:
            self.last_setup_settlement = vertex_key
        self.setup_action = "road" if in_setup else "settlement"

        return {
            'success': True,
            'error': '',
            'building_type': building_type,
            'island_points': island_points,
        }

    def build_road(self, player_name: str, edge_key: str) -> dict:
        """Build a road, free during setup and paid for afterwards.

        Returns {'success', 'error', 'code', 'used_free_road'} — a Two Roads
        card pays for the placement instead of the player's hand.
        """
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        in_setup = self.game_phase == "setup"
        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can place buildings')

        if in_setup and self.setup_action != "road":
            return refused('WRONG_PHASE', 'You must place a settlement first')

        if not self.has_piece_available(player_name, 'road'):
            return refused('NO_PIECES_LEFT', f'You have used all {self.MAX_ROADS} roads')

        edge = self.edges.get(edge_key)
        if edge is None:
            return refused('INVALID_TARGET', 'Invalid edge')
        if edge.road is not None:
            return refused('OCCUPIED', 'This location already has a road')
        # Roads and ships never share a hex side, and a road needs land under
        # it — with ships in play the board holds open-water sides too.
        if edge.ship is not None:
            return refused('OCCUPIED', 'This coastal side already carries a ship')
        if not self.land_hexes_of_edge(edge_key):
            return refused('INVALID_PLACEMENT', 'A road cannot be built out at sea')

        used_free_road = False
        if in_setup:
            # The setup road must touch the settlement just placed. This is
            # unconditional — guarding it on last_setup_settlement being set
            # meant a road emitted before any settlement could land anywhere.
            if not self.last_setup_settlement:
                return refused('WRONG_PHASE', 'You must place a settlement first')
            if self.last_setup_settlement not in edge.neighbors.get('vertices', []):
                return refused('INVALID_PLACEMENT', 'Road must be connected to your settlement')
        else:
            if not self._road_connects(player_name, edge_key):
                return refused('INVALID_PLACEMENT', 'Road must be connected to your own road')
            if self.free_roads_remaining > 0:
                self.free_roads_remaining -= 1
                used_free_road = True
            elif not self.can_afford(player_name, 'road'):
                return refused('INSUFFICIENT_RESOURCES', self._cost_message('road'))
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
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot upgrade to city during setup phase')

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can upgrade buildings')

        if not self.has_piece_available(player_name, 'city'):
            return refused('NO_PIECES_LEFT', f'You have used all {self.MAX_CITIES} cities')

        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return refused('INVALID_TARGET', 'Invalid vertex')
        if vertex.building is None:
            return refused('INVALID_TARGET', 'No building at this location')
        if vertex.building.get('type') != 'settlement':
            return refused('INVALID_TARGET', 'Can only upgrade settlements to cities')
        if vertex.building.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'Can only upgrade your own settlements')

        if not self.can_afford(player_name, 'city'):
            return refused('INSUFFICIENT_RESOURCES', self._cost_message('city'))
        self.deduct_cost(player_name, 'city')

        vertex.building = {'type': 'city', 'player': player_name}

        player = self.get_player(player_name)
        if player and vertex_key in player.settlements:
            player.settlements.remove(vertex_key)
            player.cities.append(vertex_key)

        self.update_harbormaster()
        return {'success': True, 'error': ''}

    def _touches_own_road(self, player_name: str, vertex_key: str) -> bool:
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return False
        for edge_key in vertex.neighbors.get('edges', []):
            edge = self.edges.get(edge_key)
            if edge and edge.road and edge.road.get('player') == player_name:
                return True
        return False

    def _touches_own_route(self, player_name: str, vertex_key: str) -> bool:
        """Whether a building here would join this player's own network.

        Roads and ships both, because "a shipping route functions exactly like
        a road network for the purpose of expansion" and "when a player's
        shipping route reaches a coastline, that player may build a settlement
        on that coast even if it lies on a new island" — the rule the whole
        expansion exists for, and the only way a second island is ever settled.

        Knights keep to `_touches_own_road`: they march, they do not sail.
        """
        if self._touches_own_road(player_name, vertex_key):
            return True
        if not self.rules['ships']:
            return False

        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return False
        for edge_key in vertex.neighbors.get('edges', []):
            edge = self.edges.get(edge_key)
            if edge and edge.ship and edge.ship.get('player') == player_name:
                return True
        return False

    def victory_points_for(self, player_name: str) -> int:
        """A player's total, including anything the optional rules award.

        Single entry point so a new scoring rule is added in one place rather
        than in every handler that checks for a win.
        """
        player = self.get_player(player_name)
        if player is None:
            return 0

        points = player.get_victory_points(self.longest_road_holder, self.largest_army_holder)

        # A held Victory Point card is secret, so this total is deliberately
        # higher than the one every browser is shown: the card only becomes
        # public on the turn it wins the game.
        if self.rules['victory_point_cards_count_in_hand']:
            points += player.dev_cards['victory_point']['count']

        if self.rules['harbormaster'] and self.harbormaster_holder == player_name:
            points += 2

        # Special points sit under the settlement that earned them and are
        # never lost, so they are simply added to the owner's total.
        if self.rules['island_victory_points']:
            points += self.island_points.get(player_name, 0)

        # "The player controlling the merchant scores 1 victory point for as
        # long as they control it" — and control passes the moment somebody
        # else plays a Merchant card, so this is read rather than banked.
        if self.merchant_holder == player_name:
            points += 1

        if self.ck is not None:
            if self.rules['metropolis']:
                # A metropolis makes its city worth 4 instead of 2, so it adds
                # 2 on top of what the city already scored.
                points += 2 * self.ck.metropolis_count(player_name)
            if self.rules['barbarians']:
                points += self.ck.defender_cards.get(player_name, 0)

        return points

    def public_victory_points(self, player_name: str) -> int:
        """A player's total as the whole table is allowed to see it.

        `victory_points_for` is the authority on scoring, so the scoreboard has
        to come from it or the optional rules award points nobody can see. The
        one thing it knows that the table may not is a Victory Point card still
        in hand, which stays secret until it wins the game, so that part comes
        back off here.
        """
        player = self.get_player(player_name)
        if player is None:
            return 0

        points = self.victory_points_for(player_name)
        if self.rules['victory_point_cards_count_in_hand']:
            points -= player.dev_cards['victory_point']['count']
        return points

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
            edge_data = {
                'road': edge_obj.road,
                'ship': edge_obj.ship,
                # Whether a ship may lie here is a rule, not geometry: the
                # renderer needs it to draw the placement targets, and working
                # it out again in JavaScript is a second answer waiting to
                # disagree with this one. False on every side without ships.
                'sea': self.is_sea_edge(key),
                'neighbors': edge_obj.neighbors,
            }
            # A harbour belongs to this coastal edge; both of its intersections
            # also carry it, which is where the renderer still reads it from.
            if edge_obj.port:
                edge_data['port'] = edge_obj.port
            edges[key] = edge_data

        # Clean up expired trades
        self.trade_manager.cleanup_expired()

        # Build my_offers for each player
        my_offers = {}
        for player in self.players:
            my_offers[player.name] = self.trade_manager.get_my_offers(player.name)

        players = []
        for player in self.players:
            shown = player.to_dict(self.longest_road_holder, self.largest_army_holder, viewer)
            # A Player counts its own buildings and the two base-game cards and
            # knows nothing of the optional rules. The browser draws its
            # scoreboard from this number, so it has to be the public total.
            shown['victory_points'] = self.public_victory_points(player.name)
            players.append(shown)

        return {
            'hexes': hexes,
            'vertices': vertices,
            'edges': edges,
            'players': players,
            'bank': self.bank.get_all(),
            'rules': self.rules,
            'cities_knights': self.ck.to_dict(viewer) if self.ck else None,
            'harbormaster_holder': self.harbormaster_holder,
            'harbor_points': self.harbor_points,
            # Only the total: the per-type breakdown is the deck order, and
            # knowing what is left turns a probabilistic draw into a certain one.
            'dev_cards_remaining': self.bank.total_dev_cards_remaining(),
            # How many combinations are left in a dealt dice deck. A count and
            # never the contents: the order would turn a probabilistic draw
            # into a certain one, which is why dev_cards_remaining is a total
            # too. Zero when no deck is in play.
            'dice_deck_remaining': len(self.dice_deck),
            'state_version': self.state_version,
            'trades': {'active': self.trade_manager.get_all_active(), 'my_offers': my_offers},
            'game_phase': self.game_phase,
            'setup_action': self.setup_action,
            'current_player': self.players[self._get_setup_player_index()].name
            if self.game_phase == "setup"
            else self.players[self.current_player_index].name,
            'robber_hex': self.robber_hex,
            'merchant_hex': self.merchant_hex,
            'merchant_holder': self.merchant_holder,
            # Public: a 2:1 nobody can see is a 2:1 nobody uses, and the table
            # is entitled to know why a player is buying cheaply this turn.
            'merchant_fleet_types': self.merchant_fleet_types,
            # Filtered per recipient: only the player who owes a decision is
            # told what the options are, because they can be the contents of
            # somebody else's hand.
            'pending_choices': self.pending_choices_for_client(viewer),
            'pirate_hex': self.pirate_hex,
            'ship_moved_this_turn': self.ship_moved_this_turn,
            'island_points': self.island_points,
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

    def production_for(self, vertex, hex_obj, dice_total: int, robber_here: bool) -> dict:
        """What one building takes from one hex when that hex's number comes up.

        The single place production is decided: {'resources': how many cards of
        the hex's own type, 'commodity': its commodity or None}. A settlement
        takes one card, and every rule that changes that — the city's share,
        commodities, the robber — is a modifier folded over it in a fixed
        order. See `game/modifiers.py`.
        """
        value, changed = modifiers_module.apply_traced(
            modifiers_module.PRODUCTION,
            self.rules,
            {'resources': 1, 'commodity': None},
            building_type=vertex.building.get('type'),
            terrain=hex_obj.type,
            dice_total=dice_total,
            robber_here=robber_here,
        )
        # Remembered rather than returned, so every caller of production_for
        # keeps its signature: only the roll that collects the whole table's
        # production reads this, and it reads it once.
        self.production_modifiers.update(changed)
        return value

    def distribute_resources(self, dice_total: int) -> dict:
        """Distribute resources to players based on dice roll.

        Each settlement adjacent to a hex with matching number receives 1 resource.
        Skips distribution for 7 (robber not implemented).

        Args:
            dice_total: The sum of the two dice rolled

        Returns:
            dict: {player name: {card type: count}} — what this roll actually
            paid, commodities included. Empty when it paid nobody, which the
            log says out loud rather than leaving "did anything happen?"
            unanswerable.
        """
        # One roll's worth: cleared here so the set never carries a rule over
        # from the previous turn.
        self.production_modifiers = set()

        if dice_total == 7:
            return {}

        gained_resources = {}

        for _vertex_key, vertex in self.vertices.items():
            if not vertex.building or vertex.building.get('type') not in ('settlement', 'city'):
                continue

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
                if hex_obj.number != dice_total or hex_obj.type in ('desert', 'ocean'):
                    continue

                produced = self.production_for(
                    vertex, hex_obj, dice_total, hex_key == self.robber_hex
                )
                commodity = produced['commodity']

                for _ in range(produced['resources']):
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

        # Sorted on the way out: the walk visits vertices in dict order, and a
        # payload whose key order varies per process is exactly the kind of
        # thing a seeded replay is supposed to pin down.
        return {
            player_name: dict(sorted(cards.items()))
            for player_name, cards in sorted(gained_resources.items())
        }

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

                # The starting city yields "one resource and, where applicable,
                # one commodity" from each adjacent hex — one of each, not the
                # doubled production of a normal city turn.
                if self.rules['commodities'] and is_city:
                    commodity = ck_module.COMMODITY_FROM_TERRAIN.get(hex_obj.type)
                    if commodity:
                        player.commodities[commodity] = player.commodities.get(commodity, 0) + 1
                        gained[commodity] = gained.get(commodity, 0) + 1

        if gained:
            logger.debug(f"Starter resources for {player_name} from {vertex_key}: {gained}")

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
        """What this costs to build, once every active modifier has had its say.

        The one place a price is decided, so a rule that makes something
        cheaper has somewhere to attach. See `game/modifiers.py`.
        """
        return modifiers_module.apply(
            modifiers_module.COST,
            self.rules,
            dict(self.building_costs.get(building_type, {})),
            building_type=building_type,
        )

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

    def roll_dice(self, player_name: str) -> dict:
        """Roll for the current player, resolve the roll, and pay production.

        Returns the usual pair plus 'dice1', 'dice2', 'total', 'discards' and
        'event' — the last being the Cities & Knights event die outcome, or
        None in the base game.
        """
        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot roll dice during setup phase')

        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can roll dice')

        if self.has_rolled_dice:
            return refused('ALREADY_ROLLED', 'You have already rolled this turn')

        dice1, dice2 = self.next_dice()
        total = dice1 + dice2

        self.set_dice_rolled()

        # The barbarians bring a third die, and it is resolved *before*
        # production. Without this the barbarian ship never moves and knights
        # have nothing to defend against. The same die is what deals progress
        # cards, which is why they depend on this rule.
        event = self._resolve_event_die(dice2) if self.rules['barbarians'] else None

        if total == 7:
            # Two rules can hold the robber back, and both leave the discard
            # alone: the barbarians keep it off the board until their first
            # attack, and an opening grace keeps it off for the first rounds.
            barbarians_still_coming = (
                self.rules['barbarians'] and not self.ck.barbarians_have_attacked
            )
            if not barbarians_still_coming and not self.in_robber_free_opening():
                self.must_move_robber = True
            self.check_discard_required()

        # A 7 produces nothing; distribute_resources knows that itself.
        gained = self.distribute_resources(total)

        return {
            'success': True,
            'error': '',
            'dice1': dice1,
            'dice2': dice2,
            'total': total,
            'event': event,
            'discards': dict(self.players_needing_discard),
            # The house rules that changed what this roll paid, so the log can
            # say why. Sorted for a stable payload.
            'modifiers': sorted(self.production_modifiers),
            # Who the roll paid and in what. Empty means it paid nobody.
            'gained': gained,
        }

    def next_dice(self) -> tuple:
        """The two faces this roll produces.

        Rolled through the game's own generator so a test can script the
        sequence and so production uses a source that cannot be reconstructed
        from observed outcomes. With the dice deck in play the faces are dealt
        instead: every one of the 36 combinations comes out once before any of
        them comes out twice, which is what evens the production out.

        An Alchemist played before the roll has already decided both faces, and
        those are used once and then forgotten — including in place of a dealt
        pair, since the card overrules the deck for exactly one roll.

        A table playing with a dice set other than the standard pair draws from
        that set instead, dealt or rolled the same way.
        """
        if self.pending_dice is not None:
            chosen, self.pending_dice = self.pending_dice, None
            return chosen

        if self.rules['dice_deck']:
            if not self.dice_deck:
                self.dice_deck = list(self.dice_combinations())
                self.rng.shuffle(self.dice_deck)
            return tuple(self.dice_deck.pop())

        if not modifiers_module.active(modifiers_module.DICE, self.rules):
            # Two dice, rolled. Deliberately still two `randint` calls rather
            # than one draw from the 36: a seeded game has to reproduce the
            # sequence it has always produced.
            return self.rng.randint(1, 6), self.rng.randint(1, 6)

        return self.rng.choice(self.dice_combinations())

    def dice_combinations(self) -> tuple:
        """The face pairs the dice may show, after every dice modifier.

        Every combination of two six-sided dice, unless a modifier says
        otherwise — a dice set is a list of combinations, which is what lets a
        new one be data rather than another branch above.
        """
        return modifiers_module.apply(
            modifiers_module.DICE, self.rules, modifiers_module.STANDARD_DICE,
        )

    def in_robber_free_opening(self) -> bool:
        """Whether a 7 rolled now leaves the robber where it is.

        A round is one turn each, so the grace covers `rounds x players` turns.
        `turn_count` starts at 0 and rises once per completed turn, which makes
        it the count of turns already played.
        """
        rounds = self.rules['robber_free_opening_rounds']
        return self.turn_count < rounds * len(self.players)

    def route_pieces(self, player_name: str) -> dict:
        """The player's pieces a trade route can run along: edge key -> kind.

        Roads alone in the base game. With the Longest Trade Route in play,
        "both roads and ships count toward the length of a player's trade
        route", so the ships join them — and the kind is kept, because the two
        only chain together where their owner has a building.
        """
        pieces = {
            edge_key: 'road'
            for edge_key, edge in self.edges.items()
            if edge.road and edge.road.get('player') == player_name
        }
        if self.rules['longest_trade_route']:
            for edge_key, edge in self.edges.items():
                if edge.ship and edge.ship.get('player') == player_name:
                    pieces[edge_key] = 'ship'
        return pieces

    def calculate_longest_road(self, player_name: str) -> int:
        """The player's longest unbranched line of pieces, respecting blocks.

        Ships count alongside roads once the table plays the Longest Trade
        Route; `route_pieces` decides which pieces are in play, and this walk
        is otherwise the base game's.
        """
        player = self.get_player(player_name)
        if not player:
            return 0

        player_roads = self.route_pieces(player_name)

        if not player_roads:
            return 0

        def own_building(vertex_key):
            """Whether this player has a settlement or city here."""
            vertex = self.vertices.get(vertex_key)
            return bool(
                vertex and vertex.building and vertex.building.get('player') == player_name
            )

        def has_other_player_building(vertex_key):
            """Whether an opponent holds this intersection against the walk.

            A knight counts alongside a settlement or city: it "interrupts an
            opponent's longest road passing through it" (expansions.md 389).
            """
            if self.knight_blocks(player_name, vertex_key):
                return True
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

        def dfs(vertex_key, visited_edges, arrived_by=None):
            """DFS to find longest path from current vertex.

            `arrived_by` is the kind of piece the walk reached this
            intersection on. A road and a shipping route "only count as one
            continuous trade route if the player has a settlement or city at
            the intersection where the two meet", so changing kind here needs
            a building of the player's own.
            """
            max_length = len(visited_edges)

            # Get all connected edges
            vertex = self.vertices.get(vertex_key)
            if not vertex:
                return max_length

            for edge_key in vertex.neighbors.get('edges', []):
                if edge_key in visited_edges:
                    continue

                # Check if this is a piece of the player's own
                if edge_key not in player_roads:
                    continue
                edge = self.edges.get(edge_key)
                kind = player_roads[edge_key]
                if arrived_by is not None and kind != arrived_by and not own_building(vertex_key):
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
                result = dfs(next_vertex, visited_edges + [edge_key], kind)
                max_length = max(max_length, result)

            return max_length

        # Find longest path from each valid endpoint
        endpoints = find_road_endpoints()

        # If no valid endpoints (all blocked), try finding any starting point
        if not endpoints:
            for edge_key in sorted(player_roads):
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
        """Work out who holds the Longest Road, or the Longest Trade Route.

        The Seafarers card replaces the base-game one rather than joining it,
        so the table playing trade routes is enough on its own to award it.
        """
        if not self.rules['longest_road_card'] and not self.rules['longest_trade_route']:
            return

        for player in self.players:
            self.longest_road_length[player.name] = self.calculate_longest_road(player.name)

        max_length = max(
            (self.longest_road_length[player.name] for player in self.players), default=0
        )
        # A tie leaves the card where it is: only a route strictly longer than
        # the holder's takes it off them. Seating order decided it before, so
        # the player earlier in the turn order took the two points off the
        # player who had earned them.
        if self.longest_road_length.get(self.longest_road_holder, 0) == max_length:
            longest_holder = self.longest_road_holder
        else:
            longest_holder = next(
                player.name for player in self.players
                if self.longest_road_length[player.name] == max_length
            )

        # Nobody holds the card below the minimum (5 in the base game). That
        # includes the current holder: an opponent's settlement can break their
        # road, and the card has to go back rather than stay with a player whose
        # longest road no longer qualifies.
        if max_length < self.rules['longest_road_minimum']:
            longest_holder = None

        if self.longest_road_holder != longest_holder:
            old_holder = self.longest_road_holder
            self.longest_road_holder = longest_holder
            logger.debug(
                "Longest Road! %s now has %s roads (took from %s)",
                longest_holder, max_length, old_holder
            )

    def update_largest_army(self):
        """Update largest army holder after playing knight."""
        if not self.rules['largest_army_card']:
            return

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
