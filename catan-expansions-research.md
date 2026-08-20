# Catan Expansions & Variants — Research Reference

Research for the CatanGame engine roadmap. This engine implements every mechanic as an
individually-switchable **rule** (no "expansion mode"); each expansion is decomposed into
single rules a table ticks. This document catalogues what exists — official and
unofficial — with enough mechanical detail that any entry can later be decomposed into
individual rules, mirroring how the engine already decomposed Cities & Knights, Seafarers,
Explorers & Pirates, and Traders & Barbarians.

**Compiled:** 2026-08-13. Research via web search + fetch by four parallel passes.

## Source-quality legend

Every claim below carries a confidence tier. Do not treat fan-sourced numbers as final;
verify against the primary PDF before implementing.

- **[OFFICIAL]** — catan.com rulebook / PDF read directly, or Wikipedia quoting one.
- **[NEAR-OFFICIAL]** — UltraBoardGames / officialgamerules mirrors reproducing rulebook text.
- **[FAN]** — catan.fandom wiki, BGG, blogs, forum consensus.
- **unverified** — could not pin to at least a near-official source; flagged inline.

Blockers during research: `catan.fandom.com` returned HTTP 402 (paywalled) throughout;
several official PDFs are image-only or exceeded the fetch size limit (main E&P and T&B
rulebooks especially). Where a number rests only on a fan mirror it is marked.

---

## What the engine already implements (confirmed from `server/game/rules.py`)

Read directly from the rule registry, so this is ground truth, not memory:

- **Base game** — full (costs, robber, dev deck, longest road / largest army, harbours, victory target).
- **Cities & Knights** — full: `commodities`, `city_improvements`, `metropolis`, `knights`,
  `barbarians`, `city_walls`, `progress_cards`, `setup_second_city`.
- **Seafarers — CORE mechanics only**: `ships`, `ship_movement`, `pirate`,
  `longest_trade_route`, `island_victory_points`, `gold`, `start_on_main_land`. Board choice
  covers *Heading for New Shores* and *New World*. **The scenario-specific mechanics of the
  other seven named Seafarers scenarios are NOT implemented** (see §1).
- **Explorers & Pirates** — full, all five scenarios: `transport_ships`, `harbor_settlements`,
  `ships_explore`, `cargo_settlers`, `crews`, `transshipping`, `pirate_ship_instead_of_robber`,
  `chase_pirate`, `missions` + `mission_pirate_lairs` / `mission_fish` / `mission_spices`,
  `movement_phase`, `gold`.
- **Traders & Barbarians — all five scenarios**: fishing (`fish_tokens`, `fishing_grounds`,
  `lake_hex`, `old_boot`), rivers (`gold_coins`, `river_gold`, `bridges`, `wealthiest_settler`,
  `poor_settler`), `caravans`, `barbarian_attack`, and the namesake wagon scenario
  (`trade_caravans`, `baggage_train`, `roaming_barbarians`, `trade_dev_deck`).
- **Variants already done as rules**: `dice_deck` (**Event Cards**), `friendly_robber`,
  `harbormaster`, `no_adjacent_red_numbers` (fair setup), `robber_free_opening_rounds`,
  `robber_may_return_to_desert`, `epidemic`.

**Implication:** Event Cards, Friendly Robber, Harbormaster, and fair-setup — items on the
brief's "to research" list — are already shipped. The genuinely-new targets are the Seafarers
named scenarios, the "Scenarios & Variants" mini-expansion line, the two Legend campaigns, and
the standalone reimplementations (Inkas, New Energies).

---

## 1. Summary table

| Expansion / variant | Official? | In engine? | Core mechanic (one line) | Size | Source |
|---|---|---|---|---|---|
| Base game | Yes | ✅ done | roll-produce-build-trade, robber, dev cards | — | [OFFICIAL] |
| 5–6 Player Extension | Yes | ⚠ partial | more pieces + special-build / paired-turn phase | S | [OFFICIAL] |
| Cities & Knights | Yes | ✅ done | commodities, knights, barbarians, metropolis, walls | — | [OFFICIAL] |
| Seafarers (core) | Yes | ✅ done | ships, sea hexes, gold fields, pirate, island VP | — | [OFFICIAL] |
| — Seafarers: The Four Islands | Yes | ❌ no | no home continent; race to foreign islands for +2 VP | S | [OFFICIAL] |
| — Seafarers: The Fog Islands | Yes | ❌ no | win on normal VP via face-down hex exploration | S | [OFFICIAL] |
| — Seafarers: Through the Desert | Yes | ❌ no | desert belt splits island; reach far strips | S | [OFFICIAL] |
| — Seafarers: The Forgotten Tribe | Yes | ❌ no | sail to coast edges to claim gift tokens (VP/dev/harbour) | M | [OFFICIAL] |
| — Seafarers: Cloth for Catan | Yes | ❌ no | connect to villages, earn cloth chits, 2 cloth = 1 VP | M | [OFFICIAL] |
| — Seafarers: The Pirate Islands | Yes | ❌ no | roaming enemy fleet + fortress die-combat | L | [OFFICIAL] |
| — Seafarers: The Wonders of Catan | Yes | ❌ no | race to build a 4-level Wonder for alt victory | M | [OFFICIAL] / [FAN] |
| Explorers & Pirates | Yes | ✅ done | settlers/crew/missions/spice/fish, pirate lairs | — | [NEAR-OFFICIAL] |
| Traders & Barbarians (5 scenarios) | Yes | ✅ done | fishing, rivers, caravans, barbarians, wagons | — | [OFFICIAL] |
| Event Cards (dice deck) | Yes | ✅ done | 36-card deck replaces 2d6 + events | — | [OFFICIAL] |
| Friendly Robber | Yes | ✅ done | can't rob a ≤2-VP player | — | [OFFICIAL] |
| Harbormaster | Yes | ✅ done | harbour points → +2 VP card | — | [OFFICIAL] |
| Fair setup (no adjacent 6/8) | Yes | ✅ done | constraint-based token placement | — | [OFFICIAL] |
| Catan for Two | Yes | ❌ no | 2 players + neutral colours + trade-token catch-up | M | [OFFICIAL] |
| Oil Springs | Yes (free DL) | ❌ no | oil commodity + shared disaster/pollution track | M | [OFFICIAL]/[NEAR] |
| The Crop Trust | Yes | ❌ no | crop tokens + shared seed vault + extinctions | L | [OFFICIAL] |
| Frenemies of Catan | Yes | ❌ no | favour tokens earned by pro-social acts, redeemed at guild | M | [OFFICIAL] |
| Helpers of Catan | Yes (free) | ❌ no | 12 one-shot character-ability tiles | M | [OFFICIAL] |
| The Volcano | Origin unverified | ❌ no | volcano hex erupts, destroys adjacent building | S | [FAN] |
| The Great Canal | Yes (in TD&A) | ❌ no | knights dig canals to irrigate desert (needs C&K+Sea) | L | [OFFICIAL] |
| Treasures, Dragons & Adventurers | Yes | ❌ no | 6-scenario box: dragons, treasure, canals | L | [OFFICIAL] |
| Legend of the Sea Robbers | Yes | ❌ no | 4-chapter Seafarers campaign, friend cards, legend pts | L | [OFFICIAL] |
| Legend of the Conquerors | Yes | ❌ no | 3-chapter C&K campaign, cannons, cavalry, conquerors | L | [OFFICIAL] |
| Rise of the Inkas | Yes (standalone) | ❌ no | 3 tribes, forced decline + overbuild ruins | M | [OFFICIAL]/[FAN] |
| New Energies | Yes (standalone) | ❌ no | fossil vs renewable plants + global footprint events | L | [OFFICIAL] |
| Starfarers | Yes (standalone) | ❌ no | fixed board, moving ships, 15 VP, space theme | L | [OFFICIAL] |
| Historical Scenarios (Alexander, Cheops, Troy, Great Wall) | Yes (OOP) | ❌ no | fixed-map history reskins with unique rules | M | [FAN] |
| Catan Geographies | Yes | ❌ no | fixed real-world maps + landmark building | S | [FAN] |
| Santa / Easter mini-scenarios | Yes | ❌ no | move a figure, drop gift tokens | S | [FAN] |
| — Rob-the-Rich / steal-from-leader | Fan | ❌ no | robber must go to leader's hex | S | [FAN], contested |
| — Discard-on-7 alternatives | Fan | ❌ no | poverty tokens / victim-choice / no-7 | S | [FAN] |
| — Balanced-setup constraint set | Partly official | ⚠ partial | pip caps, no adjacent same-number/resource | S | [OFFICIAL]/[FAN] |
| — Longest Road/Army tie handling | Official (FAQ) | ❓ verify | holder keeps on tie; set aside on multi-tie | S | [OFFICIAL] |
| — Farming Robber | Fan | ❌ no | move robber to empty hex, take 2 of its resource | S | [FAN] |
| — Win-at-N-VP / final-turn-for-all | Fan | ⚠ partial | victory target already tunable; equal-turns not | S | [FAN] |
| — Draft / auction setup | Fan | ❌ no | bid for placement order | M | [FAN], under-specified |

Legend: ✅ done · ⚠ partial · ❓ verify · ❌ not implemented.

---

## 2. Not-yet-implemented items in detail

### 2.1 Seafarers — the seven un-built named scenarios

**Source [OFFICIAL, full text]:** https://www.catan.com/sites/default/files/2021-06/catan-seafarers_2021_rule_book_201201.pdf

The engine has all the *shared* Seafarers mechanics. Each scenario below adds one distinct
sub-mechanic or victory twist on top of them. These are the cleanest new-rule candidates in
the whole document because the infrastructure (ships, sea hexes, exploration, gold fields,
pirate) already exists.

- **The Four Islands** (win 13). No home continent — each player starts split across islands;
  race to be first onto each *foreign* island for +2 VP (max 6 at 3p / 4 at 4p). No desert, no
  gold fields. *Decomposes to:* a board layout + reuse of `island_victory_points` with a
  "no starting continent" flag.
- **The Fog Islands** (win 12). Built entirely around exploring face-down hexes; discovery gives
  only resources, no special VP. *Decomposes to:* a Seafarers-flavoured `ships_explore` (the E&P
  exploration mechanic already exists and is likely reusable) + fog-tile board.
- **Through the Desert** (win 14). A desert belt splits the main island; reach the far strip and
  outer gold/ore islands for +2 VP per first-settled area (up to 8). 3 deserts, 2 gold fields.
  *Decomposes to:* board layout + `island_victory_points` generalised to "regions", not just islands.
- **The Forgotten Tribe** (win 13). Sail a ship to marked coast edges to claim **gifts**: 1-VP
  chits, dev cards, or placeable harbour tiles. No building on small islands (they yield no
  tokens); robber movement restricted. *Decomposes to:* a new `coast_gift_tokens` rule (draw
  bag of VP/dev/harbour rewards triggered by ship reaching a marked edge) + board.
- **Cloth for Catan** (win 14, or when ≤3 villages remain). Connect ship routes to 8 coastal
  **villages**; each village pays **cloth** chits when its number rolls; 2 cloth = 1 VP (a lone
  odd chit scores 0). **Longest Trade Route is disabled**; players start with a 3rd settlement.
  *Decomposes to:* a `cloth_tokens` commodity earned per-village-on-number + a "2 cloth = 1 VP"
  scorer + a toggle to disable `longest_trade_route`.
- **The Pirate Islands** (win = recapture your fortress **and** ≥10 VP). A roaming enemy pirate
  fleet attacks each roll (moves a number of steps equal to the lower die); players build
  **warships** (from Knight cards) and conquer their own colour's fortress via die-combat.
  **No robber; no Longest Road / Largest Army.** *Decomposes to:* a scripted-fleet AI mover +
  warship pieces + a die-combat resolver + fortress-capture VP. **Largest/messiest Seafarers
  scenario — an AI-driven adversary is genuinely new engine territory.**
- **The Wonders of Catan** (win = finish a Wonder to level 4, OR 10 VP + higher wonder level
  than everyone). Race to build one of 5 Wonders, 4 levels each, each level with entry
  prerequisites (e.g. Monument = city at a harbour + 5 consecutive unbranched roads/ships).
  +1 VP per small-island settlement. Pirate not used. *Decomposes to:* a `wonders` rule (5
  buildable multi-level structures with prerequisite checks + an alternate victory condition).
  **Note:** only the Monument prerequisite is confirmed [OFFICIAL]; Cathedral / Great Bridge /
  Great Wall are [FAN], and the 5th (Theatre) prerequisite is **unverified** — read the PDF's
  wonder table before building.

**Also:** a **Seafarers 5–6 Player Extension** exists but is the same nine scenarios rescaled,
not new content [FAN/secondary].

### 2.2 Catan for Two

**Source [OFFICIAL]:** bundled in Traders & Barbarians; https://www.catan.com/sites/default/files/2021-06/catan-t_b_2020_rule_book_200820.pdf

- **Core:** 2 players plus two **neutral** colours that occupy space but do **not** produce.
  A **Trade Token** economy drives catch-up: start with a handful, earn them (near desert / on
  the coast / by sacrificing a knight), and each token-action **costs 2 for the leader, 1 for
  the trailing player**. Neutrals expand to block space when a real player builds. Win 10 VP.
- **State/pieces:** two neutral piece sets, trade-token pool per player, a "who is leading" check.
- **Board:** standard.
- **Decomposes to:** a `neutral_players` rule (non-producing blocker colours with a placement
  policy) + a `trade_tokens` catch-up economy. The token costs must be verified against the PDF.
- **Interactions:** it *is* the 2-player mode; excludes nothing but overlaps with the engine's
  existing min/max-player rules.

### 2.3 The "Scenarios & Variants" mini-expansion line

Small, mostly base-game-compatible modules. High implementation value: each is one or two
self-contained rules, and several are free official downloads.

**Oil Springs** [OFFICIAL page + NEAR-OFFICIAL rules] — https://www.catan.com/oil-springs
- Oil is a 6th commodity from buildings on **oil-spring hexes**. Consuming oil is powerful but
  advances a shared **Disaster Track**; sequestering it scores VP. Win 12 VP. Every 5 oil
  consumed → a disaster: on a 7, coastal flooding removes sea-bordering settlements / downgrades
  cities; otherwise a hex is permanently polluted (loses its number). Board "dies" at 5 removed
  numbers. Metropolis upgrade (3 VP) is flood-proof; Champion of the Environment token = 1 VP;
  sequester = 1 VP per 3 oil.
- *State:* 15 oil tokens, 3 oil-spring tiles, disaster track + marker, metropolis tokens, VP tokens.
- *Decomposes to:* `oil_tokens` commodity + `disaster_track` (shared counter with flood/pollution
  outcomes) + `oil_sequester_vp` + `oil_metropolis`. Base game only; 5–6 adaptation is fan.

**The Crop Trust** [OFFICIAL, best-sourced] — https://www.catan.com/sites/default/files/2021-06/catan-crop_trust_rulesalmanaceng_180705xs.pdf
- Semi-cooperative. Fields grow 5 crop varieties (all count as generic food/grain). Harvesting
  removes crop tokens; players balance self-harvest against depositing seeds in a shared **Seed
  Vault**. Over-harvest / monoculture triggers crop loss and **extinctions**. Win 10 VP — but the
  game also ends (and is scored on crop tokens banked) if 3 of 5 fields empty or 2 of 5 species go
  extinct, which can override a same-move 10-VP win. Seed deposits reward: nothing / free dev card /
  +1 VP each for the 1st/2nd/3rd–5th in a row.
- *State:* 90 crop tokens, 41 event tokens (4 disaster types), Fields hex, Seed-Vault display, storage aids.
- *Decomposes to:* `crop_tokens` + `seed_vault` (shared) + `extinction_end_conditions` + a
  deposit-reward ladder. **Large** because of the alt end-conditions and shared state. Base only.

**Frenemies of Catan** [OFFICIAL] — https://www.catan.com/sites/default/files/2021-07/catan_frenemies_rules_093012s.pdf
- Reverse-altruism. Earn blind-drawn **Favour Tokens** for pro-social acts (harmless robber move
  = 1; gift a resource to an equal/lower-VP opponent = 1; first road-connection to an opponent's
  network = 3 to you + 1 to them). Redeem matching tokens at a **Guild Hall** for favours
  (1:1 swap / take any resource / free road / free dev card / take a VP marker). Can't use tokens
  the turn received; not tradeable. Win 11 VP.
- *State:* Guild Hall board, 8 VP markers, 58 favour tokens.
- *Decomposes to:* `favour_tokens` (earn-triggers + guild redemption menu). Base; 5–6 needs 2 copies.

**Helpers of Catan** [OFFICIAL, free] — https://www.catan.com/sites/default/files/2023-02/Helpers_Rules.pdf
- 12 double-sided **helper tiles** (named characters), each a one-shot ability usable once per
  turn or right after production; after use, exchange for a new one or flip sun→moon to reuse
  once more. No direct VP change. The 12 abilities: forced trade, road-cost substitution,
  empty-production compensation, move-a-road, 7-protection, dev-card choice, take-card-from-leader,
  knight→building, 2:1 trade frenzy, chase robber to desert, take robber-hex resource, dev-card swap.
- *Decomposes to:* a `helper_tiles` framework (a pool of small activated abilities, each its own
  sub-rule) — this is the natural container-plus-many-small-rules pattern the engine already uses
  for progress cards. Supports base + Seafarers (+ their 5–6). C&K support not listed (unverified).

**The Volcano** [FAN — weakest sourcing] — https://www.ultraboardgames.com/catan/the-volcano.php
- A volcano hex replaces the desert; when its number rolls it (optionally) produces, then
  **erupts**, destroying a settlement / downgrading a city at one adjacent corner. Victory
  unchanged (10 VP). Seafarers has an official **"Krakatoa"** variant (3 volcano tiles, tokens
  4/5/6). Origin (Teuber, *Das Buch zum Spielen* 2000) is **unverified**; modern physical volcano
  tiles are third-party. *Decomposes to:* a `volcano_hex` rule (produce-then-destroy-adjacent on
  number). Small and self-contained, but confirm rules before shipping.

**Santa Claus / Easter Bunny minis** [FAN/shop] — feed a figure 1 wool to move it (2 wool also
chases the robber); it leaves gift tokens for adjacent buildings; 2 gifts = any 1 resource. No VP
change. *Decomposes to:* a `gift_figure` rule. Trivial; seasonal novelty.

### 2.4 Boxed scenario anthologies (needs C&K and/or Seafarers)

**Treasures, Dragons & Adventurers** [OFFICIAL] — https://www.catan.com/treasures-dragons-adventurers
(rulebook: https://www.catan.com/sites/default/files/2021-08/Treasure%20Dragons%20and%20Adventurers%20Rulebook_210107-sm.pdf)
- A 6-scenario box (Desert Dragons, Greater Catan, **The Great Canal**, Enchanted Land, The
  Treasure Islands, Into the Unknown). Adds wooden **dragons**, **treasure tokens**, **canal
  tiles**. Requires base + Seafarers + C&K to play all six. Each scenario is its own rule cluster.

**The Great Canal** (the flagship TD&A scenario) [OFFICIAL] —
- Cooperative canal-digging to irrigate a desert. **Activated C&K knights** are diggers: 2+
  activated knights on a marked hex's intersections excavate a canal (remove its 2 Catan chips,
  place a canal tile). Extra **gold points**: road along a river edge = 1; settlement/city on the
  delta swamp = 2. Requires **base + Seafarers + C&K** — the heaviest dependency stack here.
- *Decomposes to:* `canal_digging` (knight-count trigger on marked hexes) + `river_gold_points`
  (the engine already has a `river_gold` rule from T&B — likely reusable).

### 2.5 The two Legend campaigns

Both are **linked multi-chapter campaigns** with cross-game **Legend Point** carryover — a
fundamentally different shape from a single toggle. Implementing them means a campaign/scoring
harness plus per-chapter rule sets. Large.

**Legend of the Sea Robbers** [OFFICIAL] — https://www.catan.com/sites/default/files/2021-06/catan-searobbers_rule_book_171009s_0.pdf
- 4 chapters (The Castaways / The Attack / The Battle Against the Sea Robbers / The Spice Islands),
  also playable standalone. New systems: **Friend cards** (two-sided, non-tradeable, degrade),
  **Chest tokens** (one-time reward at sea intersections), **Outposts** (cost 2 lumber+1 wool,
  1 VP, don't produce/upgrade), **Spice** (ch. 4), plus castaway-rescue and sea-robber-fleet
  mechanics. In-chapter win 10 VP with a Friendly-Robber protection rule; campaign winner = most
  **Legend Points** in the "Catan Chronicle" score sheet. Requires base + Seafarers; combinable
  with C&K (separate combo PDF); cannot combine with E&P or T&B.

**Legend of the Conquerors** [OFFICIAL page/PDF; fine numbers secondary-sourced] —
https://www.catan.com/legend-conquerors
- 3 linked chapters, semi-cooperative defence against board-driven **conquerors** moved by a
  **directional die**. New mechanics: **swamp hexes**; **cannons** (build a foundry, cannon+knight
  = +1 strength, cap 4); **horse farms** → cavalry that jumps disconnected road networks; **amber**
  and **wine** commodity tokens; forts and trade stations. Requires **base + C&K**. Not standalone.

### 2.6 Standalone reimplementations (whole games, not toggles)

These are separate boxes that reuse the Catan loop with one big new idea. Each would be a large
board + several rules; they don't "add on" so much as replace the base ruleset.

**Rise of the Inkas** [OFFICIAL page; VP thresholds FAN] — https://www.catan.com/rise-inkas
- Model the rise-and-decline of 3 successive tribes. Normal Catan loop plus **forced decline**:
  at a VP threshold your tribe declines — remove your roads, cover settlements with **thicket**
  markers; declined buildings still produce but can never expand/upgrade or build roads. You found
  a new tribe elsewhere; opponents can later **build over** your ruins. Third tribe = endgame.
  Board: 24 hexes, ocean (fish) on one side, jungle (feathers/coca) on the other.
- *Decomposes to:* `tribe_decline` (threshold-triggered lockdown of a player's network) +
  `overbuild_ruins` (build settlements onto declined pieces) + a jungle/fish resource board.
  Novel and self-contained-ish; the decline/overbuild mechanic is the interesting rule.

**New Energies (2024)** [OFFICIAL] — https://www.catan.com/new-energies
- Standalone climate game. Buy a **fossil plant** (cheap, 1 science) or a **renewable plant**
  (3 science) — same energy output, but fossils raise a **Global Footprint** and renewables
  lower it. The active player draws **event discs** from a bag (count scales with the footprint);
  filling an icon triggers a pollution event whose effect depends on players' footprints. Ends at
  10 VP **or** when the disc bag empties (then best fossil/renewable balance wins).
- *Decomposes to:* `power_plants` (two build types) + `global_footprint` (shared track) +
  `event_disc_bag` (footprint-scaled random events) + a dual end-condition. Large; thematically
  close to Oil Springs' disaster track (shared-consequence pattern).

**Starfarers** [OFFICIAL] — https://www.catan.com/starfarers
- Space reskin on a **fixed** board with **moving ships**, colonies/spaceports/trade stations,
  friendly/hostile encounters, and a **15 VP** target. Big box, many subsystems (fuel, ship
  upgrades, aliens). Low priority: it's essentially a different game wearing Catan's coat.

### 2.7 Historical / geographic fixed-map lines

**Historical Scenarios I & II** [FAN — OOP] — Alexander the Great (advisors guide Alexander along
a fixed green path Greece→Egypt→India→Persepolis; no starting settlements), Cheops (all building
along the Nile; ore unavailable at start), Troy (draw a Decision Card = side with Greece or Troy),
Great Wall. Each is a fixed-map reskin with 1–2 bespoke rules. *Decomposes to:* mostly board data
plus a small scenario rule each. Niche; sourcing is fan-level.

**Catan Geographies** [FAN] — a line of fixed real-world maps (Germany, US states, Hawai'i, etc.)
with **landmark building** objectives and non-modular boards. Mostly standard 10-VP rules on a
fixed layout. *Decomposes to:* board data + an optional `landmarks` rule. **No official "Amazon"
map exists** — treat any such reference as a misremembering.

### 2.8 Fan-made / house rules (well-specified enough to implement)

Robber & 7 family:
- **Rob-the-Rich / steal-from-leader** [FAN, contested] — robber must move to a hex touching the
  current leader. **No canonical metric** (VP? cards? production?) — you must pick one. A cousin,
  "**multiple robbers**", adds a 2nd robber. *Needs a design decision before implementing.*
- **Discard-on-7 alternatives** [FAN] — poverty tokens; combine 2s & 12s to remove the 7 entirely;
  victim chooses the stolen card; count only resources (not dev cards) toward the discard threshold.
- **Farming Robber** [FAN] — move the robber to an *unsettled* hex and collect 2 of that resource
  yourself. Clean toggle.
- **Robber off-board start** [FAN] — robber starts off the board; first 7 places it on the desert.
- **No robber early game** — reroll a 7 in the first two rounds (CMU tournament rule, cleanly
  specified) — the engine already has `robber_free_opening_rounds`, so **verify overlap**.

Setup & turn order:
- **Balanced-setup constraint set** [OFFICIAL for 6/8 only; rest FAN convention] — no two red 6/8
  on a shared edge (**official**); plus community conventions: no two 2/12 adjacent, no two identical
  numbers adjacent, no two identical resources adjacent, intersection pip cap ≤11. The engine has
  `no_adjacent_red_numbers` (the official part); the extra constraints are clean boolean add-ons.
  Precise thresholds: https://simonvandevelde.be/posts/Balanced_Catan_Board_Generator.html
- **Roll for turn order** [FAN, informal] — trivial. Base rulebook actually uses oldest/youngest.
- **Draft / auction setup** [FAN, under-specified] — bid resources or VP-debt for placement order;
  no authoritative rules PDF exists. You'd define currency + tie resolution yourself. Low confidence.

Scoring & trading:
- **Longest Road / Largest Army tie handling** [OFFICIAL, FAQ] — holder **keeps** on a tie
  (challenger must strictly exceed); if broken and 2+ then tie (or none ≥5), the card is **set
  aside, awarded to no one** until broken. Cleanest precise switch; **verify the engine's current
  tie behaviour** (`longest_road_minimum` / `largest_army_minimum` exist, tie policy unclear).
  https://www.catan.com/faq/basegame
- **Win-at-N-VP** [FAN] — the engine's `victory_target` already covers this. "Give everyone a final
  turn after someone hits the target" is the un-built part.
- **Robin Hood** (stolen card → lowest-VP player), **The Banker** (7 = free chosen resource),
  **no-leader-trade** [FAN, blog-level] — real but loosely specified; mark contested.

Fan expansions (mostly whole modes, poor fit as single toggles): Super Catan (Seafarers+C&K+T&B
mashup), Heroes & Capitols, Harbors & Artisans. **"Catan: Elements" is NOT a documented product** —
only a brainstorming thread; do not implement as if defined.

---

## 3. Recommended next targets (ranked)

Ranked by value × cleanliness of decomposition into individual rules, given what the engine
already has.

**Tier 1 — highest value, cleanest fit (do these first):**
1. **Seafarers named scenarios** (Four Islands, Fog Islands, Through the Desert, Forgotten Tribe,
   Cloth for Catan, Wonders). All the plumbing (ships, exploration, gold fields, island VP) is
   already in the engine — these are mostly board data + one bespoke rule each (`cloth_tokens`,
   `coast_gift_tokens`, `wonders`, a generalised region-VP). This is the biggest coverage gap in an
   *already-owned* expansion and the highest-leverage work. **[OFFICIAL], well-sourced.** (Skip/defer
   The Pirate Islands — see Tier 4.)
2. **Helpers of Catan.** A pool of 12 small one-shot abilities maps directly onto the engine's
   existing progress-card container pattern. Free official rules, base-compatible, additive, no board
   changes. Clean and self-contained.
3. **Oil Springs.** One new commodity + a shared disaster track + sequester-VP. Free official,
   base-only, and the shared-consequence pattern is a good template for New Energies later.

**Tier 2 — good value, moderate effort:**
4. **Frenemies of Catan.** A single `favour_tokens` subsystem (earn-triggers + guild redemption).
   Base-only, official, self-contained. Interesting because it inverts the usual robber incentives.
5. **The Crop Trust.** `crop_tokens` + shared seed vault + alternate end-conditions. Best-sourced of
   the mini-line; larger only because of the extinction end-states.
6. **Catan for Two.** Fills the 2-player gap with `neutral_players` + `trade_tokens`. Official,
   verify token costs against the PDF.
7. **The Volcano.** Trivial `volcano_hex` rule — but sourcing is fan-only; confirm before shipping.
8. **Balanced-setup add-ons + Longest-Road/Army tie handling.** Small boolean rules that extend the
   engine's existing setup/award logic; official where it matters.

**Tier 3 — standalone reimplementations (large, but novel mechanics worth harvesting):**
9. **Rise of the Inkas** — the decline/overbuild mechanic (`tribe_decline`, `overbuild_ruins`) is
   genuinely new and not expressible with existing rules; a strong "flagship new mechanic" candidate.
10. **New Energies** — power-plant choice + global footprint; overlaps conceptually with Oil Springs,
    so build Oil Springs first and reuse the shared-track pattern.

**Tier 4 — messy, heavy dependencies, or poor fit (defer / avoid):**
- **The Pirate Islands** and **Legend of the Conquerors** — both need a board-driven AI adversary
  (roaming fleet / directional-die conquerors) plus die-combat. Novel but expensive; the AI-mover is
  new engine territory.
- **The two Legend campaigns** — require a cross-game campaign/Legend-Point harness on top of
  per-chapter rules. Only worth it if campaign play is a product goal.
- **The Great Canal / Treasures, Dragons & Adventurers** — triple dependency (base + Seafarers +
  C&K) and cooperative digging; high complexity for niche appeal.
- **Starfarers** — effectively a different game; not an "add-on" and not worth decomposing here.
- **Rob-the-Rich, draft/auction setup, blog-level trade rules** — under-specified; would be original
  design work, not implementation of a known rule.

## 4. Notable gaps & honesty notes

- **Biggest gap in owned content:** the engine markets Seafarers but only implements its *core
  mechanics* + two board choices. Seven of the nine official Seafarers scenarios have un-built
  scenario-specific rules (§2.1). This is the clearest "we own it but haven't finished it" gap.
- **Already done (don't re-scope):** Event Cards / dice deck, Friendly Robber, Harbormaster, and
  the official fair-setup (no adjacent 6/8) are shipped rules — they appear on the brief's research
  list but need no work.
- **Verify in-engine:** Longest Road / Largest Army *tie* policy (official rule is holder-keeps /
  set-aside-on-multi-tie); and whether the C&K 5–6 special-building / paired-players' turn is
  correctly implemented (`5-6 Player` strings appear in code but the phase rule wasn't confirmed).
- **Weakest sourcing, don't ship without the PDF:** The Volcano (origin unverified, fan rules only);
  Seafarers Wonders prerequisites (only Monument confirmed, Theatre entirely unverified); E&P settler
  cost / fish-spawn trigger / tribute numbers (official PDFs were image-only/oversized); Legend of
  the Conquerors and Rise of the Inkas exact VP thresholds (secondary-sourced). `catan.fandom.com`
  was paywalled (HTTP 402) throughout, so several fan cross-checks are missing.
- **Not real products (do not implement as if defined):** a Catan "Amazon" geography map; "Catan:
  Elements". Both surfaced only as misremembering / brainstorming threads.
