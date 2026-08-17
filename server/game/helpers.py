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
        # An advantage that opens a follow-up decision of its own (Diara's
        # keep-one-of-three) defers the exchange-or-flip until that decision is
        # answered; its resolver opens it. Everything else opens it now.
        if not outcome.get("defer_resolution"):
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

    def _helper_asla(self, player_name: str, params: dict) -> dict:
        """Asla: demand a resource from up to two players, paying one back each.

        A player-to-player exchange (bank-neutral): each named opponent who holds
        the requested resource gives one, and gets one of the player's choice in
        return - which may be the very card just received. Applied one player at
        a time so the returned card can be paid out of the receipt, and rolled
        back if the player cannot pay a return (Helpers_Rules.pdf, Forced Trade,
        p. 6).
        """
        resource = params.get("resource")
        if resource not in RESOURCE_TYPES:
            return refused("NEEDS_RESOURCE", "Choose which resource to request")
        targets = params.get("targets") or []
        returns = params.get("returns") or []
        if not 1 <= len(targets) <= 2 or len(returns) != len(targets):
            return refused("INVALID_TARGET", "Name 1 or 2 players and a return for each")
        if len(set(targets)) != len(targets):
            return refused("INVALID_TARGET", "Name each player only once")

        me = self.get_player(player_name)
        exchanges = []
        for target, give_back in zip(targets, returns, strict=True):
            victim = self.get_player(target)
            if victim is None or victim.name == player_name:
                return refused("INVALID_TARGET", "Choose opponents to request from")
            if give_back not in RESOURCE_TYPES:
                return refused("NEEDS_RESOURCE", "Choose a resource to give back")
            if victim.resources.get(resource, 0) <= 0:
                continue  # they do not hold it; nothing changes hands with them
            # Take first, so the return may be paid out of the card received.
            victim.resources[resource] -= 1
            me.resources[resource] = me.resources.get(resource, 0) + 1
            if me.resources.get(give_back, 0) <= 0:
                # Undo the take; the whole activation is refused so no card is
                # left half-exchanged.
                me.resources[resource] -= 1
                victim.resources[resource] += 1
                return refused("CANNOT_RETURN", f"You have no {give_back} to give {target}")
            me.resources[give_back] -= 1
            victim.resources[give_back] = victim.resources.get(give_back, 0) + 1
            exchanges.append({"from": target, "took": resource, "returned": give_back})
        return {"exchanges": exchanges}

    def _helper_stina(self, player_name: str, params: dict) -> dict:
        """Stina: exchange one resource with the bank at 2:1, several times at once.

        Reuses the bank's take/return directly rather than the trade offer flow,
        because this is a burst of bank trades resolved in one go, not a standing
        2:1 rate for the turn (Helpers_Rules.pdf, 2:1 Trade Frenzy, p. 9).
        """
        give = params.get("resource_out") or params.get("resource")
        if give not in RESOURCE_TYPES:
            return refused("NEEDS_RESOURCE", "Choose the resource to trade away")
        receives = params.get("resources") or []
        if not receives or any(item not in RESOURCE_TYPES for item in receives):
            return refused("NEEDS_RESOURCE", "Choose the resources to receive")

        me = self.get_player(player_name)
        cost = 2 * len(receives)
        if me.resources.get(give, 0) < cost:
            return refused("CANNOT_AFFORD", f"A 2:1 for {len(receives)} needs {cost} {give}")
        for received in receives:
            if not self.bank.take(received):
                return refused("SUPPLY_EMPTY", f"The supply has no {received} left")

        me.resources[give] -= cost
        self.bank.return_resources(give, cost)
        for received in receives:
            me.resources[received] = me.resources.get(received, 0) + 1
        return {"gave": give, "count": cost, "received": list(receives)}

    def _helper_diara(self, player_name: str, params: dict) -> dict:
        """Diara: buy a development card, one resource swappable, keep 1 of 3.

        Pays the card's cost with one resource optionally substituted, draws
        three from the deck, and opens the keep-one choice; the deferred
        exchange-or-flip follows the keep. Needs the development deck in play
        (Helpers_Rules.pdf, Development Card Choice, p. 9).
        """
        if not self.dev_deck_in_play():
            return refused("DEV_CARDS_NOT_IN_PLAY", "This table does not buy development cards")

        cost = self.get_cost("dev_card")
        substitute_from = params.get("substitute_from")
        substitute_with = params.get("substitute_with")
        if substitute_from is not None or substitute_with is not None:
            if substitute_from not in cost:
                return refused("INVALID_SUBSTITUTE", "You may only swap a card you must pay")
            if substitute_with not in RESOURCE_TYPES:
                return refused("NEEDS_RESOURCE", "Choose a resource to pay instead")
            cost = dict(cost)
            cost[substitute_from] -= 1
            if cost[substitute_from] == 0:
                del cost[substitute_from]
            cost[substitute_with] = cost.get(substitute_with, 0) + 1

        me = self.get_player(player_name)
        if any(me.resources.get(res, 0) < amount for res, amount in cost.items()):
            return refused("CANNOT_AFFORD", "You cannot pay for the development card")

        drawn = [self.bank.draw_dev_card() for _ in range(3)]
        drawn = [card for card in drawn if card is not None]
        if not drawn:
            return refused("ACTION_FAILED", "No development cards left to draw")

        for res, amount in cost.items():
            me.resources[res] -= amount
            self.bank.return_resources(res, amount)

        self.open_choice("helper_keep_dev", player_name, drawn, drawn=drawn)
        return {"drawn_count": len(drawn), "defer_resolution": True}

    def _choice_helper_keep_dev(self, choice: dict, option: str) -> dict:
        """Keep the chosen card, return the other two, then owe exchange-or-flip."""
        player_name = choice["player"]
        drawn = list(choice["context"]["drawn"])
        me = self.get_player(player_name)

        # The kept card enters the hand stamped with this turn, so it cannot be
        # played until the next turn, exactly like a bought card.
        me.dev_cards[option]["count"] += 1
        me.dev_cards[option]["purchase_turn"] = self.turn_count
        drawn.remove(option)
        for card in drawn:
            self.bank.return_dev_card(card)

        self._open_helper_resolution(player_name)
        return {"kept": option}

    def _helper_carla(self, player_name: str, params: dict) -> dict:
        """Carla: return an unplayed development card and draw a fresh one.

        The bank's deck is a weighted bag, so "bottom of the stack" is modelled
        as returning the card to the bag before drawing anew - the swap effect is
        faithful even though the bag has no order. The drawn card is stamped with
        this turn so it cannot be played at once (Helpers_Rules.pdf, Development
        Card Swap, p. 11).
        """
        if not self.dev_deck_in_play():
            return refused("DEV_CARDS_NOT_IN_PLAY", "This table does not use development cards")
        card_type = params.get("dev_card")
        me = self.get_player(player_name)
        if card_type not in me.dev_cards or me.dev_cards[card_type]["count"] <= 0:
            return refused("NOT_HELD", "You have no such development card to swap")

        me.dev_cards[card_type]["count"] -= 1
        self.bank.return_dev_card(card_type)
        drawn = self.bank.draw_dev_card()
        if drawn is None:
            # Nothing to draw: undo the return so no card is lost.
            me.dev_cards[card_type]["count"] += 1
            return refused("ACTION_FAILED", "No development cards left to draw")
        me.dev_cards[drawn]["count"] += 1
        me.dev_cards[drawn]["purchase_turn"] = self.turn_count
        return {"returned": card_type, "drawn": drawn}

    def _helper_yngvi(self, player_name: str, params: dict) -> dict:
        """Yngvi: build a road, paying a substitute for one of its base cards.

        Reuses `build_road` in full - every placement check, the free-road path,
        the Longest Road update. The substitution is set up around it: the player
        is lent the dropped base card from the bank and pays the substitute, so
        `build_road` deducts the ordinary road cost and the net paid is the
        substitute plus the other base card (Helpers_Rules.pdf, Makeshift Road
        Building, p. 6).

        The road's edge may arrive in `params` (the engine and its tests name it
        directly) or, when the player is picking on the board, be left out - then
        the legal road sides are opened as a pending choice and the build is
        deferred to its answer. Either way the swap and `build_road` are the same.
        """
        edge = params.get("edge")
        drop = params.get("drop")
        pay = params.get("resource") or params.get("pay")
        if drop not in ("wood", "brick"):
            return refused("INVALID_SUBSTITUTE", "You may only substitute lumber or brick")
        if pay not in RESOURCE_TYPES or pay == drop:
            return refused("NEEDS_RESOURCE", "Choose a different resource to pay instead")
        if self.free_roads_remaining > 0:
            return refused("HAS_FREE_ROAD", "Use your free road rather than Yngvi")

        me = self.get_player(player_name)
        if me.resources.get(pay, 0) <= 0:
            return refused("CANNOT_AFFORD", f"You have no {pay} to pay instead")
        if not self.bank.take(drop):
            return refused("SUPPLY_EMPTY", f"The supply cannot lend a {drop}")

        me.resources[drop] = me.resources.get(drop, 0) + 1
        me.resources[pay] -= 1
        self.bank.return_resources(pay, 1)

        if edge is not None:
            return self._yngvi_build(player_name, edge, drop, pay)

        options = self._helper_road_targets(player_name)
        if not options:
            self._yngvi_unswap(player_name, drop, pay)
            return refused("NO_ROAD_SPOT", "You have nowhere to build a road right now")
        self.open_choice("helper_makeshift_road", player_name, options, drop=drop, pay=pay)
        return {"defer_resolution": True, "dropped": drop, "paid": pay}

    def _yngvi_build(self, player_name: str, edge: str, drop: str, pay: str) -> dict:
        """Build the makeshift road, undoing the swap if the placement is refused."""
        result = self.build_road(player_name, edge)
        if not result["success"]:
            self._yngvi_unswap(player_name, drop, pay)
            return result
        return {"edge": edge, "dropped": drop, "paid": pay}

    def _yngvi_unswap(self, player_name: str, drop: str, pay: str) -> None:
        """Reverse the lend-and-pay so a refused road costs nothing."""
        me = self.get_player(player_name)
        me.resources[drop] -= 1
        self.bank.return_resources(drop, 1)
        me.resources[pay] += 1
        self.bank.take(pay)

    def _choice_helper_makeshift_road(self, choice: dict, option: str) -> dict:
        """Lay Yngvi's road on the side the player tapped, then owe exchange-or-flip."""
        context = choice["context"]
        result = self._yngvi_build(choice["player"], option, context["drop"], context["pay"])
        self._open_helper_resolution(choice["player"])
        return result

    def _helper_road_targets(self, player_name: str) -> list:
        """The sides a road of this player's could legally be built on, sorted.

        The base-game road checks `build_road` makes: an empty land side, off any
        river bridge site, that touches the player's own network. Sorted so an
        abandoned choice auto-resolves deterministically. Scenario-specific road
        refusals (a conquered coast, a locked lair) are left to `build_road`
        itself; a Helpers table with those rules on is the documented edge.
        """
        targets = []
        for edge_key, edge in self.edges.items():
            if edge.road is not None or edge.ship is not None:
                continue
            if not self.land_hexes_of_edge(edge_key):
                continue
            if self.is_bridge_site(edge_key):
                continue
            if self._road_connects(player_name, edge_key):
                targets.append(edge_key)
        return sorted(targets)

    def _is_end_road(self, player_name: str, edge_key: str) -> bool:
        """Whether one end of this road touches none of the player's own pieces."""
        edge = self.edges.get(edge_key)
        if edge is None:
            return False
        for vertex_key in edge.neighbors.get("vertices", []):
            vertex = self.vertices.get(vertex_key)
            if vertex is not None and vertex.building \
                    and vertex.building.get("player") == player_name:
                continue  # a building of the player's own holds this end
            touches = False
            for other in vertex.neighbors.get("edges", []) if vertex else []:
                if other == edge_key:
                    continue
                other_edge = self.edges.get(other)
                if other_edge and other_edge.road \
                        and other_edge.road.get("player") == player_name:
                    touches = True
                    break
            if not touches:
                return True
        return False

    def _helper_hogni(self, player_name: str, params: dict) -> dict:
        """Hogni: pick up one of your end roads and lay it elsewhere for free.

        The lift is a plain removal; the re-lay reuses `build_road` through a
        granted free road, so the new spot has to obey every normal placement
        rule and the Longest Road is recomputed (Helpers_Rules.pdf, Move a Road,
        p. 7).

        Both edges may arrive in `params` (the engine and its tests name them),
        or the player picks on the board: with neither given, the end roads are
        opened as a first pending choice, and its answer opens a second listing
        where the lifted road may go. The lift-then-build below is what both the
        direct call and the two-step board flow run.
        """
        from_edge = params.get("from_edge")
        to_edge = params.get("to_edge")
        if from_edge is not None and to_edge is not None:
            problem = self._hogni_lift_refusal(player_name, from_edge)
            if problem is not None:
                return problem
            return self._hogni_move(player_name, from_edge, to_edge)

        options = self._helper_end_roads(player_name)
        if not options:
            return refused("NOT_END_ROAD", "You have no end road to move")
        self.open_choice("helper_move_road_from", player_name, options)
        return {"defer_resolution": True}

    def _hogni_lift_refusal(self, player_name: str, from_edge: str):
        """Refuse a from-edge that is not one of the player's own end roads."""
        edge = self.edges.get(from_edge)
        if edge is None or edge.road is None or edge.road.get("player") != player_name:
            return refused("NOT_YOUR_PIECE", "That is not one of your roads")
        if not self._is_end_road(player_name, from_edge):
            return refused("NOT_END_ROAD", "You may only move a road with a free end")
        return None

    def _hogni_move(self, player_name: str, from_edge: str, to_edge: str) -> dict:
        """Lift the end road and lay it on `to_edge`, restoring it if refused."""
        me = self.get_player(player_name)
        edge = self.edges.get(from_edge)
        edge.road = None
        if from_edge in me.roads:
            me.roads.remove(from_edge)

        self.free_roads_remaining += 1
        result = self.build_road(player_name, to_edge)
        if not result["success"]:
            # Put the lifted road back exactly where it was.
            if self.free_roads_remaining > 0:
                self.free_roads_remaining -= 1
            edge.road = {"player": player_name}
            if from_edge not in me.roads:
                me.roads.append(from_edge)
            return result
        return {"from": from_edge, "to": to_edge}

    def _choice_helper_move_road_from(self, choice: dict, option: str) -> dict:
        """Lift the tapped end road, then open where it may be laid.

        The road is picked up now so the free side it vacates counts as a legal
        destination when the second choice is built; if nothing is legal even
        after the lift, the road is set straight back down and the tile still
        owes its exchange-or-flip.
        """
        player_name = choice["player"]
        me = self.get_player(player_name)
        edge = self.edges.get(option)
        edge.road = None
        if option in me.roads:
            me.roads.remove(option)
        self.free_roads_remaining += 1

        targets = self._helper_road_targets(player_name)
        if not targets:
            if self.free_roads_remaining > 0:
                self.free_roads_remaining -= 1
            edge.road = {"player": player_name}
            if option not in me.roads:
                me.roads.append(option)
            self._open_helper_resolution(player_name)
            return {"from": option, "to": None}
        self.open_choice("helper_move_road_to", player_name, targets, from_edge=option)
        return {"from": option}

    def _choice_helper_move_road_to(self, choice: dict, option: str) -> dict:
        """Lay the already-lifted road on the tapped side, then owe exchange-or-flip."""
        player_name = choice["player"]
        from_edge = choice["context"]["from_edge"]
        result = self.build_road(player_name, option)
        if not result["success"]:
            # The road is still lifted: set it back where it came from.
            if self.free_roads_remaining > 0:
                self.free_roads_remaining -= 1
            edge = self.edges.get(from_edge)
            edge.road = {"player": player_name}
            me = self.get_player(player_name)
            if from_edge not in me.roads:
                me.roads.append(from_edge)
            self._open_helper_resolution(player_name)
            return {"from": from_edge, "to": from_edge}
        self._open_helper_resolution(player_name)
        return {"from": from_edge, "to": option}

    def _helper_end_roads(self, player_name: str) -> list:
        """This player's roads that have a free end, sorted; Hogni may move any."""
        me = self.get_player(player_name)
        return sorted(
            edge_key for edge_key in me.roads
            if self._is_end_road(player_name, edge_key)
        )

    def _lend(self, player_name: str, resources) -> list:
        """Lend the player one of each named resource from the bank, if it can.

        Returns the resources actually lent, so the caller can reclaim exactly
        those if the build it was setting up is refused.
        """
        me = self.get_player(player_name)
        lent = []
        for resource in resources:
            if self.bank.take(resource):
                me.resources[resource] = me.resources.get(resource, 0) + 1
                lent.append(resource)
        return lent

    def _reclaim(self, player_name: str, lent) -> None:
        """Take back resources lent by `_lend` after a refused build."""
        me = self.get_player(player_name)
        for resource in lent:
            if me.resources.get(resource, 0) > 0:
                me.resources[resource] -= 1
                self.bank.return_resources(resource, 1)

    def _helper_gregor(self, player_name: str, params: dict) -> dict:
        """Gregor: discard a played knight to build at a reduced cost.

        Reuses `place_settlement` and `upgrade_city` in full. The reduction is
        set up by lending the player the cards the helper waives - the wheat and
        wool a settlement normally also costs, the extra ore and grain a city
        normally costs - so the real build deducts its full price and the net
        paid is Gregor's price (Helpers_Rules.pdf, Assign Knight to Building,
        p. 10).
        """
        build = params.get("build")
        vertex = params.get("vertex")
        if build not in ("settlement", "city"):
            return refused("INVALID_BUILD", "Choose to build a settlement or a city")
        me = self.get_player(player_name)
        if me.knights_played < 1:
            return refused("NO_KNIGHT", "You have no played knight to discard")

        me.knights_played -= 1
        self.update_largest_army()

        # A settlement's full cost is wood+brick+wheat+wool; Gregor's is wood+brick,
        # so the wheat and wool are lent. A city's full cost is 3 ore + 2 wheat;
        # Gregor's is 2 ore + 1 wheat, so one of each is lent.
        waived = ["wheat", "sheep"] if build == "settlement" else ["ore", "wheat"]
        lent = self._lend(player_name, waived)

        if vertex is not None:
            return self._gregor_build(player_name, build, vertex, lent)

        # No intersection named: the player picks on the board. Only open the
        # choice if the reduced price is actually payable and a legal spot
        # exists, so a resolver that must succeed is never handed an impossible
        # build (a refused build inside a resolver is silently masked).
        if not self.can_afford(player_name, build):
            self._gregor_return_knight(player_name, lent)
            return refused("CANNOT_AFFORD", f"You cannot pay Gregor's price for a {build}")
        options = self._helper_build_targets(player_name, build)
        if not options:
            self._gregor_return_knight(player_name, lent)
            return refused("NO_BUILD_SPOT", f"You have nowhere to build a {build} right now")
        self.open_choice("helper_knight_to_building", player_name, options,
                         build=build, lent=lent)
        return {"defer_resolution": True, "build": build}

    def _gregor_build(self, player_name: str, build: str, vertex: str, lent: list) -> dict:
        """Raise Gregor's cut-price building, restoring the knight if refused."""
        if build == "settlement":
            result = self.place_settlement(player_name, vertex)
        else:
            result = self.upgrade_city(player_name, vertex)
        if not result["success"]:
            self._gregor_return_knight(player_name, lent)
            return result
        return {"built": build, "vertex": vertex}

    def _gregor_return_knight(self, player_name: str, lent: list) -> None:
        """Undo the lend and hand the discarded knight back after a failed build."""
        self._reclaim(player_name, lent)
        me = self.get_player(player_name)
        me.knights_played += 1
        self.update_largest_army()

    def _choice_helper_knight_to_building(self, choice: dict, option: str) -> dict:
        """Build at the tapped intersection with Gregor, then owe exchange-or-flip."""
        context = choice["context"]
        result = self._gregor_build(
            choice["player"], context["build"], option, list(context["lent"])
        )
        self._open_helper_resolution(choice["player"])
        return result

    def _helper_build_targets(self, player_name: str, build: str) -> list:
        """The intersections Gregor could raise this building on, sorted.

        A city goes on one of the player's own settlements; a settlement on any
        empty intersection that keeps the distance rule and touches the player's
        own network, the same tests `place_settlement` makes.
        """
        if build == "city":
            return sorted(
                vertex_key for vertex_key, vertex in self.vertices.items()
                if vertex.building and vertex.building.get("player") == player_name
                and vertex.building.get("type") == "settlement"
            )
        targets = []
        for vertex_key, vertex in self.vertices.items():
            if vertex.building or not vertex.neighbors.get("hexes"):
                continue
            if self.knight_holds(vertex_key):
                continue
            if not self._respects_distance_rule(vertex_key):
                continue
            if not self._touches_own_route(player_name, vertex_key):
                continue
            targets.append(vertex_key)
        return sorted(targets)

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
