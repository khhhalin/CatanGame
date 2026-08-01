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

    # Check if player must move robber first
    if state.current_game.must_move_robber:
        reject('MUST_MOVE_ROBBER', 'You must move the robber first')
        return

    # Check if player must choose victim first
    if state.current_game.must_choose_victim:
        reject('MUST_CHOOSE_VICTIM', 'You must choose a victim to steal from')
        return

    # Check if player must discard first
    requester = data.get('name')
    if requester in state.current_game.players_needing_discard:
        reject('MUST_DISCARD', 'You must discard resources first')
        return

    # Don't allow manual turn advancement during setup phase
    if state.current_game.game_phase == "setup":
        reject('WRONG_PHASE', 'Cannot skip turn during setup phase')
        return

    with game_lock:
        current_player = state.current_game.players[state.current_game.current_player_index]
        current_player_name = current_player.name if current_player else None

        # The seat's own player normally ends the turn. Once the round timer has
        # run out anyone may advance it, so an absent player cannot stall the table.
        if requester != current_player_name and not state.current_game.is_round_expired():
            reject('NOT_YOUR_TURN', f'Only {current_player_name} can advance the turn')
            return

        _advance_turn()


def _advance_turn():
    """Move to the next player and reset the turn timers. Caller holds game_lock."""
    state.current_game.current_player_index = (state.current_game.current_player_index + 1) % len(
        state.current_game.players
    )
    state.current_game.turn_count += 1
    new_current_player = state.current_game.players[state.current_game.current_player_index]
    new_current_player_name = new_current_player.name if new_current_player else None

    # A new turn clears any follow-up the previous player never used, so an
    # unspent Invention cannot be redeemed two turns later.
    state.current_game.pending_invention = None
    state.current_game.pending_monopoly = None
    state.current_game.free_roads_remaining = 0

    # Reset turn timer
    state.current_game.start_turn()
    if state.current_game.ck:
        # Clears each knight's per-turn flags. Without it a knight that acts
        # once stays spent for the rest of the game.
        state.current_game.ck.start_turn()

    logger.info(
        "turn changed to=%s turn=%s", new_current_player_name, state.current_game.turn_count
    )
    log_event('turn', f"{new_current_player_name}'s turn", player=new_current_player_name)

    socketio.emit(
        'turn_changed',
        {
            'players': state.current_game.get_player_names(),
            'observers': state.current_game.observers,
            'current_player': new_current_player_name,
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

    # Don't allow dice rolling during setup phase
    if state.current_game.game_phase == "setup":
        reject('WRONG_PHASE', 'Cannot roll dice during setup phase')
        return

    try:
        name = require_str(data.get('name'), 'name')
    except InvalidPayload as exc:
        reject(exc.code, exc.message)
        return

    with game_lock:
        current_player = state.current_game.players[state.current_game.current_player_index]
        if current_player.name != name:
            reject('NOT_YOUR_TURN', f'Only {current_player.name} can roll dice')
            return

        if state.current_game.has_rolled_dice:
            reject('ALREADY_ROLLED', 'You have already rolled this turn')
            return

        _apply_dice_roll(name)


def _resolve_event_die(red_die):
    """Roll the C&K event die and act on it. Caller holds game_lock.

    Three of its six faces advance the barbarian ship; the other three open a
    city gate for one discipline, which is what lets players draw progress
    cards (the red production die decides who qualifies).
    """
    ck = state.current_game.ck
    event = state.current_game.roll_event_die()
    ck.last_event = event
    ck.last_red_die = red_die

    if event != ck_module.EVENT_BARBARIAN:
        # A city gate. Progress card draws are not wired up yet, so record it
        # for the client and move on rather than silently doing nothing.
        log_event('dice', f"City gate: {event} (red die {red_die})")
        return

    arrived = ck.advance_barbarians()
    if not arrived:
        remaining = ck_module.BARBARIAN_TRACK_LENGTH - ck.barbarian_position
        log_event(
            'dice',
            f"The barbarians advance ({ck.barbarian_position}/"
            f"{ck_module.BARBARIAN_TRACK_LENGTH}) - {remaining} to go",
        )
        return

    result = state.current_game.resolve_barbarian_attack()
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


def _apply_dice_roll(name):
    """Roll, distribute, and broadcast. Caller holds game_lock."""
    # Rolled through the game's own generator so a test can script the sequence
    # and so production uses a source that cannot be reconstructed from
    # observed outcomes.
    dice1 = state.current_game.rng.randint(1, 6)
    dice2 = state.current_game.rng.randint(1, 6)
    total = dice1 + dice2

    # Mark dice as rolled
    state.current_game.set_dice_rolled()

    logger.info("roll player=%s dice=%s+%s total=%s", name, dice1, dice2, total)
    log_event('dice', f"{name} rolled {dice1} + {dice2} = {total}", player=name, total=total)

    # Cities & Knights rolls a third die, and it is resolved *before*
    # production. Without this the barbarian ship never moves and knights have
    # nothing to defend against.
    if state.current_game.ck:
        _resolve_event_die(dice2)

    # Set must_move_robber if 7 is rolled (resources not distributed)
    if total == 7:
        # C&K: until the barbarians have attacked once, a 7 does not move the
        # robber — but the discard rule still applies.
        if not state.current_game.ck or state.current_game.ck.barbarians_have_attacked:
            state.current_game.must_move_robber = True
        state.current_game.check_discard_required()
        state.current_game.distribute_resources(total)  # This will skip distribution
    else:
        state.current_game.distribute_resources(total)

    # Who must discard and how much is public: it is derived from hand sizes,
    # which every player can already see.
    if state.current_game.players_needing_discard:
        for player_name, amount in state.current_game.players_needing_discard.items():
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
                    _apply_dice_roll(current_player.name)
                    continue

                if state.current_game.has_rolled_dice and state.current_game.is_round_expired():
                    logger.info("round timer expired, advancing past %s", current_player.name)
                    _advance_turn()
        except Exception:
            logger.exception("turn watchdog error")
