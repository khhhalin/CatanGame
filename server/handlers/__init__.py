"""Socket.IO event handlers, grouped by the part of the game they serve.

Importing a module here registers its handlers as a side effect of the
@socketio.on decorators, so app.py imports all of them at startup.
"""
