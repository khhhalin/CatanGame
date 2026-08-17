"""Barbarian Attack: the coastal war, the castle knights, and the prisoners.

One mixin on `Game`, the pattern the other expansion modules use. Every method
is gated on the `barbarian_attack` rule, so a table not running it is untouched
and the base game is byte-for-byte unchanged. The scenario's own state — the
per-coast barbarian counts, the knight pieces, the prisoners, the conquered
hexes and the 26-card deck — lives on `self.tb` (see game/tb.py) so it persists.

The mechanics (expansions.md 607-662):

- Barbarians land on the coastal hexes. Each build (a settlement, or an upgrade
  to a city) after set-up resolves an attack: three placement rolls, each a
  distinct non-7 number, dropping a barbarian on the coastal hex bearing that
  number. A hex reaching three barbarians is conquered — its token turns face
  down (`conquered_hexes`), it produces nothing (the `conquered_hex` production
  modifier), and any building walled off by conquered hexes and the frame topples
  (`toppled`, worth no victory points, harbour dead).
- Knights are trained from the scenario deck (game/tb_decks.py): a Knighthood
  places one on a castle-adjacent path, a Swift Knight on any path. They are
  moved out from the castle to defend, and a coast with more knights on its six
  paths than barbarians frees those barbarians as the involved players' prisoners
  — every two prisoners are worth one victory point. After each victory a die
  removes some involved knights, paid off at 3 gold each.

Some interactions the printed rules resolve at the table are resolved
deterministically here (they are noted where they occur): the coastal check runs
in sorted hex order rather than clockwise-from-the-castle. Treason and Intrigue
both ask the player: Intrigue for the one coast to raid (expansions.md 642),
Treason for the two coasts to pull from and the two to redeploy to as a
sequenced pending choice (639), drawing from the supply for any barbarian the
board is short of, and resolving each step without a prompt when it has a single
legal option. The
scored effects — conquest, defence, prisoners, knight losses — are faithful.
"""

from game import tb_decks
from game.results import refused

# Two prisoners are worth one victory point (expansions.md 661).
PRISONERS_PER_VP = 2
# Compensation in gold when a knight is removed by the post-victory die, or when
# a player rolls for a prisoner and misses (expansions.md 651, 655).
GOLD_PER_LOST_KNIGHT = 3
GOLD_FOR_MISSED_PRISONER = 3
# Treason hands its resolver 2 gold (expansions.md 638).
TREASON_GOLD = 2
# Treason removes and redeploys exactly 2 barbarians (expansions.md 639).
TREASON_MOVES = 2
# The most barbarians one coastal hex can hold before it is conquered (623).
MAX_BARBARIANS_PER_HEX = 3
# A barbarian attack is three placement rolls (621).
ATTACK_ROLLS = 3


class BarbarianAttackRules:
    """The coastal war: attacks, conquest, knights, victories and prisoners."""

    # --- Board setup -------------------------------------------------------

    def setup_barbarian_board(self):
        """Read the castle, the coast and the un-conquerable hexes off the map,
        seed the opening barbarians and shuffle the scenario deck.

        A no-op without `barbarian_attack` or a state container, and for every
        board that prints no castle, so the base game is untouched. The two
        opening barbarians go on the coastal hexes bearing the '2' and the '12'
        (expansions.md 616).
        """
        if not self.rules['barbarian_attack'] or self.tb is None:
            return

        self.tb.castle_hex = next(
            (key for key, hex_obj in self.hexes.items() if hex_obj.type == 'castle'),
            None,
        )
        # The castle and the desert can never be conquered, so no building beside
        # either is ever toppled (expansions.md 632).
        self.tb.unconquerable_hexes = {
            key for key, hex_obj in self.hexes.items()
            if hex_obj.type in ('castle', 'desert')
        }
        if self.tb.castle_hex is not None:
            self.tb.castle_paths = sorted(
                edge_key for edge_key, edge in self.edges.items()
                if self.tb.castle_hex in edge.neighbors.get('hexes', [])
            )

        # A coastal hex is a land hex bearing a number token that touches the
        # ocean. The castle, the desert and the inner hexes carry no barbarians.
        self.tb.coastal_hexes = sorted(
            key for key, hex_obj in self.hexes.items()
            if hex_obj.number is not None and self._is_coastal_hex(key)
        )
        self.tb.barbarians = {key: 0 for key in self.tb.coastal_hexes}

        self.tb.barbarians_left = self.rules['barbarian_supply']
        for number in (2, 12):
            hex_key = next(
                (key for key in self.tb.coastal_hexes
                 if self.hexes[key].number == number),
                None,
            )
            if hex_key is not None:
                self._place_barbarian(hex_key)

        # The scenario deck is the `barbarian_attack_deck` rule's doing — it is
        # what replaces the base development deck (rules.dev_deck_in_play) — so it
        # is dealt only when that switch is on. The dependency ties it to the war,
        # so in practice they are always on together.
        if self.rules['barbarian_attack_deck']:
            self.tb.ba_deck = tb_decks.build_deck(self.rng)
            self.tb.ba_discard = []
            self.tb.pending_card = None

    def _is_coastal_hex(self, hex_key: str) -> bool:
        """Whether a land hex touches the ocean — where barbarians can land."""
        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None:
            return False
        return any(
            self.hexes.get(neighbor) is not None
            and self.hexes[neighbor].type in ('ocean', 'sea')
            for neighbor in hex_obj.neighbors
        )

    # --- Barbarian landings and conquest -----------------------------------

    def _place_barbarian(self, hex_key: str) -> bool:
        """Drop one barbarian from the supply onto a coastal hex, conquering it
        at three. Returns whether one was placed (the supply may be empty or the
        hex already full)."""
        if self.tb.barbarians_left <= 0:
            return False
        current = self.tb.barbarians.get(hex_key, 0)
        if current >= MAX_BARBARIANS_PER_HEX or hex_key in self.tb.conquered_hexes:
            return False
        self.tb.barbarians[hex_key] = current + 1
        self.tb.barbarians_left -= 1
        if self.tb.barbarians[hex_key] >= MAX_BARBARIANS_PER_HEX:
            self.tb.conquered_hexes.add(hex_key)
            self._recompute_toppled()
        return True

    def trigger_barbarian_attack(self) -> dict:
        """Resolve the attack a build triggers: three distinct-number rolls, each
        landing a barbarian on the coastal hex bearing that number (expansions.md
        621-623).

        A roll of 7, or a number already used earlier in this same attack, is
        re-rolled. If the hex the roll names is already full, that roll places
        nothing and is not re-rolled. Once the supply is empty no barbarian is
        placed for the rest of the game. Returns what landed, for the log.
        """
        if not self.rules['barbarian_attack'] or self.tb is None:
            return {'placed': [], 'supply_empty': True}
        if self.tb.barbarians_left <= 0:
            return {'placed': [], 'supply_empty': True}

        placed = []
        used_numbers = set()
        for _ in range(ATTACK_ROLLS):
            if self.tb.barbarians_left <= 0:
                break
            number = self._roll_attack_number(used_numbers)
            if number is None:
                break
            used_numbers.add(number)
            hex_key = next(
                (key for key in self.tb.coastal_hexes
                 if self.hexes[key].number == number
                 and key not in self.tb.conquered_hexes
                 and self.tb.barbarians.get(key, 0) < MAX_BARBARIANS_PER_HEX),
                None,
            )
            if hex_key is not None and self._place_barbarian(hex_key):
                placed.append(hex_key)

        return {'placed': placed, 'supply_empty': self.tb.barbarians_left <= 0}

    def _roll_attack_number(self, used_numbers: set):
        """Roll two dice until the total is a non-7 not yet used this attack.

        Bounded so a scenario whose coast cannot supply three distinct numbers
        cannot spin forever — every distinct non-7 total that can be reached is
        offered at most a few hundred rolls before giving up (returns None).
        """
        for _ in range(500):
            total = self.rng.randint(1, 6) + self.rng.randint(1, 6)
            if total != 7 and total not in used_numbers:
                return total
        return None

    def _recompute_toppled(self):
        """Walk every building and topple or right it against the conquered hexes.

        A settlement or city becomes conquered (toppled, worth no VP, harbour
        dead) the moment it is adjacent only to conquered hexes and/or the frame,
        and it is turned upright again the moment a hex beside it is freed
        (expansions.md 625-626, 632). Recomputed whole rather than incrementally
        so freeing a hex un-topples exactly the buildings conquering it toppled.
        """
        toppled = set()
        for vertex_key, vertex in self.vertices.items():
            if vertex.building is None:
                continue
            land = vertex.neighbors.get('hexes', [])
            # A building beside the castle or the desert can never be conquered.
            if any(key in self.tb.unconquerable_hexes for key in land):
                continue
            # Adjacent only to conquered hexes and/or the frame: every land hex it
            # touches is conquered. (A vertex lists land hexes only, so touching
            # the frame shows up as fewer than three land neighbours.)
            if land and all(key in self.tb.conquered_hexes for key in land):
                toppled.add(vertex_key)
        self.tb.toppled = toppled

    def _hex_is_conquered(self, hex_key: str) -> bool:
        """Whether this hex is a barbarian-conquered coastal hex — read by the
        production funnel so a conquered hex pays nobody."""
        return (
            self.rules['barbarian_attack']
            and self.tb is not None
            and hex_key in self.tb.conquered_hexes
        )

    def building_is_conquered(self, vertex_key: str) -> bool:
        """Whether a toppled (conquered) building stands on this vertex — read by
        the trade-rate funnel so a conquered building's harbour may not be used
        (expansions.md 631). Un-toppling a building restores it live, so its
        harbour returns the moment a walling coast is freed."""
        return (
            self.rules['barbarian_attack']
            and self.tb is not None
            and vertex_key in self.tb.toppled
        )

    # --- Build guards ------------------------------------------------------

    def barbarian_settlement_refusal(self, vertex_key: str):
        """Refuse a settlement on an intersection beside a conquered hex (628).

        A no-op without the rule and away from the coast, so the base game and
        every non-conquered intersection are untouched.
        """
        if not self.rules['barbarian_attack'] or self.tb is None:
            return None
        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return None
        if any(key in self.tb.conquered_hexes
               for key in vertex.neighbors.get('hexes', [])):
            return refused('CONQUERED_HEX',
                           'You cannot build beside a conquered hex')
        return None

    def barbarian_road_refusal(self, edge_key: str):
        """Refuse a road on a path beside a conquered hex (628)."""
        if not self.rules['barbarian_attack'] or self.tb is None:
            return None
        edge = self.edges.get(edge_key)
        if edge is None:
            return None
        if any(key in self.tb.conquered_hexes
               for key in edge.neighbors.get('hexes', [])):
            return refused('CONQUERED_HEX',
                           'You cannot build beside a conquered hex')
        return None

    # --- The scenario deck -------------------------------------------------

    def buy_barbarian_card(self, player_name: str) -> dict:
        """Buy the top card of the scenario deck and reveal and resolve it (630).

        A card that grants a knight placement (Knighthood, Swift Knight) is left
        pending until the player places the knight; Treason and Intrigue resolve
        at once. A player may not buy a second card while a knight placement from
        the first is still owed (632). Every card is discarded once resolved, and
        the discard is reshuffled when the draw pile empties.
        """
        if not self.rules['barbarian_attack_deck'] or self.tb is None:
            return refused('RULE_OFF', 'The Barbarian Attack deck is not in play')
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'Cards are bought after set-up')
        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can buy a card')
        if not self.has_rolled_dice:
            return refused('MUST_ROLL_FIRST', 'Roll the dice before buying a card')
        if self.tb.pending_card is not None:
            return refused('CARD_PENDING',
                           'Finish resolving your card before buying another')
        if not self.can_afford(player_name, 'dev_card'):
            return refused('INSUFFICIENT_RESOURCES', 'Cannot afford a card')

        card = self._draw_barbarian_card()
        if card is None:
            return refused('DECK_EMPTY', 'The card deck is empty')
        self.deduct_cost(player_name, 'dev_card')

        return self._resolve_barbarian_card(player_name, card)

    def _draw_barbarian_card(self):
        """Take the top card, reshuffling the discard in when the pile empties."""
        if not self.tb.ba_deck and self.tb.ba_discard:
            self.tb.ba_deck = list(self.tb.ba_discard)
            self.tb.ba_discard = []
            self.rng.shuffle(self.tb.ba_deck)
        if not self.tb.ba_deck:
            return None
        return self.tb.ba_deck.pop()

    def _resolve_barbarian_card(self, player_name: str, card: str) -> dict:
        """Apply a revealed card, or hold it pending a knight placement."""
        if card in (tb_decks.KNIGHTHOOD, tb_decks.SWIFT_KNIGHT):
            self.tb.pending_card = {'player': player_name, 'card': card}
            return {'success': True, 'error': '', 'card': card,
                    'needs_knight_placement': True,
                    'legal_paths': self.legal_knight_paths(player_name, card)}

        if card == tb_decks.TREASON:
            result = self._resolve_treason(player_name)
        elif card == tb_decks.INTRIGUE:
            result = self._resolve_intrigue(player_name)
        else:
            result = {'success': True, 'error': '', 'card': card}
        self.tb.ba_discard.append(card)
        return result

    def _resolve_treason(self, player_name: str) -> dict:
        """2 gold, then the player removes 2 barbarians from 2 different coasts
        and redeploys them onto 2 other unconquered coasts, drawing from the
        supply for any barbarian the board is short of (expansions.md 638-639).

        Modelled as a sequenced pending choice: each barbarian to remove, then
        each coast to redeploy to, is a step whose options are computed from the
        picks before it — the second source excludes the first, and a coast just
        pulled from is never offered as a destination ('2 OTHER coasts', 639). A
        conquered coast is a legal source: removing a barbarian from it frees it,
        which the older auto-resolver could not do because it refused conquered
        coasts as sources. A step with a single legal option is applied without
        asking, as Intrigue's single-coast path is. Removals are held and
        applied together only once the redeploy is chosen, so a source stays on
        the board — and excluded from the destinations — until the card resolves.

        The supply-fallback: with fewer than two coasts holding a barbarian, the
        shortfall is taken from the finite supply. If the supply is empty too,
        Treason redeploys only what it can rather than conjuring a barbarian.
        """
        self.gain_gold(player_name, TREASON_GOLD)
        available = [key for key in self.tb.coastal_hexes
                     if self.tb.barbarians.get(key, 0) > 0]
        board_target = min(TREASON_MOVES, len(available))
        supply = min(TREASON_MOVES - board_target, self.tb.barbarians_left)
        ctx = {
            'sources': [], 'destinations': [],
            'board_target': board_target, 'supply': supply,
            'total': board_target + supply,
        }
        return self._treason_next(player_name, ctx)

    def _treason_next(self, player_name: str, ctx: dict) -> dict:
        """Open the next Treason step, auto-applying a step with one legal
        option, or apply the redeploy once every source and destination is set."""
        sources = ctx['sources']
        destinations = ctx['destinations']

        if len(sources) < ctx['board_target']:
            candidates = sorted(
                key for key in self.tb.coastal_hexes
                if self.tb.barbarians.get(key, 0) > 0 and key not in sources
            )
            if len(candidates) == 1:
                return self._treason_next(
                    player_name, {**ctx, 'sources': sources + [candidates[0]]})
            self.open_choice('treason_source', player_name, candidates,
                             **self._treason_step_context(ctx, 'remove'))
            return {'card': tb_decks.TREASON, 'awaiting': player_name}

        if len(destinations) < ctx['total']:
            candidates = sorted(
                key for key in self.tb.coastal_hexes
                if key not in self.tb.conquered_hexes
                and self.tb.barbarians.get(key, 0) < MAX_BARBARIANS_PER_HEX
                and key not in sources
                and key not in destinations
            )
            if not candidates:
                return self._apply_treason(player_name, ctx)
            if len(candidates) == 1:
                return self._treason_next(
                    player_name,
                    {**ctx, 'destinations': destinations + [candidates[0]]})
            self.open_choice('treason_destination', player_name, candidates,
                             **self._treason_step_context(ctx, 'place'))
            return {'card': tb_decks.TREASON, 'awaiting': player_name}

        return self._apply_treason(player_name, ctx)

    def _treason_step_context(self, ctx: dict, phase: str) -> dict:
        """Carry the running Treason plan on the choice, plus the fields the
        client reads to caption the step (which phase, how many are still owed)."""
        remaining = (ctx['board_target'] - len(ctx['sources'])) if phase == 'remove' \
            else (ctx['total'] - len(ctx['destinations']))
        return {
            'sources': list(ctx['sources']),
            'destinations': list(ctx['destinations']),
            'board_target': ctx['board_target'],
            'supply': ctx['supply'],
            'total': ctx['total'],
            'phase': phase,
            'left': remaining,
        }

    def _treason_ctx(self, context: dict) -> dict:
        """Reconstruct the running plan from a choice's recorded context."""
        return {
            'sources': list(context.get('sources', [])),
            'destinations': list(context.get('destinations', [])),
            'board_target': context['board_target'],
            'supply': context['supply'],
            'total': context['total'],
        }

    def _choice_treason_source(self, choice: dict, option: str) -> dict:
        """Record the coast a Treason card pulls a barbarian from (639)."""
        ctx = self._treason_ctx(choice['context'])
        ctx['sources'] = ctx['sources'] + [option]
        return self._treason_next(choice['player'], ctx)

    def _choice_treason_destination(self, choice: dict, option: str) -> dict:
        """Record the coast a Treason card redeploys a barbarian to (639)."""
        ctx = self._treason_ctx(choice['context'])
        ctx['destinations'] = ctx['destinations'] + [option]
        return self._treason_next(choice['player'], ctx)

    def _apply_treason(self, player_name: str, ctx: dict) -> dict:
        """Redeploy the chosen barbarians: empty each chosen source, draw the
        supply shortfall, and drop one on each chosen destination — freeing a
        conquered source and conquering a destination that reaches three."""
        sources = ctx['sources']
        destinations = ctx['destinations']
        place = len(destinations)
        board_remove = min(len(sources), place)
        supply_take = min(place - board_remove, self.tb.barbarians_left)

        for source in sources[:board_remove]:
            self.tb.barbarians[source] -= 1
            if source in self.tb.conquered_hexes \
                    and self.tb.barbarians[source] < MAX_BARBARIANS_PER_HEX:
                self.tb.conquered_hexes.discard(source)
        self.tb.barbarians_left -= supply_take

        moved = board_remove + supply_take
        for target in destinations[:moved]:
            self.tb.barbarians[target] = self.tb.barbarians.get(target, 0) + 1
            if self.tb.barbarians[target] >= MAX_BARBARIANS_PER_HEX:
                self.tb.conquered_hexes.add(target)

        self._recompute_toppled()
        return {'success': True, 'error': '', 'card': tb_decks.TREASON,
                'gold': self.get_player(player_name).gold, 'moved': moved,
                'from': list(sources[:board_remove]),
                'to': list(destinations[:moved]), 'from_supply': supply_take}

    def _resolve_intrigue(self, player_name: str) -> dict:
        """Take 1 barbarian off a coast of the player's choice into their own
        prisoners (expansions.md 640, 642). With no barbarian on any coast the
        card is discarded and a fresh one drawn (641).

        The player names the coast (642): every coast still holding a barbarian
        is offered as a pending choice and the pick is applied to that coast. A
        single candidate is applied at once — there is nothing to choose, and
        the codebase does not ask a player to click the only option (see
        `open_choice`).
        """
        candidates = sorted(
            key for key in self.tb.coastal_hexes
            if self.tb.barbarians.get(key, 0) > 0
        )
        if not candidates:
            # No barbarian anywhere: discard and draw again (641).
            self.tb.ba_discard.append(tb_decks.INTRIGUE)
            replacement = self._draw_barbarian_card()
            if replacement is None:
                return {'success': True, 'error': '', 'card': tb_decks.INTRIGUE,
                        'redrawn': None}
            return self._resolve_barbarian_card(player_name, replacement)

        if len(candidates) == 1:
            return self._take_intrigue_prisoner(player_name, candidates[0])

        self.open_choice('intrigue_coast', player_name, candidates)
        return {'success': True, 'error': '', 'card': tb_decks.INTRIGUE,
                'awaiting': player_name}

    def _take_intrigue_prisoner(self, player_name: str, source: str) -> dict:
        """Move one barbarian off `source` into the player's prisoners, freeing
        the coast if that empties a conquered hex (643)."""
        self.tb.barbarians[source] -= 1
        if source in self.tb.conquered_hexes:
            self.tb.conquered_hexes.discard(source)
            self._recompute_toppled()
        self.tb.prisoners[player_name] = self.tb.prisoners.get(player_name, 0) + 1
        return {'success': True, 'error': '', 'card': tb_decks.INTRIGUE,
                'prisoners': self.tb.prisoners[player_name], 'from': source}

    def _choice_intrigue_coast(self, choice: dict, option: str) -> dict:
        """Apply the coast the player named for an Intrigue card (642)."""
        return self._take_intrigue_prisoner(choice['player'], option)

    # --- Knights: placement and movement -----------------------------------

    def knight_count_on_board(self, player_name: str) -> int:
        return sum(1 for owner in self.tb.knights.values() if owner == player_name)

    def legal_knight_paths(self, player_name: str, card: str) -> list:
        """Every path this card could place a knight on: a Knighthood on a free
        castle path, a Swift Knight on any free path (expansions.md 636-637)."""
        if self.knight_count_on_board(player_name) >= self.rules['max_barbarian_knights']:
            return []
        if card == tb_decks.KNIGHTHOOD:
            candidates = self.tb.castle_paths
        else:
            candidates = list(self.edges.keys())
        return sorted(key for key in candidates if key not in self.tb.knights)

    def place_barbarian_knight(self, player_name: str, edge_key: str) -> dict:
        """Place the knight a pending Knighthood or Swift Knight card grants.

        The path must be legal for the pending card and not already hold a
        knight, and the player must have a knight left in their supply.
        """
        if not self.rules['barbarian_attack'] or self.tb is None:
            return refused('RULE_OFF', 'Barbarian Attack is not in play')
        pending = self.tb.pending_card
        if pending is None or pending['player'] != player_name:
            return refused('NO_PENDING_CARD', 'You have no knight to place')
        if edge_key not in self.legal_knight_paths(player_name, pending['card']):
            return refused('INVALID_PLACEMENT', 'A knight cannot be placed there')

        self.tb.knights[edge_key] = player_name
        self.tb.ba_discard.append(pending['card'])
        self.tb.pending_card = None
        return {'success': True, 'error': '', 'edge': edge_key}

    def _edge_orientation(self, edge_key: str) -> int:
        """Which of the three path orientations this edge lies on (0/1/2).

        An edge key has exactly one coordinate divisible by three; that
        coordinate's index is the orientation, so the six castle paths fall into
        three orientation pairs — what the post-victory die selects between.

        A non-standard side (a spoke) has no lattice orientation and is never a
        castle path, so it is reported as -1: an orientation the post-victory die
        never selects, which leaves any knight on such a side untouched rather
        than crashing on a key the int-split cannot parse.
        """
        if ':' in edge_key:
            return -1
        parts = [int(part) for part in edge_key.split(',')]
        for index, value in enumerate(parts):
            if value % 3 == 0:
                return index
        return 0

    def knight_move_distance(self, from_edge: str, to_edge: str) -> int | None:
        """The fewest paths between two edges, ignoring every piece on the way
        (expansions.md 645), or None if they are not connected.

        A breadth-first walk over the edge-adjacency graph. Bounded by the board,
        so it always terminates.
        """
        if from_edge == to_edge:
            return 0
        seen = {from_edge}
        frontier = [from_edge]
        distance = 0
        while frontier:
            distance += 1
            nxt = []
            for edge_key in frontier:
                edge = self.edges.get(edge_key)
                if edge is None:
                    continue
                for neighbor in edge.neighbors.get('edges', []):
                    if neighbor in seen:
                        continue
                    if neighbor == to_edge:
                        return distance
                    seen.add(neighbor)
                    nxt.append(neighbor)
            frontier = nxt
        return None

    def move_barbarian_knight(self, player_name: str, from_edge: str,
                              to_edge: str, pay_grain: bool = False) -> dict:
        """Move one of your knights up to 3 paths, or up to 5 for 1 grain (644).

        The knight is moved ignoring every other piece on the route; it may not
        end on a path another knight already holds. Only the current player, only
        after rolling.
        """
        if not self.rules['barbarian_attack'] or self.tb is None:
            return refused('RULE_OFF', 'Barbarian Attack is not in play')
        if self.current_player_name() != player_name:
            return refused('NOT_YOUR_TURN', 'It is not your turn')
        if not self.has_rolled_dice:
            return refused('MUST_ROLL_FIRST', 'Roll the dice before moving knights')
        if self.tb.pending_card is not None:
            return refused('CARD_PENDING', 'Place your knight before moving one')
        if self.tb.knights.get(from_edge) != player_name:
            return refused('NO_SUCH_KNIGHT', 'You have no knight on that path')
        if to_edge in self.tb.knights:
            return refused('OCCUPIED', 'Another knight already holds that path')
        if to_edge not in self.edges:
            return refused('INVALID_TARGET', 'No such path')

        limit = 5 if pay_grain else 3
        distance = self.knight_move_distance(from_edge, to_edge)
        if distance is None or distance > limit:
            return refused('TOO_FAR', f'That path is more than {limit} away')

        if pay_grain:
            player = self.get_player(player_name)
            if player.resources.get('wheat', 0) < 1:
                return refused('INSUFFICIENT_RESOURCES', 'A longer march costs 1 grain')
            player.resources['wheat'] -= 1
            self.bank.return_resources('wheat', 1)

        del self.tb.knights[from_edge]
        self.tb.knights[to_edge] = player_name
        return {'success': True, 'error': '', 'from': from_edge, 'to': to_edge}

    # --- Victories, prisoners and knight losses ----------------------------

    def _knights_on_hex(self, hex_key: str) -> dict:
        """player -> how many of their knights stand on this hex's six paths."""
        counts = {}
        hex_edges = [
            edge_key for edge_key, edge in self.edges.items()
            if hex_key in edge.neighbors.get('hexes', [])
        ]
        for edge_key in hex_edges:
            owner = self.tb.knights.get(edge_key)
            if owner is not None:
                counts[owner] = counts.get(owner, 0) + 1
        return counts

    def resolve_barbarian_victories(self) -> list:
        """Check every coast for a victory at the end of a turn (expansions.md
        648-660) and resolve each: free the barbarians as prisoners, un-conquer
        the hex if it was conquered, and run the knight-loss die.

        Checked in sorted hex order rather than clockwise-from-the-castle; the
        order only matters when the prisoner supply runs across hexes in one
        pass, which the deterministic order still resolves consistently. Returns
        one summary per victory, for the log.
        """
        if not self.rules['barbarian_attack'] or self.tb is None:
            return []

        victories = []
        for hex_key in self.tb.coastal_hexes:
            barbarians = self.tb.barbarians.get(hex_key, 0)
            if barbarians < 1:
                continue
            knights = self._knights_on_hex(hex_key)
            if sum(knights.values()) <= barbarians:
                continue
            victories.append(self._resolve_one_victory(hex_key, barbarians, knights))
        return victories

    def _resolve_one_victory(self, hex_key: str, barbarians: int,
                             knights: dict) -> dict:
        """Free one coast: clear its barbarians, hand out prisoners, un-conquer
        it if need be, then remove knights by the die."""
        self.tb.barbarians[hex_key] = 0
        was_conquered = hex_key in self.tb.conquered_hexes
        if was_conquered:
            self.tb.conquered_hexes.discard(hex_key)
            self._recompute_toppled()

        awarded = self._distribute_prisoners(knights, barbarians)
        losses = self._remove_knights_after_victory(hex_key, knights)
        return {'hex': hex_key, 'prisoners': awarded, 'knight_losses': losses,
                'un_conquered': was_conquered}

    def _distribute_prisoners(self, knights: dict, prisoner_count: int) -> dict:
        """Hand `prisoner_count` freed barbarians to the involved players
        (expansions.md 652-660).

        A sole involved player takes them all. Otherwise each involved player
        takes one as far as the prisoners suffice; a shortfall is settled by a
        die roll, the high rollers taking the prisoners and the rest 3 gold; a
        single leftover goes to the player with the most adjacent knights (a tie
        settled by a roll, the loser 3 gold). Returns player -> prisoners won.
        """
        involved = sorted(knights)
        awarded = {name: 0 for name in involved}
        if not involved:
            return awarded

        if len(involved) == 1:
            awarded[involved[0]] += prisoner_count
        elif prisoner_count < len(involved):
            # Not enough for everyone: roll, high rollers win, the rest get gold.
            ranked = sorted(involved, key=lambda name: self.rng.random())
            for name in ranked[:prisoner_count]:
                awarded[name] += 1
            for name in ranked[prisoner_count:]:
                self.gain_gold(name, GOLD_FOR_MISSED_PRISONER)
        else:
            for name in involved:
                awarded[name] += 1
            leftover = prisoner_count - len(involved)
            while leftover > 0:
                most = max(knights.values())
                leaders = [name for name in involved if knights[name] == most]
                winner = min(leaders, key=lambda name: self.rng.random())
                awarded[winner] += 1
                leftover -= 1

        for name, count in awarded.items():
            if count:
                self.tb.prisoners[name] = self.tb.prisoners.get(name, 0) + count
        return awarded

    def _remove_knights_after_victory(self, hex_key: str, knights: dict) -> dict:
        """Roll the die and remove the involved knights it names (expansions.md
        662-666).

        The die picks one of three path orientations (1&4, 2&5, 3&6); every
        knight that took part in this victory and stands on a path of that
        orientation is removed to its owner's supply, its owner paid 3 gold each.
        Returns player -> knights removed.
        """
        if not knights:
            return {}
        die = self.rng.randint(1, 6)
        orientation = (die - 1) % 3
        losses = {}
        hex_edges = [
            edge_key for edge_key in list(self.tb.knights)
            if hex_key in self.edges[edge_key].neighbors.get('hexes', [])
        ]
        for edge_key in hex_edges:
            if self._edge_orientation(edge_key) != orientation:
                continue
            owner = self.tb.knights.pop(edge_key)
            losses[owner] = losses.get(owner, 0) + 1
            self.gain_gold(owner, GOLD_PER_LOST_KNIGHT)
        return losses

    # --- Scoring -----------------------------------------------------------

    def barbarian_victory_points(self, player_name: str) -> int:
        """The victory points Barbarian Attack adds or takes for this player.

        Every two prisoners are worth one point (661); a toppled settlement or
        city is worth none, so the points it would otherwise score are taken back
        (626). Read live, so the total moves the instant a coast is freed or
        conquered. A no-op without the rule.
        """
        if not self.rules['barbarian_attack'] or self.tb is None:
            return 0
        points = self.tb.prisoners.get(player_name, 0) // PRISONERS_PER_VP
        for vertex_key in self.tb.toppled:
            vertex = self.vertices.get(vertex_key)
            if vertex is None or vertex.building is None:
                continue
            if vertex.building.get('player') != player_name:
                continue
            points -= 2 if vertex.building.get('type') == 'city' else 1
        return points
