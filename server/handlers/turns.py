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
    log_event,
    rate_limited,
    reject,
    update_users,
    viewer_for,
)

logger = logging.getLogger(__name__)


@socketio.on('next_turn')
def handle_next_turn(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    with session.lock:
        result = session.game.advance_turn(data.get('name'))
        if not result['success']:
            reject(result['code'], result['error'])
            return

        _announce_turn(result['current_player'])


def _announce_turn(current_player_name):
    """Tell everyone whose turn it now is. Caller holds session.lock."""
    session = state.session()
    logger.info("turn changed to=%s turn=%s", current_player_name, session.game.turn_count)
    log_event('turn', f"{current_player_name}'s turn", player=current_player_name)

    socketio.emit(
        'turn_changed',
        {
            'players': session.game.get_player_names(),
            'observers': session.game.observers,
            'current_player': current_player_name,
            'dice_roll_time': session.game.get_dice_roll_time_remaining(),
            'round_time': session.game.get_round_time_remaining(),
            'has_rolled_dice': session.game.has_rolled_dice,
        },
    )
    bump_and_broadcast()


@socketio.on('set_color')
def handle_set_color(data):
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    try:
        name = require_str(data.get('name'), 'name')
        color = require_str(data.get('color'), 'color', max_length=32)
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    # Same reason as the lobby: two players in one colour make the board
    # unreadable. Mid-game there is nowhere sensible to reassign to, so refuse.
    if any(p.color == color and p.name != name for p in session.game.players):
        reject('COLOR_TAKEN', 'Another player already has that colour')
        return

    if session.game.set_player_color(name, color):
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
    session = state.session()
    if rate_limited():
        return
    if session.game is None or session.game.game_state != "started":
        return

    try:
        name = require_str(data.get('name'), 'name')
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with session.lock:
        result = session.game.roll_dice(name)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        _announce_dice_roll(name, result)


def _announce_event_die(event):
    """Report the C&K event die outcome. Caller holds session.lock."""
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
    """Report a roll the engine has already applied. Caller holds session.lock."""
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
    session = state.session()
    if rate_limited():
        return
    """Resync for one client. Replies to the asker only.

    This used to broadcast, and every client polled it on a one-second timer,
    so a single expiring trade produced N full board snapshots to N clients.
    """
    if session.game is None or session.game.game_state != "started":
        return
    emit('board_updated', {'board': session.game.get_board_data(viewer=viewer_for())})


def _resolve_on_timeout():
    """Settle the discards and the robber the round timer left hanging.

    Caller holds session.lock. Afterwards nothing is pending, so the turn ends
    through the ordinary path and a late `move_robber` is refused rather than
    landing on the next player's turn.
    """
    game = state.session().game

    for player_name in list(game.players_needing_discard):
        discarded = game.auto_discard(player_name)
        logger.info("discard timer expired, discarding %s for %s", discarded, player_name)
        log_event(
            'trade',
            f"{player_name} ran out of time and discarded {sum(discarded.values())} cards",
            player=player_name,
        )
        socketio.emit('discard_completed', {'player': player_name})

    if not (game.must_move_robber or game.must_choose_victim):
        return

    outcome = game.auto_resolve_robber()
    logger.info("robber timer expired, resolved automatically: %s", outcome)
    if outcome['hex']:
        log_event(
            'robber',
            f"{outcome['player']} ran out of time, so the robber was moved for them",
            player=outcome['player'],
        )
    if outcome['victim']:
        # Same secrecy as a hand-picked steal: the table sees that it happened.
        log_event(
            'robber',
            f"{outcome['player']} stole a card from {outcome['victim']}",
            player=outcome['player'],
        )


def _turn_watchdog():
    """Expire turns server-side.

    Turn expiry used to depend on some client emitting next_turn, so a player
    who closed their laptop stalled the table indefinitely. This runs on the
    server and applies the timeout through the same validated path.
    """
    while True:
        socketio.sleep(1)
        try:
            # Fetched each pass rather than held: this task is started once at
            # boot and outlives any single session.
            session = state.session()
            with session.lock:
                if session.game is None or session.game.game_state != "started":
                    continue
                if session.game.game_phase == "setup":
                    continue
                # An unfinished robber or discard used to park the watchdog
                # here for good: those flags block every other action, so the
                # turn could never end and the table stopped. Give the player
                # the rest of their round, then settle it for them.
                if (
                    session.game.must_move_robber
                    or session.game.must_choose_victim
                    or session.game.players_needing_discard
                ):
                    if not session.game.is_round_expired():
                        continue
                    _resolve_on_timeout()

                current_player = session.game.players[session.game.current_player_index]

                # Auto-roll first: a turn cannot advance before the dice are up.
                if (
                    not session.game.has_rolled_dice
                    and session.game.is_dice_roll_expired()
                ):
                    logger.info("dice timer expired, auto-rolling for %s", current_player.name)
                    result = session.game.roll_dice(current_player.name)
                    if result['success']:
                        _announce_dice_roll(current_player.name, result)
                    continue

                if session.game.has_rolled_dice and session.game.is_round_expired():
                    logger.info("round timer expired, advancing past %s", current_player.name)
                    _announce_turn(session.game.force_advance_turn())
        except Exception:
            logger.exception("turn watchdog error")
