"""CATAN - The Helpers: the helper-tile subsystem, mixed into Game.

One mixin on Game, the way the other scenarios are (see pirate_islands.py). It
owns the whole lifecycle of the twelve helper tiles: the shared display the
tiles are drawn from, the one tile each player holds, activating a tile's
advantage, and the exchange-or-flip step that immediately follows every use
(Helpers_Rules.pdf, 'Using The Helpers', p. 4).

State lives on Game directly: `helper_pile` (the face-up display / draw pile),
`helper_held` (player -> the tile in front of them and which side is up), and
the per-turn record of who has already used their helper. None of it is a rule
- the subsystem is present exactly when `rules['helper_tiles']` is on, and each
individual advantage is gated on its own rule through `HELPER_TILE_RULE`, so no
code branches on the scenario name.

The exchange-or-flip step is modelled as a pending choice (kind
`helper_resolution`): it must be answered immediately, it freezes the table
until it is, and it auto-resolves to "exchange" if abandoned - all of which the
pending-choice machinery already provides.
"""

import logging

from game import helper_tiles, tiles
from game.results import refused
from game.validation import RESOURCE_TYPES

logger = logging.getLogger(__name__)

# The two faces of every tile (Helpers_Rules.pdf p. 3). A sun-side tile may be
# flipped to reuse it once; a moon-side tile is spent and can only be exchanged.
SUN = "sun"
MOON = "moon"


class HelpersRules:
    """Draw, hold, activate, exchange and flip the twelve helper tiles."""

    def helpers_in_play(self) -> bool:
        """Whether this table plays with the helper tiles at all."""
        return bool(self.rules["helper_tiles"])

    # --- Set-up ---------------------------------------------------------

    def setup_helper_pile(self) -> None:
        """Shuffle the tiles whose ability is on into the draw pile.

        Called once from Game.__init__ when the rule is on. Every enabled
        advantage contributes exactly its one tile; the unselected helpers are
        removed from the game (Helpers_Rules.pdf, 'Set-up', p. 3). The pile is
        shuffled through the game's own RNG so a seeded game deals the same
        tiles in the same order every replay.
        """
        self.helper_pile = helper_tiles.tiles_in_play(self.rules)
        self.rng.shuffle(self.helper_pile)

    def grant_starting_helpers(self) -> None:
        """Deal each player their first tile as set-up finishes.

        The scenario hands a player their first helper the moment they place
        their second settlement and road (Helpers_Rules.pdf, 'Take Your First
        Helper', p. 3); the engine does it in seat order when set-up completes,
        which is the one point every player has finished placing. A no-op off
        the scenario, and harmless if the pile is short - a player simply starts
        without one until they can be dealt.
        """
        if not self.helpers_in_play():
            return
        for player in self.players:
            tile = self._draw_helper()
            if tile is None:
                break
            # `received_turn` None means "not received on any counted turn", so
            # the starting tile is playable from the very first turn; the
            # prohibition only bites a tile taken *during* play.
            self.helper_held[player.name] = {
                "tile": tile,
                "side": SUN,
                "received_turn": None,
            }

    def _draw_helper(self) -> str | None:
        """Take the top tile off the display, or None when it is empty."""
        if not self.helper_pile:
            return None
        return self.helper_pile.pop()

    # --- Activation gate ------------------------------------------------

    def _helper_gate(self, player_name: str, tile_id: str):
        """Refuse an illegal activation, or return the held-tile record.

        Every rule that could stop a helper being played is checked here so the
        individual advantage methods only have to describe their own effect.
        Returns the player's held-tile dict on success.
        """
        if not self.helpers_in_play():
            return refused("HELPERS_NOT_IN_PLAY", "This table does not play with helper tiles")

        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        if self.game_phase == "setup":
            return refused("WRONG_PHASE", "Helpers cannot be played during set-up")

        held = self.helper_held.get(player_name)
        if held is None:
            return refused("NO_HELPER", "You have no helper tile in front of you")
        if held["tile"] != tile_id:
            return refused("WRONG_HELPER", "That is not the helper you are holding")

        rule_id = helper_tiles.HELPER_TILE_RULE.get(tile_id)
        if rule_id is None or not self.rules[rule_id]:
            return refused("HELPER_NOT_IN_PLAY", "That helper's advantage is not in play")

        if player_name in self.helper_used_this_turn:
            return refused("HELPER_ALREADY_USED", "You have already used a helper this turn")

        # "You can never play a helper during the turn you receive it"
        # (Helpers_Rules.pdf, 'Prohibitions', p. 5).
        if held["received_turn"] == self.turn_count:
            return refused(
                "HELPER_TOO_SOON", "You cannot play a helper on the turn you received it"
            )

        timing = self._helper_timing_refusal(player_name, tile_id)
        if timing is not None:
            return timing

        return held

    def _helper_timing_refusal(self, player_name: str, tile_id: str):
        """Enforce the tile's 'when to play' icon; None if the moment is right.

        Most tiles play once during the holder's own turn. The exceptions
        (resource compensation, protection from the 7) declare a different
        `when` and are handled by later batches; until their advantage rule is
        wired they never reach this method, so a plain own-turn check is correct
        for every tile now in play.
        """
        tile = helper_tiles.HELPER_TILES_BY_ID[tile_id]
        when = tile["when"]
        if when == helper_tiles.WHEN_TURN:
            current = self.players[self.current_player_index].name
            if current != player_name:
                return refused("NOT_YOUR_TURN", "You can only play this helper on your own turn")
            return None
        if when == helper_tiles.WHEN_AFTER_PRODUCTION:
            # Any player may react to a roll, so no own-turn check here; the
            # advantage that reads it (resource compensation on-turn or off,
            # take-from-leader on-turn) adds its own conditions.
            if self.last_roll_total is None:
                return refused(
                    "HELPER_WRONG_TIME", "Play this only right after a production roll"
                )
            return None
        if when == helper_tiles.WHEN_ON_SEVEN:
            if self.last_roll_total != 7:
                return refused("HELPER_WRONG_TIME", "Play this only when a 7 is rolled")
            return None
        return refused("HELPER_WRONG_TIME", "This helper cannot be played right now")

    # --- Activation dispatch -------------------------------------------

    def activate_helper(self, player_name: str, tile_id: str, params: dict) -> dict:
        """Play the advantage on the tile in front of `player_name`.

        On success the advantage's effect has been applied and the mandatory
        exchange-or-flip choice has been opened for the player; the return dict
        carries whatever the advantage did for the log and the client.
        """
        gate = self._helper_gate(player_name, tile_id)
        if isinstance(gate, dict) and not gate.get("success", True):
            return gate

        handler = getattr(self, f"_helper_{tile_id}", None)
        if handler is None:
            return refused("HELPER_NOT_IN_PLAY", "That helper's advantage is not in play")

        outcome = handler(player_name, params or {})
        if not outcome.get("success", True):
            return outcome

        self.helper_used_this_turn.add(player_name)
        self._open_helper_resolution(player_name)
        outcome.update({"success": True, "error": "", "tile": tile_id, "player": player_name})
        return outcome

    def _open_helper_resolution(self, player_name: str) -> None:
        """Open the exchange-or-flip decision the used tile now owes.

        A sun-side tile may be exchanged or flipped; a moon-side tile is spent
        and may only be exchanged. `exchange` is listed first so an abandoned
        choice auto-resolves to it - the safe default that never leaves a spent
        tile masquerading as fresh.
        """
        held = self.helper_held[player_name]
        options = ["exchange", "flip"] if held["side"] == SUN else ["exchange"]
        self.open_choice("helper_resolution", player_name, options)

    def _choice_helper_resolution(self, choice: dict, option: str) -> dict:
        """Apply the exchange or flip that follows a used tile."""
        player_name = choice["player"]
        held = self.helper_held[player_name]
        if option == "flip":
            held["side"] = MOON
            return {"action": "flip", "tile": held["tile"]}

        # Exchange: the used tile goes to the bottom of the display and a fresh
        # one comes off the top, sun side up. Inserting before drawing means a
        # pile that held only this player's tile hands it straight back, which is
        # the correct outcome when the display has run dry.
        self.helper_pile.insert(0, held["tile"])
        drawn = self._draw_helper()
        self.helper_held[player_name] = {
            "tile": drawn,
            "side": SUN,
            "received_turn": self.turn_count,
        }
        return {"action": "exchange", "tile": drawn}

    # --- The advantages -------------------------------------------------

    def _helper_kaja(self, player_name: str, params: dict) -> dict:
        """Kaja: take a resource matching the hex the robber occupies.

        The robber's hex fixes the resource; only a robber sitting on the desert
        (which produces nothing) lets the player choose. Reuses `give_resource`,
        so an empty supply pile refuses the take the same way every other draw
        does (Helpers_Rules.pdf, Take Robber's Resource, p. 11).
        """
        hex_obj = self.hexes.get(self.robber_hex)
        produced = tiles.produces(hex_obj.type) if hex_obj is not None else None
        if produced is None:
            resource = params.get("resource")
            if resource not in RESOURCE_TYPES:
                return refused(
                    "NEEDS_RESOURCE",
                    "The robber is in the desert; choose which resource to take",
                )
            produced = resource

        if not self.give_resource(player_name, produced):
            return refused("SUPPLY_EMPTY", f"The supply has no {produced} left")
        return {"taken": produced}

    def _desert_hex_key(self) -> str | None:
        """The board's desert hex, or None if it has none."""
        for key, hex_obj in self.hexes.items():
            if hex_obj.type == "desert":
                return key
        return None

    def _helper_digur(self, player_name: str, params: dict) -> dict:
        """Digur: move the robber to the desert and take the hex it left's card.

        Reuses the robber's own hex, `tiles.produces` and `give_resource`; the
        move is a plain reassignment of `robber_hex`, not a robber-phase move, so
        it steals from nobody (Helpers_Rules.pdf, Chase Robber to Desert, p. 10).
        """
        hex_obj = self.hexes.get(self.robber_hex)
        if hex_obj is not None and hex_obj.type == "desert":
            return refused("ROBBER_IN_DESERT", "The robber is already in the desert")
        desert = self._desert_hex_key()
        if desert is None:
            return refused("NO_DESERT", "There is no desert to chase the robber to")

        produced = tiles.produces(hex_obj.type) if hex_obj is not None else None
        self.robber_hex = desert
        taken = None
        if produced is not None and self.give_resource(player_name, produced):
            taken = produced
        return {"moved_to": desert, "taken": taken}

    def _helper_hilda(self, player_name: str, params: dict) -> dict:
        """Hilda: after an empty production roll, take 1 resource of choice.

        Reads the roll the engine remembered: legal only when the last roll was
        not a 7 and paid this player nothing (Helpers_Rules.pdf, Resource
        Compensation, p. 8). Reuses `give_resource`.
        """
        if self.last_roll_total is None or self.last_roll_total == 7:
            return refused(
                "HELPER_WRONG_TIME", "Hilda reacts only to a production roll that is not a 7"
            )
        if self.last_roll_gains.get(player_name):
            return refused("HELPER_NO_NEED", "You received resources from that roll")
        resource = params.get("resource")
        if resource not in RESOURCE_TYPES:
            return refused("NEEDS_RESOURCE", "Choose which resource to take")
        if not self.give_resource(player_name, resource):
            return refused("SUPPLY_EMPTY", f"The supply has no {resource} left")
        return {"taken": resource}

    def _helper_thorolf(self, player_name: str, params: dict) -> dict:
        """Thorolf: on a 7, keep an over-full hand, or take 1 if 7 or fewer.

        Over the limit means the roll already listed the player as owing a
        discard (`players_needing_discard`); removing them there is what waives
        the discard, so no card leaves the hand. A hand of 7 or fewer takes 1
        resource of choice instead (Helpers_Rules.pdf, Protection from the 7,
        p. 9).
        """
        if self.last_roll_total != 7:
            return refused("HELPER_WRONG_TIME", "Thorolf reacts only to a 7")
        if player_name in self.players_needing_discard:
            del self.players_needing_discard[player_name]
            return {"protected": True}
        resource = params.get("resource")
        if resource not in RESOURCE_TYPES:
            return refused("NEEDS_RESOURCE", "Choose which resource to take")
        if not self.give_resource(player_name, resource):
            return refused("SUPPLY_EMPTY", f"The supply has no {resource} left")
        return {"taken": resource}

    def _helper_ryan(self, player_name: str, params: dict) -> dict:
        """Ryan: after your roll, take 1 chosen card from a richer opponent.

        Own-turn only, once the roll is resolved. The opponent must have strictly
        more victory points, counted the way the scoreboard counts them (longest
        road and largest army included), and must actually hold the chosen
        resource (Helpers_Rules.pdf, Take Card From Leader, p. 10).
        """
        current = self.players[self.current_player_index].name
        if current != player_name:
            return refused("NOT_YOUR_TURN", "Ryan acts after your own production roll")

        target = params.get("target")
        victim = self.get_player(target) if target else None
        if victim is None or victim.name == player_name:
            return refused("INVALID_TARGET", "Choose an opponent to take a card from")

        me = self.get_player(player_name)
        my_vp = me.get_victory_points(self.longest_road_holder, self.largest_army_holder)
        their_vp = victim.get_victory_points(self.longest_road_holder, self.largest_army_holder)
        if their_vp <= my_vp:
            return refused(
                "NOT_A_LEADER",
                "You may only take from an opponent with more victory points than you",
            )

        resource = params.get("resource")
        if resource not in RESOURCE_TYPES:
            return refused("NEEDS_RESOURCE", "Choose which resource to take")
        if victim.resources.get(resource, 0) <= 0:
            return refused("NOT_HELD", f"{target} has no {resource} to take")

        victim.resources[resource] -= 1
        me.resources[resource] = me.resources.get(resource, 0) + 1
        return {"from": target, "taken": resource}

    # --- Client / persistence view -------------------------------------

    def helpers_client_state(self, viewer: str = None) -> dict | None:
        """The helper subsystem as the client draws it, or None when off.

        Everything here is public: in the real game the display faces sun side
        up and every player's helper sits face-up in front of them, so the tile
        ids and sides are open information. Only the count of the draw pile
        would leak nothing a player could not see by looking at the table.
        """
        if not self.helpers_in_play():
            return None
        return {
            "pile": list(self.helper_pile),
            "held": {
                name: {"tile": held["tile"], "side": held["side"]}
                for name, held in self.helper_held.items()
            },
            "used_this_turn": sorted(self.helper_used_this_turn),
            # The tiles' display metadata, so the client draws a name, title,
            # summary and its input needs from one source rather than a copy
            # that could drift. Only the enabled tiles are sent.
            "catalogue": {
                tile_id: {
                    "name": tile["name"],
                    "title": tile["title"],
                    "summary": tile["summary"],
                    "when": tile["when"],
                    "needs": tile["needs"],
                    "number": tile["number"],
                }
                for tile_id, tile in helper_tiles.HELPER_TILES_BY_ID.items()
                if self.rules[tile["rule"]]
            },
        }
