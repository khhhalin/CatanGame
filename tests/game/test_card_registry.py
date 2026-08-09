"""The card registry unifies both card families behind one descriptor + resolver.

What a player would notice if this broke: a progress card that no longer plays
(the registry lost its resolver), a development card whose effect stopped firing
(the effect dispatch went through the registry and missed), or a card whose
metadata drifted from the deck it is dealt from.

The registry mirrors descriptor fields that are *authored elsewhere*
(`progress_cards.py`), so every mirror is pinned against its source here rather
than asserted against a second copy of the literal.
"""

import pytest
from game import cards, progress_cards


class TestProgressCardsAreRegistered:
    def test_every_progress_card_is_registered_matching_its_source(self):
        for descriptor in progress_cards.PROGRESS_CARDS:
            card = cards.get(descriptor["id"])
            assert card is not None, f"{descriptor['id']} missing from the registry"
            assert card.family == cards.PROGRESS
            # Mirrored fields pinned against the authoring source, not a copy.
            assert card.name == descriptor["name"]
            assert card.deck == descriptor["deck"]
            assert card.timing == descriptor["timing"]
            assert card.needs_target == descriptor["needs_target"]
            assert card.victory_points == descriptor["victory_points"]

    def test_a_playable_progress_card_has_a_resolver(self):
        for descriptor in progress_cards.PROGRESS_CARDS:
            card = cards.get(descriptor["id"])
            if descriptor["timing"] == progress_cards.TIMING_IMMEDIATE:
                # Revealed for its point on draw, never played — no resolver.
                assert card.resolve is None
                assert card.victory_points == 1
            else:
                assert callable(card.resolve), f"{card.id} has no resolver"

    def test_the_registry_covers_exactly_the_progress_deck(self):
        registered = {c.id for c in cards.by_family(cards.PROGRESS)}
        assert registered == set(progress_cards.CARDS_BY_ID)


class TestDevCardsAreRegistered:
    def test_the_five_dev_cards_are_registered_with_resolvers(self):
        dev = {c.id: c for c in cards.by_family(cards.DEV)}
        assert set(dev) == {"knight", "victory_point", "invention",
                            "two_roads", "monopoly"}
        for card in dev.values():
            assert callable(card.resolve)
        assert dev["victory_point"].victory_points == 1

    def test_no_id_collides_across_families(self):
        ids = [c.id for c in cards.REGISTRY.values()]
        assert len(ids) == len(set(ids))


class TestTheExtensionSeam:
    """A new card is one register() call with its own resolver — no core edit."""

    def test_registering_a_new_card_makes_it_resolvable(self):
        marker = {}

        def resolve(game, player_name, target):
            marker["played_by"] = player_name
            return {"success": True, "custom": target}

        card = cards.Card(
            id="_test_homebrew", name="Homebrew", family="homebrew", deck="none",
            timing="turn", needs_target="hex", victory_points=0, resolve=resolve,
        )
        cards.register(card)
        try:
            got = cards.get("_test_homebrew")
            assert got is card
            result = got.resolve(object(), "Alice", "1,0,-1")
            assert result == {"success": True, "custom": "1,0,-1"}
            assert marker["played_by"] == "Alice"
        finally:
            cards.REGISTRY.pop("_test_homebrew", None)

    def test_a_duplicate_id_is_refused(self):
        with pytest.raises(ValueError, match="duplicate card id"):
            cards.register(cards.get("knight"))
