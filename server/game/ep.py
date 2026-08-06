"""Explorers & Pirates state: pirate ships, missions, discovery, token supplies.

Keeping it in its own module means the base game stays readable, exactly as
`cities_knights.py` does for that expansion. A base-game reader never has to
page past rules that do not apply to them.

This is a state container, not a mode. The Game builds one whenever any rule
that needs somewhere to keep per-player pirate hexes, mission tracks, the pool
of undiscovered tiles or the token supplies is on — see `rules.EP_STATE_RULES`.
Whether a given mechanic actually happens is decided by that mechanic's own
rule, never by the presence of this object.

Wave 0 lands this as a skeleton: the structure and its accessors round-trip, so
the feature waves have a state object to hang fields on. The mechanics that read
and write it — discovery, the pirate, the three missions — arrive later.
"""

# The three mission tracks. Each is a container rule of its own
# (`mission_pirate_lairs` / `mission_fish` / `mission_spices`); this names the
# tracks the markers advance along.
MISSIONS = ("pirate_lairs", "fish", "spices")

# The permanent advantages a spice village grants. Earned in play rather than
# chosen in the lobby, so they are state here and not catalogue rules: Swift
# Voyage (+1 movement point), Pirate Bonus (chase on 4/5/6), Fast Gold (sell 1
# resource for 1 gold). Read by `ship_movement_points`, the chase roll and the
# gold trade respectively once those land.
VILLAGE_ADVANTAGES = ("swift_voyage", "pirate_bonus", "fast_gold")

# The tokens each mission is delivered with, and how many of each the box holds
# (expansions.md 1053, 1074): 6 fish hauls, 24 spice sacks, 6 pirate-lair
# tokens. Passed to the constructor rather than read here so the lobby could
# change them, exactly as the Cities & Knights sizes are.
TOKEN_TYPES = ("fish_haul", "spice_sack", "lair_token")
DEFAULT_SUPPLY = {"fish_haul": 6, "spice_sack": 24, "lair_token": 6}


class EP:
    """All Explorers & Pirates state for one game.

    The supply sizes are passed in rather than read from the constants above
    because the lobby can change them; the constants remain what the box holds.
    """

    def __init__(self, token_supply: dict = None):
        # player -> the sea hex their pirate ship sits on, or None
        self.pirate_hex = {}

        # player -> {mission: how far along that track their marker stands}
        self.markers = {}
        # mission -> the player whose marker leads the track and so holds its
        # 1-VP lead card, or None while nobody is ahead of everybody else.
        self.lead_cards = {mission: None for mission in MISSIONS}

        # Tiles placed icon-side-up and not yet discovered. Their identities are
        # secret — a hidden tile is redacted from `to_dict` the way a dev card
        # is — so only the count leaves this object until one is revealed.
        self.hidden_tiles = []
        # Revealed tile ids in the order they were discovered, for the board.
        self.reveal_order = []
        # The hex a player revealed most recently this turn, cleared each turn
        # so the client only flags a fresh discovery.
        self.last_discovery = None
        # region id -> the number tokens still on that unexplored area's stack,
        # in draw order. A discovery of a producing tile pops the next one (887);
        # the icon on a tile's back is which area it belongs to, so each region
        # holds its own stack. Secret like the tile identities, so it never
        # leaves this object in `to_dict`.
        self.number_stacks = {}

        # How many of each token the supply still holds...
        self.token_supply = dict(token_supply) if token_supply else dict(DEFAULT_SUPPLY)
        # ...and how many each player has landed but not yet delivered.
        self.tokens_held = {}

        # player -> the village advantages they have earned
        self.village_advantages = {}

    def register(self, player_name: str):
        self.pirate_hex.setdefault(player_name, None)
        self.markers.setdefault(player_name, {mission: 0 for mission in MISSIONS})
        self.tokens_held.setdefault(player_name, {token: 0 for token in TOKEN_TYPES})
        self.village_advantages.setdefault(player_name, [])

    def start_turn(self):
        """Clear the per-turn state so a fresh discovery reads as fresh."""
        self.last_discovery = None

    # --- Pirate ship -------------------------------------------------------

    def pirate_of(self, player_name: str):
        """The sea hex this player's pirate ship sits on, or None."""
        return self.pirate_hex.get(player_name)

    def place_pirate(self, player_name: str, hex_key):
        self.pirate_hex[player_name] = hex_key

    def pirate_at(self, hex_key: str):
        """Every player whose pirate ship sits on this hex."""
        return [name for name, where in self.pirate_hex.items() if where == hex_key]

    # --- Missions ----------------------------------------------------------

    def marker(self, player_name: str, mission: str) -> int:
        return self.markers.get(player_name, {}).get(mission, 0)

    def advance_marker(self, player_name: str, mission: str, steps: int = 1) -> int:
        """Move a player's marker along a track and return its new position."""
        track = self.markers.setdefault(player_name, {m: 0 for m in MISSIONS})
        track[mission] = track.get(mission, 0) + steps
        return track[mission]

    def leader(self, mission: str) -> str:
        """The player alone at the front of a track, or None if none is.

        A marker level every other player has failed to reach holds the lead
        card; a tie at the front leaves the card with nobody.
        """
        positions = {name: self.marker(name, mission) for name in self.markers}
        if not positions:
            return None
        best = max(positions.values())
        if best == 0:
            return None
        leaders = [name for name, at in positions.items() if at == best]
        return leaders[0] if len(leaders) == 1 else None

    def recompute_lead_cards(self):
        """Recompute who holds each mission's lead card from the markers."""
        for mission in MISSIONS:
            self.lead_cards[mission] = self.leader(mission)

    def lead_card_count(self, player_name: str) -> int:
        return sum(1 for holder in self.lead_cards.values() if holder == player_name)

    # --- Discovery ---------------------------------------------------------

    def seed_hidden_tiles(self, tile_ids):
        """Fill the undiscovered pool. The order is drawn from, not shown."""
        self.hidden_tiles = list(tile_ids)

    def reveal(self, tile_id: str, player_name: str = None):
        """Discover one tile: take it from the pool and record its order."""
        if tile_id in self.hidden_tiles:
            self.hidden_tiles.remove(tile_id)
        self.reveal_order.append(tile_id)
        self.last_discovery = tile_id

    def hidden_count(self) -> int:
        return len(self.hidden_tiles)

    def seed_number_stacks(self, stacks: dict):
        """Fill the per-area number-token stacks, in the order they are drawn."""
        self.number_stacks = {region: list(numbers) for region, numbers in stacks.items()}

    def draw_number(self, region_id: str):
        """Take the next token off an area's stack, or None if it is empty.

        A tile that produces nothing (a desert, a sea, a fish-shoal) never asks,
        so an empty or absent stack simply means "no token" rather than an error.
        """
        stack = self.number_stacks.get(region_id)
        if not stack:
            return None
        return stack.pop()

    # --- Token supplies ----------------------------------------------------

    def supply_of(self, token: str) -> int:
        return self.token_supply.get(token, 0)

    def take_token(self, player_name: str, token: str) -> bool:
        """Land one token from the supply into a player's hold, if any remain."""
        if self.token_supply.get(token, 0) <= 0:
            return False
        self.token_supply[token] -= 1
        held = self.tokens_held.setdefault(player_name, {t: 0 for t in TOKEN_TYPES})
        held[token] = held.get(token, 0) + 1
        return True

    def held_by(self, player_name: str, token: str) -> int:
        return self.tokens_held.get(player_name, {}).get(token, 0)

    # --- Village advantages ------------------------------------------------

    def advantages_of(self, player_name: str) -> list:
        return self.village_advantages.setdefault(player_name, [])

    def grant_advantage(self, player_name: str, advantage: str):
        earned = self.advantages_of(player_name)
        if advantage not in earned:
            earned.append(advantage)

    def has_advantage(self, player_name: str, advantage: str) -> bool:
        return advantage in self.village_advantages.get(player_name, [])

    def to_dict(self, viewer: str = None) -> dict:
        """Serialize for the client.

        Pirate hexes, mission markers, lead cards and the token supplies are all
        public. The undiscovered pool is not: its tiles' identities are secret
        like a dev card, so only how many remain leaves this object — the
        revealed tiles go out named, in discovery order.
        """
        return {
            "pirate_hex": self.pirate_hex,
            "markers": self.markers,
            "lead_cards": self.lead_cards,
            "hidden_count": self.hidden_count(),
            "reveal_order": list(self.reveal_order),
            "last_discovery": self.last_discovery,
            "token_supply": self.token_supply,
            "tokens_held": self.tokens_held,
            "village_advantages": self.village_advantages,
            "missions": list(MISSIONS),
        }
