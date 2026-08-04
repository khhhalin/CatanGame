# AGENTS.md - CatanPro Development Guide

## Project Overview
- **Backend**: Python with Flask and Flask-SocketIO
- **Frontend**: Vanilla JavaScript and HTML (no framework)
- **Architecture**: Modular component-based design

---

## Build, Lint, and Test Commands

### Python (Backend)
```bash
# Install dependencies (into a venv or the Nix shell, never system Python)
pip install -r server/requirements.txt

# Run the Flask server for local development
python server/app.py

# Run in production (never the dev server — see coding-rules.md Part I)
gunicorn -w 1 --threads 100 -b 0.0.0.0:5000 wsgi:app

# Run all tests
pytest

# Run a single test
pytest tests/game/test_rules.py::TestCosts::test_city_cost_matches_the_rulebook -v
pytest tests/ -k "discard" -v

# Run tests with coverage
pytest --cov=server --cov-report=term

# Lint and format
ruff check server/ tests/
ruff format server/ tests/
```

### JavaScript (Frontend)
No build system - vanilla JS served directly. For linting:
```bash
npm install eslint --save-dev
npx eslint server/static/js/
```

---

## Code Style Guidelines

### General Principles
- Keep functions small and focused (single responsibility)
- Maximum line length: 100 characters
- Use 2 spaces for indentation (no tabs)
- Comment complex logic, not obvious code

### Python Style

**Imports** (order: stdlib → external → project):
```python
import json
import os
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from game.game import Game
```
- Use absolute imports: `from server.game.models import Player`
- Avoid `from module import *`

**Naming Conventions**:
- Variables/functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

**Types**:
- Use type hints for function signatures
- Prefer explicit types over `Any`
- Use `Optional[X]` instead of `X | None`

**Error Handling**:
- Use specific exceptions, not bare `except:`
- Log errors before re-raising
- Never expose stack traces to users

**Example**:
```python
from typing import Optional
import logging
from flask import Flask

logger = logging.getLogger(__name__)

class GameError(Exception):
    pass

def create_app(config: dict) -> Flask:
    app = Flask(__name__)
    app.config.update(config)
    return app
```

### JavaScript Style

**General**: Use ES6+ syntax, keep scripts modular, avoid global variables.

**Naming**:
- Variables/functions: `camelCase`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`

**Error Handling**: Handle async errors with try/catch, display user-friendly messages.

**Example**:
```javascript
const socket = io();
let currentUser = null;
const MAX_PLAYERS = 4;

function handleJoin(data) {
    try {
        const name = data.name.trim();
        if (!name) {
            throw new Error('Name cannot be empty');
        }
        // Game logic here
    } catch (error) {
        console.error('Join error:', error.message);
        displayError(error.message);
    }
}
```

---

## Project Structure
```
CatanPro/
├── server/
│   ├── app.py              # Flask + SocketIO entry point
│   ├── requirements.txt    # Python dependencies
│   ├── static/css/         # Stylesheets
│   ├── static/js/          # JavaScript files
│   ├── templates/          # HTML templates
│   ├── data/               # Game data (JSON)
│   ├── game/               # Game logic modules
├── tests/                  # Python tests (pytest), mirrors server/
├── build.md                # Project specification
└── AGENTS.md               # This file
```

---

## Testing Guidelines
- Use `pytest` as test framework
- Place tests in the top-level `tests/` directory, mirroring `server/`
- Follow naming: `test_<module>_<function>.py`
- Use fixtures for common test setup
- Mock external dependencies
- Run tests with coverage: `pytest --cov=server --cov-report=term`

---

## Socket Events
Document custom events when implementing:
- `connect` / `disconnect` - Client connects/disconnects
- `join` - Player joins game
- `start_game` - Start new game
- `next_turn` - Advance turn
- `place_settlement` / `place_road` - Place game pieces
- `set_color` - Set player color
- `roll_dice` - Roll dice
- `error` - Error response

---

## Git Workflow
1. Create feature branch: `git checkout -b feature/feature-name`
2. Make changes and commit with descriptive messages
3. Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`
4. Run linting and tests before committing
5. Push to remote and create pull request

---

## Additional Notes
- Run linting before committing
- Ensure all tests pass before submitting PRs
- Frontend: vanilla JS in `server/static/js/`
- Backend: Flask + SocketIO in `server/`
- Run production under gunicorn with `async_mode="threading"`; eventlet is deprecated and no longer used

---

## Reference documents
- `coding-rules.md` — architecture, security, and protocol rules. Read the
  relevant Part before changing that layer.
- `OPEN-THREADS.md` — what is started, known-broken, or deliberately deferred.
  (The compliance audit that produced these rules is no longer in the tree: it
  documented a live authorisation hole in a public repo. See `git log` if you
  need it.)
- `expansions.md` — pick-and-choose catalogue of official expansion rules.
- `board-zoom-plan.md` — researched plan for board zoom/pan (not yet implemented).

## Adding an optional rule
`server/game/rules.py` is the single registry. Add an entry there (with an accurate
`source` citing the rulebook) and it appears in the lobby automatically — the picker
renders from the server's catalogue, so no front-end change is needed. Then read
`game.rules['your_id']` wherever it applies, and add a test in
`tests/game/test_rules_options.py`.

Three standing rules about the registry:

- **There are no modes.** An expansion is listed as the individual rules it is made
  of, and no engine code asks "is expansion X on" — it asks for the one rule that
  governs the behaviour in front of it. A table that wants knights and barbarians
  without commodities must be able to have exactly that. `PRESETS` ticks a named
  set of rules in one click; nothing anywhere records which preset was used.
- **Never add a rule nothing reads.** A setting the engine ignores is worse than no
  setting: the lobby shows it, the table agrees on it, and the game does not play
  it. If you cannot implement it, leave it out of `RULES`.
- **A rule may suggest a victory target; only the table sets one.** Nothing may
  add to or overwrite `victory_target` at construction — that bug was reported as
  "10 vp needed setting got overridden". Put the suggestion in the rule's
  `suggests_victory_target` and in the preset that ticks it.
- **Dependencies are refused, never quietly satisfied.** A rule that cannot act
  alone (a metropolis with no improvement tracks) declares what it needs in
  `DEPENDENCIES`; `start_game` refuses the combination and names what is missing.
  Switching the missing rule on for the table would hand them a game they did not
  agree to.
