import logging
import random

from game import buildings, resources, tiles, validation
from game import cities_knights as ck_module
from game import ep as ep_module
from game import modifiers as modifiers_module
from game import rules as rules_module
from game import tb as tb_module
from game.bank import Bank
from game.barbarian_attack import BarbarianAttackRules
from game.board import BoardBuilder
from game.caravans import CaravansRules
from game.cargo import CargoRules
from game.cities_knights_rules import CitiesKnightsRules
from game.cloth_for_catan import CLOTH_GENERAL_SUPPLY, ClothForCatanRules
from game.coast_gifts import CoastGiftRules
from game.dev_card_rules import DevCardRules
from game.ep_pirate import EpPirateRules
from game.exploration import ExplorationRules
from game.favours import FavourRules
from game.fishing import FishingRules
from game.gold import GoldRules
from game.harbor_settlements import HarborSettlementRules
from game.helpers import HelpersRules
from game.inkas import InkasRules
from game.missions import MissionRules
from game.missions_fish import MissionFishRules
from game.missions_lairs import MissionLairsRules
from game.missions_spices import MissionSpicesRules
from game.neutral_players import NeutralPlayersRules
from game.new_energies import NewEnergiesRules
from game.oil_springs import OIL_SUPPLY, OilSpringsRules
from game.path_barbarians import PathBarbarianRules
from game.pending_choice import PendingChoiceRules
from game.pirate_islands import PirateIslandsRules
from game.player import Player
from game.results import refused
from game.rivers import RiversRules
from game.robber_rules import RobberRules
from game.seafarers import SeafarersRules
from game.tb_gold import TBGoldRules
from game.trade import TradeManager
from game.trade_rules import TradeRules
from game.trade_tokens import TradeTokenRules
from game.transport import TransportShipRules
from game.turn_clock import TurnClock
from game.volcano import VolcanoRules
from game.wagons import WagonRules
from game.wonders import WonderRules

logger = logging.getLogger(__name__)

class Game(BoardBuilder, TradeRules, RobberRules, SeafarersRules, DevCardRules,
           CitiesKnightsRules, GoldRules, HarborSettlementRules, TransportShipRules,
           CargoRules, EpPirateRules, ExplorationRules, MissionRules,
           MissionLairsRules, MissionFishRules, MissionSpicesRules,
           FishingRules, TBGoldRules, RiversRules, CaravansRules,
           BarbarianAttackRules, WagonRules, PathBarbarianRules,
           CoastGiftRules, ClothForCatanRules, WonderRules,
           PirateIslandsRules, HelpersRules, OilSpringsRules, VolcanoRules,
           InkasRules, FavourRules, NeutralPlayersRules, TradeTokenRules,
           NewEnergiesRules, PendingChoiceRules, TurnClock):
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

    # A colour per seat, for a player who never picked one. Six of them, in
    # seating order: the last two are the 5-6 Player Extension's own green and
    # brown, because a fifth player used to fall through to white and a sixth
    # sat in the same white beside them. Ink on these comes from the WCAG
    # `getContrastColor` in static/js/contrast.js, and every one of them clears
    # AA against the better of black and white.
    PLAYER_COLORS = ['#e74c3c', '#3498db', '#f39c12', '#9b59b6',
                     '#27ae60', '#8e5a2b']

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
            # No starting resources - players get resources from dice rolls.
            # Gold is the exception: every Explorers & Pirates scenario seeds
            # each purse (rules['starting_gold'], set to 2 by the E&P preset). A
            # base game leaves it at 0, so this is a no-op there.
            player.gold = self.rules['starting_gold']
            self.players.append(player)

        self.observers = observers
        self.current_player_index = 0
        self.game_state = "waiting"

        # Setup phase variables
        self.game_phase = "setup"  # "setup" or "playing"
        self.setup_turn = 0  # two placements per seat, out and back
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
        # The Pirate Islands: a fortress may be attacked only once a turn (p. 22).
        self.fortress_attacked_this_turn = False
        # Which islands each player has a building on, and what the special
        # points for reaching a new one have added up to.
        self.player_islands = {}
        self.island_points = {}
        # The Forgotten Tribe. The marked gift coast edges read off the map
        # (edge key -> {'gift', 'port'}), which of them have been claimed, the
        # barren small islands the gift edges border, the 1-VP chits each player
        # has claimed, and the harbours a player is holding until they can place
        # one. All empty off the Forgotten Tribe board.
        self.gift_edges = {}
        self.claimed_gift_edges = set()
        self.barren_island_hexes = set()
        self.gift_points = {}
        self.held_gift_harbors = {}
        # Cloth for Catan: each village's number and its remaining bolts of
        # cloth, the players who have established trade relations with each (so a
        # connection pays its opening bolt only once), each player's banked
        # bolts, and the general supply a short village draws its shortfall from.
        self.village_number = {}
        self.village_cloth = {}
        self.village_traders = {}
        self.cloth_tokens = {}
        self.cloth_general_supply = CLOTH_GENERAL_SUPPLY
        # Rise of the Inkas: the player who owes a free founding settlement after
        # sending a tribe into decline, or None. Per-player tribe number and
        # culture markers live on the Player; this is the one piece of turn state
        # the placement handlers gate on. None off the scenario.
        self.founding_player = None
        # Catan: Oil Springs. The oil-spring hexes read off the dealt board, the
        # general oil supply (15 tokens for 3-4 players), the shared disaster
        # track (0-5, advanced as oil is used), how many number tokens pollution
        # has removed (the board dies at 5), each player's total sequestered oil
        # and who holds the Champion of the Environment token, and the cities
        # upgraded into metropolises (vertex -> owner). All map-derived or
        # play-derived, so a save keeps only what play changed.
        self.oil_spring_hexes = set()
        self.oil_supply = OIL_SUPPLY
        self.disaster_track = 0
        self.oil_numbers_removed = 0
        self.oil_sequestered = {}
        self.oil_champion = None
        self.oil_metropolises = {}
        # CATAN: New Energies. The power plants on the board, keyed by the
        # (building vertex, hex) cutout they face -> {'player', 'kind'}; the
        # hexes carrying a hazard token (event chunk), which block production and
        # energy; and the per-turn flag that one plant has been built (a
        # triggered event may build one on top of it). All empty off the
        # scenario, so a base game is unchanged.
        self.power_plants = {}
        self.hazard_hexes = set()
        self.power_plant_built_this_turn = False
        self.fossil_demolished_this_turn = False
        # The event-disc bag (a flat list of disc-type strings) and each player's
        # face-down stack of green discs, dealt under their renewable-plant spaces
        # and fed into the bag as those plants are built. `event_phase_done` is
        # the per-turn flag that this turn's discs have been drawn. All empty off
        # the scenario.
        self.event_bag = []
        self.green_discs = {}
        self.event_phase_done = False
        # Seafarers, the Krakatoa/Volcano variant: the volcano hexes read off the
        # dealt board. Map-derived, so a save re-reads them; empty off the rule.
        self.volcano_hexes = set()
        # Per-turn: how much oil this turn's player has used, and whether they
        # have sequestered, reset each turn. Using oil and sequestering are
        # mutually exclusive within a turn (p. 2).
        self.oil_used_this_turn = 0
        self.oil_sequestered_this_turn = False
        # Catan: Frenemies. The face-down favour-token bag (dealt once the RNG
        # exists, below), each player's usable and locked holdings (a token drawn
        # on your own turn is locked until your next one), the Victory-Point
        # markers taken from the guild and the 8-marker supply, the network
        # connections already rewarded (a set of {builder, opponent} pairs, so a
        # first-time join pays once), and the per-turn flag that a resource has
        # been gifted. All empty or full off the scenario.
        self.favour_bag = []
        self.favour_usable = {}
        self.favour_locked = {}
        self.favour_vp_markers = {}
        self.favour_vp_supply = 0
        self.favour_connections = set()
        self.favour_gift_made_this_turn = False
        # Per-turn: a table redeems or exchanges favours, never both, and only
        # one exchange a turn (p. 2). Rebuilt by start_turn like the gift flag.
        self.favour_redeemed_this_turn = False
        self.favour_exchanged_this_turn = False
        # The Wonders of Catan: which Wonder each player has started (player ->
        # wonder id) and how many of its four levels they have finished (player ->
        # level), and the marked intersections read off the map — the strait
        # squares the Great Bridge is built against and the wasteland squares the
        # Great Wall is. All empty off the Wonders board.
        self.wonder_choice = {}
        self.wonder_level = {}
        self.wonder_strait = set()
        self.wonder_wasteland = set()
        # The Pirate Islands: the fleet's track (ordered sea-hex keys) and where it
        # sits on it, the four fortresses (vertex -> {index, owner, chits,
        # captured}) read off the map, and each player's warship count. All empty
        # off the Pirate Islands board.
        self.pirate_fleet_track = []
        self.pirate_fleet_index = 0
        self.pirate_fortresses = {}
        self.player_warships = {}
        # CATAN - The Helpers: the face-up display the tiles are drawn from, the
        # one tile each player holds (name -> {tile, side, received_turn}) and
        # the per-turn record of who has already used their helper. All empty off
        # the scenario. The pile is dealt once the board's RNG exists (below).
        self.helper_pile = []
        self.helper_held = {}
        self.helper_used_this_turn = set()
        # What the last production roll paid and what it totalled, so the helper
        # tiles that react to a roll (resource compensation, protection from the
        # 7, take from leader) can tell an empty roll from a 7. Reset to None at
        # the top of every turn; `last_roll_gains` is {player: {card: count}}.
        self.last_roll_total = None
        self.last_roll_gains = {}
        self.must_move_robber = False  # Set to true when 7 is rolled
        self.must_choose_victim = False  # Set to true when need to pick victim
        self.robber_victims = []  # List of players with settlements near robber hex

        # Discard half mechanic
        self.players_needing_discard = {}  # player_name -> amount to discard

        # One clock per phase of a turn, in seconds. The table sets them in the
        # lobby; a rule left at 0 means "whatever this server is configured
        # with", which is how a deployment keeps its own defaults and how a
        # test run keeps its one-second clocks.
        self.dice_roll_time_limit = self._timer_limit('dice_timer_seconds',
                                                      config, 'DICE_ROLL_SECONDS', 15)
        self.discard_time_limit = self._timer_limit('discard_timer_seconds',
                                                    config, 'DISCARD_SECONDS', 60)
        self.robber_time_limit = self._timer_limit('robber_timer_seconds',
                                                   config, 'ROBBER_SECONDS', 60)
        self.round_time_limit = self._timer_limit('turn_timer_seconds',
                                                  config, 'ROUND_SECONDS', 120)
        # How long a player has to answer a pending choice before the server
        # answers it for them. Shorter than a round: the whole table is frozen
        # while one player decides, and often it is not even their turn.
        self.choice_time_limit = self._timer_limit('choice_timer_seconds',
                                                   config, 'CHOICE_SECONDS', 30)

        # Which clock is running and when it started. Both are worked out from
        # the game's own state on demand (see `TurnClock.timer_phase`), so a
        # rule that opens a discard or a robber move does not have to remember
        # to start a clock for it.
        self.clock_phase = None
        self.clock_started_time = None

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
        self.MAX_HARBOR_SETTLEMENTS = self.rules['max_harbor_settlements']
        self.MAX_SETTLERS = self.rules['max_settlers']
        self.MAX_CREWS = self.rules['max_crews']

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

        # The Explorers & Pirates equivalent: pirate hexes, mission tracks, the
        # pool of undiscovered tiles and the token supplies, built only when a
        # rule needs it. Like `self.ck`, its presence is not a rule.
        self.ep = None
        if rules_module.needs_ep_state(self.rules):
            self.ep = ep_module.EP()
            for player in self.players:
                self.ep.register(player.name)
            # Each active mission declares its track now the container exists.
            self.setup_pirate_lairs()
            self.setup_fish()
            self.setup_spices()

        # The Traders & Barbarians (Fishermen) equivalent: the fish-token supply,
        # each player's private fish hand, and the old boot. Built only when a
        # rule needs it; its presence is not a rule. The fishing grounds and the
        # lake are read off the board in `setup_fishing_board` once it is dealt.
        self.tb = None
        if rules_module.needs_tb_state(self.rules):
            self.tb = tb_module.TB(rng=self.rng)
            self.tb.seed_supply()
            for player in self.players:
                self.tb.register(player.name)

        # How many times each player has converted at the gold supply this turn
        # (player -> {'sells', 'buys'}), reset in start_turn. Both conversions
        # are capped per turn — see game/gold.py.
        self.gold_conversions = {}
        # Transport ships get a per-game id so a ship is still the same ship
        # after it sails to another edge, and the set of ids that have already
        # moved this turn enforces one move per ship per turn. Both are E&P
        # transport state and never touch a Seafarers ship. See game/transport.py.
        self.transport_ship_counter = 0
        self.transport_ships_moved = set()
        # E&P fixes the turn order production -> trade/build -> movement, and
        # moving a ship is the point of no return: nothing may be built or
        # traded after it (expansions.md 851-862). The phase only matters when
        # `movement_phase` is on; `start_turn` resets it every turn. Like the
        # other per-turn E&P state, it is transient and not persisted.
        self.turn_phase = 'production'
        # What the last production roll paid in gold (player -> amount), the way
        # `production_modifiers` records which rules changed a roll. Read once by
        # the roll payload, cleared at the top of every distribution.
        self.gold_gained = {}
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

        # Flat build prices, read from the building registry (name/cost/icon in
        # one place — see game/buildings.py). The engine prices by build id, so
        # this is the registry's cost view, keyed the same way the old
        # data/costs.json was.
        self.building_costs = {
            build_type: dict(definition['cost'])
            for build_type, definition in buildings.registry().items()
        }

        # Board data structures
        self.hexes = {}  # key -> Hex object
        self.vertices = {}  # key -> Vertex object
        self.edges = {}  # key -> Edge object
        # The hexes a custom map calls its main land; None means "all of it",
        # which is every built-in layout.
        self.main_hex_keys = None

        # The Rivers of Catan river-crossing bridge sites: the edge keys a bridge
        # may span and a normal road may never sit on. Read off the dealt map in
        # `setup_rivers_board`; empty on every board that prints none, so the base
        # game is untouched.
        self.bridge_sites = set()

        # The Caravans oasis and its three arrow paths — the hex the camels grow
        # out of and the edges each caravan starts on. Read off the dealt map in
        # `setup_caravans_board`; empty on every board that prints no oasis, so
        # the base game is untouched. `camel_owed` is the per-turn flag that a
        # settlement was built or upgraded and a camel is due at turn's end.
        self.oasis_hex = None
        self.oasis_arrows = []
        self.camel_owed = False

        # The Traders & Barbarians main scenario. The trade-hex plazas (where a
        # wagon delivers, and where no building may stand) and their sea-border
        # paths (where no road may sit) are derived off the dealt board in
        # `setup_wagons_board`; both empty for a board that prints no trade hex,
        # so the base game is untouched. `must_move_barbarian` names the player
        # who owes a roaming-barbarian move after rolling a 7, or None.
        self.trade_plazas = set()
        self.trade_sea_paths = set()
        self.must_move_barbarian = None
        # Per-turn wagon state, reset in `start_turn` beside the other per-turn
        # counters: the movement points left this turn (lazily set on first move),
        # whether the grain boost has been bought, and which barbarians a
        # drive-off has already been tried on.
        self.wagon_points_left = None
        self.wagon_grain_used = False
        self.barbarians_driven = set()
        # Whether a Swift Journey card has opened its distinct second wagon
        # movement this turn (expansions.md 747). Kept apart from the base
        # movement so its fresh point allocation never merges with a base
        # remainder; reset in `start_turn` like the rest of the per-turn state.
        self.wagon_swift_journey = False

        # Generate the complete board
        self._generate_board()

        # Now the terrain is dealt, open a bank pool for every resource the board
        # can pay. A standard board produces only the base five and its bank
        # keeps exactly those; a map that deals cotton hexes gets a cotton pile
        # too, so a cotton roll has somewhere to draw from and a cotton trade
        # somewhere to settle. The pile appears where the board earns it and
        # nowhere else — a base game never shows one.
        self.bank.stock_for_board(self.producible_resources())

        # Explorers & Pirates: fill the undiscovered pool and the per-area
        # number-token stacks a discovery draws from, now the board's hidden
        # tiles exist. A no-op without the exploration rule.
        self._seed_exploration_pool()

        # Traders & Barbarians (Fishermen): read the fishing grounds and the lake
        # off the dealt board into TB state. A no-op without the fishing rules.
        self.setup_fishing_board()

        # Traders & Barbarians (Rivers): read the map's river-crossing bridge
        # sites into `self.bridge_sites`. A no-op for a board that prints none.
        self.setup_rivers_board()

        # The Forgotten Tribe: read the map's marked gift coast edges and the
        # barren islands they border. A no-op for a board that prints none.
        self.setup_coast_gifts_board()

        # Cloth for Catan: read the map's villages and the barren islands they
        # sit on into cloth state. A no-op for a board that prints no villages.
        self.setup_cloth_villages()

        # Catan: Oil Springs: read the map's oil-spring hexes off the dealt
        # board. A no-op for a board that prints none.
        self.setup_oil_springs()

        # CATAN: New Energies: fill the event-disc bag with the 43 brown discs
        # and deal each player their nine green discs. A no-op off the rule.
        self.setup_event_discs()

        # Seafarers, the Krakatoa/Volcano variant: read the map's volcano hexes
        # off the dealt board. A no-op for a board that prints none.
        self.setup_volcano_hexes()

        # The Wonders of Catan: read the map's marked strait and wasteland
        # intersections. A no-op for a board that prints no markers.
        self.setup_wonders_board()

        # The Pirate Islands: read the map's fleet track and the four fortresses,
        # and hand each fortress to a player in seat order. A no-op for a board
        # that prints no fleet.
        self.setup_pirate_islands()

        # Traders & Barbarians (Caravans): read the oasis and its arrow paths off
        # the dealt board. A no-op for a board that prints no oasis.
        self.setup_caravans_board()

        # CATAN - The Helpers: shuffle the enabled advantages' tiles into the
        # display. Needs no board of its own, only the RNG and the chosen rules.
        # A no-op unless the helper subsystem is on.
        if self.helpers_in_play():
            self.setup_helper_pile()

        # Catan: Frenemies: shuffle the 58-token favour bag. Needs no board of
        # its own, only the RNG and the chosen rules. A no-op off the scenario.
        self.setup_favours()

        # Traders & Barbarians (Barbarian Attack): read the castle, the coast and
        # the un-conquerable hexes off the dealt board, seed the opening two
        # barbarians and shuffle the scenario deck. A no-op for a board that
        # prints no castle, so the base game is untouched.
        self.setup_barbarian_board()

        # Traders & Barbarians (main scenario): read the three trade hexes and
        # the roaming-barbarian paths off the dealt board, build the commodity
        # stacks and deal the scenario deck. A no-op for a board that prints no
        # trade hex, so the base game is untouched.
        self.setup_wagons_board()

        # The Fishermen scenario starts the robber beside the board, not on the
        # desert: it enters only on the first 7 or a knight (expansions.md 504).
        # Board generation may have dropped it on a desert, so clear it here.
        if self.rules['robber_starts_off_board']:
            self.robber_hex = None

        # Trade manager. How long an offer stays open is the table's, and the
        # server is the only clock that counts: the countdown a proposer and a
        # responder watch is drawn from this number, and every path that could
        # still move the cards checks it.
        self.trade_manager = TradeManager(
            offer_expiry_seconds=self.rules['trade_offer_seconds'],
        )

        # Catan for Two: seat the two non-producing neutral colours and place
        # their opening settlements. A no-op unless `neutral_players` is on, and
        # deliberately last so the board, its vertices and the distance rule the
        # opening placement reads are all in place. `neutral_players` stays the
        # empty list off the rule, so every neutral method downstream no-ops.
        self.neutral_players = []
        self.setup_neutral_players()

        # Catan for Two: give every real seat its opening five trade tokens. A
        # no-op off the `trade_tokens` rule. The once-per-turn flag for trading a
        # knight for tokens is cleared here and reset by `start_turn`.
        self.trade_token_knight_discarded = False
        self.seed_trade_tokens()

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
        if piece == 'harbor_settlement':
            return len(player.harbor_settlements) < self.MAX_HARBOR_SETTLEMENTS
        if piece == 'road':
            return len(player.roads) < self.MAX_ROADS
        if piece == 'ship':
            return len(player.ships) < self.MAX_SHIPS
        if piece == 'settler':
            return player.settlers < self.MAX_SETTLERS
        if piece == 'crew':
            return player.crews < self.MAX_CREWS
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

        Out along the seating order and back down it: with four players
        0,1,2,3,3,2,1,0, and with six 0..5,5..0. Derived from the seat count,
        never from a table's worth of literals.
        """
        num_players = len(self.players)
        if self.setup_turn < num_players:
            # First round: forward, in seating order
            return self.setup_turn
        if self.setup_turn < 2 * num_players:
            # Second round: back down it
            return (2 * num_players - 1) - self.setup_turn
        # Third round (Cloth for Catan): forward again, "starting with this same
        # player" — the one who laid the last second settlement, at index 0 — and
        # on clockwise. Only reached when `setup_third_settlement` keeps setup
        # going past the second round.
        return self.setup_turn - 2 * num_players

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
        # Cloth for Catan runs a third setup round, and it is the third
        # settlement that pays the opening hand — "when you place your third
        # settlement, you receive your starting resources" (Seafarers 2021,
        # p. 22). Every other table stops after two and pays from the second.
        rounds = 3 if self.rules['setup_third_settlement'] else 2
        if self.setup_turn >= num_players * rounds:
            # Setup complete - distribute starter resources from the last-placed
            # starting settlement (the second normally, the third with the rule).
            logger.debug("=== Distributing starter resources from starting settlements ===")
            for player in self.players:
                settlements = self.player_settlements.get(player.name, [])
                if len(settlements) >= rounds:
                    self.distribute_from_settlement(settlements[rounds - 1], player.name)

            self.game_phase = "playing"
            self.current_player_index = 0
            # The wagon sits on its owner's starting city once set-up finishes
            # (expansions.md 701). A no-op without the wagon rule.
            self.place_starting_wagons()
            # The Helpers: each player takes their first tile as set-up ends
            # (the one point every seat has finished placing). A no-op off the
            # scenario.
            self.grant_starting_helpers()
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
        # The old boot raises only its holder's threshold by 1 (expansions.md
        # 518); everyone else wins on the table's target. Zero without the rule.
        target = self.victory_points_to_win + self.personal_target_delta(player_name)
        # The Wonders of Catan replaces the plain threshold win with its own two
        # ends: finishing a Wonder, or reaching the target with a strictly higher
        # wonder level than every opponent (p. 28). Reaching ten points alone is
        # not a win here, so the threshold path is gated out entirely when the
        # rule is on rather than run alongside.
        if self.rules['wonders']:
            if not self.wonder_victory(player_name, points, target):
                return None
            self.game_state = "finished"
            return points
        # The Pirate Islands replaces the plain threshold win with its own end:
        # recapturing your own-colour fortress AND holding the target in points
        # (p. 22). Reaching ten points alone is not a win here, so the threshold
        # path is gated out entirely when the rule is on rather than run alongside.
        if self.rules['pirate_fortresses']:
            if not self.pirate_islands_victory(player_name, points):
                return None
            self.game_state = "finished"
            return points
        # Rise of the Inkas replaces the plain threshold win with its own end: the
        # first player to bring their third tribe to its cultural apex wins (p. 8),
        # whatever the point total reads. The threshold path is gated out entirely
        # when the rule is on rather than run alongside it.
        if self.rules['third_tribe_victory']:
            if not self.inka_victory(player_name):
                return None
            self.game_state = "finished"
            return points
        if points < target:
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
        moved = self.movement_phase_block()
        if moved is not None:
            return moved
        voting = self.camel_vote_block(player_name)
        if voting is not None:
            return voting

        in_setup = self.game_phase == "setup"
        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can place buildings')

        # Rise of the Inkas: a player who has just declined a tribe owes a free
        # founding settlement before anything else. Its siting rules are its own
        # (free, no road, its own restrictions), so it diverts here rather than
        # threading a founding flag through the whole paid build below.
        if self.founding_required(player_name):
            return self.place_founding_settlement(player_name, vertex_key)

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
        # Rise of the Inkas: an active tribe may build a settlement over a
        # declining (thicket-covered) building, which the base placement would
        # refuse as OCCUPIED. Diverts to the overbuild path, which charges a
        # settlement, returns the old piece to its owner and plants the new one.
        if not in_setup and self.rules['overbuild_ruins'] and self.is_ruin(vertex_key):
            return self.overbuild_ruin(player_name, vertex_key)
        # A settlement may not stand at an intersection beside a face-down hex
        # (891). A no-op unless the table is exploring, since nothing else hides
        # a hex.
        if self.rules['ships_explore']:
            undiscovered = self.undiscovered_build_refusal(vertex.neighbors['hexes'])
            if undiscovered is not None:
                return undiscovered
        # An uncaptured pirate lair locks the corners of its gold field.
        lair = self.pirate_lair_build_refusal(vertex.neighbors['hexes'])
        if lair is not None:
            return lair
        # A spice village locks its corners for a player until they befriend it.
        spice = self.spice_build_refusal(player_name, vertex.neighbors['hexes'])
        if spice is not None:
            return spice
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
        # The Wonders of Catan: the marked strait and wasteland squares carry no
        # *starting* settlement (p. 26) — they are settled later, in play, to gate
        # a Wonder. A no-op without the rule and away from a marked intersection.
        if in_setup and self.rules['wonders'] and self.is_wonder_marker(vertex_key):
            return refused(
                'INVALID_PLACEMENT', 'This marked intersection cannot take a starting settlement'
            )
        if vertex.building is not None:
            return refused('OCCUPIED', 'This location already has a building')
        if self.knight_holds(vertex_key):
            return refused('OCCUPIED', 'A knight is standing here')
        # Barbarian Attack: no settlement may stand beside a conquered hex (628).
        # A no-op without the rule and away from the coast.
        conquered = self.barbarian_settlement_refusal(vertex_key)
        if conquered is not None:
            return conquered
        # Main scenario: no building on a trade hex plaza (699). A no-op without
        # the wagon rule and away from a trade hex.
        plaza = self.trade_hex_settlement_refusal(vertex_key)
        if plaza is not None:
            return plaza
        # The Forgotten Tribe: no settlement on the barren small islands. A
        # no-op without the rule and away from a barren island.
        barren = self.barren_island_build_refusal(vertex.neighbors['hexes'])
        if barren is not None:
            return barren
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
        if not in_setup:
            # A building blocks an opponent's route through its intersection,
            # so settling mid-route takes the card off them — the same reason
            # a knight standing there does.
            self.update_longest_road()
        # The islands a player starts on are theirs already, so setup records
        # them without scoring them.
        island_points = self.record_island_settlement(
            player_name, vertex_key, award=not in_setup
        )

        if in_setup:
            self.last_setup_settlement = vertex_key
        self.setup_action = "road" if in_setup else "settlement"

        # The Forgotten Tribe: a player holding a gift harbour with nowhere to
        # put it is offered it again now a fresh coastal settlement may give it
        # one. A no-op without the rule and when nothing is held.
        if self.rules['coast_gifts']:
            self.offer_held_gift_harbors(player_name)

        # The Rivers of Catan: a settlement adjacent to a river hex pays 1 gold
        # coin — set-up and later both, but never for a city. A no-op without
        # `river_gold`. Kept a distinct method, not a branch inside the build.
        river_gold = 0
        if building_type != 'city':
            river_gold = self.grant_river_settlement_gold(player_name, vertex_key)

        # Catan for Two: a new settlement earns trade tokens for its builder —
        # 2 by the desert, 1 on the coast, 3 by both — in set-up and in play
        # alike, but never for a city. A no-op off the `trade_tokens` rule and
        # for a neutral colour, which earns nothing.
        trade_tokens_earned = 0
        if building_type != 'city':
            trade_tokens_earned = self.grant_settlement_trade_tokens(player_name, vertex_key)

        # The Fishermen of Catan: a second setup settlement beside a fishing
        # ground draws 1 fish at set-up (497). Only the second — the first draws
        # nothing — and only a settlement, so a starting city (setup_second_city)
        # takes none. A no-op without the fish rules, handled inside the method.
        if in_setup and building_type != 'city' \
                and len(self.player_settlements.get(player_name, [])) == 2:
            self.draw_setup_fish(player_name, vertex_key)

        # The Caravans: a settlement built after set-up earns a camel, placed by
        # a voting round when the turn ends (expansions.md 578). A no-op without
        # the rule. A setup settlement earns nothing.
        if not in_setup and self.rules['caravans']:
            self.camel_owed = True

        # Barbarian Attack: every build after set-up resolves an attack at once
        # (expansions.md 621). A no-op without the rule. A setup build earns none
        # — the opening two barbarians are seeded at board setup instead.
        attack = None
        if not in_setup and self.rules['barbarian_attack']:
            attack = self.trigger_barbarian_attack()

        # Rise of the Inkas: tag the new building with its owner's tribe (and add
        # its culture marker), then — in play — check whether the tribe has just
        # reached its apex and must decline. A no-op off the rule. Setup buildings
        # are tagged (the two starting settlements are the first tribe's first two
        # markers) but never trigger a decline.
        self.tag_building_tribe(player_name, vertex_key)
        tribe_decline = None
        if not in_setup:
            tribe_decline = self.check_tribe_transition(player_name)

        # Catan for Two: a real player building in play forces one free neutral
        # piece onto the board (rulebook "Building Progress of the Neutral
        # Players"). A no-op off the rule and during setup, where the neutral
        # openings are seeded once instead.
        neutral_expansion = None
        if not in_setup and self.rules['neutral_players']:
            neutral_expansion = self.expand_neutral_players(player_name)

        return {
            'success': True,
            'error': '',
            'building_type': building_type,
            'island_points': island_points,
            'river_gold': river_gold,
            'barbarian_attack': attack,
            'tribe_decline': tribe_decline,
            'neutral_expansion': neutral_expansion,
            'trade_tokens_earned': trade_tokens_earned,
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

        moved = self.movement_phase_block()
        if moved is not None:
            return moved
        voting = self.camel_vote_block(player_name)
        if voting is not None:
            return voting

        in_setup = self.game_phase == "setup"
        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can place buildings')

        if in_setup and self.setup_action != "road":
            return refused('WRONG_PHASE', 'You must place a settlement first')

        # Rise of the Inkas: a player who has just declined a tribe must place
        # their founding settlement before any other build.
        if self.founding_required(player_name):
            return refused('MUST_FOUND_TRIBE', 'Place your founding settlement first')

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
        # The Rivers of Catan: a normal road may never sit on a river-crossing
        # bridge site — only a bridge spans one (expansions.md 541). This also
        # stops the Road Building card placing a bridge, since it drives this
        # method. A no-op off the river board, where there are no sites.
        if self.is_bridge_site(edge_key):
            return refused('INVALID_PLACEMENT', 'Only a bridge may span this river crossing')
        # Barbarian Attack: no road may lie on a path beside a conquered hex
        # (628). A no-op without the rule and away from the coast.
        conquered = self.barbarian_road_refusal(edge_key)
        if conquered is not None:
            return conquered
        # Main scenario: no road on a trade hex's sea-border path (700). A no-op
        # without the wagon rule and away from a trade hex.
        trade_sea = self.trade_hex_road_refusal(edge_key)
        if trade_sea is not None:
            return trade_sea
        # A road may not lie on a path beside a face-down hex (891). A no-op
        # unless the table is exploring, since nothing else hides a hex.
        if self.rules['ships_explore']:
            undiscovered = self.undiscovered_build_refusal(edge.neighbors['hexes'])
            if undiscovered is not None:
                return undiscovered
        # An uncaptured pirate lair locks the edges of its gold field.
        lair = self.pirate_lair_build_refusal(edge.neighbors['hexes'])
        if lair is not None:
            return lair
        # A spice village locks its edges for a player until they befriend it.
        spice = self.spice_build_refusal(player_name, edge.neighbors['hexes'])
        if spice is not None:
            return spice

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
            # Rise of the Inkas: a tribe in decline may not expand — a road may
            # reach up to a thicket-covered building but never extend from one.
            if self.rules['tribe_decline'] and self.road_only_from_ruin(player_name, edge_key):
                return refused('DECLINED_NO_EXPANSION', 'A tribe in decline cannot build roads')
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
            # Catan: Frenemies: a road that joins your network to an opponent's
            # for the first time earns three favours for you and one for them
            # (p. 1). A no-op off the rule and during setup (no favours then).
            self.award_connection_favours(player_name, edge_key)

        # The Rivers of Catan: a road on a path adjacent to a river hex pays 1
        # gold coin — set-up and later both. A no-op without `river_gold`.
        river_gold = self.grant_river_road_gold(player_name, edge_key)

        # The Fog Islands: a road reaching a fog hex reveals it for a resource
        # (Seafarers 2021, Scenario 3). A no-op without `fog_reveal` and away
        # from a face-down hex.
        revealed = self.discover_from_build(player_name, edge.neighbors['hexes'])

        # Catan for Two: a real player's road in play forces one free neutral
        # piece too (rulebook "Building Progress of the Neutral Players"). A
        # no-op off the rule and during setup.
        neutral_expansion = None
        if not in_setup and self.rules['neutral_players']:
            neutral_expansion = self.expand_neutral_players(player_name)

        return {'success': True, 'error': '', 'used_free_road': used_free_road,
                'river_gold': river_gold, 'revealed': revealed,
                'neutral_expansion': neutral_expansion}

    def upgrade_city(self, player_name: str, vertex_key: str) -> dict:
        """Turn one of the player's own settlements into a city."""
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
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
            return refused('WRONG_PHASE', 'Cannot upgrade to city during setup phase')

        # Explorers & Pirates never upgrades a settlement to a city (838): the
        # game is scored on settlements instead. Gated on the rule, not the
        # expansion name.
        if self.rules['no_city_upgrades']:
            return refused('NO_CITY_UPGRADES', 'This table plays without city upgrades')

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

        # Rise of the Inkas: a tribe in decline cannot upgrade, a player owing a
        # founding settlement must place it first, and a tribe may hold only one
        # city (rulebook pp. 6-7). Gated on the rule, so base play is untouched.
        if self.rules['tribe_decline']:
            if self.founding_required(player_name):
                return refused('MUST_FOUND_TRIBE', 'Place your founding settlement first')
            if vertex.building.get('ruined'):
                return refused('DECLINED_NO_EXPANSION',
                               'A tribe in decline cannot upgrade to a city')
            upgrading = self.get_player(player_name)
            if upgrading is not None and self.tribe_has_city(player_name, upgrading.tribe):
                return refused('ONE_CITY_PER_TRIBE', 'A tribe may build only one city')

        if not self.can_afford(player_name, 'city'):
            return refused('INSUFFICIENT_RESOURCES', self._cost_message('city'))
        self.deduct_cost(player_name, 'city')

        # A city keeps the tribe tag its settlement already carried, so the
        # upgraded building still counts toward the right tribe's apex.
        upgraded = {'type': 'city', 'player': player_name}
        if 'tribe' in vertex.building:
            upgraded['tribe'] = vertex.building['tribe']
        vertex.building = upgraded

        player = self.get_player(player_name)
        if player and vertex_key in player.settlements:
            player.settlements.remove(vertex_key)
            player.cities.append(vertex_key)

        self.update_harbormaster()

        # Rise of the Inkas: the upgrade places one more culture marker (a city is
        # worth 2, one more than the settlement it replaces) and may carry the
        # tribe to its apex, sending it into decline.
        tribe_decline = None
        if self.rules['tribe_decline'] and player is not None:
            player.culture_points += 1
            tribe_decline = self.check_tribe_transition(player_name)

        # The Caravans: upgrading a settlement to a city earns a camel too,
        # placed when the turn ends (expansions.md 578). A no-op without the rule.
        if self.rules['caravans']:
            self.camel_owed = True

        # Barbarian Attack: an upgrade to a city resolves an attack too (621). A
        # no-op without the rule.
        attack = None
        if self.rules['barbarian_attack']:
            attack = self.trigger_barbarian_attack()

        return {'success': True, 'error': '', 'barbarian_attack': attack,
                'tribe_decline': tribe_decline}

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
            if not edge or not edge.ship or edge.ship.get('player') != player_name:
                continue
            # An E&P transport ship extends no network (866); it must never be
            # read as a route extender. The `sea_ship_model` exclusion already
            # forbids transport ships with `ships`, so this branch is only
            # reachable in a table that has no transports — the guard is defence
            # in depth, not a live case.
            if edge.ship.get('kind') == 'transport':
                continue
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

        # The Forgotten Tribe: each 1-VP Catan chit claimed at a marked coast
        # edge is a special point banked under its claimer, added like the
        # island bonus above. A no-op without the rule.
        if self.rules['coast_gifts']:
            points += self.gift_points.get(player_name, 0)

        # Cloth for Catan: every two bolts of cloth score a point, an unpaired
        # bolt nothing. Read live off the bolt count, so a point lands the moment
        # a second bolt does. A no-op without the villages rule.
        if self.rules['cloth_villages']:
            points += self.cloth_victory_points(player_name)

        # The Wonders of Catan: +1 for each of this player's buildings on a small
        # island (p. 27). Read live off the board like the cloth points above, so
        # a point lands the moment a small-island settlement does. A no-op without
        # the rule.
        if self.rules['wonder_island_points']:
            points += self.wonder_island_victory_points(player_name)

        # "The player controlling the merchant scores 1 victory point for as
        # long as they control it" — and control passes the moment somebody
        # else plays a Merchant card, so this is read rather than banked.
        if self.merchant_holder == player_name:
            points += 1

        # Each mission's 1-VP lead card scores for whoever is alone at the front
        # of that track. Held state, recomputed on every advance, so it is read
        # off `self.ep` the same way the awards above are.
        if self.rules['missions']:
            points += self.mission_victory_points(player_name)

        if self.ck is not None:
            if self.rules['metropolis']:
                # A metropolis makes its city worth 4 instead of 2, so it adds
                # 2 on top of what the city already scored.
                points += 2 * self.ck.metropolis_count(player_name)
            if self.rules['barbarians']:
                points += self.ck.defender_cards.get(player_name, 0)

        # The Rivers of Catan tiles: +1 for the sole wealthiest player, -2 for
        # every player tied for the fewest coins. Dynamic — recomputed here from
        # the live coin totals — so the tiles move the instant gold changes. A
        # no-op unless one of the two flags is on.
        if self.rules['wealthiest_settler'] or self.rules['poor_settler']:
            points += self.river_tile_points(player_name)

        # The Caravans: +1 for each of this player's buildings standing between
        # two camels. Read live off the camel positions, so a point appears and
        # goes as caravans grow. A no-op unless the rule is on.
        if self.rules['caravans']:
            points += self.camel_victory_points(player_name)

        # Barbarian Attack: +1 for every two prisoners held, and a toppled
        # settlement or city scores nothing. Read live off the war state, so a
        # point appears as a coast is freed and vanishes as one is conquered. A
        # no-op unless the rule is on.
        if self.rules['barbarian_attack']:
            points += self.barbarian_victory_points(player_name)

        # Traders & Barbarians (main scenario): +1 for each delivered commodity
        # token, the fifth baggage-train card and each held Toolmaking/
        # Glassmaking/Quarry card. Read live off the wagon state. A no-op without
        # the rule.
        if self.rules['trade_caravans']:
            points += self.trade_victory_points(player_name)

        # Catan: Oil Springs. Sequestered oil scores 1 VP per 3 plus the 1-VP
        # Champion of the Environment token, and each metropolis adds 1 on top of
        # the 2 its city already scored. Read live off the oil state, so a point
        # lands the moment a third oil is sequestered or a city is upgraded. Each
        # gated on its own rule, so a table without it is unaffected.
        if self.rules['oil_sequester_vp']:
            points += self.oil_sequester_victory_points(player_name)
        if self.rules['oil_metropolis']:
            points += self.oil_metropolis_victory_points(player_name)

        # Catan: Frenemies. Each Victory-Point marker taken from the Master
        # Builders' guild is worth 1 point and is kept face up, so it counts
        # toward the public total. A no-op off the guild-hall rule.
        if self.rules['guild_hall']:
            points += self.favour_victory_points(player_name)

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

    def priced_builds(self) -> dict:
        """Every flat price in the game, as this table's rules charge it.

        The client used to keep its own copy of `data/costs.json` to grey a
        build button out, which is a second table of prices free to disagree
        with the engine's — and a cost modifier would have moved one of them
        and not the other, so a rule that made building cheaper would have been
        charged but never shown.

        Flat prices only: a city improvement is priced per level, which is a
        question with an argument rather than a line in a table, so a client
        that needs one asks the rule that governs it instead of rebuilding the
        table here. Every price goes through `get_cost`, so what the payload
        carries is what the player would actually pay.
        """
        return {
            build_type: self.get_cost(build_type) for build_type in self.building_costs
        }

    def producible_resources(self) -> set:
        """Every resource this board's terrain can pay out on a roll.

        The base five for a standard board; those plus cotton where a map deals
        cotton hexes. Read off the terrain the board was actually dealt, so it is
        the truth about this table rather than a copy of a layout's intent.
        """
        produced = set()
        for hex_obj in self.hexes.values():
            resource = tiles.produces(hex_obj.type)
            if resource is not None:
                produced.add(resource)
        return produced

    def in_play_resource_types(self) -> list:
        """The resources this game uses, base five first then any a map adds.

        The client renders its hand, bank and every resource picker from this
        list, so a standard board shows exactly the five in their usual order and
        a cotton map shows cotton after them. Ordered deterministically — the
        base five as they have always been, extras sorted — so the payload does
        not depend on set iteration order.
        """
        base = list(validation.BASE_RESOURCE_TYPES)
        extra = sorted(self.producible_resources() - set(base))
        return base + extra

    def in_play_card_types(self) -> list:
        """The resources and commodities this game can deal, for a picker that
        offers a card *type* (the Merchant Fleet's 2:1 nomination).

        In-play resources first, then the commodities the table plays. A board
        without cotton never offers it, so a standard Cities & Knights table sees
        exactly the eight it always has — the five resources and the three
        commodities. Science is offered only when New Energies is in play, the
        same way: a picker follows what the table can actually hold.
        """
        cards = self.in_play_resource_types()
        if self.rules['commodities']:
            cards = cards + ['cloth', 'coin', 'paper']
        if self.rules['power_plants']:
            cards = cards + ['science']
        return cards

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
            if hex_obj.hidden:
                # Face-down: its identity is secret like a dev card until
                # discovery reveals it. No viewer sees an undiscovered tile yet,
                # so it redacts for everyone; the per-viewer reveal set lands
                # with the exploration wave.
                entry = {'type': 'hidden', 'number': None, 'hidden': True,
                         'neighbors': hex_obj.neighbors}
            else:
                entry = {
                    'type': hex_obj.type,
                    'number': hex_obj.number,
                    'neighbors': hex_obj.neighbors,
                }
            if hex_obj.meta:
                entry['meta'] = hex_obj.meta.to_json()
            hexes[key] = entry

        vertices = {}
        for key, vertex_obj in self.vertices.items():
            vertex_data = {'building': vertex_obj.building, 'neighbors': vertex_obj.neighbors}
            if vertex_obj.port:
                vertex_data['port'] = vertex_obj.port
            # A non-standard piece (a trade-hex plaza) is tagged so the renderer
            # can draw it as a plaza rather than a plain intersection. Absent on
            # every standard vertex, so a board with no such pieces is unchanged.
            if vertex_obj.kind != 'standard':
                vertex_data['kind'] = vertex_obj.kind
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
            # A non-standard side (a trade-hex interior spoke) is tagged so the
            # renderer can draw the interior path even before a road sits on it.
            # Absent on every standard edge, so a board with no such pieces is
            # unchanged.
            if edge_obj.kind != 'standard':
                edge_data['kind'] = edge_obj.kind
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
            # What each build costs at this table, modifiers included. The
            # client greys its buttons out from this and never from a table of
            # its own.
            'costs': self.priced_builds(),
            # The resource registry — name, colour, symbol and pattern per
            # resource. The client draws terrain from this rather than its own
            # copy, so adding a resource is one server-side entry. Server-global.
            'resources': resources.registry(),
            # The resources this board actually deals, base five first then any a
            # map adds (cotton). The client renders its hand, bank and pickers
            # from this order rather than a hardcoded five, so a cotton map shows
            # cotton and a standard board shows exactly the five it always has.
            'resource_types': self.in_play_resource_types(),
            # The building registry — name, cost and icon per build. The client
            # draws each build's label and glyph from this rather than its own
            # copy, so adding or relabelling a build is one server-side entry.
            # `costs` above stays the per-table priced view (modifiers applied);
            # this carries the static list price alongside the name and icon.
            'buildings': buildings.registry(),
            'cities_knights': self.ck.to_dict(viewer) if self.ck else None,
            # Pirate hexes, mission tracks/markers/lead cards, token supplies and
            # the undiscovered-pool count. Mission progress is public; the pool's
            # tile identities are the one secret, redacted inside `to_dict`.
            'ep': self.ep.to_dict(viewer) if self.ep else None,
            # Traders & Barbarians (Fishermen): the fish-supply count, the old
            # boot holder, and the board's fishing grounds and lake. A viewer's
            # own fish hand is included in full; every other hand is a count
            # only, redacted inside `to_dict` the way a resource hand is.
            'tb': self.tb.to_dict(viewer) if self.tb else None,
            # Catan for Two: the two non-producing neutral colours and their
            # pieces. The renderer draws each neutral settlement and road in its
            # colour off this; empty off the rule, so a normal board is unchanged.
            'neutrals': self.neutral_board_state(),
            'harbormaster_holder': self.harbormaster_holder,
            'harbor_points': self.harbor_points,
            # The Rivers of Catan bridge sites: the paths a bridge may span. The
            # client draws a bridge affordance on these; empty off the river
            # board, so nothing changes there. Bridges themselves ride on the
            # edge payload as roads carrying kind='bridge'.
            'bridge_sites': sorted(self.bridge_sites),
            # The Caravans oasis arrows: the paths each caravan starts from. The
            # client draws the arrows on these; empty off the Caravans board. The
            # camels themselves and the caravan chains ride on the `tb` payload.
            'oasis_arrows': sorted(self.oasis_arrows),
            # The Forgotten Tribe marked gift coast edges: the kind of gift on
            # each, and which have already been claimed, so the client can draw
            # the markers and grey out spent ones. Empty off the scenario board.
            'gift_edges': {
                edge_key: gift['gift'] for edge_key, gift in sorted(self.gift_edges.items())
            },
            'claimed_gift_edges': sorted(self.claimed_gift_edges),
            'gift_points': self.gift_points,
            # Cloth for Catan: each village's number and remaining bolts, so the
            # client can mark the villages and grey a spent one, and each
            # player's banked bolts for the scoreboard readout. Empty off the
            # scenario board.
            'cloth_villages': {
                vertex_key: {
                    'number': self.village_number[vertex_key],
                    'cloth': self.village_cloth.get(vertex_key, 0),
                }
                for vertex_key in sorted(self.village_number)
            },
            'cloth_tokens': self.cloth_tokens,
            # Catan: Oil Springs — the oil springs to badge, the general supply,
            # and each player's oil. None off the scenario.
            'oil': self.oil_client_state(),
            # CATAN: New Energies — the power plants on the board, each player's
            # energy and remaining plant supply. None off the scenario.
            'new_energies': self.new_energies_client_state(viewer),
            # Catan: Frenemies — the favour-token bag count, each player's token
            # count, and the viewer's own tokens by guild. None off the scenario.
            'frenemies': self.frenemies_client_state(viewer),
            # Rise of the Inkas — each player's tribe number and culture markers,
            # the cultural goals, and who owes a founding settlement. The thicket
            # markers themselves ride on each vertex's building.ruined flag. None
            # off the scenario.
            'inkas': self.inkas_client_state(),
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
            # The Wonders of Catan: the catalogue, each player's Wonder and level,
            # and the marked intersections. None off the scenario.
            'wonders': self.wonders_client_state(),
            # The Pirate Islands: the fleet's track and where it sits, the
            # fortresses and each player's warships. None off the scenario.
            'pirate_islands': self.pirate_islands_client_state(),
            # CATAN - The Helpers: the display pile, each player's held tile and
            # which side is up, and who has spent their helper this turn. None
            # off the scenario.
            'helpers': self.helpers_client_state(viewer),
            'must_move_robber': self.must_move_robber,
            # Main scenario: who owes a roaming-barbarian move after a 7, or None.
            'must_move_barbarian': self.must_move_barbarian,
            # This turn's remaining wagon movement points, for the mover's client.
            'wagon_points_left': self.wagon_points_left,
            # Whether those points belong to a Swift Journey second movement,
            # so the mover's client can show the distinct phase.
            'wagon_swift_journey': self.wagon_swift_journey,
            'must_choose_victim': self.must_choose_victim,
            'robber_victims': self.robber_victims,
            'players_needing_discard': self.players_needing_discard,
            'dice_roll_time': self.get_dice_roll_time_remaining(),
            'round_time': self.get_round_time_remaining(),
            # Which clock is actually running and how much of it is left. The
            # two fields above are one phase each and say nothing while a
            # discard or a robber move is holding the table up.
            'timer': self.timer_state(),
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
            # A Barbarian Attack conquered hex pays nobody; game state, not
            # geometry, so the funnel is told rather than left to work it out.
            conquered_here=self._hex_is_conquered(hex_obj.key),
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
        self.gold_gained = {}

        if dice_total == 7:
            return {}

        gained_resources = {}
        # Seafarers gold fields owe resources of the owner's choice rather than a
        # card: the production modifier marks how many each building is owed, and
        # they are gathered here and turned into pending choices once the whole
        # roll is walked. {player: resources owed}.
        gold_field_choices_owed = {}

        for _vertex_key, vertex in self.vertices.items():
            if not vertex.building or vertex.building.get('type') not in (
                'settlement', 'city', 'harbor_settlement'
            ):
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
                # Anything that pays out on its roll: the resource terrains and a
                # gold field (which pays gold, not a card). Desert, sea, and the
                # fish/spice mission tiles carry no token, so they never pay here.
                if hex_obj.number != dice_total or not tiles.takes_token(hex_obj.type):
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

                # A gold field pays gold, not a resource card: the modifier put
                # the amount on the produced value and the bank was never asked.
                field_gold = produced.get('gold', 0)
                if field_gold:
                    self.gain_gold(player_name, field_gold)
                    self.gold_gained[player_name] = (
                        self.gold_gained.get(player_name, 0) + field_gold
                    )

                # A gold-of-choice field pays no card here: it only records how
                # many resources the owner may pick, opened as choices below.
                owed = produced.get('gold_choice', 0)
                if owed:
                    gold_field_choices_owed[player_name] = (
                        gold_field_choices_owed.get(player_name, 0) + owed
                    )

        # A non-7 roll that paid a player no resource cards hands them 1 gold
        # (854); folded in after the walk so it sees the whole roll's payout.
        for player_name, amount in self.pay_empty_roll_gold(gained_resources).items():
            self.gold_gained[player_name] = self.gold_gained.get(player_name, 0) + amount

        # Gold fields that pay resources of choice open one pending choice per
        # owed resource, after the walk so every owed player is known and the
        # bank supply the choices are gated on reflects the whole roll's payout.
        self.open_gold_field_choices(gold_field_choices_owed)

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
            if hex_obj and tiles.produces(hex_obj.type) is not None:
                if self.bank.take(hex_obj.type):
                    player.resources[hex_obj.type] = player.resources.get(hex_obj.type, 0) + 1
                    gained[hex_obj.type] = gained.get(hex_obj.type, 0) + 1

                # The starting city yields "one resource and, where applicable,
                # one commodity" from each adjacent hex — one of each, not the
                # doubled production of a normal city turn. A table playing the
                # Traders & Barbarians reading takes the resource alone.
                pays_commodity = self.rules['starting_city_yield'] == 'resource_and_commodity'
                if self.rules['commodities'] and is_city and pays_commodity:
                    commodity = ck_module.COMMODITY_FROM_TERRAIN.get(hex_obj.type)
                    if commodity:
                        player.commodities[commodity] = player.commodities.get(commodity, 0) + 1
                        gained[commodity] = gained.get(commodity, 0) + 1

        # New Energies: "Each player also takes 1 science card for their city."
        # A single flat science for the starting city, not one per hex (rulebook,
        # 'Collect your starting hand', p. 7). A no-op off the rule and for a
        # starting settlement, since the New Energies opening building is a city.
        if self.rules['power_plants'] and is_city:
            player.commodities['science'] = player.commodities.get('science', 0) + 1
            gained['science'] = gained.get('science', 0) + 1

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

    def _base_cost(self, building_type: str, context: dict) -> dict:
        """The listed price of one build, before any modifier.

        Everything with a flat price is an entry in the building registry (see
        game/buildings.py), read here as `self.building_costs`. A city
        improvement is the one thing whose price depends on more than the build
        type — it is the level being bought, in the track's own commodity — so
        it is worked out from the track table instead.
        """
        if building_type.startswith(ck_module.IMPROVEMENT_PREFIX):
            level = context.get('level')
            if level is None:
                raise ValueError(f'{building_type} is priced per level; pass level=')
            priced = ck_module.improvement_price(building_type, level)
            if priced is not None:
                return priced
        if building_type not in self.building_costs:
            # An unlisted type used to price at nothing, so a typo bought the
            # piece for free and said nothing. Better to stop here than to
            # deduct an empty hand and call it a sale.
            raise KeyError(f'no listed price for {building_type!r}')
        return dict(self.building_costs[building_type])

    def get_cost(self, building_type: str, **context) -> dict:
        """What this costs to build, once every active modifier has had its say.

        The one place a price is decided, so a rule that makes something
        cheaper has somewhere to attach. See `game/modifiers.py`. `context` is
        whatever else the price turns on — a city improvement's level is the
        only one so far — and the hook is handed it too, so a rule can charge
        one level differently from another.
        """
        return modifiers_module.apply(
            modifiers_module.COST,
            self.rules,
            self._base_cost(building_type, context),
            building_type=building_type,
            **context,
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

        # New Energies runs an Event Phase before production: the active player
        # draws the footprint-scaled number of event discs and resolves them
        # (rulebook, 'Turn Overview' p. 9). Run here, once a turn (the phase
        # guards itself), so the events land before the roll pays out. The card
        # events may leave a pending choice, which freezes the table until it is
        # answered, exactly as any other choice does. A no-op off the rule.
        event_phase = self.run_event_phase(player_name)

        dice1, dice2 = self.next_dice()
        total = dice1 + dice2

        self.set_dice_rolled()

        # The Pirate Islands fleet sails "before anything else" (p. 22): the lower
        # of the two dice, along its track, and it raids any coast it lands beside
        # before production or a 7 is resolved. A no-op off the scenario.
        pirate_fleet = None
        if self.rules['pirate_fleet'] and self.pirate_fleet_track:
            landed = self.advance_pirate_fleet(min(dice1, dice2))
            pirate_fleet = {
                'hex': landed,
                'steps': min(dice1, dice2),
                'attacks': self.resolve_pirate_fleet_attack(landed, min(dice1, dice2)),
            }

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
            # Barbarian Attack uses no robber at all (expansions.md 619), and the
            # main scenario moves a roaming barbarian instead of the robber
            # (expansions.md 736): a 7 still forces the discard but moves the
            # robber only in a game that has one.
            # The Pirate Islands has no robber (p. 22): a 7 still forces the
            # discard, but no robber is moved.
            if (not barbarians_still_coming and not self.in_robber_free_opening()
                    and not self.rules['barbarian_attack']
                    and not self.rules['roaming_barbarians']
                    and not self.rules['pirate_fleet']):
                self.must_move_robber = True
            # The main scenario: the roller must move one of the three barbarians
            # to a free path (expansions.md 736), gated the way the robber move is.
            if self.rules['roaming_barbarians'] and self.tb is not None \
                    and self.tb.path_barbarians:
                self.must_move_barbarian = player_name
            self.check_discard_required()

        # A 7 produces nothing; distribute_resources knows that itself.
        gained = self.distribute_resources(total)

        # Remembered for the helper tiles that react to a roll: what it totalled
        # (a 7 or not) and who it paid, so Hilda can tell an empty roll from a
        # seven and Thorolf can fire on the seven. A no-op read off the scenario.
        self.last_roll_total = total
        self.last_roll_gains = gained

        # Fishermen: fishing grounds and the lake draw fish on their numbers,
        # after the resource walk so the short-supply check sees the whole roll.
        # A no-op without the fishing rules. Kept apart from `gained` because a
        # fish token is not a resource card.
        fish = self.distribute_fish(total)

        # Cloth for Catan: a village pays a bolt to each route joined to it when
        # its number is rolled. After the resource walk, like the fish, and kept
        # apart from `gained` because a bolt of cloth is not a resource card. A
        # no-op without the villages rule.
        cloth = self.distribute_cloth(total)

        # Oil Springs: buildings on an oil spring produce oil on the hex's
        # number, handed out one token at a time from the roller clockwise. After
        # the resource walk, like the fish and cloth, and kept apart from
        # `gained` because oil is a currency, not a resource card. A no-op
        # without the rule.
        oil = self.distribute_oil(total, player_name)

        # New Energies: a power plant on a hex that produced pays its owner 1
        # energy, capped at 5. After the resource walk, like the fish and oil,
        # and kept apart from `gained` because energy is a currency, not a card.
        # A no-op without the rule or a matching plant.
        energy = self.distribute_energy(total)

        # Krakatoa: a volcano whose number came up erupts, destroying or
        # downgrading a building on one of its corners. After the resource walk
        # so the building produced (resources of choice) before it was hit, which
        # is the order the variant sets. A no-op without the rule or a volcano.
        eruption = self.erupt_volcanoes(total)

        # Cloth for Catan is the one scenario a roll can end: its bolts move
        # victory points and empty villages, so both of its end conditions are
        # checked here, the instant that roll resolves. The primary 14-VP win
        # comes first — a roller who reaches the target on their own turn wins by
        # points (expansions.md 191) and would be the leader anyway — and only
        # otherwise does the villages-out end fire, when three or fewer villages
        # still hold cloth (expansions.md 192). The whole block is gated on the
        # cloth rule, so a village-less board (which reports zero remaining, i.e.
        # `<= 3`) never ends on a roll.
        game_over = None
        if self.rules['cloth_villages']:
            threshold_points = self.claim_victory(player_name)
            if threshold_points is not None:
                game_over = {'winner': player_name,
                             'victory_points': threshold_points,
                             'reason': 'victory_target'}
            else:
                game_over = self.cloth_alternate_end()

        # New Energies' second end condition: the bag ran empty when a disc was
        # needed this turn. Scored by the fossil/renewable balance, not points.
        # The 10-VP threshold win is the primary end and is reached the ordinary
        # way (claim_victory after a build), so this only fires when the bag
        # empties first. A no-op off the rule or when discs remained.
        if event_phase and event_phase.get('bag_empty'):
            game_over = self.end_on_empty_bag()

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
            # Gold the roll paid — the empty-roll bonus and any gold field —
            # kept apart from `gained` because gold is a currency, not a card.
            'gold': dict(sorted(self.gold_gained.items())),
            # Fish tokens the roll drew (player -> count). Empty when no fishing
            # source matched or the supply was too short to pay the whole table.
            'fish': fish,
            # Cloth bolts the roll paid (player -> count). Empty when no village
            # matched the roll or every matching village was already empty.
            'cloth': cloth,
            # Oil tokens the roll produced (player -> count). Empty on a 7, off
            # the scenario, or when no oil spring matched the roll.
            'oil': oil,
            # New Energies energy the roll produced (player -> count). Empty on a
            # 7, off the scenario, or when no power plant matched the roll.
            'energy': energy,
            # New Energies Event Phase this turn: the discs drawn, the events they
            # triggered, and whether the bag ran empty (the second end condition).
            # None off the scenario.
            'event_phase': event_phase if self.rules['event_discs'] else None,
            # Krakatoa eruptions this roll: one record per volcano that erupted,
            # {'hex', 'die', 'vertex', 'player', 'was', 'now'}, the victim fields
            # None when the lava destroyed nothing. Empty on a 7, off the rule,
            # or when no volcano matched the roll.
            'eruption': eruption,
            # The Pirate Islands fleet's move this roll and the coasts it raided,
            # or None off the scenario: {'hex', 'steps', 'attacks'} where each
            # attack names the player, the outcome and what was lost or rewarded.
            'pirate_fleet': pirate_fleet,
            # The win this roll produced, or None. Only Cloth for Catan sets it:
            # {'winner', 'victory_points', 'reason'} where reason is
            # 'victory_target' (reached 14 on turn) or 'villages_depleted'.
            'game_over': game_over,
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
            max_length = self._route_weight(visited_edges)

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
                    # But can count the road leading TO it (a camel on that path
                    # counts it double, like any other segment).
                    max_length = max(
                        max_length,
                        self._route_weight(visited_edges) + self._camel_road_weight(edge_key),
                    )
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
