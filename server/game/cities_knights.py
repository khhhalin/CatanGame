"""Cities & Knights state: improvement tracks, knights, walls, barbarians.

Keeping it in its own module means the base game stays readable, and a
base-game reader never has to page past rules that do not apply to them.

This is a state container, not a mode. The Game builds one whenever any rule
that needs somewhere to keep tracks, knight tokens, wall counts, the barbarian
ship or the progress decks is on — see `rules.EXPANSION_STATE_RULES`. Whether
a given mechanic actually happens is decided by that mechanic's own rule, never
by the presence of this object.
"""

from game import progress_cards

COMMODITY_TYPES = ("cloth", "coin", "paper")

# Which terrain upgrades to a commodity when a *city* produces. Fields and hills
# have no commodity — a city on them just yields two of the resource, as in the
# base game.
COMMODITY_FROM_TERRAIN = {
    "sheep": "cloth",
    "ore": "coin",
    "wood": "paper",
}

TRADE = "trade"
POLITICS = "politics"
SCIENCE = "science"

# Each track is bought with one commodity and unlocks one ability at level 3.
IMPROVEMENT_TRACKS = {
    TRADE: {
        "commodity": "cloth",
        "levels": ["Market", "Trading House", "Merchant Guild", "Bank", "Great Exchange"],
        "ability": "merchant_guild",
        "metropolis": "Metropolis of Trade",
    },
    POLITICS: {
        "commodity": "coin",
        "levels": ["Town Hall", "Church", "Fortress", "Cathedral", "Council of Catan"],
        "ability": "fortress",
        "metropolis": "Metropolis of Politics",
    },
    SCIENCE: {
        "commodity": "paper",
        "levels": ["Abbey", "Library", "Aqueduct", "Theater", "University"],
        "ability": "aqueduct",
        "metropolis": "Metropolis of Science",
    },
}

MAX_IMPROVEMENT_LEVEL = 5
ABILITY_LEVEL = 3  # Merchant Guild / Fortress / Aqueduct
METROPOLIS_LEVEL = 4  # first to here claims it
METROPOLIS_STEAL_LEVEL = 5  # first to here takes it off the current holder

# Knight ranks. A knight may only be promoted one rank at a time, and reaching
# mighty additionally requires the Fortress.
BASIC, STRONG, MIGHTY = 1, 2, 3
MAX_KNIGHTS_PER_RANK = 2

BARBARIAN_TRACK_LENGTH = 7

# The event die: three faces send the barbarians one step closer, the other
# three open a city gate for one discipline.
EVENT_BARBARIAN = "barbarian"
EVENT_FACES = [
    EVENT_BARBARIAN,
    EVENT_BARBARIAN,
    EVENT_BARBARIAN,
    SCIENCE,
    POLITICS,
    TRADE,
]

CITY_WALL_COST = {"brick": 2}
CITY_WALL_HAND_BONUS = 2
MAX_CITY_WALLS = 3

# Progress cards replace development cards entirely. Four in hand is the limit
# in the standard three-to-four-player game; cards worth a victory point are
# revealed on sight and never occupy a slot.
PROGRESS_HAND_LIMIT = 4

KNIGHT_BUILD_COST = {"sheep": 1, "ore": 1}
KNIGHT_ACTIVATE_COST = {"wheat": 1}
KNIGHT_PROMOTE_COST = {"sheep": 1, "ore": 1}


def improvement_cost(level: int) -> int:
    """Commodities needed to reach `level`. Level 1 costs 1, level 5 costs 5."""
    return level


class Knight:
    """A knight standing on an intersection.

    Attributes:
        vertex: Vertex key it occupies.
        rank: BASIC, STRONG or MIGHTY — also its strength.
        active: Only active knights defend Catan or may act.
        acted_this_turn: A knight gets one action per turn.
        activated_this_turn: A knight may not act on the turn it was activated.
    """

    def __init__(self, vertex: str, rank: int = BASIC):
        self.vertex = vertex
        self.rank = rank
        self.active = False
        self.acted_this_turn = False
        self.activated_this_turn = False

    def to_dict(self) -> dict:
        return {
            "vertex": self.vertex,
            "rank": self.rank,
            "active": self.active,
            "can_act": self.can_act(),
        }

    def can_act(self) -> bool:
        return self.active and not self.acted_this_turn and not self.activated_this_turn

    def spend_action(self):
        """Acting always deactivates a knight; grain reactivates it later."""
        self.acted_this_turn = True
        self.active = False


class CitiesKnights:
    """All Cities & Knights state for one game.

    The three sizes are passed in rather than read from the constants above
    because the lobby can change them; the constants remain what the box holds.
    """

    def __init__(
        self,
        barbarian_track_length: int = BARBARIAN_TRACK_LENGTH,
        progress_hand_limit: int = PROGRESS_HAND_LIMIT,
        max_city_walls: int = MAX_CITY_WALLS,
    ):
        self.barbarian_track_length = barbarian_track_length
        self.progress_hand_limit = progress_hand_limit
        self.max_city_walls = max_city_walls
        # player -> {track: level}
        self.improvements = {}
        # player -> list[Knight]
        self.knights = {}
        # player -> the city vertices they have walled. A wall belongs to one
        # named city, not to its owner: it is lost with that city when the
        # barbarians sack it, and no city may carry two.
        self.city_walls = {}
        # track -> player holding that metropolis
        self.metropolis = {TRADE: None, POLITICS: None, SCIENCE: None}
        # Which city each metropolis sits on, so it can be drawn and so a
        # pillage knows to skip it.
        self.metropolis_vertex = {TRADE: None, POLITICS: None, SCIENCE: None}

        self.barbarian_position = 0
        self.barbarians_have_attacked = False
        self.last_event = None
        self.last_red_die = None
        # player -> Defender of Catan cards earned (1 VP each)
        self.defender_cards = {}

        # deck name -> remaining card ids. Built on first draw rather than in
        # __init__ so the shuffle can use the game's own seeded RNG, which is
        # what makes a draw order reproducible from the seed.
        self.progress_decks = {}
        # player -> progress card ids held
        self.progress_hands = {}

    def register(self, player_name: str):
        self.improvements.setdefault(player_name, {TRADE: 0, POLITICS: 0, SCIENCE: 0})
        self.knights.setdefault(player_name, [])
        self.city_walls.setdefault(player_name, [])
        self.defender_cards.setdefault(player_name, 0)
        self.progress_hands.setdefault(player_name, [])

    # --- Progress cards ----------------------------------------------------

    def deck(self, deck_name: str, rng) -> list:
        self.progress_decks.setdefault(deck_name, progress_cards.build_deck(deck_name, rng))
        return self.progress_decks[deck_name]

    def hand_of(self, player_name: str) -> list:
        return self.progress_hands.setdefault(player_name, [])

    def hand_is_full(self, player_name: str) -> bool:
        return len(self.hand_of(player_name)) >= self.progress_hand_limit

    def draw_progress_card(self, deck_name: str, rng) -> str | None:
        """Take the top card of a deck, or None once it is exhausted."""
        deck = self.deck(deck_name, rng)
        if not deck:
            return None
        return deck.pop()

    def return_progress_card(self, deck_name: str, card_id: str):
        """Put a card back underneath the deck it came from."""
        self.progress_decks.setdefault(deck_name, []).insert(0, card_id)

    # --- City improvements -------------------------------------------------

    def level(self, player_name: str, track: str) -> int:
        return self.improvements.get(player_name, {}).get(track, 0)

    def next_improvement_cost(self, player_name: str, track: str):
        """(commodity, amount) to buy the next level, or None at the top."""
        current = self.level(player_name, track)
        if current >= MAX_IMPROVEMENT_LEVEL:
            return None
        return IMPROVEMENT_TRACKS[track]["commodity"], improvement_cost(current + 1)

    def has_ability(self, player_name: str, track: str) -> bool:
        """Whether the level-3 building of this track is up."""
        return self.level(player_name, track) >= ABILITY_LEVEL

    def claim_metropolis(self, player_name: str, track: str, city_vertex: str) -> str | None:
        """Award or move a metropolis after an improvement was bought.

        Level 4 claims an unowned metropolis. Level 5 takes it from whoever
        holds it. A holder who reaches 5 themselves can never lose it.
        Returns the previous holder if it changed hands, else None.
        """
        new_level = self.level(player_name, track)
        holder = self.metropolis[track]

        if holder == player_name:
            return None
        if new_level < METROPOLIS_LEVEL:
            return None

        if holder is not None:
            # Level 5 is needed to take an occupied metropolis at all...
            if new_level < METROPOLIS_STEAL_LEVEL:
                return None
            # ...and a holder who has reached 5 themselves can never lose it,
            # so two players at level 5 leaves it with whoever got there first.
            if self.level(holder, track) >= METROPOLIS_STEAL_LEVEL:
                return None

        self.metropolis[track] = player_name
        self.metropolis_vertex[track] = city_vertex
        return holder

    def metropolis_count(self, player_name: str) -> int:
        return sum(1 for owner in self.metropolis.values() if owner == player_name)

    def is_metropolis(self, vertex_key: str) -> bool:
        return vertex_key in [v for v in self.metropolis_vertex.values() if v]

    # --- Knights -----------------------------------------------------------

    def knights_of(self, player_name: str) -> list:
        return self.knights.setdefault(player_name, [])

    def knight_at(self, vertex_key: str):
        """(owner, knight) standing on this vertex, or (None, None)."""
        for owner, knights in self.knights.items():
            for knight in knights:
                if knight.vertex == vertex_key:
                    return owner, knight
        return None, None

    def can_build_knight(self, player_name: str, rank: int = BASIC) -> bool:
        """Piece supply: two tokens of each rank, as in the box."""
        held = sum(1 for k in self.knights_of(player_name) if k.rank == rank)
        return held < MAX_KNIGHTS_PER_RANK

    def can_promote(self, player_name: str, knight: Knight) -> tuple:
        """(allowed, reason). Mighty needs the Fortress."""
        if knight.rank >= MIGHTY:
            return False, "That knight is already a mighty knight"
        target = knight.rank + 1
        if target == MIGHTY and not self.has_ability(player_name, POLITICS):
            return False, "Promoting to a mighty knight needs the Fortress (Politics level 3)"
        if not self.can_build_knight(player_name, target):
            return (
                False,
                f"You have no {'strong' if target == STRONG else 'mighty'} knight pieces left",
            )
        return True, ""

    def total_knight_strength(self, player_name: str = None) -> int:
        """Strength of active knights — the whole table's, or one player's.

        Only active knights defend Catan; an inactive one contributes nothing.
        """
        if player_name is not None:
            return sum(k.rank for k in self.knights_of(player_name) if k.active)
        return sum(k.rank for knights in self.knights.values() for k in knights if k.active)

    def deactivate_all(self):
        """After a barbarian attack every knight is spent."""
        for knights in self.knights.values():
            for knight in knights:
                knight.active = False

    def start_turn(self):
        """Clear the per-turn flags so knights may act again."""
        for knights in self.knights.values():
            for knight in knights:
                knight.acted_this_turn = False
                knight.activated_this_turn = False

    # --- Barbarians --------------------------------------------------------

    def advance_barbarians(self) -> bool:
        """Move the ship one space. True when it has arrived."""
        self.barbarian_position += 1
        if self.barbarian_position >= self.barbarian_track_length:
            return True
        return False

    def reset_barbarians(self):
        self.barbarian_position = 0
        self.barbarians_have_attacked = True

    # --- City walls --------------------------------------------------------

    def walls_of(self, player_name: str) -> list:
        """The city vertices this player has walled."""
        return self.city_walls.setdefault(player_name, [])

    def has_wall(self, vertex_key: str) -> bool:
        return any(vertex_key in walls for walls in self.city_walls.values())

    def build_wall(self, player_name: str, vertex_key: str):
        self.walls_of(player_name).append(vertex_key)

    def destroy_wall(self, player_name: str, vertex_key: str):
        """Take the wall off a city. Silent when there was none to take."""
        walls = self.walls_of(player_name)
        if vertex_key in walls:
            walls.remove(vertex_key)

    def wall_count(self, player_name: str) -> int:
        return len(self.walls_of(player_name))

    def city_wall_bonus(self, player_name: str) -> int:
        return self.wall_count(player_name) * CITY_WALL_HAND_BONUS

    def to_dict(self, viewer: str = None) -> dict:
        """Serialize for the client.

        Improvements, knights and the barbarian track are all public. Progress
        card *hands* are not: only the count goes to the table, and only the
        viewer's own cards are named.
        """
        return {
            "progress_hand": list(self.hand_of(viewer)) if viewer in self.progress_hands else [],
            "progress_hand_counts": {
                name: len(cards) for name, cards in self.progress_hands.items()
            },
            "progress_cards": {
                card["id"]: {
                    "name": card["name"],
                    "deck": card["deck"],
                    "summary": card["summary"],
                    "timing": card["timing"],
                    "needs_target": card["needs_target"],
                }
                for card in progress_cards.PROGRESS_CARDS
            },
            "improvements": self.improvements,
            "knights": {
                name: [k.to_dict() for k in knights] for name, knights in self.knights.items()
            },
            # Both shapes go out: the panel counts a player's walls, the board
            # has to know which cities carry one in order to draw them.
            "city_walls": {name: len(walls) for name, walls in self.city_walls.items()},
            "city_wall_vertices": {
                name: list(walls) for name, walls in self.city_walls.items()
            },
            "metropolis": self.metropolis,
            "metropolis_vertex": self.metropolis_vertex,
            "barbarian_position": self.barbarian_position,
            "barbarian_track_length": self.barbarian_track_length,
            "barbarians_have_attacked": self.barbarians_have_attacked,
            "last_event": self.last_event,
            "last_red_die": self.last_red_die,
            "defender_cards": self.defender_cards,
            "tracks": {
                track: {
                    "commodity": spec["commodity"],
                    "levels": spec["levels"],
                }
                for track, spec in IMPROVEMENT_TRACKS.items()
            },
        }
