"""The pending-choice phase: play stops and one named player decides.

Several rules need the server to interrupt the game, ask a *particular* player
to pick one of a set of legal options, and resume with their answer — which of
their cities the barbarians sack, which commodity a Commercial Harbor takes,
which knight a Deserter lures away. The engine had no way to express that, so
those rules either chose for the player or were refused by name.

This generalises the flags that came before it. `must_move_robber`,
`must_choose_victim`, `players_needing_discard` and `pending_invention` each
record that somebody owes one particular decision, and each needed its own
attribute, its own phase check and its own timeout. A pending choice records
the *kind* of decision, *who* owes it and the *exact options* the server
offered, so one phase check and one timeout cover every rule that needs one.

Two things here are load-bearing:

* The options are recorded when the choice is opened and an answer is checked
  against that recorded list, so a client naming a city it does not own or a
  commodity it does not hold is refused by the same code that made the offer.
* Every choice carries a deadline. `_turn_watchdog` used to `continue` while a
  blocking flag was set, so a game could hang forever and the flag leaked into
  the next player's turn. A choice nobody answers is resolved for them.
"""

import time

from game.results import refused

# Every kind of decision the engine can ask for, and what the player is being
# asked to do. The prompt is the one place the wording lives, so a refusal, a
# log line and the client's dialog cannot drift apart. Each kind is resolved by
# a `_choice_<kind>` method on Game — `tests/game/test_pending_choice.py` pins
# this table against the methods that actually exist.
KINDS = {
    'barbarian_city': 'choose which of your cities the barbarians sack',
    'progress_deck': 'choose which deck to draw a progress card from',
    'commercial_harbor': 'choose a commodity to hand over',
    'master_merchant': 'choose a card to take',
    'merchant_fleet': 'choose a card type to trade at 2:1 this turn',
    'spy': 'choose a progress card to take',
    'wedding': 'choose a card to give away',
    'deserter': 'choose which of your knights deserts',
    'deserter_placement': 'choose where your new knight stands',
    'camel_placement': 'choose which path the camel is placed on',
    'intrigue_coast': 'choose which coast to raid for a prisoner',
    'treason_source': 'choose a coast to pull a barbarian from',
    'treason_destination': 'choose a coast to redeploy a barbarian to',
    'gift_harbor': 'choose which coastal side to place your gift harbor on',
    'gold_field_choice': 'choose a resource to take from the gold field',
    'pirate_repel_reward': 'choose a resource to take for driving off the pirate fleet',
    'helper_resolution': 'exchange your used helper for a new one, or flip it to reuse it',
    'helper_keep_dev': 'choose which of the three development cards to keep',
    'helper_makeshift_road': 'choose where to build your makeshift road',
    'helper_move_road_from': 'choose which of your end roads to move',
    'helper_move_road_to': 'choose where to lay the moved road',
    'helper_knight_to_building': 'choose where to build with the knight',
    'new_energies_take_card': 'choose a resource or science card to take from the supply',
    'new_energies_discard_card': 'choose a resource or science card to discard',
}

# The safety net on draining the queue: a resolver may open a follow-up choice
# (a Master Merchant takes two cards, one at a time), so auto-resolution loops
# rather than iterating. A resolver that opened one every single time would
# otherwise spin forever inside the watchdog.
MAX_AUTO_RESOLUTIONS = 32


class PendingChoiceRules:
    """Opening, answering, serialising and expiring a pending choice."""

    def open_choice(self, kind: str, player_name: str, options, **context) -> dict | None:
        """Record that `player_name` owes a decision of `kind`.

        Returns the recorded choice, or None when there is nothing to offer.
        A caller with exactly one legal option should apply it itself rather
        than asking a player to click the only thing they can click.
        """
        if kind not in KINDS:
            raise ValueError(f"unknown pending choice kind: {kind}")

        options = list(options)
        if not options:
            return None

        choice = {
            'kind': kind,
            'player': player_name,
            'options': options,
            'context': dict(context),
            # Absolute, because the watchdog compares it against the wall
            # clock. Deliberately not saved: see persistence.deserialize.
            'deadline': time.time() + self.choice_time_limit,
        }
        self.pending_choices.append(choice)
        return choice

    def pending_choice_for(self, player_name: str) -> dict | None:
        """The next decision this player owes, in the order they were asked."""
        for choice in self.pending_choices:
            if choice['player'] == player_name:
                return choice
        return None

    def choice_block(self, player_name: str) -> dict | None:
        """A refusal while any decision is outstanding, or None.

        Everyone is frozen, not just the chooser: the table is waiting on one
        answer, and letting play carry on around it would let the current
        player spend cards a Wedding is about to take.
        """
        if not self.pending_choices:
            return None

        mine = self.pending_choice_for(player_name)
        if mine is not None:
            return refused('MUST_CHOOSE', f'You must {KINDS[mine["kind"]]} first')

        waiting = self.pending_choices[0]
        return refused(
            'AWAITING_CHOICE',
            f"Waiting for {waiting['player']} to {KINDS[waiting['kind']]}",
        )

    def resolve_choice(self, player_name: str, kind: str, option: str) -> dict:
        """Apply one player's answer.

        The chooser, the kind and the option are all checked against what was
        recorded: a choice arriving from a client is untrusted exactly like any
        other payload, and the option list is the allowlist.
        """
        choice = self.pending_choice_for(player_name)
        if choice is None:
            return refused('NO_CHOICE_PENDING', 'You have nothing to choose right now')
        if choice['kind'] != kind:
            return refused('WRONG_CHOICE', f'You were asked to {KINDS[choice["kind"]]}')
        if option not in choice['options']:
            return refused('INVALID_CHOICE', 'That was not one of the options offered')

        # Removed before the resolver runs, because a resolver may open the
        # follow-up choice this one leads to and the answered choice must not
        # still be sitting in front of it.
        self.pending_choices.remove(choice)
        outcome = getattr(self, f'_choice_{kind}')(choice, option)
        outcome.update(
            {'success': True, 'error': '', 'kind': kind, 'option': option,
             'player': player_name}
        )
        return outcome

    def choices_expired(self) -> bool:
        """Whether any outstanding decision has run out of time."""
        now = time.time()
        return any(now >= choice['deadline'] for choice in self.pending_choices)

    def auto_resolve_choices(self) -> list:
        """Answer every outstanding decision with its first option.

        Deterministic on purpose: the first entry of a list the engine built in
        a fixed order, so a seeded game replays identically whether or not the
        player answered in time — an RNG pick here would make the same seed
        produce different games depending on the wall clock.

        Resolving beats dropping. A choice that is merely cleared leaves the
        rule it belongs to half applied — a barbarian attack that sacks
        nothing — and every client learns the outcome through the same path as
        a real answer.
        """
        settled = []
        for _ in range(MAX_AUTO_RESOLUTIONS):
            if not self.pending_choices:
                break
            choice = self.pending_choices[0]
            settled.append(
                self.resolve_choice(choice['player'], choice['kind'], choice['options'][0])
            )
        return settled

    def choice_to_dict(self, choice: dict, viewer: str = None) -> dict:
        """One pending choice, as this viewer is entitled to see it.

        The options are named only to the player who has to choose: a Master
        Merchant is choosing from somebody else's hand, and anything that
        reaches a browser is readable in DevTools whatever the UI draws. The
        table still learns that a decision is owed, by whom, and how many
        options it has, which is what a "waiting for Bob" notice needs.
        """
        public = {
            'kind': choice['kind'],
            'player': choice['player'],
            'prompt': KINDS[choice['kind']],
            'option_count': len(choice['options']),
            'context': dict(choice['context']),
        }
        if viewer is not None and viewer == choice['player']:
            public['options'] = list(choice['options'])
        return public

    def pending_choices_for_client(self, viewer: str = None) -> list:
        """Every outstanding decision, filtered for one recipient."""
        return [self.choice_to_dict(choice, viewer) for choice in self.pending_choices]
