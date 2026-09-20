import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import pytest

from src.backup import backup_database, prune


def _make_database(path, rows=("first",)):
    """Create a database file with one table holding the given rows."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE note (body TEXT)")
        connection.executemany("INSERT INTO note VALUES (?)", [(r,) for r in rows])
        connection.commit()

def _rows(path):
    """Return the bodies stored in a database file's note table."""
    with closing(sqlite3.connect(path)) as connection:
        return [body for (body,) in connection.execute("SELECT body FROM note ORDER BY rowid")]

def test_backup_is_a_valid_copy(tmp_path):
    """Backup produces a readable database with the same data
    Given a database with two rows
    When backing it up
    Then the backup file holds the same two rows
    """
    db = tmp_path / "data.db"
    _make_database(db, rows=("first", "second"))

    backup = backup_database(db, tmp_path / "backups", keep=14)

    assert _rows(backup) == ["first", "second"]

def test_backup_includes_rows_still_in_the_wal(tmp_path):
    """Backup captures data not yet checkpointed into the main file
    Given a WAL database with a row committed but still in the -wal file
    When backing it up
    Then the backup holds that row
    """
    db = tmp_path / "data.db"
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE note (body TEXT)")
    writer.execute("INSERT INTO note VALUES ('in the wal')")
    writer.commit()
    try:
        assert (tmp_path / "data.db-wal").stat().st_size > 0

        backup = backup_database(db, tmp_path / "backups", keep=14)

        assert _rows(backup) == ["in the wal"]
    finally:
        writer.close()

def test_backup_name_is_timestamped_and_folder_created(tmp_path):
    """Backup is named after the time and creates its folder
    Given a database and a backup folder that doesn't exist
    When backing it up at a given time
    Then the file is data-<timestamp>.db inside the new folder
    """
    db = tmp_path / "data.db"
    _make_database(db)

    backup = backup_database(db, tmp_path / "backups", keep=14, now=datetime(2026, 9, 20, 8, 30, 5))

    assert backup == tmp_path / "backups" / "data-20260920-083005.db"

def test_missing_database_returns_none(tmp_path):
    """Backup of a database that doesn't exist yet does nothing
    Given no database file
    When backing it up
    Then None is returned and no backup folder is created
    """
    assert backup_database(tmp_path / "data.db", tmp_path / "backups", keep=14) is None
    assert not (tmp_path / "backups").exists()

def test_backup_prunes_to_the_newest(tmp_path):
    """Backup keeps only the most recent ones
    Given a database backed up 16 times, a minute apart
    When keeping 14
    Then only the 14 newest backups remain
    """
    db = tmp_path / "data.db"
    _make_database(db)
    start = datetime(2026, 9, 20, 8, 0, 0)

    for minute in range(16):
        backup_database(db, tmp_path / "backups", keep=14, now=start + timedelta(minutes=minute))

    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert len(names) == 14
    assert names[0] == "data-20260920-080200.db"
    assert names[-1] == "data-20260920-081500.db"

def test_prune_ignores_unrelated_files(tmp_path):
    """Prune never deletes files that aren't backups
    Given a folder with backups and other files
    When pruning down to one backup
    Then only the older backups are removed
    """
    folder = tmp_path / "backups"
    folder.mkdir()
    for name in ("data-20260920-080000.db", "data-20260920-090000.db", "notes.txt", "data-manual.db"):
        (folder / name).write_text("x")

    prune(folder, keep=1)

    assert sorted(p.name for p in folder.iterdir()) == ["data-20260920-090000.db", "data-manual.db", "notes.txt"]

def test_failed_backup_leaves_nothing_behind(tmp_path):
    """A backup of a file that isn't a database raises and leaves no file
    Given a file that isn't a SQLite database
    When backing it up
    Then a sqlite3 error is raised and the backup folder holds no file
    """
    db = tmp_path / "data.db"
    db.write_text("this is not a database" * 100)

    with pytest.raises(sqlite3.Error):
        backup_database(db, tmp_path / "backups", keep=14)

    assert not list((tmp_path / "backups").iterdir())
