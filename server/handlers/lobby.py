"""Joining, the lobby roster, house rules, and starting or ending a game."""

import logging
import os
import random

import build_info
import changelog
import state
from extensions import socketio
from flask import request
from flask_socketio import emit
from game import map_store, maps
from game import rules as rules_module
from game.game import Game
from game.validation import (
    InvalidPayload,
    require_str,
)
from state import (
    COLOR_PALETTE,
    SAVE_FILE,
    emit_rules,
    emit_user_list,
    get_random_color,
    get_user_by_name,
    lobby_users,
    log_event,
    rate_limited,
    reject,
    remove_user_by_name,
    save_game,
    seat_limit,
    send_state_snapshot,
    update_users,
    viewer_for,
)

logger = logging.getLogger(__name__)


def _colors_in_use(users, exclude=None) -> set:
    """Colours held by people who are actually connected, ignoring one name.

    Presence rather than the whole of users.json, for the same reason
    `lobby_users` uses it: the file remembers everyone who has ever played, and
    their colours are not in use.
    """
    present = set(state.session().viewers.values()) - {exclude}
    return {u.get('color') for u in users if u.get('name') in present and u.get('color')}


def _free_color(taken: set) -> str:
    """A palette colour nobody is using; falls back to any if all are taken."""
    for palette_color in COLOR_PALETTE:
        if palette_color not in taken:
            return palette_color
    return get_random_color()


@socketio.on('join')
def handle_join(data):
    session = state.session()
    if rate_limited():
        return
    try:
        name = require_str(data.get('name'), 'name')
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    # Taking over someone's seat is a supported move, but it has to be asked
    # for. Browsers pre-fill the name field, so without this a second window
    # silently joins as whoever joined first and both end up viewing that
    # player — which reads as "every browser became A".
    holder = next(
        (sid for sid, viewer in session.viewers.items()
         if viewer == name and sid != request.sid),
        None,
    )
    if holder is not None and not data.get('takeover'):
        reject('NAME_TAKEN',
               f'"{name}" is already connected. Pick a different name, '
               f'or confirm to take over their seat.')
        return

    role = data.get('role', 'observer')
    if role not in ('player', 'observer'):
        role = 'observer'

    color = data.get('color', '')
    if not isinstance(color, str) or len(color) > 32:
        color = ''

    if session.game is not None and session.game.game_state == "started":
        if session.game.is_player(name):
            role = "player"
        else:
            role = "observer"

    # Read once, outside the users.json update: the cap is the table's rule
    # (or this server's default), and it must not change between the refusal
    # and the message that explains it.
    seats = seat_limit()

    def add_or_replace(users):
        chosen_color = color

        existing_user = get_user_by_name(users, name)
        if existing_user:
            users = remove_user_by_name(users, name)
            # Use provided color, or existing saved color, or random
            if not chosen_color:
                chosen_color = existing_user.get('color')

        if not chosen_color:
            chosen_color = get_random_color()

        # Two players in the same colour make the board unreadable, and the
        # remembered colour in users.json means it happens without anyone
        # choosing it. Reassign rather than refuse: the join itself is fine,
        # only the colour is not, and a rejected join has no obvious recovery.
        taken = _colors_in_use(users, exclude=name)
        if chosen_color in taken:
            chosen_color = _free_color(taken)

        if role == 'player':
            # Count seats held by people who are actually connected, excluding
            # this socket's own name so rejoining or taking over a seat never
            # counts twice.
            present = set(session.viewers.values()) - {name}
            player_count = sum(
                1 for u in users
                if u.get('role') == 'player' and u.get('name') in present
            )
            if player_count >= seats:
                return None, 'full'

        users.append({'name': name, 'role': role, 'color': chosen_color})
        return users, 'ok'

    if update_users(add_or_replace) == 'full':
        reject('GAME_FULL', f'Cannot join as player. Max {seats} players allowed.')
        return

    # Bind the socket's private view only now that the join has been accepted.
    # Binding before the seat check left a rejected socket registered as
    # present, which then made its own name look taken on the retry.
    session.viewers[request.sid] = name

    if holder is not None:
        # A seat has exactly one holder. Leaving the old binding in place is
        # the two-sockets-one-player state that used to let either of them act
        # as that player, which is the thing this is meant to end. The old
        # socket is told, so a browser that lost its seat can say why.
        session.viewers.pop(holder, None)
        logger.warning("seat takeover name=%s new_sid=%s old_sid=%s",
                       name, request.sid, holder)
        log_event('game', f"Someone took over {name}'s seat", player=name)
        emit('error', {'code': 'SEAT_TAKEN',
                       'message': f"Another connection took over {name}'s seat."},
             to=holder)

    if session.game is not None and session.game.game_state == "started" \
            and not session.game.is_player(name):
        session.game.add_observer(name)

    logger.info("join name=%s role=%s sid=%s", name, role, request.sid)
    log_event('game', f"{name} joined as {role}", player=name)
    emit_user_list()

    # Always answer a join with the current state, whether or not a game is
    # running. A client that reconnects during the lobby otherwise gets nothing
    # back and has no recovery but a page reload.
    send_state_snapshot()

    # Push the rules unasked, so a client that arrives late sees the table's
    # selection without having to know to request it.
    emit_rules(to_sender_only=True)

@socketio.on('request_users')
def handle_request_users(data=None):
    if rate_limited():
        return
    emit_user_list()

@socketio.on('request_rules')
def handle_request_rules(data=None):
    if rate_limited():
        return
    emit_rules(to_sender_only=True)

@socketio.on('set_rules')
def handle_set_rules(data):
    session = state.session()
    if rate_limited():
        return
    """Change the rules for the next game.

    Anyone in the lobby may do this — it is a shared decision, and the table
    can talk. It is refused once a game is running.
    """

    if session.game is not None and session.game.game_state == "started":
        reject('GAME_IN_PROGRESS', 'Rules cannot change once a game has started')
        return

    if viewer_for() is None:
        reject('NOT_IN_LOBBY', 'Join before changing the rules')
        return

    # A preset is a shortcut, not a mode: it names a set of individual rules to
    # tick, and what lands in `lobby_rules` is that set. Nothing records which
    # preset was used, and every rule in it stays separately switchable.
    preset_id = data.get('preset')
    if preset_id is not None:
        chosen = rules_module.preset_rules(preset_id)
        if chosen is None:
            reject('UNKNOWN_PRESET', f'There is no "{preset_id}" preset')
            return
        session.lobby_rules = chosen
    else:
        session.lobby_rules = rules_module.coerce(data.get('rules'))
    logger.info("rules set by %s: %s", viewer_for(), session.lobby_rules)
    log_event('rules', f"{viewer_for()} changed the house rules", player=viewer_for())
    emit_rules()

@socketio.on('request_state')
def handle_request_state(data=None):
    if rate_limited():
        return
    """Explicit resync. Replies to the asking socket, never the room."""
    send_state_snapshot()

@socketio.on('end_game')
def handle_end_game(data=None):
    session = state.session()
    if rate_limited():
        return
    """Abandon the current game and return everyone to the lobby.

    Without this there is no way out of a game at all: a game that is
    abandoned, or left half-finished because everyone closed their tab, keeps
    `session.game` alive forever, so `start_game` refuses and every new arrival
    is dropped into a match nobody is playing.

    Any player at the table may call it — this is a friendly game, and the
    alternative is restarting the server.
    """

    with session.lock:
        if session.game is None or session.game.game_state != "started":
            reject('NO_GAME', 'There is no game to end')
            return

        if viewer_for() is None:
            reject('NOT_IN_LOBBY', 'Join before ending the game')
            return

        logger.info("game ended by %s (was: %s)", viewer_for(),
                    session.game.get_player_names())
        log_event('game', f"{viewer_for()} ended the game", player=viewer_for())
        session.game = None
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)

    socketio.emit('game_ended', {'by': viewer_for()})
    emit_user_list()
    emit_rules()

@socketio.on('start_game')
def handle_start_game(data=None):
    session = state.session()
    if rate_limited():
        return

    with session.lock:
        if session.game is not None and session.game.game_state == "started":
            reject('GAME_IN_PROGRESS', 'A game is already in progress')
            return

        _start_game_locked()

def _start_game_locked():
    session = state.session()

    # Seat only people who are actually here — the remembered list in
    # users.json includes everyone who has ever played.
    users = lobby_users()
    players = [u.get('name') for u in users if u.get('role') == 'player']
    observers = [u.get('name') for u in users if u.get('role') == 'observer']

    # Build player colors dict from users
    player_colors = {}
    for u in users:
        if u.get('role') == 'player' and u.get('color'):
            player_colors[u.get('name')] = u.get('color')

    # A custom map is read from disk here and not before. `board_map`'s options
    # are whatever was on disk when the picker was drawn, and `coerce` falls
    # back to the default on an id it does not know — so a map deleted between
    # the choice and the start would quietly hand the table a different board.
    # Refuse by name instead.
    map_definition = None
    if session.lobby_rules['board_layout'] == 'custom':
        map_id = session.lobby_rules['board_map']
        try:
            map_definition = map_store.load_definition(map_id)
        except (map_store.UnknownMap, InvalidPayload) as exc:
            reject('UNKNOWN_MAP', f'The map "{map_id}" cannot be played: {exc}')
            return

    # Some rules cannot do anything without another: a metropolis needs the
    # improvement tracks that award one, progress cards need the event die the
    # barbarians bring. A map joins the same list from the other side — two
    # islands and no Ships is a table that cannot reach half its board. Say so
    # and refuse rather than tick the missing box; switching on a rule nobody
    # asked for is a different game.
    problems = rules_module.dependency_problems(session.lobby_rules)
    if map_definition is not None:
        problems += maps.start_problems(map_definition, session.lobby_rules)
    if problems:
        reject('INCOHERENT_RULES', 'These rules do not work together: ' + '; '.join(problems))
        return

    minimum = session.lobby_rules['min_players']
    if len(players) < minimum:
        reject('NOT_ENOUGH_PLAYERS',
               f'Need at least {minimum} player{"s" if minimum != 1 else ""} to start '
               f'({len(players)} in the lobby)')
        return

    seed = getattr(session.config, 'GAME_SEED', None)
    session.game = Game(players, observers, player_colors, config=session.config,
                        rules=session.lobby_rules,
                        rng=random.Random(seed) if seed else None,
                        map_definition=map_definition)
    session.game.start()
    session.game.update_harbormaster()
    logger.info("game started players=%s observers=%s rules=%s",
                players, observers, session.game.rules)
    log_event('game', f"Game started with {', '.join(players)}")
    save_game()
    emit_rules()

    current_player = session.game.players[session.game.current_player_index]
    for sid, name in list(session.viewers.items()):
        emit('game_started', {
            'build': build_info.summary(),
            'players': session.game.get_player_names(),
            'observers': session.game.observers,
            'current_player': current_player.name if current_player else None,
            'board': session.game.get_board_data(viewer=name)
        }, to=sid)

@socketio.on('request_changelog')
def handle_request_changelog(data=None):
    """What this server is running, and what changed in it.

    Answered to the asking socket only, and answerable before anyone has
    joined: a tester on a stale tab has to be able to read the build id
    without first taking a seat.

    Registered here rather than in a module of its own because app.py names
    every handler module it imports, and a build identity is a fact about this
    server — the same thing the lobby already answers for the roster and the
    rules. A malformed changelog is reported as an error the panel can show
    instead of taking the whole reply down with it: the build id is the half
    that actually saves a triage round, and it does not depend on the file
    parsing.
    """
    if rate_limited():
        return

    payload = {'build': build_info.summary(), 'releases': []}
    try:
        payload['releases'] = changelog.load()
    except changelog.ChangelogError as exc:
        logger.exception("the changelog could not be parsed")
        payload['error'] = str(exc)
    emit('changelog', payload)

@socketio.on('disconnect')
def handle_disconnect(reason=None):
    """Drop the socket's view binding and free its lobby seat.

    The seat in a *running game* survives — a dropped connection is usually a
    brief blip, and ending the game would punish everyone else for it. But the
    lobby roster is presence-based, so leaving must free the slot; otherwise
    yesterday's players still fill the lobby today.

    Current python-socketio passes a disconnect reason; the parameter is
    optional so the handler also works on versions that pass nothing.
    """
    session = state.session()
    name = session.viewers.pop(request.sid, None)
    session.abuse_tracker.forget(request.sid)
    session.rate_limiter.prune()
    logger.info("disconnect name=%s sid=%s reason=%s", name, request.sid, reason)
    if name is not None:
        emit_user_list()
