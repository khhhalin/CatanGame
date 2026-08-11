# Traders & Barbarians — decomposition plan

A build plan for implementing the five **Catan: Traders & Barbarians (T&B)
scenarios** in this engine as **individual switchable rules**, decomposed the
way Cities & Knights, Seafarers and Explorers & Pirates already are. This is a
plan only; no engine code is written here. It is modelled on
`explorers-and-pirates-plan.md` and follows the same law.

The governing law (CLAUDE.md "Rules are individual") is absolute: **no engine
code may branch on the name of an expansion.** There is never a
`rules['traders_and_barbarians']` in engine code. Each mechanic is its own rule
read where it applies. A preset merely *ticks* individual rules; nothing records
that a preset was used. A rule may **suggest** a victory target
(`suggests_victory_target`) but never overwrite one, and a rule that cannot act
alone declares what it needs in `DEPENDENCIES` (`server/game/rules.py:823`) —
refused at `start_game`, never propped up. Contradictory rules go in
`EXCLUSIONS` (`rules.py:863`), which both refuses the combination and
auto-unchecks a rival.

**Scope.** The engine already ships the two T&B *variants* — Friendly Robber
(`rules.py:438`, `friendly_robber`) and Harbormaster (`rules.py:442`,
`harbormaster`) — and the preset `traders_and_barbarians` (`rules.py:1067`) that
ticks them. This plan covers only the five **scenarios**, absent today:

- **The Fishermen of Catan** — `expansions.md:489–526`
- **The Rivers of Catan** — `expansions.md:527–570`
- **The Caravans** — `expansions.md:571–606`
- **Barbarian Attack** — `expansions.md:607–676`
- **Traders & Barbarians (main scenario)** — `expansions.md:677–755`

Source line numbers are `expansions.md`. Touch points are `file:line`.
"Unverified" marks a claim not confirmed by reading the code.

---

## 0. What T&B reuses vs. what is genuinely new

**Reused from the existing engine (do not rebuild):**

- **map-format v2's fixed pools.** `POOL_MODES_V2` adds `'fixed'`
  (`maps.py:71`), a printed layout placing tile+token by declared position
  (`maps.py:445` `_parse_fixed_pool`). Every T&B scenario uses a
  printed/predetermined layout (`expansions.md:611,614,682,690`), so they build
  on the same fixed pool E&P and the beginner map use — they do **not** invent
  their own layout mechanism.
- **map-format v2's new terrains, partially.** `gold`, `fish`, `spice` already
  parse under v2 (`TERRAIN_TYPES_V2`, `maps.py:46`). Fishermen's fish sources
  can ride `fish`; the gold *coins* here are a currency, not a hex (see below).
  Missing terrains (lake, river, oasis, swampland, the three trade hexes) are §5.
- **map-format v2's per-hex metadata.** `HexMeta` carries `docks`, `village`,
  `lair` (`maps.py:266–289`). Fishing-ground frame tiles and trade-hex plazas
  can reuse a metadata slot rather than a new format concept — but oasis arrows,
  bridge-crossing paths and the castle hex need **new** metadata fields (§5).
- **The production funnel.** `Game.production_for` (`game.py:970`) + the ordered
  `modifiers.py` PRODUCTION hook is where a conquered barbarian hex "produces
  nothing" attaches, exactly like `_robber_takes_it_all` (`modifiers.py:213`).
- **The robber-hold pattern.** Fishermen and every scenario that keeps the
  robber off the board until the first 7 (`expansions.md:496,504`) reuses the
  existing `roll_dice` hold-back at `game.py:1247–1256`, which already keeps the
  robber off for `robber_free_opening_rounds` and until the C&K barbarians'
  first attack — a third hold reason drops in beside them.
- **The "7" discard.** Discard-half on a 7 (`expansions.md:663,738`) is
  unchanged; `check_discard_required` (`game.py:1256`) stays as-is. Both
  scenarios that keep the discard while replacing what a 7 *does* to the board
  reuse this.
- **The expansion-state container pattern.** `self.ck` (`game.py:205`) and
  `self.ep` (`game.py:218`) are built only when a rule needs one, and *presence
  is not a rule*. T&B gets an identical `self.tb` container gated by a
  `needs_tb_state()` helper mirroring `needs_ep_state` (`rules.py:1308`).
- **Existing award switches.** Barbarian Attack drops Largest Army
  (`expansions.md:618`); the main scenario drops Longest Road
  (`expansions.md:693`). These are the existing bools `largest_army_card`
  (`rules.py:391`) and `longest_road_card` (`rules.py:387`); the presets set
  them **False**. Do not add new rules.
- **`setup_second_city`.** Both Barbarian Attack (`expansions.md:620`) and the
  main scenario (`expansions.md:695`) place a city instead of the second
  settlement — the existing rule `setup_second_city` (`rules.py:580`,
  read at `game.py:408`). Reuse.
- **`dice_set=no_two_or_twelve`.** The main scenario re-rolls 2s and 12s
  (`expansions.md:739`). The existing `dice_set` CHOICE already has that option
  (`rules.py:183`), and its own `source` already cites `expansions.md:739`.
  Reuse — do not add a rule.
- **The gold *currency substrate*.** `Player.gold` (`player.py:48`) and
  `gold.py`'s `buy_resource_with_gold` (2 gold → 1 resource, twice/turn,
  `gold.py:104`) and robber/Monopoly immunity match T&B's gold spend
  (`expansions.md:559,665,741`) exactly. Reuse the field and the buy helper.
  **But the E&P `gold` rule itself is not reusable wholesale — see Risk 2.**

**Genuinely new (no analogue exists):**

- **Fish tokens** (`expansions.md:501–516`) — a private, face-down token supply
  with a spend-ladder and a 7-token cap, that is *not* a resource card (never
  discarded on a 7, never stolen, never traded). No token-hand concept exists.
- **Gold coins as coins with denominations** (`expansions.md:664,740`) — large=5,
  small=1. The stored total is all that matters, but the T&B gold *sources*
  (rivers, bridges, deliveries, barbarian victories) and its 4:1 maritime sell
  rate (`expansions.md:562`) differ from E&P gold (Risk 2).
- **Bridges** (`expansions.md:546–552`) — a road-like piece on a river-crossing
  path; counts as a road for Longest Road but costs 2 brick + 1 lumber and pays
  3 gold. `edge` has road/ship but no bridge kind.
- **Camels on paths + caravans** (`expansions.md:573–601`) — camel pieces on
  edges (side-by-side with a road), directional (a head), forming non-branching
  caravans from an oasis, placed by a **voting round**. Nothing models a
  non-road/non-ship piece on an edge, nor a directional edge piece.
- **Wagons on intersections with movement** (`expansions.md:696–713`) — a piece
  that sits on a *vertex* and moves vertex-to-vertex spending movement points, a
  mandatory movement phase, and delivery of commodity tokens between trade hexes.
- **The castle-and-knights barbarian war** (`expansions.md:607–662`) — barbarian
  *figures* on coastal hexes, knight *pieces* on the six castle-adjacent paths,
  conquest, victories, prisoners→VP. This is a completely different mechanic from
  the C&K barbarian ship (Risk 1).
- **Path barbarians** (`expansions.md:690,727–737`) — a *third* barbarian kind,
  blocking wagon movement, in the main scenario.
- **Special scenario dev decks** (`expansions.md:617,691`) — 26-card decks that
  replace the base deck outright, like C&K progress cards but scenario-specific.

---

## 1. Rule catalogue

Every mechanic a table could switch, grouped by scenario. Type: BOOL / INT /
CHOICE. All BOOLs are `group=EXPANSION`; INTs default `group=CORE` and are set
`group=EXPANSION` explicitly (as the E&P ints are, `rules.py:768`). "Depends-on"
is the `DEPENDENCIES` entry (refused at start). Defaults are chosen so the base
game is unchanged (every switch off).

### Shared substrate

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `gold_coins` | BOOL | False | 559–565, 664–668, 740–744 | Gold coins are a currency held in `Player.gold`: 2 gold buys 1 resource (twice/turn), 4 identical resources buy 1 gold at the bank (3 with a matching 3:1 harbour, never a 2:1), tradeable with opponents, immune to the robber and Monopoly. **No E&P empty-roll bonus.** | — |

`gold_coins` is the T&B gold rule, distinct from E&P `gold` (`rules.py:660`).
Both write `Player.gold` and share `gold.py`'s buy/immunity helpers, but E&P's
`gold` also grants a 1-gold empty-roll bonus (`gold.py:60`) and sells at 3:1
(`gold.py:26`), neither of which is a T&B rule. They are two economies on one
field: **EXCLUDE them** (§6, Risk 2).

### Fishermen of Catan (489–526)

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `fish_tokens` | BOOL | False | 501–516 | The fish-token supply: draw face-down, hold privately, cap 7, spend by exact fish-total for a benefit (2→send robber off, 3→steal a card, 4→a bank card, 5→a free road, 7→a free dev card); no change given; never counted, discarded on a 7, stolen or traded. Container for the sources below. | — |
| `fishing_grounds` | BOOL | False | 495–499 | Fishing-ground tiles on the frame; settlements adjacent collect 1 fish, cities 2, when the tile's number (4/5/6/8/9/10) is rolled. | `fish_tokens` |
| `lake_hex` | BOOL | False | 493,500 | A lake replaces the desert (never coastal); adjacent settlements draw 1 fish, cities 2, on a 2/3/11/12. | `fish_tokens` |
| `old_boot` | BOOL | False | 517–521 | The old boot (drawn from the fish supply) raises its holder's *personal* winning threshold by 1 and is passed after the roll to any player with equal-or-more VP; the sole VP leader must keep it. | `fish_tokens` |
| `robber_starts_off_board` | BOOL | False | 496,504 | The robber begins beside the board and enters only on the first 7 or knight; fish can send it off again. | — |

INT: `max_fish_held` (7, 1–15, `expansions.md:510`), `fishing_ground_count`
(6, 0–12, `expansions.md:492`).

### Rivers of Catan (527–570)

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `river_gold` | BOOL | False | 542–543 | Building a settlement adjacent to a river hex, or a road on a river-adjacent path, pays 1 gold immediately (setup included). No coin for upgrading to a city. | `gold_coins` |
| `bridges` | BOOL | False | 546–552 | Bridges (2 brick + 1 lumber) built only on the river-crossing paths; each pays 3 gold, counts as a road for Longest Road and connection, max 3/player; a normal road may never sit on a bridge site; Road Building may not place one. | — |
| `wealthiest_settler` | BOOL | False | 556–558 | The sole player with the most gold coins holds a tile worth +1 VP; lost the moment another equals or exceeds it. | `gold_coins` |
| `poor_settler` | BOOL | False | 553–555 | Every player tied for the fewest gold coins holds a tile worth −2 VP; returned the moment they no longer have the fewest. | `gold_coins` |

INT: `max_bridges` (3, 0–10, `expansions.md:551`).

`bridges` depends on the river map (bridge-crossing paths) rather than
`river_gold`; a table could in principle build bridges for the Longest Road
without the coin economy, so they are separate switches.

### Caravans (571–606)

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `caravans` | BOOL | False | 573–601 | Camels grow out of the central oasis in up to three non-branching caravans; each new settlement/city built in a turn places exactly 1 camel via a **voting round** (wool/grain bids); a road sharing a camel's path counts as 2 for Longest Road; a settlement/city between 2 camels is worth +1 VP. | — |

INT: `max_camels` (22, 0–40, `expansions.md:574`).

`caravans` is one container rule: the camel piece, the oasis-arrow geometry, the
voting round and the two scoring effects are inseparable (a camel with no
caravan and no vote is meaningless). Depends on the oasis map (§5), not a
separate rule.

### Barbarian Attack (607–676)

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `barbarian_attack` | BOOL | False | 607–662 | Barbarian figures land on coastal hexes (via building-triggered attack rolls); a hex with 3 is conquered (token face down, adjacent buildings toppled, no VP, harbour dead); players place knight pieces on the six castle-adjacent paths and move them to defend; a defended coastal hex frees its barbarians as prisoners; every 2 prisoners = 1 VP; a post-victory die removes some knights (3 gold each). No robber. | `gold_coins`, `barbarian_attack_deck` |
| `barbarian_attack_deck` | BOOL | False | 617,633–642 | Replaces the base deck with the 26-card Barbarian Attack deck (14 Knighthood, 4 Swift Knight, 4 Treason, 4 Intrigue); each card is revealed and resolved on purchase. | — |

INT: `max_barbarian_knights` (6, 1–12, `expansions.md:615`),
`barbarian_supply` (30, 0–60, `expansions.md:610`).

The knight *pieces* here are the scenario's own; they are **not** the C&K
`knights` rule (`rules.py:494`). See Risk 1 — `barbarian_attack` is EXCLUDED
against `knights`.

### Traders & Barbarians main scenario (677–755)

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `trade_caravans` | BOOL | False | 679,696–719 | A wagon on your starting-city vertex moves vertex-to-vertex in a movement phase, spending points (2 per bare path, 1 per own road, 1+1 gold per rival road), delivering the commodity it carries to the matching trade hex (castle/quarry/glassworks) for gold + 1 VP per delivered token, then drawing its next commodity. | `gold_coins`, `trade_dev_deck` |
| `baggage_train` | BOOL | False | 689,720–726 | An upgradeable per-player card giving wagon movement points (4→7), delivery gold (1→5) and the die numbers that drive off a barbarian; the 5th (final) upgrade is worth 1 VP. | `trade_caravans` |
| `roaming_barbarians` | BOOL | False | 690,727–737,745 | Three barbarians sit on paths, cost 2 extra movement to cross, are moved on a 7 (drawing a card from a crossed road's owner) or by the special Knight card, and can be driven off with a die roll once your baggage train is upgraded. | `trade_caravans` |
| `trade_dev_deck` | BOOL | False | 691,745–748 | Replaces the base deck with the 26-card main-scenario deck (15 Knight-moves-a-barbarian, 3 Road Building, 3 Swift Journey, 1 each Toolmaking/Glassmaking/Quarry worth 1 VP). | — |

INT: `wagon_movement_points` (4, 1–12, `expansions.md:704`).

Reuse (main scenario, no new rule): `dice_set=no_two_or_twelve` (739),
`setup_second_city` (695), `longest_road_card=False` (693), `gold_coins`.

**Rule count: 18 new BOOL + 8 new INT = 26 new catalogue entries**, plus reuse
of `setup_second_city`, `dice_set`, `longest_road_card`, `largest_army_card`,
`victory_target`, and the `Player.gold` / `gold.py` substrate.

### The special dev decks — a `card_system`-style note

`barbarian_attack_deck` and `trade_dev_deck` each *replace* the base development
deck, exactly as C&K progress cards do via `dev_deck_in_play` (`rules.py:1160`).
They could be expressed as new options on a `card_system`-like CHOICE, or as the
two bools above extended into `dev_deck_in_play`. Recommend the two **bools**
(clearer to a table, and each scenario needs exactly one), each folded into
`dev_deck_in_play` in the catalogue commit (§4) so the base deck is closed when
either is on. They EXCLUDE each other and `progress_cards` (three decks, one
board — §6).

---

## 2. New engine modules and dependency order

Each module is a mixin on `Game` (the pattern at `game.py:26`, which composes
`BoardBuilder, TradeRules, RobberRules, SeafarersRules, DevCardRules,
CitiesKnightsRules, PendingChoiceRules, TurnClock` and — after the E&P waves —
the E&P mixins). Disjoint files → parallel agents.

| module | owns | reads (deps) |
|---|---|---|
| `tb.py` (state container) | `TB` class mirroring `ep.py`: fish-token supply + per-player fish hands + old-boot holder; camel positions + caravan chains + the active voting round; wagon vertices + carried commodity + baggage-train levels + trade-hex commodity stacks; barbarian-attack state (coastal-hex barbarian counts, knight-piece positions, prisoner counts, conquered hexes); path-barbarian positions. `register(name)`, `to_dict(viewer)`, `start_turn()`. | — |
| `tb_gold.py` | `gold_coins` sources and rates not shared with E&P: the 4:1 maritime sell, the river/bridge/delivery/victory coin grants. Buy-2-for-1 and immunity are the existing `gold.py` helpers, reused, not re-implemented. | `gold.py` (`Player.gold`, buy helper) |
| `fishing.py` | Fish-token supply draw/spend ladder, the 7-cap, fishing-ground and lake production hooks, the old-boot pass. | `tb.py`, map metadata |
| `rivers.py` | River-adjacency coin grants, bridge build/placement (edge `kind='bridge'`), the wealthiest/poorest tiles into `victory_points_for`. | `tb_gold.py`, map (river hexes / bridge sites) |
| `caravans.py` | Camel placement on edges, caravan-chain geometry from oasis arrows, the voting round (extends `pending_choice.py`), the two scoring effects. | `tb.py`, map (oasis arrows), `pending_choice.py` |
| `barbarian_attack.py` | Coastal-hex barbarian counts, attack rolls on build, conquest/topple, knight-piece placement + movement on castle paths, victory checks + prisoner distribution + knight losses, prisoners→VP. | `tb.py`, `tb_gold.py`, map (castle hex), scenario deck |
| `wagons.py` | Wagon vertex movement + movement points, the commodity delivery loop, trade-hex stacks, baggage-train upgrades, the wagon movement phase. | `tb.py`, `tb_gold.py`, map (trade hexes) |
| `path_barbarians.py` | The main scenario's three path barbarians: cross-cost, move-on-7, drive-off roll. | `tb.py`, `wagons.py` |
| `tb_decks.py` | The two 26-card scenario decks and their per-card resolution, folded into `dev_deck_in_play`. | `dev_card_rules.py` |

**Dependency order (what must land before what):**

```
map-format-v2 extensions ─┬─> fishing
                          ├─> rivers
tb.py (state) ────────────┼─> caravans
                          ├─> barbarian_attack ──> (needs tb_decks + tb_gold)
tb_gold.py ───────────────┼─> wagons ──> path_barbarians
gold.py (shipped) ────────┘
tb_decks.py ──────────────────> barbarian_attack / wagons
```

Independent, can start at once: **map-format-v2 extensions**, **tb.py**,
**tb_gold.py** (once E&P `gold.py` has landed — it has), **tb_decks.py**.
Everything board-dependent waits on the map extensions (§5), the critical path.

---

## 3. Existing-code touch points (all via a rule flag, never an expansion name)

| subsystem | file:line | hook | how |
|---|---|---|---|
| state container | `game.py:205–222` | mirror `self.ck` / `self.ep` | `self.tb = None; if rules.needs_tb_state(self.rules): self.tb = tb.TB(...)`; add TB mixins to the `Game` bases (`game.py:26`) and `self.tb.register(player.name)`. |
| conquered-hex production | `game.py:970` `production_for` + `modifiers.py:229` | new PRODUCTION modifier `conquered_hex` (order 45, after robber at 40) | zero production on a barbarian-conquered coastal hex (`expansions.md:627`), guarded by `_rule_is_on('barbarian_attack')`. Reserve the order in the catalogue commit (§4) as the E&P orders are reserved (`modifiers.py:239`). |
| fish/lake production | `game.py:994` `distribute_resources` | after the resource walk | when `fishing_grounds`/`lake_hex`, draw fish tokens for adjacent buildings on the matching roll (`expansions.md:499,500`); "nobody gets fish if the supply is short" (`expansions.md:501`). Returned in the roll payload like `gold` is (`game.py:1276`). |
| the "7" | `game.py:1247–1256` `roll_dice` | robber-hold + discard | `robber_starts_off_board` adds a third hold reason beside `barbarians`/`robber_free_opening_rounds`; `roaming_barbarians` and the main scenario replace the robber move with a barbarian move (`expansions.md:736`), reusing `must_move_robber` as a generic "resolve the 7" flag, exactly as Seafarers' pirate does. Discard (`check_discard_required`) unchanged (`expansions.md:663,738`). |
| gold currency | `player.py:48`, `gold.py:104` | reuse `Player.gold` + `buy_resource_with_gold` | `tb_gold.py` adds the 4:1 sell and the T&B coin sources; do **not** reuse `gold.py:60` `pay_empty_roll_gold` (E&P-only). |
| scoring | `game.py:757` `victory_points_for` | one entry point | add, each behind its own flag: `wealthiest_settler` +1 / `poor_settler` −2 (`rivers.py`); prisoners//2 and toppled buildings score 0 (`barbarian_attack`); delivered-commodity tokens + final baggage-train card (`trade_caravans`/`baggage_train`); +1 per between-camels building (`caravans`). Same pattern as the C&K/harbormaster/island blocks already there (`game.py:775–795`). |
| personal win threshold | `game.py` win check (via `victory_points_for` callers) | old-boot raise | `old_boot` raises *only its holder's* target by 1 (`expansions.md:518`) — a per-player target, which the current single `victory_target` does not model. New: a `personal_target_delta(player)` read at the win check. (Unverified: exact win-check call site.) |
| build → barbarian attack | `game.py:507` `place_settlement`, `game.py:680` `upgrade_city` | post-build hook | when `barbarian_attack`, resolve an attack after each build (`expansions.md:621`); when `caravans`, queue a camel-voting round at end of turn (`expansions.md:578`). Add as distinct methods, not branches inside the build methods. |
| build guards | `game.py:610` `build_road`, `game.py:507` `place_settlement` | conquest / bridge / camel guards | refuse a road/settlement adjacent to a conquered hex (`expansions.md:628`); refuse a normal road on a bridge site (`expansions.md:541`); allow a road on a camel path (`expansions.md:581`). All flag-gated. |
| Longest Road | (road-length calc; grep `longest_road`) | bridge counts as road; camel path counts double | a bridge is a road segment (`expansions.md:550`); a road sharing a camel's path counts as 2 (`expansions.md:600`). (Unverified: exact function.) |
| edge model | `seafarers.py:152` (`edge.ship`) as precedent | new edge kinds | `edge` has road/ship; add `bridge` (rivers) and `camel` (a directional piece; `caravans`). A camel coexists with a road on one path (`expansions.md:581`). |
| piece supply | `game.py:299` `has_piece_available` | new pieces | `'bridge'`, `'camel'`, `'wagon'`, `'barbarian_knight'`, reading `MAX_*` from the new int rules set at `game.py:194` (the E&P block). |
| dev deck | `dev_card_rules.py`, `rules.py:1160` `dev_deck_in_play` | scenario decks | `barbarian_attack_deck` / `trade_dev_deck` close the base deck and deal their own 26 cards — extend `dev_deck_in_play` (as `progress_cards` does), do not touch `buy_dev_card`. |
| turn phase | `turn_clock.py:34` `start_turn`, `game.py:1215` | wagon movement phase | `trade_caravans` needs a production→build→movement phase like E&P `movement_phase` (`rules.py:654`); if agent H's E&P phase field lands first, reuse it — the wagon is a different *piece* but the same phase machine. Reset per-turn counters (fish/camel/gold conversion) in `start_turn`, beside `self.gold_conversions` (`gold.py:77`). |
| board payload | `game.py:836` `get_board_data` | serialize | new terrains, fishing-ground tiles, bridges, camels (+ heading), wagons (+ carried commodity, redacted per viewer), coastal-hex barbarian counts, knight pieces, prisoner counts, trade-hex stacks (redacted), fish-token counts (own hand only). Mirror `cities_knights`/`ep` at `game.py:920`. |
| board build | `board.py:331` `_apply_map_instance`, `board.py:370` `_create_hexes`, `board.py:780` `_assign_ports` | new terrains + metadata | teach the board about lake/river/oasis/swampland/trade hexes and their metadata; place fishing-ground frame tiles. (Unverified: exact signatures.) |
| map format | `maps.py:46,71,266,503` | see §5 | new terrains, new `HexMeta` fields (oasis arrows, bridge sites, castle, trade-plaza). |
| socket handlers | `handlers/` (grep for `@socketio.on`) | new `handlers/tb_*.py` | move wagon, deliver, upgrade baggage train, build bridge, place/vote camel, place/move knight, resolve barbarian attack, spend fish. Same `@socketio.on` + `session.game.<method>` shape as `handlers/ships.py`. |
| renderer | `static/js/board-renderer.js`, `static/js/board.js` | draw | new terrains, fish counts, bridges, camels, wagons, coastal barbarians, castle knights, trade hexes. No rule logic in JS — the server sends the data. |
| persistence | `persistence.py:175,361` | save/load | `self.tb`, gold, bridges, camels, wagons, barbarian state — the agent that adds each field updates the save list in the same commit. |

**Places T&B fights a current assumption (flag before building):**

- **`victory_target` is one global number** (`rules.py:256`). The old boot makes
  the threshold *per-player* (`expansions.md:518`) — genuinely new.
- **`edge` holds a road or a ship, not a directional piece.** Camels have a head
  and coexist with roads on one path (`expansions.md:581–585`).
- **No vertex-piece movement.** Wagons move vertex-to-vertex
  (`expansions.md:702`); the engine moves nothing on vertices.
- **No multiplayer sub-negotiation.** The camel voting round
  (`expansions.md:591–598`) is a bid/agree/discard interaction unlike anything
  in `pending_choice.py`.
- **Three different "barbarians"** already partly named in code (`barbarians` is
  C&K's, `rules.py:500`) — Risk 1.

---

## 4. The `rules.py` / shared-registry serialization problem

Every implementing agent would otherwise edit `rules.py`, `modifiers.py` and
`handlers/__init__.py` and collide — the exact hazard CLAUDE.md records biting
twice in one day, and the same reason the E&P plan front-loaded one catalogue
commit.

**Recommendation: one catalogue commit up front, single owner**, mirroring the
E&P Wave 0. Before any feature agent starts, a "catalogue agent" lands **one**
commit adding, in a single pass:

1. all 26 T&B `RULES` entries (real `source` line numbers and player-facing
   summaries),
2. the T&B `DEPENDENCIES` entries (§1),
3. the T&B `EXCLUSIONS` groups (§6),
4. a `TB_STATE_RULES` tuple + a `needs_tb_state()` helper mirroring
   `EP_STATE_RULES` / `needs_ep_state` (`rules.py:924,1308`),
5. the five presets (§5),
6. the `barbarian_attack_deck` / `trade_dev_deck` branches in `dev_deck_in_play`
   (`rules.py:1160`),
7. the reserved PRODUCTION-modifier order for `conquered_hex` (45), recorded
   beside the E&P reservations (`modifiers.py:239`), since `register` refuses a
   clash (`modifiers.py:99`).

Committed by explicit path (`git commit -- server/game/rules.py
server/game/modifiers.py`), it is the one serialization point. After it lands,
feature agents **never touch `rules.py`** — they only *read*
`self.rules['their_id']`. This leaves the "picker shows nothing the engine
ignores" test (CLAUDE.md line 118, AGENTS.md line 217) failing briefly (rules
exist before their engine code), acceptable only if the catalogue commit and
Wave 1 land close together — the same trade-off the E&P plan accepted.

---

## 5. Boards & scenarios

**map-format v2 already covers a lot of what T&B needs** — this is the big
difference from where the E&P plan started (E&P had no v2 at all). v2 has:

- `'fixed'` pool mode (`maps.py:71`) → every T&B printed/predetermined layout.
- `gold`/`fish`/`spice` terrains (`maps.py:46`) → Fishermen fish sources can use
  `fish`; the trade-hex commodities are tokens, not terrains.
- `HexMeta{docks, village, lair}` (`maps.py:266`) → fishing-ground and
  trade-plaza markers can reuse a metadata slot.

**What v2 still needs added for T&B** (Wave 1, one agent — the critical path):

| gap | source | why v2 doesn't cover it |
|---|---|---|
| `lake` terrain (never coastal) | 493,500 | a lake pays fish on 2/3/11/12 from a *four-number* token, unlike any current terrain. |
| `river` terrain + river-crossing path metadata | 529,541 | rivers pay coins for *adjacency* and define bridge-only paths — no path-level metadata exists (`HexMeta` is per-hex only). |
| `oasis` terrain + **arrow metadata** | 575,583 | the three caravan-start arrows are a new `HexMeta` field; nothing today carries edge-direction metadata. |
| `swampland` terrain (no token, robber start) | 534,536 | a hex that skips a number token and hosts the robber at setup. |
| `castle` / `quarry` / `glassworks` trade hexes + plaza/sea-path metadata | 682,697–700 | a hex with a central *plaza vertex*, four interior build paths, and three un-buildable sea-border paths — richer than `docks`. |
| `castle` hex (Barbarian Attack) + un-conquerable flag | 611,632 | a hex knights guard and that can never be conquered. |

Per scenario:

| scenario | expressible in current v2? | needs first | suggested target |
|---|---|---|---|
| Fishermen | Partly (fixed layout + `fish`) | `lake` terrain, fishing-ground frame tiles, fish-token supply | 10 (11 w/ boot) — 522 |
| Rivers | No | `river`/`swampland` terrain, river-crossing path metadata, bridge sites | 10 — 566 |
| Caravans | No | `oasis` terrain + arrow metadata | 12 — 602 |
| Barbarian Attack | No | `castle` hex + un-conquerable flag, coastal-hex barbarian tracking | 12 — 669 |
| T&B main | No | 3 trade hexes + plaza/sea-path metadata | 13 — 749 |

### Presets

One per scenario, each ticking individual rules and *suggesting* a target the
lobby can change (Harbormaster adds 1 to each — 523,567,603,670,750). Every
scenario ticks `gold_coins` where it has coins and EXCLUDES the E&P `gold`.

- `tb_fishermen` — `fish_tokens`, `fishing_grounds`, `lake_hex`, `old_boot`,
  `robber_starts_off_board`, `victory_target=10` (522).
- `tb_rivers` — `gold_coins`, `river_gold`, `bridges`, `wealthiest_settler`,
  `poor_settler`, `victory_target=10` (566).
- `tb_caravans` — `caravans`, `victory_target=12` (602).
- `tb_barbarian_attack` — `barbarian_attack`, `barbarian_attack_deck`,
  `gold_coins`, `setup_second_city`, `largest_army_card=False`,
  `victory_target=12` (669).
- `tb_main` — `trade_caravans`, `baggage_train`, `roaming_barbarians`,
  `trade_dev_deck`, `gold_coins`, `setup_second_city`, `longest_road_card=False`,
  `dice_set='no_two_or_twelve'`, `victory_target=13` (749).

**Preset-id collision:** the existing preset `traders_and_barbarians`
(`rules.py:1067`) is the *two variants*, not the main scenario. The main
scenario's preset **must** use a different id — `tb_main` above. Do not reuse or
overwrite `traders_and_barbarians`.

---

## 6. The Barbarian Attack ⇄ C&K barbarians question (verified in code)

**They are different mechanics that already share the word and one rule id, and
they must be mutually exclusive.**

- **C&K `barbarians`** (`rules.py:500`) is a *ship on a track*
  (`cities_knights.py:182` `barbarian_position`, `barbarian_track_length`) that
  advances on an event die (`game.py:1245`) and attacks *all cities at once*
  when it arrives. It DEPENDS on C&K `knights` (`rules.py:829`), which are
  network pieces.
- **T&B Barbarian Attack** (`expansions.md:607–662`) has barbarian *figures on
  coastal hexes*, its own knight *pieces on castle-adjacent paths* placed via a
  scenario dev deck, conquest and prisoners. Nothing about it is a track or an
  event die.

They share no state and no code path — but the T&B scenario cannot reuse the
`barbarians` id (taken) or the `knights` id (taken, different meaning). So:

1. **New ids** `barbarian_attack` and `barbarian_attack_deck` — never `barbarians`.
2. **Hard EXCLUSION `barbarian_attack` vs `knights`.** This is exactly the
   pattern the shipped `sea_ship_model` exclusion uses for transport vs
   Seafarers ships (`rules.py:887`): because C&K `barbarians` DEPENDS on
   `knights` (`rules.py:829`), barbarians-without-knights is unreachable, so
   excluding `barbarian_attack` from `knights` **alone** refuses every reachable
   both-on state (C&K knights *and* C&K barbarians coexisting with T&B's war)
   without making a clique that would refuse C&K's own knights+barbarians combo.
   Reason: "Two knight-and-barbarian systems on one board — the Cities & Knights
   barbarian ship measured against your cities, and the Barbarian Attack figures
   on the coast fought off by knights at the castle. Pick one."
3. **The three barbarian kinds** — C&K `barbarians`, T&B `barbarian_attack`, T&B
   `roaming_barbarians` — are pairwise incompatible. `roaming_barbarians`
   DEPENDS on `trade_caravans`, which is its own world; add EXCLUSIONS
   `barbarian_attack` vs `roaming_barbarians`, and `roaming_barbarians` vs
   `knights` (same reasoning as #2 for the C&K side).
4. **Scenario decks are mutually exclusive:** `barbarian_attack_deck`,
   `trade_dev_deck` and `progress_cards` each replace the base deck — one deck
   per board. EXCLUSION group `{barbarian_attack_deck, trade_dev_deck,
   progress_cards}`, kind hard.

**Recommendation: mutually exclusive, via the EXCLUSIONS above.** They cannot
coexist coherently and the exclusion machinery (`rules.py:863`, already
enforcing the ships case) expresses it exactly. No shared id, no shared state,
no clash — provided the new rules never touch the `barbarians`/`knights` ids.

---

## 7. Phased build order + honest risk list

Every agent lands its behaviour with a **failing test first** (CLAUDE.md line
39): write the test, watch it fail for the reason the behaviour describes, then
implement. Costs/counts get rulebook-pin tests; bugs get regression tests named
after the failure; player-visible board changes get browser tests
(`tests/test_browser_*.py`). One verification browser pass, per the project
memory — never triple-run.

**Wave 0 — serialize (1 agent, must land first):** the single catalogue commit
(§4) + the `tb.py` state-container skeleton (`register`/`to_dict`/`start_turn`).

**Wave 1 — disjoint foundations (4 agents, parallel):**
- A: **map-format v2 extensions** (`maps.py`, `board.py`, `hex_models.py`) — §5.
  The critical path; staff first and heaviest.
- B: **tb_gold** (`tb_gold.py`, 4:1 sell + coin sources on `Player.gold`).
- C: **tb_decks** (`tb_decks.py`, the two scenario decks + `dev_deck_in_play`).
- (tb.py from Wave 0 is shared read-only state.)

**Wave 2 — Fishermen + Rivers (2 agents, parallel):**
- D: **fishing** (`fishing.py`) — needs A.
- E: **rivers** (`rivers.py`) — needs A + B.

**Wave 3 — Caravans + Barbarian Attack (2 agents, parallel):**
- F: **caravans** (`caravans.py`, incl. the voting round) — needs A + `pending_choice.py`.
- G: **barbarian_attack** (`barbarian_attack.py`) — needs A + B + C.

**Wave 4 — main scenario (2 agents):**
- H: **wagons** (`wagons.py`, movement phase + delivery) — needs A + B + C.
- I: **path_barbarians** (`path_barbarians.py`) — needs H.

**Wave 5 — surface (2 agents):**
- J: **renderer + handlers** (`handlers/tb_*.py`, `board-renderer.js`) — needs
  the server methods landed.
- K: **scenario maps + preset verification** — the five map files; presets ship
  in Wave 0's `rules.py` commit, the maps wait on A.

`persistence.py` updates ride along with each subsystem that adds state.

### Risk list (honest)

**Risk 1 — three "barbarian" mechanics and a live id clash, and this is where
"individual rules, no modes" is tested.** C&K `barbarians` (ship-on-track,
`rules.py:500`/`cities_knights.py:182`), T&B `barbarian_attack` (coastal figures
+ castle knights), and T&B `roaming_barbarians` (path blockers) are three
distinct systems. The name and the `barbarians`/`knights` ids are already taken
by C&K. The clean answer (§6) is new ids plus hard EXCLUSIONS mirroring the
shipped `sea_ship_model` refusal — which keeps the individual-rules model intact
and needs no shared state. **Recommend the owner confirm the exclusions rather
than have an agent decide mid-build**, exactly as the E&P plan asked for the
ships case.

**Risk 2 — the E&P `gold` rule is not reusable wholesale, and T&B gold forks
it.** The shipped `gold` rule (`rules.py:660`, `gold.py`) bundles three things:
the currency + buy-2-for-1 (which T&B shares, `expansions.md:559,665,741`), a
3:1 maritime sell (`gold.py:26`), and a 1-gold empty-roll bonus (`gold.py:60`).
T&B has **no empty-roll bonus** and sells at **4:1** (`expansions.md:562`). So
T&B cannot tick `gold`; it needs `gold_coins`, sharing `Player.gold` and the buy
helper but not the E&P-specific behaviours, and EXCLUDING `gold` (two economies
on one field). The cleaner long-term shape — refactor `gold.py` into a currency
substrate + source-specific flags — is a modification to shipped E&P code that
would collide with the E&P agent still working this tree, so it is **an owner
decision, not an agent's**: accept the parallel `gold_coins` rule (recommended,
low-risk), or schedule a substrate refactor after E&P lands.

**Risk 3 — new piece-on-edge and piece-on-vertex models the engine lacks.**
Bridges (edge `kind`), camels (a *directional* edge piece coexisting with a
road, `expansions.md:581–585`), and wagons (a *moving vertex* piece,
`expansions.md:702`) have no analogue: `edge` holds a road or a Seafarers ship
(`seafarers.py:152`), and nothing moves on vertices. Each is genuinely new
infrastructure, isolated to its module but touching `has_piece_available`, the
Longest-Road calc (bridge/camel), `get_board_data` and the renderer.

**Other unknowns.**
- **The camel voting round** (`expansions.md:591–598`) — a bid/agree/discard
  multiplayer sub-negotiation beyond `pending_choice.py`; the single most
  intricate interaction in the expansion and the biggest schedule risk in Wave 3.
- **Per-player win threshold** (old boot, `expansions.md:518`) — the engine's
  single `victory_target` (`rules.py:256`) cannot express it; needs a
  per-player delta at the win check (call site unverified).
- **Wagon movement phase** overlaps E&P's `movement_phase` machine
  (`rules.py:654`); reuse it if that agent's phase field lands first, else build
  it — a wide handler surface either way (`turn_clock.py`, the build handlers).
- **File contention with the E&P agent.** Both plans touch `game.py`,
  `player.py`, `modifiers.py`, `gold.py`, `maps.py`, `board.py`, `rules.py`,
  `persistence.py` and `handlers/`. The single-catalogue-commit discipline (§4)
  and CLAUDE.md's "commit by explicit path" rule are the only guards; T&B waves
  should not begin editing a shared file until the corresponding E&P wave has
  committed, or the two will collide on `game.py`'s constructor and
  `victory_points_for` in particular.

**Can every scenario be individual rules?** Yes — all five decompose into the 26
switches above with container+member rules, the same shape as C&K and E&P. The
two places the model strains are Risk 1 (three barbarian systems, resolved by
exclusions) and Risk 2 (T&B gold forking E&P gold, resolved by a parallel rule).
Neither requires a "mode"; both are owner confirmations, not agent decisions.
The one mechanic that is awkward but not impossible is the **special dev decks
replacing the base deck** — expressible through `dev_deck_in_play` exactly as
C&K progress cards already are, so no new machinery, just three mutually
exclusive deck rules.
