"""The rules catalogue against the code that is supposed to read it.

The catalogue in `server/game/rules.py` is the source of truth for both the
lobby picker and the engine: adding an entry adds a switch a table can tick.
Nothing checked that the engine actually *does* anything with a switch, so dead
rules shipped — `transshipping`, `no_dev_cards` and `no_city_upgrades` were all
in the picker with no code behind them, found only by reading the tree by hand.
A picker showing a setting nothing honours is worse than no setting (CLAUDE.md,
"Never add a rule the engine ignores").

`test_every_catalogue_rule_is_read_by_server_code` closes that gap: it walks the
generated catalogue — never a hand-copied id list — and fails naming any rule id
that no server source consults. It caught `starting_gold`, a rule the Explorers &
Pirates preset set to 2 that the engine never handed out;
`test_starting_gold_seeds_each_player_purse` is that fix's regression.
"""

import ast
import pathlib
import random
import re

from game import rules
from game.game import Game

SERVER = pathlib.Path(__file__).resolve().parent.parent / "server"

# Rule ids that are genuinely read, but by an access the source scan cannot see
# — a value computed into the id string at runtime rather than written as a
# literal. Keep this minimal: a real dead rule belongs wired or removed, not
# parked here. One line of justification per entry, naming where it is read.
DYNAMICALLY_READ = {
    # (empty) — every catalogue id is currently read as a literal somewhere.
}


def _function_body_source(text: str) -> str:
    """The source of every function in a module, dropped of its data literals.

    `rules.py` declares each id as data (the `RULES` catalogue, the `PRESETS`,
    the dependency and exclusion tables) *and* consumes a few of them in its own
    helper functions — `dev_card_deck` reads `chosen['dev_knights']`, and so on.
    Scanning the whole module would let every id satisfy itself off its own
    declaration, so only the code that reads rules is kept: a rule set to a
    value in a preset dict but consulted by no function is exactly the dead rule
    this test exists to catch.
    """
    tree = ast.parse(text)
    lines = text.splitlines()
    bodies = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bodies.append("\n".join(lines[node.lineno - 1:node.end_lineno]))
    return "\n".join(bodies)


def _server_sources() -> dict:
    """Every server `.py`/`.js` text the engine and client are built from.

    `rules.py` is reduced to its function bodies so its catalogue does not vouch
    for itself; vendored libraries are skipped — they know nothing of our rules.
    """
    sources = {}
    for path in SERVER.rglob("*"):
        if path.suffix not in (".py", ".js") or not path.is_file():
            continue
        if "vendor" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.name == "rules.py":
            text = _function_body_source(text)
        sources[path] = text
    return sources


def test_every_catalogue_rule_is_read_by_server_code():
    catalogue_ids = [rule["id"] for rule in rules.RULES]
    assert len(catalogue_ids) == len(set(catalogue_ids)), "duplicate rule id"

    sources = _server_sources().values()
    dead = []
    for rule_id in catalogue_ids:
        if rule_id in DYNAMICALLY_READ:
            continue
        reference = re.compile(r"\b" + re.escape(rule_id) + r"\b")
        if not any(reference.search(text) for text in sources):
            dead.append(rule_id)

    assert not dead, (
        "catalogue rules no server code reads (the picker offers them but the "
        f"engine ignores them): {dead}. Wire the rule where its action happens, "
        "or remove it from the catalogue and any preset that sets it."
    )


def test_every_catalogue_rule_has_a_canonical_category():
    """Every rule self-classifies into one of the eight functional categories.

    The lobby trees the ~140-rule picker into a collapsible section per category,
    reading the category off each catalogue entry. A rule with no category, or one
    the client has no section for, would silently vanish from that tree — the same
    "picker offers a setting nothing honours" failure the read-guard above catches,
    here for the section a player opens to find the rule. Walk the generated
    catalogue (never a hand-copied id list) and fail naming any rule whose category
    is not one of the eight canonical ids.
    """
    canonical = {category["id"] for category in rules.CATEGORIES}
    stray = [
        (entry["id"], entry.get("category"))
        for entry in rules.catalogue()
        if entry.get("category") not in canonical
    ]
    assert not stray, (
        f"catalogue rules with no/invalid category: {stray}. Give each a "
        f"category from {sorted(canonical)} in rules.py."
    )


def test_category_ids_are_unique():
    """A duplicated category id would render two sections that fight over the same
    rules, or a rule that lands in whichever the client meets first."""
    ids = [category["id"] for category in rules.CATEGORIES]
    assert len(ids) == len(set(ids)), f"duplicate category id in CATEGORIES: {ids}"


def test_starting_gold_seeds_each_player_purse():
    """Regression: `starting_gold` was dead — the E&P preset set it to 2 and no
    code handed it out, so every game began with empty purses whatever the rule
    said. Each player must start with exactly the rule's gold."""
    game = Game(
        ["Alice", "Bob"],
        [],
        rng=random.Random(1),
        rules={"gold": True, "starting_gold": 2},
    )
    assert [player.gold for player in game.players] == [2, 2]
