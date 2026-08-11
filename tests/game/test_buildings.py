"""The building registry the client prices and labels every build from.

What a player would notice if these broke: a Costs panel row with no name or no
glyph, or — worse — a price shown that is not the price the bank charges. So the
registry is checked against the builds the engine actually prices, every
definition for a complete set of fields, and every listed cost against what
`get_cost` really charges — never a second copy of the literal.
"""

import random

from game import buildings
from game import rules as rules_module
from game.game import Game


def _game():
    return Game(['Alice', 'Bob'], [], {}, rng=random.Random(6),
                rules=rules_module.defaults())


def test_the_registry_prices_every_flat_build_the_engine_charges():
    registry = buildings.registry()
    # The engine prices flat builds out of `building_costs`, which is the
    # registry's cost view. Every build it can charge for must have a definition
    # here, checked against the engine's own price table rather than a copy.
    for build_type in _game().building_costs:
        assert build_type in registry, \
            f"build {build_type!r} has no definition — its Costs row would be blank"


def test_every_definition_is_complete():
    for build_id, definition in buildings.registry().items():
        assert {'name', 'cost', 'icon'} <= set(definition), \
            f"{build_id} is missing a field: {definition}"
        assert definition['name'], f"{build_id} has an empty name"
        assert isinstance(definition['cost'], dict) and definition['cost'], \
            f"{build_id} cost {definition['cost']!r} is not a resource dict"
        assert isinstance(definition['icon'], str) and definition['icon'], \
            f"{build_id} icon {definition['icon']!r} is not a sprite concept id"


def test_the_registry_cost_is_what_get_cost_actually_charges():
    """The anti-drift pin CLAUDE.md demands: the price listed beside a build's
    name and icon is the price the engine really charges for it. `get_cost` is
    the one true cost path — base cost through every active modifier — so a
    registry line that drifted from it would show one price while the bank took
    another. Checked against `get_cost`, never a hand-copied literal."""
    game = _game()
    for build_id, definition in buildings.registry().items():
        assert definition['cost'] == game.get_cost(build_id), \
            f"{build_id} lists {definition['cost']} but the engine charges " \
            f"{game.get_cost(build_id)}"


def test_a_file_override_reprices_a_build_and_adds_a_new_one(tmp_path, monkeypatch):
    """The `data/buildings.json` file overrides the defaults key by key — a
    reprice of an existing build, and a brand-new one — without restating
    untouched fields. This is the flexibility the whole feature exists for."""
    import json

    path = tmp_path / 'buildings.json'
    path.write_text(json.dumps({
        'road': {'cost': {'wood': 2, 'brick': 2}},
        'tower': {'name': 'Tower', 'cost': {'ore': 5}, 'icon': 'city'},
    }))
    monkeypatch.setattr(buildings, '_PATH', str(path))

    try:
        registry = buildings.reload()
        assert registry['road']['cost'] == {'wood': 2, 'brick': 2}
        assert registry['road']['name'] == 'Road', 'an untouched field must survive the merge'
        assert registry['tower'] == {'name': 'Tower', 'cost': {'ore': 5}, 'icon': 'city'}
    finally:
        # The module registry is process-global and every Game reads its costs
        # from it, so the default file path must be restored *and* re-read before
        # the next test builds a board — undo the patch first, then reload.
        monkeypatch.undo()
        buildings.reload()


def test_the_download_button_serves_the_registry_as_a_saveable_file(socket_app):
    """The editor's `Buildings ↓` link points at `/buildings.json`. If that route
    404s the button downloads nothing; if it forgets the attachment header the
    browser opens it in a tab instead of saving; if the body is not the registry
    the file is useless as a template. So all three are pinned."""
    import json

    response = socket_app.test_client().get('/buildings.json')

    assert response.status_code == 200
    assert response.mimetype == 'application/json'
    assert 'attachment' in response.headers.get('Content-Disposition', '')
    assert 'buildings.json' in response.headers.get('Content-Disposition', '')
    body = json.loads(response.get_data(as_text=True))
    assert body == buildings.registry(), 'the file must be the live registry'
