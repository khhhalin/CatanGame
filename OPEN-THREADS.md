# Open threads

Work that is started, known-broken, or deliberately deferred. The point of this
file is to resume things rather than start new ones.

Deployed: `aeb9ca1`. Suites at that commit: 697 fast, 132 browser, ruff clean.

---

## 1. Built, tested, and unreachable by a player

**The pending-choice UI. Do this first.**

`server/game/pending_choice.py` landed with a full protocol and no client. Eight
progress cards and the barbarian city choice are implemented and tested, and
**nothing renders them**. Worse than absent: if a card that needs a choice is
played today, the server opens a choice, freezes the table (`MUST_CHOOSE` for the
chooser, `AWAITING_CHOICE` for everyone else), and no one can answer. The 30s
timeout resolves it by picking the first option.

Handoff, already written by the engine agent:

- Client → server: `make_choice {name, kind, option}`. Errors: `MUST_CHOOSE`,
  `AWAITING_CHOICE`, `NO_CHOICE_PENDING`, `WRONG_CHOICE`, `INVALID_CHOICE`.
- Server → client: `choice_required {kind, player, prompt, option_count, context,
  options}` — `options` only to the chooser. `choice_resolved {player, kind}`.
- Board payload: `pending_choices[]` (`options` omitted for non-choosers — render
  "waiting for {player} to {prompt}"), plus `merchant_hex`, `merchant_holder`.
- Kinds and what to show: `barbarian_city` (vertex keys — highlight those
  cities), `progress_deck` (science/trade/politics), `commercial_harbor`
  (commodity ids; `context.to`, `context.resource`), `master_merchant` /
  `wedding` (card ids; `context.left` counts down from 2), `spy` (card ids),
  `deserter` (knight vertex keys), `deserter_placement` (vertex keys;
  `context.rank`).

---

## 2. Architecture, before it gets more expensive

**The modifier funnel.** Rules are *read*, not *applied*: 55 `self.rules['...']`
sites scattered through the engine. A rule can only change something where
somebody thought to read one, so "roads cost 1 less" or "+1 on a 6" has nowhere
to attach, and two modifiers touching production have no defined order.

Three chokepoints already exist and just need to become hooks:

| Concern | Today | Needed |
|---|---|---|
| Costs | `Game.get_cost` — a dict lookup | already the single site; apply modifiers there |
| Production | inline `city_production if type == 'city' else 1` in `distribute_resources` | extract `production_for(vertex, hex)` |
| Dice | `Game.next_dice` | already a clean seam |

Roughly a day. Do it **before** the map creator, which will otherwise add read
sites 56–70. It is also what unlocks custom dice sets and global modifiers.

**Custom dice sets** are nearly free once that exists — `next_dice` already
supports free rolls, a dealt 36-combination deck, and Alchemist overriding both
for one roll. A custom set is a fourth branch. Faces with *abilities* can reuse
the C&K event die precedent, and anything needing a decision now has the
pending-choice phase.

---

## 3. Known-wrong, with the correct behaviour understood

- **`merchant_fleet`** is the last refused progress card. It needs a 2:1 bank
  trade on a resource **or commodity**, and the bank holds no commodity supply
  (`propose_trade` reads `player.resources` only). Implementing it for resources
  alone would silently do nothing for three of its eight legal choices.
- **The board does not fill its pane.** `computeLayout` pads by `hexRadius + 20`
  on every side, ~17% of the layout. Left alone because `offsetX`/`offsetY` are
  coordinates several suites assert against — a sizing-contract change, not a CSS
  tweak.
- **A latent hole for the map creator.** `place_settlement` tests
  `vertex.neighbors['hexes']`, built from land *slots*, not land *terrain*. The
  two are identical today, so no test can tell them apart. `map-creator.md` plans
  pools containing `sea`, at which point a vertex ringed by ocean-typed land slots
  would accept a settlement on open water. One-line fix, unreachable now.
- **`getLayout` memoises on board object identity**, so an editor mutating hexes
  in place would draw a stale layout.
- **`dev_cards_remaining`** is still sent in games where the dev deck is unused.
- **~20 `console.log` event traces in `net.js`** — deliberate-looking tracing, not
  litter. Removing them is a judgement call, not a fix.

---

## 4. Rules deliberately not implemented, with reasons

- **Circular shipping routes** (`expansions.md` 67–68). The rulebook contradicts
  itself: 72 defines "closed" as interconnecting *two* buildings, which conflicts
  with 68. `ship_is_open` implements 66 literally. Needs a ruling, not a guess.
- **Gold fields** (`expansions.md` 105–109).
- **Catan for Two** — a mechanic, not a setting. `min_players` already lets two
  people start.
- **Special building phase** (5–6 player) — needs an out-of-turn build affordance
  the frontend cannot drive.
- **"Variable setup order"** — no official variant found to cite; `turn_order`
  and `board_layout` cover the published choices.
- **`pending_invention` / `pending_monopoly` not migrated** into the
  pending-choice phase. They are the current player's own follow-up with no
  option list and have working events; rewriting that contract mid-frontend-
  rebuild would break the live client.

---

## 5. Untested — real risk, not paranoia

- **Cities & Knights knight, knight-move and city-wall placement have no browser
  coverage at all.** The stuck-placement-mode fix is untested for exactly this
  reason: reaching a knight build needs 1 sheep + 1 ore, many non-deterministic
  turns away. A seeded fixture that arranges the hand would fix this.
- **Four C&K popovers** (barbarian, improvements, knights, progress-cards) are
  never opened by a test — they need a live C&K game.
- **No seafaring game is played to a winner** anywhere; the Seafarers browser
  suite covers placement, not a full game.
- **Touch input** was reasoned about, never tested on a device.
- **No screen-reader run.** The confirm control announces through a
  visually-hidden live region, verified only by DOM assertions.
- **Firefox** has 5 smoke tests, not full coverage.
- **gunicorn**: everything was verified against 26.0.0, but `requirements.txt`
  and `pyproject.toml` pin `>=21.2,<24`. A Docker build installs a version
  nothing here has exercised. Reconcile the pin or test what is pinned.
- **`SESSION_COOKIE_SECURE = True`** in production: correct behind TLS, but over
  plain HTTP the cookie is never returned and sessions break silently.

### One unexplained flake

`test_browser_confirm_placement.py::TestTheRobberConfirmsToo::
test_a_seven_raises_a_ghost_and_a_confirmation_for_the_robber` failed once and
has passed every run since (11+ consecutive, including three back-to-back release
runs). Never explained. Not fixed — watched.

---

## 6. Waiting on a decision

- **`audit-report.md` is still in the public git history.** Removed from the tree
  and gitignored (`66e37af`), but it went out in the first push. Purging it needs
  a history rewrite and a force-push of a public repo.
- **Identity is payload-based by design** (`data.get('name')`) — anyone connected
  can act as anyone. Deliberate: covering for an absent player is a feature. It
  holds only while the audience is the trusted group.
- **`map-creator.md` predates the ships decision.** Its v1 assumed islands would
  be preview-only; ships now exist, so that compromise is unnecessary and the
  document should be revised before anyone builds from it.

---

## 7. Test-suite decisions worth not re-litigating

- `test_every_listed_map_can_be_built` was on a kill-list and **kept**: it is the
  only test that checks the *advertised* layout options against what actually
  builds. A fourth map that appears in the picker and fails to build is caught by
  nothing else.
- The two browser suites were **deliberately not merged**. Four things live only
  in `test_browser_playthrough.py` — lobby chat, the XSS test, the zoom camera
  test, the grouped rules picker — and the confirm/YOLO split is structural, since
  `confirm_placement` short-circuits on `player.yolo`.
- See `CLAUDE.md` for the testing contract these came out of.
