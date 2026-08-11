"""The resource registry the client draws terrain from.

What a player would notice if these broke: a hex whose terrain has no definition
renders with no colour and no pattern (a blank tile), and a definition naming a
pattern the renderer does not know draws nothing over the fill. So the registry
is checked against the terrains the board can actually deal, and every definition
against the renderer's known pattern styles — never a second copy of the literal.
"""

from game import resources, tiles


def test_the_registry_covers_every_terrain_the_board_can_deal():
    registry = resources.registry()
    # A hex carries its `hex_type` as `type`, and the client looks a definition
    # up by that. Every terrain the engine can register must have one, checked
    # against the terrain registry rather than a hand-copied list.
    for terrain in tiles.REGISTRY.values():
        assert terrain.hex_type in registry, \
            f"terrain {terrain.hex_type!r} has no resource definition — it would render blank"


def test_every_definition_is_complete_and_names_a_known_pattern():
    for resource_id, definition in resources.registry().items():
        assert {'name', 'color', 'symbol', 'pattern'} <= set(definition), \
            f"{resource_id} is missing a field: {definition}"
        assert definition['color'].startswith('#'), \
            f"{resource_id} colour {definition['color']!r} is not a hex colour"
        assert definition['pattern'] in resources.PATTERN_STYLES, \
            f"{resource_id} names pattern {definition['pattern']!r}, which the renderer cannot draw"


def test_a_file_override_retints_a_resource_and_adds_a_new_one(tmp_path, monkeypatch):
    """The `data/resources.json` file overrides the defaults key by key — a retint
    of an existing resource, and a brand-new one — without restating untouched
    fields. This is the flexibility the whole feature exists for."""
    import json

    path = tmp_path / 'resources.json'
    path.write_text(json.dumps({
        'wood': {'color': '#123456'},
        'gold': {'name': 'Gold', 'color': '#d9a441', 'symbol': 'coin', 'pattern': 'stipple'},
    }))
    monkeypatch.setattr(resources, '_PATH', str(path))

    registry = resources.reload()
    assert registry['wood']['color'] == '#123456'
    assert registry['wood']['name'] == 'Wood', 'an untouched field must survive the merge'
    assert registry['gold'] == {'name': 'Gold', 'color': '#d9a441',
                                'symbol': 'coin', 'pattern': 'stipple'}
    resources.reload()  # restore the module registry for other tests
