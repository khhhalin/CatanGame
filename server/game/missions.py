"""Missions: mission tracks with per-player markers and 1-VP lead cards.

Split out of `game.py` alongside the other rules mixins. Every method here is
gated on `self.rules['missions']`, never on an expansion name, so a base-game,
Seafarers or Land Ho! table is untouched — no marker ever moves and no lead card
is ever awarded (expansions.md 969-978).

This is the *container* for the three concrete missions (pirate-lairs, fish,
spices), not the missions themselves. It owns the machinery all three share: a
track per mission, a marker per player on each track, and the mission's 1-VP
lead card, which sits with whoever is alone at the front. The mission-specific
modules (`mission_pirate_lairs` / `mission_fish` / `mission_spices`) each declare
their track's length with `register_mission_track` and call `advance_mission`
whenever a delivery or capture moves their player forward; nothing about *what*
advances a marker lives here.

The lead card resolves exactly like Longest Road and Largest Army: a sole leader
holds it, a tie leaves it unheld, and it is recomputed the moment a marker moves
(`update_longest_road` / `update_largest_army` in `game.py`). The state lives on
`self.ep`, so it round-trips through the container's `to_dict` and reaches the
client on the normal board-payload path — mission progress is public, redacted
from nobody.
"""


class MissionRules:
    """Mission tracks, marker advancement, and the lead-card scoring hook."""

    def register_mission_track(self, track: str, length: int):
        """Declare a mission's track length, so its markers cap at the end.

        The three mission modules call this once, when their board is set up, to
        say how many steps their track holds. A track left unregistered stays at
        length 0 and `advance_mission` refuses to move a marker along it — the
        container is inert until a mission fills it in. A no-op without the rule
        or a container to hold it.
        """
        if not self.rules['missions'] or self.ep is None:
            return
        self.ep.register_track(track, length)

    def mission_tracks(self) -> dict:
        """The registry: each mission track mapped to its declared length."""
        if self.ep is None:
            return {}
        return dict(self.ep.track_lengths)

    def advance_mission(self, player_name: str, track: str, steps: int = 1) -> int:
        """Move a player's marker along a mission track and return its position.

        The primitive the three missions call when a player delivers a token or
        captures a lair. The marker never runs past the track's end, so a
        delivery that would overshoot simply seats it on the final step. A move
        that changes the field recomputes the lead cards, so overtaking the
        leader flips the 1-VP card in the same call. Returns the marker's new
        position; a no-op returning 0 without the rule, a container, or a
        declared track.
        """
        if not self.rules['missions'] or self.ep is None:
            return 0

        length = self.ep.track_length(track)
        if length <= 0:
            return self.ep.marker(player_name, track)

        capped = min(self.ep.marker(player_name, track) + steps, length)
        self.ep.markers.setdefault(player_name, {})[track] = capped
        self.update_mission_lead_cards()
        return capped

    def update_mission_lead_cards(self):
        """Recompute every mission's lead card from the markers.

        A marker strictly ahead of every other on a track holds that mission's
        card; a tie at the front leaves it with nobody, mirroring how a tied
        Longest Road stays unclaimed. A no-op without the rule or a container.
        """
        if not self.rules['missions'] or self.ep is None:
            return
        self.ep.recompute_lead_cards()

    def mission_lead_holder(self, track: str) -> str:
        """The player holding a mission's 1-VP lead card, or None if it is unheld."""
        if not self.rules['missions'] or self.ep is None:
            return None
        return self.ep.lead_cards.get(track)

    def mission_victory_points(self, player_name: str) -> int:
        """How many mission lead cards a player holds, one point each."""
        if not self.rules['missions'] or self.ep is None:
            return 0
        return self.ep.lead_card_count(player_name)
