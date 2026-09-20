import logging

import pytest

from src import main


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point the configuration at a temporary data folder and capture serve().

    Returns:
        A list that receives one (app, host, port) tuple per serve() call.
    """
    monkeypatch.setattr(main.Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main.Config, "DATABASE_URL", f"sqlite:///{tmp_path / 'data.db'}")
    monkeypatch.setattr(main.Config, "LOG_FILE", tmp_path / "app.log")
    monkeypatch.setattr(main.Config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(main.Config, "PORT", 9000)

    served = []
    monkeypatch.setattr(main, "serve", lambda app, host, port: served.append((app, host, port)))
    yield served

    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, "_nexus_handler", False)]:
        root.removeHandler(handler)
        handler.close()

def test_serves_on_loopback_and_configured_port(home):
    """The server binds to 127.0.0.1 on the configured port
    Given a configured port
    When running main
    Then serve() is called once with 127.0.0.1 and that port
    """
    main.main()

    [(app, host, port)] = home
    assert host == "127.0.0.1"
    assert port == 9000
    assert app.name == "src.app"

def test_first_start_creates_folder_log_and_database_without_backup(home, tmp_path):
    """First start sets everything up and has nothing to back up
    Given an empty data folder
    When running main
    Then the database and log exist and no backup was made
    """
    main.main()

    assert (tmp_path / "data.db").exists()
    assert (tmp_path / "app.log").exists()
    assert not (tmp_path / "backups").exists()

def test_second_start_backs_up_the_database(home, tmp_path):
    """Starting again backs up the existing database
    Given a database created by a first start
    When running main again
    Then one backup file exists
    """
    main.main()
    main.main()

    assert len(list((tmp_path / "backups").iterdir())) == 1

def test_backup_runs_before_the_app_is_created(home, monkeypatch):
    """The backup happens before the migrations that create_app applies
    Given backup and app creation both recorded
    When running main
    Then the backup comes first
    """
    calls = []
    monkeypatch.setattr(main, "_backup_database", lambda: calls.append("backup"))
    monkeypatch.setattr(main, "create_app", lambda config: calls.append("create_app"))

    main.main()

    assert calls == ["backup", "create_app"]

def test_failed_backup_does_not_prevent_serving(home, monkeypatch, caplog):
    """A backup error is logged and the server still starts
    Given a backup that raises
    When running main
    Then the error is logged and serve() is still called
    """
    (main.Config.DATA_DIR / "data.db").write_text("not a database" * 100)
    def failing_backup(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(main, "backup_database", failing_backup)
    monkeypatch.setattr(main, "create_app", lambda config: object())

    with caplog.at_level(logging.ERROR):
        main.main()

    assert "backup failed" in caplog.text.lower()
    assert len(home) == 1

def test_no_backup_for_in_memory_database(home, monkeypatch):
    """A database that isn't a file is not backed up
    Given an in-memory database URL
    When running main
    Then no backup is attempted
    """
    monkeypatch.setattr(main.Config, "DATABASE_URL", "sqlite:///:memory:")
    attempts = []
    monkeypatch.setattr(main, "backup_database", lambda *a, **k: attempts.append(a))
    monkeypatch.setattr(main, "create_app", lambda config: object())

    main.main()

    assert not attempts
