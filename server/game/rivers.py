"""The Rivers of Catan: river coin grants, bridges, and the two scoring tiles.

One mixin on `Game`, the pattern the other expansion modules use. Every method
is gated on the individual rule that governs it — `river_gold`, `bridges`,
`wealthiest_settler`, `poor_settler` — so a table not running Rivers is
untouched and the base game is byte-for-byte unchanged.

The mechanics (expansions.md 527-570):

- A settlement built adjacent to a river hex, or a road built on a path adjacent
  to a river hex, pays 1 gold coin at once — during set-up as well as later; a
  city upgrade pays nothing (`grant_river_settlement_gold`, `grant_river_road_gold`).
- A bridge (2 brick, 1 lumber) is built only on one of the board's river-crossing
  bridge sites, pays 3 gold coins, counts as a road for the Longest Road and for
  connection, and each player may build at most `max_bridges` (`build_bridge`). A
  normal road may never sit on a bridge site, and Road Building may not place a
  bridge (both refused in `build_road`).
- The Wealthiest Settler tile (+1 VP) is held by the one player who alone has the
  most coins; the Poor Settler tile (-2 VP) by every player tied for the fewest.
  Both are dynamic — recomputed from the coin totals whenever they are read
  (`holds_wealthiest_settler`, `holds_poor_settler`) and folded into
  `victory_points_for` behind their flags.
"""

from game.results import refused

# A bridge costs 2 brick and 1 lumber (expansions.md 550). Not in the building
# registry because a bridge is not a flat build button — it is priced here, at
# the one place it is charged.
BRIDGE_COST = {'brick': 2, 'wood': 1}

# What a bridge build pays, and the tile swings (expansions.md 550, 556-557).
GOLD_PER_BRIDGE = 3
WEALTHIEST_SETTLER_VP = 1
POOR_SETTLER_VP = -2


class RiversRules:
    """River coin grants, bridges, and the Wealthiest/Poor Settler tiles."""

    # --- River adjacency ---------------------------------------------------

    def _is_river_hex(self, hex_key: str) -> bool:
        hex_obj = self.hexes.get(hex_key)
        return hex_obj is not None and hex_obj.type == 'river'

    def _touches_river(self, hex_keys) -> bool:
        return any(self._is_river_hex(key) for key in hex_keys)

    def grant_river_settlement_gold(self, player_name: str, vertex_key: str) -> int:
        """Pay 1 gold for a settlement adjacent to a river hex (542).

        Called after a settlement is placed — set-up and later both. A no-op
        without `river_gold`; nothing is paid for a city upgrade because the
        upgrade path never calls this. Returns the coins granted.
        """
        if not self.rules['river_gold']:
            return 0
        vertex = self.vertices.get(vertex_key)
        if vertex is None or not self._touches_river(vertex.neighbors.get('hexes', [])):
            return 0
        self.gain_gold(player_name, 1)
        return 1

    def grant_river_road_gold(self, player_name: str, edge_key: str) -> int:
        """Pay 1 gold for a road on a path adjacent to a river hex (543).

        Called after a road is built — set-up and later both. A no-op without
        `river_gold`. A bridge pays through `build_bridge` instead, so this is
        only ever reached for a normal road. Returns the coins granted.
        """
        if not self.rules['river_gold']:
            return 0
        edge = self.edges.get(edge_key)
        if edge is None or not self._touches_river(edge.neighbors.get('hexes', [])):
            return 0
        self.gain_gold(player_name, 1)
        return 1

    # --- Bridges -----------------------------------------------------------

    def is_bridge_site(self, edge_key: str) -> bool:
        """Whether this path is one of the board's river-crossing bridge sites."""
        return edge_key in self.bridge_sites

    def player_bridge_count(self, player_name: str) -> int:
        """How many bridges this player has on the board — a bridge is a road
        piece carrying `kind='bridge'`, counted off the edges."""
        return sum(
            1 for edge in self.edges.values()
            if edge.road and edge.road.get('kind') == 'bridge'
            and edge.road.get('player') == player_name
        )

    def build_bridge(self, player_name: str, edge_key: str) -> dict:
        """Build a bridge on a river-crossing site (546-552).

        A bridge is a road piece (`edge.road` with `kind='bridge'`), so the
        Longest Road and the connection check count it with no special case. It
        may only go on a bridge site, must connect to the player's network, costs
        2 brick + 1 lumber, pays 3 gold, and each player may build at most
        `max_bridges`.
        """
        if not self.rules['bridges']:
            return refused('RULE_OFF', 'Bridges are not in play')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked
        moved = self.movement_phase_block()
        if moved is not None:
            return moved

        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'Bridges are built after set-up')
        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can build')

        edge = self.edges.get(edge_key)
        if edge is None:
            return refused('INVALID_TARGET', 'Invalid edge')
        if not self.is_bridge_site(edge_key):
            return refused('INVALID_PLACEMENT', 'A bridge may only span a bridge site')
        if edge.road is not None:
            return refused('OCCUPIED', 'This site already carries a bridge or road')
        if edge.ship is not None:
            return refused('OCCUPIED', 'This side already carries a ship')
        if not self._road_connects(player_name, edge_key):
            return refused('INVALID_PLACEMENT',
                           'A bridge must connect to your own road or building')
        if self.player_bridge_count(player_name) >= self.rules['max_bridges']:
            return refused('NO_PIECES_LEFT',
                           f'You have built all {self.rules["max_bridges"]} bridges')

        player = self.get_player(player_name)
        if player is None:
            return refused('NO_SUCH_PLAYER', 'No such player')
        if any(player.resources.get(res, 0) < qty for res, qty in BRIDGE_COST.items()):
            return refused('INSUFFICIENT_RESOURCES', 'A bridge costs 2 brick and 1 lumber')
        for res, qty in BRIDGE_COST.items():
            player.resources[res] -= qty
            self.bank.return_resources(res, qty)

        edge.road = {'player': player_name, 'kind': 'bridge'}
        if edge_key not in player.roads:
            player.roads.append(edge_key)

        self.gain_gold(player_name, GOLD_PER_BRIDGE)
        self.update_longest_road()
        return {'success': True, 'error': '', 'gold': player.gold,
                'bridges': self.player_bridge_count(player_name)}

    # --- The Wealthiest and Poor Settler tiles -----------------------------

    def _coin_totals(self) -> dict:
        return {player.name: player.gold for player in self.players}

    def holds_wealthiest_settler(self, player_name: str) -> bool:
        """Whether this player alone holds the most gold coins (556-557).

        Lost the moment another player equals or passes them, so a tie leaves
        the tile with nobody. Read live off the coin totals.
        """
        if not self.rules['wealthiest_settler']:
            return False
        totals = self._coin_totals()
        mine = totals.get(player_name, 0)
        return all(mine > gold for name, gold in totals.items() if name != player_name)

    def holds_poor_settler(self, player_name: str) -> bool:
        """Whether this player is (tied for) the fewest gold coins (553-555).

        Every player tied for the fewest holds one, a tie at zero included — but
        "fewest" is only meaningful when someone has more. When every player is
        level (the whole table at the same total, the game's opening among them)
        nobody is poorer than anybody, so no tile is out, mirroring the way the
        Wealthiest tile needs a sole leader.
        """
        if not self.rules['poor_settler']:
            return False
        totals = self._coin_totals()
        if player_name not in totals:
            return False
        fewest = min(totals.values())
        if fewest == max(totals.values()):
            return False
        return totals[player_name] == fewest

    def river_tile_points(self, player_name: str) -> int:
        """The victory points the two Rivers tiles add for this player.

        Folded into `victory_points_for` behind the two flags: +1 for the
        Wealthiest Settler, -2 for the Poor Settler. Recomputed on every read, so
        the tiles move the instant the coin totals change.
        """
        points = 0
        if self.holds_wealthiest_settler(player_name):
            points += WEALTHIEST_SETTLER_VP
        if self.holds_poor_settler(player_name):
            points += POOR_SETTLER_VP
        return points
