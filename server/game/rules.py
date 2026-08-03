"""House rules the table can switch on before a game starts.

Each entry is one rule from `expansions.md`, reduced to a single setting. The
registry is the source of truth for both the lobby UI and the engine: the
lobby renders whatever is listed here, so adding a rule means adding one entry
plus the code that reads it — no UI change needed.

There is deliberately no "Cities & Knights mode". A mode is a bundle that
switches on eight unrelated mechanics behind one word, and a table that wants
knights and barbarians without commodities has no way to ask for it. The
expansion is listed here as the individual rules it is made of; `PRESETS`
below ticks a set of them in one click, and nothing in the engine ever asks
"is Cities & Knights on".

Keep `source` accurate. When someone asks "is that really the official rule?",
the answer has to point at a rulebook.
"""

BOOL = "bool"
INT = "int"
# One of a fixed set of ids, listed in the rule's "options" so the lobby can
# render the choice without knowing what any of them mean.
CHOICE = "choice"

# Groups let the lobby section the picker. "core" knobs change base-game
# numbers that are normally fixed; "expansion" is one mechanic out of a
# published expansion; "variant" is a single published house rule.
CORE = "core"
EXPANSION = "expansion"
VARIANT = "variant"


def _bool(rule_id, name, default, source, summary, **extra):
    return {
        "id": rule_id,
        "group": extra.pop("group", VARIANT),
        "type": BOOL,
        "default": default,
        "name": name,
        "source": source,
        "summary": summary,
        **extra,
    }


def _int(rule_id, name, default, minimum, maximum, source, summary, **extra):
    return {
        "id": rule_id,
        "group": extra.pop("group", CORE),
        "type": INT,
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
        "name": name,
        "source": source,
        "summary": summary,
        **extra,
    }


RULES = [
    {
        "id": "board_layout",
        "group": CORE,
        "type": CHOICE,
        "default": "random",
        "options": [
            {
                "id": "random",
                "name": "Random",
                "summary": (
                    "The variable board: 19 terrain hexes, tokens and harbours "
                    "shuffled into place. A different island every game."
                ),
            },
            {
                "id": "beginner",
                "name": "Beginner",
                "summary": (
                    "The printed starting map for beginners — the same terrain "
                    "and the same numbers every game, so a table can compare "
                    "two games on one board."
                ),
            },
            {
                "id": "large",
                "name": "Large (5–6 players)",
                "summary": (
                    "The extension's island: 30 terrain hexes, 28 number "
                    "tokens and 11 harbours. Room for five or six."
                ),
            },
        ],
        "name": "Map",
        "source": (
            "Base game rulebook, Illustration A (beginner); "
            "Catan 5–6 Player Extension rulebook (large)"
        ),
        "summary": (
            "Which island to play on. The random board is the standard game; "
            "the beginner map is the one printed in the rulebook; the large "
            "map is the 5–6 player extension board."
        ),
    },
    {
        "id": "turn_order",
        "group": CORE,
        "type": CHOICE,
        "default": "random",
        "options": [
            {
                "id": "random",
                "name": "Rolled for",
                "summary": (
                    "The seats are shuffled when the game starts, which is what "
                    "rolling the dice for the starting player amounts to."
                ),
            },
            {
                "id": "lobby",
                "name": "Order joined",
                "summary": (
                    "Play runs in the order people took their seats. Useful "
                    "when a table wants to replay the same start."
                ),
            },
        ],
        "name": "Turn order",
        "source": (
            "Base game rulebook (roll for the starting player); "
            "expansions.md 1102 (5–6 Player Extension)"
        ),
        "summary": "How the seating order is decided when the game starts.",
    },
]


# --- Core numbers -------------------------------------------------------
# Piece supplies, deck sizes and the other numbers printed on the box that the
# rules never vary, exposed so a table can build a bigger or stranger game.
# Every one of them is read at Game construction, so changing one only affects
# the next game.
RULES += [
    _int("victory_target", "Victory points to win", 10, 5, 20,
         "Base game rulebook (10); expansions.md 299 (Cities & Knights, 13)",
         "How many victory points end the game. This number is exactly what "
         "the table sets: no rule below ever changes it behind your back, "
         "though several suggest a different one."),
    _int("max_hand_before_discard", "Hand limit on a 7", 7, 5, 20,
         "Base game rulebook (7); expansions.md 244, 327",
         "Hold more than this when a 7 is rolled and you discard half, "
         "rounded down. Commodities count toward it."),
    _int("bank_trade_rate", "Bank trade rate", 4, 2, 6,
         "Base game rulebook (4:1); expansions.md 856, 1479 (3:1 variants)",
         "How many identical cards the bank charges for one of your choice, "
         "before harbours. Harbours still improve on it."),
    _int("generic_harbour_rate", "Any-resource harbour rate", 3, 2, 6,
         "Base game rulebook (the 3:1 harbours)",
         "What a settlement on a 3:1 harbour pays for one card of your "
         "choice. A harbour never makes a trade worse, so the bank rate wins "
         "if it is already better."),
    _int("special_harbour_rate", "Matching harbour rate", 2, 1, 6,
         "Base game rulebook (the five 2:1 harbours)",
         "What a settlement on a 2:1 harbour pays, for that harbour's own "
         "resource only."),
    _int("city_production", "Cards a city collects", 2, 1, 4,
         "Base game rulebook (a city collects 2 of a hex's resource)",
         "How much a city takes from each of its hexes when their number is "
         "rolled. A settlement always takes one. With commodities on, a city "
         "on pasture, mountain or forest takes one of each instead."),
    _int("min_players", "Players needed to start", 2, 1, 6,
         "Base game rulebook (3); expansions.md 804 (Catan for Two)",
         "How many players must be in the lobby before a game can start. "
         "Set it to 1 to try the board on your own."),
    _int("max_settlements", "Settlements per player", 5, 1, 20,
         "Base game rulebook (5 pieces in the box)",
         "How many settlements each player may have standing at once."),
    _int("max_cities", "Cities per player", 4, 1, 20,
         "Base game rulebook (4 pieces in the box)",
         "How many cities each player may have standing at once."),
    _int("max_roads", "Roads per player", 15, 1, 60,
         "Base game rulebook (15 pieces in the box)",
         "How many roads each player may have on the board at once."),
    _int("bank_resource_limit", "Bank cards per resource", 19, 5, 99,
         "Base game rulebook (19 of each resource)",
         "How many cards of each resource the bank starts with. When it runs "
         "out, nobody collects that resource."),
    _int("longest_road_minimum", "Longest Road minimum", 5, 2, 15,
         "Base game rulebook (5 segments); expansions.md 304",
         "The shortest road that can claim the Longest Road card."),
    _int("largest_army_minimum", "Largest Army minimum", 3, 1, 10,
         "Base game rulebook (3 knights)",
         "How many knight cards must be played before Largest Army can be "
         "claimed."),
    _int("dev_knights", "Knight cards in the deck", 14, 0, 40,
         "Base game rulebook (14 of 25)",
         "How many Knight development cards the deck holds."),
    _int("dev_victory_points", "Victory Point cards in the deck", 5, 0, 20,
         "Base game rulebook (5 of 25)",
         "How many Victory Point development cards the deck holds."),
    _int("dev_road_building", "Road Building cards in the deck", 2, 0, 20,
         "Base game rulebook (2 of 25)",
         "How many Road Building development cards the deck holds."),
    _int("dev_invention", "Year of Plenty cards in the deck", 2, 0, 20,
         "Base game rulebook (2 of 25)",
         "How many Year of Plenty (Invention) development cards the deck holds."),
    _int("dev_monopoly", "Monopoly cards in the deck", 2, 0, 20,
         "Base game rulebook (2 of 25)",
         "How many Monopoly development cards the deck holds."),
]


# --- Base-game variants -------------------------------------------------
RULES += [
    _bool("longest_road_card", "Longest Road card", True,
          "Base game rulebook; expansions.md 304 (kept in Cities & Knights)",
          "The 2-point card for the longest unbroken road. Turn it off for a "
          "game decided on buildings alone."),
    _bool("largest_army_card", "Largest Army card", True,
          "Base game rulebook; expansions.md 303 (dropped in Cities & Knights)",
          "The 2-point card for the most knight cards played. Cities & "
          "Knights drops it, because its knights replace the soldier cards."),
    _bool("dev_card_hold_a_turn", "Hold a development card a turn", True,
          "Base game rulebook; expansions.md 180, 434",
          "A development card cannot be played on the turn it was bought. "
          "Turn it off and a card bought this turn may be played at once."),
    _bool("robber_may_return_to_desert", "Robber may sit on the desert", True,
          "Base game rulebook (the robber starts there); expansions.md 188",
          "Whether the desert is a legal hex for the robber. Off, the robber "
          "must always sit on producing land, where it costs somebody "
          "something."),
    _bool("victory_point_cards_count_in_hand", "Victory Point cards count in hand", False,
          "Base game rulebook (a Victory Point card counts the moment you "
          "hold it and is revealed on the winning turn)",
          "A Victory Point card in your hand counts toward your total and can "
          "end the game, without being played and without being shown to "
          "anybody first. Off — how this server has always scored — a card "
          "does nothing until its owner plays it face up."),
    _bool("dice_deck", "Even production (dice deck)", False,
          "Traders & Barbarians, Catan Event Cards; expansions.md 767, 772 "
          "(\"a perfect distribution of production numbers ... play through "
          "all 36 event cards ... and simply reshuffle\")",
          "Production numbers come off a shuffled deck of all 36 dice "
          "combinations instead of two dice, and the deck is reshuffled once "
          "it runs out. Over a full deck every number comes up exactly as "
          "often as the odds say. This is the production half of the Event "
          "Cards variant only — the events printed on the cards are not part "
          "of it.",
          group=VARIANT),
    _bool("no_adjacent_red_numbers", "Keep 6s and 8s apart", False,
          "Base game rulebook, variable setup; expansions.md 1509–1510",
          "The rulebook's fix-up for a randomly dealt board: no two red "
          "numbers — the 6s and 8s — may end up on neighbouring hexes, and "
          "tokens are swapped until none do."),
    _bool("friendly_robber", "Friendly Robber", False,
          "Traders & Barbarians variant; expansions.md 756–763",
          "The robber may not be placed on a hex touching a settlement of a "
          "player who has only 2 victory points."),
    _bool("harbormaster", "Harbormaster", False,
          "Traders & Barbarians variant; expansions.md 793–803",
          "Settlements on a harbour are worth 1 harbour point and cities 2. "
          "The first player to 3 points takes a card worth 2 victory points, "
          "and it moves to anyone who later has more. The published variant "
          "suggests raising the target by 1 to keep the game the same length.",
          suggests_victory_target=11),
    _int("robber_free_opening_rounds", "Robber-free opening rounds", 0, 0, 10,
         "Cities & Knights rulebook (no robber until the first barbarian "
         "attack); expansions.md 317",
         "For this many rounds from the start, a 7 does not move the robber. "
         "The discard is unaffected — an early 7 still costs a big hand half "
         "its cards.",
         group=VARIANT),
]


# --- Cities & Knights, one mechanic at a time ---------------------------
# The expansion decomposed. Each of these is independently switchable, and
# `DEPENDENCIES` below records the few that genuinely cannot stand alone.
RULES += [
    _bool("commodities", "Commodities", False,
          "Cities & Knights rulebook, 'Commodities'; expansions.md 319–333",
          "Cities produce a commodity as well as a resource: pasture gives "
          "wool and cloth, mountains ore and coin, forest lumber and paper. "
          "Fields and hills are unchanged. Commodities count toward the hand "
          "limit on a 7.",
          group=EXPANSION),
    _bool("city_improvements", "City improvements", False,
          "Cities & Knights rulebook, 'City Improvements'; expansions.md 334–354",
          "Three tracks of five levels — trade bought with cloth, politics "
          "with coin, science with paper. Level 3 unlocks the Merchant Guild, "
          "the Fortress or the Aqueduct. You need a city to buy any of it.",
          group=EXPANSION),
    _bool("metropolis", "Metropolis", False,
          "Cities & Knights rulebook, 'Metropolis'; expansions.md 364–375",
          "The first player to level 4 on a track turns one of their cities "
          "into a metropolis worth 4 points instead of 2. Level 5 takes it "
          "off a holder who has not reached 5 themselves. A metropolis can "
          "never be pillaged.",
          group=EXPANSION),
    _bool("knights", "Knights", False,
          "Cities & Knights rulebook, 'Knights'; expansions.md 376–405",
          "Build knights on your road network for 1 wool and 1 ore, wake them "
          "with grain, promote them with wool and ore. An active knight can "
          "move once a turn and shove a weaker knight off its intersection.",
          group=EXPANSION),
    _bool("barbarians", "Barbarian attacks", False,
          "Cities & Knights rulebook, 'Barbarian Attacks'; expansions.md 406–425",
          "A third die is rolled every turn; three of its six faces sail the "
          "barbarian ship one space closer. When it arrives, your active "
          "knights are measured against the number of cities on the board. "
          "Win and the strongest defender scores; lose and the weakest lose a "
          "city. Until the first attack a 7 does not move the robber.",
          group=EXPANSION),
    _bool("city_walls", "City walls", False,
          "Cities & Knights rulebook, 'City Walls'; expansions.md 470–477",
          "Two brick builds a wall under one of your cities and raises your "
          "safe hand limit on a 7 by two cards. Three per player, and a wall "
          "falls with the city it protects.",
          group=EXPANSION),
    _bool("progress_cards", "Progress cards", False,
          "Cities & Knights rulebook, 'Progress Cards'; expansions.md 426–462",
          "Three decks — science, trade and politics — drawn when the event "
          "die shows a matching city gate and your improvement level beats "
          "the red die. They replace development cards outright: with this on "
          "the development deck cannot be bought from.",
          group=EXPANSION),
    _bool("setup_second_city", "Start with a city", False,
          "Cities & Knights rulebook, 'Setup'; expansions.md 301–302",
          "The second starting building is a city rather than a settlement, "
          "and it pays out one resource — and one commodity where the terrain "
          "has one — from every hex it touches.",
          group=EXPANSION),
]


# --- Expansion numbers --------------------------------------------------
RULES += [
    _int("barbarian_track_length", "Barbarian track spaces", 7, 3, 15,
         "Cities & Knights rulebook; expansions.md 407",
         "How many spaces the barbarian ship crosses before it attacks. "
         "Shorter means a more dangerous game.",
         group=EXPANSION),
    _int("progress_hand_limit", "Progress cards in hand", 4, 1, 10,
         "Cities & Knights rulebook; expansions.md 431",
         "How many progress cards a player may hold. Cards worth a victory "
         "point are revealed on sight and never take a slot.",
         group=EXPANSION),
    _int("max_city_walls", "City walls per player", 3, 0, 10,
         "Cities & Knights rulebook; expansions.md 473–474",
         "How many city walls each player may have standing at once.",
         group=EXPANSION),
]


RULES_BY_ID = {rule["id"]: rule for rule in RULES}


# A rule that cannot do anything on its own, and what it needs. These are not
# switched on for you: a table that asked for a metropolis without the tracks
# that award one has made a mistake worth naming, and silently ticking the
# missing box would hand them a game they did not choose. `start_game` refuses
# the combination and says what is missing.
DEPENDENCIES = {
    # The tracks are bought with cloth, coin and paper, and nothing else
    # produces them.
    "city_improvements": ("commodities",),
    "metropolis": ("city_improvements",),
    # Knights are the only defence; without them every attack is a loss.
    "barbarians": ("knights",),
    # Dealt by the event die the barbarians bring, to whoever's improvement
    # level beats the red die. Neither half is optional: with no tracks every
    # player sits at level 0 and the deck is all but undealt.
    "progress_cards": ("barbarians", "city_improvements"),
}

# The rules that need the expansion's own state object — its tracks, knight
# tokens, wall counts, barbarian ship and progress decks. Commodities live on
# the players and starting with a city decides nothing beyond setup, so
# neither of them needs it.
EXPANSION_STATE_RULES = (
    "city_improvements",
    "metropolis",
    "knights",
    "barbarians",
    "city_walls",
    "progress_cards",
)

# The rule set the single `cities_and_knights` toggle used to stand for. Kept
# as the preset below and as the translation for saves and clients that still
# speak the old flag — the old engine forced 13 points and dropped Largest
# Army, so a translated game keeps playing under exactly those terms.
CITIES_AND_KNIGHTS_RULES = {
    "commodities": True,
    "city_improvements": True,
    "metropolis": True,
    "knights": True,
    "barbarians": True,
    "city_walls": True,
    "progress_cards": True,
    "setup_second_city": True,
    "largest_army_card": False,
    "victory_target": 13,
}

LEGACY_RULE_ID = "cities_and_knights"


PRESETS = [
    {
        "id": "base_game",
        "name": "Base game",
        "source": "Base game rulebook",
        "summary": "Catan as it comes out of the box. Every optional rule off.",
        "rules": {},
    },
    {
        "id": "cities_and_knights",
        "name": "Cities & Knights",
        "source": "Cities & Knights rulebook; expansions.md 295–488",
        "summary": (
            "Ticks the eight rules the expansion is made of, drops the "
            "Largest Army card as the rulebook does, and sets the target to "
            "13. Every one of them stays a separate switch you can untick."
        ),
        "rules": dict(CITIES_AND_KNIGHTS_RULES),
    },
    {
        "id": "knights_only",
        "name": "Knights & barbarians only",
        "source": "Cities & Knights rulebook, 'Knights' and 'Barbarian Attacks'",
        "summary": (
            "The military half of Cities & Knights: knights, the barbarian "
            "ship and city walls, with no commodities and no improvement "
            "tracks. Still a 10-point game."
        ),
        "rules": {
            "knights": True,
            "barbarians": True,
            "city_walls": True,
            "setup_second_city": True,
            "largest_army_card": False,
        },
    },
    {
        "id": "traders_and_barbarians",
        "name": "Traders & Barbarians variants",
        "source": "Traders & Barbarians rulebook; expansions.md 756–803",
        "summary": (
            "The two published variants this engine implements: the Friendly "
            "Robber and the Harbormaster, at the 11 points the Harbormaster "
            "suggests."
        ),
        "rules": {
            "friendly_robber": True,
            "harbormaster": True,
            "victory_target": 11,
        },
    },
]

PRESETS_BY_ID = {preset["id"]: preset for preset in PRESETS}


def dev_card_deck(chosen: dict) -> dict:
    """The development card deck implied by the chosen rules."""
    return {
        "knight": chosen["dev_knights"],
        "victory_point": chosen["dev_victory_points"],
        "two_roads": chosen["dev_road_building"],
        "invention": chosen["dev_invention"],
        "monopoly": chosen["dev_monopoly"],
    }


def defaults() -> dict:
    """The rule set a game uses when nobody has chosen anything."""
    return {rule["id"]: rule["default"] for rule in RULES}


def migrate(raw: dict) -> dict:
    """Translate a rule set written against the old `cities_and_knights` flag.

    Saves and clients from before the expansion was decomposed carry one
    boolean that stood for all of it. Dropping the key would strip a game in
    progress of its commodities, knights and barbarians mid-match, so the flag
    is expanded into the rules it used to imply — including the 13-point
    target the old engine forced, because that is the game those players are
    part-way through.
    """
    if not isinstance(raw, dict) or LEGACY_RULE_ID not in raw:
        return raw

    translated = {key: value for key, value in raw.items() if key != LEGACY_RULE_ID}
    if raw[LEGACY_RULE_ID]:
        translated.update(CITIES_AND_KNIGHTS_RULES)
    return translated


def coerce(raw: dict) -> dict:
    """Validate a client-supplied rule set, falling back to defaults.

    Unknown ids are dropped and out-of-range numbers are clamped rather than
    rejected: a lobby setting is not worth refusing a whole request over, and
    silently ignoring an unknown id keeps old clients working after a rule is
    removed.
    """
    chosen = defaults()
    if not isinstance(raw, dict):
        return chosen

    for rule_id, value in migrate(raw).items():
        rule = RULES_BY_ID.get(rule_id)
        if rule is None:
            continue

        if rule["type"] == BOOL:
            chosen[rule_id] = bool(value)
        elif rule["type"] == CHOICE:
            if value in {option["id"] for option in rule["options"]}:
                chosen[rule_id] = value
        elif rule["type"] == INT:
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            chosen[rule_id] = max(rule["minimum"], min(rule["maximum"], value))

    return chosen


def preset_rules(preset_id: str) -> dict | None:
    """A full rule set for one preset, or None if there is no such preset.

    A preset is a shortcut that ticks individual rules and nothing more —
    there is no state anywhere recording that it was used, and the engine
    never asks.
    """
    preset = PRESETS_BY_ID.get(preset_id)
    if preset is None:
        return None
    return coerce(preset["rules"])


def dependency_problems(chosen: dict) -> list:
    """Rules that were switched on without what they need, as sentences.

    Empty means the set is coherent. The caller refuses the start and shows
    these; nothing is switched on automatically, because a rule the table did
    not ask for is a different game from the one they agreed to.
    """
    problems = []
    for rule_id, required in DEPENDENCIES.items():
        if not chosen.get(rule_id):
            continue
        missing = [
            RULES_BY_ID[other]["name"] for other in required if not chosen.get(other)
        ]
        if missing:
            problems.append(
                f"{RULES_BY_ID[rule_id]['name']} needs {' and '.join(missing)}"
            )
    return problems


def needs_expansion_state(chosen: dict) -> bool:
    """Whether this rule set requires the Cities & Knights state object."""
    return any(chosen.get(rule_id) for rule_id in EXPANSION_STATE_RULES)


def catalogue() -> list:
    """The registry, for the lobby to render."""
    return [dict(rule) for rule in RULES]


def presets() -> list:
    """The one-click rule sets, for the lobby to offer as buttons."""
    return [dict(preset) for preset in PRESETS]
