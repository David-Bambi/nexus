import logging
import sqlite3
from contextlib import closing

import pytest

from src.app import UnsupportedDatabaseError, create_app
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
            "INSERT INTO task (ref, kind, title, state, position, created_at, updated_at) "
            "VALUES ('t-drp', 'TASK', 'Dropped', 'CANCELLED', 0, '2026-09-21', '2026-09-21')")


def test_migrated_database_has_the_2_0_tables(tmp_path):
    """A fresh database gets the 2.0 schema, without versions
    Given an empty database file
    When the app is created
    Then the project, task, tag and event tables exist, and no version table
    """
    database = tmp_path / "data.db"
    create_app(_config_for(database))
    tables = _tables(database)
    assert {"project", "task", "tag", "task_tag", "event"} <= tables
    assert "version" not in tables
    assert "definition_of_done_criterion" not in tables


def test_deleted_ids_are_never_reused(tmp_path):
    """A deleted row's id is not handed out again
    Given a migrated database where the newest task was deleted
    When inserting a new task
    Then it gets a new id
    """
    database = tmp_path / "data.db"
    create_app(_config_for(database))
    insert = ("INSERT INTO task (ref, kind, title, state, position, created_at, updated_at) "
              "VALUES (?, 'TASK', 'T', 'INBOX', 0, '2026-11-19', '2026-11-19')")
    with closing(sqlite3.connect(database)) as connection:
        first = connection.execute(insert, ("t-aaa",)).lastrowid
        connection.execute("DELETE FROM task WHERE id = ?", (first,))
        second = connection.execute(insert, ("t-bbb",)).lastrowid
    assert second != first


def test_a_1_x_database_is_refused(tmp_path):
    """A database stamped by Nexus 1.x is refused with a clear error
    Given a database whose migration is the last 1.x one
    When the app is created
    Then UnsupportedDatabaseError is raised and the database is left alone
    """
    database = tmp_path / "data.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('e8b3f1c9a627')")
        connection.commit()

    with pytest.raises(UnsupportedDatabaseError, match="Upgrade from 1.x"):
        create_app(_config_for(database))
    assert _tables(database) == {"alembic_version"}


def test_restarting_on_a_2_0_database_is_accepted(tmp_path):
    """A database already at the 2.0 schema starts again without error
    Given a database migrated once
    When the app is created a second time
    Then no error is raised
    """
    database = tmp_path / "data.db"
    create_app(_config_for(database))
    create_app(_config_for(database))
