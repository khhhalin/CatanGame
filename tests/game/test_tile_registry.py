"""The terrain registry is the one place a tile's facts live.

What a player would notice if this broke: a hex that stopped producing (or one
that started producing water), a number token dealt onto the sea, or a city that
lost its commodity. The scattered terrain constants now derive from the registry,
so this pins the derivation against the registry rather than against a second
copy of the literal, and proves a new terrain flows through every consumer.
"""

import pytest
from game import cities_knights as ck_module
from game import maps, tiles


class TestTheBaseTerrains:
    def test_the_producers_and_the_barren_tiles(self):
        for name in ("wood", "brick", "sheep", "wheat", "ore"):
            assert tiles.produces(name) == name
            assert tiles.takes_token(name)
            assert not tiles.is_sea(name)
        for name in ("desert", "sea"):
            assert tiles.produces(name) is None
            assert not tiles.takes_token(name)

    def test_sea_carries_both_names(self):
        assert tiles.hex_type_of("sea") == "ocean"
        assert tiles.is_sea("sea")
        # A check written against the engine word reaches the same tile.
        assert tiles.is_sea("ocean")
        assert not tiles.takes_token("ocean")
        assert tiles.get("sea") is tiles.get("ocean")

    def test_only_wood_sheep_and_ore_carry_a_commodity(self):
        assert tiles.commodities_by_terrain() == {
            "wood": "paper", "sheep": "cloth", "ore": "coin",
        }


class TestTheScatteredConstantsDeriveFromIt:
    def test_maps_terrain_tables_come_from_the_registry(self):
        assert maps.TERRAIN_TYPES == tiles.names()
        assert maps.RESOURCE_TERRAINS == tiles.resource_terrains()
        # takes_a_token answers for the map word and the engine word alike.
        assert maps.takes_a_token("wood")
        assert not maps.takes_a_token("sea")
        assert not maps.takes_a_token("ocean")

    def test_the_commodity_pairing_comes_from_the_registry(self):
        assert ck_module.COMMODITY_FROM_TERRAIN == tiles.commodities_by_terrain()


class TestTheExtensionSeam:
    """A new terrain is one register() call; every consumer picks it up."""

    def test_registering_a_terrain_flows_through_the_helpers(self):
        tiles.register(tiles.Terrain(
            "_test_swamp", "_test_swamp", produces="brick", commodity=None,
        ))
        try:
            assert "_test_swamp" in tiles.names()
            assert "_test_swamp" in tiles.resource_terrains()
            assert tiles.produces("_test_swamp") == "brick"
            assert tiles.takes_token("_test_swamp")
            # Derived through maps, since maps.takes_a_token delegates to tiles.
            assert maps.takes_a_token("_test_swamp")
        finally:
            terrain = tiles.REGISTRY.pop("_test_swamp", None)
            if terrain is not None:
                tiles._BY_HEX_TYPE.pop(terrain.hex_type, None)

    def test_a_barren_land_terrain_takes_no_token(self):
        # A Rivers-of-Catan style tile: land, but pays nobody.
        tiles.register(tiles.Terrain("_test_river", "_test_river", produces=None))
        try:
            assert not tiles.takes_token("_test_river")
            assert not tiles.is_sea("_test_river")
        finally:
            terrain = tiles.REGISTRY.pop("_test_river", None)
            if terrain is not None:
                tiles._BY_HEX_TYPE.pop(terrain.hex_type, None)

    def test_a_duplicate_name_or_hex_type_is_refused(self):
        with pytest.raises(ValueError, match="duplicate terrain name"):
            tiles.register(tiles.Terrain("wood", "_x", produces="wood"))
        with pytest.raises(ValueError, match="duplicate terrain hex_type"):
            tiles.register(tiles.Terrain("_y", "ocean", produces=None))
