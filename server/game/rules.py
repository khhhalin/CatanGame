"""Optional rules the table can switch on before a game starts.

Each entry is one rule from `expansions.md`, reduced to a single setting. The
registry is the source of truth for both the lobby UI and the engine: the
lobby renders whatever is listed here, so adding a rule means adding one entry
plus the code that reads it — no UI change needed.

Keep `source` accurate. When someone asks "is that really the official rule?",
the answer has to point at a rulebook.
"""

BOOL = "bool"
INT = "int"
# One of a fixed set of ids, listed in the rule's "options" so the lobby can
# render the choice without knowing what any of them mean.
CHOICE = "choice"

# Groups let the lobby section the picker. "core" knobs change base-game
# numbers that are normally fixed; "expansion" turns on a whole rule set;
# "variant" is a single published house rule.
CORE = "core"
EXPANSION = "expansion"
VARIANT = "variant"


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
        "id": "cities_and_knights",
        "group": EXPANSION,
        "type": BOOL,
        "default": False,
        "name": "Cities & Knights",
        "source": "Cities & Knights (full expansion)",
        "summary": (
            "Cities produce commodities as well as resources, which buy city "
            "improvements on three tracks. Knights defend Catan from the "
            "barbarians. Wins at 13 points instead of 10."
        ),
    },
    {
        "id": "friendly_robber",
        "group": VARIANT,
        "type": BOOL,
        "default": False,
        "name": "Friendly Robber",
        "source": "Traders & Barbarians (variant)",
        "summary": (
            "The robber may not be placed on a hex touching a settlement of a "
            "player who has only 2 victory points."
        ),
    },
    {
        "id": "harbormaster",
        "group": VARIANT,
        "type": BOOL,
        "default": False,
        "name": "Harbormaster",
        "source": "Traders & Barbarians (variant)",
        "summary": (
            "Settlements on a harbour are worth 1 harbour point and cities 2. "
            "The first player to 3 points takes a card worth 2 victory points, "
            "and it moves to anyone who later has more. The target to win goes "
            "up by 1."
        ),
    },
    {
        "id": "victory_target",
        "group": CORE,
        "type": INT,
        "default": 10,
        "minimum": 5,
        "maximum": 20,
        "name": "Victory points to win",
        "source": "Base game (10); expansions raise it",
        "summary": (
            "How many victory points end the game. Seafarers scenarios use "
            "12–14, Cities & Knights uses 13."
        ),
    },
    {
        "id": "max_hand_before_discard",
        "group": CORE,
        "type": INT,
        "default": 7,
        "minimum": 5,
        "maximum": 20,
        "name": "Hand limit on a 7",
        "source": "Base game (7); city walls raise it in Cities & Knights",
        "summary": (
            "Hold more than this when a 7 is rolled and you discard half, "
            "rounded down."
        ),
    },
]

def _core(rule_id, name, default, minimum, maximum, source, summary):
    """A base-game number that is normally fixed in the box."""
    return {
        "id": rule_id,
        "group": CORE,
        "type": INT,
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
        "name": name,
        "source": source,
        "summary": summary,
    }


# Piece supplies and deck sizes. These are the numbers printed on the box that
# the rules never vary, exposed so a table can build a bigger or stranger game.
# Every one of them is read at Game construction, so changing one only affects
# the next game.
RULES += [
    _core("min_players", "Players needed to start", 2, 1, 6,
          "Base game (3; 2 with the Catan for Two variant)",
          "How many players must be in the lobby before a game can start. "
          "Set it to 1 to try the board on your own."),
    _core("max_settlements", "Settlements per player", 5, 1, 20,
          "Base game (5 pieces in the box)",
          "How many settlements each player may have standing at once."),
    _core("max_cities", "Cities per player", 4, 1, 20,
          "Base game (4 pieces in the box)",
          "How many cities each player may have standing at once."),
    _core("max_roads", "Roads per player", 15, 1, 60,
          "Base game (15 pieces in the box)",
          "How many roads each player may have on the board at once."),
    _core("bank_resource_limit", "Bank cards per resource", 19, 5, 99,
          "Base game (19 of each resource)",
          "How many cards of each resource the bank starts with. When it runs "
          "out, nobody collects that resource."),
    _core("longest_road_minimum", "Longest Road minimum", 5, 2, 15,
          "Base game (5 segments)",
          "The shortest road that can claim the Longest Road card."),
    _core("largest_army_minimum", "Largest Army minimum", 3, 1, 10,
          "Base game (3 knights)",
          "How many knight cards must be played before Largest Army can be claimed."),
    _core("dev_knights", "Knight cards in the deck", 14, 0, 40,
          "Base game (14 of 25)",
          "How many Knight development cards the deck holds."),
    _core("dev_victory_points", "Victory Point cards in the deck", 5, 0, 20,
          "Base game (5 of 25)",
          "How many Victory Point development cards the deck holds."),
    _core("dev_road_building", "Road Building cards in the deck", 2, 0, 20,
          "Base game (2 of 25)",
          "How many Road Building development cards the deck holds."),
    _core("dev_invention", "Year of Plenty cards in the deck", 2, 0, 20,
          "Base game (2 of 25)",
          "How many Year of Plenty (Invention) development cards the deck holds."),
    _core("dev_monopoly", "Monopoly cards in the deck", 2, 0, 20,
          "Base game (2 of 25)",
          "How many Monopoly development cards the deck holds."),
]


RULES_BY_ID = {rule["id"]: rule for rule in RULES}


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

    for rule_id, value in raw.items():
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


def catalogue() -> list:
    """The registry, for the lobby to render."""
    return [dict(rule) for rule in RULES]
