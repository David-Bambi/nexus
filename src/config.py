import os
from pathlib import Path

# Repo root (parent of src/).
BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """Default application configuration, sourced from environment
    variables with usable fallbacks."""

    # Flask session/cookie signing key. Override in prod via env var.
    SECRET_KEY = os.environ.get("NEXUS_SECRET_KEY", "dev")

    # Folder holding everything the app writes: database, log, backups.
    # NEXUS_HOME overrides the default ~/.nexus.
    DATA_DIR = Path(os.environ.get("NEXUS_HOME", "~/.nexus")).expanduser()

    # SQLAlchemy connection URL. Defaults to a SQLite file in DATA_DIR.
    DATABASE_URL = os.environ.get(
        "NEXUS_DATABASE_URL", f"sqlite:///{DATA_DIR / 'data.db'}"
    )

    # Rotating application log file.
    LOG_FILE = DATA_DIR / "app.log"

    # Folder receiving the timestamped database backups.
    BACKUP_DIR = DATA_DIR / "backups"

    # Number of most recent backups kept.
    BACKUP_KEEP = 14

    # Address the server binds to. A constant on purpose, never read from
    # the environment: the app has no authentication, so it must not be
    # reachable from the network.
    HOST = "127.0.0.1"

    # Port the server listens on.
    PORT = int(os.environ.get("NEXUS_PORT", "8765"))


class TestConfig(Config):
    """Configuration used by the test suite: in-memory DB, no file left
    behind, fresh each run."""

    TESTING = True
    DATABASE_URL = "sqlite:///:memory:"
