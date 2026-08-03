"""Development cards: buying them, playing them, and their follow-ups.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. A card that grants a follow-up action (Invention, Monopoly) records who
is owed it on the Game, which is why these methods stay mixed into it.
"""

import logging

from game.results import refused

logger = logging.getLogger(__name__)


class DevCardRules:
    """The development card deck's rules, from purchase to effect."""

    def buy_dev_card(self, player_name: str) -> dict:
        """Buy a development card from the bank. Returns result dict."""
        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot buy development cards during setup')

        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can buy development cards')

        player = self.get_player(player_name)
        if not player:
            return refused('ACTION_FAILED', 'Player not found')

        if not self.can_afford(player_name, 'knight'):
            return refused('ACTION_FAILED', 'Cannot afford development card')

        card_type = self.bank.draw_dev_card()
        if not card_type:
            return refused('ACTION_FAILED', 'No development cards left')

        if not self.deduct_cost(player_name, 'knight'):
            self.bank.return_dev_card(card_type)
            return refused('ACTION_FAILED', 'Failed to deduct cost')

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
            return refused('NO_PENDING_INVENTION', 'You have not played an Invention card')

        if sum(resources.values()) != 2:
            return refused('INVALID_PAYLOAD', 'Invention gives exactly 2 resources')

        player = self.get_player(player_name)
        if not player:
            return refused('INVALID_TARGET', 'Unknown player')

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
            return refused('NO_PENDING_MONOPOLY', 'You have not played a Monopoly card')

        # Spent the moment it is redeemed, however the redemption turns out —
        # a failed declaration must not leave a second one available.
        self.pending_monopoly = None

        player = self.get_player(player_name)
        if not player:
            return refused('ACTION_REJECTED', 'Player not found')

        if resource_type not in self.bank.resources:
            return refused('ACTION_REJECTED', 'Invalid resource type')

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
            self.rules['dev_card_hold_a_turn']
            and card_data['purchase_turn'] is not None
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
            return refused('WRONG_PHASE', 'Cannot play development cards during setup')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can play development cards')

        # A Knight may be played while the robber is still owed — that is how a
        # player reassigns it. Nothing else may.
        if card_type != 'knight' and self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')

        can_play, error = self.can_play_dev_card(player_name, card_type)
        if not can_play:
            return refused('ACTION_REJECTED', error)

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
