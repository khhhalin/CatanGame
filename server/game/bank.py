import random


class Bank:
    """Manages the resource bank for Catan game."""

    def __init__(self, resource_limit: int = 19, rng: random.Random = None,
                 dev_card_deck: dict = None):
        self.rng = rng or random.SystemRandom()
        self.resource_limit = resource_limit
        self.resources = {
            'wood': resource_limit,
            'brick': resource_limit,
            'sheep': resource_limit,
            'wheat': resource_limit,
            'ore': resource_limit
        }
        # Composition comes from the chosen rules so a table can change the odds
        # (or remove a card type entirely); these are the box defaults.
        self.dev_cards_deck = dict(dev_card_deck) if dev_card_deck else {
            'knight': 14,
            'two_roads': 2,
            'invention': 2,
            'monopoly': 2,
            'victory_point': 5
        }
    
    def take(self, resource_type: str, amount: int = 1) -> bool:
        """Take resources from bank. Returns True if successful, False if insufficient."""
        if self.resources.get(resource_type, 0) >= amount:
            self.resources[resource_type] -= amount
            return True
        return False
    
    def return_resources(self, resource_type: str, amount: int = 1):
        """Return resources to bank (up to resource_limit)."""
        self.resources[resource_type] = min(
            self.resources.get(resource_type, 0) + amount,
            self.resource_limit
        )
    
    def get_all(self) -> dict:
        """Get copy of all bank resources."""
        return self.resources.copy()
    
    def draw_dev_card(self) -> str | None:
        """Draw a development card from the deck. Returns card type or None if deck empty.

        Weighted by how many of each type remain, so a knight (14 in the deck)
        is seven times likelier than a monopoly (2). Picking uniformly among the
        *distinct* remaining types would make every type equally likely and hand
        out victory point and monopoly cards far above their real rate.
        """
        remaining = [
            (card_type, count)
            for card_type, count in self.dev_cards_deck.items()
            if count > 0
        ]
        if not remaining:
            return None

        card_type = self.rng.choices(
            [card_type for card_type, _ in remaining],
            weights=[count for _, count in remaining],
            k=1,
        )[0]
        self.dev_cards_deck[card_type] -= 1
        return card_type

    def total_dev_cards_remaining(self) -> int:
        """Number of development cards left, without revealing the composition."""
        return sum(self.dev_cards_deck.values())
    
    def return_dev_card(self, card_type: str):
        """Return a development card to the deck."""
        if card_type in self.dev_cards_deck:
            self.dev_cards_deck[card_type] += 1
    
    def get_dev_card_counts(self) -> dict:
        """Get copy of dev card deck counts."""
        return self.dev_cards_deck.copy()
    
    def __str__(self) -> str:
        """String representation for logging."""
        return ', '.join(f"{count} {resource}" 
                        for resource, count in self.resources.items())
