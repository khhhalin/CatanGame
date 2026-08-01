"""
Player class for Catan game.
"""


class Player:
    """
    Represents a player in the game.

    Attributes:
        name (str): Player's unique identifier.
        color (str): Hex color code for visual representation.
        resources (dict): Resource cards held {resource_type: count}.
        settlements (list): Vertex keys where settlements are built.
        cities (list): Vertex keys where cities are built.
        roads (list): Edge keys where roads are built.
        victory_points (int): Total victory points.
    """

    def __init__(self, name: str, color: str = None):
        self.name = name
        self.color = color
        self.resources = {}
        # Cities & Knights only: cloth, coin and paper. Kept separate from
        # resources because they buy different things (improvements, not
        # buildings) and cannot be traded at a 2:1 resource harbour — but they
        # do count together with resources toward the discard limit on a 7.
        self.commodities = {}
        self.dev_cards = {
            'knight': {'count': 0, 'purchase_turn': None},
            'two_roads': {'count': 0, 'purchase_turn': None},
            'invention': {'count': 0, 'purchase_turn': None},
            'monopoly': {'count': 0, 'purchase_turn': None},
            'victory_point': {'count': 0, 'purchase_turn': None},
        }
        self.settlements = []
        self.cities = []
        self.roads = []
        self.victory_points = 0
        self.knights_played = 0  # Track Knight cards played for Largest Army

    def set_color(self, color: str):
        """Set or update the player's color."""
        self.color = color

    def total_resources(self) -> int:
        """Number of resource cards held, without revealing which."""
        return sum(self.resources.values())

    def total_commodities(self) -> int:
        """Number of commodity cards held, without revealing which."""
        return sum(self.commodities.values())

    def total_cards(self) -> int:
        """Everything that counts toward the hand limit on a 7."""
        return self.total_resources() + self.total_commodities()

    def total_dev_cards(self) -> int:
        """Number of development cards held, without revealing which."""
        return sum(card['count'] for card in self.dev_cards.values())

    def to_dict(
        self, longest_road_holder: str = None, largest_army_holder: str = None, viewer: str = None
    ) -> dict:
        """Convert player to dictionary for serialization.

        `viewer` is the player this payload is being built for. Hands are only
        included when a player is looking at themselves — everyone else sees a
        card count. Anything sent to a browser is readable in DevTools whatever
        the UI chooses to draw, so redaction has to happen here rather than in
        the client.
        """
        is_you = viewer is not None and viewer == self.name
        return {
            'name': self.name,
            'color': self.color,
            'is_you': is_you,
            'resources': self.resources if is_you else None,
            'dev_cards': self.dev_cards if is_you else None,
            'commodities': self.commodities if is_you else None,
            'resource_count': self.total_resources(),
            'commodity_count': self.total_commodities(),
            'dev_card_count': self.total_dev_cards(),
            'settlements': self.settlements,
            'cities': self.cities,
            'roads': self.roads,
            'victory_points': self.get_victory_points(longest_road_holder, largest_army_holder),
            'knights_played': self.knights_played,
        }

    def get_victory_points(
        self, longest_road_holder: str = None, largest_army_holder: str = None
    ) -> int:
        """Calculate total victory points.

        Args:
            longest_road_holder: Name of player holding longest road (2 bonus pts)
            largest_army_holder: Name of player holding largest army (2 bonus pts)
        """
        # Settlement: 1 point each
        # City: 2 points each (not 1+2, it replaces the settlement)
        # Victory Point cards: 1 point each (already played, not in hand)
        points = len(self.settlements) + (len(self.cities) * 2) + self.victory_points

        # Add bonus points for longest road and largest army
        if self.name == longest_road_holder:
            points += 2
        if self.name == largest_army_holder:
            points += 2

        return points

    def get_playable_dev_cards(self, current_turn: int) -> dict:
        """Get development cards that can be played (bought at least 1 turn ago)."""
        playable = {}
        for card_type, card_data in self.dev_cards.items():
            if card_data['count'] > 0 and card_data['purchase_turn'] is not None:
                if current_turn - card_data['purchase_turn'] >= 1:
                    playable[card_type] = card_data['count']
        return playable
