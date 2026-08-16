"""The Seafarers scenario "The Fog Islands", built as a board plus a preset.

Source [OFFICIAL]: Seafarers 2021 rulebook, Scenario 3 "The Fog Islands"
(p. 14). Two islands start face-up; a band of fog hexes between them is dealt
face-down and turned face up only when a ship or road reaches one. The rulebook
gives the discoverer of a producing land hex "1 resource card of the type
produced by that land hex" and a revealed sea hex "no reward"; there are "no
special victory point chits in this scenario", and the game ends at 12.

The scenario reuses the exploration machinery Explorers & Pirates already has:
the hidden-tile pool, the per-region token stacks and `_reveal_hex` are shared,
and only the trigger (build, not transport-ship move) and the reward
(resources-only, no gold, no VP) differ. So what is worth pinning is the board
the scenario ships — read off the generated board, never a literal copied from
the file — and that a ship reaching a fog hex reveals it for a resource and
nothing more.

The printed face-down stack holds two gold fields. This engine has no Seafarers
gold-field production (resource-of-choice on a roll), only the Explorers &
Pirates gold currency, so a gold field would be dealt and then pay nothing when
its number came up. The map deals those two hexes as one extra sheep and one
extra wood instead; the 12 fog hexes and 10 fog tokens are otherwise faithful,
and `test_no_gold_and_no_desert` pins that substitution.
"""

import random
from collections import Counter

from game import map_store, maps
from game import rules as rules_module
from game.game import Game
from seafarers_board import give_building


def fog_game(players=('Alice', 'Bob'), seed=12345):
    """A Fog Islands game past setup, on the built-in fog board."""
    defn = maps.parse_map(map_store.read_map('fog-islands'))
    chosen = dict(rules_module.preset_rules('fog_islands'))
    chosen['turn_order'] = 'lobby'
    game = Game(list(players), [], rng=random.Random(seed), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.start_turn()
    return game


def face_up_land(game):
    return [key for key, hex_obj in game.hexes.items()
            if hex_obj.type != 'ocean' and not hex_obj.hidden]


def fog_hexes(game):
    return [key for key, hex_obj in game.hexes.items() if hex_obj.hidden]


def _single_fog_target(game, want_sea):
    """A sea side bordering exactly one fog hex, sea or land as asked.

    `want_sea` picks a fog hex whose real terrain is water (pays nothing) or a
    producing land hex (pays its resource). Searched on the generated board so
    the test never copies the deal.
    """
    for edge_key in sorted(game.edges):
        if not game.is_sea_edge(edge_key):
            continue
        fogs = [hk for hk in game.edges[edge_key].neighbors['hexes']
                if game.hexes[hk].hidden]
        if len(fogs) != 1:
            continue
        is_sea = game.hexes[fogs[0]].type == 'ocean'
        if is_sea == want_sea:
            return edge_key, fogs[0]
    raise AssertionError(f'no single-fog {"sea" if want_sea else "land"} target')


class TestTheBoardAsDealt:
    """Every assertion reads the board the engine generated, so a literal that
    drifts from the file is caught where it is consumed, not where it is
    declared."""

    def test_it_deals_two_face_up_islands_of_seven_hexes(self):
        game = fog_game()
        island_of = game.islands()
        sizes = Counter(island_of[key] for key in face_up_land(game))
        assert sorted(sizes.values()) == [7, 7]
        assert len(face_up_land(game)) == 14

    def test_the_face_up_terrain_is_the_three_player_component_list(self):
        """Rulebook face-up land: 2 fields, 2 hills, 2 mountains, 4 pasture,
        4 forest (14 hexes)."""
        game = fog_game()
        counts = Counter(game.hexes[key].type for key in face_up_land(game))
        assert counts == {'wheat': 2, 'brick': 2, 'ore': 2, 'sheep': 4, 'wood': 4}

    def test_the_face_up_number_tokens_are_the_printed_fourteen(self):
        game = fog_game()
        tokens = sorted(game.hexes[key].number for key in face_up_land(game))
        assert tokens == [3, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 11, 11, 12]

    def test_it_deals_twelve_fog_hexes_face_down_with_no_number(self):
        game = fog_game()
        fogs = fog_hexes(game)
        assert len(fogs) == 12
        assert all(game.hexes[key].number is None for key in fogs)

    def test_the_fog_stack_is_the_printed_mix_with_gold_substituted(self):
        """The face-down stack's real terrain (secret to clients, known to the
        server): 2 of each producing resource and 2 sea. The rulebook's 2 gold
        fields are the extra sheep and wood; the 10 producers and 2 sea hold."""
        game = fog_game()
        counts = Counter(game.hexes[key].type for key in fog_hexes(game))
        assert counts == {'wheat': 2, 'brick': 2, 'ore': 2, 'sheep': 2,
                          'wood': 2, 'ocean': 2}

    def test_no_gold_and_no_desert(self):
        """No gold field pays out in a Seafarers game here, and the scenario
        prints no desert, so neither belongs on the dealt board."""
        game = fog_game()
        kinds = {game.hexes[key].type for key in game.hexes}
        assert 'desert' not in kinds
        assert not any('gold' in kind for kind in kinds)


class TestDiscoveryRevealsForResourcesOnly:
    """A ship reaching a fog hex is the whole scenario. The reward is a resource
    for a land hex and nothing for a sea hex — never gold, never a victory
    point (Seafarers 2021, Scenario 3)."""

    def _scaffold(self, game, edge_key):
        """A settlement at the target's end, an empty hand and a free ship.

        Scaffolding only — the behaviour under test is the reveal the build
        triggers, so a real turn's roads and resources would add noise, and the
        free ship keeps the resource hand showing the reward alone. Called
        before the victory-point reading so the settlement's own point is not
        mistaken for a discovery point."""
        give_building(game, 'Alice', game.edges[edge_key].neighbors['vertices'][0])
        alice = game.get_player('Alice')
        alice.resources = {}
        alice.gold = 0
        game.free_roads_remaining = 1

    def test_reaching_a_land_fog_hex_pays_one_resource_of_its_type(self):
        game = fog_game()
        target, fog = _single_fog_target(game, want_sea=False)
        terrain = game.hexes[fog].type
        self._scaffold(game, target)
        vp_before = game.victory_points_for('Alice')

        result = game.build_ship('Alice', target)

        assert result['success']
        assert result['revealed'] == [fog]
        assert not game.hexes[fog].hidden
        assert game.hexes[fog].number in maps.TOKEN_VALUES
        alice = game.get_player('Alice')
        assert alice.resources == {terrain: 1}
        assert alice.gold == 0
        assert game.victory_points_for('Alice') == vp_before

    def test_reaching_a_sea_fog_hex_pays_nothing(self):
        game = fog_game()
        target, fog = _single_fog_target(game, want_sea=True)
        self._scaffold(game, target)
        vp_before = game.victory_points_for('Alice')

        result = game.build_ship('Alice', target)

        assert result['success']
        assert result['revealed'] == [fog]
        assert not game.hexes[fog].hidden
        assert game.hexes[fog].number is None
        alice = game.get_player('Alice')
        assert alice.resources == {}
        assert alice.gold == 0
        assert game.victory_points_for('Alice') == vp_before


class TestThePreset:
    def test_it_turns_on_fog_reveal_and_ends_at_twelve_without_island_points(self):
        """A rulebook pin: The Fog Islands ends at 12, reveals fog for resources,
        and — unlike the other new-shore scenarios — pays no special island
        victory points, so that rule stays off."""
        chosen = rules_module.preset_rules('fog_islands')
        assert chosen is not None
        assert chosen['victory_target'] == 12
        assert chosen['fog_reveal'] is True
        assert chosen['ships'] is True
        assert chosen['pirate'] is True
        assert chosen['island_victory_points'] is False
