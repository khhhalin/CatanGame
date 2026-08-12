"""Traders & Barbarians main scenario: the wagons, the deliveries, the deck.

One mixin on `Game`, the pattern the other expansion modules use. Every method
is gated on the `trade_caravans` rule (or its siblings), so a table not running
the main scenario is untouched and the base game is byte-for-byte unchanged. The
scenario's own state — each player's wagon and the commodity it carries, the
baggage-train levels, the trade-hex commodity stacks and the scenario deck —
lives on `self.tb` (see game/tb.py) so it persists.

The mechanics (expansions.md 696-748):

- A wagon starts on its owner's city and, after trading and building, moves
  intersection to intersection along paths, spending movement points: 2 for a
  bare path, 1 for one of the player's own roads, 1 plus 1 gold to the owner for
  a rival's road, and 2 more for any path a roaming barbarian sits on. A grain
  buys 2 more points once a turn.
- Reaching a trade hex (castle, quarry or glassworks) that matches the commodity
  the wagon carries delivers it face down — worth 1 victory point and the gold on
  the active baggage-train card — and the wagon draws the next commodity, which
  names its next destination. Arriving carrying nothing (the very first visit)
  just draws a commodity.
- The baggage-train card is upgraded during trading and building; each upgrade
  raises the wagon's movement points, the delivery gold and the die faces that
  drive off a barbarian, and the fifth is worth 1 victory point.
- The scenario's own development deck (game/tb_decks.py) replaces the base deck.

The "central plaza" of the printed trade hex — a vertex at the hex's centre
reached by four interior paths — is modelled here as one designated land corner
of the trade hex (its `plaza`), so no new board topology is needed: the wagon
delivers when it stops on that corner. This is the one deliberate simplification
of the printed board; the delivery, movement-point and scoring mechanics are
faithful.
"""

from game import tb_decks
from game.results import refused

# The baggage-train ladder (expansions.md 720-726). Five cards; each upgrade
# raises the wagon's movement points, the delivery gold, and the die faces that
# drive off a barbarian. expansions.md pins the endpoints — points 4 up to 7,
# gold 1 up to 5, card 5 worth a victory point, no drive-off until the first
# upgrade — but not each card's exact numbers or upgrade cost, so the
# intermediate values below are a faithful ladder documented as an assumption and
# pinned by a test against what the engine actually reads.
MAX_BAGGAGE_LEVEL = 5
# Level -> movement-point bonus over the `wagon_movement_points` rule (its
# default, 4, is level 1's value): 4, 5, 6, 6, 7 across the five cards.
BAGGAGE_POINT_BONUS = {1: 0, 2: 1, 3: 2, 4: 2, 5: 3}
# Level -> gold each delivery pays (1..5).
BAGGAGE_GOLD = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
# Level -> the die faces that drive off a barbarian. Card 1 cannot (you must
# upgrade at least once, expansions.md 731); each later card widens the range.
BAGGAGE_DRIVE_NUMBERS = {1: (), 2: (6,), 3: (5, 6), 4: (4, 5, 6), 5: (3, 4, 5, 6)}
# Level reached -> the resources its upgrade costs, paid off the card's back.
BAGGAGE_UPGRADE_COST = {
    2: {'wood': 1, 'brick': 1},
    3: {'sheep': 1, 'wheat': 1},
    4: {'ore': 2},
    5: {'wheat': 2, 'ore': 1},
}

# Movement-point costs (expansions.md 705-712).
BARE_PATH_COST = 2
ROAD_PATH_COST = 1
RIVAL_ROAD_GOLD = 1
BARBARIAN_CROSS_SURCHARGE = 2
GRAIN_BOOST_POINTS = 2

TRADE_HEX_TYPES = ('castle', 'quarry', 'glassworks')


class WagonRules:
    """The wagon run: placement, movement, delivery, the baggage train, the deck."""

    # --- Board setup -------------------------------------------------------

    def setup_wagons_board(self):
        """Read the three trade hexes and the barbarian paths off the dealt map.

        A no-op without `trade_caravans` or a state container, and for every board
        that prints no trade hex, so the base game is untouched. Each trade hex's
        plaza (a land corner where the wagon delivers) and its sea-border paths
        (where no road may sit) are derived from the board geometry; its face-down
        commodity stack is built from what the hex exports (game/tb_decks.py).
        """
        self.trade_plazas = set()
        self.trade_sea_paths = set()
        if not self.rules['trade_caravans'] or self.tb is None:
            return

        for hex_key, hex_obj in sorted(self.hexes.items()):
            if hex_obj.type not in TRADE_HEX_TYPES:
                continue
            plaza = self._trade_plaza_vertex(hex_key)
            sea_paths = self._trade_sea_paths(hex_key)
            self.tb.trade_hexes[hex_key] = {
                'type': hex_obj.type,
                'plaza': plaza,
                'sea_paths': sea_paths,
            }
            self.tb.trade_hex_stacks[hex_key] = tb_decks.build_commodity_stack(
                hex_obj.type, self.rng)
            if plaza is not None:
                self.trade_plazas.add(plaza)
            self.trade_sea_paths.update(sea_paths)

        # The scenario deck is the `trade_dev_deck` rule's doing — it replaces the
        # base deck (rules.dev_deck_in_play) — so it is dealt only when that switch
        # is on. The dependency ties it to the wagon run, so they are always on
        # together in practice.
        if self.rules['trade_dev_deck']:
            self.tb.td_deck = tb_decks.build_trade_deck(self.rng)
            self.tb.td_discard = []
            self.tb.td_pending = None

        # The three roaming barbarians on their printed paths.
        if self.rules['roaming_barbarians'] and self.map_definition is not None:
            for key in getattr(self.map_definition, 'barbarian_paths', ()):
                canonical = self.canonical_edge_key(key)
                if canonical is not None:
                    self.tb.path_barbarians.add(canonical)

    def _trade_plaza_vertex(self, hex_key: str):
        """The land corner of a trade hex a wagon delivers on.

        The printed plaza is at the hex's centre; modelled here as one corner
        deterministically chosen so delivery has a real board vertex. A fully
        inland corner (no sea neighbour) is preferred so a delivery point is never
        a coastal build spot; failing that, the sorted-first corner is used.
        """
        corners = sorted(
            key for key, vertex in self.vertices.items()
            if hex_key in vertex.neighbors.get('hexes', [])
        )
        for corner in corners:
            neighbours = self.vertices[corner].neighbors.get('hexes', [])
            if len(neighbours) == 3 and not any(
                    self._is_sea_hex(k) for k in neighbours):
                return corner
        return corners[0] if corners else None

    def _trade_sea_paths(self, hex_key: str) -> list:
        """The trade hex's paths that border the sea — no road may sit on them."""
        sea_paths = []
        for edge_key, edge in self.edges.items():
            hexes = edge.neighbors.get('hexes', [])
            if hex_key not in hexes:
                continue
            other = [k for k in hexes if k != hex_key]
            if not other or all(self._is_sea_hex(k) for k in other):
                sea_paths.append(edge_key)
        return sorted(sea_paths)

    def _is_sea_hex(self, hex_key: str) -> bool:
        hex_obj = self.hexes.get(hex_key)
        return hex_obj is not None and hex_obj.type in ('ocean', 'sea')

    def place_starting_wagons(self):
        """Put each player's wagon on their starting city (expansions.md 701).

        Called once setup finishes. A player's starting city is the city
        `setup_second_city` places; if a table runs the wagon without that rule,
        the wagon goes on their first settlement instead so it still has a home. A
        no-op without the rule.
        """
        if not self.rules['trade_caravans'] or self.tb is None:
            return
        for player in self.players:
            if self.tb.wagons.get(player.name) is not None:
                continue
            city = next((key for key, vertex in sorted(self.vertices.items())
                         if vertex.building
                         and vertex.building.get('player') == player.name
                         and vertex.building.get('type') == 'city'), None)
            home = city or next(
                (key for key, vertex in sorted(self.vertices.items())
                 if vertex.building
                 and vertex.building.get('player') == player.name), None)
            self.tb.wagons[player.name] = home

    # --- Build guards ------------------------------------------------------

    def trade_hex_settlement_refusal(self, vertex_key: str):
        """Refuse a settlement or city on a trade hex's plaza (expansions.md 699)."""
        if not self.rules['trade_caravans'] or self.tb is None:
            return None
        if vertex_key in self.trade_plazas:
            return refused('TRADE_PLAZA',
                           'You cannot build on a trade hex plaza')
        return None

    def trade_hex_road_refusal(self, edge_key: str):
        """Refuse a road on a trade hex's sea-border path (expansions.md 700)."""
        if not self.rules['trade_caravans'] or self.tb is None:
            return None
        if edge_key in self.trade_sea_paths:
            return refused('TRADE_SEA_PATH',
                           'You cannot build a road on a trade hex sea path')
        return None

    # --- The baggage train -------------------------------------------------

    def wagon_movement_value(self, player_name: str) -> int:
        """This player's wagon movement points from their baggage-train card."""
        level = self.tb.baggage_level.get(player_name, 1) if self.tb else 1
        return self.rules['wagon_movement_points'] + BAGGAGE_POINT_BONUS.get(level, 0)

    def wagon_delivery_gold(self, player_name: str) -> int:
        """The gold this player's baggage-train card pays for a delivery."""
        level = self.tb.baggage_level.get(player_name, 1) if self.tb else 1
        return BAGGAGE_GOLD.get(level, 1)

    def upgrade_baggage_train(self, player_name: str) -> dict:
        """Upgrade the baggage train one card, paying the next card's cost (720).

        During trading and building only, by the current player, once they have
        rolled. The fifth card is worth a victory point (counted in scoring). A
        no-op-refusal without the rule.
        """
        if not self.rules['baggage_train'] or self.tb is None:
            return refused('RULE_OFF', 'The baggage train is not in play')
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'Upgrade after set-up')
        if self.current_player_name() != player_name:
            return refused('NOT_YOUR_TURN', 'It is not your turn')
        if not self.has_rolled_dice:
            return refused('MUST_ROLL_FIRST', 'Roll the dice before upgrading')

        level = self.tb.baggage_level.get(player_name, 1)
        if level >= MAX_BAGGAGE_LEVEL:
            return refused('MAX_LEVEL', 'Your baggage train is fully upgraded')
        next_level = level + 1
        cost = BAGGAGE_UPGRADE_COST[next_level]
        player = self.get_player(player_name)
        if any(player.resources.get(res, 0) < amount for res, amount in cost.items()):
            return refused('INSUFFICIENT_RESOURCES',
                           'You cannot afford the baggage-train upgrade')
        for res, amount in cost.items():
            player.resources[res] -= amount
            self.bank.return_resources(res, amount)
        self.tb.baggage_level[player_name] = next_level
        return {'success': True, 'error': '', 'level': next_level,
                'movement_points': self.wagon_movement_value(player_name),
                'delivery_gold': self.wagon_delivery_gold(player_name)}

    # --- Wagon movement ----------------------------------------------------

    def _wagon_points_left(self, player_name: str) -> int:
        """This turn's remaining movement points, initialised on first use."""
        if self.wagon_points_left is None:
            self.wagon_points_left = self.wagon_movement_value(player_name)
        return self.wagon_points_left

    def wagon_step_cost(self, player_name: str, edge_key: str) -> int:
        """What crossing this path costs the wagon in movement points (705-712)."""
        edge = self.edges.get(edge_key)
        cost = BARE_PATH_COST
        if edge is not None and edge.road is not None:
            cost = ROAD_PATH_COST
        if self.rules['roaming_barbarians'] and edge_key in self.tb.path_barbarians:
            cost += BARBARIAN_CROSS_SURCHARGE
        return cost

    def boost_wagon(self, player_name: str) -> dict:
        """Pay 1 grain for 2 more movement points this turn (expansions.md 713)."""
        if not self.rules['trade_caravans'] or self.tb is None:
            return refused('RULE_OFF', 'The wagon is not in play')
        if self.current_player_name() != player_name:
            return refused('NOT_YOUR_TURN', 'It is not your turn')
        if not self.has_rolled_dice:
            return refused('MUST_ROLL_FIRST', 'Roll the dice first')
        if self.wagon_grain_used:
            return refused('ALREADY_BOOSTED', 'You have already bought movement this turn')
        player = self.get_player(player_name)
        if player.resources.get('wheat', 0) < 1:
            return refused('INSUFFICIENT_RESOURCES', 'A boost costs 1 grain')
        player.resources['wheat'] -= 1
        self.bank.return_resources('wheat', 1)
        self.wagon_grain_used = True
        self.wagon_points_left = self._wagon_points_left(player_name) + GRAIN_BOOST_POINTS
        return {'success': True, 'error': '', 'points_left': self.wagon_points_left}

    def move_wagon(self, player_name: str, to_vertex: str) -> dict:
        """Move the wagon one path to an adjacent intersection (expansions.md 702).

        Spends the path's movement points, pays 1 gold for a rival's road, and
        stops — ending movement — the moment it steps onto a trade hex plaza,
        delivering the carried commodity or drawing the first one. Only the
        current player, only after rolling.
        """
        if not self.rules['trade_caravans'] or self.tb is None:
            return refused('RULE_OFF', 'The wagon is not in play')
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'Move the wagon after set-up')
        if self.current_player_name() != player_name:
            return refused('NOT_YOUR_TURN', 'It is not your turn')
        if not self.has_rolled_dice:
            return refused('MUST_ROLL_FIRST', 'Roll the dice before moving')
        if self.must_move_barbarian or self.tb.td_pending is not None:
            return refused('MUST_MOVE_BARBARIAN', 'Move the barbarian first')

        current = self.tb.wagons.get(player_name)
        if current is None:
            return refused('NO_WAGON', 'Your wagon is not placed')
        origin = self.vertices.get(current)
        if origin is None or to_vertex not in origin.neighbors.get('vertices', []):
            return refused('INVALID_TARGET', 'That intersection is not adjacent')

        edge_key = self._edge_between(current, to_vertex)
        if edge_key is None:
            return refused('INVALID_TARGET', 'No path connects those intersections')

        cost = self.wagon_step_cost(player_name, edge_key)
        points = self._wagon_points_left(player_name)
        if cost > points:
            return refused('OUT_OF_POINTS', 'Not enough movement points to cross that path')

        edge = self.edges[edge_key]
        toll_owner = None
        if edge.road is not None and edge.road.get('player') != player_name:
            toll_owner = edge.road['player']
            player = self.get_player(player_name)
            if player.gold < RIVAL_ROAD_GOLD:
                return refused('INSUFFICIENT_GOLD',
                               'Crossing a rival road costs 1 gold')

        # Commit the move.
        if toll_owner is not None:
            self.spend_gold(player_name, RIVAL_ROAD_GOLD)
            self.gain_gold(toll_owner, RIVAL_ROAD_GOLD)
        self.wagon_points_left = points - cost
        self.tb.wagons[player_name] = to_vertex
        self.turn_phase = 'movement'

        delivery = None
        if to_vertex in self.trade_plazas:
            # Reaching a plaza ends the movement (expansions.md 708).
            self.wagon_points_left = 0
            delivery = self._wagon_reached_plaza(player_name, to_vertex)

        return {'success': True, 'error': '', 'to': to_vertex,
                'points_left': self.wagon_points_left,
                'toll_paid_to': toll_owner, 'delivery': delivery}

    def _edge_between(self, from_vertex: str, to_vertex: str):
        """The edge joining two adjacent vertices, or None."""
        origin = self.vertices.get(from_vertex)
        if origin is None:
            return None
        for edge_key in origin.neighbors.get('edges', []):
            edge = self.edges.get(edge_key)
            if edge and to_vertex in edge.neighbors.get('vertices', []):
                return edge_key
        return None

    def _trade_hex_of_type(self, hex_type: str):
        """The trade-hex key of a given type (castle/quarry/glassworks)."""
        return next((key for key, meta in self.tb.trade_hexes.items()
                     if meta['type'] == hex_type), None)

    def _wagon_reached_plaza(self, player_name: str, vertex_key: str) -> dict:
        """Deliver, or draw the first commodity, when a wagon stops on a plaza.

        Which trade hex the plaza belongs to decides everything (expansions.md
        707-719): carrying nothing draws a commodity for no gold; carrying the
        commodity this hex accepts delivers it — a victory point and the baggage
        card's gold — then draws the next; carrying a commodity this hex does not
        accept does nothing.
        """
        hex_key = next((key for key, meta in self.tb.trade_hexes.items()
                        if meta['plaza'] == vertex_key), None)
        if hex_key is None:
            return None
        hex_type = self.tb.trade_hexes[hex_key]['type']
        carried = self.tb.carried_commodity.get(player_name)

        if carried is None:
            drawn = self._draw_commodity(hex_key)
            return {'hex': hex_key, 'picked_up': drawn, 'gold': 0}

        if tb_decks.DELIVERY_TARGET.get(carried) != hex_type:
            return {'hex': hex_key, 'delivered': None}

        # A delivery: the token goes face down (a victory point) and pays gold.
        self.tb.delivered.setdefault(player_name, []).append(carried)
        gold = self.wagon_delivery_gold(player_name)
        self.gain_gold(player_name, gold)
        self.tb.carried_commodity[player_name] = None
        drawn = self._draw_commodity(hex_key)
        return {'hex': hex_key, 'delivered': carried, 'gold': gold,
                'picked_up': drawn}

    def _draw_commodity(self, hex_key: str):
        """Take the top commodity token of a trade hex's stack and carry it.

        Sets the drawing player's destination to the hex that accepts it. Returns
        the commodity drawn, or None if the stack is empty.
        """
        stack = self.tb.trade_hex_stacks.get(hex_key, [])
        if not stack:
            return None
        commodity = stack.pop()
        # The player standing here is the current player (only they can move).
        player_name = self.current_player_name()
        self.tb.carried_commodity[player_name] = commodity
        target_type = tb_decks.DELIVERY_TARGET.get(commodity)
        self.tb.wagon_destination[player_name] = self._trade_hex_of_type(target_type)
        return commodity

    # --- The scenario deck -------------------------------------------------

    def buy_trade_card(self, player_name: str) -> dict:
        """Buy and resolve the top card of the wagon deck (expansions.md 745-748).

        A Knight is held pending the barbarian it moves; Road Building grants two
        free roads; Swift Journey grants a second wagon movement; a Toolmaking,
        Glassmaking or Quarry card is kept face down, worth a victory point. Every
        resolved card but the victory-point ones is discarded, and the discard is
        reshuffled when the draw pile empties.
        """
        if not self.rules['trade_dev_deck'] or self.tb is None:
            return refused('RULE_OFF', 'The wagon deck is not in play')
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'Cards are bought after set-up')
        if self.current_player_name() != player_name:
            return refused('NOT_YOUR_TURN', 'It is not your turn')
        if not self.has_rolled_dice:
            return refused('MUST_ROLL_FIRST', 'Roll the dice before buying a card')
        if self.tb.td_pending is not None:
            return refused('CARD_PENDING', 'Resolve your card before buying another')
        if not self.can_afford(player_name, 'dev_card'):
            return refused('INSUFFICIENT_RESOURCES', 'Cannot afford a card')

        card = self._draw_trade_card()
        if card is None:
            return refused('DECK_EMPTY', 'The card deck is empty')
        self.deduct_cost(player_name, 'dev_card')
        return self._resolve_trade_card(player_name, card)

    def _draw_trade_card(self):
        """Take the top card, reshuffling the discard in when the pile empties."""
        if not self.tb.td_deck and self.tb.td_discard:
            self.tb.td_deck = list(self.tb.td_discard)
            self.tb.td_discard = []
            self.rng.shuffle(self.tb.td_deck)
        if not self.tb.td_deck:
            return None
        return self.tb.td_deck.pop()

    def _resolve_trade_card(self, player_name: str, card: str) -> dict:
        """Apply a revealed wagon-deck card."""
        if card == tb_decks.TRADE_KNIGHT:
            # Held until the player moves a barbarian (game/path_barbarians.py).
            self.tb.td_pending = {'player': player_name, 'card': card}
            return {'success': True, 'error': '', 'card': card,
                    'needs_barbarian_move': True,
                    'barbarians': sorted(self.tb.path_barbarians)}

        if card == tb_decks.TRADE_ROAD_BUILDING:
            self.free_roads_remaining += 2
            self.tb.td_discard.append(card)
            return {'success': True, 'error': '', 'card': card,
                    'free_roads': self.free_roads_remaining}

        if card == tb_decks.SWIFT_JOURNEY:
            # A second wagon movement: a fresh allocation of points this turn.
            self.wagon_points_left = self._wagon_points_left(player_name) \
                + self.wagon_movement_value(player_name)
            self.tb.td_discard.append(card)
            return {'success': True, 'error': '', 'card': card,
                    'points_left': self.wagon_points_left}

        # A victory-point card (Toolmaking, Glassmaking, Quarry): kept, not
        # discarded, and revealed only when it wins the game.
        self.tb.td_vp_cards.setdefault(player_name, []).append(card)
        return {'success': True, 'error': '', 'card': card, 'victory_point': True}

    # --- Scoring -----------------------------------------------------------

    def trade_victory_points(self, player_name: str) -> int:
        """The victory points the wagon run adds for this player (expansions.md
        710, 726, 748).

        Every delivered commodity token is worth 1 point; the fifth baggage-train
        card is worth 1; each held Toolmaking/Glassmaking/Quarry card is worth 1.
        Read live off the state. A no-op without the rule.
        """
        if not self.rules['trade_caravans'] or self.tb is None:
            return 0
        points = len(self.tb.delivered.get(player_name, []))
        if self.rules['baggage_train'] \
                and self.tb.baggage_level.get(player_name, 1) >= MAX_BAGGAGE_LEVEL:
            points += 1
        if self.rules['trade_dev_deck']:
            points += len(self.tb.td_vp_cards.get(player_name, []))
        return points
