import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

# Backup file names: data-YYYYmmdd-HHMMSS.db. Only files matching this are
# ever pruned, so anything else a user drops in the folder is left alone.
_BACKUP_NAME = re.compile(r"^data-\d{8}-\d{6}\.db$")


def backup_database(db_path : Path, backup_dir : Path, keep : int, now : datetime | None = None) -> Path | None:
    """Copy a SQLite database into a timestamped backup, then prune old ones.

    Uses SQLite's online backup API rather than copying the file: in WAL
    mode a plain copy can miss data still sitting in the -wal file.

    Args:
        db_path: The database file to back up.
        backup_dir: Folder receiving the backups; created if missing.
        keep: Number of most recent backups to keep.
        now: Time used for the file name (defaults to the current time).
            Two backups taken within the same second share a name, the
            second replaces the first.

    Returns:
        The path of the new backup, or None if the database file doesn't
        exist yet (e.g. first run).

    Raises:
        sqlite3.Error: If the database can't be read as SQLite. No partial
            backup file is left behind.
    """
    if not db_path.exists():
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"data-{stamp}.db"

    try:
        with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
    except sqlite3.Error:
        target.unlink(missing_ok=True)
        raise

    prune(backup_dir, keep)
    return target


def prune(backup_dir : Path, keep : int) -> None:
    """Delete the oldest backups, keeping the most recent ones.

    Args:
        backup_dir: Folder holding the backups.
        keep: Number of most recent backups to keep. Files that don't
            follow the backup naming scheme are never touched.
    """
    backups = sorted(
        (path for path in backup_dir.iterdir() if _BACKUP_NAME.match(path.name)),
        reverse=True,
    )
    for path in backups[keep:]:
        path.unlink()
