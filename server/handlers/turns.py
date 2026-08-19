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
    announce_choices,
    bump_and_broadcast,
    log_event,
    rate_limited,
    reject,
    require_actor,
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

    name = require_actor(data)
    if name is None:
        return

    with session.lock:
        result = session.game.advance_turn(name)
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
            'timer': session.game.timer_state(),
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

    name = require_actor(data)
    if name is None:
        return

    try:
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

    name = require_actor(data)
    if name is None:
        return

    with session.lock:
        result = session.game.roll_dice(name)
        if not result['success']:
            reject(result['code'], result['error'])
            return

        _announce_dice_roll(name, result)


def _announce_event_die(event):
    """Report the C&K event die outcome. Caller holds session.lock."""
    # Sent on every roll, not only on an attack: the barbarian track moves on
    # the roll and the client should not have to wait for a turn boundary — or
    # diff a whole board snapshot — to notice.
    socketio.emit('event_die', {
        'face': event['face'],
        'red_die': event['red_die'],
        'barbarian': event['barbarian'],
        'position': event['position'],
        'track_length': ck_module.BARBARIAN_TRACK_LENGTH,
        'arrived': event['arrived'],
        # Who drew is public; which card they drew is not.
        'drew': sorted(event.get('draws') or {}),
    })

    if not event['barbarian']:
        log_event('dice', f"City gate: {event['face']} (red die {event['red_die']})")
        for player_name in sorted(event.get('draws') or {}):
            log_event(
                'dice',
                f"{player_name} drew a {event['face']} progress card",
                player=player_name,
            )
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
            for player_name in sorted(result.get('draws') or {}):
                log_event(
                    'game',
                    f"{player_name} drew a progress card for the joint defence",
                    player=player_name,
                )
    else:
        # A player with more than one city to lose picks which one, so the
        # attack is not finished until they have answered.
        losers = ', '.join(result['pillaged'] + result['awaiting']) or 'nobody'
        log_event(
            'game',
            f"The barbarians sack Catan! {losers} lost a city "
            f"(knights {result['defence']} vs {result['attack']} cities)",
        )

    socketio.emit('barbarian_attack', result)


def _announce_production(total, gained):
    """Say what the roll paid, in one entry for the whole table.

    One line rather than one per player: the log is a shared history, and four
    players collecting on the same number would push everything else off the
    panel four lines at a time.

    Naming what each player took leaks nothing. Hands themselves stay redacted
    per viewer, but production is not a hand: `get_board_data` already sends
    every hex's type and number, every building with its owner, the robber's
    hex and the rule set to every client, and the roll itself is broadcast — so
    every client can already compute this exactly. Saying it out loud only
    saves them the arithmetic, and it is what tells a player their city paid
    one card where they expected two.
    """
    if gained:
        text = 'Production: ' + '; '.join(
            f"{player_name} " + ', '.join(f"+{count} {card}" for card, count in cards.items())
            for player_name, cards in gained.items()
        )
    else:
        # Said rather than left silent: "did anything happen?" has to be
        # answerable from the log alone.
        text = f"Production: the {total} paid nobody"

    log_event('dice', text, total=total, gained=gained)


def _announce_eruption(eruptions):
    """Say what a Krakatoa volcano's eruption struck, one entry per volcano.

    Public like production: `get_board_data` sends every building with its owner
    and every hex, and the roll is broadcast, so the whole table can already see
    a building vanish — this only names it as an eruption rather than leaving the
    disappearance to be read as a bug. Logged under `robber`, the category the
    other board-disruption events use.
    """
    for record in eruptions:
        player = record.get('player')
        if player is None:
            text = "A volcano erupts — the lava reaches open ground and spares every building."
        elif record.get('was') == 'city':
            text = f"A volcano erupts! {player}'s city is reduced to a settlement."
        else:
            text = f"A volcano erupts! {player}'s settlement is destroyed."
        log_event('robber', text, eruption=record)


def _announce_dice_roll(name, result):
    """Report a roll the engine has already applied. Caller holds session.lock."""
    dice1, dice2, total = result['dice1'], result['dice2'], result['total']

    logger.info("roll player=%s dice=%s+%s total=%s", name, dice1, dice2, total)
    # `modifiers` names the house rules that changed what this roll paid, so
    # the client can say why a city yielded less than the player expected
    # rather than leaving them to report it as a bug.
    log_event('dice', f"{name} rolled {dice1} + {dice2} = {total}",
              player=name, total=total, modifiers=result.get('modifiers') or [])

    # A 7 pays nobody by rule and has its own consequences to report, so the
    # production line is skipped there rather than stating the obvious.
    if total != 7:
        _announce_production(total, result.get('gained') or {})

    # Krakatoa: a volcano that came up erupts after production, so it is
    # announced after the production line — the building produced, then was
    # struck. A no-op off the rule or when no volcano matched.
    _announce_eruption(result.get('eruption') or [])

    if result['event']:
        _announce_event_die(result['event'])

    # Who must discard and how much is public: it is derived from hand sizes,
    # which every player can already see.
    for player_name, amount in result['discards'].items():
        socketio.emit('discard_required', {'player': player_name, 'amount': amount})

    socketio.emit('dice_rolled', {'player': name, 'dice1': dice1, 'dice2': dice2, 'total': total,
                                  'eruption': result.get('eruption') or []})

    # A barbarian attack can stop the game on a question — which city is lost,
    # which deck a joint defender draws from — so whoever owes an answer is
    # told before the board goes out.
    announce_choices()
    bump_and_broadcast({'highlight': total})

    # Cloth for Catan can win on a roll — the primary 14-VP win or the
    # villages-out end — so the same banner every other win uses is fired here,
    # after the final board so the table sees the deciding roll first. `reason`
    # rides along so the banner can name why it ended.
    game_over = result.get('game_over')
    if game_over:
        socketio.emit('game_won', {
            'player': game_over['winner'],
            'victory_points': game_over['victory_points'],
            'reason': game_over['reason'],
        })
        logger.info("GAME OVER! %s wins with %s victory points (%s)",
                    game_over['winner'], game_over['victory_points'],
                    game_over['reason'])


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


def _resolve_discards_on_timeout():
    """Discard for everyone the discard clock left hanging.

    Caller holds session.lock. A 7 blocks the robber, every build and every
    trade until the last card is in, so this is settled rather than skipped.
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


def _resolve_robber_on_timeout():
    """Move the robber and steal for a player who never did.

    Caller holds session.lock. Afterwards nothing is pending, so the turn ends
    through the ordinary path and a late `move_robber` is refused rather than
    landing on the next player's turn.
    """
    game = state.session().game

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


def _resolve_choices_on_timeout():
    """Answer the decisions nobody made in time. Caller holds session.lock.

    Every one is answered rather than dropped: the rule that asked is half
    applied until it has an answer, and clearing the queue instead would leave
    a barbarian attack that sacked no city at all.
    """
    game = state.session().game

    for settled in game.auto_resolve_choices():
        logger.info("choice timer expired, answered automatically: %s", settled)
        log_event(
            'game',
            f"{settled['player']} ran out of time, so the choice was made for them",
            player=settled['player'],
        )
        socketio.emit('choice_resolved', {'player': settled['player'], 'kind': settled['kind']})


def _watchdog_tick():
    """One pass of the turn watchdog. Runs with no request context.

    This is the server acting on its own behalf, so there is no socket and no
    seat behind it: nothing in here may reach for `request`, or a table whose
    player walked away stalls forever with a "working outside of request
    context" in the log and no error anyone can see.
    """
    # Fetched each pass rather than held: this task is started once at boot and
    # outlives any single session.
    session = state.session()
    with session.lock:
        game = session.game
        if game is None or game.game_state != "started":
            return

        # Exactly one clock runs at a time and this pass expires only that one.
        # An unfinished robber or discard used to park the watchdog here for
        # good — it `continue`d while either was pending, so the turn could
        # never end and the flag leaked into the next player's turn. Now the
        # phase says which clock to expire, resolving it clears the phase, and
        # the next pass picks up whatever the game moved on to.
        phase = game.timer_phase()
        if phase is None or not game.timer_expired():
            return

        current_player = game.players[game.current_player_index]

        if phase in ('discard', 'robber', 'choice'):
            if phase == 'discard':
                _resolve_discards_on_timeout()
            elif phase == 'robber':
                _resolve_robber_on_timeout()
            else:
                _resolve_choices_on_timeout()
            # Hands, the robber and whatever a choice settled all changed with
            # nobody clicking anything, so the table is told without waiting
            # for the next action to carry it.
            bump_and_broadcast()
        elif phase == 'dice':
            logger.info("dice timer expired, auto-rolling for %s", current_player.name)
            result = game.roll_dice(current_player.name)
            if result['success']:
                _announce_dice_roll(current_player.name, result)
        elif phase == 'turn':
            logger.info("turn timer expired, advancing past %s", current_player.name)
            _announce_turn(game.force_advance_turn())


def _turn_watchdog():
    """Expire turns server-side.

    Turn expiry used to depend on some client emitting next_turn, so a player
    who closed their laptop stalled the table indefinitely. This runs on the
    server and applies the timeout through the same validated path.
    """
    while True:
        socketio.sleep(1)
        try:
            _watchdog_tick()
        except Exception:
            logger.exception("turn watchdog error")
