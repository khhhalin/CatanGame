"""Traders & Barbarians main scenario: the three barbarians that roam the paths.

One mixin on `Game`, gated on `roaming_barbarians`, so a table not running it is
untouched. The barbarians sit on edges (`self.tb.path_barbarians`); a wagon pays
2 extra movement points to cross one (game/wagons.py reads the set). They move in
three ways (expansions.md 727-737, 745):

- On a rolled 7 the roller moves one barbarian to a free path; landing it on a
  road draws a random resource — never gold — from that road's owner.
- The scenario's own Knight card moves one the same way.
- Once a player's baggage train has been upgraded at least once, a wagon paused
  beside a barbarian may roll to drive it off, moving it to a free path — but
  never drawing a card.

The 7-move and the Knight card share `move_path_barbarian`; the drive-off is its
own path because it rolls and may fail.
"""

from game.results import refused


class PathBarbarianRules:
    """The roaming barbarians: the 7-move, the Knight card, and the drive-off."""

    def _barbarian_move_authorised(self, player_name: str) -> str | None:
        """Which mechanic lets this player move a barbarian now, or None.

        A rolled 7 (`must_move_barbarian`) or a pending Knight card
        (`tb.td_pending`). The card takes precedence so a 7 and a card owed at
        once are each cleared in turn.
        """
        if self.tb is not None and self.tb.td_pending is not None \
                and self.tb.td_pending.get('player') == player_name:
            return 'card'
        if self.must_move_barbarian == player_name:
            return 'seven'
        return None

    def move_path_barbarian(self, player_name: str, from_edge: str,
                            to_edge: str) -> dict:
        """Move a barbarian to a free path, drawing a card off a road (735-737).

        Authorised only by a rolled 7 or a pending Knight card. The destination
        must be a real path holding no other barbarian. Landing on a road draws
        one random resource (never gold) from that road's owner — including the
        mover's own roads, which simply yields nothing to steal from oneself in
        practice but is not special-cased. Clears the authorising flag.
        """
        if not self.rules['roaming_barbarians'] or self.tb is None:
            return refused('RULE_OFF', 'Roaming barbarians are not in play')
        source = self._barbarian_move_authorised(player_name)
        if source is None:
            return refused('NOT_AUTHORISED', 'You have no barbarian to move')
        if from_edge not in self.tb.path_barbarians:
            return refused('NO_SUCH_BARBARIAN', 'No barbarian sits on that path')
        if to_edge not in self.edges:
            return refused('INVALID_TARGET', 'No such path')
        if to_edge in self.tb.path_barbarians:
            return refused('OCCUPIED', 'Another barbarian already holds that path')
        if to_edge == from_edge:
            return refused('INVALID_TARGET', 'Move the barbarian to a different path')

        self.tb.path_barbarians.discard(from_edge)
        self.tb.path_barbarians.add(to_edge)

        stolen = None
        edge = self.edges[to_edge]
        if edge.road is not None:
            owner = edge.road.get('player')
            if owner is not None and owner != player_name:
                stolen = self.steal_resource(owner, player_name)

        # Clear whichever authorised the move.
        if source == 'card':
            self.tb.td_discard.append(self.tb.td_pending['card'])
            self.tb.td_pending = None
        else:
            self.must_move_barbarian = None

        return {'success': True, 'error': '', 'from': from_edge, 'to': to_edge,
                'stole_from': edge.road.get('player') if stolen else None,
                'stolen': stolen}

    def drive_off_barbarian(self, player_name: str, barbarian_edge: str,
                            to_edge: str) -> dict:
        """Roll to drive a barbarian off the path beside your wagon (731-734).

        Allowed only once your baggage train has been upgraded at least once and
        only while your wagon rests on an intersection beside the barbarian, and
        only once per barbarian per turn. On a die face your baggage-train card
        shows, the barbarian is moved to a free path; driving off never draws a
        card. Whether or not it succeeds, the attempt is spent for that barbarian.
        """
        if not self.rules['roaming_barbarians'] or self.tb is None:
            return refused('RULE_OFF', 'Roaming barbarians are not in play')
        if self.current_player_name() != player_name:
            return refused('NOT_YOUR_TURN', 'It is not your turn')
        if not self.has_rolled_dice:
            return refused('MUST_ROLL_FIRST', 'Roll the dice first')
        level = self.tb.baggage_level.get(player_name, 1)
        from game.wagons import BAGGAGE_DRIVE_NUMBERS
        drive_numbers = BAGGAGE_DRIVE_NUMBERS.get(level, ())
        if not drive_numbers:
            return refused('BAGGAGE_TOO_LOW',
                           'Upgrade your baggage train before driving off a barbarian')
        if barbarian_edge not in self.tb.path_barbarians:
            return refused('NO_SUCH_BARBARIAN', 'No barbarian sits on that path')
        if barbarian_edge in self.barbarians_driven:
            return refused('ALREADY_TRIED',
                           'You have already tried that barbarian this turn')

        wagon = self.tb.wagons.get(player_name)
        edge = self.edges.get(barbarian_edge)
        if wagon is None or edge is None \
                or wagon not in edge.neighbors.get('vertices', []):
            return refused('NOT_ADJACENT', 'Your wagon must rest beside the barbarian')

        self.barbarians_driven.add(barbarian_edge)
        die = self.rng.randint(1, 6)
        if die not in drive_numbers:
            return {'success': True, 'error': '', 'die': die, 'driven_off': False}

        if to_edge not in self.edges or to_edge in self.tb.path_barbarians \
                or to_edge == barbarian_edge:
            return refused('INVALID_TARGET', 'Move the barbarian to a free path')
        self.tb.path_barbarians.discard(barbarian_edge)
        self.tb.path_barbarians.add(to_edge)
        return {'success': True, 'error': '', 'die': die, 'driven_off': True,
                'from': barbarian_edge, 'to': to_edge}
