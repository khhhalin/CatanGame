"""Configuration objects, selected by the CATAN_CONFIG environment variable."""

import os


class Config:
    """Defaults shared by every environment. Safe-by-default: a forgotten
    override fails closed rather than open."""

    DEBUG = False
    TESTING = False

    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Game knobs. Here rather than as literals in handlers so a test can run
    # with a one-second turn timer and production can run with a real one.
    # The fallback seat count, used when the table leaves the `max_players`
    # rule at 0 — the same arrangement as the clocks below.
    MAX_PLAYERS = 4
    MIN_PLAYERS = 2
    VICTORY_POINTS_TO_WIN = 10
    # One clock per phase of a turn. These are the fallbacks: a table that sets
    # the matching rule in the lobby plays to its number instead.
    DICE_ROLL_SECONDS = 15
    DISCARD_SECONDS = 60
    ROBBER_SECONDS = 60
    ROUND_SECONDS = 120
    CHOICE_SECONDS = 30

    # Fix the shuffles and the dice to a reproducible sequence. Unset in
    # normal play; set it to replay a game exactly, which is what makes an
    # end-to-end test a gate rather than a coin toss.
    GAME_SEED = os.environ.get("CATAN_SEED")

    # Runtime state lives outside the repo tree in deployment.
    DATA_DIR = os.environ.get(
        "CATAN_DATA_DIR",
        os.path.join(os.path.dirname(__file__), "data"),
    )

    @staticmethod
    def secret_key() -> str:
        key = os.environ.get("SECRET_KEY")
        if not key:
            raise RuntimeError(
                "SECRET_KEY is not set. Generate one with:\n"
                "  python -c 'import secrets; print(secrets.token_hex())'\n"
                "and export it before starting the server."
            )
        return key


class DevelopmentConfig(Config):
    DEBUG = True
    # Local HTTP has no TLS, so a Secure cookie would never be sent back.
    SESSION_COOKIE_SECURE = False

    @staticmethod
    def secret_key() -> str:
        # Development only: a throwaway key so `python app.py` just works.
        # Any non-development config raises instead, per Config.secret_key.
        return os.environ.get("SECRET_KEY", "dev-only-not-for-deployment")


class TestingConfig(DevelopmentConfig):
    TESTING = True
    DICE_ROLL_SECONDS = 1
    # The discard and robber clocks were the round clock's job before they were
    # split out, so they keep its two seconds here. The decision clock is left
    # at the shared default: a browser test clicks a dialog at human speed, and
    # two seconds would answer it first.
    DISCARD_SECONDS = 2
    ROBBER_SECONDS = 2
    ROUND_SECONDS = 2


class ProductionConfig(Config):
    pass


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Resolve a config class by name, defaulting to CATAN_CONFIG or development."""
    name = name or os.environ.get("CATAN_CONFIG", "development")
    if name not in _CONFIGS:
        raise RuntimeError(
            f"Unknown config {name!r}. Expected one of: {', '.join(sorted(_CONFIGS))}"
        )
    return _CONFIGS[name]
