import logging
from pathlib import Path

from sqlalchemy.engine import make_url
from waitress import serve

from src.app import create_app
from src.backup import backup_database
from src.config import Config
from src.logging_config import configure_logging

logger = logging.getLogger(__name__)


def _database_file() -> Path | None:
    """Return the path of the configured SQLite database file.

    Returns:
        The file path, or None if the database isn't a SQLite file (another
        database, or in memory), which has nothing to copy.
    """
    url = make_url(Config.DATABASE_URL)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        return Path(url.database)
    return None


def _backup_database() -> None:
    """Back up the database before anything touches it.

    A failure is logged and swallowed: the app being available matters more
    than one missing snapshot.
    """
    database = _database_file()
    if database is None:
        return
    try:
        backup = backup_database(database, Config.BACKUP_DIR, Config.BACKUP_KEEP)
    except Exception:
        logger.exception("Database backup failed; starting anyway")
        return
    if backup is None:
        logger.info("No database to back up yet")
    else:
        logger.info("Database backed up to %s", backup)


def main() -> None:
    """Run the app as a long-lived local service.

    Creates the data folder, sets up logging, backs up the database, then
    builds the app (which applies pending migrations) and serves it on the
    loopback address only.
    """
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    configure_logging(Config.LOG_FILE)

    # Before create_app(), which runs the migrations: a bad migration then
    # always has a pre-upgrade snapshot to fall back on.
    _backup_database()

    app = create_app(Config)
    logger.info("Serving on http://%s:%s", Config.HOST, Config.PORT)
    serve(app, host=Config.HOST, port=Config.PORT)


if __name__ == "__main__":
    main()
