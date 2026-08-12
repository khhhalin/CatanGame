"""The Caravans: camel geometry, the voting round, and the two scoring effects.

One mixin on `Game`, the pattern the other expansion modules use. Every method
is gated on the `caravans` rule, so a table not running it is untouched and the
base game is byte-for-byte unchanged.

The mechanics (expansions.md 573-601):

- Camels grow out of the central oasis in up to three non-branching caravans.
  Each camel sits on a path (edge) and has a head pointing to its `front` vertex,
  where its caravan continues. The first camel of a caravan starts on one of the
  three arrow paths printed on the oasis, head pointing away from the oasis; each
  later camel starts at the previous camel's front and points away from it. A
  caravan never branches — at any moment it offers at most two legal next paths —
  and with three caravans at most six paths are ever on offer.
- After set-up, whenever a player builds or upgrades at least one settlement in a
  turn, exactly one camel is placed at the end of that turn. Where it goes is
  decided by a voting round: each player bids wool and grain cards once, the
  player with the most votes (ties fall to the player who just finished) chooses
  the path, and every bidder then discards the cards they bid.
- A road on the same path as a camel counts as two roads for the Longest Road
  (`_camel_road_weight`, read by `calculate_longest_road`).
- A settlement or city standing between two camels is worth one extra victory
  point (`camel_victory_points`, folded into `victory_points_for`).

Camels are neutral pieces: no player owns them. Their positions, the caravan
chains and the open vote live on `self.tb` so they persist; the oasis arrows are
read off the dealt map here.
"""

from game.results import refused

# A camel counts a road double for the Longest Road (expansions.md 600).
CAMEL_ROAD_WEIGHT = 2
# A building between two camels is worth one extra point (expansions.md 601).
CAMEL_BUILDING_VP = 1
# Camels are bid for with wool and grain (expansions.md 592). In this engine's
# resource vocabulary that is sheep and wheat.
CAMEL_BID_RESOURCES = ('sheep', 'wheat')


class CaravansRules:
    """Camel placement, the voting round, and the caravan scoring effects."""

    # --- Board setup -------------------------------------------------------

    def setup_caravans_board(self):
        """Read the oasis hex and its arrow paths off the dealt map.

        The oasis is the single hex whose terrain is oasis; the arrows are the
        map's `oasis_arrows`, canonicalised to this board's edge keys and any
        that name nothing on this board dropped. A no-op for a map that prints no
        oasis, and for every built-in layout, so the base game is untouched.
        """
        self.oasis_hex = next(
            (key for key, hex_obj in self.hexes.items() if hex_obj.type == 'oasis'),
            None,
        )
        self.oasis_arrows = []
        definition = self.map_definition
        if definition is None or not getattr(definition, 'oasis_arrows', ()):
            return
        for key in definition.oasis_arrows:
            canonical = self.canonical_edge_key(key)
            if canonical is not None:
                self.oasis_arrows.append(canonical)

    # --- Camel geometry ----------------------------------------------------

    def _edge_other_vertex(self, edge_key: str, from_vertex: str):
        """The far endpoint of an edge — where a camel entering from
        `from_vertex` points its head."""
        edge = self.edges.get(edge_key)
        if edge is None:
            return None
        return next(
            (v for v in edge.neighbors.get('vertices', []) if v != from_vertex),
            None,
        )

    def _oasis_arrow_front(self, edge_key: str):
        """The front of the first camel on an arrow path: the endpoint that does
        not touch the oasis, so the head points away from it (expansions.md 583).

        An arrow path is a spoke — exactly one of its two vertices is a corner of
        the oasis — so the other is unambiguous.
        """
        edge = self.edges.get(edge_key)
        if edge is None:
            return None
        for vertex_key in edge.neighbors.get('vertices', []):
            vertex = self.vertices.get(vertex_key)
            if vertex and self.oasis_hex not in vertex.neighbors.get('hexes', []):
                return vertex_key
        return None

    def legal_camel_placements(self) -> list:
        """Every path a camel could legally be placed on right now.

        Each entry is {'edge', 'front', 'caravan', 'arrow'}: the path, the vertex
        the new camel's head would point at, the index of the caravan it extends
        (None for a fresh caravan), and the arrow it starts from (None when it
        extends). The union of the unused arrows (while fewer than three caravans
        exist) and each caravan's up-to-two frontier paths, minus any path that
        already carries a camel (expansions.md 580, 585, 588, 589).
        """
        if not self.rules['caravans'] or self.tb is None:
            return []
        if len(self.tb.camels) >= self.rules['max_camels']:
            return []

        options = []
        used_arrows = {caravan['arrow'] for caravan in self.tb.caravans}

        # A fresh caravan may start from any unused arrow, at most three in all.
        if len(self.tb.caravans) < 3:
            for arrow in self.oasis_arrows:
                if arrow in used_arrows or arrow in self.tb.camels:
                    continue
                front = self._oasis_arrow_front(arrow)
                if front is not None:
                    options.append({'edge': arrow, 'front': front,
                                    'caravan': None, 'arrow': arrow})

        # Each caravan may extend from the front of its last camel.
        for index, caravan in enumerate(self.tb.caravans):
            frontier = caravan['frontier']
            vertex = self.vertices.get(frontier)
            if vertex is None:
                continue
            for edge_key in vertex.neighbors.get('edges', []):
                if edge_key in self.tb.camels:
                    continue
                front = self._edge_other_vertex(edge_key, frontier)
                if front is not None:
                    options.append({'edge': edge_key, 'front': front,
                                    'caravan': index, 'arrow': None})

        return options

    def place_camel(self, edge_key: str) -> dict:
        """Place one camel on a legal path and grow its caravan.

        The path is checked against `legal_camel_placements`, so a placement that
        would branch a caravan, reuse an occupied path, open a fourth caravan or
        overrun the camel supply is refused by the same code that offers the
        moves. Returns the placement, or a refusal.
        """
        if not self.rules['caravans'] or self.tb is None:
            return refused('RULE_OFF', 'The Caravans are not in play')
        option = next(
            (o for o in self.legal_camel_placements() if o['edge'] == edge_key),
            None,
        )
        if option is None:
            return refused('INVALID_PLACEMENT', 'A camel cannot be placed there')

        self.tb.camels[edge_key] = {'front': option['front']}
        if option['arrow'] is not None:
            self.tb.caravans.append({
                'arrow': option['arrow'],
                'edges': [edge_key],
                'frontier': option['front'],
            })
        else:
            caravan = self.tb.caravans[option['caravan']]
            caravan['edges'].append(edge_key)
            caravan['frontier'] = option['front']

        # A road already on this path now counts double for the Longest Road, so
        # recompute it in case the new camel lengthened somebody's route.
        self.update_longest_road()
        return {'success': True, 'error': '', 'edge': edge_key,
                'front': option['front']}

    # --- The Longest Road and the scoring tiles ----------------------------

    def _camel_road_weight(self, edge_key: str) -> int:
        """What one road segment is worth for the Longest Road: two when a camel
        shares its path, one otherwise (expansions.md 600). Always one when the
        Caravans are not in play, so the base-game walk is unchanged."""
        if self.rules['caravans'] and self.tb is not None and edge_key in self.tb.camels:
            return CAMEL_ROAD_WEIGHT
        return 1

    def _route_weight(self, edges) -> int:
        """The Longest-Road length of a run of road segments, camels counted
        double. Equal to the plain count when no camel shares any path."""
        return sum(self._camel_road_weight(edge_key) for edge_key in edges)

    def camel_victory_points(self, player_name: str) -> int:
        """Extra points for this player's buildings that stand between two camels.

        A settlement or city on an intersection touched by two or more camels is
        worth one extra point (expansions.md 601). Read live off the camel
        positions so a point appears and disappears as caravans grow. A no-op
        without the rule.
        """
        if not self.rules['caravans'] or self.tb is None:
            return 0
        player = self.get_player(player_name)
        if player is None:
            return 0
        points = 0
        for vertex_key in list(player.settlements) + list(player.cities):
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            touching = sum(
                1 for edge_key in vertex.neighbors.get('edges', [])
                if edge_key in self.tb.camels
            )
            if touching >= 2:
                points += CAMEL_BUILDING_VP
        return points

    # --- The voting round --------------------------------------------------

    def camel_vote_block(self, player_name: str = None) -> dict | None:
        """A refusal while a camel voting round is open, or None.

        The table is settling where a camel goes; letting the game carry on
        around it would let a player spend the wool and grain a rival is bidding
        against. A no-op without the rule or while no vote is open, so the base
        game and every non-Caravans build are untouched.
        """
        if self.rules['caravans'] and self.tb is not None and self.tb.camel_vote is not None:
            return refused('CAMEL_VOTE',
                           'A camel is being placed — finish the voting round first')
        return None

    def _clockwise_from(self, finisher: str) -> list:
        """Player names in bidding order — the finisher first, then clockwise
        (expansions.md 591)."""
        names = [player.name for player in self.players]
        if finisher in names:
            start = names.index(finisher)
            names = names[start:] + names[:start]
        return names

    def open_camel_vote(self, finisher: str) -> dict:
        """Open the voting round for the camel the finisher's turn has earned.

        Records who has yet to bid (everyone, the finisher first) and an empty
        set of bids. Resolution waits until every player has bid once; a player
        who does not want to bid submits an empty bid to pass.
        """
        self.tb.camel_vote = {
            'finisher': finisher,
            'pending': self._clockwise_from(finisher),
            'bids': {},
        }
        return self.tb.camel_vote

    def bid_camel(self, player_name: str, cards: list) -> dict:
        """Record one player's single bid of wool and grain cards.

        Each bidder bids exactly once; the cards are checked against the hand and
        left in it until the camel is placed, then discarded (expansions.md 598).
        A bid of no cards is a pass. When the last player has bid, the round is
        resolved and the camel is placed.
        """
        if not self.rules['caravans'] or self.tb is None or self.tb.camel_vote is None:
            return refused('NO_VOTE', 'There is no camel voting round open')
        vote = self.tb.camel_vote
        if player_name not in vote['pending']:
            return refused('ALREADY_BID', 'You have already made your single bid')

        if not isinstance(cards, list):
            return refused('INVALID_PAYLOAD', 'A bid is a list of wool and grain cards')
        counts = {}
        for card in cards:
            if card not in CAMEL_BID_RESOURCES:
                return refused('INVALID_BID', 'You may bid only wool and grain')
            counts[card] = counts.get(card, 0) + 1
        player = self.get_player(player_name)
        if player is None:
            return refused('NO_SUCH_PLAYER', 'No such player')
        for resource, needed in counts.items():
            if player.resources.get(resource, 0) < needed:
                return refused('INSUFFICIENT_RESOURCES', f'You do not hold {needed} {resource}')

        vote['bids'][player_name] = list(cards)
        vote['pending'].remove(player_name)

        if not vote['pending']:
            return self._resolve_camel_vote()
        return {'success': True, 'error': '', 'votes': len(cards),
                'awaiting': list(vote['pending'])}

    def _vote_winner(self, vote: dict) -> str:
        """Who chooses the placement (expansions.md 594-597).

        The player with strictly the most votes chooses; a tie for the most, or
        nobody bidding at all, falls to the player who just finished their turn.
        The negotiated-coalition path of the printed rules is reduced to this —
        the server cannot broker a table's private agreement — so the largest
        single bidder decides, which is the rulebook's own fallback.
        """
        votes = {name: len(cards) for name, cards in vote['bids'].items()}
        most = max(votes.values(), default=0)
        leaders = [name for name, count in votes.items() if count == most and count > 0]
        if len(leaders) == 1:
            return leaders[0]
        return vote['finisher']

    def _resolve_camel_vote(self) -> dict:
        """Decide the winner and either place the only camel path or ask them.

        With one legal path there is nothing to choose, so it is placed at once;
        with several, a `camel_placement` pending choice asks the winner. The
        bids are discarded and the turn advances the moment the camel lands
        (`_finish_camel_vote`).
        """
        vote = self.tb.camel_vote
        winner = self._vote_winner(vote)
        options = [option['edge'] for option in self.legal_camel_placements()]

        if not options:
            # Nothing legal to place — discard the bids and move on rather than
            # stall the table on a camel that cannot go anywhere.
            current = self._finish_camel_vote()
            return {'success': True, 'error': '', 'placed': None,
                    'current_player': current}
        if len(options) == 1:
            self.place_camel(options[0])
            current = self._finish_camel_vote()
            return {'success': True, 'error': '', 'placed': options[0],
                    'current_player': current}

        self.open_choice('camel_placement', winner, options, finisher=vote['finisher'])
        return {'success': True, 'error': '', 'chooser': winner, 'options': options}

    def _choice_camel_placement(self, choice: dict, option: str) -> dict:
        """The winner's answer: place the camel there, discard, advance."""
        self.place_camel(option)
        current = self._finish_camel_vote()
        return {'camel_edge': option, 'current_player': current}

    def _finish_camel_vote(self) -> str:
        """Discard every bid, close the vote, and advance the turn.

        The camel has been placed at the end of the finisher's turn, so the turn
        that was held open by the vote now passes to the next player.
        """
        vote = self.tb.camel_vote or {'bids': {}}
        for name, cards in vote.get('bids', {}).items():
            player = self.get_player(name)
            if player is None:
                continue
            for resource in cards:
                if player.resources.get(resource, 0) > 0:
                    player.resources[resource] -= 1
                    self.bank.return_resources(resource, 1)
        self.tb.camel_vote = None
        self.camel_owed = False
        return self.force_advance_turn()
