"""The Explorers & Pirates pirate ship: a per-player robber for the sea.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. Where Seafarers has one pirate for the table (`seafarers.py`), E&P gives
every player their own pirate ship: on a 7 the roller places *their* pirate on a
sea hex, steals one card from an opponent with a ship there, and thereafter that
hex charges every mover 1 gold in tribute for each ship that crosses it
(expansions.md 841, 843, 934-949).

It reuses the robber-diversion pattern Seafarers already established: the 7 sets
`must_move_robber` (the shared flag) and the same `steal_from_victim` resolves
the theft — see `robber_rules.py`. The only genuinely new pieces are placement on
`self.ep`, the empty-handed-victim gold fallback (943), and the movement tribute
(949).

Every method is gated on `self.rules['pirate_ship_instead_of_robber']`, never on
an expansion name. Per-player pirate hexes live on `self.ep`; the rule depends on
`gold`, so a table with the pirate always has a gold purse to pay tribute into.
"""

from game.results import refused

# What a ship pays each time it crosses a hex holding an opponent's pirate
# (expansions.md 949).
TRIBUTE_GOLD = 1


class EpPirateRules:
    """Placing the pirate ship on a 7, stealing, and the movement tribute."""

    def place_pirate_ship(self, player_name: str, hex_key: str) -> dict:
        """Place the roller's own pirate ship on a sea hex instead of the robber.

        Reuses `must_move_robber` exactly as Seafarers' `move_pirate` does, and
        answers with the same victim shape: a non-empty list means the mover
        still owes a `steal_from_victim` choice. The hex thereafter charges
        tribute — that is recorded simply by the pirate sitting on it.
        """
        if not self.rules['pirate_ship_instead_of_robber']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with the pirate ship')

        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot place the pirate ship during setup')

        if not self.must_move_robber:
            return refused('WRONG_PHASE', 'You do not need to place the pirate ship')

        current_name = self.players[self.current_player_index].name
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can place the pirate ship')

        # All discarding happens before the pirate moves, the same order the
        # robber keeps (`move_robber`), so an unpaid discard anywhere holds it
        # back.
        if self.players_needing_discard:
            owed = ', '.join(sorted(self.players_needing_discard))
            return refused('MUST_DISCARD', f'{owed} must discard before the pirate ship is placed')

        hex_obj = self.hexes.get(hex_key)
        if hex_obj is None:
            return refused('INVALID_TARGET', 'Invalid hex')
        if hex_obj.type != 'ocean':
            return refused('INVALID_TARGET', 'The pirate ship sails; it may only sit on a sea hex')

        if self.ep is None:
            # Every rule that needs the pirate builds the EP container, so this
            # is a wiring bug, not a player error — but refuse rather than raise.
            return refused('WRONG_PHASE', 'This table has no pirate state')

        self.ep.place_pirate(player_name, hex_key)
        self.must_move_robber = False

        victims = self.pirate_ship_victims(player_name, hex_key)
        if victims:
            self.must_choose_victim = True
            self.robber_victims = victims

        return {'success': True, 'error': '', 'victims': victims}

    def pirate_ship_victims(self, player_name: str, hex_key: str) -> list:
        """Every opponent with a ship on a side of this hex.

        One card is stolen from a player however many ships they have there, so
        each opponent appears once — the same rule the Seafarers pirate keeps
        (`pirate_victims`, expansions.md 93).
        """
        victims = []
        for edge in self.edges.values():
            if edge.ship is None or hex_key not in edge.neighbors['hexes']:
                continue
            owner = edge.ship.get('player')
            if owner and owner != player_name and owner not in victims:
                victims.append(owner)
        return victims

    def _steal_gold_fallback(self, victim_name: str, thief_name: str) -> str | None:
        """Take 1 gold from an empty-handed victim instead of a card (943).

        Called from `steal_from_victim` only when the pirate rule and gold are
        both on and the victim held no resource cards. A victim with no gold
        either yields nothing, which is a legal outcome.
        """
        victim = self.get_player(victim_name)
        thief = self.get_player(thief_name)
        if victim is None or thief is None or victim.gold <= 0:
            return None
        victim.gold -= 1
        thief.gold += 1
        return 'gold'

    def charge_pirate_tribute(self, mover_name: str, edge_key: str) -> None:
        """A ship arriving beside an opponent's pirate pays 1 gold tribute (949).

        Wired into `move_transport_ship`. Guarded so a table without the pirate
        rule is unaffected. A mover with no gold pays nothing — `spend_gold`
        refuses an empty purse rather than driving it negative.
        """
        if self.ep is None or not self.rules['pirate_ship_instead_of_robber']:
            return
        edge = self.edges.get(edge_key)
        if edge is None:
            return
        for hex_key in edge.neighbors['hexes']:
            for owner in self.ep.pirate_at(hex_key):
                if owner == mover_name:
                    continue
                if self.spend_gold(mover_name, TRIBUTE_GOLD):
                    self.gain_gold(owner, TRIBUTE_GOLD)
