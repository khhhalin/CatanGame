"""The ordered adjustments the engine folds over a number it has just worked out.

Rules used to be *read*: fifty-odd `self.rules['...']` lookups scattered
wherever somebody happened to need one. A rule could therefore only change
something at a point where a lookup already existed — "roads cost one less" or
"a 6 pays everybody" had nowhere to attach — and two rules touching the same
number had no defined order at all.

A modifier turns that round. It registers against one of three hooks, and the
engine folds every active one over its own answer at the single place that
number is produced:

    cost        `Game.get_cost`        a build cost, resource -> amount
    production  `Game.production_for`  what one building takes from one hex
    dice        `Game.dice_combinations`  the faces the dice may come up

There are three hooks because the engine has three such chokepoints. A fourth
hook is a fourth chokepoint in the engine, not an entry in this file.

`order` is an explicit integer and no two modifiers on one hook may share one.
Registration order, import order and dict order are all invisible accidents of
how the module happened to be loaded; two modifiers touching the same number
have to compose the same way in every process and on every run, and
`tests/game/test_modifiers.py` pins the sequence.
"""

from contextlib import contextmanager

from game import cities_knights as ck_module

COST = 'cost'
PRODUCTION = 'production'
DICE = 'dice'

HOOKS = (COST, PRODUCTION, DICE)

# Every combination two six-sided dice can show, in the order the dice deck has
# always built it. The dice hook's value is a sequence of these, so a dice set
# is data — a list of combinations — rather than another branch of `next_dice`.
STANDARD_DICE = tuple(
    (first, second) for first in range(1, 7) for second in range(1, 7)
)

# The dice sets a table can choose between, by the option id the `dice_set`
# rule advertises. A set is exactly what the dice may show; anything that has
# to *happen* on a face is a separate hook, not an entry here.
DICE_SETS = {
    'standard': STANDARD_DICE,
    # "When you roll a '2' or a '12' as your production roll you re-roll the
    # dice, because no hex carries those numbers in this scenario." Re-rolling
    # until the total is legal is the same thing as never dealing the two
    # combinations that produce it, and it keeps one roll to one draw.
    'no_two_or_twelve': tuple(
        pair for pair in STANDARD_DICE if sum(pair) not in (2, 12)
    ),
}


class Modifier:
    """One adjustment to one number.

    `rule_id` is the rule this speaks for. Usually one the lobby lists, but a
    base-game rule nobody can switch off — the robber below — is still a
    modifier, because it is still an adjustment to a number somebody else's
    modifier has to compose with.

    `applies` is asked whether the table's rules switch this on; `change`
    receives the value so far, the rules and the context the hook passes, and
    returns the new value. It must not mutate what it was handed — the caller
    keeps its own base value, and two modifiers sharing a dict would make the
    order they run in impossible to reason about.
    """

    def __init__(self, rule_id, hook, order, applies, change):
        self.rule_id = rule_id
        self.hook = hook
        self.order = order
        self.applies = applies
        self.change = change

    def __repr__(self):
        return f"<Modifier {self.hook}:{self.order} {self.rule_id}>"


_REGISTRY = {hook: [] for hook in HOOKS}


def register(modifier: Modifier) -> Modifier:
    """Add a modifier to its hook, in order.

    Two modifiers on one hook may not claim the same order: that would leave
    the tie broken by whichever module imported first, which is the one thing
    this file exists to prevent.
    """
    if modifier.hook not in _REGISTRY:
        raise ValueError(f"{modifier.rule_id} registers against unknown hook {modifier.hook}")
    for other in _REGISTRY[modifier.hook]:
        if other.order == modifier.order:
            raise ValueError(
                f"{modifier.rule_id} and {other.rule_id} both claim order "
                f"{modifier.order} on the {modifier.hook} hook"
            )
    _REGISTRY[modifier.hook].append(modifier)
    _REGISTRY[modifier.hook].sort(key=lambda entry: entry.order)
    return modifier


def registered(hook: str) -> tuple:
    """Every modifier on this hook, in the order the engine applies them."""
    return tuple(_REGISTRY[hook])


def active(hook: str, rules: dict) -> tuple:
    """The modifiers this rule set switches on, in order."""
    return tuple(entry for entry in _REGISTRY[hook] if entry.applies(rules))


def apply(hook: str, rules: dict, value, **context):
    """Fold every active modifier over `value`, in order."""
    for modifier in _REGISTRY[hook]:
        if modifier.applies(rules):
            value = modifier.change(value, rules, context)
    return value


@contextmanager
def installed(modifier: Modifier):
    """Register a modifier for the duration of a block, then take it away.

    For tests that need to prove the funnel carries a modifier the catalogue
    does not list — the composition order, above all, which has to hold for
    modifiers nobody has written yet.
    """
    register(modifier)
    try:
        yield modifier
    finally:
        _REGISTRY[modifier.hook].remove(modifier)


# --- Production ---------------------------------------------------------
# The value is {'resources': how many cards of the hex's own type,
# 'commodity': the commodity's name or None}. The base is one card, which is
# what a settlement takes; everything else is a modifier below.


def _always(_rules):
    return True


def _rule_is_on(rule_id):
    return lambda rules: bool(rules.get(rule_id))


def _city_production(value, rules, context):
    """A city takes what the table set it to; a settlement always takes one."""
    if context['building_type'] != 'city':
        return value
    return {**value, 'resources': rules['city_production']}


def _commodity_instead(value, rules, context):
    """A city on pasture, mountain or forest takes one resource and one commodity.

    Fields and hills have no commodity, so a city there still takes whatever
    `city_production` says, exactly as in the base game.
    """
    if context['building_type'] != 'city':
        return value
    commodity = ck_module.COMMODITY_FROM_TERRAIN.get(context['terrain'])
    if commodity is None:
        return value
    return {'resources': 1, 'commodity': commodity}


def _epidemic(value, _rules, context):
    """On a 6 or an 8 a city collects one card, however much it normally would."""
    if context['building_type'] != 'city' or context['dice_total'] not in (6, 8):
        return value
    return {**value, 'resources': min(value['resources'], 1)}


def _robber_takes_it_all(value, _rules, context):
    """The hex the robber sits on pays nobody, whatever the rest worked out.

    Last on the hook for that reason: it is not an adjustment to production but
    the absence of it.
    """
    if not context['robber_here']:
        return value
    return {'resources': 0, 'commodity': None}


register(Modifier('city_production', PRODUCTION, 10, _always, _city_production))
register(Modifier('commodities', PRODUCTION, 20,
                  _rule_is_on('commodities'), _commodity_instead))
register(Modifier('epidemic', PRODUCTION, 30, _rule_is_on('epidemic'), _epidemic))
register(Modifier('robber', PRODUCTION, 40, _always, _robber_takes_it_all))


# --- Dice ---------------------------------------------------------------
# The value is the sequence of (first, second) combinations the dice may show.


def _chosen_dice_set(value, rules, _context):
    return DICE_SETS.get(rules['dice_set'], value)


register(Modifier('dice_set', DICE, 10,
                  lambda rules: rules.get('dice_set', 'standard') != 'standard',
                  _chosen_dice_set))


# --- Cost ---------------------------------------------------------------
# The value is the cost dict, resource -> amount. Nothing in the catalogue
# changes a build cost yet; the hook is here because `get_cost` is the one
# place a cost is decided, and a rule that makes something cheaper has to have
# somewhere to attach before it can be written.
