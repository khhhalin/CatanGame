"""Catan: Frenemies — favour tokens earned for pro-social acts.

The scenario by Benjamin Teuber for Klaus Teuber's Settlers of Catan
(catan_frenemies_rules_093012s.pdf, the 3-4 player rules). One mixin on `Game`,
the pattern the other scenario modules use (see `oil_springs.py`, `fishing.py`).
Every method is gated on the individual rule that governs it — never on the
scenario's name — so a table not running Frenemies is untouched:

- `favour_tokens` — the framework and the three earn-triggers. A face-down bag
  of 58 favour tokens is drawn blind. You earn one for a *harmless* robber move,
  one for gifting a resource to an equal-or-lower-VP opponent, and — the first
  time a road connects your network to an opponent's — three to you and one to
  them (p. 1). A token drawn during your own turn is locked until your next turn
  ("not allowed to use FTs that you receive during your turn", p. 2), and favour
  tokens are never traded or given away, which is why they live in their own
  purse rather than the resource hand the robber and trades reach into.
- `guild_hall` — redeeming and exchanging those tokens (see the second chunk of
  this mixin).

The bag, each player's usable and locked holdings, the recorded first-time
network connections, and the 8 Victory-Point markers live on the game and are
read straight off it.
"""

from game.results import refused

# The face-down supply for a 4-player game (p. 1): 8 Trader (wagons), 8 Merchant
# (ships), 8 Road Builder (shovels), 17 Scholar (books), 17 Master Builder
# (compasses) — 58 tokens in all. A 3-player game removes the dotted tokens; the
# rulebook does not print which tokens carry a dot, so the full 58-token bag is
# dealt whatever the player count and the type ratios are preserved (see the
# module docstring's known-limits note in the plan).
FAVOUR_TYPES = ('trader', 'merchant', 'road_builder', 'scholar', 'master_builder')
FAVOUR_BAG_COMPOSITION = {
    'trader': 8,
    'merchant': 8,
    'road_builder': 8,
    'scholar': 17,
    'master_builder': 17,
}
FAVOUR_BAG_SIZE = sum(FAVOUR_BAG_COMPOSITION.values())  # 58

# The 8 Victory-Point markers a Master Builder favour hands out (p. 1).
FAVOUR_VP_MARKERS = 8

# How many tokens each earn-trigger draws (p. 1).
HARMLESS_ROBBER_FAVOUR = 1
GIFT_FAVOUR = 1
CONNECTION_BUILDER_FAVOURS = 3
CONNECTION_OPPONENT_FAVOURS = 1


class FavourRules:
    """The favour-token bag, the blind draw, per-player holdings and the three
    earn-triggers. Guild-hall redemption is folded in by the later chunk."""

    # --- The bag -----------------------------------------------------------

    def setup_favours(self):
        """Build and shuffle the favour-token bag, off the game's own RNG.

        A no-op off the `favour_tokens` rule, so every other board is unaffected.
        The bag is a list drawn from the end, so a seeded game deals the same
        tokens in the same order on every replay.
        """
        if not self.rules['favour_tokens']:
            return
        bag = []
        for token_type, count in FAVOUR_BAG_COMPOSITION.items():
            bag.extend([token_type] * count)
        self.rng.shuffle(bag)
        self.favour_bag = bag
        self.favour_vp_supply = FAVOUR_VP_MARKERS
        for player in self.players:
            self.favour_usable.setdefault(player.name, {})
            self.favour_locked.setdefault(player.name, {})

    def _draw_favours(self, player_name: str, count: int) -> list:
        """Draw `count` tokens blind from the bag for a player (p. 1).

        A token drawn during that player's own turn is locked until their next
        turn; one drawn during anybody else's turn — the +1 an opponent earns
        when you connect to them — is usable at once, because it will not be
        their turn until they could spend it anyway. Draws stop when the bag is
        empty. Returns the token types drawn, for the caller's event log.
        """
        drawn = []
        locked = (self.game_phase == 'playing'
                  and player_name == self.current_player_name())
        target = self.favour_locked if locked else self.favour_usable
        for _ in range(count):
            if not self.favour_bag:
                break
            token = self.favour_bag.pop()
            drawn.append(token)
            bucket = target.setdefault(player_name, {})
            bucket[token] = bucket.get(token, 0) + 1
        return drawn

    def start_favour_turn(self):
        """Free the tokens this player was holding and reopen their gift (p. 2).

        Called from `start_turn` for the player whose turn is beginning: the
        tokens they drew on their previous turn have now waited a turn and become
        usable, and a fresh turn may gift one resource again. A no-op off the
        rule.
        """
        if not self.rules['favour_tokens']:
            return
        self.favour_gift_made_this_turn = False
        name = self.current_player_name()
        locked = self.favour_locked.get(name)
        if locked:
            usable = self.favour_usable.setdefault(name, {})
            for token_type, count in locked.items():
                usable[token_type] = usable.get(token_type, 0) + count
            self.favour_locked[name] = {}

    def favour_holdings_total(self, player_name: str) -> int:
        """Every favour token a player holds, usable and locked together.

        The public count — like a resource-hand count — so the table sees who is
        sitting on favours without seeing which guilds they are.
        """
        return (sum(self.favour_usable.get(player_name, {}).values())
                + sum(self.favour_locked.get(player_name, {}).values()))

    # --- Earn: a harmless robber move --------------------------------------

    def award_harmless_robber_favour(self, player_name: str, hex_key: str, victims: list):
        """Grant 1 favour for moving the robber harmlessly (p. 1).

        Way 1 of earning: the robber is moved to a hex with no settlement or city
        on any of its corners, so nobody is robbed and nobody is blocked out of a
        producing hex. `victims` empty is not enough on its own — a hex touching
        only the mover's own building has no victims either, and the rulebook's
        harmless move is one with no surrounding settlements *or cities* at all.
        The desert-decline half of the rule is `decline_steal` below.
        """
        if not self.rules['favour_tokens']:
            return
        if victims or self._favour_hex_has_building(hex_key):
            return
        self._draw_favours(player_name, HARMLESS_ROBBER_FAVOUR)

    def _favour_hex_has_building(self, hex_key: str) -> bool:
        """Whether any settlement or city sits on a corner of this hex."""
        for vertex in self.vertices.values():
            if not vertex.building:
                continue
            if vertex.building.get('type') not in ('settlement', 'city'):
                continue
            if hex_key in vertex.neighbors.get('hexes', []):
                return True
        return False

    def decline_steal(self, player_name: str) -> dict:
        """Decline to steal on the desert for 1 favour token (p. 1).

        The other half of the harmless-robber rule: you moved the robber to the
        desert next to a player's settlement or city and choose not to rob them.
        Only the desert qualifies — declining on a producing hex still blocked
        it — so this is refused anywhere else, and the base game, which has no
        way to decline a steal, never reaches it because it is gated on the rule.
        """
        if not self.rules['favour_tokens']:
            return refused('RULE_OFF', 'Favour tokens are not in play')
        if not self.must_choose_victim:
            return refused('WRONG_PHASE', 'There is nobody to decline stealing from')
        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} may decline the steal')
        hex_obj = self.hexes.get(self.robber_hex)
        if hex_obj is None or hex_obj.type != 'desert':
            return refused(
                'NOT_HARMLESS',
                'You only earn a favour for declining to steal on the desert',
            )
        self.must_choose_victim = False
        self.robber_victims = []
        drawn = self._draw_favours(player_name, HARMLESS_ROBBER_FAVOUR)
        return {'success': True, 'error': '', 'favours': len(drawn)}

    # --- Earn: gifting a resource ------------------------------------------

    def gift_resource(self, giver_name: str, recipient_name: str, resource: str) -> dict:
        """Give 1 resource card to an equal-or-lower-VP opponent for 1 favour (p. 1).

        Way 2 of earning: on your turn you may hand one resource card to an
        opponent whose visible victory points are no greater than yours, and if
        they take it you earn a favour token. Only one gift a turn (p. 1). The
        card moves straight from your hand to theirs, the way a stolen card does,
        so it never touches the bank.
        """
        if not self.rules['favour_tokens']:
            return refused('RULE_OFF', 'Favour tokens are not in play')
        if self.game_phase == 'setup':
            return refused('WRONG_PHASE', 'You cannot gift a resource during setup')
        current_name = self.current_player_name()
        if current_name != giver_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} may gift a resource')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        if giver_name == recipient_name:
            return refused('INVALID_TARGET', 'You cannot gift a resource to yourself')

        giver = self.get_player(giver_name)
        recipient = self.get_player(recipient_name)
        if giver is None or recipient is None:
            return refused('INVALID_TARGET', 'No such player')
        if self.favour_gift_made_this_turn:
            return refused('ALREADY_GIFTED', 'You may only give away one resource a turn')
        if resource not in self.in_play_resource_types():
            return refused('INVALID_RESOURCE', 'Choose a resource the board deals')
        if giver.resources.get(resource, 0) < 1:
            return refused('INSUFFICIENT_RESOURCES', f'You have no {resource} to give')
        if self.public_victory_points(recipient_name) > self.public_victory_points(giver_name):
            return refused(
                'RECIPIENT_AHEAD',
                'You may only gift to an opponent with as many visible victory '
                'points as you or fewer',
            )

        giver.resources[resource] -= 1
        recipient.resources[resource] = recipient.resources.get(resource, 0) + 1
        self.favour_gift_made_this_turn = True
        drawn = self._draw_favours(giver_name, GIFT_FAVOUR)
        return {'success': True, 'error': '', 'resource': resource,
                'recipient': recipient_name, 'favours': len(drawn)}

    # --- Earn: connecting to an opponent's network -------------------------

    def award_connection_favours(self, builder_name: str, edge_key: str) -> dict:
        """Grant favours the first time a road joins two colours' networks (p. 1).

        Way 3 of earning: build a road that connects one of your networks to an
        opponent's for the first time and that opponent draws 1 favour, then you
        draw 3. Connecting your own networks earns nothing; a later road between
        two networks that have already met earns nothing. If one road connects
        you to two opponents at once you still draw only 3, and each opponent
        draws 1 (p. 1). Returns {'builder': n, 'opponents': [names]} for the log,
        empty when no new connection was made.
        """
        result = {'builder': 0, 'opponents': []}
        if not self.rules['favour_tokens']:
            return result
        fresh = []
        for opponent in sorted(self._newly_connected_opponents(builder_name, edge_key)):
            pair = frozenset((builder_name, opponent))
            if pair in self.favour_connections:
                continue
            self.favour_connections.add(pair)
            fresh.append(opponent)
        if not fresh:
            return result
        # The opponents draw first, then the builder draws three once (p. 1).
        for opponent in fresh:
            self._draw_favours(opponent, CONNECTION_OPPONENT_FAVOURS)
        self._draw_favours(builder_name, CONNECTION_BUILDER_FAVOURS)
        result['builder'] = CONNECTION_BUILDER_FAVOURS
        result['opponents'] = fresh
        return result

    def _newly_connected_opponents(self, builder_name: str, edge_key: str) -> set:
        """The opponents this road newly joins the builder's network to.

        Computed as a diff: which opponents the builder's network touches with
        this edge, minus the ones it touched without it. The edge is already
        recorded on the builder's pieces by the time this runs, so 'without it'
        excludes exactly this edge.
        """
        after = self._network_opponents(builder_name, exclude_edge=None)
        before = self._network_opponents(builder_name, exclude_edge=edge_key)
        return after - before

    def _network_opponents(self, builder_name: str, exclude_edge: str) -> set:
        """Which other players share an intersection with the builder's network.

        Two colours' networks meet where both have a piece on the same
        intersection — a road or ship end, a settlement or a city. Enough to
        detect a first-time connection without walking the whole graph, which is
        why the length DFS is not reused here.
        """
        builder_vertices = self._network_vertices(builder_name, exclude_edge)
        opponents = set()
        for player in self.players:
            if player.name == builder_name:
                continue
            if self._network_vertices(player.name, None) & builder_vertices:
                opponents.add(player.name)
        return opponents

    def _network_vertices(self, player_name: str, exclude_edge: str) -> set:
        """Every intersection a player has a road, ship or building touching."""
        vertices = set()
        player = self.get_player(player_name)
        if player is None:
            return vertices
        for edge_key in list(player.roads) + list(player.ships):
            if edge_key == exclude_edge:
                continue
            edge = self.edges.get(edge_key)
            if edge is not None:
                vertices.update(edge.neighbors.get('vertices', []))
        vertices.update(player.settlements)
        vertices.update(player.cities)
        vertices.update(player.harbor_settlements)
        return vertices

    # --- Client state ------------------------------------------------------

    def frenemies_client_state(self, viewer: str = None) -> dict | None:
        """The favour-token panel's state, or None off the scenario.

        The bag count and each player's token count are public — like a resource
        hand, the table sees how many favours somebody holds but not which
        guilds. Only the viewer's own tokens are broken out by guild.
        """
        if not self.rules['favour_tokens']:
            return None
        your = {'usable': {}, 'locked': {}}
        if viewer is not None:
            your = {
                'usable': dict(self.favour_usable.get(viewer, {})),
                'locked': dict(self.favour_locked.get(viewer, {})),
            }
        return {
            'bag_remaining': len(self.favour_bag),
            'counts': {player.name: self.favour_holdings_total(player.name)
                       for player in self.players},
            'your_favours': your,
            'gift_made_this_turn': self.favour_gift_made_this_turn,
            # Whether the viewer may decline a steal right now for a favour — the
            # robber is on the desert, a victim is on offer and it is their turn.
            'can_decline': self._favour_can_decline(viewer),
        }

    def _favour_can_decline(self, viewer: str) -> bool:
        """Whether this viewer may decline a steal on the desert for a favour."""
        if viewer is None or not self.must_choose_victim:
            return False
        if self.current_player_name() != viewer:
            return False
        hex_obj = self.hexes.get(self.robber_hex)
        return hex_obj is not None and hex_obj.type == 'desert'
