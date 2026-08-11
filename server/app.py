"""Flask application factory and the HTTP surface.

The socket handlers live in `handlers/`, grouped by the part of the game they
serve; shared state and helpers live in `state.py`. This module only builds the
app, attaches the extension, and pulls the handler modules in so their
`@socketio.on` decorators run.

Nothing here runs at import time: the app is built by `create_app()` so a test
can ask for its own app, with its own configuration and its own game session,
instead of every test sharing whatever the first import happened to build.
"""

import json
import logging
import uuid

import state
from config import Config, get_config
from extensions import socketio
from flask import Flask, Response, render_template, request
from flask_socketio import emit
from game import resources

# Importing these registers every handler as a side effect of the decorators.
# Without the import the events simply do not exist, with no error to say so —
# which is why they are named here rather than discovered dynamically. They
# register against the unbound `socketio`, so this costs nothing until a
# factory call binds it to an app.
from handlers import (  # noqa: F401  (imported for their side effects)
    building,
    chat,
    choices,
    cities_knights,
    commands,
    dev_cards,
    lobby,
    maps,
    robber,
    ships,
    trading,
    turns,
)

logger = logging.getLogger(__name__)


def create_app(config=None):
    """Build an app. `config` is a config name, a Config subclass, or None.

    None resolves through CATAN_CONFIG, so production and a plain `python
    app.py` need no argument while a test can ask for `create_app('testing')`.
    """
    config_class = config if isinstance(config, type) and issubclass(config, Config) \
        else get_config(config)

    app = Flask(__name__)
    # Config first: extensions read app.config during init_app and silently
    # fall back to defaults if the values are not there yet.
    app.config.from_object(config_class)
    app.config['SECRET_KEY'] = config_class.secret_key()

    # Pinned rather than auto-detected: auto-detection picks whichever greenlet
    # library happens to be installed, so a transitive dependency could silently
    # change the concurrency model between dev and prod.
    socketio.init_app(app, async_mode='threading')

    # A new app is a new server, so it gets an empty session: one game, one set
    # of viewers, one event log. This is what lets a test start from a clean
    # table rather than unsetting state module by module.
    state.new_session(config_class)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/resources.json')
    def resources_export():
        """The current resource registry, as a file the player downloads.

        This is the whole registry — the defaults with any `data/resources.json`
        overrides already merged in — so the download doubles as a template: edit
        it, drop it back at that path, and the server draws every board from it.
        The attachment disposition makes the browser save rather than display it.
        """
        payload = json.dumps(resources.registry(), indent=2, ensure_ascii=False)
        return Response(
            payload,
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename="resources.json"'},
        )

    return app


@socketio.on_error_default
def handle_socket_error(exc):
    """Catch anything a handler raises.

    Without this, python-socketio swallows the exception: the move simply
    vanishes with no error, no acknowledgement, and no disconnect, and the
    player is left staring at a button that did nothing.

    The player gets a short reference code and the exception type — enough to
    tell "the server is broken" from "I did something wrong", and enough to
    find the traceback in the log without asking them to reproduce it. The
    traceback itself stays server-side; it would mean nothing to a player and
    leaks internals.
    """
    event = request.event.get('message') if request else '?'
    args = request.event.get('args') if request else None
    reference = uuid.uuid4().hex[:8]

    logger.exception(
        "unhandled error [%s] in event=%s sid=%s viewer=%s payload=%r",
        reference, event, getattr(request, 'sid', '?'),
        state.session().viewers.get(getattr(request, 'sid', None)), args,
    )

    emit('error', {
        'code': 'SERVER_ERROR',
        'message': (
            f'The server hit an error handling "{event}" '
            f'({type(exc).__name__}). Reference {reference} — it is in the '
            f'server log.'
        ),
        'details': {'event': event, 'reference': reference},
    })


if __name__ == '__main__':
    # Development only. The production entry point is wsgi.py, run under
    # gunicorn — the Werkzeug dev server has no hardening and, with debug on,
    # exposes an interactive console that executes arbitrary Python.
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
    )
    dev_app = create_app()
    state.restore_saved_game()
    socketio.start_background_task(turns._turn_watchdog)
    socketio.run(dev_app, host='127.0.0.1', port=5000, debug=dev_app.config['DEBUG'])
