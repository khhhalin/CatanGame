"""Traders & Barbarians gold coins: the maritime sell rate that differs from
Explorers & Pirates gold.

The T&B coin currency lives in the same `Player.gold` field E&P gold uses, and
spends through the same `gold.py` helpers: `buy_resource_with_gold` (2 gold buy
any 1 resource, twice a turn) is shared, and the robber and Monopoly cannot
touch gold because it is a currency held apart from the resource hand, not a
card — that immunity is a property of the field, so nothing here re-implements
it.

What differs is the bank sell. E&P gold sells 3 identical resources for 1 gold
flat (`gold.py`); T&B coins are bought by *maritime* trade — 4 identical
resources for 1 coin, 3 with the matching 3:1 harbour, and never a 2:1
(expansions.md 562-564). That rate, gated on `gold_coins`, is the one method
here. The river and bridge coin *grants* live in `rivers.py`, where they hook
the build methods, and simply call `gain_gold`.
"""

from game.results import refused
from game.validation import RESOURCE_TYPES

# Maritime rates for buying 1 gold coin (expansions.md 562-563). The plain bank
# rate is 4 identical resources; a matching 3:1 (generic) harbour brings it to
# 3. A 2:1 harbour never applies — no 2:1 gold harbour was ever printed.
RESOURCES_FOR_ONE_COIN = 4
RESOURCES_FOR_ONE_COIN_WITH_HARBOUR = 3


class TBGoldRules:
    """The one coin action that is not shared with E&P gold: the maritime sell."""

    def coin_sell_rate(self, player_name: str) -> int:
        """How many identical resources buy 1 gold coin for this player.

        4 at the plain bank rate, 3 if they own a generic 3:1 harbour. A 2:1
        harbour is deliberately ignored: there is no 2:1 gold harbour, so a
        resource harbour never cheapens a coin (expansions.md 564).
        """
        if self.get_player_ports(player_name).get('generic'):
            return RESOURCES_FOR_ONE_COIN_WITH_HARBOUR
        return RESOURCES_FOR_ONE_COIN

    def sell_resources_for_gold_coins(self, player_name: str, resource: str) -> dict:
        """Buy 1 gold coin from the bank with identical resources (562-563).

        Maritime trade, so the rate follows the player's harbours: 4 normally, 3
        with the matching 3:1. Unlike the buy, there is no per-turn cap in the
        rulebook, and none is imposed here — a coin costs four cards, which is
        its own brake.
        """
        if not self.rules['gold_coins']:
            return refused('RULE_OFF', 'Gold coins are not in play')
        player = self.get_player(player_name)
        if not player:
            return refused('NO_SUCH_PLAYER', 'No such player')
        if resource not in RESOURCE_TYPES:
            return refused('INVALID_RESOURCE', f'{resource} is not a resource')
        rate = self.coin_sell_rate(player_name)
        if player.resources.get(resource, 0) < rate:
            return refused(
                'INSUFFICIENT_RESOURCES',
                f'You need {rate} {resource} to buy 1 gold coin',
            )
        player.resources[resource] -= rate
        self.bank.return_resources(resource, rate)
        self.gain_gold(player_name, 1)
        return {'success': True, 'error': '', 'gold': player.gold, 'rate': rate}
