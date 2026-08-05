# House-rule mutual-exclusions — audit & design

An audit of the house-rule catalogue (`server/game/rules.py`) for **mutual
exclusions** — pairs or groups of rules that cannot sensibly be switched on
together — and a design for recording, enforcing and surfacing them so the lobby
picker can group excluding rules, explain why, and auto-uncheck a rival when its
partner is ticked.

This is design + audit only. No engine code is written here.

## What this is *not*

The engine already models **dependencies** (`DEPENDENCIES`, `rules.py:682`;
refused by `dependency_problems`, `rules.py:931`, called at
`handlers/lobby.py:319`): rule A *requires* rule B, and the start is refused with
`INCOHERENT_RULES` naming what is missing (`handlers/lobby.py:323`). Nothing is
switched on for the table.

**Mutual exclusion is the opposite relationship and does not exist in the engine
today.** A ⇄ B where A and B *contradict or subsume each other*, so a coherent
table picks at most one. Two kinds, each finding is labelled:

- **Hard conflict** — both-on is incoherent: two rules claiming the same slot,
  edge, phase, or two settings of one underlying quantity. Must be refused or
  auto-resolved.
- **Soft "two flavours, pick one"** — both coherent alone but expressing one
  design choice two ways, so a table wants exactly one. Auto-uncheck is really
  for these.

## Headline

- **CHOICE rules are already one-of-N exclusive** and render as a single control
  — they need nothing from this design. The interesting targets are separate
  BOOLs that fight.
- The current catalogue contains **exactly one** real exclusion group:
  `{longest_road_card, longest_trade_route}` (**hard**, same award slot).
- The E&P plan's `transport_ships` vs Seafarers ships is the **second, designed-for**
  case — a hard conflict on `edge.ship` the owner has already accepted should be
  mutually exclusive. Its rules are not in the catalogue yet; the model below is
  built so it slots in unchanged when they are.
- Several pairs *look* like conflicts but **compose** and are deliberately kept
  out of the map (see "Rejected"). A false exclusion stops a table playing a
  combination that is actually fine — worse than none.

---

## 1. The exclusion map

| Group | Rule ids (at most one on) | Kind | Why they conflict | Sensible default |
|---|---|---|---|---|
| Longest-line award | `longest_road_card`, `longest_trade_route` | **hard** | Both feed the single `longest_road_holder` slot and the single +2 (`game.py:1437`, `player.py:129`). They are two settings of one quantity — what counts toward the one 2-point card: roads only vs. roads+ships (`route_pieces`, `game.py:1298`). "instead of the Longest Road" (`expansions.md:77`); docstring "replaces the base-game one rather than joining it" (`game.py:1434`). | `longest_road_card` on, `longest_trade_route` off (base game) |
| Sea-ship model *(not yet in catalogue; E&P)* | `transport_ships` ⇄ `ships`, `ship_movement`, `longest_trade_route` | **hard** | Both make `edge.ship` mean opposite things on one data slot: Seafarers ship is a route connector that extends the network (`_touches_own_route`, `game.py:712`; `route_pieces`, `game.py:1298`); an E&P transport ship carries cargo, has movement points and **forms no routes** (`expansions.md:866`). Both-on would make `_touches_own_route` and the trade-route walk treat transport ships as network — wrong. See `explorers-and-pirates-plan.md:381` (Risk 1). | `ships` family on, `transport_ships` off (Seafarers is the older, catalogued reading) |

Two groups: one hard in the live catalogue, one hard reserved for E&P. **Zero
soft** groups in the current catalogue — see Rejected for why the apparent soft
pairs compose.

---

## 2. Verification of each claim

### Group 1 — `longest_road_card` ⇄ `longest_trade_route` (hard, verified)

The award is a single slot with a single winner and a single +2:

- `update_longest_road` (`game.py:1431`) runs if *either* rule is on
  (`game.py:1437`) and writes one field, `self.longest_road_holder`.
- `player.get_victory_points` adds `+2` iff `self.name == longest_road_holder`
  (`player.py:129`) — one award, not one per rule.
- `route_pieces` (`game.py:1293`) includes ships **iff `longest_trade_route`**
  (`game.py:1298`). So with both on, `longest_trade_route` silently wins the
  computation and `longest_road_card` becomes a no-op.

So the engine does **not crash or double-award** — it degrades to
"trade-route-wins". The conflict is therefore one of *coherence*, not a runtime
contradiction: ticking both is meaningless, and `longest_road_card` (the
roads-only reading the table explicitly asked for) is discarded without a word.
That is exactly the "two settings of the same underlying quantity" the hard
category names, so it is enforced, but the enforcement is about clarity, not
preventing a stack trace.

**Live evidence it is unhandled today:** the `seafarers` preset
(`rules.py:772`) sets `longest_trade_route=True` and does **not** untick
`longest_road_card`. After `coerce` fills defaults, `longest_road_card` stays
`True` — so the shipped Seafarers preset already produces the both-on state. It
plays correctly only because trade-route-wins hides it. The exclusion model
below would have the preset (or the coerce step) untick `longest_road_card`, and
the picker would show why.

### Group 2 — `transport_ships` ⇄ Seafarers ships (hard, from the plan)

Verified against `explorers-and-pirates-plan.md:381-398` and the touch points it
cites: `edge.ship` is `{player, built_turn}` with no cargo field
(`seafarers.py:152`), the network walk keys off it (`game.py:712`), and the
trade route reads it (`game.py:1298`). The plan's own recommendation is
mutual-exclusion refusal (`explorers-and-pirates-plan.md:390`), and it flags the
tension that this "edges close to admitting E&P's ship is a distinct mode"
(`:395`) — a decision it explicitly leaves to the owner. Included here as the
worked second case so the model has a real, non-degenerate group beyond today's
single one. **Unverified:** the exact E&P rule ids are proposals in the plan, not
committed catalogue entries; treat the ids as placeholders until Wave 0 lands
them.

### Modifier-collision check (`modifiers.py`)

`register` refuses two modifiers claiming the same `order` on one hook
(`modifiers.py:97-102`) — a hard-conflict-by-construction detector. **No two
current rules collide:** the PRODUCTION hook uses distinct orders 10/20/30/40
(`modifiers.py:210-214`), DICE uses 10 (`:225`), COST has none. The module
imports cleanly, so there is no live modifier-order exclusion to report. This
guard is relevant only to *future* rules (the E&P plan pre-assigns orders for
exactly this reason, `explorers-and-pirates-plan.md:278`).

---

## 3. Rejected — apparent conflicts that actually compose

Kept **out** of the map on purpose; each was checked in code.

| Pair | Verdict | Why it composes |
|---|---|---|
| `dice_deck` × `dice_set=no_two_or_twelve` | composes | `dice_deck` builds its deck from `dice_combinations()` (`game.py:1252`), which applies the DICE modifiers including the dice set (`game.py:1271`, `modifiers.py:221`). Both-on = a shuffled, even deck of the 34 non-2/12 combinations. Coherent and a plausible want. |
| `epidemic` × `dice_deck` | composes | Different hooks: `epidemic` is a PRODUCTION modifier (`modifiers.py:213`), `dice_deck` is the dice *source*. Orthogonal. |
| `largest_army_card` × `knights` / `progress_cards` | composes | Largest Army counts knight *dev cards* (`update_largest_army`, `game.py:1473`); C&K `knights` are separate physical pieces. With `card_system=progress` the dev deck is unbuyable (`rules.py:825`) so the card may simply never be awarded — unwinnable, not incoherent. The C&K preset unticks it as a *suggestion* (`rules.py:729`), which is the right mechanism; forcing exclusion would stop a house table running both. |
| `friendly_robber` × `pirate` × `robber_may_return_to_desert` × `robber_free_opening_rounds` | compose | All are independent constraints on robber/7 behaviour; the pirate is moved *instead of* the robber per 7 (both exist in Seafarers). No shared slot. |
| `starting_city_yield` (choice) × `setup_second_city` / `commodities` | dependency, not exclusion | `starting_city_yield` only matters when there is a starting city; that is a one-directional "meaningful only if" relationship, not a contradiction. Out of scope for the exclusion model. |
| `card_system=both` | already exclusive | The three readings are options of one CHOICE control (`rules.py:521`); mutual exclusion is inherent. Nothing to add. |

`min_players` > `max_players` is an int-range coherence issue, not a rule
exclusion; noted but out of scope for a bool/flavour exclusion model.

---

## 4. The model — `EXCLUSIONS` in `rules.py`

Record exclusions as **mutual groups** next to `DEPENDENCIES`, each group a set
where at most one member may be on, plus a player-readable reason. A group (not a
pair list) so N-way sets like the E&P ship group are one entry.

```python
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
    # Reserved for Explorers & Pirates (rules not yet in the catalogue):
    # {
    #     "id": "sea_ship_model",
    #     "rules": ("transport_ships", "ships", "ship_movement",
    #               "longest_trade_route"),
    #     "kind": "hard",
    #     "reason": "Seafarers ships form routes; E&P transport ships carry "
    #               "cargo and form none. They are one physical piece read two "
    #               "opposite ways on the same board — pick one sea system.",
    # },
]

EXCLUSIONS_BY_RULE = {
    rule_id: group
    for group in EXCLUSIONS
    for rule_id in group["rules"]
}
```

Shape notes:

- **List of groups, each with a stable `id`**, mirroring `PRESETS`. `id` lets the
  client key group DOM and lets a test pin membership.
- **`kind`** (`"hard"`/`"soft"`) so the picker can phrase it ("cannot both be on"
  vs "pick one") and so a future policy could refuse hard but only warn on soft.
- **`reason`** is one sentence a player reads — the thing the owner wants visible
  when a box unchecks itself.
- A CHOICE member would be a mistake (choices are already exclusive); a small
  guard test should assert every id in `EXCLUSIONS` is a BOOL in `RULES_BY_ID`,
  the same way the existing "every catalogue id is read by the engine" test
  guards the registry.

**Reaching the client.** No new channel. The rules payload already carries the
catalogue, presets and selection (`emit_rules`, `state.py:410-425`). Add one key:

```python
payload = {
    'catalogue': rules_module.catalogue(),
    'presets': rules_module.presets(),
    'exclusions': rules_module.exclusions(),   # new: list(EXCLUSIONS)
    'selected': live.lobby_rules,
    'locked': ...,
}
```

`exclusions()` returns `[dict(group) for group in EXCLUSIONS]`, matching
`presets()` (`rules.py:988`). It rides the same `rules_changed` broadcast, so
every client learns the groups with no new event and no front-end wiring beyond
reading the field.

---

## 5. Lobby UX (`server/static/js/lobby.js`)

The picker renders rows and collapsible groups from the catalogue
(`buildRuleRow` `:265`, `buildRuleGroup` `:328`, `renderRulesPanel` `:434`),
pushes server values onto controls (`applyRuleValue` `:363`), and sends the whole
selection on `change`, coalesced (`sendRules` `:470`, `queueRuleSend` `:508`, the
delegated `change` listener `:520`).

**Showing a group.** Exclusion groups cut across the existing section groups
(`longest_road_card` is a base-game variant; `longest_trade_route` is an
expansion rule), so do **not** re-section the picker by exclusion. Instead, after
the rows exist, decorate each excluding row: a small "exclusive" badge on the
row carrying the group's `reason` as its `title`/tooltip, and `aria-describedby`
pointing at a one-line note rendered under the row (the picker already renders
per-rule `.rule-source`/`.rule-summary`, `:305-311` — add a `.rule-exclusion`
sibling in the same shape). Both members show the same `reason`, so a player
reads why before ticking.

**Auto-uncheck live, with the reason visible.** On the delegated `change`
handler (`:520`), when the changed control is a checkbox that was just ticked
`true` and its id is in `EXCLUSIONS_BY_RULE`, untick every *other* member of its
group in the DOM, then let the existing `queueRuleSend()` fire the whole
selection as it already does. Crucially, surface *why*: flash/expand the
`.rule-exclusion` note on the row that just unchecked ("Unchecked because Longest
Trade Route replaces it") and log it to the existing lobby toast/announce channel
— the owner's requirement is that the uncheck is never silent. Because
`sendRules` transmits the entire selection (`:476`), no partial-state race: the
server receives a coherent set in one message.

**Why auto-uncheck is safe here when auto-*adding* a dependency was deliberately
rejected.** The two are not symmetric. Auto-*adding* a missing dependency imposes
a rule the table did not choose — a different game behind their back, which is
why `dependency_problems` refuses and names instead of propping up
(`rules.py:936-948`, AGENTS.md:224). Auto-*unchecking* an excluded rival
**removes** a setting; it takes nothing the table can't immediately re-tick, and
it removes precisely the box that was about to be silently ignored anyway
(`longest_road_card` is a no-op once `longest_trade_route` is on). Removal with a
visible reason is reversible and honest; addition is neither. So: **auto-uncheck
for exclusions, keep refuse-and-name for dependencies.**

---

## 6. Server enforcement

The client uncheck is UX only. A crafted `set_rules` payload, an old save, or a
preset can still deliver an incoherent set over the wire, so the server must
refuse it independently — exactly as it does for dependencies.

Add a sibling to `dependency_problems`:

```python
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
```

Wire it into the same start gate that runs `dependency_problems`
(`handlers/lobby.py:319-324`): append `exclusion_problems(session.lobby_rules)`
to `problems` before the `INCOHERENT_RULES` reject, so one refusal path reports
both dependency and exclusion faults. No new error code needed —
`INCOHERENT_RULES` already means "these rules do not work together".

**Do not auto-resolve server-side.** Keep the server a pure *refuser* for
symmetry with dependencies and to avoid two places silently mutating the set. The
client removes; the server only rejects what still arrives wrong. (If the owner
later wants old saves to load rather than refuse, the one acceptable auto-resolve
is in `coerce`/`migrate`, dropping the lower-priority member with a logged note —
but that is a separate decision, not part of enforcement.)

One consequence to fix in the same breath: the `seafarers` preset
(`rules.py:772`) must gain `"longest_road_card": False`, or it will now fail its
own start. This is the live both-on state from §2 surfacing — the exclusion
model makes it an error instead of a hidden no-op, which is the point.

---

## 7. Phased build order

Failing-test-first throughout (CLAUDE.md:39). `EXCLUSIONS` is one edit to one
file — the same serialization hazard that bit the repo twice
(`explorers-and-pirates-plan.md:247`, CLAUDE.md:133). **Give it a single owner;
feature agents only read it.**

**Wave 0 — the registry edit (1 agent, lands first, alone on `rules.py`).**
Add `EXCLUSIONS`, `EXCLUSIONS_BY_RULE`, `exclusions()`, `exclusion_problems()`,
the BOOL-membership guard test, and fix the `seafarers` preset
(`longest_road_card=False`). Failing tests first: (a) `exclusion_problems`
returns a sentence for `{longest_road_card, longest_trade_route}` both-on and
`[]` otherwise; (b) `preset_rules("seafarers")` produces no exclusion problem
(fails until the preset is fixed). Commit by explicit path
`git commit -- server/game/rules.py tests/game/test_rules_options.py`.

**Wave 1 — server enforcement (1 agent, `handlers/lobby.py` + its test).**
Failing test first in `tests/test_socket_handlers.py`: a `start_game` on a
crafted both-on payload is refused with `INCOHERENT_RULES` naming the exclusion.
Then append `exclusion_problems` at the gate (`handlers/lobby.py:319`). Disjoint
from Wave 0's file.

**Wave 2 — payload (1 agent, `state.py` + its test).** Add `'exclusions'` to the
`emit_rules` payload (`state.py:420`). Test: the `rules_changed` payload carries
the group. Disjoint file.

**Wave 3 — lobby UX (1 agent, `lobby.js` + browser test).** Badge/reason
decoration, live auto-uncheck in the `change` handler (`lobby.js:520`), visible
"unchecked because…" note. Browser test (`tests/test_browser_*.py`, the only
tests that catch player-visible regressions per CLAUDE.md:68): tick
`longest_trade_route`, assert `longest_road_card`'s box goes unchecked **and** a
reason is shown. Disjoint file; depends on Wave 2's payload landing.

Waves 1–3 touch disjoint files and can overlap once Wave 0's `rules.py` is
committed. The E&P `sea_ship_model` group is added — commented stub → live entry
— by whoever lands the E&P catalogue commit (`explorers-and-pirates-plan.md`
Wave 0), reusing this exact structure; no rework here.

---

## Summary

- **Exclusion groups: 2.** Split: **2 hard, 0 soft.** One live in the catalogue
  (`longest_road_card` ⇄ `longest_trade_route`), one reserved for E&P
  (`transport_ships` ⇄ Seafarers ships).
- **Riskiest call:** classifying the Longest-line group as **hard** at all. The
  engine already resolves both-on gracefully (trade-route-wins, `game.py:1298`)
  and the shipped Seafarers preset relies on that resolution, so an equally
  defensible reading is "they compose, trade route subsumes." I call it hard
  because it is one award slot set two ways and the roads-only choice is silently
  discarded — but if the owner disagrees, the *only* change is dropping this one
  group, and the whole `EXCLUSIONS`/`exclusion_problems`/UX machinery still earns
  its place for the E&P ship group. No other current pair is a real exclusion;
  the rest compose or are already CHOICE-exclusive.
</content>
</invoke>
