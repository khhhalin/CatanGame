# Explorers & Pirates — decomposition plan

A build plan for implementing Catan: Explorers & Pirates (E&P) in this engine as
**individual switchable rules**, decomposed the way Cities & Knights and
Seafarers already are. This is a plan only; no engine code is written here.

The governing law (CLAUDE.md "Rules are individual") is absolute and repeated
here because every step below obeys it: **no engine code may branch on the name
of an expansion.** There is never a `rules['explorers_and_pirates']`. Each
mechanic is its own rule read where it applies. A preset named
`explorers_and_pirates` merely *ticks* the individual rules; nothing records
that a preset was used. A rule may **suggest** a victory target
(`suggests_victory_target`) but never overwrite one, and a rule that cannot act
alone declares what it needs in `DEPENDENCIES` (CLAUDE.md/AGENTS.md call the
concept "INCOHERENT_RULES"; the code's actual dict is `DEPENDENCIES` at
`server/game/rules.py:682`) — refused at `start_game`, never propped up.

Source line numbers are `expansions.md`. Touch points are `file:line`.
"Unverified" marks a claim not confirmed by reading the code.

---

## 0. What E&P reuses vs. what is genuinely new

**Reused from the existing engine (do not rebuild):**

- **Sea-board geometry.** `SeafarersRules.is_sea_edge` (`seafarers.py:26`) and
  `land_hexes_of_edge` decide which hex sides are sea routes — pure geometry,
  independent of any rule. E&P ship movement rides the same sea edges.
- **The "7" hand-back.** Discard-half on a 7 is unchanged (842); `check_discard_required`
  and the discard handler (`handlers/robber.py:54`) stay as-is. E&P touches only
  what a 7 does to the board, not the discard.
- **The robber-diversion pattern.** Seafarers already replaces the robber with a
  pirate by reusing `must_move_robber` / `steal_from_victim`
  (`seafarers.py:365`, `robber_rules.py:76`). E&P's per-player pirate ship
  follows the same shape.
- **The production funnel.** `Game.production_for` (`game.py:939`) + the ordered
  `modifiers.py` PRODUCTION hook is where "a harbor settlement yields 1, not 2"
  and "a liberated gold field pays 2 gold per adjacent building" attach — as new
  modifiers, exactly like `_city_production` / `_epidemic`.
- **The expansion-state container pattern.** `self.ck` is built only when a rule
  needs it (`game.py:203`, `rules.EXPANSION_STATE_RULES`), and its *presence is
  not a rule*. E&P gets an identical `self.ep` container.
- **Existing award switches.** E&P drops Longest Road and Largest Army (840).
  These are already the individual bools `longest_road_card` and
  `largest_army_card` (`rules.py:387,391`). The preset sets them **False**. Do
  not add new rules for this.
- **Bank/gold-ish trades.** The 3:1 same-type bank trade (856) is the existing
  `bank_trade_rate` int set to 3 in the preset. Reuse it.

**Genuinely new (no analogue exists):**

- **Ships as cargo transport with movement points** (864–882). The existing
  `edge.ship` is a *route connector* (Seafarers): no hold, no movement points,
  moved once/turn free, and it *extends the shipping network*
  (`_touches_own_route`, `game.py:712`; `ship_connects`, `seafarers.py:46`). An
  E&P ship carries cargo, has 4 movement points, explores, and **forms no routes
  at all** (866). This is the sharpest conflict in the whole expansion — see
  Risk 1.
- **Exploration of face-down tiles** (883–893) — no hidden-tile concept exists;
  `maps.py` deals every tile face-up.
- **New hex types** — gold field, fish shoal, spice (848, 963). The map format's
  `gold` terrain is explicitly *reserved for v2 and refused today*
  (`maps.py:36–39`).
- **Harbor settlements** (894–902) — a new building type worth 2 VP with a cargo
  basin, the only build site for ships/settlers/crews.
- **Cargo pieces** — settlers (903–918) and crews (919–928).
- **Gold currency** (960–967) — a second currency beside resources.
- **Missions** (969–1040) — tracks, markers, mission-lead VP cards.
- **A mandatory movement phase** (851–862) with "no build after movement".

---

## 1. Rule catalogue

Every mechanic a table could switch, grouped by subsystem. Type: BOOL / INT /
CHOICE. All are `group=EXPANSION`. "Depends-on" is the `DEPENDENCIES` entry
(refused at start, never auto-enabled). Defaults are chosen so the base game is
unchanged (every switch off).

### Turn structure & economy

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `movement_phase` | BOOL | False | 851–862 | A turn runs production → trade/build → movement, in that fixed order; you may not build after moving (one exception: founding a settlement with a settler ship). | `transport_ships` |
| `gold` | BOOL | False | 854, 960–967 | Gold is a second currency: 1 gold when a non-7 roll pays you nothing (854), 3 like resources → 1 gold, 2 gold → any 1 resource twice/turn, tradeable with opponents. | — |
| `no_dev_cards` | BOOL | False | 839 | No development cards exist — the deck cannot be bought from. | — |
| `no_city_upgrades` | BOOL | False | 838 | Settlements are never upgraded to cities; city pieces are unused. | — |

`no_city_upgrades` could instead be expressed by setting the existing
`max_cities` int to 0 (`rules.py:299`), which already makes `upgrade_city`
refuse with `NO_PIECES_LEFT`. Recommend a dedicated bool anyway: the semantic
("this game has no cities") is clearer to a table than a piece-count of 0, and
`victory_points_for` needs the flag to stop scoring cities regardless.

### Ships, harbors, cargo (the transport system)

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `transport_ships` | BOOL | False | 864–882 | Ships are transports carrying pieces in a hold (1 large or 2 small), with 4 movement points along sea routes; they never form routes. Built at a harbor settlement for 1 lumber + 1 wool. | `harbor_settlements` |
| `harbor_settlements` | BOOL | False | 894–902 | Upgrade a coastal settlement (2 grain + 2 ore) into a harbor settlement worth 2 VP with a cargo basin; the only site where ships, settlers and crews may be built. Yields 1 (not 2) on production. | — |
| `ships_explore` | BOOL | False | 883–893 | Moving a ship so an end points at an undiscovered hex reveals it; discovery ends that ship's movement. | `transport_ships` |
| `cargo_settlers` | BOOL | False | 903–918 | Settlers (cost = a settlement) are built into a basin/hold and carried by ship; a settler ship pointing at a coastal corner founds a settlement there for free. | `transport_ships`, `harbor_settlements` |
| `crews` | BOOL | False | 919–928 | Crews (1 ore + 1 wool) ride ships and are placed on mission destinations only. | `transport_ships`, `harbor_settlements` |
| `transshipping` | BOOL | False | 929–932 | A loaded ship pointing at a loaded harbor settlement may swap the pieces between hold and basin. | `transport_ships`, `harbor_settlements` |

### Pirate

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `pirate_ship_instead_of_robber` | BOOL | False | 841, 843, 934–949 | The roller of a 7 places their own pirate ship on an allowed sea hex, steals 1 card from an opponent with a ship there, and thereafter charges every mover 1 gold tribute per ship crossing that hex. No robber, no blocked land. | `gold` |
| `chase_pirate` | BOOL | False | 951–958 | A battle-ready ship (unmoved, adjacent to the pirate hex) may roll 1 die; a 6 chases the pirate away and lets the chaser reposition it and steal. | `pirate_ship_instead_of_robber`, `transport_ships` |

### Missions

| rule id | type | default | source | summary | depends-on |
|---|---|---|---|---|---|
| `missions` | BOOL | False | 969–978 | Mission tracks with per-player markers; a marker ahead of every other on a track holds that mission's 1-VP lead card. Container for the three missions below. | — |
| `mission_pirate_lairs` | BOOL | False | 980–998 | Discover gold-field/pirate-lair hexes, land crews to capture lairs, advance the Pirate Lairs track; a captured lair's number pays 2 gold per adjacent building. | `missions`, `crews` |
| `mission_fish` | BOOL | False | 1000–1019 | Catch fish hauls at discovered shoal hexes and deliver them to the Council of Catan docks to advance the Fish track. | `missions`, `transport_ships` |
| `mission_spices` | BOOL | False | 1021–1040 | Trade crews for spice sacks at village hexes (each village grants a permanent advantage) and deliver sacks to the Council to advance the Spices track. | `missions`, `crews` |

### Numbers (INT)

| rule id | type | default | min–max | source | summary |
|---|---|---|---|---|---|
| `max_harbor_settlements` | INT | 4 | 0–20 | 849 | Harbor settlements per player. |
| `max_settlers` | INT | 2 | 0–10 | 849 | Settlers per player. |
| `max_crews` | INT | 9 | 0–20 | 849 | Crews per player. |
| `ship_movement_points` | INT | 4 | 1–12 | 874 | Movement points a ship has per turn (before wool/Swift-Voyage bonuses). |
| `starting_gold` | INT | 0 | 0–10 | 1045, 1053 | Gold each player starts with (2 in every E&P scenario). |

Reuse the existing `max_ships` int (`rules.py:662`, default 15) — the preset
sets it to **3** (849). Do **not** add a second ships-count rule.

### CHOICE rules (mission advantages, if modelled as options rather than derived state)

The three spice-village advantages (1031–1040) — Swift Voyage (+1 MP), Pirate
Bonus (chase on 4/5/6), Fast Gold (sell 1 resource → 1 gold) — are *earned in
play*, not chosen in the lobby, so they are **not** catalogue rules. They live in
`ep` state and are read by `ship_movement_points`, the chase roll, and the gold
trade respectively. Listed here only to record the decision that they are not
rules.

**Rule count: 17 new catalogue entries** (11 BOOL + 5 INT + reuse of
`max_ships`, `bank_trade_rate`, `longest_road_card`, `largest_army_card`,
`victory_target`).

### Presets

One preset per scenario, each ticking individual rules and suggesting a target
(never setting it behind the table's back — the preset writes `victory_target`,
which the lobby can change). Targets: Land Ho! 8 (1049), Pirate Lairs 12 (1060),
Fish 15 (1068), Spices 15 (1075), main E&P 17 (1084).

- `ep_land_ho` — `harbor_settlements`, `transport_ships`, `ships_explore`,
  `cargo_settlers`, `movement_phase`, `gold`, `no_dev_cards`, `no_city_upgrades`,
  `longest_road_card=False`, `largest_army_card=False`, `bank_trade_rate=3`,
  `max_ships=3`, `starting_gold=2`, `victory_target=8`.
- `ep_pirate_lairs` — Land Ho! plus `crews`, `transshipping`,
  `pirate_ship_instead_of_robber`, `chase_pirate`, `missions`,
  `mission_pirate_lairs`, `victory_target=12`.
- `ep_fish` — Pirate Lairs plus `mission_fish`, `victory_target=15`.
- `ep_spices` — Fish minus `mission_pirate_lairs` plus `mission_spices`,
  `victory_target=15` (1071: lairs removed).
- `explorers_and_pirates` — all three missions on, `victory_target=17` (1077–1084).

---

## 2. New engine modules and dependency order

Each module is a mixin on `Game` (the established pattern; `game.py:24` composes
`BoardBuilder, TradeRules, RobberRules, SeafarersRules, DevCardRules,
CitiesKnightsRules, PendingChoiceRules, TurnClock`). Disjoint files → parallel
agents.

| module | owns | reads (deps) |
|---|---|---|
| `ep.py` (state container) | `EP` class: per-player pirate hex, mission tracks + markers + lead-card holders, hidden-tile pool & reveal order, token supplies (fish hauls, spice sacks, lair tokens), village advantages earned. Mirrors `cities_knights.py`. `register(name)`, `to_dict(viewer)`, `start_turn()`. | — |
| `harbor_settlements.py` | `build_harbor_settlement` (upgrade a coastal settlement), basin state on the vertex building, coastal test. | `is_sea_edge` geometry |
| `gold.py` | Gold as a `Player.gold` int; helpers for gain/spend, the empty-roll bonus, 3→1 and 2→1 conversions, and the gold PRODUCTION modifier for gold fields. | — |
| `transport.py` | E&P ship build/move: hold/cargo on `edge.ship`, movement points, load/unload, the movement-phase state machine. **Not** route logic. | `harbor_settlements`, `is_sea_edge` |
| `exploration.py` | Hidden-tile pool, discovery trigger on ship movement, reveal + reward (resource or 2 gold), the "no build adjacent to undiscovered" guard. | map-format v2, `transport.py` |
| `cargo.py` | Settlers & crews: build into basin/hold, load/unload, found-settlement-by-settler-ship, crew placement on destinations. | `transport.py`, `harbor_settlements` |
| `ep_pirate.py` | Per-player pirate placement on 7, steal, gold tribute on movement, chase roll. | `gold.py`, `transport.py`, robber-diversion pattern |
| `missions.py` | Track state, marker advance, lead-card recomputation, mission VP into `victory_points_for`. | `ep.py` |
| `missions_lairs.py` / `missions_fish.py` / `missions_spices.py` | Per-mission destination logic (lair capture + hero roll; fish catch/deliver; spice trade/deliver + advantages). Split so three agents work disjoint. | `missions.py`, `cargo.py`, `exploration.py`, map-format v2 |

**Dependency order (what must land before what):**

```
map-format-v2 ─┐
               ├─> exploration ─┐
transport ─────┤                ├─> missions_lairs / missions_fish / missions_spices
harbor_settle ─┤                │
gold ──────────┼─> ep_pirate    │
               └─> cargo ────────┘
missions (container) ───────────┘
ep.py (state) is a wave-0 sibling of the catalogue; everything above hangs state on it.
```

Independent (no ordering between them): `map-format-v2`, `gold`,
`harbor_settlements`, `ep.py` can all start at once. `transport` waits on
`harbor_settlements` only.

---

## 3. Existing-code touch points (all via a rule flag, never an expansion name)

| subsystem | file:line | hook | how |
|---|---|---|---|
| state container | `game.py:203–211` | mirror `self.ck` | `self.ep = None; if rules.needs_ep_state(self.rules): self.ep = ep.EP(...)`; add EP mixins to the `Game` bases at `game.py:24`. |
| harbor yield | `game.py:939` `production_for` + `modifiers.py:157` | new PRODUCTION modifier `harbor_settlement_yield` (applies when building_type == `'harbor_settlement'`, forces resources→1), and `gold_field` (2 gold per adjacent building on a liberated field, 998). New building type `'harbor_settlement'` recognised at the settlement/city checks (`game.py:988`, `game.py:1058`). |
| empty-roll gold | `game.py:963` `distribute_resources` | after the walk, if `rules['gold']` and a player produced nothing on a non-7 roll, grant 1 gold (854). Returned in the roll payload like `gained`. |
| the "7" | `game.py:1201–1210` `roll_dice` | when `pirate_ship_instead_of_robber`, set `must_move_robber` (reused flag) but resolve via a new `place_pirate_ship` instead of `move_robber`, exactly as Seafarers' `move_pirate` reuses the flag (`seafarers.py:378`). Discard path (`check_discard_required`) unchanged. |
| pirate steal | `robber_rules.py:76` `steal_from_victim` | reuse for the pirate's card theft; the "no cards → take 1 gold" branch (943) is a new fallback guarded by `rules['gold']`. |
| city upgrade | `game.py:660` `upgrade_city` | refuse when `no_city_upgrades` (or `max_cities==0` already refuses); add the *harbor* upgrade as a separate `build_harbor_settlement` method, not a branch here. |
| build guards | `game.py:487` `place_settlement`, `game.py:590` `build_road` | when `ships_explore`, refuse a build adjacent to an undiscovered hex (891); add the settler-ship founding path (guarded by `cargo_settlers`) as a distinct method. |
| network expansion | `game.py:712` `_touches_own_route` | **must not** treat E&P transport ships as route extenders. Guard: transport-ship edges never count here (see Risk 1). Seafarers `ship_connects`/`build_ship`/`move_ship` (`seafarers.py:46,100,286`) are **not** used by transport ships. |
| scoring | `game.py:737` `victory_points_for` | add: 2 per harbor settlement, mission VP + lead cards, and stop counting cities under `no_city_upgrades`. Same single-entry-point pattern as the C&K/island/harbormaster blocks already there. |
| Player state | `player.py:39–43`, `player.py:126` | add `harbor_settlements`, `settlers`, `crews`, `gold` fields and supply lists; `get_victory_points` counts harbor settlements at 2. `to_dict` (`player.py:95`) exposes gold/cargo counts. |
| piece supply | `game.py:279` `has_piece_available` | add `'harbor_settlement'`, `'settler'`, `'crew'`, reading `MAX_*` set from the new int rules at `game.py:194`. |
| dev deck | `dev_card_rules.py:21` `dev_deck_in_play`, `rules.py:825` | `no_dev_cards` makes the deck unbuyable — extend the existing `dev_deck_in_play` predicate (don't touch `buy_dev_card` directly). |
| turn phase | `turn_clock.py:34` `start_turn`, `game.py:1201` | add a per-turn phase field (`production`/`build`/`movement`) when `movement_phase`; reset in `start_turn`; build handlers refuse once movement has begun. |
| board payload | `game.py:816` `get_board_data` | serialize: new hex types + face-down state (redacted per viewer — a hidden tile's identity is secret like a dev card, `game.py:894`), `edge.ship.cargo`, harbor settlements, per-player pirate hexes, mission tracks, gold, token supplies. |
| board build | `board.py:331` `_apply_map_instance`, `board.py:370` `_create_hexes`, `board.py:780` `_assign_ports` | teach the board about gold/fish/spice hexes and face-down/hidden tiles; E&P has no base-game harbours (844), so `_assign_ports` is skipped when the map declares none. (Unverified: exact signatures beyond names.) |
| map format | `maps.py:39,51,56,230` | see §5 — new terrain types, a hidden/exploration pool mode, special-hex metadata. |
| socket handlers | `handlers/ships.py:50`, `handlers/robber.py:24` | new `handlers/ep_*.py` (build/move transport ship, build harbor settlement, load/unload cargo, place/chase pirate, mission actions), registered in `handlers/__init__.py`. Same `@socketio.on` + `session.game.<method>` shape. |
| renderer | `static/js/board-renderer.js`, `static/js/board.js` | draw new hex types, face-down icons, cargo, harbor settlements, per-player pirates, mission tracks, gold counts. No new rule logic in JS — the server sends `sea`/costs/etc. (`game.py:848`). |
| persistence | `persistence.py:175,361` | save/load `self.ep`, gold, cargo, pirate hexes, mission state. |

**Places E&P fights a current assumption (flag before building):**

- `edge.ship` is `{player, built_turn}` with **no cargo field** (`seafarers.py:152`).
  Transport needs a hold; extend the dict (`cargo`, `kind`).
- Turn structure assumes **roll → free build until `advance_turn`**; there is no
  phase machine (`turn_clock.py`, `game.py:1201`). Movement phase is new.
- **Cities are assumed** in production (`game.py:988`), scoring
  (`player.py:126`), and `upgrade_city`. `no_city_upgrades` must be honoured in
  each.
- The map format assumes **every tile is dealt face-up and shuffled** (`gold`
  terrain refused, `maps.py:39`; only `POOL_MODES=('shuffled',)`, `maps.py:56`;
  `fog` kind refuses to start, `maps.py:230,563`).

---

## 4. The `rules.py` serialization problem

Every implementing agent would otherwise edit `rules.py` to add its rule entry,
and they would collide on the same `RULES` list, `DEPENDENCIES`,
`EXPANSION_STATE_RULES` and `PRESETS` — the exact hazard CLAUDE.md records biting
twice in one day.

**Recommendation: one catalogue commit up front, single owner.** Before any
feature agent starts, a "catalogue agent" lands **one** commit to `rules.py`
adding, in a single pass:

1. all 17 E&P `RULES` entries (with real `source` line numbers and summaries),
2. the E&P `DEPENDENCIES` entries,
3. an `EP_STATE_RULES` tuple + a `needs_ep_state()` helper mirroring
   `EXPANSION_STATE_RULES` / `needs_expansion_state` (`rules.py:707,952`),
4. the five presets,
5. a `no_dev_cards` branch in `dev_deck_in_play` (`rules.py:825`) if that rule
   is chosen over the max_cities approach.

Committed by explicit path (`git commit -- server/game/rules.py`), it is the one
serialization point. After it lands, **feature agents never touch `rules.py`** —
they only *read* `self.rules['their_id']`. This keeps the "picker shows nothing
the engine ignores" test (CLAUDE.md line 118, AGENTS.md line 217) failing
briefly (rules exist before their engine code) — acceptable *if* the catalogue
commit and Wave-1 land close together; the alternative (each agent adds its own
entry with its code) reintroduces the collision. Prefer the single owner and
sequence Wave 1 immediately after.

Same discipline for the two other shared registries: **`modifiers.py`** (each
new PRODUCTION modifier needs a unique `order` int, `modifiers.py:88` refuses a
clash) and **`handlers/__init__.py`** (handler registration). Assign the modifier
`order` values in the catalogue commit too (e.g. harbor yield 15, gold field 25,
between the existing 10/20/30/40) so agents don't race for numbers.

---

## 5. Boards & scenarios

The current map format (`maps.py`, v1) **cannot express any of the five
scenarios.** Three gaps, all in the format, all prerequisites:

1. **Hidden / face-down tiles** (884–890). v1 deals every tile face-up
   (`maps.py:655` `instantiate`). Exploration needs a pool that is placed
   icon-side-up and revealed on discovery, with a per-icon number-token stack
   drawn at reveal time (887). Nothing models this. The `fog` region kind parses
   but *refuses to start* (`maps.py:230,563`) — the natural hook to extend into a
   real "unexplored area", but it is currently a dead end.
2. **Fixed (printed) layouts** (1046 Land Ho! predetermined positions; 1042–1049).
   `POOL_MODES=('shuffled',)` only (`maps.py:56`); a fixed pool "is v2" per the
   comment. The beginner base-game map already can't be expressed for the same
   reason.
3. **New hex types + special-hex metadata.** `gold` terrain is reserved for v2
   and refused (`maps.py:36–39`); fish-shoal and spice hexes don't exist; the
   Council of Catan hex is a sea hex with 2 docks and asymmetric build rules
   (1002–1005), and spice/lair hexes carry villages/tokens. `TERRAIN_TYPES`
   (`maps.py:39`) and `Hex.type` (`hex_models.py:21`) need extending, and hexes
   need per-hex metadata the current dumb `MapInstance` (`maps.py:313`) has no
   slot for.

Per scenario:

| scenario | expressible in current format? | needs first |
|---|---|---|
| Land Ho! | No | fixed pools (1046) + hidden tiles + new hex types |
| Pirate Lairs | No | hidden tiles + gold-field/lair hexes + free-setup variant (1055) |
| Fish for Catan | No | above + Council-of-Catan hex with docks (1002–1005) |
| Spices for Catan | No | above + spice/village hexes + advantages |
| Explorers & Pirates | No | all of the above; 7+3+3+3 hex shuffle per unexplored area (1082) |

So a **map-format v2** (Wave 1, agent A) is a hard serial prerequisite for every
board-dependent subsystem. It must add: a hidden/exploration pool mode; the
gold/fish/spice terrain types; per-hex metadata (docks, village advantage, lair);
and a fixed-pool mode (also unblocks the beginner map, a nice side effect). This
is the single largest new piece of infrastructure.

---

## 6. Phased build order

Every agent lands its behaviour with a **failing test first** (CLAUDE.md line
39): write the test, watch it fail *for the reason the behaviour describes*, then
implement. Costs/counts get rulebook-pin tests; bugs get regression tests named
after the failure; player-visible board changes get browser tests
(`tests/test_browser_*.py`).

**Wave 0 — serialize (1 agent, must land before the rest):**
- Catalogue agent: the single `rules.py` + `modifiers.py` order-assignment +
  `handlers/__init__.py` reservation commit (§4). Also `ep.py` state container
  skeleton (`EP` class, `register`/`to_dict`/`start_turn`) so Wave-1 agents have
  a state object to hang fields on.

**Wave 1 — disjoint foundations (4 agents, parallel):**
- A: **map-format v2** (`maps.py`, `board.py`, `hex_models.py`, tests) — §5.
- B: **gold** (`gold.py`, `player.py` gold field, `distribute_resources` hook,
  gold PRODUCTION modifier).
- C: **harbor settlements** (`harbor_settlements.py`, new building type,
  `production_for` modifier, `victory_points_for`, `has_piece_available`).
- (ep.py from Wave 0 is shared read-only state; Wave-1 agents add their own
  fields on it in separate methods.)

**Wave 2 — transport & pirate (2 agents, parallel):**
- D: **transport ships** (`transport.py`, `edge.ship` cargo/kind, movement
  points, `_touches_own_route` guard, movement-phase field) — needs C.
- E: **E&P pirate** (`ep_pirate.py`, `roll_dice` "7" branch, `steal_from_victim`
  reuse, tribute) — needs B.

**Wave 3 — exploration, cargo, turn phase, chase (4 agents, parallel):**
- F: **exploration** (`exploration.py`, discovery trigger, reveal/reward, build
  guards) — needs A + D.
- G: **cargo** (`cargo.py`, settlers + crews, found-by-settler-ship) — needs D + C.
- H: **movement phase** (`turn_clock.py` phase field, build-handler guards) — needs D.
- I: **chase pirate** — needs E + D.

**Wave 4 — missions (1 + 3 agents):**
- J: **missions container** (`missions.py`, tracks/markers/lead cards, scoring
  hook) — needs Wave-0 ep.py + `victory_points_for`.
- K/L/M: **pirate-lairs / fish / spices** (`missions_lairs.py` /
  `missions_fish.py` / `missions_spices.py`) — each needs J + G + A + F; disjoint
  files, so all three run in parallel.

**Wave 5 — surface (2 agents):**
- N: **renderer + handlers** (`board-renderer.js`, `board.js`, `handlers/ep_*.py`,
  browser tests) — needs the server methods landed.
- O: **scenario presets + maps** (the five map files, preset verification) —
  needs everything; the presets themselves ship in Wave 0's `rules.py` commit,
  the *maps* wait on A and the mission hexes.

`persistence.py` updates ride along with each subsystem that adds state (the
agent that adds `self.ep` fields updates the save list in the same commit).

---

## 7. Risk list (honest)

**Risk 1 — the two ship concepts collide on one data slot, and this is where
"individual rules, no modes" strains hardest.** Seafarers `ships` makes `edge.ship`
a *route connector* that extends the network (`ship_connects`,
`_touches_own_route`) and forms the Longest Trade Route. E&P `transport_ships`
makes the same `edge.ship` a *cargo transport* that forms **no routes** (866) and
has movement points. They are near-opposites sharing one field and one build
path. If both rules were on at once, `_touches_own_route` and the trade-route
calculation would treat E&P ships as network — wrong. The cleanest expression
that stays faithful to "no modes" is to declare `transport_ships` **incoherent
with** `ships` / `ship_movement` / `longest_trade_route` in `DEPENDENCIES`-style
refusal (they are two implementations of one physical piece; a table cannot
sensibly ask for both). But note the tension: forbidding a *combination of
individual rules* is exactly what the dependency system is for, yet it edges
close to admitting E&P's ship is a distinct *mode of the sea board* rather than a
free-standing rule. **This is a decision for the owner:** accept mutual-exclusion
refusal (recommended, and precedented by `DEPENDENCIES`), or invest in a unified
ship model that both readings configure. I do not think a single shared model is
worth it — the two ships genuinely do opposite things.

**Risk 2 — turn structure has no phase machine.** The engine assumes roll → free
build until `advance_turn`, with build/move actions each doing their own
precondition checks (`game.py`, `turn_clock.py`). E&P's mandatory
production→build→**movement** ordering with "no build after movement" (852, 861)
needs a per-turn phase threaded through every build/trade/move handler — a wide
collision surface touching `handlers/building.py`, `handlers/ships.py`,
`handlers/trading.py`. Isolated to agent H, but H's guard must land before the
mission/cargo agents rely on movement-phase semantics.

**Risk 3 — the map format expresses none of the five scenarios, and the fix is a
large serial prerequisite.** Hidden/face-down tiles, fixed pools, and three new
hex types with per-hex metadata (docks, villages, lairs) are all absent
(`maps.py:36–39,56,230`). Everything board-dependent — exploration and all three
missions — waits on map-format v2 (Wave 1, agent A). If A slips, Waves 3–4 stall.
This is the critical path; staff A first and heaviest.

**Other unknowns:** gold as a currency that must (a) count or not count toward
the 7 discard (842 says discard is unchanged — gold does **not** count, unverified
against `check_discard_required`), (b) be stealable when a hand is empty (943),
and (c) be tradeable player-to-player (859, reusing `TradeManager` — unverified
whether the trade layer can carry a non-resource token). The hero-of-the-battle
die roll and tie-breaks in Pirate Lairs (991–994) are the most intricate single
piece of rules logic and warrant their own regression tests.

**Nothing in E&P is impossible to express as individual rules** — the mechanics
decompose cleanly into the 17 switches above. The **one** place where the
individual-rules model is genuinely strained is Risk 1 (transport vs. Seafarers
ships on one slot); the recommended answer (mutual-exclusion refusal) keeps the
model intact, but the owner should confirm it rather than have an agent decide it
mid-build.
