# Catan Expansion Rules — Pick-and-Choose Catalogue

Every line below is a complete, standalone sentence, so any single rule can be
lifted out and implemented on its own. Pick the sections you want; nothing here
assumes you are implementing a whole expansion.

The current implementation is base-game only (hex board with ports, robber,
development cards, bank and player trading, longest road, largest army, turn
timers). Everything in this file is an addition to or a modification of that.

**Contents**

- [Seafarers](#seafarers) — ships, the pirate, gold fields, island scenarios
- [Cities & Knights](#cities--knights) — commodities, city improvements, knights, barbarians, progress cards
- [Traders & Barbarians](#traders--barbarians) — five scenarios plus four modular variants
- [Explorers & Pirates](#explorers--pirates) — ships as transport, exploration, missions
- [Mini-Expansions, Scenario Packs, and Official Variants](#mini-expansions-scenario-packs-and-official-variants) — 5-6 players, Helpers, Frenemies, Crop Trust, Treasures/Dragons/Adventurers, the two Legend campaigns, board setup variants

**Cheapest things to add first**, judged against what is already built:

- *The Friendly Robber* (Traders & Barbarians variants) — six rules, needs only a filter on legal robber hexes.
- *Harbormaster* (Traders & Barbarians variants) — eight rules, and ports already exist in the codebase.
- *Special Build Phase* (5-6 Player Extension) — pure turn-order change, no new pieces.
- *Gold fields* (Seafarers) — one new hex type plus a "choose your resource" prompt.
- *Fixed versus variable board setup* — the generator already exists; this only changes token placement order.

Rules were cross-checked against the official rulebooks (catan.com), catan.fandom.com,
and BoardGameGeek rules summaries. Where an edition differs, the current English
edition was used; legacy content is marked.

---

## Seafarers

### Ships
- A ship costs one wool and one lumber to build.
- A ship represents a segment of a shipping route rather than an individual vessel, in the same way a road represents a trade route rather than a cart.
- A ship must be placed on the boundary (hex side) between two hexes, exactly as a road is.
- A ship may only be placed on a hex side where at least one of the two adjacent hexes is a sea hex.
- A ship may never be placed on a hex side between two land hexes.
- A ship placed between two sea hexes forms an open-water route, and a ship placed between a sea hex and a land hex forms a coastal route.
- A new ship may be placed adjacent to any settlement or city the building player already owns on the coast.
- A new ship may alternatively be placed adjacent to any of the building player's ships already on the board.
- A player may branch their shipping routes freely, exactly as they may branch their roads.
- A player may not build a ship along a coastal hex side that already contains a road, and may not build a road along a coastal hex side that already contains a ship.
- A shipping route functions exactly like a road network for the purpose of expansion, so a player may build new pieces anywhere connected to their combined network of roads and ships.
- When a player's shipping route reaches a coastline, that player may build a settlement on that coast even if it lies on a new island.
- The distance rule from basic Catan applies to every settlement, including settlements built on newly reached islands.
- A settlement built on a new island may be used as a base for further expansion with new roads and new ships.
- Each player has fifteen ship pieces available in their colour.
- A player who runs out of ship pieces may not build any more ships until a ship becomes available again.

### Ships Versus Roads
- A ship may never be connected directly to a road, and a road may never be connected directly to a ship.
- A player may only join a land network of roads to a sea network of ships by building a settlement at the intersection where the two networks meet.
- Roads and ships may be built toward one another, but they remain separate networks until a settlement is built at the shared intersection.
- Two unconnected networks belonging to the same player are counted separately when determining the Longest Trade Route.
- Ships may be moved during the game, whereas roads may never be moved once built.

### Moving Ships
- A player may move at most one ship per turn, and only during that player's building phase.
- A player may not move a ship on the same turn on which that ship was built.
- When a player moves a ship, the ship's new position must satisfy all of the normal rules for placing a new ship.
- A player may only move a ship if at least one of that ship's two ends is not adjacent to any other piece belonging to that player.
- A ship may be moved to any hex side where its owner would be allowed to build a new ship.
- A ship that is part of a closed shipping route may never be moved, even if moving it would not break the connection between the two settlements.
- If a circular shipping route does not touch any of the owner's settlements or cities, every ship in that route counts as open and may be moved.
- If a shipping route leaves one settlement and returns to that same settlement without touching any other settlement or city, one ship at each end of that route counts as open.
- Moving a ship does not cost the owner any resources.

### Shipping Routes
- A closed shipping route is any unbroken line of ships that interconnects two of the owner's settlements and/or cities.
- An open shipping route is any shipping route that does not interconnect two of the owner's settlements or cities.
- A chain of connected ships of the same colour forms a single shipping route.

### The Longest Trade Route
- In Seafarers, players compete for the Longest Trade Route instead of the Longest Road.
- The Longest Trade Route special card is worth two victory points, exactly as the Longest Road card is in basic Catan.
- Both roads and ships count toward the length of a player's trade route, and both open and closed shipping routes are counted.
- The player with the longest continuous line of roads and/or ships receives the Longest Trade Route special card.
- A road and a shipping route only count as one continuous trade route if the player has a settlement or city at the intersection where the two meet.
- Only the single longest unbranched line of a player's roads and ships is counted when calculating the Longest Trade Route.
- A player who moves a ship does not lose the Longest Trade Route card as long as their continuous route remains at least as long after the move.
- All other Longest Road rules from basic Catan, including the minimum length of five segments and the rules for breaking an opponent's route, apply to the Longest Trade Route.

### The Pirate
- The pirate is a single black ship piece that is placed beside the board before the game begins.
- A player who rolls a seven may choose to move the pirate instead of moving the robber.
- A player who plays a knight card may choose to move either the robber or the pirate.
- The pirate may only be placed in the centre of a sea hex, never on a land hex.
- After moving the pirate, the active player steals one random resource card from any one player who has a ship adjacent to the pirate's new hex.
- If a player has more than one ship adjacent to the pirate's hex, the active player may still steal only one card from that player.
- No player may place a new ship on any hex side bordering the hex the pirate occupies.
- No ship on a hex side bordering the pirate's hex may be moved away from that position.
- The pirate does not block the production of any hex, and does not prevent the building of roads, settlements, or cities.
- The pirate does not affect harbours or trading with harbours.
- The pirate may not be placed adjacent to any ship during the initial set-up phase.
- In scenarios that contain no desert hex, the robber starts off the board just as the pirate does, and enters play when it is first moved.

### Starting With a Ship
- A player may place either or both of their starting settlements on the coastline.
- A player who places a starting settlement on the coast may place a ship instead of a road next to that settlement.

### Gold Fields
- A gold field is a terrain hex that produces gold, and there is no gold resource card in the game.
- Whenever the number on a gold field is rolled, each player collects resources for every settlement or city they own adjacent to that hex.
- A settlement adjacent to a producing gold field entitles its owner to one resource card, and a city entitles its owner to two resource cards.
- A player collecting from a gold field may choose any of the five normal resources, namely grain, lumber, ore, brick, and wool.
- A player collecting two cards from a gold field may take two of the same resource or two different resources, in any combination they wish.

### The Board and the Frame
- The board frame is assembled from the six Catan frame pieces turned to their all-sea sides plus the Seafarers frame pieces.
- The harbours printed on the reverse of the basic Catan frame pieces are not used in Seafarers scenarios.
- The smaller harbour tokens from the basic Catan game are not used when playing with the Seafarers expansion.
- Sea hexes are placed inside the frame exactly as the scenario diagram shows, and they never receive number tokens.
- Sea hexes never produce resources.
- Players may build ships on the inner edges of the frame pieces but never on the outer edges of the frame.
- Harbour tokens listed in a scenario are shuffled face down and placed one at a time at the positions shown in the scenario diagram.

### Catan Chits and Special Victory Points
- A Catan chit is a token that may serve as a special victory point, as a marker, or as a counter, depending on the scenario.
- A player who earns a special victory point takes a Catan chit and places it underneath the settlement or city that earned it, so that all players can see how the points were gained.
- Special victory points are earned in addition to the normal victory points a settlement or city provides.
- A settlement that has earned two special victory points is worth three victory points in total.

### The Road Building Development Card
- When playing the Road Building development card in Seafarers, the player may build two roads, two ships, or one road and one ship.

### Scenario: Heading for New Shores
- The game ends as soon as a player reaches fourteen victory points on their turn.
- Players build their first two settlements with roads or ships on the main island.
- Both the robber and the pirate are used in this scenario.
- The pirate starts on the sea hex marked with a pirate ship in the scenario diagram.
- In a four-player game the robber starts in the desert, and in a three-player game the robber starts on the hills hex marked with a twelve.
- Each time a player builds their first settlement on one of the small islands, that player receives two special victory points.
- A player may earn two special victory points for each different small island, regardless of whether other players have already settled that island.

### Scenario: The Four Islands
- The game ends as soon as a player reaches thirteen victory points on their turn.
- Each player may place their two starting settlements on any one island or on two different islands of their choice.
- The island or islands on which a player places their starting settlements are that player's home islands, and every other island is a foreign island to that player.
- When a player builds their first settlement on a foreign island, that player earns two special victory points.
- Additional settlements built on an island where a player has already earned special victory points do not earn any further special victory points.
- A player who starts with two home islands may earn at most four special victory points in this scenario.
- A player who starts with only one home island may earn at most six special victory points in this scenario.
- A player earns the special victory points even if another player has already settled that island, and even if the island is another player's home island.
- Both the robber and the pirate are used in this scenario, with the pirate starting on the sea hex marked with a pirate ship and the robber starting on the hex with a twelve.
- The five-to-six-player version of this scenario is called The Six Islands and uses the same additional rules.

### Scenario: The Fog Island
- The game ends as soon as a player reaches twelve victory points on their turn.
- There are no special victory point chits in this scenario.
- Players build their first two settlements with roads or ships on the upper island and/or the lower island.
- The empty hex spaces marked with question marks are filled by a face-down stack of shuffled hexes, with the matching number tokens shuffled into a separate face-down stack.
- When a player places a ship or road that connects to an intersection of an unexplored hex space, that player must immediately draw the top hex from the stack and place it face up in that empty space.
- If the newly discovered hex is a land hex, the discovering player must also draw a number token from the token stack and place it on that hex.
- If the newly discovered hex is a land hex, the discovering player immediately receives one resource card of the type that hex produces.
- If the newly discovered hex is a sea hex, the discovering player receives no reward.
- Both the robber and the pirate are used in this scenario, with the pirate starting on the sea hex marked with a pirate ship and the robber starting on the hex with a twelve.

### Scenario: Through the Desert
- The game ends as soon as a player reaches fourteen victory points on their turn.
- A desert zone divides the large island into the main island and a small land strip.
- Players must build both of their first two settlements on the main island.
- The smaller islands and the small land strip are all considered foreign areas.
- The first time a player builds a settlement in each foreign area, that player receives two special victory points.
- A player earns these special victory points even if another player has already built a settlement in that foreign area.
- Each player can earn up to eight special victory points in this scenario.
- Both the robber and the pirate are used in this scenario, with the robber starting on one of the three deserts and the pirate on the sea hex marked with a pirate ship.

### Scenario: The Forgotten Tribe
- The game ends as soon as a player reaches thirteen victory points on their turn.
- Players build their first two settlements with roads or ships on the big main island.
- No player may ever build a settlement on the surrounding small islands, which produce no resources and receive no number tokens.
- Eight Catan chits are placed on the marked coastlines of the small islands during set-up.
- Six harbour tokens and four development cards drawn from the top of the shuffled deck are placed face down on the marked spots during set-up and then revealed.
- Each Catan chit placed on a small island is worth one victory point to the player who claims it.
- A player who builds or moves a ship onto an edge bearing a Catan chit takes that chit and places it face up in front of themselves.
- A player who builds or moves a ship onto the edge next to one of the placed development cards takes that card and may use it like any normally purchased development card.
- A development card gained from the forgotten tribe is subject to all the usual restrictions, including that it may not be played on the turn it is acquired.
- A player who builds or moves a ship onto an edge next to one of the placed harbours takes that harbour token.
- A player who takes a harbour token must immediately place it on an edge adjacent to one of their coastal settlements, if they have a suitable settlement.
- A harbour may never be placed on an edge adjacent to, or the same as, an edge already occupied by another harbour.
- A player who has no suitable coastal settlement sets the harbour token aside until such a settlement is built.
- A player may use a newly placed harbour immediately, even during the same turn on which it was placed.
- Both the robber and the pirate are used in this scenario, with the robber starting on any desert and the pirate on the sea hex marked with a pirate ship.
- The robber may never be moved onto the small islands in this scenario.
- Once the robber has left the desert it started from, it may never be moved back onto that desert.

### Scenario: Cloth for Catan
- The game ends when a player reaches fourteen victory points on their turn, or when three or fewer of the forgotten tribe's villages still contain at least one Catan chit.
- If the game ends because of the villages running out of cloth, the player with the most victory points wins, and a tie is broken in favour of the player with more bolts of cloth.
- Each Catan chit in this scenario represents one bolt of cloth.
- Players build their first two settlements with roads or ships on the two main islands, after which every player builds a third settlement in reverse-clockwise turn order starting with the last player.
- A player receives their starting resources when they place their third settlement.
- The four small central islands are inhabited by the forgotten tribe, and their number tokens placed on intersections represent villages.
- No player may ever build a settlement on the four central islands.
- Five Catan chits are placed next to each of the eight villages during set-up, and ten further chits form a general supply beside the board.
- As soon as a player establishes a shipping route between one of their own settlements or cities and a village, that player establishes trade relations with that village.
- A player who establishes trade relations with a village immediately takes one bolt of cloth from that village's supply.
- Each time the number of a village is rolled, every player connected to that village receives one bolt of cloth from that village's supply.
- If a village's own supply has too few chits to give one to each connected player, the missing chits are taken from the general supply.
- If a village has no Catan chits left when its number is rolled, no player receives any cloth from that village and no chits are taken from the general supply.
- Two bolts of cloth are worth one victory point, and an unpaired bolt of cloth is worth nothing.
- Any shipping route that connects one of a player's settlements or cities to a village is closed, so no ship in that route may be moved.
- Both the robber and the pirate are used in this scenario, with the robber starting on the fields hex bearing the twelve token.
- The robber may never be moved onto the islands of the forgotten tribe.
- A player may not move the pirate until that player has at least one shipping route between one of their settlements or cities and a village.
- When a player moves the pirate, that player may either draw a resource card or take a bolt of cloth from one of the players whose ship is adjacent to the pirate's new hex.
- No victory points are awarded for the Longest Trade Route in this scenario.

### Scenario: The Pirate Islands
- A player wins by capturing the pirate fortress of their own colour and having at least ten victory points in total.
- Four pirate fortresses are built on the western islands, and each fortress consists of three Catan chits stacked with one settlement of a particular colour on top.
- In a three-player game the white player's position and all white pieces are removed from the game.
- Each player builds two settlements with roads or ships on the main eastern island during set-up, and one settlement and one ship of each colour are already placed on the eastern coast, so each player begins with three settlements.
- The eastern island may be colonised normally, and all other islands are pirate islands.
- There is no robber in this scenario, and the pirate fleet is represented by the black pirate ship.
- The Longest Road and Largest Army special cards are not used in this scenario.
- In a three-player game the victory point development cards are removed from the deck, and in a four-player game they remain in the deck but function in all ways as knight cards.
- Each player may build only one shipping route, which must begin at one of their coastal settlements or cities on the eastern island.
- A player's shipping route must first lead to the intersection marked with a circle of their colour and then to the pirate fortress of their colour.
- A player's shipping route may not branch, and it may not be continued beyond the pirate fortress.
- A player's shipping route must be built so that it reaches its destination by as short a path as possible, and it may not veer off in order to block another player's route.
- When a player reveals a knight card, that player may convert the hindmost normal ship of their route, meaning the ship closest to the route's starting settlement, into a warship by turning it on its side.
- A card used to create a warship is placed in a discard pile and never returns to the development card deck.
- Every time the dice are rolled, and before anything else is resolved, the pirate fleet moves clockwise around the two desert islands a number of hexes equal to the lower of the two die results.
- If both dice show the same result, the pirate fleet moves that number of hexes.
- If the pirate fleet ends its movement on a hex adjacent to one of a player's settlements or cities, that player is attacked immediately, even before resource production or the resolution of a rolled seven.
- The strength of the attacking pirate fleet is equal to the die result used for its movement.
- A defending player's strength is equal to the number of warships that player has.
- If the pirate fleet is stronger than the defender, the defender loses one resource card plus one further resource card for each of their cities, drawn at random from their hand and discarded.
- If the defender is stronger than the pirate fleet, that defender receives one resource card of their choice.
- If the pirate fleet and the defender are equally strong, nothing happens.
- Once a player's shipping route reaches the marked intersection of their colour on the pirate islands, that player may pay the normal building costs to build a settlement there.
- A player may build only one settlement on the pirate islands, though that settlement may later be upgraded to a city.
- A player whose shipping route has reached the pirate fortress of their own colour may attack it at the end of their turn.
- The strength of the pirate fortress for an attack is determined by rolling one die.
- If the attacker has more warships than the number rolled, the attacker removes one Catan chit from underneath the pirate fortress.
- If the attacker has fewer warships than the number rolled, the attacker must remove their two ships closest to the pirate fortress.
- If the attacker's number of warships equals the number rolled, the attacker loses the single ship adjacent to the pirate fortress.
- A player's turn ends immediately after an attack, so no player may attack a pirate fortress more than once per turn.
- Once a pirate fortress has lost all three of its Catan chits, the attacking player has recaptured the settlement, which then counts as one of that player's own settlements for victory points and production and may be upgraded to a city.
- If a seven is rolled, every player with more than seven resource cards discards half of them, and the player who rolled the seven steals one card from any other player.
- Once all pirate fortresses have been captured, the pirate fleet is removed from the board.
- The set-up of this scenario should not be varied except for the placement of harbours, because the balance depends on the given layout.

### Scenario: The Wonders of Catan
- A player wins immediately upon finishing the fourth level of their Wonder of Catan.
- A player also wins if they have ten victory points and have completed a higher level of their wonder than any other player.
- Players build their first two settlements with roads or ships on the main island only.
- No starting settlement may be placed on the small islands, on the intersections marked with coloured squares, or on the intersections marked with red exclamation points.
- Each player receives one Catan chit at the start of the game, which is used as a level marker on their wonder card.
- A player who builds a settlement on one of the smaller islands receives one special victory point, regardless of whether other players have already settled that island.
- There are five wonder cards in the three-to-four-player scenario and seven wonder cards in the five-to-six-player extension version.
- Each player may build at most one wonder during the game.
- The first player to start building a wonder may freely choose among all available wonders, and later players must choose among those that remain.
- A player may only begin building a wonder once that player has fulfilled the specific requirement printed on that wonder's card.
- The Monument, for example, may only be started by a player who has a city at a harbour and a trade route of at least five consecutive unbranched roads or ships.
- A player begins building a wonder by placing one of their ships on the corresponding wonder card, after which that player is obliged to build that wonder.
- Once a player has started a wonder, no other player may start building that same wonder.
- Each wonder is divided into four levels, and each level costs the five resources shown on that wonder's card.
- When a player pays for the first level of their wonder, that player places their Catan chit on the field marked "1" on the wonder card, and moves it to the next field as each further level is completed.
- A player with sufficient resources may build several levels of their wonder during the same turn.
- The robber starts on one of the three deserts, and the pirate is not used in this scenario.

### Scenario: New World
- The game ends once a player has reached twelve victory points.
- The board is created by shuffling all listed hexes face down and placing them face up at random within the assembled frame.
- Number tokens are shuffled and placed at random, one on each land hex, and no number tokens are placed on sea hexes.
- The red number tokens showing six and eight may not be placed on adjacent hexes, and a second red token drawn next to a first must be replaced by another token drawn at random.
- Harbour tokens are shuffled face down, and players take turns starting with the oldest player to place one harbour each on an edge between a sea hex and a land hex, or between a land hex and a frame piece.
- A harbour token must lie on the sea hex or frame piece with both of its corners touching the land hex.
- Each player may place their two starting settlements on any islands they choose, either both on the same island or on two separate islands.
- The island or islands on which a player places their starting settlements are that player's home islands, and all other islands are foreign islands to that player.
- A player who builds a settlement on a foreign island receives one special victory point, regardless of whether other players have already settled that island.
- Each player may earn only one special victory point per foreign island in this scenario.
- Both the robber and the pirate are used, and both start on the frame and enter play when first moved.
- Players may agree to adjust the randomly generated set-up if they are unhappy with it, and may freely design and play scenarios of their own.

### Scenario: The Great Crossing (legacy)
- The Great Crossing is a legacy scenario that appeared in earlier editions of Seafarers and is not part of the current fifth-edition scenario set.
- The board in The Great Crossing is divided into two large islands, the home island of Catan and the distant island of Transcatania.
- Players begin on the home island and must cross the open sea with shipping routes in order to reach the second island.
- A player earns special victory points for connecting their settlements on the home island to settlements on the far island by a continuous shipping route.
- Because this scenario is superseded, an implementation should treat it as optional and derive its exact victory point total from the edition of the rulebook being reproduced.

### General Scenario Guidance
- Every Seafarers scenario specifies its own victory point total, which replaces the ten victory points used in basic Catan.
- A reasonable rule of thumb for a self-designed scenario is that the victory point target equals the number of terrain hexes minus the deserts, divided by two.
- Each scenario's variable set-up section states which parts of the layout may be rearranged, and the outlines of the islands should generally be preserved.
- When randomising a layout, red production numbers, meaning sixes and eights, should never be placed on adjacent hexes.
- When randomising a layout, red production numbers should not be placed on gold fields.
- As of the December 2020 revision, the rules in the fifth English-language edition take precedence over any previously published Seafarers rules.
## Cities & Knights

### Setup and General Changes
- Cities & Knights is played on the standard Catan board and uses all standard Catan rules except where the expansion's rules explicitly replace them.
- The game is won by the first player who reaches 13 victory points, instead of the 10 points required in the base game.
- A player may only win the game on their own turn, and must announce the win at a moment when they hold at least 13 points.
- During initial placement each player places one settlement with an adjoining road in the first round, and one city with an adjoining road in the second round, instead of two settlements.
- Each player collects one resource (and, where applicable, one commodity) from every terrain hex adjacent to the city placed during the second setup round.
- Development cards are not used in Cities & Knights and are completely replaced by progress cards.
- The Largest Army special card is not used in Cities & Knights, because knights replace the base game's soldier cards.
- The Longest Road special card is still used and is still worth 2 victory points to the player with the longest continuous road of at least five road segments.
- Each player receives their own city improvement flip chart, six knight tokens, and three city wall pieces at the start of the game.

### Dice and the Event Die
- Three dice are rolled at the start of every player's turn: a yellow production die, a red production die, and a six-sided event die.
- The sum of the yellow die and the red die determines which number tokens produce resources and commodities, exactly as in the base game.
- The event die is resolved before resource production and before any robber effects from a roll of 7.
- The event die has three faces showing a barbarian ship, one face showing a green science city gate, one face showing a blue politics city gate, and one face showing a yellow trade city gate.
- Whenever the event die shows the barbarian ship, the barbarian ship advances one space along the barbarian track toward Catan.
- Whenever the event die shows a colored city gate, every player whose improvement level in that colored discipline is high enough relative to the red die may draw a progress card from the matching deck.
- The value of the red production die is used both for resource production and for determining progress card eligibility, so a single red die roll serves two purposes.
- A roll of 7 still forces all players holding more than seven cards to discard half of their cards, rounded down, counting resources and commodities together.
- Until the barbarians have attacked for the first time, the robber is not moved when a 7 is rolled, although the discard rule still applies normally.

### Commodities
- The game adds three commodity card types: cloth, coin, and paper.
- A city adjacent to a pasture hex produces one wool and one cloth when that hex's number is rolled.
- A city adjacent to a mountain hex produces one ore and one coin when that hex's number is rolled.
- A city adjacent to a forest hex produces one lumber and one paper when that hex's number is rolled.
- A city adjacent to a field hex produces two grain when that hex's number is rolled, exactly as in the base game.
- A city adjacent to a hill hex produces two brick when that hex's number is rolled, exactly as in the base game.
- A settlement always produces exactly one resource and never produces any commodity, regardless of the terrain type.
- Commodities count toward the seven-card hand limit that triggers discarding when a 7 is rolled.
- Commodities may be stolen by the robber and by progress cards in the same way as resources.
- Commodities may be traded with other players and with the bank in all the same ways that resources may be traded.
- Commodities may be traded to the bank at the rate of four identical commodities for one card of choice, or at three-for-one using a generic 3:1 harbor.
- Commodities may never be traded at a 2:1 resource-specific harbor, because those harbors only accept their own resource.
- A hex blocked by the robber produces neither resources nor commodities.

### City Improvements
- City improvements are bought with commodities only and are tracked on each player's personal city improvement flip chart.
- A player must own at least one city in order to buy any city improvement.
- Cloth is the commodity used to buy improvements on the yellow trade track.
- Coin is the commodity used to buy improvements on the blue politics track.
- Paper is the commodity used to buy improvements on the green science track.
- Each of the three tracks has five levels, and the levels of a track must be bought in ascending order without skipping any level.
- Advancing to level 1 of a track costs one commodity of that track's type.
- Advancing to level 2 of a track costs two commodities of that track's type.
- Advancing to level 3 of a track costs three commodities of that track's type.
- Advancing to level 4 of a track costs four commodities of that track's type.
- Advancing to level 5 of a track costs five commodities of that track's type.
- The five trade improvements are, in order, the Market, the Trading House, the Merchant Guild, the Bank, and the Great Exchange.
- The five politics improvements are, in order, the Town Hall, the Church, the Fortress, the Cathedral, and the Council of Catan.
- The five science improvements are, in order, the Abbey, the Library, the Aqueduct, the Theater, and the University.
- Reaching level 3 of the trade track builds the Merchant Guild, which lets the player trade any two identical commodities to the bank for one resource or commodity of choice.
- Reaching level 3 of the politics track builds the Fortress, which lets the player promote strong knights into mighty knights.
- Reaching level 3 of the science track builds the Aqueduct, which lets the player take one resource of choice from the bank whenever a production roll other than 7 gives them no resources and no commodities at all.
- City improvements are never lost, even if the player's cities are destroyed by the barbarians or reduced in number.
- City improvement levels themselves are worth no victory points, apart from the metropolis granted at level 4 or 5.

### Progress Card Eligibility from Improvements
- A player at level 1 in a discipline draws a progress card of that color when the event die shows that color's city gate and the red die shows 1 or 2.
- A player at level 2 in a discipline draws a progress card of that color when the event die shows that color's city gate and the red die shows 1, 2, or 3.
- A player at level 3 in a discipline draws a progress card of that color when the event die shows that color's city gate and the red die shows 1, 2, 3, or 4.
- A player at level 4 in a discipline draws a progress card of that color when the event die shows that color's city gate and the red die shows 1, 2, 3, 4, or 5.
- A player at level 5 in a discipline draws a progress card of that color whenever the event die shows that color's city gate, regardless of the red die value.
- A player at level 0 in a discipline never draws progress cards of that color.
- All eligible players draw a card when a city gate is rolled, not only the active player.

### Metropolis
- Exactly three metropolises exist in the game, one for trade, one for politics, and one for science.
- The first player to reach level 4 of a given track immediately places that track's metropolis gate piece on one of their own cities.
- A city carrying a metropolis is worth 4 victory points in total, which is 2 points more than an ordinary city.
- A player must own a city that is not already a metropolis in order to build the level 4 improvement and claim the metropolis.
- A player may hold more than one metropolis at the same time, provided each metropolis sits on a different city of theirs.
- Once a metropolis of a given type has been claimed, another player can only take it by being the first to reach level 5 of that same track.
- When a player reaches level 5 of a track whose metropolis is held by another player, the metropolis gate is moved immediately from the current holder's city to one of the new player's cities.
- A player who already holds a metropolis of a given type keeps it and cannot lose it to anyone once they themselves have reached level 5 of that track.
- A metropolis can never be destroyed or reduced by a barbarian attack.
- A metropolis is never moved or removed for any reason other than another player reaching level 5 of the same track.

### Knights
- Building a new basic knight costs one wool and one ore.
- A newly built knight is placed on any vacant intersection that touches at least one of the builder's own roads.
- The distance rule that applies to settlements does not apply to knights, so a knight may be placed on an intersection adjacent to any building.
- A knight is always placed inactive, showing its inactive side.
- Activating a knight costs one grain and flips the knight to its active side.
- A knight may be built and activated on the same turn, but a knight may never perform a knight action on the turn it was activated.
- Promoting a basic knight into a strong knight costs one wool and one ore.
- Promoting a strong knight into a mighty knight costs one wool and one ore and additionally requires that the player has built the Fortress at level 3 of the politics track.
- A knight may not be promoted twice in the same turn.
- Promotion does not change a knight's active or inactive status.
- A basic knight has strength 1, a strong knight has strength 2, and a mighty knight has strength 3.
- Each player has exactly six knight tokens consisting of two basic, two strong, and two mighty knights, and may never have more knights of a given rank on the board than they have tokens.
- A knight standing on an intersection blocks opposing road building through that intersection and interrupts an opponent's longest road passing through it.
- A knight never blocks its own owner's roads or longest road.
- Knights are never worth victory points by themselves.

### Knight Actions
- Only an active knight may perform an action, and a knight may perform at most one action per turn.
- Performing any knight action immediately deactivates the knight, which must then be reactivated with grain before it can act again.
- The move action lets a player move an active knight along their own connected roads to any vacant intersection in that road network.
- The displacement action lets a player move an active knight onto an intersection occupied by an opponent's knight of strictly lower strength, provided the target intersection is reachable through the moving player's own road network.
- A basic knight can never displace another knight, because no knight is weaker than strength 1.
- The owner of a displaced knight must immediately move it to an adjacent vacant intersection that is connected to their own roads, and the displaced knight keeps its rank and its active or inactive status.
- A displaced knight that has no legal intersection to move to is removed from the board and returned to its owner's supply.
- The chase-away-the-robber action lets a player use an active knight standing on an intersection adjacent to the robber's hex to move the robber to any other land hex.
- After chasing the robber away, the acting player steals one random resource or commodity card from one player who has a settlement, city, or metropolis adjacent to the robber's new hex.
- Knights do not need to act in order to contribute to barbarian defense, and an active knight contributes its strength to the defense of Catan simply by being active when the barbarians attack.
- An inactive knight contributes nothing to the defense of Catan.

### Barbarian Attacks
- The barbarian ship travels along a track of seven spaces leading to the island of Catan.
- The barbarian ship advances one space each time the event die shows the barbarian ship face.
- When the barbarian ship reaches the final space of the track, a barbarian attack is resolved immediately, before any other part of the current turn is completed.
- The barbarians' attack strength equals the total number of cities and metropolises owned by all players together, counting each city and each metropolis as 1.
- Catan's defense strength equals the sum of the strengths of all active knights belonging to all players together.
- The defense succeeds if the total knight strength is greater than or equal to the barbarians' strength.
- The defense fails if the total knight strength is strictly less than the barbarians' strength.
- When the defense succeeds, the player who contributed the single highest total active knight strength receives a Defender of Catan card worth 1 victory point.
- When the defense succeeds and several players are tied for the highest contributed knight strength, each tied player instead draws one progress card of their choice from any one of the three progress card decks.
- A player may earn multiple Defender of Catan cards over the course of a game, and each one is worth 1 victory point.
- When the defense fails, the player with the lowest total active knight strength loses one city, which is turned back into a settlement.
- When the defense fails and several players are tied for the lowest total active knight strength, every one of those tied players loses one city.
- A player who owns no cities at all is not affected when the defense fails.
- A player whose only cities are metropolises is not affected when the defense fails, because a metropolis cannot be pillaged.
- A city wall on a pillaged city is destroyed and returned to its owner's supply along with the city piece.
- A player who loses a city must return the city piece to their supply and place a settlement on that intersection, and if they have no settlement piece available they must first remove a settlement elsewhere on the board.
- Immediately after a barbarian attack is resolved, all knights belonging to all players are flipped to their inactive side.
- Immediately after a barbarian attack is resolved, the barbarian ship is returned to the starting space of its track.

### Progress Cards
- Progress cards completely replace development cards and can never be bought with resources.
- There are three progress card decks: the green science deck, the yellow trade deck, and the blue politics deck.
- Each of the three decks contains 18 cards, for a total of 54 progress cards.
- A progress card is only ever obtained by drawing it when the event die shows a city gate matching that deck's color and the player's improvement level in that discipline is high enough for the red die value rolled.
- A player may hold at most four progress cards in hand at any time in the standard three-to-four-player game.
- A player who would exceed the hand limit must immediately play or discard cards until the limit is respected.
- Progress cards granting a victory point are revealed and played immediately when drawn, and they do not count against the progress card hand limit.
- A progress card may be played on the same turn it was drawn.
- A player may play more than one progress card during a single turn.
- Progress cards may only be played on the player's own turn, except where a card's own text states otherwise.
- The Alchemist card is the only card that is played before the dice are rolled, and it lets the player choose the values of the red and yellow production dice.
- A progress card that would have no effect when played may not be played.
- The Crane card lets the player build one city improvement for one commodity less than its normal cost.
- The Engineer card lets the player build one city wall for free on one of their cities.
- The Inventor card lets the player swap two number tokens on the board, excluding tokens showing 2, 6, 8, or 12.
- The Irrigation card gives the player two grain for each of their settlements and cities adjacent to a field hex.
- The Mining card gives the player two ore for each of their settlements and cities adjacent to a mountain hex.
- The Medicine card lets the player upgrade a settlement into a city for two ore and one grain instead of the normal cost.
- The Printer card is a science card worth 1 victory point that is revealed immediately.
- The Road Building card lets the player build two roads for free.
- The Smith card lets the player promote up to two of their knights one rank each for free.
- The Commercial Harbor card forces each other player to either trade one commodity of their choice for one resource offered by the player, or decline if they hold no commodities.
- The Master Merchant card lets the player look at the hand of a player who has more victory points than they do and take two cards of their choice from it.
- The Merchant Fleet card lets the player trade one chosen resource or commodity at a 2:1 rate with the bank for the rest of the turn.
- The Resource Monopoly card forces every other player to give the playing player two cards of one named resource, or as many as they hold if they hold fewer.
- The Trade Monopoly card forces every other player to give the playing player one card of one named commodity if they hold any.
- The Bishop card lets the player move the robber and then steal one random card from every player with a building adjacent to the robber's new hex.
- The Constitution card is a politics card worth 1 victory point that is revealed immediately.
- The Deserter card lets the player remove one knight of a chosen opponent and place a knight of the same rank of their own on the board for free, if they have a matching knight token available.
- The Diplomat card lets the player remove any open road that does not connect at both ends to another road or building, and if the removed road is their own they may rebuild it elsewhere for free.
- The Intrigue card lets the player displace an opponent's knight that stands on an intersection adjacent to one of the player's own roads, without needing a stronger knight.
- The Saboteur card forces every player with at least as many victory points as the playing player to discard half of their hand, rounded down.
- The Spy card lets the player look at the progress card hand of another player and take one card from it.
- The Warlord card activates all of the playing player's inactive knights for free.
- The Wedding card forces every player with more victory points than the playing player to give that player two cards of the giver's choice from their hand.

### The Merchant
- The merchant is a single wooden piece that enters the game only when a player plays a Merchant progress card.
- A player who plays a Merchant card places the merchant piece on any land hex adjacent to one of their own settlements or cities.
- The player controlling the merchant may trade the resource type of the hex the merchant stands on with the bank at a 2:1 rate.
- The player controlling the merchant scores 1 victory point for as long as they control it.
- Control of the merchant passes to any player who plays a Merchant card afterwards, and that player moves the merchant piece to a hex adjacent to one of their own buildings.

### City Walls
- Building a city wall costs two brick.
- A city wall may only be placed under a city that the player already owns, and each city may have at most one wall.
- Each player may have at most three city walls on the board at once.
- Each city wall raises that player's safe hand limit for a roll of 7 by two cards, so one wall raises the limit to nine cards, two walls to eleven cards, and three walls to thirteen cards.
- A city wall is destroyed and returned to the supply when its city is pillaged by the barbarians.
- City walls are worth no victory points.

### Victory Points
- Each settlement a player owns is worth 1 victory point.
- Each ordinary city a player owns is worth 2 victory points.
- Each city carrying a metropolis is worth 4 victory points.
- The Longest Road special card is worth 2 victory points.
- Each Defender of Catan card is worth 1 victory point.
- Control of the merchant is worth 1 victory point.
- Each revealed Printer or Constitution progress card is worth 1 victory point.
- The first player to hold 13 or more victory points on their own turn immediately wins the game.
## Traders & Barbarians

### Scenario: The Fishermen of Catan

- The Fishermen of Catan is a standalone scenario for the Catan base game that lasts about 45 to 60 minutes and adds fishing grounds, a lake, fish tokens, and the old boot token.
- The additional components for this scenario are 6 fishing ground tiles bearing the production numbers 4, 5, 6, 8, 9, and 10, one lake hex bearing the production numbers 2, 3, 11, and 12, 29 fish tokens, 1 old boot token, and 4 player overview cards.
- During preparation you replace the desert hex with the lake hex, and the lake hex may never be placed on the edge of the island (that is, never on the coast).
- During preparation you mix the 29 fish tokens together with the old boot token face down and place that supply near the resource cards.
- During preparation you place one fishing ground tile on a free vertex of each frame section, oriented so that each fishing ground points toward the island.
- During preparation you place the robber beside the game board instead of on the map, and the robber only enters the game when the first "7" is rolled.
- If you place your second starting settlement on an intersection adjacent to a fishing ground tile, you immediately receive one fish token in addition to your normal starting resources.
- Each fishing ground tile touches exactly 3 coastal intersections, and only settlements and cities built on those intersections can collect fish from that fishing ground.
- When the production dice roll matches the number shown on a fishing ground tile, each settlement adjacent to that fishing ground collects 1 fish token and each city adjacent to it collects 2 fish tokens.
- If you have a settlement adjacent to the lake hex you draw 1 fish token whenever a 2, 3, 11, or 12 is rolled, and if you have a city adjacent to the lake hex you draw 2 fish tokens instead.
- Fish tokens are always drawn randomly and face down from the supply, and if there are not enough fish tokens left to fulfil everyone's production that turn, then nobody receives any fish tokens that turn.
- Each fish token shows 1, 2, or 3 fish, and the supply contains 11 tokens showing 1 fish, 10 tokens showing 2 fish, and 8 tokens showing 3 fish.
- When you draw a fish token you examine it privately and keep it face down in front of you until you decide to spend it, unless it is the old boot token, which must be revealed immediately.
- During your turn you may discard fish tokens whose fish total is exactly 2 fish to remove the robber from the board without stealing any card, and the robber then stays off the board until he re-enters the game through a "7" or a knight card.
- During your turn you may discard fish tokens whose fish total is exactly 3 fish to steal one random resource card from another player.
- During your turn you may discard fish tokens whose fish total is exactly 4 fish to take one resource card of your choice from the bank.
- During your turn you may discard fish tokens whose fish total is exactly 5 fish to build one road for free, subject to the normal road building placement rules.
- During your turn you may discard fish tokens whose fish total is exactly 7 fish to draw one development card for free.
- You place every fish token you spend face up next to the face-down supply of fish tokens.
- You may never hold more than 7 fish tokens at any one time, and if you already hold 7 fish tokens and would receive another token for a settlement or city, you may instead exchange one of your fish tokens for a new random token from the supply.
- You cannot make change when spending fish, so if the fish shown on the tokens you spend exceeds the purchase price, the excess fish are simply lost.
- You may perform more than one fish action during the same turn, but each action must be paid for separately with its own tokens and you may not combine leftover fish from one action into another.
- Fish tokens are not resource cards, so they do not count toward your hand limit, you never discard them when a "7" is rolled, and the robber can never steal them.
- Fish tokens may never be traded between players.
- If your settlement or city stands on an intersection that touches both a harbor and a fishing ground tile, you receive the benefits of both.
- When the last face-down fish token is drawn from the supply, you turn all the spent face-up fish tokens back over and mix them to form a new face-down supply.
- If you draw the old boot token you must reveal it immediately and keep it face up in front of you.
- As long as you hold the old boot you need one additional victory point to win the game, so you would need 11 victory points instead of 10 in the base game.
- The old boot is not a negative victory point and does not reduce your victory point total; it only raises the threshold you personally need to reach in order to win.
- After rolling the dice on your turn you may give the old boot away to any other player who has the same number of victory points as you or more victory points than you.
- If you alone have the most victory points, you must keep the old boot and may not give it away.
- The Fishermen of Catan scenario ends as soon as a player reaches 10 victory points during his own turn, or 11 victory points if that player holds the old boot.
- When The Fishermen of Catan is combined with the Harbormaster variant, the game is played until a player reaches 11 victory points during his turn, or 12 victory points if he holds the old boot.
- When The Fishermen of Catan is combined with Catan for Two, each player receives 5 fish tokens during set-up consisting of two 1-fish tokens, two 2-fish tokens, and one 3-fish token, the remaining fish tokens are shuffled face down beside the board, trade tokens are not used at all, the player with fewer victory points needs 1 fish less for each fish action, and new fish tokens are obtained only when a fishing ground or lake number is rolled.
- When The Fishermen of Catan is combined with the Catan Event Cards variant, the "Robber Flees" event places the robber beside the game board until he is used again via a "7" or a knight card.

### Scenario: The Rivers of Catan

- The Rivers of Catan is a scenario lasting about 45 to 60 minutes in which rivers cross the island, roads and settlements along the rivers earn gold coins, and bridges span the rivers.
- The additional components for this scenario are 3 river tiles (one tile carrying a 3-hex river and two tiles carrying a 4-hex river each), 2 replacement sea frame pieces, 12 bridges (3 of each player color), 40 gold coins, 1 "Wealthiest Settler" tile, and 1 "Poor Settler" tile.
- During preparation you assemble the frame and replace the two base game frame pieces labeled 4–5 and 5–6 with the two corresponding frame pieces provided in this expansion.
- During preparation you place the 3 river tiles in the arrangement shown in the scenario illustration and build the rest of the island from the remaining terrain hexes.
- During preparation you remove from play 2 mountains hexes, 2 hills hexes, 2 pasture hexes, and 1 desert hex from the Catan base game.
- When placing number tokens you skip the two swampland hexes entirely and never place a number token on them.
- You place the first number token "A" on any coastal hex, you set the number token "2" (B) aside, you place all remaining number tokens in alphabetical order as in the base game, and you finally place the token "2" (B) on the hex that already carries the token "12" (H) so that this hex produces on both a "2" and a "12".
- During preparation you place the robber on one of the two swampland hexes.
- During preparation you place all gold coins beside the game board, and no player owns any coins at that moment.
- During preparation each player takes the 3 bridges of his own color.
- During preparation you place the "Wealthiest Settler" tile and the "Poor Settler" tile beside the game board.
- Each player builds 2 settlements with 1 road each during set-up, exactly as in the Catan base game.
- You may never build a normal road on a bridge building site, which is a path that crosses a river, and this restriction applies for the entire game.
- For each settlement you build adjacent to one or two river hexes, whether during set-up or later in the game, you immediately receive 1 gold coin.
- For each road you build on a path adjacent to a river hex, whether during set-up or later in the game, you immediately receive 1 gold coin.
- You do not receive any coins for upgrading a settlement adjacent to a river hex into a city.
- Because of the set-up rules you can start the game with at most 4 gold coins.
- Building a bridge costs 2 brick and 1 lumber.
- A new bridge must always connect to one of your existing roads, settlements, or cities.
- A bridge may only be built on one of the 7 bridge building sites, each of which is a path that crosses a river.
- For each bridge you build you immediately receive 3 gold coins.
- A bridge counts exactly as a road for the purposes of the Longest Road and for the purpose of connecting to new settlements.
- Each player may build a maximum of 3 bridges during the game.
- You may not use the "Road Building" development card to build a bridge in place of a road.
- If you have the smallest number of gold coins at any point in the game, you immediately receive a "Poor Settler" tile, which reduces your victory point total by 2 victory points.
- If several players are tied for the smallest number of gold coins, including a tie at zero coins, then each of those tied players receives a "Poor Settler" tile.
- As soon as you no longer have the smallest number of gold coins you immediately return your "Poor Settler" tile to the supply and regain the 2 victory points.
- If you and you alone have the most gold coins, you receive the "Wealthiest Settler" tile, which is worth 1 victory point.
- You lose the "Wealthiest Settler" tile as soon as another player's coin total equals or exceeds your own coin total, whether because you spent coins or because another player gained coins.
- When the "Wealthiest Settler" tile is lost it passes immediately to whichever player is then the sole player with the most coins, and if no single player has the most coins the tile is set aside until one player alone has the most coins again.
- Up to two times during your turn you may spend 2 gold coins to buy 1 resource card of your choice from the supply.
- You may spend gold coins on the same turn on which you received them.
- You may freely trade gold coins for resource cards with other players and trade resource cards for gold coins with other players.
- You may use maritime trade to obtain gold coins at the usual rate of 4 identical resources for 1 coin, or 3 identical resources for 1 coin if you own the matching 3:1 harbor.
- A 2:1 harbor can never be used to obtain gold coins, because no 2:1 gold harbors exist.
- Gold coins can never be stolen by the robber.
- Gold coins can never be taken from a player with the "Monopoly" development card.
- The Rivers of Catan scenario ends when a player reaches 10 victory points during his own turn.
- When The Rivers of Catan is combined with the Harbormaster variant, the game is played until a player reaches 11 victory points during his turn.
- When The Rivers of Catan is combined with Catan for Two, you receive 2 trade tokens for building a settlement adjacent to a swampland hex, and the robber is sent to a swampland hex whenever the rules would send him to the desert.
- When The Rivers of Catan is combined with the Catan Event Cards variant, the "Robber Flees" event places the robber beside the game board until he is used again via a "7" or a knight card.

### Scenario: The Caravans

- The Caravans is a scenario lasting about 60 minutes in which three caravans of camels grow out from a central oasis and increase the value of adjacent settlements, cities, and roads.
- The additional components for this scenario are 1 oasis hex and 22 camels.
- During preparation the oasis hex replaces the desert hex and is placed at the very center of the island before the rest of the island is created, and the rotational orientation of the oasis hex is arbitrary.
- During preparation you place all camels beside the game board.
- During preparation you place the robber beside the game board, and as soon as the first "7" is rolled you place him on any hex that has a number token, but never on the oasis.
- After set-up, whenever you build one or more settlements or upgrade one or more settlements to cities during your turn, exactly 1 camel is placed at the end of that turn.
- The player who triggered the camel placement does not simply choose where the camel goes, because the camel's exact placement is decided in a voting round.
- A camel must always be placed on a path that is not already occupied by another camel, although that path may be occupied by a road.
- You may build a road on a path that is already occupied by a camel, and the road and the camel are then placed side by side on that same path.
- Every camel has a front end, which is its head, and the direction the head points determines where the caravan can continue.
- The first camel of a caravan must be placed on a path directly pointed to by one of the 3 arrows printed on the oasis hex, with its front pointing away from that arrow.
- Each of the 3 caravans must begin from a different arrow of the oasis hex.
- Every camel after the first camel of a caravan must be placed on a path adjacent to the front of the last camel previously placed in that caravan, with its own front pointing away from that previous camel.
- The first camel of a caravan may never be placed on a path along the edge of the oasis hex, but if a caravan later winds its way back to the oasis, a camel may then be placed on a path along the oasis edge.
- A caravan may be extended by placing a camel on a coastal path.
- A caravan may never branch, so at any moment each caravan offers at most 2 legal paths for its next camel, and with 3 caravans there are at most 6 legal paths for a given camel placement.
- A caravan ends when it can no longer be extended by any legal camel placement, and all 3 caravans end immediately when the camel supply is exhausted.
- Two caravans that meet at an intersection merge into a single caravan as soon as the next camel is placed.
- In a voting round each player may bid exactly once, and bidding starts with the player who just finished his turn and proceeds clockwise.
- You bid by placing wool cards and/or grain cards face up in front of yourself, and you gain one vote for each card you bid.
- Only players who bid at least one card may negotiate with each other about where the camel is placed.
- If you have more votes than all other players combined, you alone choose where the camel is placed.
- If instead two or more players together hold a majority of the votes and agree on a placement, the camel is placed as they agree.
- If no agreement is reached, the single player with the most votes chooses the placement, even if his votes are a minority of the total.
- If there is no single player with the most votes, the player who just finished his turn chooses the placement, even if he bid no cards at all.
- After the camel is placed, every player discards all the resource cards he bid for voting.
- A player may never add further bidding cards to his offer after having made his single bid.
- A road built on the same path as a camel counts as 2 roads when determining the Longest Road, so a chain of 4 road segments of which 2 share paths with camels counts as a road length of 6.
- Each settlement or city located on an intersection between 2 camels is worth 1 additional victory point.
- The Caravans scenario ends when a player reaches 12 victory points during his own turn.
- When The Caravans is combined with the Harbormaster variant, the game is played until a player reaches 13 victory points during his turn.
- When The Caravans is combined with Catan for Two, each voting round determines the placement of 2 camels, the winner of the vote must place his 2 camels into 2 different caravans, in case of a tie each player places one camel starting with the player who just finished his turn, and the robber is placed beside the board instead of being sent to the desert until he is used again via a "7" or a knight card.
- When The Caravans is combined with the Catan Event Cards variant, the "Robber Flees" event places the robber beside the game board until he is used again via a "7" or a knight card.

### Scenario: Barbarian Attack

- Barbarian Attack is a scenario lasting about 60 to 90 minutes in which barbarians land on the coastal hexes of Catan and players train knights at a central castle to expel them.
- The additional components for this scenario are 24 knights (6 of each player color), 30 barbarian figures, 40 gold coins, and a special deck of 26 development cards.
- During preparation you first place the desert hex and the castle hex in the outer ring as shown in the scenario illustration.
- During preparation you randomly place 2 forest hexes, 2 hills hexes, 3 pasture hexes, 1 mountains hex, and 2 fields hexes into the remaining spaces of the outer ring, and all of these hexes count as coastal hexes.
- During preparation you randomly place 1 forest hex, 1 pasture hex, 1 hills hex, 2 mountains hexes, and 2 fields hexes into the inner area of the board, and one forest hex is left unused.
- During preparation you place the number tokens according to the fixed pattern printed in the scenario illustration rather than in alphabetical order.
- During preparation each player takes the 6 knights of his own color.
- During preparation you place one barbarian on the coastal hex bearing the "2" number token and one barbarian on the coastal hex bearing the "12" number token, and all remaining barbarians are placed beside the board as the supply.
- During preparation you replace the base game development card deck entirely with this scenario's 26 development cards, which consist of 14 "Knighthood" cards, 4 "Swift Knight" cards, 4 "Treason" cards, and 4 "Intrigue" cards.
- The "Largest Army" special card is not used in this scenario.
- The robber is not used at all in this scenario.
- During set-up each player places 1 settlement with a road and then 1 city with a road instead of a second settlement, and he still receives only 1 resource for each terrain hex adjacent to that starting city.
- Each time you build a settlement or upgrade a settlement to a city, you must immediately interrupt your turn and resolve a barbarian attack.
- If there are no barbarians left in the supply, no further barbarian attacks take place for the rest of the game.
- To resolve a barbarian attack you roll the dice until you get a result that is not a "7", and you then place one barbarian on the coastal hex whose number token matches that result.
- If the coastal hex indicated by a barbarian attack roll already holds 3 barbarians, no barbarian is placed for that roll and you do not re-roll the dice.
- A barbarian attack consists of three such placement rolls in total, and the second and third rolls must each produce a number that is not a "7" and that differs from every previous result in that same attack.
- As soon as a coastal hex holds 3 barbarians it becomes a conquered hex and its number token is turned face down.
- A conquered hex no longer produces any resources when its number is rolled, and no further barbarians are ever placed on it.
- You may not build a road on a path adjacent to a conquered hex, and you may not build a settlement on an intersection adjacent to a conquered hex.
- As soon as a settlement or city is adjacent only to conquered hexes and/or the frame, it becomes a conquered settlement or conquered city and is turned on its side while remaining on its intersection.
- A conquered settlement or conquered city is worth no victory points to its owner.
- The harbor of a conquered settlement or conquered city may not be used.
- A settlement or city adjacent to the desert hex or the castle hex can never be conquered, because those two hexes can never be conquered themselves.
- When you buy a development card in this scenario you must immediately reveal and resolve it, and you must finish resolving it before buying another development card during the same turn.
- Every development card is discarded after it has been resolved, and when the development card stack runs out the discard pile is shuffled to form a new stack.
- When you play a "Knighthood" development card you place one of your knights on one of the 6 paths adjacent to the castle hex, and that path must not already be occupied by another knight.
- When you play a "Swift Knight" development card you place one of your knights on any path not already occupied by another knight.
- When you resolve a "Treason" development card you obtain 2 gold, you remove 2 barbarians from 2 different hexes, and you place those 2 barbarians on 2 other unconquered coastal hexes.
- If there are not enough barbarians in play to satisfy a "Treason" card, you take either one or both of the required barbarians from the supply instead.
- When you resolve an "Intrigue" development card you remove 1 barbarian from a coastal hex of your choice and add him to your own prisoners.
- If there are no barbarians on any coastal hex when you resolve an "Intrigue" card, you discard that card and draw a new development card instead.
- A barbarian may never be moved onto a hex that already contains 3 barbarians when resolving "Treason" or "Intrigue".
- If a "Treason" or "Intrigue" card removes a barbarian from a conquered hex, that hex's number token is turned face up again and any adjacent conquered settlements and cities are turned upright and become fully functional again.
- After you finish trading and building on your turn, you may move each of your knights from path to adjacent path.
- Each knight may move up to 3 paths, and you may pay 1 grain per knight to increase that knight's movement to up to 5 paths for that turn.
- When moving a knight you ignore all other knights, roads, settlements, and cities that lie along the route.
- No knight may end its movement on a path that is already occupied by another knight, whether that knight belongs to you or to another player.
- After you finish moving your knights, none of your knights may remain on a path adjacent to the castle hex.
- At the end of your turn, after moving your knights, you check every coastal hex for a victory, beginning with the coastal hex numbered "4" to the left of the castle hex and continuing clockwise until all coastal hexes have been checked.
- A victory occurs at a coastal hex if that hex holds at least 1 barbarian and the number of knights standing on the hex's 6 adjacent paths is greater than the number of barbarians on the hex.
- When a victory occurs, all the defeated barbarians on that coastal hex become prisoners and are distributed among the involved players, who are the players with knights on the paths adjacent to that hex.
- If you are the only involved player in a victory, you receive all of the prisoners from that hex.
- If several players are involved in a victory, each involved player receives one prisoner as far as the prisoners suffice.
- If there are not enough prisoners for every involved player, each involved player rolls the dice and the highest rollers receive the prisoners, with ties re-rolled.
- If you roll for a prisoner and do not receive one, you receive 3 gold as compensation instead.
- If every involved player has received a prisoner and one prisoner is still left over, that extra prisoner goes to the involved player who had the most knights adjacent to the hex.
- If several involved players are tied for the most knights adjacent to the hex when an extra prisoner is awarded, those players roll the dice with ties re-rolled, the high roller takes the prisoner, and the loser receives 3 gold.
- Every two prisoners you hold are worth 1 victory point.
- When a victory occurs at a conquered coastal hex, that hex's number token is turned face up again and any adjacent conquered settlements and cities are turned upright, so the hex produces resources again, those buildings count for victory points again, and the hex can once again be targeted by barbarian attacks.
- After each victory, one of the involved players rolls a single die and places it in the center of the castle hex to determine knight losses.
- The die roll determines one of three orientation pairs of paths adjacent to the castle hex, namely "1 and 4", "2 and 5", or "3 and 6".
- Every knight involved in the victory that stands on a path whose orientation matches the rolled orientation pair is removed from the board and returned to its owner's supply.
- For each of your own knights removed after a victory you receive 3 gold as compensation.
- If you roll a "7" for production in this scenario, you may draw 1 random resource card from a player of your choice, and every player holding more than 7 resource cards must return half of them, rounded down, to the bank.
- In this scenario the large gold coins are worth 5 gold each and the small gold coins are worth 1 gold each.
- Up to two times during your turn you may buy 1 resource card of your choice for 2 gold.
- You may trade gold for resource cards with other players and resource cards for gold with other players.
- You may use maritime trade to obtain gold at the usual rate of 4 identical resources for 1 gold, or 3 identical resources for 1 gold if you own the matching 3:1 harbor, and no 2:1 gold harbor exists.
- Gold does not count as a resource, so it is ignored when a "7" is rolled and it can never be taken with a "Monopoly" development card.
- The Barbarian Attack scenario ends as soon as a player reaches 12 victory points during his own turn.
- When Barbarian Attack is combined with the Harbormaster variant, the game is played until a player reaches 13 victory points during his turn.
- When Barbarian Attack is combined with Catan for Two, a neutral-colored foreign knight takes part in the game and may be freely used by both players, it is placed on a path adjacent to the castle hex when you build your first knight, it is moved after your own knights on your turn, and it always remains on the board and is never removed after a victory.
- When Barbarian Attack is combined with Catan for Two and you build a settlement for yourself and then a settlement for a neutral player, the barbarians attack twice, first for your own settlement and then for the neutral settlement.
- When Barbarian Attack is combined with Catan for Two you may pay trade tokens to move a barbarian instead of moving the robber, costing 1 trade token if your victory point total is less than or equal to your opponent's and 2 trade tokens otherwise.
- When Barbarian Attack is combined with Catan for Two, a default die roll of "3" is used for the foreign knight when a roll is required after a victory, and the compensation for a removed knight is 2 gold plus 1 trade token instead of 3 gold.
- When Barbarian Attack is combined with the Catan Event Cards variant, the "Robber Attacks!" event lets the active player draw one random resource card from a player of his choice and forces every player with more than 7 resource cards to discard half of them rounded down, the "Robber Flees" event does not take place, and the "Conflict" event lets the single player who alone owns the most knights on the board take a random resource card from a player of his choice.

### Scenario: Traders & Barbarians (main scenario)

- Traders & Barbarians is the main scenario of the expansion, lasts about 90 minutes, and has players move wagons along roads to deliver commodities between three trade hexes for gold and victory points.
- The additional components for this scenario are 3 trade hexes (castle, quarry, and glassworks), 2 replacement sea frame pieces, 36 commodity tokens, 4 wagons (one per player), 20 baggage train cards (5 per player), 30 barbarian figures, 40 gold coins, and a special deck of 26 development cards.
- During preparation you assemble the frame and replace the two base game frame pieces labeled 1–2 and 5–6 with the two corresponding frame pieces provided in this expansion.
- During preparation you place the 3 trade hexes as shown in the scenario illustration so that the sea side of each trade hex matches up with a sea side of the frame.
- During preparation you remove the desert hex, one pasture hex, and one fields hex from play, and you remove the "2" and "12" number tokens from play.
- You never place a number token on a trade hex, and you place the remaining number tokens according to the base game set-up rules while skipping the trade hexes and leaving out tokens "2" (B) and "12" (H).
- During preparation you sort the 36 commodity tokens into 3 stacks by the building picture on their backs (castle, quarry, and glassworks), shuffle each stack separately, and place each stack face down beside its corresponding trade hex.
- The castle hex needs marble and glass delivered to it, and it produces tools from its smithy and sand from its shore.
- The quarry hex needs tools delivered to it, and it produces marble as well as sand from its shore.
- The glassworks hex needs sand delivered to it, and it produces glass and tools from its smithy.
- During preparation each player takes the set of 5 baggage train cards whose frame color matches his own color, stacks them face down sorted so the card backs run in sequence from 1 to 5, and turns the top card numbered 1 face up beside the stack as his active baggage train card.
- During preparation you place the 3 barbarians on the three paths marked with black crosses in the scenario illustration.
- During preparation you replace the base game development card deck entirely with this scenario's development card deck, which consists of 15 "Knight" cards, 3 "Road Building" cards, 3 "Swift Journey" cards, 1 "Toolmaking" card, 1 "Glassmaking" card, and 1 "Quarry" card.
- During preparation each player receives 5 gold.
- The "Longest Road" special card is not used in this scenario.
- The robber is not used at all in this scenario.
- During set-up each player places 1 settlement with a road and then 1 city with a road instead of a second settlement, and he still receives only 1 resource for each terrain hex adjacent to that starting city.
- Once you have built your starting city you place your wagon on that city's intersection.
- Each trade hex has a central plaza intersection carrying a building, and four interior paths lead from the trade hex's corners to that central plaza.
- You may build roads on the interior paths of a trade hex according to the usual road building rules.
- You may never build a settlement or city on the central plaza intersection of a trade hex.
- You may never build a road on any of the three paths of a trade hex that border the sea.
- You may build settlements and cities on the 4 land corners of a trade hex, observing the normal distance rule.
- After you finish trading and building during your turn, you may move your wagon from intersection to adjacent intersection along paths, spending movement points.
- Any number of wagons may occupy the same intersection at the same time.
- At the start of the game your wagon has 4 movement points available on each of your turns, and unused movement points are lost at the end of your movement.
- Moving your wagon along a path that has no road on it costs 2 movement points.
- Moving your wagon along a path that carries one of your own roads costs 1 movement point.
- Moving your wagon along a path that carries another player's road costs 1 movement point and additionally requires you to pay 1 gold to the owner of that road.
- Moving your wagon along any path that is occupied by a barbarian costs 2 additional movement points on top of the normal cost, so a roadless path with a barbarian costs 4 movement points and a road path with a barbarian costs 3 movement points.
- Once per turn you may pay exactly 1 grain to increase your wagon's movement points by 2 for that turn, and you may do so even after having already spent some or all of your movement points.
- Your wagon may stop and end its movement on any intersection it reaches.
- Your wagon must always stop and end its movement as soon as it moves onto the central plaza of a trade hex.
- If you do not have enough remaining movement points to complete a move along a path, you may not move partially along it and your wagon must end its movement on its current intersection.
- The first time you move your wagon you choose one of the 3 trade hexes as your initial destination, and you may change that initial destination freely until you arrive.
- When your wagon first reaches the central plaza of a trade hex you receive no gold because you carry no commodity, but you take the top commodity token from that trade hex's stack and turn it face up in front of you.
- The four commodity types are glass, marble, sand, and tools, and the commodity revealed on your token determines the trade hex your wagon must travel to next.
- Glass must be delivered to the castle hex, marble must be delivered to the castle hex, tools must be delivered to the quarry hex, and sand must be delivered to the glassworks hex.
- A player may carry only one commodity token at a time and may only draw another commodity token after completing the current delivery.
- When your wagon stops at the central plaza of the trade hex matching your commodity token, you must deliver that commodity by turning the token face down in front of you.
- Each delivered commodity token that lies face down in front of you is worth 1 victory point.
- For each delivery you also receive between 1 and 5 gold, and the exact amount is the gold value printed on your currently active baggage train card.
- Immediately after making a delivery you take and reveal a new commodity token from the stack of the trade hex you are standing on, and that new commodity determines your next destination.
- Your active baggage train card shows three values: your wagon's movement points, the gold you receive for each delivery, and the die roll numbers required to drive off a barbarian.
- Wagon movement points range from 4 on the first baggage train card up to 7 on the best baggage train cards, and delivery gold ranges from 1 up to 5 correspondingly.
- During trading and building on your turn you may upgrade your baggage train by paying the resources printed on the back of the top face-down card of your baggage train stack.
- When you upgrade your baggage train you turn that top card of the stack over and place it on top of your previous active card, and it becomes your new active baggage train card.
- Upgrading to the fifth and last baggage train card in your stack is worth 1 victory point, as indicated on that card.
- Barbarians may occupy paths with roads as well as paths without roads, and only 1 barbarian may occupy any given path.
- You are always allowed to build a road on a path that is occupied by a barbarian.
- If you do not have enough movement points to move past a barbarian, you must either stop on the intersection before the barbarian and lose your unused movement points, or move in another direction.
- You may only attempt to drive off a barbarian if you have upgraded your baggage train card at least once.
- To attempt to drive off a barbarian you pause your moving wagon on an intersection adjacent to that barbarian and roll one die.
- If the die result is one of the numbers shown on your active baggage train card, you may move that barbarian to any path or road not already occupied by another barbarian.
- Whether or not your attempt to drive off a barbarian succeeds, you may continue moving your wagon normally with any remaining movement points.
- Driving off a barbarian never lets you steal a resource card from another player.
- During each of your turns you may attempt to drive off any given barbarian only once.
- When you roll a "7" as your production roll you must move one of the 3 barbarians to any path not already occupied by a barbarian.
- If you move a barbarian onto a path occupied by a road when a "7" is rolled, you may draw one random resource card, but never gold, from the owner of that road.
- When a "7" is rolled every player holding more than 7 resource cards must select half of his resource cards, rounded down, and return them to the bank.
- When you roll a "2" or a "12" as your production roll you re-roll the dice, because no hex carries those numbers in this scenario.
- In this scenario the large gold coins are worth 5 gold each and the small gold coins are worth 1 gold each.
- Up to two times during your turn you may buy 1 resource card of your choice for 2 gold.
- You may trade gold for resource cards with other players and resource cards for gold with other players.
- You may use maritime trade to obtain gold at the usual rate of 4 identical resources for 1 gold, or 3 identical resources for 1 gold if you own the matching 3:1 harbor, and no 2:1 gold harbor exists.
- Gold does not count as a resource, so it is ignored when a "7" is rolled and it can never be taken with a "Monopoly" development card.
- The "Knight" development card in this scenario lets you move 1 barbarian to another road or path, and if you place him on a road you draw 1 resource card from the owner of that road.
- The "Road Building" development card in this scenario lets you place 2 new roads as if you had just built them normally.
- The "Swift Journey" development card in this scenario lets you move your wagon a second time on the same turn, after you have already moved it in the regular manner.
- The "Toolmaking", "Glassmaking", and "Quarry" development cards are each worth 1 victory point and are revealed on your turn if they bring you to the number of points required for victory.
- The Traders & Barbarians scenario ends when a player reaches a total of 13 or more victory points during his own turn.
- When Traders & Barbarians is combined with the Harbormaster variant, the game is played until a player reaches 14 victory points during his turn.
- When Traders & Barbarians is combined with Catan for Two, you return half of the gold you pay for using neutral roads to the bank, rounded up, and give the other half, rounded down, to your opponent.
- When Traders & Barbarians is combined with Catan for Two you may pay a trade token to move a barbarian to a path not occupied by a road or another barbarian, in place of the usual action of sending the robber to the desert.
- When Traders & Barbarians is combined with Catan for Two you take 1 trade token whenever you build a settlement adjacent to a trade hex, including during the set-up phase.
- When Traders & Barbarians is combined with the Catan Event Cards variant, the "Robber Attacks!" event instead makes you move one of the 3 barbarians to a free path with the usual card-drawing and discarding effects, the "Robber Flees" event does not take place, and the "Earthquake" event makes a road turned sideways cost 2 movement points to traverse, exactly as if it were a path without a road.

### Variant: The Friendly Robber

- The Friendly Robber is a variant that requires no additional components and can be played for the duration of whatever scenario it is added to.
- When a "7" is rolled or a knight card is played, the robber may not be moved to a terrain hex that is adjacent to a settlement belonging to a player who has only 2 victory points.
- If this restriction leaves no legal terrain hex for the robber, the robber is moved to the desert hex or remains on the desert hex.
- When the robber ends up on the desert hex because of this restriction, no resource card may be taken from any player who has only 2 victory points.
- Even when playing with The Friendly Robber, you still lose half of your resource cards when a "7" is rolled and you hold more than 7 resource cards.
- The Friendly Robber variant can be combined with all other Traders & Barbarians variants, all Traders & Barbarians scenarios, and all Seafarers scenarios without any rule changes.

### Variant: Catan Event Cards

- Catan Event Cards is a variant that replaces the production dice roll with a deck of 38 cards consisting of 36 event cards, 1 "New Year" card, and 1 brief rules card.
- To prepare the deck you separate out the brief rules card and the "New Year" card, shuffle the remaining 36 event cards, place 5 of the shuffled cards face down as the start of the deck, place the "New Year" card face down on top of those 5 cards, and place the remaining 31 shuffled cards face down on top of the "New Year" card.
- On your turn you do not roll the dice; instead you reveal the top card of the event deck, resolve any event shown on it first, and then produce resources using the number shown on the circular chit in the card's upper right corner.
- When the "New Year" card is revealed you immediately repeat the entire deck preparation process to build a new event deck, and you then reveal the top card of the new deck to continue your turn.
- Because 5 cards are set aside each time the deck is prepared, those 5 cards never appear before the next reshuffle, which keeps the final production numbers of a deck uncertain.
- If you prefer a perfect distribution of production numbers you may play through all 36 event cards without the "New Year" card and simply reshuffle once all cards have been used.
- The deck contains 6 "Robber Attacks!" cards, 2 "Epidemic" cards, 1 "Earthquake" card, 1 "Good Neighbors" card, 1 "Tournament" card, 1 "Trade Advantage" card, 2 "Calm Seas" cards, 2 "Robber Flees" cards, 2 "Neighborly Assistance" cards, 1 "Conflict" card, 1 "Plentiful Year" card, and 16 event-free "Catan Prospers" cards.
- The "Robber Attacks!" event carries production number "7", forces every player with more than 7 cards to discard half rounded down, and lets the active player move the robber and draw 1 random resource card from any one player with a settlement or city next to the robber's new hex.
- The "Epidemic" event appears on production numbers "6" and "8" and causes each player to receive only 1 resource for each of his cities that produces that turn.
- The "Earthquake" event appears on production number "6" and makes each player turn at most 1 of his roads sideways at a 90 degree angle.
- A player whose road is turned sideways by an "Earthquake" may not build any roads until he repairs that road by paying 1 lumber and 1 brick.
- A road turned sideways by an "Earthquake" still counts toward the "Longest Road", but no settlement may be built adjacent to a damaged road.
- The "Good Neighbors" event appears on production number "6" and makes each player give the player on his left 1 resource of the giver's choice, if he has one.
- The "Tournament" event appears on production number "5" and lets each player with the most revealed knight cards take 1 resource of his choice from the bank.
- The "Trade Advantage" event appears on production number "5" and lets the player holding the "Longest Road" card, or the single player with more roads than any other player if the card is unclaimed, take 1 resource card from any player.
- The "Trade Advantage" event is ignored if there is a tie in road count and no player has at least 5 roads, and it never allows taking a development card.
- The "Calm Seas" event appears on production numbers "9" and "12" and gives each player with the most harbors 1 resource card of his choice from the supply.
- The "Robber Flees" event appears on two cards with production number "4" and returns the robber to the desert without any player drawing a card.
- The "Neighborly Assistance" event appears on production numbers "10" and "11" and makes each player with the most victory points give 1 resource card of the giver's choice to a player with fewer victory points.
- A player affected by "Neighborly Assistance" who holds no resource card simply ignores that event.
- The "Conflict" event appears on production number "3" and lets the holder of the "Largest Army" card, or the single player with the most face-up knight cards if the card is unclaimed, take 1 random resource card from any one player.
- The "Conflict" event is ignored if there is a tie for face-up knight cards with fewer than 3 knights, and it never allows taking a development card.
- The "Plentiful Year" event appears on production number "2" and lets each player take 1 resource of his choice from the supply.
- The event-free cards carry production numbers "3", "4", two of "5", two of "6", four of "8", three of "9", two of "10", and "11", and they trigger no event at all.
- The Catan Event Cards variant can be combined with all other Traders & Barbarians variants, all Traders & Barbarians scenarios, and all Seafarers scenarios without rule changes.

### Variant: Harbormaster

- Harbormaster is a variant whose only additional component is the "Harbormaster" special victory point card, which is placed beside the board during preparation.
- A settlement located at a harbor gives its owner 1 harbor point.
- A city located at a harbor gives its owner 2 harbor points.
- The first player to acquire 3 harbor points immediately receives the "Harbormaster" special card, which is worth 2 victory points.
- If another player later acquires more harbor points than the current holder, that player immediately takes the "Harbormaster" card and its 2 victory points.
- When the Harbormaster variant is used with the plain Catan base game, the game ends and you win as soon as you have 11 or more victory points during your turn.
- Whenever the Harbormaster variant is added to any scenario, the number of victory points normally required for victory in that scenario is increased by one point.
- The Harbormaster variant can be combined with all other Traders & Barbarians variants, all Traders & Barbarians scenarios, and all Seafarers scenarios without further rule changes.

### Variant: Catan for Two Players

- Catan for Two is a variant for exactly two real players whose only additional components are 20 trade tokens, and it uses the two unused sets of playing pieces as two imaginary neutral players.
- During preparation you place the two sets of game pieces not chosen by the players beside the board to serve as the components of the two neutral players.
- During preparation you place the trade tokens beside the board and each real player receives 5 trade tokens.
- During set-up you place the terrain hexes only within the white area shown in the variant's illustration, rather than across the full board.
- During set-up each neutral player is given 1 settlement without a road, placed on one of the specific intersections marked in the variant's illustration.
- Each real player then builds 2 settlements and 2 roads according to the normal set-up rules, so after set-up each real player has 2 settlements and 2 roads while each neutral player has exactly 1 settlement.
- On your turn you roll the dice twice in a row, and the two results must differ, so you re-roll the second roll as many times as necessary to obtain a different result.
- Immediately after each of the two dice rolls, both real players obtain resources normally, or the robber is moved if the result was a "7".
- Whenever you build a road or a settlement, you must also build for free either 1 road or 1 settlement for one of the two neutral players of your choice.
- If there is no legal settlement location for the neutral players when you owe them a build, you must build a road for a neutral player instead.
- Building a city or buying a development card never triggers any building for the neutral players.
- The neutral players never receive any resources, but a neutral player can hold the "Longest Road" card.
- On your turn you may spend trade tokens to take the "Forced Trade" action, in which you draw 2 random cards from your opponent's hand and give him 2 cards of your choice from your own hand in exchange.
- If your opponent has only 1 card when you take the "Forced Trade" action, you may take that single card but you must still give him 2 cards in exchange.
- On your turn you may spend trade tokens to take the "Move Robber" action, which moves the robber to the desert hex.
- Any trade token action costs 1 trade token if your victory point total is less than or equal to your opponent's total, and it costs 2 trade tokens otherwise.
- Trade tokens spent on actions are returned to the supply.
- Once during your turn you may discard one of your face-up knight cards to take 2 trade tokens in exchange.
- If discarding a knight card for trade tokens leaves you with only 2 face-up knight cards, or with no more face-up knight cards than your opponent, you must set the "Largest Army" card aside, and thereafter the player with the most face-up knight cards and at least 3 of them takes it.
- When you build a settlement adjacent to the desert hex you take 2 trade tokens, and this also applies during the set-up phase.
- When you build a settlement on the coast you take 1 trade token, and this also applies during the set-up phase.
- When you build a settlement adjacent to both the desert hex and the coast you take 3 trade tokens, and this also applies during the set-up phase.
- The Catan for Two variant can be combined without rule changes with all other Traders & Barbarians variants and with any Traders & Barbarians or Seafarers scenario in which the "Largest Army" is not excluded.
- When Catan for Two is combined with the Catan Event Cards variant you draw two event cards on your turn instead of rolling the dice, and if the second card shows the same production result as the first, no further cards are drawn and that production result is simply applied twice.

### Note on scope

- "The Great Caravan" and "Enchanted Land" are not part of the Catan: Traders & Barbarians box and should not be implemented as Traders & Barbarians content, because the official expansion contains exactly five campaign scenarios (The Fishermen of Catan, The Rivers of Catan, The Caravans, Barbarian Attack, and Traders & Barbarians) and four variants (The Friendly Robber, Catan Event Cards, Harbormaster, and Catan for Two).
## Explorers & Pirates

### Fundamental Differences from Base Catan
- Catan: Explorers & Pirates uses the base Catan rules as its foundation, but replaces several of them with new mechanisms and requires the board frame pieces introduced in the 4th edition of Catan.
- Settlements can never be upgraded to cities in Explorers & Pirates, and the city pieces from base Catan are not used at all.
- There are no development cards in Explorers & Pirates, so no knight, progress, or victory point development cards exist.
- There are no "Longest Road" and "Largest Army" special victory point cards in Explorers & Pirates.
- There is no robber piece in Explorers & Pirates, and no hex is ever blocked from producing resources by a robber.
- Whenever a "7" is rolled, every player holding more than 7 resource cards must still discard half of their cards rounded down, exactly as in base Catan.
- Starting with the second scenario, a player-owned pirate ship replaces the robber and performs many of the same functions as the classic robber.
- There are no harbors of the base Catan type printed on the board frame, so the 2:1 and 3:1 harbor trades of base Catan do not exist.
- A player wins immediately on their own turn as soon as they reach the victory point total required by the scenario being played.
- Victory points are awarded for building regular settlements and harbor settlements, and additional victory points are earned by making progress on missions.
- A regular settlement is worth 1 victory point, exactly as in base Catan.
- The game uses the base Catan terrain hexes and resource cards, plus new hex types, gold coins, fish hauls, and spice sacks introduced by this expansion.
- Each player uses the following Explorers & Pirates pieces in addition to base Catan settlements and roads: 4 harbor settlements, 3 ships, 2 settlers, 9 crews, 3 markers, and 1 pirate ship.

### Turn Structure
- Each turn consists of a production phase, then a trade and build phase, and finally a movement phase, in that fixed order.
- On your turn you roll the two dice for production as usual, and the result produces resources for all players.
- If a production die roll produces no resources at all for you, and the roll was not a "7", you receive 1 gold from the supply as compensation.
- After the production phase you may trade and build in any order you wish, and you may alternate freely between trading and building.
- On your turn you may trade resources with the supply at a 3:1 rate by returning 3 resources of the same type and taking any 1 different resource of your choice.
- On your turn you may also obtain 1 gold from the supply by paying 3 resources of the same type.
- Twice during your turn you may pay 2 gold to the supply to buy any 1 resource of your choice.
- You may trade gold with your opponents in the same way that you trade resource cards.
- During your movement phase you may move all of your ships and perform actions with them.
- You are not allowed to trade or build during or after your movement phase, with the single exception of building a settlement with the aid of a settler ship.
- Your turn ends after your movement phase is complete.

### Ships and Movement
- A ship costs 1 lumber and 1 wool to build.
- A ship is a transport unit that carries game pieces in its hold and is not a road-like connector, so ships never form routes or chains between settlements.
- Each ship has a hold that can accommodate either 1 large game piece (a settler or a fish haul) or 2 small game pieces (crews or spice sacks).
- When you build a ship you must place it on a sea route directly adjacent to one of your own harbor settlements.
- Ships are moved along sea routes, which are the edges of sea hexes, including edges that separate a sea hex from a terrain hex and edges of frame pieces that border sea hexes or terrain hexes.
- You may not build a ship on a sea route adjacent to an undiscovered hex, because doing so would immediately trigger the discovery of that hex.
- If all of your ships are already on the board and you want to build a new one, you may remove any 1 of your ships from the board and build the new ship adjacent to one of your harbor settlements for the usual cost of 1 lumber and 1 wool.
- Any pieces in the hold of a ship that you remove from the board in order to rebuild it are lost and returned to the appropriate supply.
- You may only move your ships during your own movement phase.
- Each ship has 4 movement points, and moving a ship from one sea route to an adjacent sea route costs 1 movement point.
- You may move a ship in any direction and may change direction during its movement, including moving forward and then back to the same sea route.
- You must complete the movement of one ship before you begin moving your next ship.
- Once during your turn, for each individual ship, you may spend 1 wool card to buy 2 additional movement points for that ship.
- Up to 2 ships may occupy the same sea route at once, and those ships may belong to the same player or to different players.
- You may move your ship past another ship or past 2 side-by-side ships, but your ship's movement may not end on a sea route already occupied by 2 ships.
- Loading and unloading a ship costs no movement points, and you may continue moving that ship afterwards as long as it still has movement points remaining.
- You may remove a game piece from one of your ships at any time and return it to the appropriate supply, for example to make room for a more valuable piece.

### Exploration and Discovery
- The unexplored areas of the board consist of hexes placed face down with only an icon showing, using green moon icons for the northern unexplored area and orange sun icons for the southern unexplored area.
- To discover new land you must move one of your ships toward an unexplored area of the board.
- If, after moving a ship, either end of that ship (its bow or its stern) points toward the corner of an undiscovered hex, you must immediately discover that hex.
- To discover a hex you turn it face up, and if it is a terrain hex you take a number token from the stack whose icon matches the icon on the back of that hex and place it number side up on the hex.
- If you discover a terrain hex, you immediately receive 1 resource of the type produced by that hex as your reward.
- If you discover any other type of hex, whether land or sea, you immediately receive 2 gold as your reward.
- After making a discovery you may not move that ship any farther on this turn, and all of its remaining movement points are forfeited.
- Roads may not be built on paths adjacent to undiscovered hexes, and settlements may not be built on intersections adjacent to undiscovered hexes.
- Building a road whose end points toward an undiscovered hex does not discover that hex, because hexes can only ever be discovered by means of ships.

### Harbor Settlements
- A harbor settlement costs 2 grain and 2 ore and is built by upgrading one of your existing coastal settlements.
- A settlement counts as coastal, and is therefore eligible to become a harbor settlement, if it borders a sea hex or the board frame.
- To build a harbor settlement you pay the cost, return the regular settlement to your supply, and replace it on the board with a harbor settlement piece.
- A harbor settlement is worth 2 victory points.
- When the number of a terrain hex adjacent to your harbor settlement is rolled, you receive only 1 resource from that hex, because harbor settlements do not produce double resources the way cities do in base Catan.
- Each harbor settlement has a basin that can hold either 1 large game piece (a settler or a fish haul) or 2 small game pieces (crews or spice sacks).
- Harbor settlements are the only places where you may build new ships, settlers, and crews, since all of those pieces must be placed at or adjacent to one of your harbor settlements.

### Settlers and Founding Settlements
- You can build a settlement in two ways: along a road exactly as in base Catan, or by landing a settler ship at a coastal intersection.
- You must observe the normal Catan distance rule of at least 2 paths between settlements in both methods of building a settlement.
- Building a settler costs the same resources as building a settlement, which is 1 lumber, 1 brick, 1 grain, and 1 wool.
- When you build a settler you must place it either into the empty basin of one of your harbor settlements or directly into the empty hold of one of your ships that is on a sea route adjacent to one of your harbor settlements.
- You are never allowed to place a newly built settler directly onto land.
- A ship that has a settler in its hold is called a settler ship.
- If the harbor basin and the hold of an adjacent ship are both occupied by other game pieces, you may only build a settler by first removing one of those pieces and returning it to your supply.
- You are not allowed to move a settler overland, and settlers can only ever be transported by your own ships.
- If either end of one of your empty ships points toward one of your harbor settlements that contains a settler, you may load that settler onto the ship.
- Loading a settler onto a ship does not end that ship's movement, and the ship may continue moving if it has movement points left.
- If either end of one of your settler ships points toward the corner of a terrain hex, you may build a settlement at that intersection.
- To build a settlement with the aid of a settler ship you return both the ship and the settler in its hold to your supply, and then place the new settlement on that intersection at no additional resource cost.
- In each of the two unexplored areas of the board, your very first settlement in that area can only be built by using a settler ship.
- Once you have established your first settlement in an unexplored area, you may build roads and further settlements there in the regular fashion, or you may continue to found settlements there with additional settler ships.

### Crews
- A crew costs 1 ore and 1 wool to build.
- Crews represent specialists who ride on your ships and who act as merchants, warriors, or both depending on the mission being played.
- To build a crew you pay the cost and place the crew either on a free space in the basin of one of your harbor settlements or in the hold of one of your ships that is on a sea route adjacent to one of your harbor settlements.
- An empty harbor settlement basin or an empty ship hold can accommodate up to 2 crews.
- A crew placed in a harbor settlement basin can later be picked up by one of your ships during your movement phase, transported to a destination, and unloaded there.
- After loading or unloading a crew you may continue to move that ship as long as it still has movement points.
- Crews may only be transported by your own ships, and you are never allowed to move a crew overland along paths or roads.
- You may only place a crew on a specific mission destination, such as an active pirate lair token or the village of a spice hex, and you may never place a crew on any hex that does not contain such a destination.

### Transshipping
- If either end of one of your loaded ships points toward one of your loaded harbor settlements, you may swap the game pieces between that ship's hold and that harbor settlement's basin.
- You are not allowed to transship game pieces directly between 2 ships.
- You may transship pieces between 2 ships indirectly by having both ships point an end toward the same harbor settlement and using that harbor settlement's basin as temporary storage.

### Pirate Ships
- Each player has 1 pirate ship in their supply, and only one pirate ship can be on the board at any time.
- If you are the first player to roll a "7", you place your own pirate ship on any allowed sea hex.
- You may never place a pirate ship on a sea hex adjacent to the starting island.
- You may never place a pirate ship anywhere on the outside frame of the board, meaning frame pieces A1, A2, B1, B2, B3, or the 6 frame pieces from base Catan.
- If you roll a "7" and your own pirate ship is already on the board, you must move it to another allowed sea hex.
- If you roll a "7" and an opponent's pirate ship is on the board, you return that pirate ship to its owner's supply and place your own pirate ship on any allowed sea hex, including the hex the opponent's pirate ship just left.
- When you place your pirate ship on a sea hex, you may steal 1 random resource card from the face-down hand of an opponent who has a ship on a sea route of that hex.
- Settlements and harbor settlements are never affected by the pirate ship, which only threatens ships.
- If, and only if, the targeted opponent has no resource cards at all, you may take 1 gold from that opponent instead.
- If you move one of your ships onto, along, or off of a sea route belonging to a hex occupied by an opponent's pirate ship, you must pay a tribute of 1 gold to the supply.
- You must pay a separate tribute of 1 gold for each individual ship that you move in this way during your turn.
- Once you have paid the tribute for a given ship, that ship may move along, onto, and off of any number of the pirate hex's sea routes for the remainder of your current turn.
- You may build a new ship on a sea route adjacent to a hex occupied by a pirate ship without paying tribute, because building is not moving, but you must pay the tribute if you then wish to move that newly built ship.
- You must pay the pirate tribute even if you have already spent 4 gold to buy 2 resources during your trade and build phase.
- You never pay tribute to your own pirate ship.

### Chasing Away a Pirate Ship
- To attempt to chase away an opponent's pirate ship you must have at least one battle-ready ship.
- A ship is battle-ready only if it has not moved at all on this turn and one of its ends is directly adjacent to one of the six intersections of the sea hex occupied by the pirate ship.
- During your movement phase, each of your battle-ready ships may make exactly 1 attempt to chase away an opponent's pirate ship.
- To chase away a pirate ship you roll 1 die for each of your battle-ready ships, and a result of "6" means you have successfully chased the pirate ship away.
- When you successfully chase away a pirate ship you return it to its owner, then place your own pirate ship on any allowed sea hex and steal 1 resource card from the owner of a ship adjacent to that hex.
- A ship that was used in an attempt to chase away a pirate ship may still be moved normally afterwards.
- If you fail to chase away the pirate ship, you must pay the normal tribute to move your ship along the sea routes of the pirate hex, or else you may not use those sea routes at all.

### Gold
- Gold coins come in denominations of 1 and 3, and gold is a currency separate from resource cards.
- You receive 1 gold from the supply whenever a production roll other than a "7" gives you no resources at all.
- You receive 2 gold whenever you discover a sea hex, a gold field hex, a fish shoal hex, or a spice hex.
- You may pay 3 identical resource cards to the supply to receive 1 gold.
- You may pay 2 gold to the supply to buy 1 resource of your choice, and you may do this at most twice per turn.
- Gold is used to pay the 1 gold tribute demanded by an opponent's pirate ship.
- Gold can be traded freely with opponents in the same way as resource cards.

### Missions in General
- Every scenario except "Land Ho!" is played with between 1 and 3 missions, and when several missions are in play you may work on all of them at the same time.
- Each mission has its own mission card and its own victory point card, which are placed beside the game board at the start of the game.
- At the beginning of the game each player places 1 of their markers on the starting space, marked "S", of every mission card in use.
- Whenever you make progress on a mission, you move your marker forward 1 space on that mission card's track.
- If the space you move your marker onto already contains one or more opponents' markers, you place your marker on top of them.
- The number of victory point symbols depicted next to the space your marker occupies indicates how many mission victory points you have accumulated on that mission.
- If your marker has moved farther from the "S" space than every other player's marker on that mission, you receive that mission's victory point card, which is worth 1 additional victory point.
- If several markers are stacked on the most advanced space of a mission track, the marker on the bottom of the stack receives the mission's victory point card, because it arrived there first.
- The mission victory point card can change hands during the game whenever another player takes the lead on that mission track.

### Pirate Lairs Mission
- The Pirate Lairs mission tasks you with locating the gold field hexes hidden in the unexplored areas and capturing the pirate lairs that occupy them.
- Every gold field hex you discover is always occupied by a pirate lair.
- When you discover a gold field hex you immediately receive 2 gold, then take a pirate lair token from the stack and place it face down, without turning it over, onto that gold field hex.
- As long as an unturned pirate lair token sits on a gold field hex, that hex is called a pirate lair hex, and you may not build a road on its edges or a settlement on its corners.
- If your ship has 1 or 2 crews on board and one end of that ship points toward an intersection of a pirate lair hex, you may place those crews directly onto the pirate lair token.
- A maximum of 3 crews may stand on a single pirate lair at one time.
- As soon as the 3rd crew piece is placed on a pirate lair, that lair is captured, and the crews on it do not all have to belong to the same player.
- The results of a pirate lair capture are resolved after the capturing player has finished their movement phase.
- Each player who had a crew on the captured pirate lair immediately receives 2 gold as a reward.
- Each player who had a crew on the captured pirate lair also moves their marker forward 1 space on the "Pirate Lairs" mission card, starting with the player whose turn it is and continuing clockwise.
- To determine the hero of the battle, each participating player rolls 1 die and adds the number of their own crews that were on the pirate lair to the result.
- The participating player with the highest total is the hero of the battle, moves their marker forward 1 additional space on the "Pirate Lairs" mission card, and must remove 1 of their crews and return it to their supply.
- If the hero totals are tied, the player who had placed more crews on the lair is the hero, and if that is also tied the tying players repeat the die roll.
- If you capture a pirate lair entirely by yourself, you automatically become the hero, move your marker forward 1 additional space, and lose 1 of your crews.
- After a capture is resolved, the pirate lair token is flipped over so that its number side faces up, and the surviving crews are slid aside and placed next to the flipped token.
- You may pick up your surviving crews from beside a captured lair with one of your ships on a subsequent turn.
- Once a pirate lair has been captured, you may build roads on the edges of the liberated gold field and settlements or harbor settlements on its intersections.
- When a liberated gold field's number is rolled during a production roll, each player receives 2 gold for every settlement or harbor settlement they have on an intersection bordering that gold field.

### Fish for Catan Mission
- The Fish for Catan mission tasks you with locating fish shoal hexes, catching fish hauls there, and delivering them to the docks of the Council of Catan.
- The Council of Catan occupies a special island stronghold hex just off the eastern shore of the starting island, and this hex counts as a sea hex.
- No roads may be built on the 5 edges of the Council of Catan hex that border other sea hexes, and no settlements or harbor settlements may be built on its 4 sea-only intersections.
- You may build on the single edge and the intersections of the Council of Catan hex that border the starting island.
- A pirate ship may never be placed on the Council of Catan hex, because that hex borders the starting island.
- When you discover a fish shoal hex you immediately receive 2 gold, and that hex shows a die result from 1 to 6 in addition to its fish.
- Once during your movement phase you may roll 1 die to attempt to place a fish haul, and you may make this roll either before you move a ship or after you have finished moving a ship, but never in the middle of a ship's movement.
- If your fish placement roll matches the number shown on any discovered fish shoal hex, you take 1 fish haul from the supply and place it on that hex.
- You may not place a fish haul on a fish shoal hex that already has a fish haul on it, and you may not place a fish haul on a fish shoal hex occupied by a pirate ship.
- If you roll the number of a fish shoal hex that has not yet been discovered, no fish haul is placed.
- If the supply of fish hauls is depleted, you may not roll the die for fish haul placement at all.
- You may catch a fish haul if either end of one of your empty ships points toward a fish shoal hex that has a fish haul on it, in which case you take the fish haul from the hex and put it in your ship.
- A fish haul completely fills a ship's hold, so no further game pieces may be loaded onto that ship until the haul has been delivered.
- After catching a fish haul you may continue moving that ship if it still has movement points remaining.
- The Council of Catan hex has 2 docks marked with anchor symbols, and if either end of your fish-laden ship points toward one of these docks you may unload the fish haul there.
- To deliver a fish haul you return it to the supply and move your marker forward 1 space on the "Fish for Catan" mission card.
- After unloading a fish haul you may continue moving that ship if it still has movement points remaining.
- If a pirate ship is placed on a fish shoal hex that contains a fish haul, that fish haul is removed and returned to the supply.
- A pirate ship never steals fish hauls from the holds of adjacent ships.

### Spices for Catan Mission
- The Spices for Catan mission tasks your crews, acting as merchants, with befriending the villages on spice hexes and delivering the spice sacks they trade you to the Council of Catan.
- When you discover a spice hex with one of your ships you receive 2 gold, and you then place as many spice sacks on that hex's village as there are players in the game.
- If either end of one of your crew-laden ships points toward a corner of a spice hex, you may place 1 crew on that hex's village and in exchange load 1 spice sack onto that ship.
- You may place only 1 of your crews on each spice hex, and in exchange for that crew you may take exactly 1 spice sack from that hex.
- Once a crew has been placed on a spice hex village it must stay there permanently and can never be picked up by a ship again.
- You may not build a road on a spice hex's edges or a settlement at its corners until you have placed a crew on that spice hex.
- If either end of one of your spice-laden ships points toward either of the docks on the Council of Catan hex, you may unload the spice sacks there.
- For each spice sack you deliver to the Council of Catan you move your marker forward 1 space on the "Spices for Catan" mission card, and the delivered sacks are then removed from the game.
- After loading or unloading a spice sack you may continue moving that ship if it still has movement points remaining.
- Placing a crew on a spice hex village permanently grants you the advantage depicted on that hex, and the advantage may be used immediately during the same turn.
- Each of the three spice hex advantages is available from exactly 2 villages, one located in the northern unexplored area and one located in the southern unexplored area.
- The "Swift Voyage" advantage permanently increases the movement points of all of your ships by 1, so a single Swift Voyage village gives all your ships 5 movement points instead of 4.
- If you are friends with both "Swift Voyage" villages, all of your ships have 6 movement points per turn.
- With both "Swift Voyage" villages and the 1 wool payment for 2 extra movement points, the maximum number of movement points a single ship can have in one turn is 8.
- The "Swift Voyage" advantage can be applied immediately to the same ship that delivered the crew to the village, provided that ship did not itself just discover that hex.
- The "Pirate Bonus" advantage is shown on 2 villages, one depicting a die face of 5 pips and the other depicting a die face of 4 pips, and befriending one of them lets you chase away a pirate ship by rolling either a "6" or that village's depicted number.
- If you are friends with both "Pirate Bonus" villages, you chase away an opponent's pirate ship on a roll of "6", "5", or "4".
- The "Fast Gold" advantage lets you sell any 1 resource card from your hand to the supply for 1 gold once during your trade and build phase.
- If you are friends with both "Fast Gold" villages, you may sell 1 resource for 1 gold twice during your trade and build phase.

### Scenario: Land Ho!
- "Land Ho!" is the introductory scenario and teaches harbor settlements, ships, settlers, and discovery, and it takes roughly 30 minutes to play.
- "Land Ho!" is played without missions, without crews, without pirate ships, without fish, and without spices.
- In "Land Ho!" each player takes 5 settlements, 15 roads, 4 harbor settlements, 3 ships, 2 settlers, 2 gold, and 1 building costs card.
- In "Land Ho!" the starting positions are predetermined, and each player places 1 harbor settlement, 1 settler ship, 1 regular settlement, and 1 road at the locations shown in the setup example.
- In "Land Ho!" each player receives one resource card for each terrain hex adjacent to their starting settlement.
- In a two-player game of "Land Ho!" the pieces of the two unchosen colors remain on the starting island as obstacles, and only the settler ships of those unchosen colors are removed.
- You win "Land Ho!" if you reach 8 victory points on your turn.

### Scenario: Pirate Lairs
- "Pirate Lairs" is the second scenario and adds crews, transport, pirate ships, and the Pirate Lairs mission to the rules of "Land Ho!".
- In "Pirate Lairs" each player takes 5 settlements, 15 roads, 4 harbor settlements, 3 ships, 2 settlers, 9 crews, 1 pirate ship, 1 marker, and 2 gold.
- In "Pirate Lairs" the six pirate lair tokens are shuffled number side down and placed as a face-down stack beside the board.
- "Pirate Lairs" uses the free set-up method, in which each player first places a harbor settlement and then a regular settlement on the starting island, each without a road.
- In the free set-up your harbor settlement must be placed on one of the intersections specially marked with a circle in the setup example, while your regular settlement may be placed on any legal intersection.
- In the free set-up your starting resources are 1 card from each terrain hex adjacent to your starting regular settlement, and not from your harbor settlement.
- In the free set-up the last player to place a settlement is the first to place a road adjacent to that settlement and then a settler ship on a sea route adjacent to their harbor settlement, with the other players following in clockwise order.
- In a two-player game using the free set-up, each player additionally places one harbor settlement and one regular settlement of a neutral, unchosen color after placing their own.
- You win "Pirate Lairs" if you have 12 victory points on your turn.

### Scenario: Fish for Catan
- "Fish for Catan" is the third scenario and is played with both the "Pirate Lairs" mission and the "Fish for Catan" mission at the same time.
- "Fish for Catan" replaces the D1 sea hex with the D2 "Council of Catan" hex, which serves as the delivery point for fish hauls.
- In "Fish for Catan" each player takes 5 settlements, 15 roads, 4 harbor settlements, 3 ships, 2 settlers, 9 crews, 1 pirate ship, 2 markers, and 2 gold.
- In "Fish for Catan" each player places one of their markers on the "S" space of the "Pirate Lairs" mission card and one on the "S" space of the "Fish for Catan" mission card.
- "Fish for Catan" uses the free set-up method introduced in the "Pirate Lairs" scenario.
- You win "Fish for Catan" if you have 15 victory points on your turn.

### Scenario: Spices for Catan
- "Spices for Catan" is the fourth scenario and is played with both the "Fish for Catan" mission and the "Spices for Catan" mission, while the "Pirate Lairs" hexes and tokens are removed from the game.
- In "Spices for Catan" each player takes 5 settlements, 15 roads, 4 harbor settlements, 3 ships, 2 settlers, 9 crews, 1 pirate ship, 2 markers, and 2 gold.
- In "Spices for Catan" the 24 spice sacks and the 6 fish hauls are placed beside the board, and each player places one marker on the "S" space of each of the two mission cards in play.
- "Spices for Catan" uses the free set-up method introduced in the "Pirate Lairs" scenario.
- You win "Spices for Catan" if you have 15 victory points on your turn.

### Scenario: Explorers & Pirates
- "Explorers & Pirates" is the fifth and final scenario, it is the most epic in scope, and it includes all three missions "Pirate Lairs", "Fish for Catan", and "Spices for Catan" simultaneously.
- "Explorers & Pirates" uses every rule introduced in scenarios 1 through 4 without exception.
- In "Explorers & Pirates" each player takes 5 settlements, 15 roads, 4 harbor settlements, 3 ships, 2 settlers, 9 crews, 1 pirate ship, 3 markers, and 2 gold.
- In "Explorers & Pirates" the three mission cards and their three victory point cards are placed beside the board, and each player places one of their three markers on the "S" space of each mission card.
- In "Explorers & Pirates" each unexplored area is built from 7 standard hexes, 3 fish shoal hexes, 3 spice hexes, and 3 pirate lair hexes of the matching icon, shuffled together and placed icon side up.
- "Explorers & Pirates" uses the free set-up method introduced in the "Pirate Lairs" scenario.
- You win "Explorers & Pirates" if you have 17 victory points on your turn.
## Mini-Expansions, Scenario Packs, and Official Variants

### 5-6 Player Extension
- The CATAN 5-6 Player Extension requires the CATAN base game and lets you play CATAN with five or six players instead of three or four.
- The extension adds 11 terrain hexes, consisting of 1 desert plus 2 each of forest, hills, pasture, fields, and mountains, so that the island is built from 30 land hexes in total.
- The extension adds 4 small sea frame pieces, of which 2 carry harbors and 2 are all-sea, and these are inserted into the base game frame to enlarge the board.
- The small all-sea frame piece is placed between the "2-2" joint of the base game frame pieces, the small 2:1 wool harbor piece is placed between the "3-3" joint, the small 3:1 harbor piece is placed between the "5-5" joint, and the second small all-sea piece is placed between the "6-6" joint.
- The extension adds 28 number tokens whose back sides carry dark brown letters, and in a 5-6 player game you use only these tokens and none of the base game's number tokens.
- The extension's number tokens run from "A" through "Y" and then continue with the three double-lettered tokens "ZA", "ZB", and "ZC".
- The extension adds 10 settlements, 30 roads, and 8 cities, so that each of the five or six players receives 5 settlements, 4 cities, and 15 roads exactly as in the base game.
- The extension adds 25 resource cards and 9 development cards, which are shuffled into or stacked with the base game's cards to form the enlarged supply.
- The extension adds 2 optional harbor pieces, giving a total of 11 harbor pieces when combined with the 9 from the base game.
- To build the island for experienced players, you shuffle all 30 terrain hexes face down, place them face down inside the frame, and then turn them face up without changing their positions.
- You place the number token labeled "A" on any one of the six corner hexes and then continue placing tokens in alphabetical order along a spiral that starts on the outer ring and proceeds counter-clockwise toward the center of the board.
- When the spiral of number tokens reaches a desert hex, you skip that hex without placing a token and continue the sequence on the other side of it.
- You place the robber on either of the two desert hexes at the start of the game.
- As an optional setup step, you may shuffle all 11 harbor pieces face down and place them randomly on top of the harbor positions printed on the frame.
- Each player rolls the dice to determine the starting player, and then all players place their first two settlements and two roads and receive starting resources using the normal base game setup method.
- In a first 5-player game using the recommended beginner layout, one color remains inactive, its settlements stay on the board as neutral obstacles, and its roads are removed from the board.
- To determine the inactive color in that beginner 5-player game, one player takes 1 road of each color and hides them in a closed hand, each player draws 1 road at random unseen, and the color of the road left over is the inactive color.
- The victory point target in a 5-6 player game is unchanged from the base game, so you win as soon as you are the first player to reach 10 or more victory points on your own turn.
- The extension's components can be separated from the base game components because the 5-6 player terrain hexes carry a watermark icon in their lower left corner and the 5-6 player number tokens have dark brown letters on their backs rather than black.

### 5-6 Player Extension: Paired Players Turn (2022 revision)
- The 2022 revision of the 5-6 Player Extension replaces the older Special Build Phase entirely with the paired players turn rule.
- At the start of the game, the starting player takes the "player 1" marker and places it in front of themselves.
- The "player 2" marker is placed in front of the third player to the left of player 1, in both 5-player and 6-player games.
- Player 1 rolls the production dice for the turn, and all players receive their resources or resolve a rolled "7" exactly as in the base game.
- Player 1 then takes their trade and build phase, in which they may trade resource cards with all other players, trade with the supply, build any structures they can afford, and play 1 development card.
- Player 1 must fully complete their portion of the paired turn before player 2 may begin their portion.
- Player 2 may then trade resource cards only with the supply and may never trade with other players during their portion of the paired turn.
- Player 2 may build anything shown on their building costs card and may play 1 development card, including a victory point card played to win the game.
- After player 2 finishes, both markers are passed one seat to the left, player 1 also passes the dice, and the new player 1 begins a new turn.
- If both player 1 and player 2 would reach 10 or more victory points during the same paired turn, player 1 wins the game before player 2 is allowed to take their portion of that turn.

### Variant: Special Build Phase (classic 5-6 player rule)
- In editions of the 5-6 Player Extension published before the 2022 revision, the turn sequence is roll the dice, then the trade and build phase, then the end of the active player's turn, then the special build phase.
- The special build phase occurs after the active player's turn is finished and therefore takes place between the turns of two players.
- Every player other than the player who just finished their turn may participate in the special build phase.
- The players take their special build turns in clockwise order, beginning with the player to the left of the player who just finished their turn.
- On your special build turn you may build roads, settlements, and cities and you may buy development cards, using only the resource cards already in your hand.
- During the special build phase you may not trade with other players and you may not use maritime or harbor trade with the supply.
- During the special build phase you may not play a development card, because development cards may only be played on your own turn while you hold the dice.
- Because you may only spend resources you already hold during the special build phase, you are advised to trade as much and as advantageously as possible with the active player during that player's trade phase.

### Helpers of Catan
- Helpers of Catan is a scenario for 3 to 6 players that requires the CATAN base game and can also be used with CATAN: Seafarers and with the 5-6 Player Extension.
- The scenario adds 10 double-sided helper cards, and except where the scenario states otherwise all normal CATAN rules apply.
- Each helper card has a blue "A" side and a red "B" side, and six of the helper cards additionally show a number on their "A" side.
- During setup you make a face-up stack of the six numbered cards in numerical order so that A1 is on top, followed by A2, A3, and so on.
- The four remaining helper cards are placed beside the board to form the display, and cards in the display are always kept "A" side up.
- As soon as you build your second settlement and road during the setup phase, you take the top card of the numbered stack and place it in front of yourself "A" side up.
- Once every player has taken a starting helper card, any helper cards still left in the numbered stack are added to the display beside the board.
- You always have exactly one helper card in front of you at all times during the game, never more and never fewer.
- After you have used your helper's advantage and the card is on its "A" side, you may turn the card over to its "B" side and keep it in front of you so that you can use it a second time on a later turn.
- After you have used your helper's advantage and the card is already on its "B" side, you must return it to the display and take a different helper from the display, placing that new helper "A" side up in front of yourself.
- When you exchange a helper you may not take back the card you just returned to the display.
- You may never use a helper card during the same turn on which you received it.
- You may never use your helper card more than once during a single turn.
- When playing with 5 or 6 players, you may never use a helper card during the special building phase.
- The helper Candamir lets you, once during your turn, substitute any 1 resource of your choice for 1 of the 3 resources needed to buy a development card, and additionally lets you draw the top 3 development cards, keep 1 of them, and return and reshuffle the other 2.
- The helper Hilde lets you, once during your turn and after your production roll has been resolved, choose an opponent with more victory points showing on the board than you have, look at that player's hand of resource cards, and take 1 resource card of your choice from it.
- The helper Jean lets you choose 1 resource type during your turn and then exchange that resource type with the supply at a 2:1 rate as often as you like during that turn.
- The helper Lin lets you, once during your turn and either before or after resolving your production roll, move the robber from a terrain hex to the desert and then receive 1 resource of the type produced by the hex the robber vacated.
- After using Lin's advantage you do not get to steal a resource card from a player who has a settlement or city adjacent to the desert.
- Lin's advantage may not be used in the middle of resolving a roll, so once you have rolled the dice you must first take your resource cards or completely resolve a "7" before you may use it.
- The helper Louis lets you, once during your turn, remove 1 of your roads from the board and rebuild it elsewhere for free, but only a road with at least 1 of its 2 ends not connected to any of your other pieces.
- When checking whether Louis may move a road, you ignore your opponents' pieces and consider only your own connections.
- When playing Louis with CATAN: Seafarers, a road connected at one end to one of your ships may also be moved provided that the ship was built from the other direction, and such a road and ship count as connected only when your own settlement stands between them.
- The helper Marianne lets you, on any turn, take any 1 resource card of your choice whenever a production roll is not a "7" and yields you no resources at all.
- Marianne's advantage is always used before any other helper is used by one of your opponents in response to the same roll.
- The helper Nassir lets you, once during your turn, declare a resource type and choose 1 or 2 opponents who must each give you 1 card of the declared type if they have it, after which you must give each of those players 1 resource card of your choice in return.
- The helper Sean lets you, on any turn when a "7" is rolled, either avoid discarding any cards even though you hold more than 7 resource cards, or take any 1 resource of your choice from the supply if you hold 7 or fewer resource cards.
- The helper Vincent lets you, once during your turn, discard 1 already-played knight card in order to build 1 settlement for only 1 lumber plus 1 brick, or to upgrade 1 settlement to a city for only 2 ore plus 1 grain.
- The knight card discarded for Vincent's advantage must be a knight card that you have already played face up.
- The helper William lets you, once during your turn, build a road while substituting any 1 resource of your choice for either the lumber or the brick normally required.

### Frenemies
- Catan Scenarios: Frenemies is a scenario for 3 to 4 players that requires the CATAN base game, and except where the scenario states otherwise all normal CATAN rules apply.
- The scenario adds 1 guild hall board showing 5 guild halls, 8 victory point markers, and 58 favor tokens.
- The 58 favor tokens consist of 8 Trader Guild tokens showing wagons, 8 Merchant Guild tokens showing ships, 8 Road Builder Guild tokens showing shovels, 17 Scholar Guild tokens showing books, and 17 Master Builder Guild tokens showing compasses.
- In a 3-player game you remove from the game all favor tokens that have a dot on their face, and in a 4-player game you use all of the favor tokens.
- You set up CATAN normally, place the guild hall board next to the island, and mix all favor tokens face down or place them in an opaque bag or cup to form the supply.
- Whenever you earn a favor token you draw it at random from the face-down or hidden supply.
- You may never give favor tokens away to another player and you may never trade favor tokens with another player.
- You earn 1 favor token if, after rolling a "7" or playing a knight card, you move the robber to any hex that has no surrounding settlements or cities, including the desert.
- You earn 1 favor token if you move the robber to the desert and then decline to steal a resource from any player who owns a settlement or city adjacent to the desert.
- On your turn you may offer 1 resource card to an opponent who has an equal or smaller number of visible victory points than you have, and you earn 1 favor token if that offer is accepted.
- If your offer of a resource card is rejected you may offer a card to another player, provided that player also satisfies the same victory point restriction.
- You may give away at most 1 resource card during your turn for the purpose of earning favor tokens.
- A network consists of all the roads, cities, and settlements of one color that are connected to each other.
- If you build a road that connects one of your networks to an opponent's network for the first time, that opponent first earns and draws 1 favor token and you then earn and draw 3 favor tokens.
- You only earn favor tokens for first-time connections between two differently colored networks, so if those same two networks later connect again at another point nobody earns favor tokens.
- You cannot earn favor tokens for connecting two of your own networks to each other.
- If you connect two networks during the setup phase, nobody earns any favor tokens.
- If a single road you build connects your network to the networks of two opponents at the same time, you still receive only 3 favor tokens while each of the two opponents earns 1 favor token, and you decide which opponent draws from the supply first.
- On your turn you may either redeem favor tokens or exchange a favor token, but not both.
- You redeem favor tokens by returning them face up to the matching guild hall on the guild hall board.
- Redeeming the Traders' guild requires 1 grey wagon token, redeeming the Merchants' guild requires 1 blue ship token, and redeeming the Road Builders' guild requires 1 brick red shovel token.
- Redeeming the Scholars' guild requires 2 gold book tokens and redeeming the Master Builders' guild requires 2 green compass tokens.
- You must perform the favor you have redeemed immediately, and a favor may never be credited and saved for a later turn.
- The Traders' favor lets you trade 1 resource card for 1 different available resource card of your choice, and you may take this action once or twice in the turn in which you redeem it.
- The Merchants' favor lets you take any 1 available resource card of your choice from the supply.
- The Road Builders' favor lets you build 1 road for free.
- The Scholars' favor lets you draw 1 development card for free.
- The Master Builders' favor lets you take 1 victory point marker, which you keep face up so that everyone can see who has the most victory points.
- You are not allowed to use favor tokens that you received during your current turn and must instead wait until your next turn to use them.
- If you choose not to take a guild action on your turn, you may instead exchange a favor token by first drawing 1 favor token from the hidden supply and then returning any 1 of your favor tokens, including the one you just drew, to the supply.
- You win the Frenemies scenario as soon as you reach 11 victory points during your own turn, and the game ends immediately at that moment.
- To play Frenemies with 5 or 6 players you need the 5-6 Player Extension and a second copy of the Frenemies scenario.
- In a 5-player Frenemies game you use all 58 favor tokens from one copy of the scenario plus all the favor tokens from the second copy that have a dot on their face.
- In a 6-player Frenemies game you use all 88 favor tokens from two copies that do not have a dot on their face.
- You may not use favor tokens during a special build phase, and a favor token received during a special build phase may be used on your next turn.

### The Crop Trust
- Catan Scenario: Crop Trust requires the CATAN base game and adds 1 fields hex, 90 crop tokens, 41 event tokens, 1 seed vault display, and 4 crop storage records.
- The desert is not used in this scenario and is replaced by the additional fields hex, which is watermarked with a seed vial icon.
- The 90 crop tokens come in 5 crop varieties, namely wheat, beans, maize, rice, and quinoa, and each token shows a crop on its front and a seed storage vial on its back.
- In this scenario the fields produce wheat, maize, rice, quinoa, and beans, so the grain resource card is called a food card and is referred to as "food" rather than "grain".
- Each player takes 1 crop storage record and places it in front of themselves at the start of the game.
- In a 3-player game you set aside the pieces of 1 color entirely and do not place that color's starting settlements and roads on the board.
- The seed vault display is placed beside the board, and each player places 4 crop tokens of a single plant type, seed vial side up, onto one of the 2 seed vault spaces marked in their player color.
- In the recommended first-game setup, red chooses rice, white chooses beans, orange chooses maize, and blue chooses quinoa for their initial seed vault deposit.
- The robber starts the game on the pasture hex marked with the number "2" rather than on a desert.
- You shuffle the event tokens face down, and each player takes 7 of them and places 1 face-down event token under each of their 3 remaining settlements and 4 cities in their supply.
- You additionally place 1 face-down event token on each of the special victory point cards "Longest Road" and "Largest Army".
- All remaining event tokens are arranged into a face-down supply stack beside the board.
- When the number of a fields hex adjacent to your settlement or city is rolled, you may choose whether or not to harvest food from that hex.
- To harvest food you remove 1 crop token of your choice from the fields hex, return it to the supply, and take 1 food card from the supply in exchange.
- A city adjacent to a producing fields hex lets you remove 1 or 2 crop tokens and take a matching 1 or 2 food cards in exchange.
- If you choose not to remove a crop token from a producing fields hex, you receive no food card for that hex.
- Harvesting from a fields hex is conducted in 1 or 2 harvest rounds in player order, starting with the player who rolled the dice.
- If the player who rolled the dice has no settlement or city adjacent to the producing fields hex, the harvest round starts with the next player in clockwise order who is entitled to production from that hex.
- During each harvest round, each player entitled to harvest from the hex may remove at most 1 crop token and take 1 food card in exchange.
- If a fields hex does not contain enough crop tokens for all players entitled to harvest, harvesting simply stops as soon as the hex bears no more crop tokens.
- If there are no crop tokens left on a fields hex when your turn to harvest arrives, you cannot harvest and you obtain no food card.
- Once a fields hex has no crop tokens left, no owner of an adjacent settlement or city can harvest food from it any longer.
- Once during your turn you may make a seed deposit to store crop tokens in the seed vault.
- You may only deposit crop tokens of a type of which at least 1 token currently lies on a fields hex adjacent to one of your own settlements or cities.
- The robber does not affect seed storage, so you may take a crop token from a fields hex and store it in the seed vault even while the robber blocks that hex.
- A seed deposit consists of four steps that must all be completed, namely paying the storage costs, recording the deposit and receiving rewards, storing seeds in the vault, and replanting crops in the fields.
- To pay the storage costs you return 1 lumber and 1 ore from your hand to the supply.
- To record the deposit you take 1 crop token from a fields hex adjacent to one of your settlements or cities and place it on an unoccupied space of your crop storage record.
- Your crop storage record has 2 rows of 5 spaces each, you place your first crop token on the green-framed space in the upper row, and you place further tokens one by one on the next spaces in the direction indicated by the arrows.
- You may only place 1 crop token of each type in each row of your crop storage record.
- If you want to store a crop token of a type that already appears in your upper row, you must place it in the second row instead.
- If you have already placed a token of a given type in both rows, you may not place a third token of that type on your crop storage record and consequently you may no longer store crop tokens of that type in the seed vault.
- You receive no reward for the first crop token placed in a given row of your crop storage record.
- You receive 1 free development card when you place the second crop token in a row of your crop storage record.
- You receive 1 victory point each for the third, fourth, and fifth crop tokens you place in a row of your crop storage record.
- Because your crop storage record has two rows, you can in theory earn the full set of row rewards twice over the course of a game.
- To store seeds in the vault you take 4 crop tokens of the same type as the token you just placed on your crop storage record and place them seed vial side up on your currently unoccupied seed vault space.
- If fewer than 4 crop tokens of that type remain in the supply, you place whatever tokens of that type are still available into the seed vault.
- To replant crops you take the 4 crop tokens that were already sitting on your other seed vault space and place them onto fields hexes on the game board.
- You must place each of those 4 replanted crop tokens on a different fields hex.
- You do not need to own a settlement or city adjacent to a fields hex in order to replant crop tokens on it.
- A single fields hex may contain several identical crop tokens.
- A fields hex may never contain more than 7 crop tokens, and you may not place a crop token on a fields hex that already holds 7.
- If enough fields hexes are already full that you cannot distribute all 4 replanted crop tokens, you return the remaining tokens to the supply.
- Each time you build a settlement or a city, you take the event token that was underneath it, turn it over, read the event aloud, and resolve it.
- You proceed in the same way whenever you receive the "Longest Road" or "Largest Army" special victory point card, both the first time it is awarded and every later time it changes hands.
- If you build a city and thereby return a settlement to your supply, you draw a new event token from the supply stack and place it face down under that returned settlement.
- When you become the new owner of a special victory point card, you resolve the event token on it and then draw a new event token from the supply stack and place it face down on that card.
- If the event token supply stack is exhausted, you shuffle the played event tokens and form a new face-down supply stack.
- A "Regional Crop Loss" event token removes all crop tokens of the depicted type from the fields hexes bearing the depicted numbers and returns them to the supply.
- A "Small-scale Crop Loss" event token removes 2 crop tokens of the depicted type from the board, taking them first from fields hexes adjacent to your own settlements or cities and only then from other fields hexes.
- A "Large-scale Crop Loss" event token removes 3 crop tokens of the depicted type from the board, again taking them first from fields hexes adjacent to your own settlements or cities.
- A "Monoculture" event token requires that if any fields hex contains only 1 type of crop token, all of the crop tokens on that hex are removed and returned to the supply.
- A plant species is considered extinct when there are no crop tokens of that type anywhere on the board and none of that type stored in the seed vault.
- When a plant species goes extinct, all crop tokens of that type are returned from the supply to the game box, while tokens of that type already on crop storage records remain in place.
- Once a plant species is extinct it is no longer possible to plant, harvest, or store that crop for the rest of the game.
- If you reveal an event token depicting an extinct plant species, you return that token to the box and then draw and resolve a new event token from the supply.
- The game ends immediately when any one of three end conditions occurs, namely a player reaching 10 victory points on their turn, 3 of the 5 fields hexes containing no crop tokens, or 2 of the 5 plant species becoming extinct.
- If you reach your 10th victory point by building a settlement or city, you must still reveal the associated event token, and if that event causes the second or third end condition, that condition takes precedence over your win.
- If the game ends because 3 fields hexes are empty or 2 species are extinct, the player with the most crop tokens on their crop storage record wins, ties are broken by the most victory points, and a persisting tie means both players win.
- If during the production phase you remove a crop token that causes the second or third end condition to occur, you lose the game even if you have the most crop tokens on your crop storage record, and the player with the second most crop tokens wins instead.
- If you reach 10 victory points during your build phase and a forced event token reveal causes the second or third end condition, you may still win provided that you have the most crops stored on your crop storage record.
- For the variable setup you shuffle the terrain hexes, place them face down, turn them over, and then place the number tokens in the arrangement shown so that number distribution stays balanced while field positions vary.
- In the variable setup you place 1 quinoa on each fields hex marked "2" and "12".
- In the variable setup you place 1 quinoa and 1 maize on each fields hex marked "3" and "11".
- In the variable setup you place 1 quinoa, 1 maize, and 1 wheat on each fields hex marked "4" and "10".
- In the variable setup you place 1 quinoa, 1 maize, 1 wheat, and 1 beans on each fields hex marked "5" and "9".
- In the variable setup you place 1 crop token of every crop species on each fields hex marked "6" and "8".
- In the variable setup the starting player places 4 rice tokens on one of their seed vault spaces, and the following players in clockwise order choose beans, wheat, and maize respectively.

### Treasures, Dragons & Adventurers: general
- CATAN – Treasures, Dragons & Adventurers is a scenario pack containing 6 scenarios that requires the CATAN base game and the CATAN: Seafarers expansion, with several scenarios also requiring or supporting Cities & Knights.
- The pack contains 12 terrain hexes, 6 sea hexes whose backs depict desert, 2 sea frame pieces, 9 canal tokens, 16 cities in 4 colors, 19 dragon figures with 19 flag stickers, 12 number tokens, and 20 treasure tokens.
- The rules of the CATAN base game and Seafarers apply to all scenarios in the pack unless a scenario explicitly changes them, and where a scenario is played with Cities & Knights those rules also apply.
- The pack's terrain hexes and number tokens are marked with a distinguishing symbol so that they can be separated from other CATAN sets.

### Treasures, Dragons & Adventurers: The Treasure Islands
- In "The Treasure Islands" you build the home island according to the base game rules and then place the sea hexes and the harbors around it.
- To build the treasure islands you shuffle 3 sea hexes, 2 deserts, and the listed terrain hexes face down and place them face down in the treasure island area of the map.
- You shuffle the treasure island number tokens and place them in an opaque container beside the board to form the number token supply.
- You shuffle the 20 treasure tokens chest side up, place 15 of them on the intersections shown in the setup illustration, and stack the remaining 5 face down beside the board.
- During setup each player builds 2 settlements on the main island, and when a settlement is built on the coast the player may place a ship instead of a road next to it.
- This scenario is played with both the robber and the pirate, with the robber starting on the desert of the main island and the pirate starting on the sea hex marked with an "x".
- If you build a ship or a road adjacent to an intersection of an undiscovered terrain hex, you turn that hex face up.
- When you discover a terrain hex, you take 1 token at random from the number token supply, place it face up on that hex, and take 1 resource of the type produced by the hex as a reward.
- When you discover a gold field, you take any 1 resource of your choice as your discovery reward.
- When you discover a desert hex or a sea hex, you immediately take 1 treasure token from the stack and reveal it.
- If you build a ship or a road adjacent to an intersection holding a treasure token, you take that treasure token and reveal it.
- A revealed treasure token gives you either resources, a development card, or the right to build roads or ships for free, according to the symbol shown on it.
- The treasure token types grant respectively any 1 resource of your choice, either 1 grain, 1 wool, or 1 brick, any 2 resources of your choice, 1 development card, or the free construction of either 2 roads, 2 ships, or 1 road and 1 ship.
- You must make use of a treasure's advantage immediately upon receiving it and may never save it for a later turn.
- After a treasure token has been used you return it to the game box.
- When you build your first settlement on a treasure island you receive a special victory point in the form of a CATAN chit, which you place face up in front of yourself.
- You win "The Treasure Islands" if you reach 15 victory points in a 3-player game or 14 victory points in a 4-player game on your own turn.
- When "The Treasure Islands" is combined with Cities & Knights, the target is 16 victory points in a 3-player game and 17 victory points in a 4-player game.
- When "The Treasure Islands" is combined with Cities & Knights, a treasure token depicting a development card instead lets you take the topmost progress card from any 1 of the 3 progress card stacks.

### Treasures, Dragons & Adventurers: Into the Unknown
- In "Into the Unknown" you place 2 deserts and 2 gold fields face up as depicted, put a "6" number token on one gold field and an "8" on the other, and shuffle the remaining 18 hexes face down into the unknown sea area.
- The remaining number tokens of the undiscovered area are shuffled face down and placed in an opaque container beside the board to form the number token supply.
- In a 3-player game you randomly remove 3 of the treasure tokens before play and use the remaining 17.
- Each player starts with 3 settlements in this scenario rather than 2.
- During setup all players build their first 2 settlements on the main island, each with 1 adjacent ship or road, using the normal base game order.
- After the last player has built their second settlement, that same player immediately places their third settlement with an adjacent road or ship, and then all other players place their third settlements in clockwise order.
- Each player receives the resources produced by the terrain hexes surrounding their third settlement.
- This scenario is played only with the robber and there is no pirate.
- If you build a ship or a road adjacent to an intersection at an undiscovered hex, you turn that hex face up, and if it is a terrain hex you place a number token from the supply on it and take 1 resource of the type it produces.
- If an intersection holds both a treasure and an undiscovered hex, you first take the treasure and then discover the hex.
- If you discover a sea hex in this scenario, nothing happens.
- When you take a treasure token in this scenario you look at its back and then make an irrevocable choice between immediately revealing it for its printed reward and keeping it face down in front of yourself for its ongoing advantages.
- Holding 1 or more unrevealed treasure tokens means that when a "7" is rolled you only lose resources if you have more than 9 resource cards.
- Holding 2 or more unrevealed treasure tokens additionally lets you take a special harbor from the supply and place it adjacent to one of your coastal settlements, after which you may trade the depicted resource at 2:1.
- Holding 3 unrevealed treasure tokens gives you the advantages of holding 1 and 2 tokens plus 1 victory point.
- Holding 4 unrevealed treasure tokens gives you the advantages of holding 1 and 2 tokens plus 2 victory points.
- Once you have decided to keep a treasure token for its ongoing advantages, that decision is irrevocable and you may never afterwards use that token's printed reward.
- You may never place more than 4 treasure tokens face down in front of yourself, and any further treasure tokens you receive must be used for their printed advantages immediately.
- You win "Into the Unknown" if you reach 12 victory points on your own turn.
- When "Into the Unknown" is combined with Cities & Knights, each player builds a city instead of a second settlement during setup and the game ends when a player reaches 14 victory points on their turn.

### Treasures, Dragons & Adventurers: Greater Catan
- In "Greater Catan" each player additionally receives the 4 cities of their color from the scenario pack, so that each player can build a total of 8 cities.
- The new island hexes are shuffled and placed either terrain side up or sea side up in the designated area, and the new island number tokens are shuffled face down into an opaque container to form the number token supply.
- During setup each player builds 2 settlements on the main island, and a settlement built on the coast may be accompanied by a ship instead of a road.
- This scenario is played with both the robber and the pirate, with the robber starting on the desert and the pirate starting on the sea hex marked with an "x".
- If one of your ships or roads reaches an intersection at a terrain hex that has no number token, you take 1 token from the number token supply and place it on that hex.
- If the number token supply is exhausted, you must instead take a number token from the home island and place it on the new island's terrain hex.
- When taking a number token from the home island you must ensure that the numbers 6 and 8 do not end up adjacent to each other on the new islands.
- When taking a number token from the home island you must take it from a terrain hex adjacent to which you have built a settlement or city.
- When taking a number token from the home island you must leave at least 1 number token on the other neighboring terrain hexes of that settlement or city.
- Only if it is impossible to satisfy all three number-token removal restrictions may you break them, and you must break them in order starting with the 6-and-8 adjacency restriction.
- You win "Greater Catan" if you reach 18 victory points on your own turn, or 20 victory points when the scenario is combined with Cities & Knights.

### Treasures, Dragons & Adventurers: Desert Dragons
- "Desert Dragons" is a Seafarers scenario that cannot be combined with the Cities & Knights expansion.
- The scenario uses 18 desert dragon figures, which are placed beside the game board during preparation with their flag icons hidden from view.
- Neither the robber nor the pirate is used in this scenario.
- When a "7" is rolled in this scenario, all players with more than 7 resource cards still lose half of them rounded down, and the active player takes any 1 card from an opponent's hand.
- Each time you build a settlement or a city after the setup phase, you must place desert dragons onto the 3 desert hexes, placing 3 dragons in a 3-player game and 2 dragons in a 4-player game.
- The desert dragons placed on the deserts should be distributed as evenly as possible among the 3 desert hexes.
- As soon as all 18 desert dragons have been placed on the deserts, the dragons begin to attack the island.
- Once the dragons attack, each time the number of a hex adjacent to a hex holding a desert dragon is rolled, 1 desert dragon is moved from one of the 3 desert hexes onto the hex whose number was rolled.
- Only 1 desert dragon may ever occupy a single terrain hex.
- If two hexes adjacent to dragons share the rolled number, each of those two hexes receives 1 desert dragon from the desert hexes.
- Dragons taken from the desert hexes should always be taken so that the number of dragons remaining on the desert hexes stays as even as possible.
- A dragon standing on a terrain hex blocks that hex's number token, so adjacent settlements and cities no longer receive resources from it.
- Before you place a dragon onto a terrain hex, the owners of settlements and cities adjacent to that hex still receive their resources for that turn.
- A road that runs between two terrain hexes both occupied by dragons is blocked, and you rotate that road 90 degrees to indicate this.
- A blocked road does not count toward the Longest Road and you may not build a new road connecting to it.
- A settlement or city surrounded only by terrain hexes that hold dragons is blocked and is no longer worth any victory points.
- Dragons can never be placed on sea hexes, so a coastal settlement or city and any harbor adjacent to it can never be blocked.
- If you reveal one of your knight cards, you may remove 1 dragon from a terrain hex of your choice, and the removed dragon is taken entirely out of play while the used knight card goes to the discard pile.
- Because there is no robber in this scenario, playing a knight card never lets you steal a resource card from an opponent.
- There is no Largest Army special card in the "Desert Dragons" scenario.
- When a terrain hex is freed from its dragon it can produce resources again on the next dice roll, and any road, settlement, or city that was blocked by that dragon is no longer blocked.
- You win "Desert Dragons" if you reach 13 victory points on your own turn.

### Treasures, Dragons & Adventurers: The Great Canal
- "The Great Canal" is a scenario for Seafarers combined with Cities & Knights, and it uses 9 canal tokens and 18 CATAN chits.
- The fields hexes have their number tokens placed face down and do not produce anything for as long as the desert basin marked "A" remains unflooded.
- Each player starts with 2 settlements and 1 city, building first a settlement and then a city in place of a second settlement, each with an adjacent road or ship.
- After the last player has built their city, that player immediately places their second settlement with an adjacent road or ship, and then all other players place their second settlements in clockwise order.
- Each player receives the resources produced by the terrain hexes surrounding their second settlement, including 1 grain for building on an infertile fields hex.
- Each player must build at least 1 settlement or city on the coast, and the lake in the east does not count as coast for this requirement.
- When you build a settlement or city on the coast in this scenario you must place a ship rather than a road.
- This scenario is played only with the robber, which starts on any of the deserts.
- Knights may only be built on the home island in this scenario.
- As soon as at least 2 active knights stand on the intersections of a terrain hex bearing CATAN chits, a canal is built by removing the two CATAN chits and placing a canal token on that hex with its waterless side face up.
- The short sides of a placed canal token must be aligned with the hex sides that are adjacent to an existing canal or to a CATAN chit on a neighboring hex, so you choose either a straight or a bent canal token accordingly.
- If both knights that trigger a canal belong to one player, that player receives both removed CATAN chits, and if they belong to different players each of those players receives 1 CATAN chit.
- Each CATAN chit is worth 1 victory point.
- A canal is built immediately after the second knight is activated, so a third player cannot activate a knight adjacent to that hex before the canal is built.
- The strength of a knight is irrelevant when building a canal, and knights involved in building a canal are not deactivated afterwards.
- If you have a shipping route that reaches an intersection at a gold field on the small islands, you may move a knight to that intersection to act as a gold miner.
- While one of your knights stands on a gold field intersection, you receive any 1 resource of your choice each time an "8" is rolled, and the knight does not need to be active to grant this.
- If you have 2 knights at a gold field, you still receive only 1 resource of your choice when an "8" is rolled.
- If you move a knight to a harbor intersection on the small islands, you may use the advantage of the corresponding special harbor, and the knight does not need to be active to do so.
- Knights standing on the small islands do not count toward the defense of Catan against the barbarians.
- The canal is complete as soon as the second-to-last canal token is built, and if the ninth token was not placed simultaneously it is placed at that moment.
- When the canal is completed, the final two CATAN chits are removed from play, all canal tokens are turned water side up, and the desert marked "A" and the face-down number tokens on the fields hexes are all flipped over so that Catan produces grain again.
- No settlement may ever be built on the small islands in this scenario.
- Once the desert is flooded with water, knights on the small islands no longer serve as gold miners.
- Contrary to the normal Seafarers rules, shipping routes may not branch out in this scenario.
- The "Irrigation" progress card is resolved even if the corresponding fields hex is still infertile.
- You win "The Great Canal" if you reach 21 victory points in a 3-player game or 18 victory points in a 4-player game on your own turn.

### Treasures, Dragons & Adventurers: Enchanted Land
- "Enchanted Land" is a scenario for Seafarers combined with Cities & Knights, and it uses 19 dragon figures that are shuffled and placed on the enchanted land island as shown on the map.
- Each player starts with 2 settlements and 1 city on the home island, building first a settlement and then a city, each with an adjacent road or ship.
- After the last player builds their city, that player immediately places their second settlement with an adjacent road or ship, and then all other players place their second settlements in clockwise order.
- Each player receives the resources produced by the terrain hexes surrounding their second settlement.
- Each player must build at least 1 settlement or city on the coast, and when building on the coast the player may choose freely between placing a ship and placing a road.
- This scenario is played only with the robber, which starts on the desert of the home island, and there is no pirate.
- On the enchanted land island, settlements may only be built on the coast.
- Settlements built on the coast of the enchanted land island may never be upgraded to cities.
- You may not build roads on any paths of the enchanted land island, neither on the coast nor inland.
- Once your shipping route reaches an intersection of the enchanted land island, you may move an active knight from the home island to that intersection, provided that knight is connected by roads or ships to the settlement from which the shipping route leads.
- A knight that crosses to the enchanted land island is deactivated on arrival according to the Cities & Knights rules.
- Each player may move only 1 of their knights to the enchanted land island, and once a knight has been moved there it may never return to the home island.
- If the intersection your shipping route leads to is occupied by one of your own settlements, you may place your crossing knight on an unoccupied neighboring coastal intersection instead.
- If the intersection your shipping route leads to is occupied by another player's settlement, or by another player's knight that cannot be displaced, your knight cannot cross there.
- Knights on the enchanted land island may move freely along the paths from intersection to intersection and are not restricted to paths on which you have built roads or ships.
- A knight's movement on the enchanted land island may never end on a coastal intersection, which prevents players from blocking other players' crossings.
- You may move an active knight on the enchanted land island a distance of up to three intersections, after which it is deactivated.
- If you displace a weaker knight on the enchanted land island, you place that displaced knight on any unoccupied intersection of the enchanted land island.
- If you move your knight to an intersection holding a dragon figure and then activate it again, that knight may fight the dragon on your following turn.
- When your knight fights a dragon, you look at the flag icon on the bottom of the dragon figure, and the more tails the flag has the stronger the knight must be to defeat it.
- A dragon whose flag has the fewest tails can be defeated by knights of any strength.
- A dragon of the middle flag type can only be defeated by strong or mighty knights.
- A dragon of the highest flag type can only be defeated by mighty knights.
- If your knight defeats a dragon, you take the dragon figure and place it in front of yourself where it is worth 1 victory point.
- If your knight loses the fight, the dragon is placed back on the intersection, your knight stays on that intersection, and you may activate it again.
- After a lost dragon fight you may on your next turn either move the knight toward a different dragon or attempt the same dragon again once your knight has been promoted sufficiently.
- Knights that were moved to the enchanted land island or that stand on an intersection between three sea hexes do not count for the defense against a barbarian attack and are consequently not deactivated after one.
- You may neither remove nor swap number tokens on the enchanted land island using the "Inventor" progress card.
- You may not play the "Deserter" or "Intrigue" progress cards against knights located on the enchanted land island.
- You win "Enchanted Land" in a 3-player game if on your turn you defeat your sixth dragon or reach 21 victory points.
- You win "Enchanted Land" in a 4-player game if on your turn you defeat your sixth dragon or reach 18 victory points.

### Legend of the Sea Robbers
- CATAN: Legend of the Sea Robbers is a four-chapter campaign that requires the CATAN base game and the CATAN: Seafarers expansion.
- Except where the campaign states otherwise, Legend of the Sea Robbers uses the same rules as the CATAN base game and Seafarers, with additional special rules given in each chapter.
- Each sea route may hold up to 2 ships belonging to different players, but you may never place 2 of your own ships on the same sea route.
- Even with 2 ships allowed per sea route, you still may not build past an opponent's settlement or city.
- During setup the robber is placed on the space indicated next to the "4" space of the victory point track.
- When you roll a "7" or play a knight card, you may not move the robber to a terrain hex adjacent to a settlement of a player who has 3 or fewer victory points.
- If there is no legal terrain hex for the robber under that restriction, you place the robber on its starting space instead.
- Regardless of where the robber moves, every player holding more than 7 resources when a "7" is rolled must discard half of them rounded down, including players with 3 or fewer victory points.
- In Legend of the Sea Robbers you may always trade 3 identical resources for any 1 resource of a different type with the supply.
- Each player builds 3 settlements in total during setup rather than 2.
- Each chapter's board setup marks 3 or 4 coastal intersections with a starting settlement token, and you must build your first settlement on one of these intersections, removing the token as you build.
- You must place a ship rather than a road adjacent to your first settlement.
- The last player to build their first settlement is the first to place their second settlement with its adjacent road, and the other players then follow in counter-clockwise order.
- The last player to build their second settlement is the first to place their third settlement with its adjacent road, and the other players then follow in clockwise order.
- You take your starting resources from the terrain hexes adjacent to your third and final settlement.
- During setup you may not build your second or third settlement on the coast, although you may build on the coast freely during normal play.
- Friend cards are received as rewards for completing the tasks assigned by the Council of Catan, and once you receive a friend card you keep it for the rest of the campaign.
- You can neither trade nor steal a friend card.
- Each friend card has an "A" side and a "B" side, and you place a newly received friend card in front of yourself "A" side up.
- You may use a friend card on the same turn you receive it, unlike helper cards in other scenarios.
- After using a friend card for the first time in a chapter you turn it "B" side up, and you may use it one more time during that chapter.
- Unless otherwise specified, you may not use the same friend card twice in a single turn.
- After using a friend card for the second time in a chapter, you put it into your color's component bag until the chapter ends.
- At the beginning of each new chapter, every friend card you acquired in previous chapters becomes active again "A" side up and is fully at your disposal.
- You may use no more than 1 friend card per turn, and normally only during your own turn.
- The friends Oda and Reiko are exceptions to the own-turn restriction, because their abilities may be used whenever any player rolls for production.
- When you place a ship on a sea route adjacent to a chest token, you take that token, may look at its reward side, and then place it face down in front of yourself.
- A chest token rewards you with either 1 free road or ship, any 1 resource of your choice from the supply, 1 development card from the stack, or the 2 depicted resources from the supply.
- You may not claim a chest token's reward on the turn you retrieved it and must wait until a subsequent turn.
- You may only use a chest token during your own turn and you may only use 1 chest token per turn.
- You may use a chest token and play a development card during the same turn, but not a development card you have just received from that chest token.
- After using a chest token you place it face up on a discard pile beside the board, and you may never trade chest tokens.
- If one of your ships has reached an unoccupied coastal intersection of a remote island, you may build an outpost on that intersection when the Council of Catan has assigned that task.
- An outpost costs 2 lumber and 1 wool and is worth 1 victory point.
- An outpost does not produce resources and may never be upgraded into a settlement or a city.
- When you build an outpost, the shipping route between that outpost and your connected settlement or city is considered closed, so no ship in that route may be moved.
- The distance rule for settlements does not apply to outposts, so you may build an outpost on an intersection adjacent to an opponent's outpost.
- You track your victory points on the victory point track located on the board frame, placing one of your markers on the space marked "3" at the beginning of each chapter.
- If several players' markers occupy the same victory point space, you simply stack them on top of one another.
- You keep victory point development cards hidden until the end of the game and only then mark them on the victory point track.
- You may receive CATAN chits for special achievements, and as in Seafarers each CATAN chit is worth 1 victory point.
- After finishing a chapter you enter the requested game results into the light areas of the Chronicle, and at the start of the next chapter you enter your earned legend points into the darker areas.
- After all four chapters have been played, the player with the highest total legend point score wins Legend of the Sea Robbers.
- If the legend point totals are tied, the player who collected the most victory points across all four chapters combined wins, and if the tie still persists those players share the win.
- For your first play you should use the board setups specified in each chapter, and on later plays you may shuffle the terrain hexes and place them randomly in the land area while keeping the number token distribution exactly as depicted.
- Each of the four chapters can also be played as a stand-alone scenario by following the instructions printed in purple in that chapter's "Additional Preparation" section.

### Legend of the Conquerors
- CATAN: Legend of the Conquerors is a three-chapter campaign that requires the CATAN base game and the CATAN: Cities & Knights expansion.
- Before assembling the game you must complete 5 sets of 4 conquerors, each set bearing the number 2, 3, 4, 5, or 6 on its flags, and you must affix the 16 hexagonal stickers to the bottoms of the 16 forts.
- During general preparation you set aside 2 frame pieces, all building costs cards, the "Largest Army" card, and all development cards from the base game, plus the "Barbarian Tile" from Cities & Knights.
- You assemble the board for 3 or 4 players using the frame pieces, terrain hexes, and number tokens shown in the illustration for the chapter you are playing.
- You place the settlement markers and road markers on the intersections and paths outlined with red borders in the chapter's setup illustration.
- Each player takes all the playing pieces of one color from the base game, 6 knight tokens from Cities & Knights, and 1 development flip-chart.
- You place the chapter tile beside the game board, put the barbarian ship on the unmarked starting space of its movement track, and place one marker per player on the first space of the hero track.
- If you roll a ship on the symbol die, you move the barbarian ship 1 space along its movement track in the direction of the arrow.
- If you roll a "7" on the pipped dice and a ship on the symbol die in the same roll, the barbarian ship does not move.
- If the barbarian ship moves onto a space bearing a picture, you must immediately resolve the corresponding event before resources are produced.
- The "Barbarian Attack" event appears on all three chapter tiles and is resolved exactly according to the Cities & Knights rules, so you must fend off the barbarians in addition to fighting the conquerors.
- As in the Cities & Knights rules, you do not take your resources until after the event triggered by the roll has been resolved.
- Instead of the usual 4:1 trade, the general trade rate with the supply in Legend of the Conquerors is 3:1 for any 3 identical resources or commodities exchanged for 1 different resource or commodity.
- Performing certain actions during a chapter moves your marker 1 space up the hero track, and the number printed next to your marker's space shows how many additional victory points you currently have.
- You track your victory points with one of your markers on the victory point track on the board frame, starting each chapter on the space indicated in that chapter's preparation.
- If several players' markers occupy the same victory point space, you stack them on top of one another, and you must remember to include the hero track's additional victory points in your total.
- After finishing each chapter you enter the indicated game results and the legend points you received into the Chronicle form.
- After all chapters have been played, the player with the largest total of legend points wins Legend of the Conquerors.
- If the legend point totals are tied, you add up each tied player's hero track positions from the light-colored Chronicle rows across all three chapters, and the player with the highest sum wins.
- If the hero track tiebreaker still leaves a tie, all of the tied players win together.
- In Chapter 1 you play entirely without the robber, so rolling a "7" never lets you draw a card from an opponent.
- In Chapter 1 you still lose half of your resource and commodity cards when a "7" is rolled and your hand exceeds the allowed number of cards.
- In Chapter 1 you are not allowed to build metropolises, and city improvement in each area of development ends at level three.
- In Chapter 1, if you are the last player to build your third settlement, you choose any one of your settlements, replace it with a city, and surround that city with 1 city wall, after which the other players do the same in counter-clockwise order.
- In Chapter 1 your goal is to prevent the conquerors from occupying 7 or more numbered hexes in a 3-player game or 10 or more numbered hexes in a 4-player game.
- When the barbarian ship reaches a "The Conquerors Land" event space showing the purple flag marked "2", you place 1 conqueror of strength "2" on each hex bearing a landing marker.
- Each later time the barbarian ship reaches a "The Conquerors Land" event space, you place another conqueror matching that space's strength flag on each hex bearing a landing marker.
- When the barbarian ship moves onto a "Conquerors Advance" event space, you move each conqueror 1 hex toward the east, southeast, or northeast, rolling the direction die separately for each conqueror.
- A green sword icon on a "Conquerors Advance" space means the advance begins with the southernmost conqueror in the southeast, while a red sword icon means it begins in the northeast.
- If several conquerors occupy the same row, you move the conqueror furthest east first and then continue westward through that row before moving on to the next row.
- You may never move the same conqueror more than once during a single advance, so a conqueror that changed rows during its movement is not moved again in that advance.

### Variant: Fixed beginner board setup versus variable setup
- The CATAN base rulebook offers two official ways to lay out the island, namely the fixed "Starting Set-up for Beginners" and the variable setup for experienced players.
- In the fixed beginner setup you assemble the frame exactly as shown in the rulebook illustration and place all 19 terrain hexes in exactly the printed positions.
- The fixed beginner setup is deliberately balanced so that all players have comparable starting prospects, and in it the players' starting settlements and roads are also placed as printed.
- In the fixed beginner setup each player receives their starting resources from the terrain hexes surrounding the starting settlement marked with a white star.
- In the variable setup you turn all terrain hexes face down, shuffle them, and then place them face up inside the frame in the arrangement shown in the rulebook illustration.
- In the variable setup you take the 9 harbor pieces and place one at random on top of each harbor position printed on the frame.
- If you want only slight variation in harbor positions, you may instead shuffle the order of the frame pieces themselves and skip the random placement of the harbor pieces.
- In the standard variable setup you sort the 18 number tokens letter side up, start at a corner of the island, and place them on the terrain hexes in alphabetical order proceeding counter-clockwise toward the center.
- The desert never receives a number token and is always skipped when placing the number tokens.
- As an alternative to alphabetical placement, you may use a fully random number token setup by starting at one corner of the island and placing the tokens in random order.
- When using the fully random number token setup, tokens showing red numbers may never end up on adjacent hexes, so you must swap tokens as needed to separate them.
- Regardless of which board setup you use, the setup phase consists of 2 rounds in which each player builds 1 road and 1 settlement per round.
- In a 3-player game using the beginner setup, nobody plays the color whose starting pieces are shown as inactive on the map.

### Cross-references
- The Friendly Robber variant, the Catan Event Cards dice-replacement variant, the Harbormaster variant, and the Catan for Two Players variant are all published in Traders & Barbarians and are documented in that section of this file rather than repeated here.
