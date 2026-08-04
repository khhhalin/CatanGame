"""Slash commands typed into the chat box.

The client sends the line the player typed and nothing else: which command that
is, whether this table allows it and what it does to the game are all decided
here. `game/commands.py` holds the parsing and the effects — this module is only
the boundary: who is speaking, what the table is told, and when the board goes
back out.
"""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game import commands as commands_module
from game.event_log import MAX_CHAT_LENGTH
from state import (
    announce_choices,
    bump_and_broadcast,
    emit_commands,
    log_event,
    rate_limited,
    reject,
    require_actor,
    viewer_for,
)

from handlers.turns import _announce_event_die, _announce_turn

logger = logging.getLogger(__name__)


@socketio.on('request_commands')
def handle_request_commands(data=None):
    """Send the catalogue to one socket, for a client that arrived late."""
    if rate_limited():
        return
    emit_commands(to_sender_only=True)


@socketio.on('run_command')
def handle_run_command(data):
    """Run one slash command for the seat this socket holds."""
    session = state.session()
    # Charged to chat's bucket, not a second one of its own: the command bar is
    # the chat box, and two budgets would let one client type at the table twice
    # as fast as chat allows.
    if rate_limited(budget_event='chat_message'):
        return

    text = (data or {}).get('text') if isinstance(data, dict) else None
    if not isinstance(text, str) or not text.strip():
        reject('INVALID_PAYLOAD', 'A command must be a line of text')
        return
    if len(text) > MAX_CHAT_LENGTH:
        reject('INVALID_PAYLOAD', f'A command must be at most {MAX_CHAT_LENGTH} characters')
        return
    if not commands_module.looks_like_command(text):
        reject('NOT_A_COMMAND', 'A command starts with /')
        return

    command_id, _args = commands_module.parse(text)
    command = commands_module.COMMANDS_BY_ID.get(command_id)

    # A command that changes the game is an action, so it comes from a seat at
    # the table — `require_actor` refuses an observer and anyone with no seat at
    # all. One that only reports needs no more than a place in the lobby, or a
    # watcher could not even ask what the rules are.
    if command is not None and command['changes_state']:
        actor = require_actor(data)
        if actor is None:
            return
    else:
        actor = viewer_for()
        if actor is None:
            reject('NOT_IN_LOBBY', 'Join before running commands')
            return

    with session.lock:
        game = session.game if session.game is not None \
            and session.game.game_state == "started" else None
        rules = game.rules if game is not None else session.lobby_rules

        result = commands_module.run(text, actor, game, rules)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        logger.info("command %r run by %s", text, actor)
        _announce(result, actor)

    # Answering the caller is the whole point of the four commands that only
    # report, and it is confirmation for the rest. Sender only: the table reads
    # the log entry, and a /whoami is nobody else's business.
    emit('command_result', {'command': command_id, 'lines': result['lines']})


def _announce(result, actor):
    """Log, broadcast and settle whatever the command did. Caller holds the lock.

    A command that changes the game is written into the shared log naming who
    ran it. That is the bargain this whole feature is played under: a table that
    allows commands is not promising nobody adds a card, it is promising
    everybody can see it happen.
    """
    if result['log']:
        log_event('command', result['log'], player=actor)

    if not result['changed']:
        return

    attack = result.get('attack')
    if attack is not None:
        # Reuse the roll's own reporting so a summoned attack reaches the client
        # through exactly the path a rolled one does — a second description
        # would be free to disagree with it.
        _announce_event_die({
            'face': 'barbarian',
            'red_die': None,
            'barbarian': True,
            'arrived': True,
            'position': 0,
            'attack': attack,
            'draws': {},
        })

    if result.get('current_player'):
        # Says whose turn it now is and broadcasts, exactly as ending a turn
        # normally does.
        _announce_turn(result['current_player'])
        return

    # A barbarian attack can stop the game on a question — which city is lost —
    # so whoever owes an answer is told before the board goes out.
    announce_choices()
    bump_and_broadcast()
