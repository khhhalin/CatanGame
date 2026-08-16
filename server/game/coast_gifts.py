"""The Forgotten Tribe: gifts claimed by sailing a ship to a marked coast edge.

One mixin on `Game`, the pattern the other expansion modules use. Every method
is gated on the individual rule that governs it — `coast_gifts` for the claim
and the chit points, `no_build_barren_islands` for the small-island ban,
`robber_avoids_barren_islands` for the robber — so a table not running the
scenario is untouched and the base game is unchanged.

The mechanic (Seafarers 2021, Scenario 5, p. 20): the small islands around the
main land carry 18 marked coast edges. Building *or moving* a ship onto a marked
edge claims its gift, once. The three gift kinds reuse machinery that already
exists rather than reimplementing it:

- a 1-VP Catan chit adds a special victory point, banked in `gift_points` and
  read in `victory_points_for` the way the island bonus is;
- a development card is drawn from the shared dev deck (`bank.draw_dev_card`)
  and enters the hand carrying this turn's `purchase_turn`, so it cannot be
  played the same turn — the exact terms a bought card gets;
- a harbour is handed over for the player to place at one of their own coastal
  settlements. Placement is a pending choice among the legal edges; with no
  legal edge (no coastal settlement yet) the harbour is held aside and offered
  again the next time that player settles, matching "you can put the harbor
  aside until such a settlement is built".

The small islands "do not produce resources" and never receive number tokens,
so they are dealt as barren desert hexes. Which hexes are barren is derived from
the gift edges — the land hex each marked edge borders — so the no-build and
robber restrictions need no separate marking.
"""

import logging

from game.results import refused

logger = logging.getLogger(__name__)


class CoastGiftRules:
    """Claiming coast gifts, and the small-island building and robber bans."""

    # --- Board setup -------------------------------------------------------

    def setup_coast_gifts_board(self):
        """Read the map's marked gift edges and the barren islands they border.

        A gift edge is a hex-side key the map declares; the author may name it by
        either of the side's two coordinates, so each is canonicalised to the one
        key the board holds and any that names nothing here is dropped. The
        barren small islands are the land hexes those edges border that are not
        the main land, which is all the no-build and robber bans need. A no-op for
        a map that prints no gifts, and for every built-in layout bar this one.
        """
        definition = self.map_definition
        if definition is None or not getattr(definition, 'gift_edges', ()):
            return
        for edge_key, kind, port in definition.gift_edges:
            canonical = self.canonical_edge_key(edge_key)
            if canonical is None:
                continue
            self.gift_edges[canonical] = {'gift': kind, 'port': port}
            for hex_key in self.land_hexes_of_edge(canonical):
                if not self.is_main_land(hex_key):
                    self.barren_island_hexes.add(hex_key)

    # --- Claiming a gift ---------------------------------------------------

    def claim_coast_gift(self, player_name: str, edge_key: str) -> dict | None:
        """Claim the gift on this edge, or None if there is nothing to claim.

        Called after a ship is built or moved onto `edge_key`. A no-op without
        `coast_gifts`, away from a marked edge, or on an edge already claimed, so
        the ship methods can call it unconditionally the way `build_ship` calls
        `discover_from_build`. Returns a dict describing the gift applied.
        """
        if not self.rules['coast_gifts']:
            return None
        gift = self.gift_edges.get(edge_key)
        if gift is None or edge_key in self.claimed_gift_edges:
            return None

        self.claimed_gift_edges.add(edge_key)
        kind = gift['gift']
        if kind == 'victory_point':
            self.gift_points[player_name] = self.gift_points.get(player_name, 0) + 1
            logger.debug("%s claimed a 1-VP coast gift at %s", player_name, edge_key)
            return {'gift': 'victory_point', 'victory_points': self.gift_points[player_name]}
        if kind == 'dev_card':
            return self._grant_gift_dev_card(player_name, edge_key)
        return self._grant_gift_harbor(player_name, gift['port'])

    def _grant_gift_dev_card(self, player_name: str, edge_key: str) -> dict:
        """Draw the next development card as a gift, on the same terms as a buy.

        Shares the dev deck with `buy_dev_card`: the card is drawn from
        `bank.draw_dev_card` and stamped with this turn so it cannot be played
        the same turn. An empty or absent deck yields no card, which is a legal
        outcome rather than a refusal.
        """
        if not self.dev_deck_in_play():
            return {'gift': 'dev_card', 'card_type': None}
        card_type = self.bank.draw_dev_card()
        if card_type is None:
            return {'gift': 'dev_card', 'card_type': None}
        player = self.get_player(player_name)
        player.dev_cards[card_type]['count'] += 1
        player.dev_cards[card_type]['purchase_turn'] = self.turn_count
        logger.debug("%s claimed a dev-card coast gift at %s", player_name, edge_key)
        return {'gift': 'dev_card', 'card_type': card_type}

    def _grant_gift_harbor(self, player_name: str, port_type: str) -> dict:
        """Hand a harbour to a player to place at one of their coastal settlements.

        Opens a pending choice among the legal placement edges; the resolver
        drops the harbour on the chosen one. With no legal edge — no coastal
        settlement of the player's has a free, non-adjacent coastal side — the
        harbour is held aside on `held_gift_harbors` and offered again the next
        time that player settles.
        """
        port = self._port_dict(port_type)
        options = self.legal_gift_harbor_edges(player_name)
        if options:
            self.open_choice('gift_harbor', player_name, options, port=port)
            return {'gift': 'harbor', 'port': port, 'pending': True}
        self.held_gift_harbors.setdefault(player_name, []).append(port)
        return {'gift': 'harbor', 'port': port, 'pending': False, 'held': True}

    @staticmethod
    def _port_dict(port_type: str) -> dict:
        """The harbour payload the board and the trade rules already read.

        The same shape `_assign_ports` writes onto an edge: a generic 3:1 or a
        resource 2:1, so a gift harbour trades exactly like a printed one.
        """
        if port_type == 'generic':
            return {'type': 'generic'}
        return {'type': 'resource', 'resource': port_type}

    def legal_gift_harbor_edges(self, player_name: str) -> list:
        """Coastal sides a player may drop a gift harbour on, in a stable order.

        A harbour sits on a coastal side of one of the player's own settlements
        or cities, on an empty side that carries no ship, and never adjacent to
        or on another harbour — "harbors must never occupy adjacent or the same
        edges". Sorted so an auto-resolved choice is deterministic.
        """
        edges = set()
        for vertex_key in self._own_building_vertices(player_name):
            vertex = self.vertices.get(vertex_key)
            if vertex is None:
                continue
            for edge_key in vertex.neighbors.get('edges', []):
                if self._harbor_placement_ok(edge_key):
                    edges.add(edge_key)
        return sorted(edges)

    def _own_building_vertices(self, player_name: str) -> list:
        """Intersections where this player has a settlement or city."""
        return [
            vertex_key
            for vertex_key, vertex in self.vertices.items()
            if vertex.building and vertex.building.get('player') == player_name
        ]

    def _harbor_placement_ok(self, edge_key: str) -> bool:
        """Whether a gift harbour could be dropped on this side."""
        edge = self.edges.get(edge_key)
        if edge is None or not self.is_sea_edge(edge_key):
            return False
        if edge.port is not None or edge.ship is not None:
            return False
        # No harbour may touch another: a side is barred if either of its ends
        # already carries a port.
        for vertex_key in edge.neighbors.get('vertices', []):
            vertex = self.vertices.get(vertex_key)
            if vertex is not None and vertex.port:
                return False
        return True

    def _choice_gift_harbor(self, choice: dict, option: str) -> dict:
        """Place a gift harbour on the coastal side the player chose."""
        self._place_gift_harbor(option, choice['context']['port'])
        return {'edge': option, 'port': choice['context']['port']}

    def _place_gift_harbor(self, edge_key: str, port: dict):
        """Drop a harbour on an edge, the way `_assign_ports` does.

        `edge.port` is the geometry; `vertex.port` is kept populated on both
        ends because the trade rules, the save file and the renderer all read it
        there — a copy per vertex so a mutation of one intersection cannot
        silently change the whole harbour.
        """
        edge = self.edges[edge_key]
        edge.port = dict(port)
        for vertex_key in edge.neighbors['vertices']:
            self.vertices[vertex_key].port = dict(port)

    def offer_held_gift_harbors(self, player_name: str):
        """Offer any harbour a player is holding, now they may have a spot.

        Called after a settlement is built (gated on `coast_gifts`), so a player
        who claimed a harbour with nowhere to put it is asked to place it as soon
        as a legal side opens up. A no-op when nothing is held or nothing is
        legal yet.
        """
        held = self.held_gift_harbors.get(player_name)
        if not held:
            return
        options = self.legal_gift_harbor_edges(player_name)
        if not options:
            return
        port = held.pop(0)
        self.open_choice('gift_harbor', player_name, options, port=port)

    # --- The barren small islands ------------------------------------------

    def barren_island_build_refusal(self, hex_keys) -> dict | None:
        """Refuse a settlement that would stand on a barren small island.

        "No settlement can be built on the surrounding small islands that do not
        produce resources." A no-op without `no_build_barren_islands` and away
        from a barren island, so every other board is unaffected.
        """
        if not self.rules['no_build_barren_islands']:
            return None
        if any(hex_key in self.barren_island_hexes for hex_key in hex_keys):
            return refused(
                'BARREN_ISLAND',
                'You cannot build on the small islands of the Forgotten Tribe',
            )
        return None
