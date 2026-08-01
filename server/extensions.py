"""The Socket.IO extension, on its own so nothing has to import the app.

Created unbound and attached to the app in the factory. Every handler module
imports `socketio` from here, so this module must import nothing of ours —
anything it pulled in would become a cycle.
"""

from flask_socketio import SocketIO

socketio = SocketIO()
