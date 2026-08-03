"""Production entry point.

Run with:
    gunicorn -w 1 --threads 100 -b 0.0.0.0:5000 wsgi:app

`-w 1` is not a placeholder. Game state lives in this process's memory, so a
second worker would serve a different, empty game to whichever players its
connections happened to land on. Socket.IO's polling handshake also requires
every request of a session to reach the same process, and gunicorn does not do
sticky sessions. Scale by running several single-worker instances behind a
sticky load balancer, and move game state out of memory first.
"""

import logging
import logging.config

import state
from app import create_app
from extensions import socketio
from handlers.turns import _turn_watchdog

logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {'format': '%(asctime)s %(levelname)-8s %(name)s: %(message)s'},
    },
    # stdout, not a file: the container filesystem is ephemeral and the
    # platform already collects stdout.
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'default'},
    },
    'root': {'level': 'INFO', 'handlers': ['console']},
})

app = create_app()

# Bring back an interrupted game before accepting connections.
state.restore_saved_game()

socketio.start_background_task(_turn_watchdog)

__all__ = ['app', 'socketio']
