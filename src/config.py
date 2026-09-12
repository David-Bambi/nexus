import os
from pathlib import Path

# Repo root (parent of src/), used to build the default DB path.
BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """Default application configuration, sourced from environment
    variables with development-friendly fallbacks."""

    # Flask session/cookie signing key. Override in prod via env var.
    SECRET_KEY = os.environ.get("NEXUS_SECRET_KEY", "dev")

    # SQLAlchemy connection URL. Defaults to a SQLite file under instance/.
    DATABASE_URL = os.environ.get(
        "NEXUS_DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'nexus.db'}"
    )


class TestConfig(Config):
    """Configuration used by the test suite: in-memory DB, no file left
    behind, fresh each run."""

    TESTING = True
    DATABASE_URL = "sqlite:///:memory:"
