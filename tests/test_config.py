import importlib
from pathlib import Path

import pytest

import src.config

# Environment variables that change the configuration.
_ENV_VARS = ("NEXUS_HOME", "NEXUS_DATABASE_URL", "NEXUS_PORT", "NEXUS_HOST")


@pytest.fixture
def load_config(monkeypatch):
    """Reload src.config under a controlled environment and return its Config.

    Every configuration variable is cleared first; pass the ones to set.
    The module is reloaded again on teardown so later tests see the real
    environment.
    """
    def _load(**env):
        for name in _ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(src.config).Config

    yield _load
    monkeypatch.undo()
    importlib.reload(src.config)


def test_defaults(load_config):
    """Default configuration lives under ~/.nexus
    Given no configuration variable
    When loading the configuration
    Then every path is under ~/.nexus and the server uses 127.0.0.1:8765
    """
    config = load_config()
    home = Path.home() / ".nexus"

    assert config.DATA_DIR == home
    assert config.DATABASE_URL == f"sqlite:///{home / 'data.db'}"
    assert config.LOG_FILE == home / "app.log"
    assert config.BACKUP_DIR == home / "backups"
    assert config.BACKUP_KEEP == 14
    assert config.HOST == "127.0.0.1"
    assert config.PORT == 8765

def test_nexus_home_moves_every_path(load_config, tmp_path):
    """NEXUS_HOME relocates the database, log and backups
    Given NEXUS_HOME set to a folder
    When loading the configuration
    Then the database, log and backup paths are inside it
    """
    config = load_config(NEXUS_HOME=str(tmp_path))

    assert config.DATA_DIR == tmp_path
    assert config.DATABASE_URL == f"sqlite:///{tmp_path / 'data.db'}"
    assert config.LOG_FILE == tmp_path / "app.log"
    assert config.BACKUP_DIR == tmp_path / "backups"

def test_nexus_home_expands_tilde(load_config):
    """NEXUS_HOME accepts a path starting with ~
    Given NEXUS_HOME set to '~/somewhere'
    When loading the configuration
    Then the data folder is under the user's home directory
    """
    config = load_config(NEXUS_HOME="~/somewhere")
    assert config.DATA_DIR == Path.home() / "somewhere"

def test_database_url_overrides_home(load_config, tmp_path):
    """NEXUS_DATABASE_URL wins over the default database location
    Given both NEXUS_HOME and NEXUS_DATABASE_URL
    When loading the configuration
    Then the database URL is the explicit one, the other paths follow NEXUS_HOME
    """
    config = load_config(NEXUS_HOME=str(tmp_path), NEXUS_DATABASE_URL="sqlite:///custom.db")

    assert config.DATABASE_URL == "sqlite:///custom.db"
    assert config.LOG_FILE == tmp_path / "app.log"

def test_port_is_configurable(load_config):
    """NEXUS_PORT changes the port, as an integer
    Given NEXUS_PORT set to 9000
    When loading the configuration
    Then the port is the integer 9000
    """
    assert load_config(NEXUS_PORT="9000").PORT == 9000

def test_host_ignores_environment(load_config):
    """The host can't be changed by configuration
    Given NEXUS_HOST set to 0.0.0.0
    When loading the configuration
    Then the host is still 127.0.0.1
    """
    assert load_config(NEXUS_HOST="0.0.0.0").HOST == "127.0.0.1"

def test_test_config_uses_memory_database(load_config):
    """TestConfig keeps the in-memory database whatever the environment
    Given NEXUS_DATABASE_URL pointing to a file
    When loading TestConfig
    Then its database is in memory
    """
    load_config(NEXUS_DATABASE_URL="sqlite:///custom.db")
    assert src.config.TestConfig.DATABASE_URL == "sqlite:///:memory:"
    assert src.config.TestConfig.TESTING
