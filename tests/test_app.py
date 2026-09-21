import logging
import sqlite3
from contextlib import closing

from src.app import create_app
from src.config import Config
from src.logging_config import configure_logging


def _config_for(database_path):
    """Return a Config subclass (migrations enabled) using the given database file."""
    class FileConfig(Config):
        DATABASE_URL = f"sqlite:///{database_path}"
    return FileConfig

def _tables(database_path):
    """Return the table names of a SQLite file."""
    with closing(sqlite3.connect(database_path)) as connection:
        return {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

def test_missing_database_folder_is_created(tmp_path):
    """First start creates the database folder and migrates into it
    Given a database path inside folders that don't exist
    When creating the app
    Then the folders and the migrated database exist
    """
    database = tmp_path / "home" / ".nexus" / "data.db"

    create_app(_config_for(database))

    assert {"project", "task", "event"} <= _tables(database)

def test_migrates_the_configured_database_only(tmp_path, monkeypatch):
    """The app migrates the database from its config, not the default one
    Given the default database location pointing to another file
    When creating the app with an explicit database
    Then only the explicit database is created
    """
    default = tmp_path / "default.db"
    monkeypatch.setattr(Config, "DATABASE_URL", f"sqlite:///{default}")
    explicit = tmp_path / "explicit.db"

    create_app(_config_for(explicit))

    assert explicit.exists()
    assert not default.exists()

def test_creating_the_app_keeps_logging_configuration(tmp_path):
    """Running migrations at startup doesn't replace the app's log handlers
    Given logging configured on a file
    When creating the app, which runs the migrations
    Then a message logged afterwards still reaches that file
    """
    log_file = tmp_path / "app.log"
    configure_logging(log_file)
    try:
        create_app(_config_for(tmp_path / "data.db"))

        logging.getLogger("nexus").info("after startup")
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert "after startup" in log_file.read_text()
    finally:
        root = logging.getLogger()
        for handler in [h for h in root.handlers if getattr(h, "_nexus_handler", False)]:
            root.removeHandler(handler)
            handler.close()


def test_migrated_database_accepts_cancelled_tasks(tmp_path):
    """The migrated task table accepts the cancelled state
    Given a freshly migrated database
    When inserting a cancelled task
    Then the insert succeeds
    """
    database = tmp_path / "data.db"
    create_app(_config_for(database))
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO task (title, state, position, created_at, updated_at) "
            "VALUES ('Dropped', 'CANCELLED', 0, '2026-09-21', '2026-09-21')")
