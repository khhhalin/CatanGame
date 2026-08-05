"""Slash commands typed into chat.

The table types `/add_resource wheat 2` into the chat box and the server does
it. Everything here is deliberately server-side: the client sends the raw line
it was given and nothing else, because a command payload is a player's typing
and a client that decided for itself which command it had run would be deciding
what the game does.

Two halves:

* `catalogue()` is the list of commands, in the same spirit as
  `rules.catalogue()` — the client renders its command bar from it and knows no
  command id of its own. A list in the browser would drift the first time an
  argument changed here.
* `run()` parses one line and applies it. It refuses by name: a command the
  table's rules do not allow says which rule is missing, and a command that has
  nothing to report says so. A command that silently does nothing is worse than
  one that is absent — that is the whole reason every refusal below names
  something.

Transport-free by design (see coding-rules.md Part V): nothing here imports
Flask or Socket.IO. The handler in `handlers/commands.py` decides who is
speaking, calls `run`, and turns the result into a log entry and a broadcast.
"""

from game import progress_cards
from game import rules as rules_module
from game.results import refused
from game.validation import CARD_TYPES, COMMODITY_TYPES

# The character that turns a line of chat into a command. A message that merely
# contains one — "back in 5 mins w/ coffee" — is chat, and only a line that
# *starts* with this is looked at here at all.
PREFIX = '/'

# The house rule that has to be on before a command may change the game.
COMMAND_RULE = 'chat_commands'

# What a card argument may be: the five resources plus the three commodities,
# since commodities are cards a player holds like any other.
CARD_NAMES = CARD_TYPES

# Bounds on a count argument. Twenty is far more than any correction to a
# misdeal needs and still leaves the number readable in the log; the bank's own
# supply refuses anything it cannot actually pay.
MIN_COUNT = 1
MAX_COUNT = 20


def _ok(lines, log=None, changed=False, **extra):
    """A command that worked.

    `lines` is what the player who typed it is shown, `log` the one sentence the
    whole table reads. A command with a `log` has changed the game by
    definition, which is why the two travel together.
    """
    return {
        'success': True,
        'error': '',
        'lines': list(lines),
        'log': log,
        'changed': changed,
        **extra,
    }


def _rule_off(rule_id: str) -> dict:
    """Refuse for the one rule that would have to be on, by name."""
    name = rules_module.RULES_BY_ID[rule_id]['name']
    return refused('RULE_IS_OFF', f'"{name}" is not one of this table\'s rules')


def _describe_value(rule: dict, value) -> str:
    """One rule's setting, as a player would say it."""
    if rule['type'] == rules_module.BOOL:
        return 'on' if value else 'off'
    if rule['type'] == rules_module.CHOICE:
        for option in rule.get('options') or ():
            if option['id'] == value:
                return option['name']
        return str(value)
    return str(value)


def changed_rules(rules: dict) -> list:
    """The settings this table has moved off the defaults, as phrases."""
    said = []
    for rule in rules_module.RULES:
        value = rules.get(rule['id'])
        if value is None or value == rule['default']:
            continue
        said.append(f"{rule['name']} {_describe_value(rule, value)}")
    return said


# --- The commands -------------------------------------------------------
#
# Each entry is one command. `args` is the hint the command bar shows next to
# the name, `requires_rules` every rule that has to be on before it may run
# (None for the four that only report), and `needs_game` whether there has to be
# a game to talk about at all.


def _command(command_id, args, summary, run, requires_rules=(), needs_game=False,
             changes_state=False):
    return {
        'id': command_id,
        'name': f'{PREFIX}{command_id}',
        'args': args,
        'summary': summary,
        # Every rule that has to be on. More than one for `/barbarians`, which
        # needs both the table's permission to run commands at all and the rule
        # that puts a barbarian ship on the board to move.
        'requires_rules': tuple(requires_rules),
        'needs_game': needs_game,
        # Whether running this can change the game. It decides two things: that
        # the caller must hold a seat *at the table* rather than merely in the
        # lobby, and that what they did is written into the shared log.
        'changes_state': changes_state,
        'run': run,
    }


def _cmd_help(game, rules, actor, args) -> dict:
    """List what this table can type, from the catalogue itself."""
    lines = []
    for command in catalogue(rules, game is not None):
        hint = f" {command['args']}" if command['args'] else ''
        note = '' if command['available'] else f" — unavailable: {command['unavailable']}"
        lines.append(f"{command['name']}{hint} — {command['summary']}{note}")
    return _ok(lines)


def _cmd_whoami(game, rules, actor, args) -> dict:
    """Which seat this connection holds — the question a second tab raises."""
    lines = [f'This connection holds {actor}\'s seat.']
    if game is None:
        lines.append('No game is running; you are in the lobby.')
        return _ok(lines)

    if game.is_player(actor):
        player = game.get_player(actor)
        lines.append(
            f'You are playing, with {player.total_resources()} resource cards, '
            f'{player.total_commodities()} commodities and '
            f'{player.total_dev_cards()} development cards.'
        )
    else:
        lines.append('You are watching this game, not playing it.')
    lines.append(f"It is {game.current_player_name()}'s turn.")
    return _ok(lines)


def _cmd_rules(game, rules, actor, args) -> dict:
    """The settings that differ from the defaults, in one line."""
    said = changed_rules(rules)
    if not said:
        return _ok(['Every rule is at its default: this is the base game.'])
    return _ok(['Changed from the defaults: ' + '; '.join(said) + '.'])


def _cmd_deck(game, rules, actor, args) -> dict:
    """What is left to draw.

    Counts only, never contents: what is still in a deck is public — anyone can
    count the cards already dealt — but its order is the one thing that would
    turn a probabilistic draw into a certain one.
    """
    lines = []

    if not rules_module.dev_deck_in_play(rules):
        lines.append(
            'Development cards: none — progress cards replace them, so the '
            'development deck cannot be bought from.'
        )
    else:
        lines.append(f'Development cards: {game.bank.total_dev_cards_remaining()} left.')

    if not rules_module.progress_deck_in_play(rules):
        lines.append('Progress cards: this table does not play them.')
    else:
        # A deck is shuffled on its first draw, so one nobody has drawn from is
        # still whole — reporting 0 there would read as "exhausted".
        full = progress_cards.deck_counts()
        remaining = []
        for deck in progress_cards.DECKS:
            dealt = game.ck.progress_decks.get(deck)
            remaining.append(f'{deck} {len(dealt) if dealt is not None else full[deck]}')
        lines.append('Progress cards: ' + ', '.join(remaining) + ' left.')

    if not rules['dice_deck']:
        lines.append('Dice deck: this table rolls dice, so there is no deck.')
    else:
        # An empty deck is not an exhausted one: the next roll deals a fresh
        # set, which is what makes the distribution even over the whole game.
        whole = len(game.dice_combinations())
        left = len(game.dice_deck) or whole
        lines.append(f'Dice deck: {left} of {whole} combinations left.')

    return _ok(lines)


def _require_card(token: str, rules: dict):
    """(card, refusal). A commodity needs the rule that makes commodities exist."""
    card = token.lower()
    if card not in CARD_NAMES:
        return None, refused(
            'UNKNOWN_CARD',
            f'"{token}" is not a card. Try one of: {", ".join(CARD_NAMES)}',
        )
    if card in COMMODITY_TYPES and not rules['commodities']:
        return None, _rule_off('commodities')
    return card, None


def _require_count(token: str):
    """(count, refusal) for a whole number of cards."""
    try:
        count = int(token)
    except ValueError:
        return None, refused('INVALID_COUNT', f'"{token}" is not a whole number of cards')
    if count < MIN_COUNT or count > MAX_COUNT:
        return None, refused(
            'INVALID_COUNT', f'The count must be between {MIN_COUNT} and {MAX_COUNT}'
        )
    return count, None


def _require_player(game, name: str):
    """(player name, refusal). Matched without case so typing is forgiving."""
    for player in game.players:
        if player.name.lower() == name.lower():
            return player.name, None
    seated = ', '.join(player.name for player in game.players)
    return None, refused('UNKNOWN_PLAYER', f'"{name}" is not at this table. Playing: {seated}')


def _cmd_add_resource(game, rules, actor, args) -> dict:
    """Put cards into a hand, from the bank where the bank holds them."""
    if len(args) < 2:
        return refused('INVALID_ARGUMENTS', 'Usage: /add_resource <card> <count> [player]')

    card, problem = _require_card(args[0], rules)
    if problem:
        return problem
    count, problem = _require_count(args[1])
    if problem:
        return problem

    target = actor
    if len(args) > 2:
        target, problem = _require_player(game, ' '.join(args[2:]))
        if problem:
            return problem
    elif not game.is_player(actor):
        return refused('NOT_A_PLAYER', 'You are watching this game — name the player to add to')

    player = game.get_player(target)
    if card in COMMODITY_TYPES:
        # Commodities have no bank in this engine: a city's production mints
        # them, so there is nothing to draw them from and nothing to run out.
        player.commodities[card] = player.commodities.get(card, 0) + count
    else:
        if game.bank.resources.get(card, 0) < count:
            return refused(
                'BANK_EMPTY',
                f'The bank has only {game.bank.resources.get(card, 0)} {card} left',
            )
        game.bank.take(card, count)
        player.resources[card] = player.resources.get(card, 0) + count

    whose = 'their own hand' if target == actor else f"{target}'s hand"
    return _ok(
        [f'{target} now holds {player.all_cards()[card]} {card}.'],
        log=f'{actor} added {count} {card} to {whose}',
        changed=True,
    )


def _cmd_give(game, rules, actor, args) -> dict:
    """Move cards out of the caller's own hand — a misdeal, corrected."""
    if len(args) < 3:
        return refused('INVALID_ARGUMENTS', 'Usage: /give <player> <card> <count>')

    # Card and count come off the end so a name with a space in it survives.
    card, problem = _require_card(args[-2], rules)
    if problem:
        return problem
    count, problem = _require_count(args[-1])
    if problem:
        return problem
    target, problem = _require_player(game, ' '.join(args[:-2]))
    if problem:
        return problem

    if not game.is_player(actor):
        return refused('NOT_A_PLAYER', 'You are watching this game and hold no cards')
    if target == actor:
        return refused('INVALID_TARGET', 'You already hold those cards')

    giver = game.get_player(actor)
    held = giver.hand_for(card).get(card, 0)
    if held < count:
        return refused('NOT_ENOUGH_CARDS', f'You hold {held} {card}, not {count}')

    giver.hand_for(card)[card] = held - count
    taker = game.get_player(target)
    taker.hand_for(card)[card] = taker.hand_for(card).get(card, 0) + count

    return _ok(
        [f'You gave {target} {count} {card}.'],
        log=f'{actor} gave {target} {count} {card}',
        changed=True,
    )


def _cmd_set_dice(game, rules, actor, args) -> dict:
    """Decide the next production roll.

    Through `pending_dice`, the field the Alchemist already writes: a seeded
    replay stays a replay because the faces are consumed by `next_dice` on the
    one path every roll takes.
    """
    if len(args) != 2:
        return refused('INVALID_ARGUMENTS', 'Usage: /set_dice <a> <b>, each 1 to 6')

    faces = []
    for token in args:
        try:
            face = int(token)
        except ValueError:
            return refused('INVALID_ARGUMENTS', f'"{token}" is not a die face')
        if face < 1 or face > 6:
            return refused('INVALID_ARGUMENTS', 'A die shows 1 to 6')
        faces.append(face)

    game.pending_dice = (faces[0], faces[1])
    total = faces[0] + faces[1]
    return _ok(
        [f'The next roll will be {faces[0]} + {faces[1]} = {total}.'],
        log=f'{actor} set the next roll to {faces[0]} + {faces[1]} = {total}',
        changed=True,
    )


def _skip_blocker(game) -> str | None:
    """Why this turn cannot simply be ended, or None.

    The same conditions `advance_turn` refuses on. Forcing past them is what
    carried a robber flag into the next player's turn once already; each of
    these has its own clock, and the watchdog settles them.
    """
    if game.game_phase == 'setup':
        return 'the setup round advances as buildings go down, so there is no turn to skip'
    if game.must_move_robber:
        return f'{game.current_player_name()} still has to move the robber'
    if game.must_choose_victim:
        return f'{game.current_player_name()} still has to pick who to steal from'
    if game.players_needing_discard:
        return f"{', '.join(sorted(game.players_needing_discard))} still owe a discard"
    if game.pending_choices:
        owed = ', '.join(sorted({choice['player'] for choice in game.pending_choices}))
        return f'{owed} still owe a decision'
    return None


def _cmd_skip(game, rules, actor, args) -> dict:
    """End the current turn without waiting for the clock."""
    blocker = _skip_blocker(game)
    if blocker is not None:
        return refused(
            'CANNOT_SKIP',
            f'The turn cannot be skipped: {blocker}. That has a clock of its own.',
        )

    skipped = game.current_player_name()
    now = game.force_advance_turn()
    return _ok(
        [f"{skipped}'s turn was ended; it is {now}'s turn."],
        log=f"{actor} skipped {skipped}'s turn",
        changed=True,
        current_player=now,
    )


def _cmd_barbarians(game, rules, actor, args) -> dict:
    """Move the barbarian ship, or land it now."""
    if not rules['barbarians'] or game.ck is None:
        return _rule_off('barbarians')

    if len(args) != 1:
        return refused('INVALID_ARGUMENTS', 'Usage: /barbarians <space> or /barbarians attack')

    track = game.ck.barbarian_track_length
    if args[0].lower() == 'attack':
        result = game.resolve_barbarian_attack()
        return _ok(
            ['The barbarians attack now.'],
            log=f'{actor} sent the barbarians in early',
            changed=True,
            attack=result,
        )

    try:
        space = int(args[0])
    except ValueError:
        return refused(
            'INVALID_ARGUMENTS', f'"{args[0]}" is neither a space on the track nor "attack"'
        )

    # Clamped rather than refused: the track's length is a house rule the caller
    # may not have looked up, and landing on the last space is a real position.
    game.ck.barbarian_position = max(0, min(track, space))
    position = game.ck.barbarian_position
    return _ok(
        [f'The barbarian ship stands on {position} of {track}.'],
        log=f'{actor} moved the barbarian ship to {position} of {track}',
        changed=True,
    )


COMMANDS = [
    _command('help', '', 'The commands this table has.', _cmd_help),
    _command('whoami', '', 'Which seat this connection holds.', _cmd_whoami),
    _command('rules', '', 'The rules that differ from the defaults.', _cmd_rules),
    _command('deck', '', 'What is left to draw.', _cmd_deck, needs_game=True),
    _command('add_resource', '<card> <count> [player]',
             'Put cards into a hand — yours unless you name somebody.',
             _cmd_add_resource, requires_rules=(COMMAND_RULE,), needs_game=True,
             changes_state=True),
    _command('give', '<player> <card> <count>',
             'Move cards out of your own hand, to correct a misdeal.',
             _cmd_give, requires_rules=(COMMAND_RULE,), needs_game=True,
             changes_state=True),
    _command('set_dice', '<a> <b>', 'Fix the next production roll.',
             _cmd_set_dice, requires_rules=(COMMAND_RULE,), needs_game=True,
             changes_state=True),
    _command('skip', '', 'End the current turn without waiting for the clock.',
             _cmd_skip, requires_rules=(COMMAND_RULE,), needs_game=True,
             changes_state=True),
    _command('barbarians', '<space>|attack',
             'Move the barbarian ship, or land it now.',
             _cmd_barbarians, requires_rules=(COMMAND_RULE, 'barbarians'), needs_game=True,
             changes_state=True),
]

COMMANDS_BY_ID = {command['id']: command for command in COMMANDS}


def _unavailable(command: dict, rules: dict, has_game: bool) -> str | None:
    """Why this command cannot run right now, or None.

    The first missing rule, by name. Naming one at a time is deliberate: a
    table reads "Barbarian attacks is not one of this table's rules" and knows
    which switch to look for.
    """
    for rule_id in command['requires_rules']:
        if not rules.get(rule_id):
            name = rules_module.RULES_BY_ID[rule_id]['name']
            return f'"{name}" is not one of this table\'s rules'
    if command['needs_game'] and not has_game:
        return 'no game is running'
    return None


def catalogue(rules: dict, has_game: bool = False) -> list:
    """The commands, for the client to render its command bar from.

    Every command is listed whatever the table's rules are, with the reason it
    cannot run alongside it: a bar that silently omits `/add_resource` teaches a
    player that the command does not exist, when what is true is that this table
    has not switched it on.

    `run` is dropped — it is a function, and the caller is putting this on a
    wire.
    """
    listed = []
    for command in COMMANDS:
        reason = _unavailable(command, rules, has_game)
        listed.append({
            'id': command['id'],
            'name': command['name'],
            'args': command['args'],
            'summary': command['summary'],
            'requires_rules': list(command['requires_rules']),
            'needs_game': command['needs_game'],
            'changes_state': command['changes_state'],
            'available': reason is None,
            'unavailable': reason,
        })
    return listed


def looks_like_command(text: object) -> bool:
    """Whether this line was meant as a command at all.

    Only a line that *begins* with the prefix. A message that merely contains a
    slash — a date, a URL, "w/ coffee" — is chat and must stay chat.
    """
    return isinstance(text, str) and text.strip().startswith(PREFIX)


def parse(text: str) -> tuple:
    """(command id, arguments) from one typed line.

    The id is lowercased so `/HELP` works; arguments keep their case because
    player names do.
    """
    tokens = text.strip()[len(PREFIX):].split()
    if not tokens:
        return '', []
    return tokens[0].lower(), tokens[1:]


def run(text: str, actor: str, game, rules: dict) -> dict:
    """Parse and apply one command line for `actor`.

    `rules` is the running game's rule set when there is a game and the lobby's
    selection when there is not, so a table that has switched commands on can
    read `/rules` and `/help` before anybody starts.

    Returns either a refusal in the shape every engine action refuses in, or
    `_ok`: `lines` for the caller, `log` for the table, `changed` for whether
    the board has to go back out.
    """
    if not looks_like_command(text):
        return refused('NOT_A_COMMAND', 'A command starts with /')

    command_id, args = parse(text)
    command = COMMANDS_BY_ID.get(command_id)
    if command is None:
        known = ', '.join(entry['name'] for entry in COMMANDS)
        return refused(
            'UNKNOWN_COMMAND',
            f'There is no {PREFIX}{command_id} command. This table has: {known}',
        )

    reason = _unavailable(command, rules, game is not None)
    if reason is not None:
        missing_rule = any(not rules.get(rule_id) for rule_id in command['requires_rules'])
        code = 'RULE_IS_OFF' if missing_rule else 'NO_GAME'
        return refused(code, f'{command["name"]} cannot run: {reason}')

    return command['run'](game, rules, actor, args)
