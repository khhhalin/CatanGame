"""The turn cycle: rolling, the event die, advancing, and the turn watchdog."""

import logging

import state
from extensions import socketio
from flask_socketio import emit
from game import cities_knights as ck_module
from game.validation import (
    InvalidPayload,
    require_str,
)
from state import (
    bump_and_broadcast,
    game_lock,
    log_event,
    rate_limited,
    reject,
    update_users,
    viewer_for,
)

logger = logging.getLogger(__name__)


@socketio.on('next_turn')
def handle_next_turn(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return

    with game_lock:
        result = state.current_game.advance_turn(data.get('name'))
        if not result['success']:
            reject(result['code'], result['error'])
            return

        _announce_turn(result['current_player'])


def _announce_turn(current_player_name):
    """Tell everyone whose turn it now is. Caller holds game_lock."""
    logger.info("turn changed to=%s turn=%s", current_player_name, state.current_game.turn_count)
    log_event('turn', f"{current_player_name}'s turn", player=current_player_name)

    socketio.emit(
        'turn_changed',
        {
            'players': state.current_game.get_player_names(),
            'observers': state.current_game.observers,
            'current_player': current_player_name,
            'dice_roll_time': state.current_game.get_dice_roll_time_remaining(),
            'round_time': state.current_game.get_round_time_remaining(),
            'has_rolled_dice': state.current_game.has_rolled_dice,
        },
    )
    bump_and_broadcast()


@socketio.on('set_color')
def handle_set_color(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return

    try:
        name = require_str(data.get('name'), 'name')
        color = require_str(data.get('color'), 'color', max_length=32)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    if state.current_game.set_player_color(name, color):
        socketio.emit('player_color_changed', {'name': name, 'color': color})

        def set_color(users):
            for user in users:
                if user.get('name') == name:
                    user['color'] = color
                    break
            return users, None

        update_users(set_color)


@socketio.on('roll_dice')
def handle_roll_dice(data):
    if rate_limited():
        return
    if state.current_game is None or state.current_game.game_state != "started":
        return

    try:
        name = require_str(data.get('name'), 'name')
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with game_lock:
        result = state.current_game.roll_dice(name)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        _announce_dice_roll(name, result)


def _announce_event_die(event):
    """Report the C&K event die outcome. Caller holds game_lock."""
    if not event['barbarian']:
        # A city gate. Progress card draws are not wired up yet, so record it
        # for the client and move on rather than silently doing nothing.
        log_event('dice', f"City gate: {event['face']} (red die {event['red_die']})")
        return

    if not event['arrived']:
        remaining = ck_module.BARBARIAN_TRACK_LENGTH - event['position']
        log_event(
            'dice',
            f"The barbarians advance ({event['position']}/"
            f"{ck_module.BARBARIAN_TRACK_LENGTH}) - {remaining} to go",
        )
        return

    result = event['attack']
    logger.info("barbarian attack: %s", result)

    if result['won']:
        if len(result['defenders']) == 1:
            log_event(
                'game',
                f"The barbarians are beaten off! {result['defenders'][0]} "
                f"led the defence and takes a victory point "
                f"(knights {result['defence']} vs {result['attack']} cities)",
            )
        else:
            defenders = ', '.join(result['defenders']) or 'nobody'
            log_event(
                'game',
                f"The barbarians are beaten off by {defenders} "
                f"(knights {result['defence']} vs {result['attack']} cities)",
            )
    else:
        losers = ', '.join(result['pillaged']) or 'nobody'
        log_event(
            'game',
            f"The barbarians sack Catan! {losers} lost a city "
            f"(knights {result['defence']} vs {result['attack']} cities)",
        )

    socketio.emit('barbarian_attack', result)


def _announce_dice_roll(name, result):
    """Report a roll the engine has already applied. Caller holds game_lock."""
    dice1, dice2, total = result['dice1'], result['dice2'], result['total']

    logger.info("roll player=%s dice=%s+%s total=%s", name, dice1, dice2, total)
    log_event('dice', f"{name} rolled {dice1} + {dice2} = {total}", player=name, total=total)

    if result['event']:
        _announce_event_die(result['event'])

    # Who must discard and how much is public: it is derived from hand sizes,
    # which every player can already see.
    for player_name, amount in result['discards'].items():
        socketio.emit('discard_required', {'player': player_name, 'amount': amount})

    socketio.emit('dice_rolled', {'player': name, 'dice1': dice1, 'dice2': dice2, 'total': total})

    bump_and_broadcast({'highlight': total})


@socketio.on('refresh_board')
def handle_refresh_board(data=None):
    if rate_limited():
        return
    """Resync for one client. Replies to the asker only.

    This used to broadcast, and every client polled it on a one-second timer,
    so a single expiring trade produced N full board snapshots to N clients.
    """
    if state.current_game is None or state.current_game.game_state != "started":
        return
    emit('board_updated', {'board': state.current_game.get_board_data(viewer=viewer_for())})


def _turn_watchdog():
    """Expire turns server-side.

    Turn expiry used to depend on some client emitting next_turn, so a player
    who closed their laptop stalled the table indefinitely. This runs on the
    server and applies the timeout through the same validated path.
    """
    while True:
        socketio.sleep(1)
        try:
            with game_lock:
                if state.current_game is None or state.current_game.game_state != "started":
                    continue
                if state.current_game.game_phase == "setup":
                    continue
                if state.current_game.must_move_robber or state.current_game.must_choose_victim:
                    continue
                if state.current_game.players_needing_discard:
                    continue

                current_player = state.current_game.players[state.current_game.current_player_index]

                # Auto-roll first: a turn cannot advance before the dice are up.
                if (
                    not state.current_game.has_rolled_dice
                    and state.current_game.is_dice_roll_expired()
                ):
                    logger.info("dice timer expired, auto-rolling for %s", current_player.name)
                    result = state.current_game.roll_dice(current_player.name)
                    if result['success']:
                        _announce_dice_roll(current_player.name, result)
                    continue

                if state.current_game.has_rolled_dice and state.current_game.is_round_expired():
                    logger.info("round timer expired, advancing past %s", current_player.name)
                    _announce_turn(state.current_game.force_advance_turn())
        except Exception:
            logger.exception("turn watchdog error")
