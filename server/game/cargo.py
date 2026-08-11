"""Cargo pieces — the Explorers & Pirates settlers and crews.

Split out of `game.py` alongside the other rules mixins; see `board.py` for the
pattern. Settlers and crews are the two things a harbor settlement's basin and a
transport ship's hold carry (expansions.md 903-928). A settler is a large piece
that fills a hold; carried to a coastal corner, a settler ship founds a
settlement there for free. A crew is a small piece — two fit a hold — that rides
to a mission destination and is landed there.

Both build sites and the hold's capacity are transport's, so this module reuses
transport's slot arithmetic rather than re-deriving it: a basin holds "1 large
or 2 small" exactly as a hold does (910, 925). Loading and unloading a piece
between a basin and a hold is transport's `load_transport_ship` /
`unload_transport_ship` — a cargo piece already carries the `size` these methods
read, so nothing here re-implements them; a piece is stamped with its size when
it is built, below.

Every method is gated on `self.rules['cargo_settlers']` / `self.rules['crews']`,
never on an expansion name. Both rules depend on `transport_ships` and
`harbor_settlements`, so the basins and holds the pieces live in already exist;
like those modules, cargo needs no `self.ep` container.
"""

from game.results import refused
from game.transport import HOLD_SLOTS, _is_transport_ship, _piece_slots

# What each cargo piece is: the rule that switches it on, the price funnelled
# through `get_cost`, the size that decides how much of a hold or basin it fills,
# and the player supply field it is counted against.
_CARGO = {
    'settler': {'rule': 'cargo_settlers', 'size': 'large', 'supply': 'settlers'},
    'crew': {'rule': 'crews', 'size': 'small', 'supply': 'crews'},
}


class CargoRules:
    """Building, founding-with and landing Explorers & Pirates cargo pieces."""

    # --- Building settlers and crews ---------------------------------------

    def build_settler(self, player_name: str, into: str, key: str) -> dict:
        """Build a settler into a harbor basin (`into='basin'`) or ship hold
        (`into='hold'`), paying a settlement's price (expansions.md 903-910)."""
        return self._build_cargo(player_name, 'settler', into, key)

    def build_crew(self, player_name: str, into: str, key: str) -> dict:
        """Build a crew into a harbor basin or ship hold for 1 ore + 1 wool
        (expansions.md 919-925)."""
        return self._build_cargo(player_name, 'crew', into, key)

    def _build_cargo(self, player_name: str, piece_type: str, into: str, key: str) -> dict:
        spec = _CARGO[piece_type]
        if not self.rules[spec['rule']]:
            return refused('RULE_NOT_IN_PLAY', f'This table is not playing with {piece_type}s')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked
        moved = self.movement_phase_block()
        if moved is not None:
            return moved
        if self.game_phase == "setup":
            return refused('WRONG_PHASE', f'Cannot build a {piece_type} during setup phase')

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can build pieces')

        if not self.has_piece_available(player_name, piece_type):
            limit = getattr(self, f'MAX_{piece_type.upper()}S')
            return refused('NO_PIECES_LEFT', f'You have used all {limit} {piece_type}s')

        container = self._cargo_container(player_name, into, key)
        if container is None:
            return refused(
                'INVALID_TARGET', 'A cargo piece is built into a harbor basin or a ship hold'
            )

        piece = {'type': piece_type, 'size': spec['size']}
        if self._hold_used(container) + _piece_slots(piece) > HOLD_SLOTS:
            return refused('HOLD_FULL', 'A basin or hold takes one large piece or two small ones')

        if not self.can_afford(player_name, piece_type):
            return refused('INSUFFICIENT_RESOURCES', self._cost_message(piece_type))
        self.deduct_cost(player_name, piece_type)

        container.append(piece)
        player = self.get_player(player_name)
        setattr(player, spec['supply'], getattr(player, spec['supply']) + 1)
        return {'success': True, 'error': ''}

    def _cargo_container(self, player_name: str, into: str, key: str):
        """The basin list or hold list a piece is built into, or None.

        A basin is a harbor settlement of the player's own; a hold is one of
        the player's transport ships lying beside a harbor settlement, the one
        site cargo is built at (expansions.md 907, 922).
        """
        if into == 'basin':
            vertex = self.vertices.get(key)
            if (
                vertex is not None
                and vertex.building is not None
                and vertex.building.get('type') == 'harbor_settlement'
                and vertex.building.get('player') == player_name
            ):
                return vertex.building['basin']
            return None
        if into == 'hold':
            edge = self.edges.get(key)
            if (
                edge is not None
                and _is_transport_ship(edge.ship)
                and edge.ship.get('player') == player_name
                and self._adjacent_harbor_settlement(player_name, key) is not None
            ):
                return edge.ship['cargo']
            return None
        return None

    # --- Founding a settlement with a settler ship -------------------------

    def found_settlement_from_ship(
        self, player_name: str, edge_key: str, vertex_key: str
    ) -> dict:
        """Land a settler ship at a coastal corner to found a free settlement.

        A distinct build, not a branch of `place_settlement`: the settler ship
        and the settler in its hold are both returned to supply, and the new
        settlement is placed at the corner one of the ship's ends points to,
        at no resource cost (expansions.md 913-916). It needs no road or route
        connection — sailing there is the point — only an empty coastal corner
        that keeps the distance rule.
        """
        if not self.rules['cargo_settlers']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with settlers')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked
        if self.game_phase == "setup":
            return refused('WRONG_PHASE', 'Cannot found a settlement during setup phase')

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can found settlements')

        edge = self.edges.get(edge_key)
        if edge is None or not _is_transport_ship(edge.ship):
            return refused('INVALID_TARGET', 'There is no transport ship there')
        if edge.ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'You can only found from your own ships')
        settler_index = next(
            (i for i, piece in enumerate(edge.ship['cargo']) if piece['type'] == 'settler'),
            None,
        )
        if settler_index is None:
            return refused('NO_SETTLER', 'That ship is carrying no settler')

        vertex = self.vertices.get(vertex_key)
        if vertex is None:
            return refused('INVALID_TARGET', 'Invalid vertex')
        if vertex_key not in edge.neighbors['vertices']:
            return refused(
                'INVALID_PLACEMENT', 'A settler ship founds only at a corner it points to'
            )
        if not vertex.neighbors['hexes']:
            return refused(
                'INVALID_PLACEMENT', 'A settlement founds at the corner of a terrain hex'
            )
        # No building on a corner beside an undiscovered hex, exactly as
        # `place_settlement` refuses one (891). A no-op unless the table is
        # exploring; founding is how a revealed area is first settled.
        if self.rules['ships_explore']:
            undiscovered = self.undiscovered_build_refusal(vertex.neighbors['hexes'])
            if undiscovered is not None:
                return undiscovered
        if vertex.building is not None:
            return refused('OCCUPIED', 'This location already has a building')
        if self.knight_holds(vertex_key):
            return refused('OCCUPIED', 'A knight is standing here')
        if not self._respects_distance_rule(vertex_key):
            return refused(
                'INVALID_PLACEMENT', 'Cannot found a settlement next to another settlement'
            )
        if not self.has_piece_available(player_name, 'settlement'):
            return refused(
                'NO_PIECES_LEFT', f'You have used all {self.MAX_SETTLEMENTS} settlements'
            )

        # The ship and its settler both return to supply, then the settlement
        # takes the corner for free (915-916).
        edge.ship['cargo'].pop(settler_index)
        edge.ship = None
        player = self.get_player(player_name)
        if edge_key in player.ships:
            player.ships.remove(edge_key)
        player.settlers -= 1

        vertex.building = {'type': 'settlement', 'player': player_name}
        player.settlements.append(vertex_key)

        self.track_settlement(player_name, vertex_key)
        self.update_harbormaster()
        self.update_longest_road()
        island_points = self.record_island_settlement(player_name, vertex_key, award=True)
        return {'success': True, 'error': '', 'island_points': island_points}

    # --- Landing a crew on a mission destination ---------------------------

    def is_crew_destination(self, vertex_key: str) -> bool:
        """Whether a crew may be landed at this vertex.

        A crew is landed only on a mission destination — an active pirate lair
        or a spice village (expansions.md 928). No mission provides one yet
        (they land in Wave 4), so this is always False; the mission modules
        extend it. Tests stub it to exercise the landing primitive.
        """
        return False

    def place_crew_on_destination(
        self, player_name: str, edge_key: str, vertex_key: str
    ) -> dict:
        """Land a crew from a ship's hold onto a mission destination.

        The build/load/carry/place-on-destination primitive the mission agents
        (Wave 4) consume. The ship must point an end at the destination; the
        crew is removed from the hold and handed to the destination — what the
        destination does with it is the mission's to decide, so the crew is not
        returned to supply here.
        """
        if not self.rules['crews']:
            return refused('RULE_NOT_IN_PLAY', 'This table is not playing with crews')
        if self.must_move_robber:
            return refused('MUST_MOVE_ROBBER', 'You must move the robber first')
        blocked = self.choice_block(player_name)
        if blocked is not None:
            return blocked

        current_name = self.current_player_name()
        if current_name != player_name:
            return refused('NOT_YOUR_TURN', f'Only {current_name} can land crews')

        edge = self.edges.get(edge_key)
        if edge is None or not _is_transport_ship(edge.ship):
            return refused('INVALID_TARGET', 'There is no transport ship there')
        if edge.ship.get('player') != player_name:
            return refused('NOT_YOUR_PIECE', 'You can only land crews from your own ships')
        crew_index = next(
            (i for i, piece in enumerate(edge.ship['cargo']) if piece['type'] == 'crew'),
            None,
        )
        if crew_index is None:
            return refused('NO_CREW', 'That ship is carrying no crew')

        if vertex_key not in edge.neighbors['vertices']:
            return refused('INVALID_PLACEMENT', 'A ship lands a crew only at a corner it points to')
        if not self.is_crew_destination(vertex_key):
            return refused('NOT_A_DESTINATION', 'A crew is landed only on a mission destination')

        piece = edge.ship['cargo'].pop(crew_index)
        return {'success': True, 'error': '', 'crew': piece}
