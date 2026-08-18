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


# Categories are the *functional* home of a rule, kept beside `group` rather than
# replacing it: `group` says where a rule was published (core/expansion/variant),
# `category` says what part of the game it touches, so the lobby can offer the
# ~140 rules as a collapsible tree a player can read instead of one flat list.
# This is the single, ordered source of truth — the client renders whatever is
# listed here, in this order, so adding a category is a one-place change. Each
# rule carries exactly one `category`, its single best-fit primary home; the
# guard in tests/test_rules.py fails any rule whose category is not one of these.
CATEGORIES = [
    {"id": "board", "label": "Board & Setup",
     "hint": "The map, terrain, regions and how the game is set up."},
    {"id": "base", "label": "Base numbers",
     "hint": "Piece supplies, bank size, dev-deck composition, player counts — "
             "the numbers on the box."},
    {"id": "victory", "label": "Victory & Awards",
     "hint": "The victory target, the road and army cards, and everything that "
             "scores or ends the game."},
    {"id": "trade", "label": "Trade & Money",
     "hint": "Bank and harbour rates, gold, coins, favour tokens and the guild."},
    {"id": "sea", "label": "Sea & Ships",
     "hint": "Ships, their movement, the pirate, warships, gold fields and fog."},
    {"id": "military", "label": "Knights & Barbarians",
     "hint": "Knights, city walls and the barbarian scenarios they defend against."},
    {"id": "cards", "label": "Commodities & Cards",
     "hint": "Commodities, city improvements, the card decks, and the helper "
             "tiles."},
    {"id": "scenario", "label": "Scenario mechanics",
     "hint": "Wagons, caravans, fishing, rivers, missions and the other "
             "one-scenario mechanics."},
]

CATEGORY_IDS = {category["id"] for category in CATEGORIES}


def _bool(rule_id, category, name, default, source, summary, **extra):
    return {
        "id": rule_id,
        "group": extra.pop("group", VARIANT),
        "category": category,
        "type": BOOL,
        "default": default,
        "name": name,
        "source": source,
        "summary": summary,
        **extra,
    }


def _int(rule_id, category, name, default, minimum, maximum, source, summary, **extra):
    return {
        "id": rule_id,
        "group": extra.pop("group", CORE),
        "category": category,
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
        "category": "board",
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
            {
                "id": "custom",
                "name": "Custom map",
                "summary": (
                    "A map from the map editor — its own frame, its own "
                    "regions and its own pool of tiles per region. Which one "
                    "is the setting below."
                ),
            },
        ],
        "name": "Map",
        "source": (
            "Base game rulebook, Illustration A (beginner); "
            "Catan 5–6 Player Extension rulebook (large); "
            "Seafarers rulebook, Scenario: New World, on designing your own "
            "(\"may freely design and play scenarios of their own\")"
        ),
        "summary": (
            "Which island to play on. The random board is the standard game; "
            "the beginner map is the one printed in the rulebook; the large "
            "map is the 5–6 player extension board; a custom map is one "
            "somebody at this table drew."
        ),
    },
    {
        "id": "board_map",
        "group": CORE,
        "category": "board",
        "type": CHOICE,
        "default": "standard",
        # Filled in by `catalogue()` from whatever is on disk right now, so a
        # map saved a second ago is in every client's picker on the next
        # `rules_changed` with no front-end change at all.
        "options": [],
        "dynamic": True,
        "name": "Custom map",
        "source": (
            "Seafarers rulebook, Scenario: New World (\"the board is created "
            "by shuffling all listed hexes face down and placing them face up "
            "at random within the assembled frame\")"
        ),
        "summary": (
            "Which custom map to play, when the map above is set to Custom. "
            "Ignored otherwise."
        ),
    },
    {
        "id": "turn_order",
        "group": CORE,
        "category": "board",
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
    {
        "id": "dice_set",
        "group": CORE,
        "category": "board",
        "type": CHOICE,
        "default": "standard",
        "options": [
            {
                "id": "standard",
                "name": "Two dice",
                "summary": (
                    "The pair out of the box: every number from 2 to 12, as "
                    "often as two six-sided dice throw it."
                ),
            },
            {
                "id": "no_two_or_twelve",
                "name": "No 2s or 12s",
                "summary": (
                    "A 2 or a 12 is re-rolled, so production only ever lands "
                    "on 3 through 11. The two numbers nothing much sits on "
                    "stop costing the table a turn."
                ),
            },
        ],
        "name": "Dice",
        "source": (
            "Base game rulebook (two dice); expansions.md 739, Traders & "
            "Barbarians main scenario (\"When you roll a '2' or a '12' as your "
            "production roll you re-roll the dice\")"
        ),
        "summary": (
            "Which dice the table rolls for production. The set decides which "
            "numbers can come up at all, and how often each one does."
        ),
    },
    {
        "id": "starting_city_yield",
        "group": CORE,
        "category": "board",
        "type": CHOICE,
        "default": "resource_and_commodity",
        "options": [
            {
                "id": "resource_and_commodity",
                "name": "A resource and a commodity",
                "summary": (
                    "The Cities & Knights reading: the starting city collects "
                    "one resource from every terrain hex it touches, and one "
                    "commodity as well where that terrain has one."
                ),
            },
            {
                "id": "resource_only",
                "name": "One resource a hex",
                "summary": (
                    "The Traders & Barbarians reading: the starting city "
                    "collects one resource per adjacent terrain hex and "
                    "nothing else, however the rest of the game pays."
                ),
            },
        ],
        "name": "Starting city yield",
        # Two published readings of the same placement, which is why this is a
        # choice and not a switch: the table says which rulebook it is playing.
        "source": (
            "expansions.md 302, Cities & Knights (\"Each player collects one "
            "resource (and, where applicable, one commodity) from every "
            "terrain hex adjacent to the city placed during the second setup "
            "round\"); expansions.md 620 and 695, Traders & Barbarians "
            "scenarios (\"he still receives only 1 resource for each terrain "
            "hex adjacent to that starting city\")"
        ),
        "summary": (
            "What the city placed in the second setup round pays out. Both "
            "readings are official: Cities & Knights adds the commodity where "
            "the terrain has one, the Traders & Barbarians scenarios pay one "
            "resource a hex and nothing more. Either way it is one resource "
            "per hex, and the desert and the sea pay nothing."
        ),
    },
]


# --- Core numbers -------------------------------------------------------
# Piece supplies, deck sizes and the other numbers printed on the box that the
# rules never vary, exposed so a table can build a bigger or stranger game.
# Every one of them is read at Game construction, so changing one only affects
# the next game.
RULES += [
    _int("victory_target", "victory", "Victory points to win", 10, 5, 20,
         "Base game rulebook (10); expansions.md 299 (Cities & Knights, 13)",
         "How many victory points end the game. This number is exactly what "
         "the table sets: no rule below ever changes it behind your back, "
         "though several suggest a different one."),
    _int("max_hand_before_discard", "base", "Hand limit on a 7", 7, 5, 20,
         "Base game rulebook (7); expansions.md 244, 327",
         "Hold more than this when a 7 is rolled and you discard half, "
         "rounded down. Commodities count toward it."),
    _int("bank_trade_rate", "trade", "Bank trade rate", 4, 2, 6,
         "Base game rulebook (4:1); expansions.md 856, 1479 (3:1 variants)",
         "How many identical cards the bank charges for one of your choice, "
         "before harbours. Harbours still improve on it."),
    _int("generic_harbour_rate", "trade", "Any-resource harbour rate", 3, 2, 6,
         "Base game rulebook (the 3:1 harbours)",
         "What a settlement on a 3:1 harbour pays for one card of your "
         "choice. A harbour never makes a trade worse, so the bank rate wins "
         "if it is already better."),
    _int("special_harbour_rate", "trade", "Matching harbour rate", 2, 1, 6,
         "Base game rulebook (the five 2:1 harbours)",
         "What a settlement on a 2:1 harbour pays, for that harbour's own "
         "resource only."),
    _int("city_production", "base", "Cards a city collects", 2, 1, 4,
         "Base game rulebook (a city collects 2 of a hex's resource)",
         "How much a city takes from each of its hexes when their number is "
         "rolled. A settlement always takes one. With commodities on, a city "
         "on pasture, mountain or forest takes one of each instead."),
    _int("min_players", "base", "Players needed to start", 2, 1, 6,
         "Base game rulebook (3); expansions.md 804 (Catan for Two)",
         "How many players must be in the lobby before a game can start. "
         "Set it to 1 to try the board on your own."),
    # 0 is not "no limit": it means "whatever this server is configured with",
    # exactly as the clocks below do. A table that never opened the setting
    # keeps the deployment's own cap.
    _int("max_players", "base", "Seats at the table", 0, 0, 6,
         "Base game rulebook (4 players); Catan 5-6 Player Extension rulebook "
         "(6, on the larger board)",
         "How many people may take a seat. The 5-6 player game needs a board "
         "with room for them - the large map or a custom one. 0 keeps this "
         "server's own default."),
    _int("max_settlements", "base", "Settlements per player", 5, 1, 20,
         "Base game rulebook (5 pieces in the box)",
         "How many settlements each player may have standing at once."),
    _int("max_cities", "base", "Cities per player", 4, 1, 20,
         "Base game rulebook (4 pieces in the box)",
         "How many cities each player may have standing at once."),
    _int("max_roads", "base", "Roads per player", 15, 1, 60,
         "Base game rulebook (15 pieces in the box)",
         "How many roads each player may have on the board at once."),
    _int("bank_resource_limit", "base", "Bank cards per resource", 19, 5, 99,
         "Base game rulebook (19 of each resource)",
         "How many cards of each resource the bank starts with. When it runs "
         "out, nobody collects that resource."),
    _int("longest_road_minimum", "victory", "Longest Road minimum", 5, 2, 15,
         "Base game rulebook (5 segments); expansions.md 304",
         "The shortest road that can claim the Longest Road card."),
    _int("largest_army_minimum", "victory", "Largest Army minimum", 3, 1, 10,
         "Base game rulebook (3 knights)",
         "How many knight cards must be played before Largest Army can be "
         "claimed."),
    _int("dev_knights", "base", "Knight cards in the deck", 14, 0, 40,
         "Base game rulebook (14 of 25)",
         "How many Knight development cards the deck holds."),
    _int("dev_victory_points", "base", "Victory Point cards in the deck", 5, 0, 20,
         "Base game rulebook (5 of 25)",
         "How many Victory Point development cards the deck holds."),
    _int("dev_road_building", "base", "Road Building cards in the deck", 2, 0, 20,
         "Base game rulebook (2 of 25)",
         "How many Road Building development cards the deck holds."),
    _int("dev_invention", "base", "Year of Plenty cards in the deck", 2, 0, 20,
         "Base game rulebook (2 of 25)",
         "How many Year of Plenty (Invention) development cards the deck holds."),
    _int("dev_monopoly", "base", "Monopoly cards in the deck", 2, 0, 20,
         "Base game rulebook (2 of 25)",
         "How many Monopoly development cards the deck holds."),
]


# --- The clocks ---------------------------------------------------------
# One clock per phase of a turn, all of them the table's to set. Zero is not
# "no limit" — it means "whatever this server is configured with", which is
# what a table that never opened these settings gets. Nothing here is a
# rulebook number: the physical game has no clock at all, and these exist
# because an online table cannot wait for a player who closed their laptop.
RULES += [
    _int("dice_timer_seconds", "base", "Dice roll clock", 0, 0, 600,
         "No published rule: an online table's replacement for a player who "
         "has walked away from the table",
         "How long a player has to roll before the server rolls for them. "
         "0 keeps this server's own default."),
    _int("discard_timer_seconds", "base", "Discard clock", 0, 0, 600,
         "No published rule; the discard itself is base game rulebook (a 7 "
         "costs every hand over the limit half its cards)",
         "How long a player has to hand back half their hand after a 7 "
         "before the server discards at random for them. 0 keeps this "
         "server's own default."),
    _int("robber_timer_seconds", "base", "Robber clock", 0, 0, 600,
         "No published rule; the move itself is base game rulebook (the "
         "robber is moved to another hex and one card is stolen)",
         "How long the roller of a 7 has to move the robber and pick a "
         "victim before the server does it for them. 0 keeps this server's "
         "own default."),
    _int("turn_timer_seconds", "base", "Turn clock", 0, 0, 3600,
         "No published rule: an online table's replacement for a player who "
         "has walked away from the table",
         "How long the rest of a turn lasts once the roll — and any discard "
         "and robber move it caused — is settled. 0 keeps this server's own "
         "default."),
    # The one clock in this block whose zero means "no clock at all": there is
    # no deployment setting behind it to fall back to, and a table that never
    # wanted a trade timer is playing the physical game, where an offer stands
    # until it is taken or withdrawn.
    _int("trade_offer_seconds", "trade", "Trade offer clock", 0, 0, 600,
         "No published rule: the physical game leaves an offer on the table "
         "until it is taken or withdrawn, and this is the online table's "
         "stand-in for picking the cards back up",
         "How long an offer stays open for the rest of the table to accept "
         "before the server drops it. 0 leaves an offer standing until its "
         "proposer cancels it or somebody trades."),
    _int("choice_timer_seconds", "base", "Decision clock", 0, 0, 600,
         "No published rule; the decisions themselves are the rules that ask "
         "for them (which city the barbarians sack, which card a Wedding "
         "takes)",
         "How long a player has to answer a decision the engine stopped to "
         "ask for before the server answers it for them. 0 keeps this "
         "server's own default."),
]


# --- Base-game variants -------------------------------------------------
RULES += [
    _bool("longest_road_card", "victory", "Longest Road card", True,
          "Base game rulebook; expansions.md 304 (kept in Cities & Knights)",
          "The 2-point card for the longest unbroken road. Turn it off for a "
          "game decided on buildings alone."),
    _bool("largest_army_card", "victory", "Largest Army card", True,
          "Base game rulebook; expansions.md 303 (dropped in Cities & Knights)",
          "The 2-point card for the most knight cards played. Cities & "
          "Knights drops it, because its knights replace the soldier cards."),
    _bool("dev_card_hold_a_turn", "cards", "Hold a development card a turn", True,
          "Base game rulebook; expansions.md 180, 434",
          "A development card cannot be played on the turn it was bought. "
          "Turn it off and a card bought this turn may be played at once."),
    _bool("robber_may_return_to_desert", "board", "Robber may sit on the desert", True,
          "Base game rulebook (the robber starts there); expansions.md 188",
          "Whether the desert is a legal hex for the robber. Off, the robber "
          "must always sit on producing land, where it costs somebody "
          "something."),
    _bool("victory_point_cards_count_in_hand", "victory",
          "Victory Point cards count in hand", False,
          "Base game rulebook (a Victory Point card counts the moment you "
          "hold it and is revealed on the winning turn)",
          "A Victory Point card in your hand counts toward your total and can "
          "end the game, without being played and without being shown to "
          "anybody first. Off — how this server has always scored — a card "
          "does nothing until its owner plays it face up."),
    _bool("dice_deck", "board", "Even production (dice deck)", False,
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
    _bool("epidemic", "scenario", "Epidemic", False,
          "Traders & Barbarians, Catan Event Cards; expansions.md 775 (\"The "
          "'Epidemic' event appears on production numbers '6' and '8' and "
          "causes each player to receive only 1 resource for each of his "
          "cities that produces that turn\")",
          "The Epidemic standing over the whole game instead of turning up on "
          "one card: on a 6 or an 8 every city collects a single card from "
          "each of its hexes rather than its usual two. Settlements are "
          "untouched, and so is the commodity a city takes with commodities "
          "on — it was only ever one card either way.",
          group=VARIANT),
    _bool("no_adjacent_red_numbers", "board", "Keep 6s and 8s apart", False,
          "Base game rulebook, variable setup; expansions.md 1509–1510",
          "The rulebook's fix-up for a randomly dealt board: no two red "
          "numbers — the 6s and 8s — may end up on neighbouring hexes, and "
          "tokens are swapped until none do."),
    _bool("friendly_robber", "board", "Friendly Robber", False,
          "Traders & Barbarians variant; expansions.md 756–763",
          "The robber may not be placed on a hex touching a settlement of a "
          "player who has only 2 victory points."),
    _bool("harbormaster", "victory", "Harbormaster", False,
          "Traders & Barbarians variant; expansions.md 793–803",
          "Settlements on a harbour are worth 1 harbour point and cities 2. "
          "The first player to 3 points takes a card worth 2 victory points, "
          "and it moves to anyone who later has more. The published variant "
          "suggests raising the target by 1 to keep the game the same length.",
          suggests_victory_target=11),
    _bool("chat_commands", "scenario", "Chat commands", False,
          "No published rule: the online table's version of reaching into the "
          "box mid-game, which a table sitting round a real board can do "
          "without asking anybody's permission",
          "Slash commands typed into chat may change the game: hand out cards, "
          "move cards between players, fix the next roll, skip a stuck turn, "
          "move the barbarian ship. Every one of them is written into the game "
          "log naming who ran it, so the table can see what was done. The "
          "commands that only report — /help, /whoami, /rules, /deck — work "
          "whether this is on or off.",
          group=VARIANT),
    _int("robber_free_opening_rounds", "board", "Robber-free opening rounds", 0, 0, 10,
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
    _bool("commodities", "cards", "Commodities", False,
          "Cities & Knights rulebook, 'Commodities'; expansions.md 319–333",
          "Cities produce a commodity as well as a resource: pasture gives "
          "wool and cloth, mountains ore and coin, forest lumber and paper. "
          "Fields and hills are unchanged. Commodities count toward the hand "
          "limit on a 7.",
          group=EXPANSION),
    _bool("city_improvements", "cards", "City improvements", False,
          "Cities & Knights rulebook, 'City Improvements'; expansions.md 334–354",
          "Three tracks of five levels — trade bought with cloth, politics "
          "with coin, science with paper. Level 3 unlocks the Merchant Guild, "
          "the Fortress or the Aqueduct. You need a city to buy any of it.",
          group=EXPANSION),
    _bool("metropolis", "cards", "Metropolis", False,
          "Cities & Knights rulebook, 'Metropolis'; expansions.md 364–375",
          "The first player to level 4 on a track turns one of their cities "
          "into a metropolis worth 4 points instead of 2. Level 5 takes it "
          "off a holder who has not reached 5 themselves. A metropolis can "
          "never be pillaged.",
          group=EXPANSION),
    _bool("knights", "military", "Knights", False,
          "Cities & Knights rulebook, 'Knights'; expansions.md 376–405",
          "Build knights on your road network for 1 wool and 1 ore, wake them "
          "with grain, promote them with wool and ore. An active knight can "
          "move once a turn and shove a weaker knight off its intersection.",
          group=EXPANSION),
    _bool("barbarians", "military", "Barbarian attacks", False,
          "Cities & Knights rulebook, 'Barbarian Attacks'; expansions.md 406–425",
          "A third die is rolled every turn; three of its six faces sail the "
          "barbarian ship one space closer. When it arrives, your active "
          "knights are measured against the number of cities on the board. "
          "Win and the strongest defender scores; lose and the weakest lose a "
          "city. Until the first attack a 7 does not move the robber.",
          group=EXPANSION),
    _bool("city_walls", "military", "City walls", False,
          "Cities & Knights rulebook, 'City Walls'; expansions.md 470–477",
          "Two brick builds a wall under one of your cities and raises your "
          "safe hand limit on a 7 by two cards. Three per player, and a wall "
          "falls with the city it protects.",
          group=EXPANSION),
    _bool("progress_cards", "cards", "Progress cards", False,
          "Cities & Knights rulebook, 'Progress Cards'; expansions.md 426–462",
          "Three decks — science, trade and politics — drawn when the event "
          "die shows a matching city gate and your improvement level beats "
          "the red die. They replace development cards outright: with this on "
          "the development deck cannot be bought from.",
          group=EXPANSION),
    {
        "id": "card_system",
        "group": EXPANSION,
        "category": "cards",
        "type": CHOICE,
        # "Progress" rather than "development", so a table that ticks progress
        # cards and changes nothing else plays the published rule. It says
        # nothing at all in a base game: with the progress decks switched off
        # there is only one deck to draw from whatever this is set to.
        "default": "progress",
        "options": [
            {
                "id": "progress",
                "name": "Progress cards replace them",
                "summary": (
                    "The Cities & Knights rule: where progress cards are in "
                    "play they are the table's only card deck, and the "
                    "development deck cannot be bought from. A table not "
                    "playing progress cards buys development cards as usual."
                ),
            },
            {
                "id": "development",
                "name": "Development cards only",
                "summary": (
                    "The base game deck, bought with grain, wool and ore. A "
                    "table that switched the progress decks on and then chose "
                    "this is dealt no progress cards — the city gates open "
                    "onto nothing."
                ),
            },
            {
                "id": "both",
                "name": "Both decks (house rule)",
                "summary": (
                    "The two systems side by side: the development deck stays "
                    "buyable and the city gates still deal progress cards. No "
                    "rulebook plays it this way — the decks, the hands and the "
                    "victory points simply add up, and a card that names "
                    "\"development cards\" and one that names \"progress "
                    "cards\" each mean their own."
                ),
            },
        ],
        "name": "Card system",
        "source": (
            "expansions.md 303 (\"Development cards are not used in Cities & "
            "Knights and are completely replaced by progress cards\") and 427 "
            "(\"Progress cards completely replace development cards and can "
            "never be bought with resources\"); base game rulebook, "
            "'Development Cards'. Both decks at once is a house rule and no "
            "rulebook's."
        ),
        "summary": (
            "Which deck of cards this table plays with. The published answer "
            "is that progress cards replace development cards outright, which "
            "is what a table playing Cities & Knights gets by default; the "
            "third option is a house rule that runs both at once."
        ),
    },
    _bool("setup_second_city", "board", "Start with a city", False,
          "Cities & Knights rulebook, 'Setup'; expansions.md 301–302",
          "The second starting building is a city rather than a settlement, "
          "and it pays out one resource — and one commodity where the terrain "
          "has one — from every hex it touches.",
          group=EXPANSION),
]


# --- Seafarers, one mechanic at a time ----------------------------------
# The expansion decomposed the same way Cities & Knights is. Ships are the
# foundation: nothing else here means anything without a sea network, which is
# what `DEPENDENCIES` below records.
RULES += [
    _bool("ships", "sea", "Ships", False,
          "Seafarers rulebook, 'Ships'; expansions.md 35-56",
          "One wool and one lumber builds a ship on a sea edge, and a shipping "
          "route expands your network exactly as roads do. A ship may never "
          "share a hex side with a road, and the two networks only join where "
          "you have a settlement. This also gives the board its sea edges, so "
          "a second island can be reached at all.",
          group=EXPANSION),
    _bool("ship_movement", "sea", "Moving ships", False,
          "Seafarers rulebook, 'Moving Ships'; expansions.md 62-71",
          "One ship per turn may be picked up and re-laid anywhere you could "
          "build a new one, for free. Not a ship built this turn, not one whose "
          "both ends touch your other pieces — which is what a closed route "
          "between two of your settlements is — and never off a hex side the "
          "pirate is sitting beside.",
          group=EXPANSION),
    _bool("pirate", "sea", "The pirate", False,
          "Seafarers rulebook, 'The Pirate'; expansions.md 88-100",
          "A black ship the roller of a 7 may move instead of the robber. It "
          "sits on a sea hex, steals one card from a player with a ship beside "
          "it, and blocks every hex side around that hex: no ship may be built "
          "there and none may be moved away. It does not stop production.",
          group=EXPANSION),
    _bool("longest_trade_route", "victory", "Longest Trade Route", False,
          "Seafarers rulebook, 'The Longest Trade Route'; expansions.md 76-85",
          "Roads and ships count together for the 2-point card, replacing the "
          "roads-only Longest Road. A road and a shipping route only join into "
          "one route where their owner has a settlement or city at the "
          "intersection they meet on.",
          group=EXPANSION),
    _bool("start_on_main_land", "board", "Start on the main land only", False,
          "Seafarers rulebook, Scenario: The Wonders of Catan; expansions.md 251 "
          "(\"Players build their first two settlements with roads or ships on "
          "the main island only\"); Heading for New Shores, expansions.md 131",
          "A starting settlement may only go on a region the map calls the "
          "main land. It does not restrict building later — sailing to a far "
          "island and settling it is the point of the game this belongs to. On "
          "the built-in boards every land region is main land, so this changes "
          "nothing there; it takes effect on a custom map that names an island "
          "region.",
          group=EXPANSION),
    _bool("island_victory_points", "victory", "Special points for new islands", False,
          "Seafarers rulebook, 'Catan Chits'; expansions.md 121-122, 208-210",
          "Your first settlement on an island you did not start on scores "
          "special victory points on top of the point the settlement itself is "
          "worth. An island is worked out from the board — every stretch of "
          "land the sea cuts off from the rest is one — so the same rule fits "
          "any map.",
          group=EXPANSION),
    _bool("desert_regions", "board", "Desert splits regions like the sea", False,
          "Seafarers rulebook, Scenario: Through the Desert; expansions.md 125-127 "
          "(research §2.1)",
          "A belt of desert counts as a barrier between regions, exactly as open "
          "sea does. Your first settlement in each area the desert cuts off — the "
          "land strip beyond it — scores the same special victory points a new "
          "island does, so 'Through the Desert' is played by reaching four "
          "foreign areas rather than four islands. Needs the island bonus, which "
          "does the scoring. On a board with no desert belt it changes nothing.",
          group=EXPANSION),
    _bool("fog_reveal", "sea", "Fog hexes revealed by ships", False,
          "Seafarers rulebook, Scenario: The Fog Islands; expansions.md 119 "
          "(research §2.1)",
          "The fog hexes lie face-down until one of your ships or roads reaches "
          "them. Revealing a producing land hex hands you 1 resource of its "
          "type on the spot; a revealed sea hex is just open water and pays "
          "nothing. There are no special victory points for a discovery — the "
          "fog only hides resources. Play it on the Fog Islands map.",
          group=EXPANSION),
    _bool("coast_gifts", "scenario", "Coast gifts of the Forgotten Tribe", False,
          "Seafarers rulebook, Scenario 5: The Forgotten Tribe, p. 20; "
          "expansions.md 128-131 (research §2.1)",
          "The small islands carry marked coast edges. Sailing a ship onto one — "
          "building it or moving it there — claims the gift printed on it, once: "
          "a Catan chit worth 1 special victory point, a development card drawn "
          "from the deck (playable only from your next turn, like a bought one), "
          "or a harbour you place at one of your own coastal settlements. Play it "
          "on the Forgotten Tribe map.",
          group=EXPANSION),
    _bool("no_build_barren_islands", "scenario", "No building on barren islands", False,
          "Seafarers rulebook, Scenario 5: The Forgotten Tribe, p. 20 "
          "(\"no settlement can be built on the surrounding small islands that do "
          "not produce resources\")",
          "You may not build a settlement on the barren small islands — the ones "
          "that carry the gift edges and yield no resources. They exist only to "
          "hold the gifts. On a board with no such islands it changes nothing.",
          group=EXPANSION),
    _bool("robber_avoids_barren_islands", "scenario", "Robber avoids barren islands", False,
          "Seafarers rulebook, Scenario 5: The Forgotten Tribe, p. 20 "
          "(\"the robber cannot move to the small islands\")",
          "The robber may not be moved onto the barren small islands of the "
          "Forgotten Tribe. On a board with no such islands it changes nothing.",
          group=EXPANSION),
    _bool("cloth_villages", "cards", "Cloth for Catan villages", False,
          "Seafarers rulebook, Scenario 6: Cloth for Catan, p. 22",
          "The small islands carry villages — number tokens sitting on "
          "intersections, each with a supply of cloth bolts. Connect one of your "
          "settlements or cities to a village by a shipping route and you take 1 "
          "bolt at once, then 1 more from that village every time its number is "
          "rolled, until its supply runs dry. Two bolts of cloth score 1 victory "
          "point; an unpaired bolt scores nothing. Play it on the Cloth for Catan "
          "map.",
          group=EXPANSION),
    _bool("oil_tokens", "cards", "Oil Springs: oil production", False,
          "Catan: Oil Springs (Assadourian & Hansen), coilspringsgb_2015_web.pdf "
          "p. 1 (\"Buildings on oil springs produce oil\")",
          "Three hexes carry Oil Spring tiles. A building on one produces oil "
          "when the hex's number is rolled — one for a settlement, two for a "
          "city, three for a metropolis — handed out one token at a time from "
          "the roller clockwise until everyone has what they made or the supply "
          "of 15 runs out. You may hold at most 4 oil. Play it on the Oil "
          "Springs map.",
          group=EXPANSION),
    _bool("disaster_track", "scenario", "Oil Springs: disaster track", False,
          "Catan: Oil Springs, coilspringsgb_2015_web.pdf p. 2 (\"For every five "
          "oil used ... an environmental disaster results\")",
          "Using oil is powerful — convert 1 oil into 2 of any resource — but "
          "every fifth oil used advances a shared disaster track that fires at "
          "the end of the turn. A 7 floods the coasts (sea-bordering settlements "
          "are removed and coastal cities reduced to settlements); any other "
          "roll pollutes a hex, which loses its number for good. When five "
          "number tokens have been destroyed the board dies and the game ends "
          "with no true winner.",
          group=EXPANSION),
    _bool("oil_sequester_vp", "victory", "Oil Springs: sequester oil for VP", False,
          "Catan: Oil Springs, coilspringsgb_2015_web.pdf p. 2 (\"For every 3 "
          "oil you sequester, you gain 1 Victory Point\")",
          "Instead of using oil you may sequester one per turn — flipping it out "
          "of the game for good rather than advancing the disaster track. Every "
          "three oil sequestered scores a victory point, and the first player to "
          "sequester three takes the 1-VP Champion of the Environment token, "
          "which passes to anyone who later sequesters more.",
          group=EXPANSION),
    _bool("oil_metropolis", "cards", "Oil Springs: oil metropolis", False,
          "Catan: Oil Springs, coilspringsgb_2015_web.pdf p. 2 (\"use 1 brick, 1 "
          "grain, 1 ore and 2 oil to upgrade one of your cities to a "
          "metropolis\")",
          "Spend 1 brick, 1 grain, 1 ore and 2 oil to upgrade one of your cities "
          "into a metropolis. A metropolis produces three of its resource instead "
          "of two, is worth 3 victory points, and — thanks to its sea walls — is "
          "immune to coastal flooding. Using the oil advances the disaster track "
          "like any other oil use.",
          group=EXPANSION),
    _bool("setup_third_settlement", "board", "Start with a third settlement", False,
          "Seafarers rulebook, Scenario 6: Cloth for Catan, p. 22 "
          "(\"everyone can build a third settlement ... you receive your "
          "starting resources\")",
          "Setup runs a third round: after the two normal starting settlements, "
          "everyone places a third one, and it is the third settlement — not the "
          "second — that pays out its adjacent hexes as your opening hand.",
          group=EXPANSION),
    _bool("gold_field_choice", "sea", "Gold fields (resources of choice)", False,
          "Seafarers rulebook, Section 9 'Gold Fields' (\"each settlement is "
          "entitled to one resource, while each city is entitled to two ... may "
          "select ANY of the five resources ... any mix\")",
          "A gold field pays resources of your choice, not a fixed card. When "
          "its number is rolled, every adjacent building's owner takes resources "
          "from the bank — one per settlement, two per city — in any mix of the "
          "five. Each owed player picks their own, and the roll waits on them. "
          "Distinct from the Explorers & Pirates gold currency, which pays coins.",
          group=EXPANSION),
    _bool("wonders", "victory", "Wonders of Catan", False,
          "Seafarers rulebook, Scenario 8: The Wonders of Catan, pp. 26-29",
          "Each player may build one Wonder chosen from five — Cathedral, Great "
          "Bridge, Great Wall, Monument, Theater. A Wonder can only be started "
          "once its printed requirement is met (a city and 6 points, a settlement "
          "at the strait, settlements at the wasteland, a harbour city with a "
          "5-long trade route, or two cities), and once you start one no other "
          "player may build the same Wonder. Each Wonder has four levels, every "
          "level costing the five resources on its card. You win by finishing a "
          "Wonder, or by reaching the target with a strictly higher wonder level "
          "than every opponent. Play it on the Wonders of Catan map.",
          group=EXPANSION),
    _bool("wonder_island_points", "victory", "Special points for small islands", False,
          "Seafarers rulebook, Scenario 8: The Wonders of Catan, p. 27 "
          "(\"If you build a settlement on one of the smaller islands ... you "
          "receive a special victory point\")",
          "Every one of your settlements on a small island is worth 1 special "
          "victory point — each settlement, not the first on a new island, so two "
          "on one island score two. An island is worked out from the board, so "
          "the rule fits any map; on a board with no small islands it changes "
          "nothing.",
          group=EXPANSION),
    _bool("pirate_fleet", "sea", "The pirate fleet", False,
          "Seafarers rulebook, Scenario 7 'The Pirate Islands', p. 22",
          "A roaming enemy fleet — a neutral ship, not a player — circles the two "
          "central desert islands clockwise. After every roll, before production or "
          "a 7, it sails the lower of the two dice along its track; if it lands "
          "beside one of your coastal settlements or cities it raids you, its "
          "strength the die it moved and yours your warships. Lose and you are "
          "robbed of a card and one more per city; win and you take a card of your "
          "choice. There is no robber in this scenario. Play it on the Pirate "
          "Islands map.",
          group=EXPANSION),
    _bool("pirate_warships", "sea", "Warships", False,
          "Seafarers rulebook, Scenario 7 'The Pirate Islands', p. 20",
          "Reveal a Knight card to turn one of your ships into a warship. Warships "
          "are your strength against the pirate fleet and the fortresses; the card "
          "is spent and set aside, and the ship stays on the board turned on its "
          "side. Needs ships, so there is a ship to convert.",
          group=EXPANSION),
    _bool("pirate_fortresses", "sea", "Pirate fortresses", False,
          "Seafarers rulebook, Scenario 7 'The Pirate Islands', pp. 20-22",
          "Four fortresses — a settlement of a player's colour on three Catan "
          "chits — sit on the western islands. Sail a route to your own-colour "
          "fortress and attack at the end of your turn: roll a die for its "
          "strength, and more warships than the roll strips a chit; fewer costs you "
          "two warships and a tie one. Clear all three chits and you recapture the "
          "settlement — a point, a producer, upgradeable to a city. You win by "
          "recapturing your fortress and holding at least 10 victory points.",
          group=EXPANSION),
]


# --- Explorers & Pirates, one mechanic at a time ------------------------
# The expansion decomposed the same way Cities & Knights and Seafarers are.
# Every switch is off by default so the base game is unchanged, and the few
# that cannot stand alone are recorded in `DEPENDENCIES` below. These rules are
# declared ahead of the engine code that reads them — the feature waves land
# after this catalogue — so the picker and the presets have real ids to point
# at while the mechanics are built.
RULES += [
    _bool("movement_phase", "sea", "Movement phase", False,
          "Catan: Explorers & Pirates rulebook, 'Turn Structure'; expansions.md 851-862",
          "A turn runs production, then trade and build, then movement, in that "
          "fixed order. You may not trade or build once movement has begun — the "
          "one exception is founding a settlement with a settler ship.",
          group=EXPANSION),
    _bool("gold", "trade", "Gold", False,
          "Catan: Explorers & Pirates rulebook, 'Gold'; expansions.md 854, 960-967",
          "Gold is a second currency beside resources: you take 1 gold when a "
          "non-7 production roll pays you nothing, three identical resources buy "
          "1 gold, and twice a turn 2 gold buys any 1 resource. Gold trades with "
          "opponents like a resource card.",
          group=EXPANSION),
    _bool("no_dev_cards", "cards", "No development cards", False,
          "Catan: Explorers & Pirates rulebook, 'Fundamental Differences'; "
          "expansions.md 839",
          "No development cards exist — the deck cannot be bought from at all. "
          "Explorers & Pirates has no knight, progress or victory point "
          "development cards.",
          group=EXPANSION),
    _bool("no_city_upgrades", "scenario", "No city upgrades", False,
          "Catan: Explorers & Pirates rulebook, 'Fundamental Differences'; "
          "expansions.md 838",
          "Settlements are never upgraded to cities and the city pieces are "
          "unused. A game scored on settlements, harbor settlements and missions "
          "instead.",
          group=EXPANSION),
    _bool("transport_ships", "sea", "Transport ships", False,
          "Catan: Explorers & Pirates rulebook, 'Ships and Movement'; "
          "expansions.md 864-882",
          "Ships are transports carrying pieces in a hold (1 large or 2 small) "
          "with movement points along sea routes; they never form routes. Built "
          "for 1 lumber and 1 wool on a sea route beside one of your harbor "
          "settlements.",
          group=EXPANSION),
    _bool("harbor_settlements", "sea", "Harbor settlements", False,
          "Catan: Explorers & Pirates rulebook, 'Harbor Settlements'; "
          "expansions.md 894-902",
          "Upgrade a coastal settlement (2 grain and 2 ore) into a harbor "
          "settlement worth 2 victory points with a cargo basin — the only site "
          "where ships, settlers and crews may be built. It yields 1, not 2, on "
          "production.",
          group=EXPANSION),
    _bool("ships_explore", "sea", "Ships explore", False,
          "Catan: Explorers & Pirates rulebook, 'Discovery'; expansions.md 883-893",
          "Moving a ship so one end points at an undiscovered hex reveals it, "
          "and that discovery ends the ship's movement for the turn.",
          group=EXPANSION),
    _bool("cargo_settlers", "sea", "Settlers", False,
          "Catan: Explorers & Pirates rulebook, 'Settlers'; expansions.md 903-918",
          "Settlers (a settlement's cost) are built into a basin or hold and "
          "carried by ship. A settler ship pointing at a free coastal corner "
          "founds a settlement there for free.",
          group=EXPANSION),
    _bool("crews", "sea", "Crews", False,
          "Catan: Explorers & Pirates rulebook, 'Crews'; expansions.md 919-928",
          "Crews (1 ore and 1 wool) ride ships and are landed on mission "
          "destinations only.",
          group=EXPANSION),
    _bool("pirate_ship_instead_of_robber", "sea", "Pirate ship instead of the robber", False,
          "Catan: Explorers & Pirates rulebook, 'The Pirate Ship'; "
          "expansions.md 841, 843, 934-949",
          "The roller of a 7 places their own pirate ship on an allowed sea hex, "
          "steals 1 card from an opponent with a ship there, and thereafter "
          "charges every mover 1 gold tribute per ship crossing that hex. No "
          "robber, and no land is blocked.",
          group=EXPANSION),
    _bool("chase_pirate", "sea", "Chase the pirate", False,
          "Catan: Explorers & Pirates rulebook, 'Chasing the Pirate'; "
          "expansions.md 951-958",
          "A battle-ready ship — unmoved and next to the pirate's hex — may roll "
          "one die; a 6 chases the pirate away and lets the chaser reposition it "
          "and steal.",
          group=EXPANSION),
    _bool("missions", "scenario", "Missions", False,
          "Catan: Explorers & Pirates rulebook, 'Missions in General'; "
          "expansions.md 969-978",
          "Mission tracks with a per-player marker each; a marker ahead of every "
          "other on a track holds that mission's 1-point lead card. The container "
          "for the three missions below.",
          group=EXPANSION),
    _bool("mission_pirate_lairs", "scenario", "Mission: Pirate Lairs", False,
          "Catan: Explorers & Pirates rulebook, 'Pirate Lairs'; expansions.md 980-998",
          "Discover gold-field and pirate-lair hexes, land crews to capture "
          "lairs and advance the Pirate Lairs track. A captured lair's number "
          "pays 2 gold per adjacent building.",
          group=EXPANSION),
    _bool("mission_fish", "scenario", "Mission: Fish for Catan", False,
          "Catan: Explorers & Pirates rulebook, 'Fish for Catan'; "
          "expansions.md 1000-1019",
          "Catch fish hauls at discovered shoal hexes and deliver them to the "
          "Council of Catan docks to advance the Fish track.",
          group=EXPANSION),
    _bool("mission_spices", "scenario", "Mission: Spices for Catan", False,
          "Catan: Explorers & Pirates rulebook, 'Spices for Catan'; "
          "expansions.md 1021-1040",
          "Trade crews for spice sacks at village hexes — each village grants a "
          "permanent advantage — and deliver the sacks to the Council to advance "
          "the Spices track.",
          group=EXPANSION),
]


# --- Expansion numbers --------------------------------------------------
RULES += [
    _int("barbarian_track_length", "military", "Barbarian track spaces", 7, 3, 15,
         "Cities & Knights rulebook; expansions.md 407",
         "How many spaces the barbarian ship crosses before it attacks. "
         "Shorter means a more dangerous game.",
         group=EXPANSION),
    _int("progress_hand_limit", "cards", "Progress cards in hand", 4, 1, 10,
         "Cities & Knights rulebook; expansions.md 431",
         "How many progress cards a player may hold. Cards worth a victory "
         "point are revealed on sight and never take a slot.",
         group=EXPANSION),
    _int("max_city_walls", "military", "City walls per player", 3, 0, 10,
         "Cities & Knights rulebook; expansions.md 473–474",
         "How many city walls each player may have standing at once.",
         group=EXPANSION),
    _int("max_ships", "sea", "Ships per player", 15, 1, 60,
         "Seafarers rulebook; expansions.md 51-52",
         "How many ships each player may have on the board at once.",
         group=EXPANSION),
    _int("island_points_per_island", "victory", "Points for a new island", 2, 1, 5,
         "Seafarers rulebook, 'Heading for New Shores'; expansions.md 121",
         "How many special victory points the first settlement on an island "
         "you did not start on is worth.",
         group=EXPANSION),
    # The Explorers & Pirates piece supplies (849): 4 harbor settlements, 2
    # settlers, 9 crews. Ships reuse the existing `max_ships`, which every E&P
    # preset sets to 3 rather than adding a second ships count.
    _int("max_harbor_settlements", "sea", "Harbor settlements per player", 4, 0, 20,
         "Catan: Explorers & Pirates rulebook; expansions.md 849",
         "How many harbor settlements each player may have standing at once.",
         group=EXPANSION),
    _int("max_settlers", "sea", "Settlers per player", 2, 0, 10,
         "Catan: Explorers & Pirates rulebook; expansions.md 849",
         "How many settlers each player may have at once.",
         group=EXPANSION),
    _int("max_crews", "sea", "Crews per player", 9, 0, 20,
         "Catan: Explorers & Pirates rulebook; expansions.md 849",
         "How many crews each player may have at once.",
         group=EXPANSION),
    _int("ship_movement_points", "sea", "Ship movement points", 4, 1, 12,
         "Catan: Explorers & Pirates rulebook, 'Ships and Movement'; expansions.md 874",
         "How many movement points a ship has each turn, before any wool or "
         "Swift Voyage bonus.",
         group=EXPANSION),
    _int("starting_gold", "trade", "Starting gold", 0, 0, 10,
         "Catan: Explorers & Pirates rulebook; expansions.md 1045, 1053",
         "How much gold each player starts the game with. Every published "
         "Explorers & Pirates scenario starts each player with 2.",
         group=EXPANSION),
]


# --- Traders & Barbarians: The Fishermen of Catan -----------------------
# The first T&B scenario, decomposed into individual switches the way Cities &
# Knights, Seafarers and Explorers & Pirates are. `fish_tokens` is the container
# for the supply and the spend ladder; the sources (fishing grounds, the lake)
# and the old boot each declare `fish_tokens` in DEPENDENCIES below. Every switch
# defaults off, so a base game is unchanged.
RULES += [
    _bool("fish_tokens", "scenario", "Fish tokens", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 501-516",
          "A face-down supply of fish tokens you draw, hold privately (cap 7) "
          "and spend by fish total for a benefit: 2 sends the robber off the "
          "board, 3 steals a random card, 4 takes a bank card, 5 builds a free "
          "road, 7 draws a free development card. No change is given; fish are "
          "never counted toward the hand limit, never discarded on a 7, never "
          "stolen and never traded. The container for the fish sources below.",
          group=EXPANSION),
    _bool("fishing_grounds", "scenario", "Fishing grounds", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 495-499",
          "Fishing-ground tiles sit on the board frame; a settlement built on "
          "one of the three coastal intersections a tile touches draws 1 fish "
          "token, a city 2, whenever the tile's number (4/5/6/8/9/10) is rolled.",
          group=EXPANSION),
    _bool("lake_hex", "scenario", "The lake", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 493, 500",
          "A lake replaces the desert (and never sits on the coast); a "
          "settlement adjacent to it draws 1 fish token, a city 2, whenever a "
          "2, 3, 11 or 12 is rolled.",
          group=EXPANSION),
    _bool("old_boot", "scenario", "The old boot", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 517-521",
          "The old boot (mixed into the fish supply and revealed the moment it "
          "is drawn) raises its holder's personal winning threshold by 1. After "
          "rolling you may pass it to any player with as many victory points as "
          "you or more; the sole points leader must keep it.",
          group=EXPANSION),
    _bool("robber_starts_off_board", "board", "Robber starts off the board", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 496, 504",
          "The robber begins beside the board rather than on the desert and "
          "enters play only when the first 7 (or a knight) is rolled. Spending "
          "2 fish can send it back off the board.",
          group=EXPANSION),
]

RULES += [
    _int("max_fish_held", "scenario", "Fish tokens in hand", 7, 1, 15,
         "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
         "expansions.md 510",
         "How many fish tokens a player may hold at once. A draw that would "
         "exceed the cap is not taken.",
         group=EXPANSION),
    _int("fishing_ground_count", "scenario", "Fishing grounds on the board", 6, 0, 12,
         "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
         "expansions.md 492",
         "How many fishing-ground tiles the board frame carries.",
         group=EXPANSION),
]


# --- Traders & Barbarians: gold coins (shared substrate) ----------------
# The T&B gold currency, held in `Player.gold`. Distinct from the Explorers &
# Pirates `gold` rule: it shares the field and gold.py's buy/immunity helpers,
# but sells at 4:1 (not 3:1) and grants no empty-roll bonus. The two are two
# economies on one field, so EXCLUSIONS refuses them both on. Defaults off, so a
# base game is unchanged.
RULES += [
    _bool("gold_coins", "trade", "Gold coins", False,
          "Catan: Traders & Barbarians rulebook, 'The Rivers of Catan'; "
          "expansions.md 559-565, 664-668, 740-744",
          "Gold coins are a second currency held apart from your resource hand: "
          "twice a turn 2 gold buys any 1 resource from the supply, and maritime "
          "trade buys 1 gold for 4 identical resources (3 with the matching 3:1 "
          "harbour, never a 2:1). Coins trade with opponents like a resource "
          "card and can never be stolen by the robber or a Monopoly.",
          group=EXPANSION),
]


# --- Traders & Barbarians: The Rivers of Catan --------------------------
# Rivers cross the island; roads and settlements along them earn gold coins, and
# bridges span the crossings. Decomposed the way the other expansions are —
# every switch off by default, the coin economy shared through `gold_coins`, and
# the two scoring tiles folded into `victory_points_for` behind their own flags.
RULES += [
    _bool("river_gold", "scenario", "River gold", False,
          "Catan: Traders & Barbarians rulebook, 'The Rivers of Catan'; "
          "expansions.md 542-544",
          "Building a settlement adjacent to a river hex, or a road on a path "
          "adjacent to a river hex, pays you 1 gold coin immediately — during "
          "set-up as well as later. Upgrading a settlement to a city pays "
          "nothing.",
          group=EXPANSION),
    _bool("bridges", "scenario", "Bridges", False,
          "Catan: Traders & Barbarians rulebook, 'The Rivers of Catan'; "
          "expansions.md 546-552",
          "Bridges (2 brick and 1 lumber) are built only on a river-crossing "
          "bridge site and pay 3 gold coins each. A bridge counts exactly as a "
          "road for the Longest Road and for connecting new buildings; a normal "
          "road may never sit on a bridge site, and Road Building may not place "
          "one. Each player may build at most three.",
          group=EXPANSION),
    _bool("wealthiest_settler", "victory", "Wealthiest Settler", False,
          "Catan: Traders & Barbarians rulebook, 'The Rivers of Catan'; "
          "expansions.md 556-558",
          "The one player who alone holds the most gold coins keeps the "
          "Wealthiest Settler tile, worth +1 victory point. It is lost the "
          "moment another player's coin total equals or passes theirs.",
          group=EXPANSION),
    _bool("poor_settler", "victory", "Poor Settler", False,
          "Catan: Traders & Barbarians rulebook, 'The Rivers of Catan'; "
          "expansions.md 553-555",
          "Every player tied for the fewest gold coins (a tie at zero counts) "
          "holds a Poor Settler tile, worth -2 victory points. It is returned "
          "the moment they no longer have the fewest.",
          group=EXPANSION),
]

RULES += [
    _int("max_bridges", "scenario", "Bridges per player", 3, 0, 10,
         "Catan: Traders & Barbarians rulebook, 'The Rivers of Catan'; "
         "expansions.md 551",
         "How many bridges one player may build over the whole game.",
         group=EXPANSION),
]


# --- Traders & Barbarians: The Caravans ---------------------------------
# Camels grow out of the central oasis in up to three non-branching caravans.
# One container rule: the camel piece, the oasis-arrow geometry, the voting round
# and the two scoring effects are inseparable — a camel with no caravan and no
# vote is meaningless. Depends on the oasis map (refused at start without it), so
# it needs no other rule; defaults off, so a base game is unchanged.
RULES += [
    _bool("caravans", "scenario", "The Caravans", False,
          "Catan: Traders & Barbarians rulebook, 'The Caravans'; "
          "expansions.md 573-601",
          "Camels grow out of the central oasis in up to three non-branching "
          "caravans. Whenever you build or upgrade at least one settlement in a "
          "turn, exactly one camel is placed at the end of it, its position "
          "decided by a voting round in which players bid wool and grain cards. "
          "A road sharing a camel's path counts as two roads for the Longest "
          "Road, and a settlement or city standing between two camels is worth "
          "one extra victory point. Needs the oasis board.",
          group=EXPANSION, suggests_victory_target=12),
]

RULES += [
    _int("max_camels", "scenario", "Camels in the supply", 22, 0, 40,
         "Catan: Traders & Barbarians rulebook, 'The Caravans'; "
         "expansions.md 574",
         "How many camels the box holds; all three caravans end the moment the "
         "supply is exhausted.",
         group=EXPANSION),
]


# --- Traders & Barbarians: Barbarian Attack -----------------------------
# Barbarians land on the coastal hexes and players train knights at a central
# castle to expel them. Decomposed the way the other expansions are: the war
# itself is one container rule (`barbarian_attack`), the scenario's 26-card deck
# is a second switch that closes the base development deck (`barbarian_attack_deck`),
# and the two supplies are ints. Every switch off by default, so a base game is
# unchanged. `barbarian_attack` needs the coin economy (`gold_coins`) for its
# compensation payouts and the scenario deck it trains knights from, so it
# declares both in DEPENDENCIES below.
RULES += [
    _bool("barbarian_attack", "military", "Barbarian Attack", False,
          "Catan: Traders & Barbarians rulebook, 'Barbarian Attack'; "
          "expansions.md 607-662",
          "Barbarians land on the coastal hexes whenever you build: each build "
          "resolves an attack that drops barbarians on the hexes whose numbers "
          "come up. A hex holding three is conquered — its token turns face "
          "down, it produces nothing, its harbour dies and the buildings walled "
          "off by it topple. You train knights from the scenario's card deck, "
          "place them on the six paths around the castle and move them out to "
          "defend the coast; a coast with more knights than barbarians frees "
          "those barbarians as your prisoners, and every two prisoners are worth "
          "a victory point. There is no robber. Needs the castle board.",
          group=EXPANSION, suggests_victory_target=12),
    _bool("barbarian_attack_deck", "military", "Barbarian Attack deck", False,
          "Catan: Traders & Barbarians rulebook, 'Barbarian Attack'; "
          "expansions.md 617, 633-642",
          "Replaces the base development deck with the scenario's 26 cards — 14 "
          "Knighthood, 4 Swift Knight, 4 Treason and 4 Intrigue. Each card is "
          "revealed and resolved the moment you buy it, then discarded; when the "
          "stack runs out the discard pile is reshuffled.",
          group=EXPANSION),
]

RULES += [
    _int("max_barbarian_knights", "military", "Knights per player", 6, 1, 12,
         "Catan: Traders & Barbarians rulebook, 'Barbarian Attack'; "
         "expansions.md 615",
         "How many knights of their own colour each player may have on the "
         "board at once.",
         group=EXPANSION),
    _int("barbarian_supply", "military", "Barbarians in the supply", 30, 0, 60,
         "Catan: Traders & Barbarians rulebook, 'Barbarian Attack'; "
         "expansions.md 610",
         "How many barbarian figures the box holds; once the supply is empty no "
         "further attacks take place for the rest of the game.",
         group=EXPANSION),
]


# --- Traders & Barbarians: the main scenario ----------------------------
# The wagon scenario: each player drives a wagon between three trade hexes,
# delivering commodities for gold and victory points. Decomposed the way every
# other expansion is — the delivery run (`trade_caravans`), the upgradeable
# baggage-train card (`baggage_train`), the three path barbarians that block a
# wagon (`roaming_barbarians`) and the scenario's own 26-card deck
# (`trade_dev_deck`) are four separate switches, every one off by default so the
# base game is unchanged. The delivery run needs the coin economy it is paid in
# and the scenario deck it draws Swift Journey and Knight cards from, so it
# declares both in DEPENDENCIES; the baggage train and the path barbarians are
# meaningless without the wagon, so each depends on it.
RULES += [
    _bool("trade_caravans", "scenario", "Trade wagons", False,
          "Catan: Traders & Barbarians rulebook, 'Traders & Barbarians'; "
          "expansions.md 679, 696-719",
          "Your wagon starts on your city's intersection and, after you finish "
          "trading and building, moves intersection to intersection along paths, "
          "spending movement points — 2 for a path with no road, 1 for one of "
          "your own roads, and 1 plus 1 gold to the owner for a rival's road. "
          "Reaching a trade hex (castle, quarry or glassworks) that matches the "
          "commodity you carry delivers it for gold and 1 victory point, then you "
          "draw the next commodity, which names your next destination. Needs the "
          "trade-hex board.",
          group=EXPANSION, suggests_victory_target=13),
    _bool("baggage_train", "scenario", "Baggage train", False,
          "Catan: Traders & Barbarians rulebook, 'Traders & Barbarians'; "
          "expansions.md 689, 720-726",
          "An upgradeable card of your own: upgrading it (paying the resources on "
          "the back of the next card) raises your wagon's movement points (4 up "
          "to 7), the gold each delivery pays (1 up to 5) and the die numbers "
          "that drive off a barbarian. The fifth and last upgrade is worth 1 "
          "victory point.",
          group=EXPANSION),
    _bool("roaming_barbarians", "military", "Roaming barbarians", False,
          "Catan: Traders & Barbarians rulebook, 'Traders & Barbarians'; "
          "expansions.md 690, 727-737, 745",
          "Three barbarians sit on paths. Crossing a barbarian's path costs 2 "
          "extra movement points. A rolled 7 makes you move one barbarian to a "
          "free path, drawing a card from the owner of any road you land it on. "
          "Once your baggage train is upgraded you may pause beside a barbarian "
          "and roll to drive it off.",
          group=EXPANSION),
    _bool("trade_dev_deck", "cards", "Trade wagon deck", False,
          "Catan: Traders & Barbarians rulebook, 'Traders & Barbarians'; "
          "expansions.md 691, 745-748",
          "Replaces the base development deck with the scenario's 26 cards — 15 "
          "Knight (move a barbarian), 3 Road Building, 3 Swift Journey (move your "
          "wagon a second time) and 1 each Toolmaking, Glassmaking and Quarry "
          "worth a victory point. Each card is bought and resolved through its "
          "own path, not the base deck.",
          group=EXPANSION),
]

RULES += [
    _int("wagon_movement_points", "scenario", "Wagon movement points", 4, 1, 12,
         "Catan: Traders & Barbarians rulebook, 'Traders & Barbarians'; "
         "expansions.md 704",
         "How many movement points a wagon has each turn from the first baggage "
         "train card, before any upgrade.",
         group=EXPANSION),
]


# --- CATAN - The Helpers ------------------------------------------------
# The scenario is twelve one-shot "helper" tiles, each a named character with an
# activated advantage. Decomposed the way every other expansion is: the tile
# framework (the display, the one tile each player holds, the exchange/sun-moon
# lifecycle) is one container rule, and each of the twelve advantages is its own
# switch. No advantage does anything without the framework, so each declares it
# in DEPENDENCIES below; the framework defaults off, so a base game is
# unchanged. No tile touches the victory target (Helpers_Rules.pdf p. 4), so the
# preset keeps the 10-point game.
RULES += [
    _bool("helper_tiles", "cards", "Helper tiles", False,
          "Helpers_Rules.pdf, 'The Helpers Overview and Set-up' and 'Using The "
          "Helpers', pp. 2-4",
          "CATAN - The Helpers: each player holds one helper tile with a "
          "one-shot advantage, drawn from a shared face-up display. After using "
          "a tile you exchange it for a new one or flip it from its sun side to "
          "its moon side to use once more, then it is spent. Which advantages "
          "are in play is set by the twelve switches below; a base game is "
          "unchanged.",
          group=EXPANSION),
    _bool("helper_forced_trade", "cards", "Helper: Forced Trade (Asla)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Forced Trade (Asla), p. 6",
          "Choose 1 resource type and request it from 1 or 2 players; each who "
          "holds it gives you 1, and you give back 1 resource of your choice per "
          "resource received.",
          group=EXPANSION),
    _bool("helper_makeshift_road", "cards", "Helper: Makeshift Road Building (Yngvi)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Makeshift Road Building "
          "(Yngvi), p. 6",
          "When you build a road you may substitute 1 lumber or 1 brick with any "
          "1 other resource of your choice.",
          group=EXPANSION),
    _bool("helper_resource_compensation", "cards", "Helper: Resource Compensation (Hilda)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Resource Compensation "
          "(Hilda), p. 8",
          "Immediately after any production roll that is not a 7, if you received "
          "no resources, take any 1 resource card of your choice from the supply.",
          group=EXPANSION),
    _bool("helper_move_road", "cards", "Helper: Move a Road (Hogni)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Move a Road (Hogni), p. 7",
          "Remove 1 of your end roads and place it in another location following "
          "normal placement rules.",
          group=EXPANSION),
    _bool("helper_protection_from_seven", "cards", "Helper: Protection from the 7 (Thorolf)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Protection from the 7 "
          "(Thorolf), p. 9",
          "When any player rolls a 7 you must use this: if over 7 cards, keep "
          "them all instead of discarding half; if 7 or fewer, take any 1 "
          "resource of your choice from the supply.",
          group=EXPANSION),
    _bool("helper_dev_card_choice", "cards", "Helper: Development Card Choice (Diara)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Development Card Choice "
          "(Diara), p. 9",
          "When you buy a development card you may substitute 1 of the 3 "
          "resources, then look at the top 3 cards, keep 1 and shuffle the other "
          "2 back.",
          group=EXPANSION),
    _bool("helper_take_from_leader", "cards", "Helper: Take Card from Leader (Ryan)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Take Card From Leader "
          "(Ryan), p. 10",
          "After your production roll is resolved, take 1 resource card of your "
          "choice from an opponent who has more victory points than you.",
          group=EXPANSION),
    _bool("helper_knight_to_building", "cards", "Helper: Assign Knight to Building (Gregor)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Assign Knight to Building "
          "(Gregor), p. 10",
          "Discard 1 of your played knight cards (it no longer counts toward the "
          "Largest Army) to build a settlement for 1 lumber + 1 brick or a city "
          "for 2 ore + 1 grain.",
          group=EXPANSION),
    _bool("helper_trade_frenzy", "cards", "Helper: 2:1 Trade Frenzy (Stina)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', 2:1 Trade Frenzy (Stina), "
          "p. 11",
          "Choose 1 resource type and exchange it with the bank at 2:1 as many "
          "times as you like, all at once.",
          group=EXPANSION),
    _bool("helper_chase_robber", "cards", "Helper: Chase Robber to Desert (Digur)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Chase Robber to Desert "
          "(Digur), p. 10",
          "Move the robber to the desert and take 1 resource of the type the hex "
          "it left produced. Not playable if the robber is already in the desert.",
          group=EXPANSION),
    _bool("helper_take_robber_resource", "cards", "Helper: Take Robber's Resource (Kaja)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Take Robber's Resource "
          "(Kaja), p. 11",
          "Take 1 resource from the supply matching the terrain hex the robber "
          "occupies; if it is in the desert, take a resource of your choice.",
          group=EXPANSION),
    _bool("helper_dev_card_swap", "cards", "Helper: Development Card Swap (Carla)", False,
          "Helpers_Rules.pdf, 'The Helpers in Detail', Development Card Swap "
          "(Carla), p. 11",
          "Place 1 unplayed development card at the bottom of the stack and draw "
          "1 from the top; the drawn card cannot be played this turn.",
          group=EXPANSION),
]


# --- Catan: Frenemies ---------------------------------------------------
# The scenario by Benjamin Teuber: pro-social acts earn blind-drawn favour
# tokens you spend at a guild hall. Decomposed the way every other expansion is
# — the earn framework (`favour_tokens`) is one container rule and the guild-hall
# redemption (`guild_hall`) is a second, each individually switchable and each
# read by engine code. Both default off, so a base game is unchanged. The guild
# rule needs the bag to spend from, so it declares `favour_tokens` in
# DEPENDENCIES below.
RULES += [
    _bool("favour_tokens", "trade", "Favour tokens", False,
          "Catan: Frenemies (Benjamin Teuber), catan_frenemies_rules_093012s.pdf "
          "p. 1, 'Earning Favor Tokens'",
          "Catan: Frenemies. A face-down bag of 58 favour tokens you draw blind "
          "for pro-social acts: 1 for moving the robber harmlessly (to a hex "
          "with no building, or the desert without stealing), 1 for gifting a "
          "resource to an opponent on as many visible points as you or fewer, "
          "and — the first time a road joins your network to an opponent's — 3 "
          "to you and 1 to them. A token drawn on your turn is locked until your "
          "next turn, and favours are never traded or stolen. The bag is spent "
          "at the guild hall below.",
          group=EXPANSION, suggests_victory_target=11),
    _bool("guild_hall", "trade", "Guild hall", False,
          "Catan: Frenemies (Benjamin Teuber), catan_frenemies_rules_093012s.pdf "
          "p. 2, 'Using Favor Tokens'",
          "Catan: Frenemies. On your turn you redeem favour tokens face up at a "
          "guild hall for its favour, or — if you take no guild action — "
          "exchange one token for a fresh blind draw. The five favours (p. 2): "
          "traders (1 token) swap a resource for a different one, merchants (1) "
          "take any resource, road builders (1) build a free road, scholars (2) "
          "draw a development card, and master builders (2) take one of the 8 "
          "Victory-Point markers, worth 1 point each. A token drawn this turn "
          "cannot be spent until your next. Needs the favour tokens above.",
          group=EXPANSION, suggests_victory_target=11),
]


# --- Catan Histories: Rise of the Inkas, one mechanic at a time ---------
# The expansion decomposed into three independently switchable rules. Every one
# is read by the engine's InkasRules mixin and the placement handlers; none of
# the engine ever asks "is this the Inkas" — it asks for the rule that governs
# the behaviour in front of it.
RULES += [
    _bool("tribe_decline", "scenario", "Tribe decline", False,
          "Catan Histories: Rise of the Inkas (Klaus & Benjamin Teuber, 2018), "
          "rulebook 'The Tribes' pp. 7-8; the 4/4/3 cultural goals are stated "
          "verbatim on p. 7 (OFFICIAL, not fan-sourced)",
          "Rise of the Inkas. Each player develops three successive tribes. A "
          "settlement is 1 culture point, a city 2, and a tribe reaches its apex "
          "at 4 culture points (the 1st and 2nd tribes) — the moment it does, it "
          "declines: you remove all your roads, cover that tribe's settlements "
          "and cities with thickets (they keep producing but can never expand or "
          "upgrade, and a tribe may build only one city), and found the next "
          "tribe by placing one free settlement elsewhere, which ends your turn. "
          "The third tribe's apex is 3 culture points. Turn on 'Third-tribe "
          "victory' to end the game on it.",
          group=EXPANSION, suggests_victory_target=11),
    _bool("overbuild_ruins", "scenario", "Overbuild ruins", False,
          "Catan Histories: Rise of the Inkas (Teuber, 2018), rulebook "
          "'Consequences of Decline / Rebuilding' p. 7",
          "Rise of the Inkas. An active tribe may build a settlement over an "
          "opponent's declining (thicket-covered) building: build a road up to "
          "it, pay a settlement's cost, and the old settlement or city and its "
          "thicket go back to their owner's supply, replaced by your own "
          "settlement. Needs Tribe decline, which is what covers a building with "
          "a thicket in the first place.",
          group=EXPANSION, suggests_victory_target=11),
    _bool("third_tribe_victory", "victory", "Third-tribe victory", False,
          "Catan Histories: Rise of the Inkas (Teuber, 2018), rulebook 'Game "
          "End' p. 8 (11 culture markers total: 4 + 4 + 3)",
          "Rise of the Inkas. The game is won not by a point threshold but by "
          "the first player to bring their third tribe to its cultural apex (3 "
          "culture points, 11 markers in all). The plain point-total win is "
          "switched off while this is on. Needs Tribe decline, which is what "
          "gives a player a third tribe to complete.",
          group=EXPANSION, suggests_victory_target=11),
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
    # Every one of these acts on ships. Without them the board has no sea edges
    # at all, so the pirate would sit where nothing can be blocked, the trade
    # route would be the Longest Road under another name, and no island beyond
    # the one everybody started on could ever be reached.
    "ship_movement": ("ships",),
    "pirate": ("ships",),
    "longest_trade_route": ("ships",),
    "island_victory_points": ("ships",),
    # The desert belt only matters as a barrier because reaching the region it
    # cuts off is worth special points; without the island bonus there is
    # nothing to score, so the two are ticked together or not at all.
    "desert_regions": ("island_victory_points",),
    # The Fog Islands' fog hexes lie out in the sea and are reached across water,
    # so without ships there is no way to sail to one and reveal it — the board
    # is islands separated by ocean.
    "fog_reveal": ("ships",),
    # The Forgotten Tribe's gift edges are the coasts of small islands out in the
    # sea; a gift is claimed by sailing a ship onto one, so without ships nothing
    # can ever be claimed.
    "coast_gifts": ("ships",),
    # The Cloth for Catan villages are on small islands out in the sea, and a
    # village pays cloth only to a settlement it is joined to by a shipping
    # route; with no ships there is no route to reach one, so cloth can never be
    # earned.
    "cloth_villages": ("ships",),
    # The Wonders of Catan is a Seafarers scenario: its board is a main island
    # ringed by small islands out at sea, the Monument's requirement counts a
    # trade route of ships, and the small-island bonus is scored by sailing to
    # them, so the whole scenario needs ships. The small-island bonus can be
    # ticked on its own map, but it too is only reachable by sea.
    "wonders": ("ships",),
    "wonder_island_points": ("ships",),
    # The Pirate Islands. Warships are converted ships, so there must be a ship to
    # turn on its side; the fortresses are fought and recaptured with warships, so
    # the fortress rule needs the warship rule (and, through it, ships). The fleet
    # can move and raid with no warships at all — you simply always lose — so it
    # stands alone.
    "pirate_warships": ("ships",),
    "pirate_fortresses": ("pirate_warships",),
    # Explorers & Pirates. Transport ships are built and moved from harbor
    # settlements, so nothing in the transport system means anything without
    # them; the pirate charges its tribute in gold; missions need their tracks
    # container and the pieces each mission is delivered with.
    "transport_ships": ("harbor_settlements",),
    "movement_phase": ("transport_ships",),
    "ships_explore": ("transport_ships",),
    "cargo_settlers": ("transport_ships", "harbor_settlements"),
    "crews": ("transport_ships", "harbor_settlements"),
    "pirate_ship_instead_of_robber": ("gold",),
    "chase_pirate": ("pirate_ship_instead_of_robber", "transport_ships"),
    "mission_pirate_lairs": ("missions", "crews"),
    "mission_fish": ("missions", "transport_ships"),
    "mission_spices": ("missions", "crews"),
    # Traders & Barbarians, The Fishermen of Catan. The fish sources and the old
    # boot are all worked in fish tokens: a fishing ground, the lake or the boot
    # with no token supply to draw from or spend into does nothing, so each needs
    # the container rule that owns the supply and the spend ladder.
    "fishing_grounds": ("fish_tokens",),
    "lake_hex": ("fish_tokens",),
    "old_boot": ("fish_tokens",),
    # Traders & Barbarians, The Rivers of Catan. The river coin grants and the
    # two scoring tiles are all worked in gold coins: with no coin currency to
    # pay into or measure, a river settlement earns nothing and neither tile can
    # ever be held. Bridges are the exception — they pay coins but are really a
    # road piece for the Longest Road, so they turn on the river map's crossing
    # sites, not on `gold_coins`.
    "river_gold": ("gold_coins",),
    "wealthiest_settler": ("gold_coins",),
    "poor_settler": ("gold_coins",),
    # Traders & Barbarians, Barbarian Attack. The war pays its compensation and
    # its buy-a-resource in gold coins, and it trains its knights from the
    # scenario's own 26-card deck; with no coin economy and no deck to draw a
    # Knighthood from, the scenario cannot be played, so it needs both.
    "barbarian_attack": ("gold_coins", "barbarian_attack_deck"),
    # Traders & Barbarians, the main scenario. The wagon run is paid in gold
    # coins and draws its Swift Journey and Knight cards from the scenario's own
    # 26-card deck, so it needs both. The baggage-train card and the path
    # barbarians are meaningless without a wagon to move, so each needs the run.
    "trade_caravans": ("gold_coins", "trade_dev_deck"),
    "baggage_train": ("trade_caravans",),
    "roaming_barbarians": ("trade_caravans",),
    # CATAN - The Helpers. Every advantage acts through a tile a player holds,
    # and the framework rule is what deals, holds and cycles those tiles; an
    # advantage with no framework is a tile nobody ever draws, so each needs it.
    "helper_forced_trade": ("helper_tiles",),
    "helper_makeshift_road": ("helper_tiles",),
    "helper_resource_compensation": ("helper_tiles",),
    "helper_move_road": ("helper_tiles",),
    "helper_protection_from_seven": ("helper_tiles",),
    "helper_dev_card_choice": ("helper_tiles",),
    "helper_take_from_leader": ("helper_tiles",),
    "helper_knight_to_building": ("helper_tiles",),
    "helper_trade_frenzy": ("helper_tiles",),
    "helper_chase_robber": ("helper_tiles",),
    "helper_take_robber_resource": ("helper_tiles",),
    "helper_dev_card_swap": ("helper_tiles",),
    # Catan: Oil Springs. Everything that uses, sequesters or spends oil is
    # meaningless without oil to hold, so each needs the production rule that
    # brings oil into the game.
    "disaster_track": ("oil_tokens",),
    "oil_sequester_vp": ("oil_tokens",),
    "oil_metropolis": ("oil_tokens",),
    # Catan: Frenemies. The guild hall spends favour tokens; with no bag to earn
    # from there is nothing to redeem or exchange, so it needs the earn rule.
    "guild_hall": ("favour_tokens",),
    # Rise of the Inkas. Overbuilding replaces a thicket-covered building, and
    # only tribe decline ever covers one; the third-tribe win needs a third tribe
    # to complete, and only decline gives a player one. Both are meaningless
    # without the decline machinery, so each needs it.
    "overbuild_ruins": ("tribe_decline",),
    "third_tribe_victory": ("tribe_decline",),
}

# Rules that contradict or subsume one another: at most one member of a group
# may be on. Unlike DEPENDENCIES (A needs B), these are refused *and* the lobby
# auto-unchecks a rival when its partner is ticked. `reason` is shown to the
# player so an auto-uncheck is never silent.
EXCLUSIONS = [
    {
        "id": "longest_line_award",
        "rules": ("longest_road_card", "longest_trade_route"),
        "kind": "hard",
        "reason": (
            "Both award the one Longest Road / Trade Route card. The Trade "
            "Route counts ships as well as roads and replaces the roads-only "
            "Longest Road — a table plays one or the other, not both."
        ),
    },
    # Seafarers ships form routes and count for the trade route; Explorers &
    # Pirates transport ships carry cargo and form none. They are one physical
    # piece (`edge.ship`) read two opposite ways on the same board, so a table
    # picks one sea system, not both (the owner accepted this refusal as Risk 1
    # of the E&P plan rather than build a unified ship model).
    #
    # Only `ships` is named against `transport_ships`, not the whole Seafarers
    # stack: `ship_movement` and `longest_trade_route` both DEPEND on `ships`
    # (above), so they can never be on without it. Listing all four would make
    # this a clique — Seafarers itself has ships, moving them and the trade
    # route all on at once — which the "at most one member" rule would refuse.
    # Excluding `transport_ships` from `ships` alone refuses every reachable
    # both-on state and leaves the Seafarers stack coherent.
    {
        "id": "sea_ship_model",
        "rules": ("transport_ships", "ships"),
        "kind": "hard",
        "reason": (
            "Seafarers ships (with moving them and the Longest Trade Route) "
            "form routes; Explorers & Pirates transport ships carry cargo and "
            "form none. They are one physical piece read two opposite ways on "
            "the same board — pick one sea system."
        ),
    },
    # Explorers & Pirates gold and Traders & Barbarians gold coins are two
    # economies on one `Player.gold` field: E&P gold pays a 1-gold empty-roll
    # bonus and sells at 3:1, T&B coins pay neither bonus and sell at 4:1 (3:1
    # only with the matching harbour). A board that ran both would apply one
    # rule's rates to the other's coins, so a table picks one.
    {
        "id": "gold_economy",
        "rules": ("gold", "gold_coins"),
        "kind": "hard",
        "reason": (
            "Explorers & Pirates gold and Traders & Barbarians gold coins both "
            "live in one purse but earn and sell at different rates — E&P pays "
            "an empty-roll bonus and sells at 3:1, T&B sells at 4:1 and pays no "
            "bonus. Pick one gold economy."
        ),
    },
    # A gold hex pays one thing on its roll. The Explorers & Pirates `gold`
    # field pays 2 gold coins per building (a currency); the Seafarers
    # `gold_field_choice` field pays resources of the owner's choice from the
    # bank. Both read `context['terrain'] == 'gold'` in the production fold, so
    # with both on a hex would try to pay a coin and a card of choice at once.
    # A table picks one gold field, not both.
    {
        "id": "gold_field_yield",
        "rules": ("gold", "gold_field_choice"),
        "kind": "hard",
        "reason": (
            "The Explorers & Pirates gold field pays 2 gold coins per building "
            "and the Seafarers gold field pays resources of your choice from the "
            "bank — a hex pays one or the other on its roll, not both. Pick one."
        ),
    },
    # The Cities & Knights barbarian ship and the Barbarian Attack coastal war
    # are two different knight-and-barbarian systems on one board — the C&K ship
    # is measured against your cities on a track, the Barbarian Attack figures
    # sit on the coast and are fought off by knight pieces at the castle. They
    # share no state and no code path but cannot coexist coherently, so a table
    # picks one. Only `knights` is named against `barbarian_attack`, not the
    # whole C&K stack: C&K `barbarians` DEPENDS on `knights`, so a both-on state
    # is unreachable without `knights`, and excluding it alone refuses every
    # reachable clash while leaving C&K's own knights+barbarians coherent — the
    # same shape the ships exclusion uses above.
    {
        "id": "knight_and_barbarian_system",
        "rules": ("barbarian_attack", "knights"),
        "kind": "hard",
        "reason": (
            "Two knight-and-barbarian systems on one board — the Cities & "
            "Knights barbarian ship measured against your cities, and the "
            "Barbarian Attack figures on the coast fought off by knights at the "
            "castle. Pick one."
        ),
    },
    # One development deck per board. The Barbarian Attack deck, the Traders &
    # Barbarians main-scenario wagon deck and the Cities & Knights progress decks
    # each replace the base deck outright, so a board runs at most one of them.
    {
        "id": "scenario_dev_deck",
        "rules": ("barbarian_attack_deck", "trade_dev_deck", "progress_cards"),
        "kind": "hard",
        "reason": (
            "The Barbarian Attack deck, the Traders & Barbarians wagon deck and "
            "the Cities & Knights progress decks each replace the base "
            "development deck outright — a board deals one deck, not two. Pick "
            "one."
        ),
    },
    # The main-scenario path barbarians and the Cities & Knights knights are two
    # unrelated barbarian systems on one board — the roaming barbarians block a
    # wagon on the paths, the C&K knights defend cities from the barbarian ship.
    # As with `barbarian_attack` above, only `knights` is named: C&K
    # `barbarians` DEPENDS on `knights`, so excluding `knights` alone refuses
    # every reachable clash while leaving the C&K stack coherent.
    {
        "id": "roaming_barbarian_knight_system",
        "rules": ("roaming_barbarians", "knights"),
        "kind": "hard",
        "reason": (
            "Two unrelated barbarian systems on one board — the roaming "
            "barbarians that block your wagon on the paths, and the Cities & "
            "Knights knights that defend your cities from the barbarian ship. "
            "Pick one."
        ),
    },
    # The two Traders & Barbarians barbarian systems cannot share a board: the
    # coastal war's figures land on hexes and are fought by castle knights, while
    # the main scenario's roaming barbarians sit on paths and block wagons.
    {
        "id": "tb_barbarian_system",
        "rules": ("roaming_barbarians", "barbarian_attack"),
        "kind": "hard",
        "reason": (
            "Two Traders & Barbarians barbarian systems on one board — the "
            "Barbarian Attack figures on the coast fought off by castle knights, "
            "and the main-scenario barbarians that sit on the paths and block "
            "wagons. Pick one."
        ),
    },
]

EXCLUSIONS_BY_RULE = {
    rule_id: group
    for group in EXCLUSIONS
    for rule_id in group["rules"]
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

# The Explorers & Pirates rules that need the expansion's own state object —
# the per-player pirate hexes, the mission tracks with their markers and lead
# cards, the hidden-tile pool and reveal order, and the token supplies. Gold,
# harbor settlements and cargo live on the players and the board, so, like
# commodities, they need no container.
EP_STATE_RULES = (
    "ships_explore",
    # Seafarers' The Fog Islands reuses the hidden-tile pool, the per-region
    # number-token stacks and the reveal record that live on this container, so a
    # fog table needs it exactly as an exploring Explorers & Pirates one does.
    "fog_reveal",
    "pirate_ship_instead_of_robber",
    "chase_pirate",
    "missions",
    "mission_pirate_lairs",
    "mission_fish",
    "mission_spices",
)

# The Traders & Barbarians rules that need their own state object — the
# face-down fish-token supply, each player's private fish hand, and who holds the
# old boot. `robber_starts_off_board` decides only where the robber begins and
# needs no container, exactly as gold and harbour settlements do not.
TB_STATE_RULES = (
    "fish_tokens",
    "fishing_grounds",
    "lake_hex",
    "old_boot",
    # The Caravans keep the camel positions, the caravan chains and the open
    # voting round in the same container — see game/tb.py.
    "caravans",
    # Barbarian Attack keeps the per-hex barbarian counts, the knight pieces on
    # their paths, each player's prisoners, the conquered hexes and the scenario
    # deck in the same container — see game/tb.py.
    "barbarian_attack",
    "barbarian_attack_deck",
    # The main scenario keeps each player's wagon and carried commodity, the
    # baggage-train levels, the trade-hex commodity stacks and the path-barbarian
    # positions in the same container — see game/tb.py.
    "trade_caravans",
    "baggage_train",
    "roaming_barbarians",
    "trade_dev_deck",
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


# The five Explorers & Pirates scenarios, built up the way the rulebook teaches
# them: each is the one before it plus a mechanic or two. Every scenario drops
# the Longest Road and Largest Army cards (840), trades with the bank at 3:1
# (856), gives each player three ships (849) and 2 starting gold (1045), and
# suggests the scenario's own victory target — which the lobby can still change.
EP_LAND_HO_RULES = {
    "harbor_settlements": True,
    "transport_ships": True,
    "ships_explore": True,
    "cargo_settlers": True,
    "movement_phase": True,
    "gold": True,
    "no_dev_cards": True,
    "no_city_upgrades": True,
    "longest_road_card": False,
    "largest_army_card": False,
    "bank_trade_rate": 3,
    "max_ships": 3,
    "starting_gold": 2,
    "victory_target": 8,
}

EP_PIRATE_LAIRS_RULES = {
    **EP_LAND_HO_RULES,
    "crews": True,
    "pirate_ship_instead_of_robber": True,
    "chase_pirate": True,
    "missions": True,
    "mission_pirate_lairs": True,
    "victory_target": 12,
}

EP_FISH_RULES = {
    **EP_PIRATE_LAIRS_RULES,
    "mission_fish": True,
    "victory_target": 15,
}

# 1071: the Pirate Lairs hexes and mission are removed for Spices.
EP_SPICES_RULES = {
    **EP_FISH_RULES,
    "mission_pirate_lairs": False,
    "mission_spices": True,
    "victory_target": 15,
}

EXPLORERS_AND_PIRATES_RULES = {
    **EP_SPICES_RULES,
    "mission_pirate_lairs": True,
    # Deal the built-in Pirate Cove scenario board — a home harbour, open water
    # and fog to explore. Without a scenario map E&P's harbour settlements,
    # discovery and missions have nothing to act on. board_layout must be
    # 'custom' or the lobby ignores board_map entirely.
    "board_layout": "custom",
    "board_map": "pirate-cove",
    "victory_target": 17,
}


# Traders & Barbarians, The Fishermen of Catan. Ticks the scenario's five rules
# and points the table at the built-in Fishermen board so one click deals a
# playable game. The scenario plays to 10 — the base target (522) — with the old
# boot raising its holder's own threshold to 11 in the engine, so nothing is
# added to `victory_target` here.
TB_FISHERMEN_RULES = {
    "fish_tokens": True,
    "fishing_grounds": True,
    "lake_hex": True,
    "old_boot": True,
    "robber_starts_off_board": True,
    "board_layout": "custom",
    "board_map": "fishermen",
    "victory_target": 10,
}


# Traders & Barbarians, The Rivers of Catan. Ticks the coin economy, the river
# grants, bridges and the two scoring tiles, and points the table at the built-in
# Rivers board. Played to 10 (566) — the base target — so nothing is added to
# `victory_target`; the Harbormaster variant would raise it to 11, which the
# lobby can still do by hand.
TB_RIVERS_RULES = {
    "gold_coins": True,
    "river_gold": True,
    "bridges": True,
    "wealthiest_settler": True,
    "poor_settler": True,
    "board_layout": "custom",
    "board_map": "rivers",
    "victory_target": 10,
}


# Traders & Barbarians, The Caravans. Ticks the one container rule and points the
# table at the built-in Caravans board (an oasis at the centre with three arrows).
# Played to 12 (602) — the target the rule suggests; the Harbormaster variant
# would raise it to 13, which the lobby can still do by hand.
TB_CARAVANS_RULES = {
    "caravans": True,
    "board_layout": "custom",
    "board_map": "caravans",
    "victory_target": 12,
}


# Traders & Barbarians, Barbarian Attack. Ticks the coastal war, its 26-card
# deck and the coin economy, starts each player with a city in place of the
# second settlement (695/620 — the existing setup_second_city rule), drops the
# Largest Army card the scenario does not use, and points the table at the
# built-in castle board. Played to 12 (669) — the target the rule suggests; the
# Harbormaster variant would raise it to 13, which the lobby can still do by
# hand.
TB_BARBARIAN_ATTACK_RULES = {
    "barbarian_attack": True,
    "barbarian_attack_deck": True,
    "gold_coins": True,
    "setup_second_city": True,
    "largest_army_card": False,
    "board_layout": "custom",
    "board_map": "barbarian-attack",
    "victory_target": 12,
}


# Traders & Barbarians, the main scenario. Ticks the wagon run, the baggage
# train, the roaming barbarians, the scenario deck and the coin economy; starts
# each player with a city in place of the second settlement (695 — the existing
# setup_second_city rule), drops the Longest Road card the scenario does not use
# (693), re-rolls 2s and 12s (739 — the existing no_two_or_twelve dice set), and
# points the table at the built-in trade-hex board. Played to 13 (749) — the
# target the wagon rule suggests; the Harbormaster variant would raise it to 14,
# which the lobby can still do by hand.
TB_MAIN_RULES = {
    "trade_caravans": True,
    "baggage_train": True,
    "roaming_barbarians": True,
    "trade_dev_deck": True,
    "gold_coins": True,
    "setup_second_city": True,
    "longest_road_card": False,
    "dice_set": "no_two_or_twelve",
    "board_layout": "custom",
    "board_map": "traders-barbarians",
    "victory_target": 13,
}


# Seafarers, The Wonders of Catan. Ticks ships and moving them, the two wonder
# rules and the small-island bonus, keeps the pirate off (the scenario does not
# use it, p. 28), restricts starting settlements to the main island, drops the
# roads-only Longest Road for the Longest Trade Route the sea game awards, and
# points the table at the built-in Wonders board. The alternate win is 10 points
# with the highest wonder level, so the target is suggested at 10; the lobby can
# still change it.
WONDERS_OF_CATAN_RULES = {
    "ships": True,
    "ship_movement": True,
    "longest_road_card": False,
    "longest_trade_route": True,
    "wonders": True,
    "wonder_island_points": True,
    "start_on_main_land": True,
    "board_layout": "custom",
    "board_map": "wonders-of-catan",
    "victory_target": 10,
}


# Seafarers, The Pirate Islands. Ticks ships and moving them, the roaming pirate
# fleet, warships and the fortresses; restricts starting settlements to the
# eastern main island (p. 21); drops the Longest Trade Route and Largest Army the
# scenario sets aside (p. 20) — the roads-only Longest Road is off in a ship game
# too; and points the table at the built-in Pirate Islands board. There is no
# robber, gated off the fleet rule. The alternate win is recapturing your fortress
# with 10 points, so the target is suggested at 10; the lobby can still change it.
PIRATE_ISLANDS_RULES = {
    "ships": True,
    "ship_movement": True,
    "pirate_fleet": True,
    "pirate_warships": True,
    "pirate_fortresses": True,
    "start_on_main_land": True,
    "longest_road_card": False,
    "largest_army_card": False,
    "board_layout": "custom",
    "board_map": "pirate-islands",
    "victory_target": 10,
}


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
        "id": "seafarers",
        "name": "Seafarers",
        "source": "Seafarers rulebook; expansions.md 33-131",
        "summary": (
            "Ships, moving them, the pirate, the Longest Trade Route in place "
            "of the Longest Road, and special points for settling a new "
            "island. The scenarios play to more than 10 points, so the target "
            "is raised to 14 as 'Heading for New Shores' asks."
        ),
        "rules": {
            # 'Heading for New Shores' deals a sea board, not the landlocked
            # standard one — bind it so picking Seafarers plays a Seafarers board.
            "board_layout": "custom",
            "board_map": "large-island",
            "ships": True,
            "ship_movement": True,
            "pirate": True,
            # The Trade Route replaces the roads-only Longest Road; leaving the
            # base card on too is the both-on state the exclusion model refuses.
            "longest_road_card": False,
            "longest_trade_route": True,
            "island_victory_points": True,
            "victory_target": 14,
        },
    },
    {
        "id": "four_islands",
        "name": "Seafarers: The Four Islands",
        "source": (
            "Seafarers 2021 rulebook, Scenario 2 'The Four Islands', pp. 11-12; "
            "expansions.md 118 (research §2.1)"
        ),
        "summary": (
            "The Seafarers scenario with no home continent: the four-islands "
            "board has no main land, so a player places their two starting "
            "settlements anywhere and the same island bonus that rewards a new "
            "shore rewards the first settlement on each foreign island. "
            "The rulebook ends the race at 13, so the target is suggested at 13; "
            "the lobby can still change it. Pick the Four Islands map — or its "
            "larger 4-Player variant at a four-player table."
        ),
        "rules": {
            "board_layout": "custom",
            "board_map": "four-islands",
            "ships": True,
            "ship_movement": True,
            "pirate": True,
            "longest_road_card": False,
            "longest_trade_route": True,
            "island_victory_points": True,
            "victory_target": 13,
        },
    },
    {
        "id": "fog_islands",
        "name": "Seafarers: The Fog Islands",
        "source": (
            "Seafarers 2021 rulebook, Scenario 3 'The Fog Islands', p. 14; "
            "expansions.md 119 (research §2.1)"
        ),
        "summary": (
            "The Seafarers scenario built around exploration: two islands start "
            "face-up and a band of fog hexes between them is dealt face-down. A "
            "ship or road reaching a fog hex reveals it — a producing land hex "
            "pays 1 resource of its type, a sea hex nothing. Discovery is the "
            "only twist: there are no special victory points for it, so unlike "
            "the other new-shore scenarios the island bonus is left off. The "
            "rulebook ends the race at 12, so the target is suggested at 12; the "
            "lobby can still change it. Pick the Fog Islands map."
        ),
        "rules": {
            "board_layout": "custom",
            "board_map": "fog-islands",
            "ships": True,
            "ship_movement": True,
            "pirate": True,
            "longest_road_card": False,
            "longest_trade_route": True,
            "fog_reveal": True,
            "gold_field_choice": True,
            "victory_target": 12,
        },
    },
    {
        "id": "through_the_desert",
        "name": "Seafarers: Through the Desert",
        "source": (
            "Seafarers 2021 rulebook, Scenario 4 'Through the Desert', p. 17; "
            "expansions.md 125-127 (research §2.1)"
        ),
        "summary": (
            "The Seafarers scenario whose island is split by a belt of desert: "
            "the same island bonus that rewards a new shore rewards the first "
            "settlement in each foreign area, and the desert-regions rule makes "
            "the land strip beyond the desert one such area alongside the outer "
            "islands. The rulebook ends the race at 14, so the target is "
            "suggested at 14; the lobby can still change it. Pick the Through "
            "the Desert map."
        ),
        "rules": {
            "board_layout": "custom",
            "board_map": "through-the-desert",
            "ships": True,
            "ship_movement": True,
            "pirate": True,
            "longest_road_card": False,
            "longest_trade_route": True,
            "island_victory_points": True,
            "desert_regions": True,
            "gold_field_choice": True,
            "victory_target": 14,
        },
    },
    {
        "id": "forgotten_tribe",
        "name": "Seafarers: The Forgotten Tribe",
        "source": (
            "Seafarers 2021 rulebook, Scenario 5 'The Forgotten Tribe', p. 20; "
            "expansions.md 128-131 (research §2.1)"
        ),
        "summary": (
            "The Seafarers scenario built around gifts: the small islands around "
            "the main land carry marked coast edges, and sailing a ship onto one "
            "claims its gift — a 1-VP Catan chit, a development card, or a harbour "
            "you place at one of your own coastal settlements. All six harbours "
            "arrive as gifts; none start on the board. The barren islands cannot "
            "be built on and the robber may not move to them. The rulebook ends "
            "the race at 13, so the target is suggested at 13; the lobby can still "
            "change it. Pick the Forgotten Tribe map."
        ),
        "rules": {
            "board_layout": "custom",
            "board_map": "forgotten-tribe",
            "ships": True,
            "ship_movement": True,
            "pirate": True,
            "longest_road_card": False,
            "longest_trade_route": True,
            "coast_gifts": True,
            "no_build_barren_islands": True,
            "robber_avoids_barren_islands": True,
            "victory_target": 13,
        },
    },
    {
        "id": "cloth_for_catan",
        "name": "Seafarers: Cloth for Catan",
        "source": (
            "Seafarers 2021 rulebook, Scenario 6 'Cloth for Catan', p. 22; "
            "research §2.1"
        ),
        "summary": (
            "The Seafarers scenario built around trade: the small islands carry "
            "villages, and connecting one to a settlement by a shipping route "
            "earns cloth — a bolt on the connection and a bolt each time the "
            "village number is rolled, until its supply runs out. Every two "
            "bolts are worth a victory point. No victory points are awarded for "
            "the Longest Trade Route, so both line awards are left off, and "
            "players start with a third settlement. The barren islands cannot be "
            "built on and the robber may not move to them. The rulebook ends the "
            "race at 14, so the target is suggested at 14; the lobby can still "
            "change it. Pick the Cloth for Catan map."
        ),
        "rules": {
            "board_layout": "custom",
            "board_map": "cloth-for-catan",
            "ships": True,
            "ship_movement": True,
            "pirate": True,
            # No line award at all: the rulebook awards no points for the
            # Longest Trade Route, and the roads-only Longest Road is not in a
            # ship scenario either.
            "longest_road_card": False,
            "longest_trade_route": False,
            "cloth_villages": True,
            "setup_third_settlement": True,
            "no_build_barren_islands": True,
            "robber_avoids_barren_islands": True,
            "victory_target": 14,
        },
    },
    {
        "id": "oil_springs",
        "name": "Catan: Oil Springs",
        "source": (
            "Catan: Oil Springs (Erik Assadourian & Ty Hansen, 2011/2015), "
            "coilspringsgb_2015_web.pdf, 3-4 player rules pp. 1-2"
        ),
        "summary": (
            "Oil has been discovered on Catan. Three hexes carry Oil Spring "
            "tiles whose buildings produce oil, a sixth commodity. Oil converts "
            "into resources and upgrades cities into flood-proof metropolises, "
            "but every fifth oil used triggers a disaster: a 7 floods the coasts, "
            "otherwise a hex is polluted and loses its number, and the board dies "
            "at five lost tokens. Sequestering oil scores victory points and the "
            "Champion of the Environment token. The rulebook ends the race at 12, "
            "so the target is suggested at 12; the lobby can still change it. "
            "Pick the Oil Springs map."
        ),
        "rules": {
            "board_layout": "custom",
            "board_map": "oil-springs",
            "oil_tokens": True,
            "disaster_track": True,
            "oil_sequester_vp": True,
            "oil_metropolis": True,
            "victory_target": 12,
        },
    },
    {
        "id": "wonders_of_catan",
        "name": "Seafarers: The Wonders of Catan",
        "source": (
            "Seafarers 2021 rulebook, Scenario 8 'The Wonders of Catan', "
            "pp. 26-29; catan-expansions-research.md §2.1"
        ),
        "summary": (
            "The Seafarers scenario built around a race to raise a Wonder: each "
            "player picks one of five — Cathedral, Great Bridge, Great Wall, "
            "Monument or Theater — starts it once its requirement is met, and no "
            "two players may build the same one. Every Wonder has four levels, "
            "each costing five resources. Win by finishing a Wonder or by reaching "
            "10 points with a strictly higher wonder level than every opponent. A "
            "settlement on a small island is worth a special point, the pirate is "
            "not used, and starting settlements go on the main land. The rulebook "
            "ends the race at 10, so the target is suggested at 10; the lobby can "
            "still change it. Pick the Wonders of Catan map."
        ),
        "rules": dict(WONDERS_OF_CATAN_RULES),
    },
    {
        "id": "pirate_islands",
        "name": "Seafarers: The Pirate Islands",
        "source": (
            "Seafarers 2021 rulebook, Scenario 7 'The Pirate Islands', pp. 20-22"
        ),
        "summary": (
            "The largest Seafarers scenario: pirates hold four fortresses on the "
            "western islands and a roaming enemy fleet circles the two central "
            "desert islands clockwise, sailing the lower die each roll and raiding "
            "any coast it lands beside. Reveal Knight cards to turn ships into "
            "warships, fight the fleet and your own-colour fortress with dice, and "
            "win by recapturing your fortress while holding 10 points. There is no "
            "robber, no Longest Trade Route and no Largest Army. The rulebook ends "
            "the race at 10, so the target is suggested at 10; the lobby can still "
            "change it. Pick the Pirate Islands map."
        ),
        "rules": dict(PIRATE_ISLANDS_RULES),
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
    {
        "id": "tb_fishermen",
        "name": "The Fishermen of Catan",
        "source": "Catan: Traders & Barbarians rulebook, Scenario: The Fishermen "
                  "of Catan; expansions.md 489-526",
        "summary": (
            "Fishing grounds on the frame, a lake in place of the desert, the "
            "fish-token supply with its spend ladder, the old boot and the "
            "robber that starts off the board. Dealt on the built-in Fishermen "
            "map and played to 10 — 11 for whoever is stuck with the boot. "
            "Every switch it ticks stays one you can untick."
        ),
        "rules": dict(TB_FISHERMEN_RULES),
    },
    {
        "id": "tb_rivers",
        "name": "The Rivers of Catan",
        "source": "Catan: Traders & Barbarians rulebook, Scenario: The Rivers "
                  "of Catan; expansions.md 527-570",
        "summary": (
            "Rivers cross the island: settlements and roads built along them "
            "earn gold coins, bridges span the crossings, and the Wealthiest "
            "and Poor Settler tiles swing a victory point on who holds the most "
            "and fewest coins. Dealt on the built-in Rivers map and played to "
            "10. Every switch it ticks stays one you can untick."
        ),
        "rules": dict(TB_RIVERS_RULES),
    },
    {
        "id": "tb_caravans",
        "name": "The Caravans",
        "source": "Catan: Traders & Barbarians rulebook, Scenario: The Caravans; "
                  "expansions.md 571-606",
        "summary": (
            "Three caravans of camels grow out of a central oasis, decided by a "
            "voting round each time you build. A road on a camel's path counts "
            "double for the Longest Road, and a building between two camels is "
            "worth an extra point. Dealt on the built-in Caravans map and played "
            "to 12. The one switch it ticks stays one you can untick."
        ),
        "rules": dict(TB_CARAVANS_RULES),
    },
    {
        "id": "tb_barbarian_attack",
        "name": "Barbarian Attack",
        "source": "Catan: Traders & Barbarians rulebook, Scenario: Barbarian "
                  "Attack; expansions.md 607-676",
        "summary": (
            "Barbarians land on the coast whenever you build; you train knights "
            "at a central castle from the scenario's own 26-card deck and march "
            "them out to free the coast, banking two prisoners for each victory "
            "point. Each player starts with a city, there is no robber, and the "
            "Largest Army card is set aside. Dealt on the built-in castle map "
            "and played to 12. Every switch it ticks stays one you can untick."
        ),
        "rules": dict(TB_BARBARIAN_ATTACK_RULES),
    },
    {
        "id": "tb_main",
        "name": "Traders & Barbarians",
        "source": "Catan: Traders & Barbarians rulebook, Scenario: Traders & "
                  "Barbarians; expansions.md 677-755",
        "summary": (
            "The main scenario: drive your wagon between the castle, quarry and "
            "glassworks, delivering commodities for gold and a victory point "
            "each, upgrading your baggage train as you go. Three barbarians roam "
            "the paths and block your way, the scenario's own 26-card deck "
            "replaces the base deck, each player starts with a city, there is no "
            "robber and no Longest Road card, and 2s and 12s are re-rolled. Dealt "
            "on the built-in trade-hex map and played to 13. Every switch it "
            "ticks stays one you can untick."
        ),
        "rules": dict(TB_MAIN_RULES),
    },
    {
        "id": "explorers_and_pirates",
        "name": "Explorers & Pirates",
        "source": "Catan: Explorers & Pirates rulebook, Scenario: Explorers & "
                  "Pirates; expansions.md 1077-1084",
        "summary": (
            "The whole expansion in one: harbor settlements, transport ships, "
            "settlers, crews, discovery, gold, the pirate ship in place of the "
            "robber, and all three missions — Pirate Lairs, Fish for Catan and "
            "Spices for Catan. Played to 17 points. Every switch it ticks stays "
            "an individual rule you can untick — so a shorter game (the intro "
            "scenarios ran to 8–15 points) is a matter of turning missions or "
            "the pirate back off."
        ),
        "rules": dict(EXPLORERS_AND_PIRATES_RULES),
    },
    {
        "id": "helpers_of_catan",
        "name": "CATAN - The Helpers",
        "source": "Helpers_Rules.pdf (catan.com), the whole scenario",
        "summary": (
            "The twelve helper tiles and the framework that deals, holds and "
            "cycles them. Each player holds one one-shot helper, uses its "
            "advantage on their turn, then exchanges or flips it. No tile touches "
            "victory points, so it stays a 10-point game. Every advantage is a "
            "separate switch you can untick."
        ),
        "rules": {
            "helper_tiles": True,
            "helper_forced_trade": True,
            "helper_makeshift_road": True,
            "helper_resource_compensation": True,
            "helper_move_road": True,
            "helper_protection_from_seven": True,
            "helper_dev_card_choice": True,
            "helper_take_from_leader": True,
            "helper_knight_to_building": True,
            "helper_trade_frenzy": True,
            "helper_chase_robber": True,
            "helper_take_robber_resource": True,
            "helper_dev_card_swap": True,
        },
    },
    {
        "id": "frenemies",
        "name": "Catan: Frenemies",
        "source": (
            "Catan: Frenemies (Benjamin Teuber), "
            "catan_frenemies_rules_093012s.pdf, the 3-4 player rules"
        ),
        "summary": (
            "Altruism has gripped Catan. You earn blind-drawn favour tokens for "
            "pro-social acts — moving the robber harmlessly, gifting a resource "
            "to a player who is not ahead of you, and connecting your road "
            "network to an opponent's for the first time — and spend them at the "
            "guild hall for trades, resources, free roads, development cards or "
            "victory-point markers. Played on the base board to 11 points. Every "
            "switch it ticks stays one you can untick."
        ),
        "rules": {
            "favour_tokens": True,
            "guild_hall": True,
            "victory_target": 11,
        },
    },
    {
        "id": "rise_of_the_inkas",
        "name": "Catan Histories: Rise of the Inkas",
        "source": (
            "Catan Histories: Rise of the Inkas (Klaus & Benjamin Teuber, 2018), "
            "rulebook pp. 2-8 (5f-catan-rise-of-the-inkas-rulebook.pdf); "
            "catan-expansions-research.md"
        ),
        "summary": (
            "Three tribes rise and fall on a stretch of western South America: "
            "ocean and fishing grounds to the west, jungle to the east. Each "
            "player brings three successive tribes to their cultural apex — a "
            "settlement is 1 culture point, a city 2 — and the first two decline "
            "at 4 points each: your roads come off, your buildings are covered "
            "with thickets (they still produce but can never grow), and you found "
            "the next tribe with one free settlement. Opponents may build over "
            "your ruins. The third tribe wins at 3 points, 11 markers in all, so "
            "the target is suggested at 11; the lobby can still change it. The "
            "Longest Road and Largest Army award no points here. Pick the Rise of "
            "the Inkas map."
        ),
        "rules": {
            "board_layout": "custom",
            "board_map": "rise-of-the-inkas",
            "tribe_decline": True,
            "overbuild_ruins": True,
            "third_tribe_victory": True,
            # The Longest Trade Route and Mightiest Combat Arts grant a gameplay
            # advantage, not victory points, in this game (rulebook p. 5). The
            # advantage itself is not modelled; the point award is switched off.
            "longest_road_card": False,
            "largest_army_card": False,
            # Eight settlements, two cities, seven roads per player (rulebook
            # p. 4). The engine keeps a tribe's ruins on the board until its next
            # decline, so a little headroom on cities avoids a piece-starvation
            # stall; the one-city-per-tribe rule is what really caps them.
            "max_settlements": 8,
            "max_cities": 3,
            "max_roads": 7,
            "victory_target": 11,
        },
    },
]

PRESETS_BY_ID = {preset["id"]: preset for preset in PRESETS}


def card_system(chosen: dict) -> str:
    """Which card system this table plays.

    A rule set saved before this rule existed, or one carrying a value nobody
    recognises, falls back to the default — the published rule, which is what
    those games were already being played under.
    """
    rule = RULES_BY_ID["card_system"]
    value = chosen.get(rule["id"])
    if value in {option["id"] for option in rule["options"]}:
        return value
    return rule["default"]


def dev_deck_in_play(chosen: dict) -> bool:
    """Whether this table may buy and play development cards.

    Only the progress decks can close the development deck, and only when the
    table chose the published reading: two card systems at once is the house
    rule `card_system` calls "both". The Barbarian Attack deck replaces the base
    deck outright with its own 26 cards, so it closes the base deck too — the
    scenario's cards are bought and resolved through their own path, not through
    `buy_dev_card`.
    """
    if chosen.get("barbarian_attack_deck"):
        return False
    # The Traders & Barbarians wagon deck replaces the base deck the same way.
    if chosen.get("trade_dev_deck"):
        return False
    if not chosen.get("progress_cards"):
        return True
    return card_system(chosen) != "progress"


def progress_deck_in_play(chosen: dict) -> bool:
    """Whether the city gates deal progress cards at this table."""
    if not chosen.get("progress_cards"):
        return False
    return card_system(chosen) != "development"


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
            if rule.get("dynamic"):
                # The options are whatever is on disk at this instant, and this
                # module does not touch the disk. Accepting any well-formed id
                # is safe because it is only ever a lookup key: the map has to
                # be read and validated before a game can start on it, and
                # `_start_game_locked` refuses if it cannot be.
                from game import maps
                if isinstance(value, str) and maps.SLUG.match(value):
                    chosen[rule_id] = value
            elif value in {option["id"] for option in rule["options"]}:
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


def exclusion_problems(chosen: dict) -> list:
    """Groups with more than one member switched on, as sentences.

    Empty means coherent. Reported and refused the same way dependencies are;
    nothing is auto-unchecked server-side — the client does that live, and a
    payload that still arrives incoherent is refused, not quietly fixed.
    """
    problems = []
    for group in EXCLUSIONS:
        on = [rid for rid in group["rules"] if chosen.get(rid)]
        if len(on) > 1:
            names = " and ".join(RULES_BY_ID[rid]["name"] for rid in on)
            problems.append(f"{names} exclude each other: {group['reason']}")
    return problems


def needs_expansion_state(chosen: dict) -> bool:
    """Whether this rule set requires the Cities & Knights state object."""
    return any(chosen.get(rule_id) for rule_id in EXPANSION_STATE_RULES)


def needs_ep_state(chosen: dict) -> bool:
    """Whether this rule set requires the Explorers & Pirates state object."""
    return any(chosen.get(rule_id) for rule_id in EP_STATE_RULES)


def needs_tb_state(chosen: dict) -> bool:
    """Whether this rule set requires the Traders & Barbarians state object."""
    return any(chosen.get(rule_id) for rule_id in TB_STATE_RULES)


def catalogue() -> list:
    """The registry, for the lobby to render.

    `board_map`'s options are read off disk here rather than declared above, so
    a map saved a moment ago appears in the picker on the next broadcast. The
    import is inside the function on purpose: a rules registry that could not be
    imported without touching the filesystem would be felt by every test in the
    suite.
    """
    from game import map_store

    listed = []
    for rule in RULES:
        rule = dict(rule)
        if rule["id"] == "board_map":
            rule["options"] = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "summary": (
                        f"{row['hexes']} hexes, {row['regions']} regions, "
                        f"{row['islands']} island{'s' if row['islands'] != 1 else ''}"
                        + (" — has problems and cannot be played" if row["problems"] else "")
                    ),
                }
                for row in map_store.list_maps()
            ]
        listed.append(rule)
    return listed


def presets() -> list:
    """The one-click rule sets, for the lobby to offer as buttons."""
    return [dict(preset) for preset in PRESETS]


def exclusions() -> list:
    """The mutual-exclusion groups, for the lobby to decorate and enforce."""
    return [dict(group) for group in EXCLUSIONS]


def categories() -> list:
    """The functional sections, in display order, for the lobby to tree the picker.

    The client reads its section headers and their order from this, exactly as it
    reads the rules themselves from `catalogue()` — a category added here appears
    as a new collapsible section in every client with no front-end change.
    """
    return [dict(category) for category in CATEGORIES]
