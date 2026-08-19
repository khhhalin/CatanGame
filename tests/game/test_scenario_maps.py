"""A named scenario preset must deal its own board.

The Seafarers named-scenario presets (Four Islands, Fog Islands, Through the
Desert, The Forgotten Tribe, Cloth for Catan) each have a dedicated built-in
map, but their presets shipped without binding it: `preset_rules('four_islands')`
left `board_map` at 'standard', so a player who clicked "The Four Islands" — and
the lobby's scenario preview — got an ordinary board, and the scenario mechanics
(foreign islands, fog hexes, the desert belt, gift edges, villages) had nothing
to act on. This pins each preset to the board its rules need.
"""

import pytest
from game import map_store, rules

# Each named scenario preset and the built-in map it must deal. Base Seafarers
# ('Heading for New Shores') gets a real sea board rather than the landlocked
# standard one.
SCENARIO_BOARDS = {
    "seafarers": "large-island",
    "four_islands": "four-islands",
    "fog_islands": "fog-islands",
    "through_the_desert": "through-the-desert",
    "forgotten_tribe": "forgotten-tribe",
    "cloth_for_catan": "cloth-for-catan",
    "krakatoa": "krakatoa",
}


@pytest.mark.parametrize("preset_id,expected_map", SCENARIO_BOARDS.items())
def test_a_scenario_preset_binds_its_own_board(preset_id, expected_map):
    resolved = rules.preset_rules(preset_id)
    # The lobby ignores board_map unless the layout is custom, so both must be set.
    assert resolved["board_layout"] == "custom", (
        f"{preset_id} does not switch to a custom board_layout, "
        f"so its board_map is ignored and it deals a random board"
    )
    assert resolved["board_map"] == expected_map, (
        f"{preset_id} deals {resolved['board_map']!r}, not its own {expected_map!r}"
    )
    # The board it names has to exist, or starting the scenario would refuse.
    assert map_store.load_definition(expected_map) is not None, (
        f"{expected_map} is not a loadable built-in map"
    )
