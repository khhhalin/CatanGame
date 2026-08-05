"""Harbor settlements, the Explorers & Pirates coastal upgrade.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. A harbor settlement is a settlement upgraded on the coast (2 grain and
2 ore) into a piece worth 2 victory points that carries a cargo basin — the one
site where ships, settlers and crews are later built (expansions.md 894-902).

It is not a branch inside `upgrade_city`: a city and a harbor settlement are two
different upgrades of a settlement, priced differently and scored differently,
and a table may play with either, both or neither. Every method here is gated on
`self.rules['harbor_settlements']`, never on an expansion name; harbor
settlements live on the players and the board, so — like commodities — they need
no `self.ep` container.
"""

from game.results import refused

# A harbor settlement is worth 2 victory points (expansions.md 894). Read by
# `Player.get_victory_points`, so the count is scored in exactly one place.
HARBOR_SETTLEMENT_VICTORY_POINTS = 2


class HarborSettlementRules:
    """Upgrading a coastal settlement into a harbor settlement."""

    def is_coastal_settlement_site(self, vertex_key: str) -> bool:
        """Whether a settlement here sits on the coast a harbor needs.

        Coastal is the ship geometry read from the intersection: at least one
        of the sides meeting here is a hex side a ship could lie on — land on
        one hand, sea on the other (`SeafarersRules.is_sea_edge`). Reusing that
        test rather than counting ocean hexes keeps the one definition of "where
        land meets sea" the rest of the engine already trusts.
        """
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return False
        return any(
            self.is_sea_edge(edge_key)
            for edge_key in vertex.neighbors.get('edges', [])
        )

    def build_harbor_settlement(self, player_name: str, vertex_key: str) -> dict:
        """Upgrade one of the player's coastal settlements into a harbor settlement.

        Mirrors `upgrade_city`: the same turn and ownership guards, a different
        price (2 grain + 2 ore), a different supply, and the coastal test a city
        never needs. The settlement piece is returned to the player's supply as
        the harbor settlement takes its place, exactly as a city upgrade returns
        the settlement.
        """
        if not self.rules['harbor_settlements']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with harbor settlements')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot build a harbor settlement during setup phase')

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can upgrade buildings')

        if not self.has_piece_available(player_name, 'harbor_settlement'):
            return refused(
                'NO_PIECES_LEFT',
                f'You have used all {self.MAX_HARBOR_SETTLEMENTS} harbor settlements',
            )

        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return refused('INVALID_TARGET', 'Invalid vertex')
        if vertex.building is None:
            return refused('INVALID_TARGET', 'No building at this location')
        if vertex.building.get('type') != 'settlement':
            return refused('INVALID_TARGET', 'Can only upgrade settlements to harbor settlements')
        if vertex.building.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'Can only upgrade your own settlements')

        if not self.is_coastal_settlement_site(vertex_key):
            return refused(
                'NOT_COASTAL', 'A harbor settlement must stand where land meets sea'
            )

        if not self.can_afford(player_name, 'harbor_settlement'):
            return refused('INSUFFICIENT_RESOURCES', self._cost_message('harbor_settlement'))
        self.deduct_cost(player_name, 'harbor_settlement')

        # The basin is where ships, settlers and crews are later loaded; it
        # starts empty, and the mechanics that fill it arrive in a later wave.
        vertex.building = {'type': 'harbor_settlement', 'player': player_name, 'basin': []}

        player = self.get_player(player_name)
        if player and vertex_key in player.settlements:
            player.settlements.remove(vertex_key)
            player.harbor_settlements.append(vertex_key)

        self.update_harbormaster()
        return {'success': True, 'error': ''}
