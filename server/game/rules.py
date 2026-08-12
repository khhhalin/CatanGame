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
    # 0 is not "no limit": it means "whatever this server is configured with",
    # exactly as the clocks below do. A table that never opened the setting
    # keeps the deployment's own cap.
    _int("max_players", "Seats at the table", 0, 0, 6,
         "Base game rulebook (4 players); Catan 5-6 Player Extension rulebook "
         "(6, on the larger board)",
         "How many people may take a seat. The 5-6 player game needs a board "
         "with room for them - the large map or a custom one. 0 keeps this "
         "server's own default."),
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


# --- The clocks ---------------------------------------------------------
# One clock per phase of a turn, all of them the table's to set. Zero is not
# "no limit" — it means "whatever this server is configured with", which is
# what a table that never opened these settings gets. Nothing here is a
# rulebook number: the physical game has no clock at all, and these exist
# because an online table cannot wait for a player who closed their laptop.
RULES += [
    _int("dice_timer_seconds", "Dice roll clock", 0, 0, 600,
         "No published rule: an online table's replacement for a player who "
         "has walked away from the table",
         "How long a player has to roll before the server rolls for them. "
         "0 keeps this server's own default."),
    _int("discard_timer_seconds", "Discard clock", 0, 0, 600,
         "No published rule; the discard itself is base game rulebook (a 7 "
         "costs every hand over the limit half its cards)",
         "How long a player has to hand back half their hand after a 7 "
         "before the server discards at random for them. 0 keeps this "
         "server's own default."),
    _int("robber_timer_seconds", "Robber clock", 0, 0, 600,
         "No published rule; the move itself is base game rulebook (the "
         "robber is moved to another hex and one card is stolen)",
         "How long the roller of a 7 has to move the robber and pick a "
         "victim before the server does it for them. 0 keeps this server's "
         "own default."),
    _int("turn_timer_seconds", "Turn clock", 0, 0, 3600,
         "No published rule: an online table's replacement for a player who "
         "has walked away from the table",
         "How long the rest of a turn lasts once the roll — and any discard "
         "and robber move it caused — is settled. 0 keeps this server's own "
         "default."),
    # The one clock in this block whose zero means "no clock at all": there is
    # no deployment setting behind it to fall back to, and a table that never
    # wanted a trade timer is playing the physical game, where an offer stands
    # until it is taken or withdrawn.
    _int("trade_offer_seconds", "Trade offer clock", 0, 0, 600,
         "No published rule: the physical game leaves an offer on the table "
         "until it is taken or withdrawn, and this is the online table's "
         "stand-in for picking the cards back up",
         "How long an offer stays open for the rest of the table to accept "
         "before the server drops it. 0 leaves an offer standing until its "
         "proposer cancels it or somebody trades."),
    _int("choice_timer_seconds", "Decision clock", 0, 0, 600,
         "No published rule; the decisions themselves are the rules that ask "
         "for them (which city the barbarians sack, which card a Wedding "
         "takes)",
         "How long a player has to answer a decision the engine stopped to "
         "ask for before the server answers it for them. 0 keeps this "
         "server's own default."),
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
    _bool("epidemic", "Epidemic", False,
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
    _bool("chat_commands", "Chat commands", False,
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
    {
        "id": "card_system",
        "group": EXPANSION,
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
    _bool("setup_second_city", "Start with a city", False,
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
    _bool("ships", "Ships", False,
          "Seafarers rulebook, 'Ships'; expansions.md 35-56",
          "One wool and one lumber builds a ship on a sea edge, and a shipping "
          "route expands your network exactly as roads do. A ship may never "
          "share a hex side with a road, and the two networks only join where "
          "you have a settlement. This also gives the board its sea edges, so "
          "a second island can be reached at all.",
          group=EXPANSION),
    _bool("ship_movement", "Moving ships", False,
          "Seafarers rulebook, 'Moving Ships'; expansions.md 62-71",
          "One ship per turn may be picked up and re-laid anywhere you could "
          "build a new one, for free. Not a ship built this turn, not one whose "
          "both ends touch your other pieces — which is what a closed route "
          "between two of your settlements is — and never off a hex side the "
          "pirate is sitting beside.",
          group=EXPANSION),
    _bool("pirate", "The pirate", False,
          "Seafarers rulebook, 'The Pirate'; expansions.md 88-100",
          "A black ship the roller of a 7 may move instead of the robber. It "
          "sits on a sea hex, steals one card from a player with a ship beside "
          "it, and blocks every hex side around that hex: no ship may be built "
          "there and none may be moved away. It does not stop production.",
          group=EXPANSION),
    _bool("longest_trade_route", "Longest Trade Route", False,
          "Seafarers rulebook, 'The Longest Trade Route'; expansions.md 76-85",
          "Roads and ships count together for the 2-point card, replacing the "
          "roads-only Longest Road. A road and a shipping route only join into "
          "one route where their owner has a settlement or city at the "
          "intersection they meet on.",
          group=EXPANSION),
    _bool("start_on_main_land", "Start on the main land only", False,
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
    _bool("island_victory_points", "Special points for new islands", False,
          "Seafarers rulebook, 'Catan Chits'; expansions.md 121-122, 208-210",
          "Your first settlement on an island you did not start on scores "
          "special victory points on top of the point the settlement itself is "
          "worth. An island is worked out from the board — every stretch of "
          "land the sea cuts off from the rest is one — so the same rule fits "
          "any map.",
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
    _bool("movement_phase", "Movement phase", False,
          "Catan: Explorers & Pirates rulebook, 'Turn Structure'; expansions.md 851-862",
          "A turn runs production, then trade and build, then movement, in that "
          "fixed order. You may not trade or build once movement has begun — the "
          "one exception is founding a settlement with a settler ship.",
          group=EXPANSION),
    _bool("gold", "Gold", False,
          "Catan: Explorers & Pirates rulebook, 'Gold'; expansions.md 854, 960-967",
          "Gold is a second currency beside resources: you take 1 gold when a "
          "non-7 production roll pays you nothing, three identical resources buy "
          "1 gold, and twice a turn 2 gold buys any 1 resource. Gold trades with "
          "opponents like a resource card.",
          group=EXPANSION),
    _bool("no_dev_cards", "No development cards", False,
          "Catan: Explorers & Pirates rulebook, 'Fundamental Differences'; "
          "expansions.md 839",
          "No development cards exist — the deck cannot be bought from at all. "
          "Explorers & Pirates has no knight, progress or victory point "
          "development cards.",
          group=EXPANSION),
    _bool("no_city_upgrades", "No city upgrades", False,
          "Catan: Explorers & Pirates rulebook, 'Fundamental Differences'; "
          "expansions.md 838",
          "Settlements are never upgraded to cities and the city pieces are "
          "unused. A game scored on settlements, harbor settlements and missions "
          "instead.",
          group=EXPANSION),
    _bool("transport_ships", "Transport ships", False,
          "Catan: Explorers & Pirates rulebook, 'Ships and Movement'; "
          "expansions.md 864-882",
          "Ships are transports carrying pieces in a hold (1 large or 2 small) "
          "with movement points along sea routes; they never form routes. Built "
          "for 1 lumber and 1 wool on a sea route beside one of your harbor "
          "settlements.",
          group=EXPANSION),
    _bool("harbor_settlements", "Harbor settlements", False,
          "Catan: Explorers & Pirates rulebook, 'Harbor Settlements'; "
          "expansions.md 894-902",
          "Upgrade a coastal settlement (2 grain and 2 ore) into a harbor "
          "settlement worth 2 victory points with a cargo basin — the only site "
          "where ships, settlers and crews may be built. It yields 1, not 2, on "
          "production.",
          group=EXPANSION),
    _bool("ships_explore", "Ships explore", False,
          "Catan: Explorers & Pirates rulebook, 'Discovery'; expansions.md 883-893",
          "Moving a ship so one end points at an undiscovered hex reveals it, "
          "and that discovery ends the ship's movement for the turn.",
          group=EXPANSION),
    _bool("cargo_settlers", "Settlers", False,
          "Catan: Explorers & Pirates rulebook, 'Settlers'; expansions.md 903-918",
          "Settlers (a settlement's cost) are built into a basin or hold and "
          "carried by ship. A settler ship pointing at a free coastal corner "
          "founds a settlement there for free.",
          group=EXPANSION),
    _bool("crews", "Crews", False,
          "Catan: Explorers & Pirates rulebook, 'Crews'; expansions.md 919-928",
          "Crews (1 ore and 1 wool) ride ships and are landed on mission "
          "destinations only.",
          group=EXPANSION),
    _bool("transshipping", "Transshipping", False,
          "Catan: Explorers & Pirates rulebook, 'Transshipping'; expansions.md 929-932",
          "A loaded ship pointing at a loaded harbor settlement may swap the "
          "pieces between its hold and the basin.",
          group=EXPANSION),
    _bool("pirate_ship_instead_of_robber", "Pirate ship instead of the robber", False,
          "Catan: Explorers & Pirates rulebook, 'The Pirate Ship'; "
          "expansions.md 841, 843, 934-949",
          "The roller of a 7 places their own pirate ship on an allowed sea hex, "
          "steals 1 card from an opponent with a ship there, and thereafter "
          "charges every mover 1 gold tribute per ship crossing that hex. No "
          "robber, and no land is blocked.",
          group=EXPANSION),
    _bool("chase_pirate", "Chase the pirate", False,
          "Catan: Explorers & Pirates rulebook, 'Chasing the Pirate'; "
          "expansions.md 951-958",
          "A battle-ready ship — unmoved and next to the pirate's hex — may roll "
          "one die; a 6 chases the pirate away and lets the chaser reposition it "
          "and steal.",
          group=EXPANSION),
    _bool("missions", "Missions", False,
          "Catan: Explorers & Pirates rulebook, 'Missions in General'; "
          "expansions.md 969-978",
          "Mission tracks with a per-player marker each; a marker ahead of every "
          "other on a track holds that mission's 1-point lead card. The container "
          "for the three missions below.",
          group=EXPANSION),
    _bool("mission_pirate_lairs", "Mission: Pirate Lairs", False,
          "Catan: Explorers & Pirates rulebook, 'Pirate Lairs'; expansions.md 980-998",
          "Discover gold-field and pirate-lair hexes, land crews to capture "
          "lairs and advance the Pirate Lairs track. A captured lair's number "
          "pays 2 gold per adjacent building.",
          group=EXPANSION),
    _bool("mission_fish", "Mission: Fish for Catan", False,
          "Catan: Explorers & Pirates rulebook, 'Fish for Catan'; "
          "expansions.md 1000-1019",
          "Catch fish hauls at discovered shoal hexes and deliver them to the "
          "Council of Catan docks to advance the Fish track.",
          group=EXPANSION),
    _bool("mission_spices", "Mission: Spices for Catan", False,
          "Catan: Explorers & Pirates rulebook, 'Spices for Catan'; "
          "expansions.md 1021-1040",
          "Trade crews for spice sacks at village hexes — each village grants a "
          "permanent advantage — and deliver the sacks to the Council to advance "
          "the Spices track.",
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
    _int("max_ships", "Ships per player", 15, 1, 60,
         "Seafarers rulebook; expansions.md 51-52",
         "How many ships each player may have on the board at once.",
         group=EXPANSION),
    _int("island_points_per_island", "Points for a new island", 2, 1, 5,
         "Seafarers rulebook, 'Heading for New Shores'; expansions.md 121",
         "How many special victory points the first settlement on an island "
         "you did not start on is worth.",
         group=EXPANSION),
    # The Explorers & Pirates piece supplies (849): 4 harbor settlements, 2
    # settlers, 9 crews. Ships reuse the existing `max_ships`, which every E&P
    # preset sets to 3 rather than adding a second ships count.
    _int("max_harbor_settlements", "Harbor settlements per player", 4, 0, 20,
         "Catan: Explorers & Pirates rulebook; expansions.md 849",
         "How many harbor settlements each player may have standing at once.",
         group=EXPANSION),
    _int("max_settlers", "Settlers per player", 2, 0, 10,
         "Catan: Explorers & Pirates rulebook; expansions.md 849",
         "How many settlers each player may have at once.",
         group=EXPANSION),
    _int("max_crews", "Crews per player", 9, 0, 20,
         "Catan: Explorers & Pirates rulebook; expansions.md 849",
         "How many crews each player may have at once.",
         group=EXPANSION),
    _int("ship_movement_points", "Ship movement points", 4, 1, 12,
         "Catan: Explorers & Pirates rulebook, 'Ships and Movement'; expansions.md 874",
         "How many movement points a ship has each turn, before any wool or "
         "Swift Voyage bonus.",
         group=EXPANSION),
    _int("starting_gold", "Starting gold", 0, 0, 10,
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
    _bool("fish_tokens", "Fish tokens", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 501-516",
          "A face-down supply of fish tokens you draw, hold privately (cap 7) "
          "and spend by fish total for a benefit: 2 sends the robber off the "
          "board, 3 steals a random card, 4 takes a bank card, 5 builds a free "
          "road, 7 draws a free development card. No change is given; fish are "
          "never counted toward the hand limit, never discarded on a 7, never "
          "stolen and never traded. The container for the fish sources below.",
          group=EXPANSION),
    _bool("fishing_grounds", "Fishing grounds", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 495-499",
          "Fishing-ground tiles sit on the board frame; a settlement built on "
          "one of the three coastal intersections a tile touches draws 1 fish "
          "token, a city 2, whenever the tile's number (4/5/6/8/9/10) is rolled.",
          group=EXPANSION),
    _bool("lake_hex", "The lake", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 493, 500",
          "A lake replaces the desert (and never sits on the coast); a "
          "settlement adjacent to it draws 1 fish token, a city 2, whenever a "
          "2, 3, 11 or 12 is rolled.",
          group=EXPANSION),
    _bool("old_boot", "The old boot", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 517-521",
          "The old boot (mixed into the fish supply and revealed the moment it "
          "is drawn) raises its holder's personal winning threshold by 1. After "
          "rolling you may pass it to any player with as many victory points as "
          "you or more; the sole points leader must keep it.",
          group=EXPANSION),
    _bool("robber_starts_off_board", "Robber starts off the board", False,
          "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
          "expansions.md 496, 504",
          "The robber begins beside the board rather than on the desert and "
          "enters play only when the first 7 (or a knight) is rolled. Spending "
          "2 fish can send it back off the board.",
          group=EXPANSION),
]

RULES += [
    _int("max_fish_held", "Fish tokens in hand", 7, 1, 15,
         "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
         "expansions.md 510",
         "How many fish tokens a player may hold at once. A draw that would "
         "exceed the cap is not taken.",
         group=EXPANSION),
    _int("fishing_ground_count", "Fishing grounds on the board", 6, 0, 12,
         "Catan: Traders & Barbarians rulebook, 'The Fishermen of Catan'; "
         "expansions.md 492",
         "How many fishing-ground tiles the board frame carries.",
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
    # Every one of these acts on ships. Without them the board has no sea edges
    # at all, so the pirate would sit where nothing can be blocked, the trade
    # route would be the Longest Road under another name, and no island beyond
    # the one everybody started on could ever be reached.
    "ship_movement": ("ships",),
    "pirate": ("ships",),
    "longest_trade_route": ("ships",),
    "island_victory_points": ("ships",),
    # Explorers & Pirates. Transport ships are built and moved from harbor
    # settlements, so nothing in the transport system means anything without
    # them; the pirate charges its tribute in gold; missions need their tracks
    # container and the pieces each mission is delivered with.
    "transport_ships": ("harbor_settlements",),
    "movement_phase": ("transport_ships",),
    "ships_explore": ("transport_ships",),
    "cargo_settlers": ("transport_ships", "harbor_settlements"),
    "crews": ("transport_ships", "harbor_settlements"),
    "transshipping": ("transport_ships", "harbor_settlements"),
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
    "transshipping": True,
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
    "board_map": "fishermen",
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
    rule `card_system` calls "both".
    """
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
