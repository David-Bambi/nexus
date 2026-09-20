from sqlalchemy import text

from src.db import get_engine


def _journal_mode(engine):
    """Return the journal mode SQLite reports on a fresh connection."""
    with engine.connect() as connection:
        return connection.execute(text("PRAGMA journal_mode")).scalar()

def test_file_database_uses_wal(tmp_path):
    """A file-based SQLite database runs in WAL mode
    Given an engine on a database file
    When reading its journal mode
    Then it is wal
    """
    engine = get_engine(f"sqlite:///{tmp_path / 'data.db'}")
    assert _journal_mode(engine) == "wal"

def test_wal_persists_for_other_connections(tmp_path):
    """WAL stays on for connections opened without the engine's listener
    Given a database file first opened through get_engine
    When opening it again with a plain engine
    Then its journal mode is still wal
    """
    path = tmp_path / "data.db"
    _journal_mode(get_engine(f"sqlite:///{path}"))

    from sqlalchemy import create_engine
    assert _journal_mode(create_engine(f"sqlite:///{path}")) == "wal"

def test_memory_database_is_left_alone():
    """An in-memory database keeps its default journal mode
    Given an engine on an in-memory database
    When reading its journal mode
    Then it is not wal
    """
    assert _journal_mode(get_engine("sqlite:///:memory:")) != "wal"
