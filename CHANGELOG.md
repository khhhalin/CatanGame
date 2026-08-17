# Changelog

What changed, in the words of somebody playing the game rather than somebody
writing it. The server parses this file and serves it to the panel in the corner
of the screen, so this is the only place an entry is ever written.

**If you are testing:** open the panel, read the build id it shows, and put that
line in your report. Three bugs were filed twice in one day — city walls,
discarding commodities, the progress card deck — and all three had been fixed
hours before the report came in. Every one of them was a tab left open on an
older build.

Adding to it, for whoever deploys next: put a new release at the top, newest
first. The heading is `## <build id> — <YYYY-MM-DD HH:MM>`, where the build id is
a **version** — `v<MAJOR>.<MINOR>.<PATCH>`, e.g. `v1.0.0` — the moment it goes
out, or `unreleased` while the work has not shipped, or a bare
`git rev-parse --short HEAD` for a one-off dev build. The version is the identity
a deployed server shows (a container carries no `.git`), so cutting a release is:
bump `VERSION` at the repo root — **patch** for a bug-fix deploy, **minor** for a
batch of features, **major** for a milestone — and rename the top `unreleased`
heading to `v<the new VERSION>`. `VERSION` and this heading must agree; a test
enforces it. Every line under the heading is
`- **Fixed|New|Known issue** <one line>`, with an optional `[reported]` straight
after the kind for anything that answers something a tester filed — that marker
is what tells them what to go and re-test. The server refuses to serve a file
that breaks any of that, with the line number, so a typo is a server error and
never a half-drawn panel.

## v3.7.0 — 2026-08-17 08:13

- **New** Seafarers now has all seven named scenarios, each with its own board and twist: The Four Islands, The Fog Islands, Through the Desert, The Forgotten Tribe, Cloth for Catan, The Pirate Islands and The Wonders of Catan.
- **New** The Four Islands: no home continent — start split across the sea and race to be first onto each foreign island for points. Now with its own four-player board too.
- **New** The Fog Islands: most of the map starts face-down, and a ship that reaches a fog hex flips it over and takes whatever it finds.
- **New** Through the Desert: a belt of desert splits the island; cross it and reach the far regions to score for each new area you settle first.
- **New** The Forgotten Tribe: sail a ship to a marked coast to claim a gift — a victory point, a development card, or a harbour you place yourself.
- **New** Cloth for Catan: connect your ships to the coastal villages; each pays cloth on its number and two cloth make a point. The game can also end when the villages run dry.
- **New** The Pirate Islands: a roaming pirate fleet raids the coast every roll; build warships from your knights, storm the fortress of your colour and take it back to win.
- **New** The Wonders of Catan: race to raise one of five Wonders — Cathedral, Great Bridge, Great Wall, Monument or Theatre — four levels each, and be the first to finish one.
- **New** Gold fields, the Seafarers way: when the number on a gold field is rolled, each town beside it takes resources of your own choosing.
- **New** Helpers of Catan: twelve character tiles, each a one-shot favour — a forced trade, a cheaper road, a card from the leader, safety from the seven and more; use one, then swap it or flip it to use once more.
- **New** Oil Springs: pump oil from the springs and burn it for a rush of resources — but every five oil used brings a disaster, and enough disasters kill the board. Sequester oil instead to score.
- **New** Frenemies of Catan: earn favour tokens by playing nice — a harmless robber, a gift to a trailing rival, the first road to a neighbour — and spend them at the Guild Hall.
- **New** Rise of the Inkas: your tribe rises then declines — roads vanish and towns become ruins that still produce but never grow, and rivals can build over them. The third tribe ends the game.
- **New** Gold and coins can now be put on either side of a trade offer between players.
- **Fixed** Every scenario deals its own board now, instead of sometimes handing one table a random map.
- **Fixed** The board no longer collapses to a strip in a narrow or tiled window, and the crowded Cities & Knights table fits on screen at 1920×1080.
- **Fixed** Barbarian Attack: you now choose where Treason and Intrigue strike, and a building the barbarians conquer loses the use of its harbour.
- **Fixed** Scenario side panels no longer leak into the wrong Traders & Barbarians scenario.
- **Known issue** The Traders & Barbarians central trade hex still uses a simplified plaza — one land corner rather than the printed central square and spokes.

## v3.6.0 — 2026-08-12 20:34

- **New** Caravans of Catan, a new scenario: each turn you build, a camel joins a caravan out of the oasis (the table bids wool and grain for who places it); roads along a caravan count double for the Longest Road, and a settlement between two caravans is worth a point.
- **New** Barbarian Attack, a new scenario: barbarians land on the coast as you build and conquer a hex once three gather; place knights around the castle to fight them off, free their prisoners for points, and buy from a deck of their own.
- **New** Traders & Barbarians, the main scenario: drive a wagon of goods to the castle, quarry and glassworks for gold and points, upgrade your baggage train, and get past the barbarians roaming the roads.
- **New** Three more lobby presets — Caravans, Barbarian Attack and Traders & Barbarians — one click each, every rule still yours to change.

## v3.5.0 — 2026-08-12 18:59

- **New** Rivers of Catan, a new scenario: settle or build a road beside a river and the bank pays you a gold coin. Spend two coins for any resource, or turn four spare resources into one coin.
- **New** Bridges cross the river paths (2 brick + 1 lumber, and 3 coins for building one); they count toward the Longest Road like any road, up to three each.
- **New** The richest player holds a tile worth +1 point; whoever is tied for the fewest coins holds one worth −2. They move the moment the coin counts change.

## v3.4.0 — 2026-08-12 16:24

- **New** Fishermen of Catan, a new scenario: fishing grounds on the frame and a lake in the middle pay out fish tokens.
- **New** Spend fish for a one-off boost — send the robber off the board, steal a card, take a card from the bank, a free road, or a free development card. Mind the old boot, which raises your own target to win.
- **Fixed** [reported] Explorers & Pirates is now a single lobby preset (the whole expansion, to 17 points) instead of five separate scenario presets; every rule it ticks is still yours to turn off.

## v3.3.0 — 2026-08-11 22:41

- **New** Resources and buildings are now editable data — a resource is a name, colour, symbol and pattern; a building a name, cost and icon.
- **New** Download either set from the map editor, edit it, and upload it back to retint a resource, relabel or reprice a build, or add a new one — no code needed.
- **New** Cotton, a new resource: paint cotton hexes onto a custom map and it produces, banks, trades, discards and monopolises like any other. Standard games are unchanged — it only appears where a map places it.

## v3.2.1 — 2026-08-11 20:40

- **Fixed** [reported] A trade offer you leave open is cleared when your turn ends, instead of hanging over the table into the next player's turn.
- **Fixed** [reported] Incoming trade offers pop up on a side rail now, clear of the board, so they never cover the map.
- **Fixed** [reported] The move-the-robber prompt (and the other turn prompts) no longer sits on top of the players panel.
- **New** [reported] The game log and chat moved to a wide panel down the left side — much bigger, and it fits the screen.

## v3.2.0 — 2026-08-11 20:10

- **New** Explorers & Pirates: build transport ships, carry cargo, and sail into fog to discover hidden parts of the map.
- **New** The three E&P missions — hunt fish, capture pirate lairs, befriend spice villages — played by sailing a ship to the spot and acting there.
- **New** Gold trades for the resource you need, and on a 7 the pirate ship sails out instead of the robber.
- **New** A Pirate Cove scenario map to play it on — a home harbour, open water, and fog to explore.

## v3.1.0 — 2026-08-11 18:46

- **New** Every resource now carries its own name, colour, board pattern and icon in one place, so the board draws each terrain from that definition. The base resources look exactly as before; the difference is that adding a new one — gold, say — is now a single entry rather than a code change.
- **New** The map editor has a Resources button that downloads the current resource set as a file you can edit and drop back in to retint a resource or add one.

## v3.0.1 — 2026-08-11 16:22

- **Fixed** [reported] Trade offers no longer vanish on their own — an offer stands until it is taken or you withdraw it.
- **New** [reported] A trade offer now pops up for every player the moment it is made, so you never have to open the Trade tab to see or answer one, and you can withdraw your own from the popup.
- **Fixed** [reported] Tapping a staged resource in the build-and-trade tray takes one off the pile instead of clearing the whole stack.
- **New** [reported] Discarding on a 7 works like the trade tray now — tap the cards in your hand to choose what to discard, and Discard lights up once you have picked enough.
- **Fixed** [reported] The panels floating over the board no longer collide — your standings, the build/"what changed" pill, the zoom buttons, the dice and the log each keep their own space.

## v3.0.0 — 2026-08-09 20:30

- **New** A whole new look — "Deep Harbour". The game is dark by default, with frosted, floating panels over a full, centred board: your standings top-left, your hand of cards along the bottom, the dice in their own corner, and the build-and-trade tray on the left.
- **New** Build and trade straight from your hand: tap your resource cards onto the tray and it works out what they make — a road or settlement to build, a bank trade at your own rate, or an offer to the table — and becomes that one button. The separate build buttons and the trade dialog are gone.
- **New** New type throughout (Space Grotesk, with JetBrains Mono for every number), a deeper ocean, and the whole board and panels recoloured for the dark theme — every label rechecked to stay readable.
- **Known issue** The light theme is a rough carry-over of the old parchment look for now; the dark Deep Harbour theme is the tuned one.

## v2.1.0 — 2026-08-06 22:38

- **New** The board fills the screen now. Your players, your hand, the dice and the build/trade tray all float over it instead of penning it into a corner, and it zooms in further by default.
- **New** Your resource cards sit as real cards jutting up from the bottom edge; building and trading share one tray in the bottom-left, and the dice have their own tray in the bottom-right.
- **New** The last of the boxed, nested panels are gone — the rail reads as one quiet flowing list.
- **Fixed** Placing the robber, the pirate, a road or a ship against a hex low on the board or in a corner could leave the ✓ confirm tucked behind your hand or a tray, refusing the click; it now always sits on top of the floating panels.

## v2.0.2 — 2026-08-05 19:30

- **New** The build buttons are clean labels now, and what each build costs lives in its own Costs panel in the sidebar instead of being crammed onto the buttons.
- **New** The sidebar panels lost their heavy boxes — Details, Costs, the bank and the rest read as one quiet list, in keeping with the rest of the redesign.

## v2.0.1 — 2026-08-05 19:00

- **Fixed** Your hand of cards no longer gets cut off the bottom of the screen on a laptop. The board gives up a little room and the cards shrink a touch below a short height, so the whole hand stays on screen.

## v2.0.0 — 2026-08-05 18:30

- **New** A calmer, warmer, more minimalist look. The panels stepped back to quiet surfaces and the board takes the room — the game reads at a glance now.
- **New** Your resources are a hand of physical cards along the bottom of the screen; tap one to lift it into a trade.
- **New** Trading is a shelf right above your hand — tap your own cards into "You give", pick what you want, and Propose, with no separate dialog.
- **New** The board wears clean minimalist patterns instead of the old textures — a woven motif per land, quiet beneath the numbers and pieces.
- **New** The dice are physical dice with pips.

## v1.0.0 — 2026-08-05 12:00

- **New** The whole interface swapped its emoji for one matching set of drawn icons — resources are small coloured tiles in the board's own colours, everything else a clean line icon. The player list reads as a card per player now, not a run of abbreviations.
- **New** Two house rules that cannot both be on now say so: tick one and its rival unticks itself with a line explaining why, instead of one silently cancelling the other out.
- **Fixed** [reported] The give and want pickers in Propose Trade are evenly spaced. Ore and cloth sat flush against each other because commodities are a second block, so the one seam in the list was tighter than every other gap.
- **Fixed** [reported] Propose Trade is shorter and fits a phone without scrolling inside itself. The pickers are two columns rather than one, which took the dialog from 927px to 680px with commodities in play — Propose used to be below the fold at 390x780.
- **Fixed** [reported] Every trade number has its own − and + button now, 48x40px to aim at instead of the browser's hairline arrows, on a phone as well as a desk — and the dialog is no taller for it. The give side stops at the cards you hold, and Clear puts all sixteen numbers back to zero.
- **Fixed** [reported] The little up/down arrows on each trade number are easier to hit: the fields are now 40px tall rather than 27px, and the arrows are drawn at the field's height. Tapping the field itself brings up a number pad on a phone.
- **New** This panel. It names the build the server is running and when that server started, so a tab left open across a deploy is obvious before a bug is filed rather than after.
- **New** [reported] Tap one of your own knights on the board and its actions appear over the piece itself — activate, promote, move — with a reason on any it cannot do. They used to be a row in a panel, identified by a coordinate no player ever sees.
- **Fixed** [reported] The discard and trade dialogs show your own cards, resources and commodities alike. Both dialogs cover the hand panel, so at the two moments you most need your counts they were behind a blur.
- **Fixed** [reported] Moving the robber onto the hex it already stands on is refused. It used to be accepted, which answered the 7 without moving anything and left every neighbour blocked exactly as before.
- **New** [reported] The table chooses which published rule the second-round starting city pays out under. Reported twice as the starting city paying too much; both readings are in print, so it is a setting rather than a bug.
- **New** Rolling, discarding, moving the robber, answering a question and the rest of the turn each have their own clock, and the table sets all five in the lobby. Paying a 7 slowly no longer costs the turn it interrupted.
- **Fixed** The countdown names the clock that is actually running — Dice, Discard, Robber or Choice — instead of showing a turn clock that had not started yet.
- **Fixed** A missed robber or discard clock is settled less bluntly: the robber goes to the busiest hex that touches none of your own buildings, rather than to a random one that was as likely to be yours.
- **New** Slash commands in chat, when the table switches the rule on: type `/` in the chat box and the commands the server offers are listed as you type.
- **Known issue** Special points for new islands cannot score on any of the three built-in boards. All three are a single landmass, so there is no second island to be first onto; the rule needs a custom map with an island region in it.
- **Known issue** Merchant Fleet works, but the card only exists in a progress card deck — a table playing the base game's development cards will never draw one.
- **Known issue** A ship in a circular route is deliberately left free to move. The Seafarers rulebook contradicts itself about whether a loop closes a route, and this is waiting on a ruling rather than a guess.
- **Known issue** Gold fields, the 5-6 player special building phase and Catan for Two are not implemented and are not offered in the lobby.

## 6b28989 — 2026-08-04 19:43

- **Fixed** [reported] A hand of cloth, coin and paper can pay what a 7 asks for. The server had accepted commodities in a discard all along; the dialog had five inputs, so a player over the limit on commodities alone could not comply at all and the table stopped there.
- **New** Cloth, coin and paper can be offered and asked for in a trade, with other players and with the bank. One commodity anywhere in an offer withdraws every 2:1 harbour rate, which is what the rulebook says those harbours are for.
- **New** Merchant Fleet, the last progress card that was refused by name: it asks which resource or commodity you want at 2:1, and holds that rate for the rest of the turn.
- **Fixed** Buy Card is greyed out with the reason on a table playing progress cards, instead of taking the click and answering with an error. Progress cards replace the development deck for the whole game.
- **Fixed** [reported] A settlement can no longer be built on an intersection a knight is standing on. Both pieces used to end up there.
- **Fixed** A second tab asks before taking over a seat instead of silently claiming it, and the browser remembers the name you last joined under so a reload mid-game does not hand you an empty box.
- **Fixed** The route award is named for the rule the table is playing and counted in the unit that rule uses. A Seafarers table playing the Longest Trade Route was told "10 roads" for a route that was mostly ships.
- **Fixed** The "needs 5" and "needs 3" on the award panel follow the thresholds the table actually set, instead of always quoting the base game.
- **New** The log says what each roll paid and to whom, and names any house rule that changed a payout — so a city that collected one card instead of two says why.
- **New** Every scoreboard row states the whole player at a glance: score, both hands as counts, every kind of piece the table plays with, knights, and a badge for each award held.
- **New** A sound for every piece placed, and a Mute toggle beside YOLO that is remembered. It starts muted if your browser asks for reduced motion.
- **New** Custom maps: a format, somewhere to keep them, and a board dealt from one. A map with no main land to start on is refused by name rather than quietly swapped for another.
- **Fixed** On a board with more than one coastline the harbours are dealt around every coast, instead of crowding onto whichever one was walked first. A sea tile can no longer take a number token or carry a settlement.
- **New** The console names the dice set in play when the table is not using the standard pair, so a player who never sees a 12 can tell a rule from a run of luck.

## a351285 — 2026-08-04 16:03

- **Fixed** Two tabs can no longer play as the same person. Every action is bound to the seat the connection holds; covering for someone who stepped away still works, but it means taking the seat, the displaced tab is told, and the table sees it in the log.
- **New** [reported] City walls are drawn on the board, on the city each one protects, and a city may carry at most one. A wall was buildable and completely invisible before this — two brick for a number in a panel.
- **New** When a card or a lost barbarian attack asks you to choose something, you are now asked. The question has a panel with the options on it, and everyone else is told who the table is waiting for; before this the server froze the table and nothing on any screen said so.
- **Fixed** [reported] The trade dialog shows the bank rate you actually hold for each resource and says in words what your numbers will do. An over-priced bank trade is lowered to your own rate once, announced, with the original still one button away.
- **Fixed** A knight standing on an intersection blocks an opponent's road through it and breaks their longest road — and so does an opponent's settlement, which had never been implemented at all.
- **Fixed** Nobody moves the robber or ends the turn while anyone at the table still owes a discard. On a 7 the roller could previously rob and pass while two opponents were still counting cards.
- **Fixed** Nothing can be built, traded or bought before the dice are rolled.
- **Fixed** A ship in a circular route can move again: every ship in a loop was treated as locked in place for ever.
- **Fixed** The board fills its pane. It was drawn inside a margin of about a sixth of the layout, so the table sat in dead space.
- **New** House rules that change a cost, a payout or the dice are applied in a defined order, so two of them switched on together cannot quietly disagree about the answer.

## aeb9ca1 — 2026-08-04 11:16

- **New** Seafarers: ships, the pirate, trade routes and special island points, with the controls to build and move a ship and open water that is never offered as a target for anything else.
- **Fixed** A shipping route can found the settlement it sails to, and a win reached at sea is announced with the special points counted in.
- **Fixed** A tie leaves the Longest Road card with the player already holding it, as the rulebook says.
- **Fixed** A road that claims the Longest Road and wins the game announces the win, instead of ending it in silence.
- **Fixed** After a restart a player keeps exactly the ships the board still holds for them.
- **Fixed** A house rule offering a choice of values can be chosen in the lobby; the picker drew it and then ignored what was picked.
- **Fixed** Ticking several house rules quickly sends one update instead of one per click, so the lobby stops flickering under a burst.
- **Fixed** Every colour in both themes is measured for contrast rather than eyeballed. Seven text colours failed the standard and were changed.

## d3736a2 — 2026-08-04 00:49

- **Fixed** [reported] The board deals the 18 number tokens that are in the box. Every board generated before this dealt 30 tokens into 18 slots, weighted by dice frequency, so no board was ever the right one.
- **Fixed** [reported] Harbours sit on a coastal edge, between the two intersections that may use them, instead of on a single vertex.
- **Fixed** Two hexes that share a side share the road on it. There used to be one edge per hex, so a road drawn between two hexes existed twice.
- **New** A click previews a placement and a ✓ commits it, so a mis-tap on the board costs nothing. YOLO mode, beside the build buttons, places on the click for anyone who prefers it.
- **New** Selectable board layouts: random, the beginner setup from the box, and the 5-6 player island.
- **New** Cities & Knights progress cards are dealt, held and played, and the decks and hands survive a restart.
- **New** Six more switchable house rules, and one-click presets for the published rule sets, so a table can reach Cities & Knights without reading thirty switches.
- **New** The dice can be dealt from a 36-combination deck when the table asks, instead of rolled independently every turn.
- **Fixed** A robber or a discard nobody answers is resolved when the round clock runs out, so one player walking away no longer freezes the table.
- **Fixed** Building, trading with yourself and taking a colour somebody already has are refused by the server, not only discouraged by the browser.
- **Fixed** The event die is announced with the roll rather than at the turn boundary, so the barbarian track stops looking frozen for a whole turn.
- **Fixed** The barbarians say what they did, and the Trade button is greyed out rather than disappearing when it cannot be used.
- **Fixed** A popover no longer opens on top of the control that opens it, which made opening one a one-way trip.
- **New** The table fits on one screen. Every subject that used to overflow the rail is a line stating its own numbers, with the detail one press away, and nothing scrolls except the game log.
- **Fixed** Nothing is loaded from anybody else's server any more, so the game works offline and cannot be taken down by a third party's outage.

## 0e1f7f4 — 2026-08-03 21:54

- **New** A new look for the whole game: one shell for the lobby and the table, a light and a dark theme that follow the browser's setting, and a board that sizes itself to the space it is given.
- **Fixed** A road may extend from your own settlement or city, not only from another of your roads.
- **Fixed** The Longest Road card is given up when the holder's route is broken below the minimum length, instead of being kept for ever.
- **Fixed** The ocean ring around the board is generated as ocean, so the coast the harbours are dealt onto is the real one.

## 0c891ad — 2026-08-01 20:12

- **New** The first build testers played: the base game end to end, the Cities & Knights engine, chat, an event log, saved games that survive a restart, and a house-rule picker in the lobby.
