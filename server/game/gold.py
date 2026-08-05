"""Gold, the Explorers & Pirates second currency.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. Gold is a currency, not a card: it lives in `Player.gold`, never in the
resource hand, so it does not count toward the discard limit on a 7
(expansions.md 842, 960) and the robber has no purchase on it.

Every action here is gated on `self.rules['gold']`, never on an expansion name.
The empty-roll bonus and the gold-field payout are folded into a production roll
by `distribute_resources`; the two supply conversions are turn actions a handler
drives, each capped per turn.
"""

from game.results import refused
from game.validation import RESOURCE_TYPES

# One gold when a non-7 production roll pays you no resource cards
# (expansions.md 854, 961).
GOLD_PER_EMPTY_ROLL = 1

# A liberated gold field pays 2 gold for every settlement bordering it, per
# building (expansions.md 998). Read by the `gold_field` PRODUCTION modifier.
GOLD_PER_GOLD_FIELD_BUILDING = 2

# The two supply conversions (expansions.md 855, 856).
RESOURCES_FOR_ONE_GOLD = 3   # 3 identical resources -> 1 gold
GOLD_FOR_ONE_RESOURCE = 2    # 2 gold -> any 1 resource

# Per-turn caps. The buy is capped at twice per turn by the rulebook explicitly
# (856). The sell has no printed cap; it is capped here as well so a turn cannot
# grind an unbounded pile of gold out of a large hand, and because the task that
# specified this mechanic asked for both to be capped. Change the sell cap here
# if a rulebook reading says otherwise — it is a house choice, not a printed one.
MAX_GOLD_SELLS_PER_TURN = 2
MAX_GOLD_BUYS_PER_TURN = 2


class GoldRules:
    """Gaining, spending and converting gold.

    Mixed onto Game because every method reaches into the players and the bank.
    The per-turn conversion counts live on the game (`self.gold_conversions`),
    reset at the top of each turn like the other per-turn flags.
    """

    def gain_gold(self, player_name: str, amount: int):
        """Add gold to a player's purse from the supply."""
        player = self.get_player(player_name)
        if player and amount:
            player.gold += amount

    def spend_gold(self, player_name: str, amount: int) -> bool:
        """Return gold to the supply, if the player has it. False if they don't."""
        player = self.get_player(player_name)
        if not player or player.gold < amount:
            return False
        player.gold -= amount
        return True

    def pay_empty_roll_gold(self, produced_resources: dict) -> dict:
        """Grant 1 gold to every player a non-7 roll paid no resource cards.

        `produced_resources` is what the production walk handed out — a player
        absent from it collected nothing, so they are compensated (854). Gold
        already handed out by a gold field is a currency, not a resource card,
        so it does not spare a player the bonus. Returns {player: gold granted}.
        """
        if not self.rules['gold']:
            return {}
        granted = {}
        for player in self.players:
            if player.name not in produced_resources:
                self.gain_gold(player.name, GOLD_PER_EMPTY_ROLL)
                granted[player.name] = GOLD_PER_EMPTY_ROLL
        return granted

    def _gold_conversions_this_turn(self, player_name: str) -> dict:
        return self.gold_conversions.setdefault(player_name, {'sells': 0, 'buys': 0})

    def sell_resources_for_gold(self, player_name: str, resource: str) -> dict:
        """Pay 3 identical resources to the supply for 1 gold (855)."""
        if not self.rules['gold']:
            return refused('RULE_OFF', 'Gold is not in play')
        player = self.get_player(player_name)
        if not player:
            return refused('NO_SUCH_PLAYER', 'No such player')
        counts = self._gold_conversions_this_turn(player_name)
        if counts['sells'] >= MAX_GOLD_SELLS_PER_TURN:
            return refused(
                'GOLD_LIMIT',
                f'You may sell resources for gold at most {MAX_GOLD_SELLS_PER_TURN} times per turn',
            )
        if player.resources.get(resource, 0) < RESOURCES_FOR_ONE_GOLD:
            return refused(
                'INSUFFICIENT_RESOURCES',
                f'You need {RESOURCES_FOR_ONE_GOLD} {resource} to buy 1 gold',
            )
        player.resources[resource] -= RESOURCES_FOR_ONE_GOLD
        self.bank.return_resources(resource, RESOURCES_FOR_ONE_GOLD)
        self.gain_gold(player_name, 1)
        counts['sells'] += 1
        return {'success': True, 'error': '', 'gold': player.gold}

    def buy_resource_with_gold(self, player_name: str, resource: str) -> dict:
        """Pay 2 gold to the supply for any 1 resource, twice a turn (856)."""
        if not self.rules['gold']:
            return refused('RULE_OFF', 'Gold is not in play')
        player = self.get_player(player_name)
        if not player:
            return refused('NO_SUCH_PLAYER', 'No such player')
        if resource not in RESOURCE_TYPES:
            return refused('INVALID_RESOURCE', f'{resource} is not a resource')
        counts = self._gold_conversions_this_turn(player_name)
        if counts['buys'] >= MAX_GOLD_BUYS_PER_TURN:
            return refused(
                'GOLD_LIMIT',
                f'You may buy a resource with gold at most {MAX_GOLD_BUYS_PER_TURN} times per turn',
            )
        if player.gold < GOLD_FOR_ONE_RESOURCE:
            return refused('INSUFFICIENT_GOLD', f'You need {GOLD_FOR_ONE_RESOURCE} gold')
        if not self.bank.take(resource):
            return refused('BANK_EMPTY', f'The bank has no {resource} left')
        self.spend_gold(player_name, GOLD_FOR_ONE_RESOURCE)
        player.resources[resource] = player.resources.get(resource, 0) + 1
        counts['buys'] += 1
        return {'success': True, 'error': '', 'gold': player.gold}
