import logging
from logging.handlers import RotatingFileHandler

import pytest

from src import logging_config
from src.logging_config import configure_logging


@pytest.fixture(autouse=True)
def clean_root_logger():
    """Remove the handlers configure_logging installed and restore the root level."""
    root = logging.getLogger()
    level = root.level
    yield
    for handler in [h for h in root.handlers if getattr(h, logging_config._MARKER, False)]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)

def _installed(root):
    """Return the handlers installed by configure_logging."""
    return [h for h in root.handlers if getattr(h, logging_config._MARKER, False)]

def test_message_reaches_the_file(tmp_path):
    """Logged messages are written to the log file
    Given logging configured on a file
    When any logger emits an info message
    Then the message, its level and logger name are in the file
    """
    log_file = tmp_path / "app.log"
    configure_logging(log_file)

    logging.getLogger("waitress").info("hello from the server")
    for handler in _installed(logging.getLogger()):
        handler.flush()

    line = log_file.read_text()
    assert "hello from the server" in line
    assert "INFO" in line
    assert "waitress" in line

def test_log_folder_is_created(tmp_path):
    """The log file's folder is created when missing
    Given a log path inside a folder that doesn't exist
    When configuring logging
    Then the folder exists afterwards
    """
    configure_logging(tmp_path / "nested" / "app.log")
    assert (tmp_path / "nested").is_dir()

def test_file_rotates_at_one_megabyte_keeping_five(tmp_path):
    """The log file rotates at 1 MB and keeps 5 old files
    Given logging configured on a file
    When reading the installed file handler
    Then it is a rotating handler set to 1 MB and 5 backups
    """
    configure_logging(tmp_path / "app.log")

    [handler] = [h for h in _installed(logging.getLogger()) if isinstance(h, RotatingFileHandler)]
    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 5

def test_second_call_does_not_duplicate_handlers(tmp_path):
    """Configuring twice leaves one file handler and one stderr handler
    Given logging configured twice
    When counting the installed handlers
    Then there are two, and a message is written once
    """
    log_file = tmp_path / "app.log"
    configure_logging(log_file)
    configure_logging(log_file)

    logging.getLogger("nexus").info("only once")
    for handler in _installed(logging.getLogger()):
        handler.flush()

    assert len(_installed(logging.getLogger())) == 2
    assert log_file.read_text().count("only once") == 1

def test_other_handlers_are_left_alone(tmp_path):
    """Configuring logging doesn't remove handlers added by someone else
    Given a handler already on the root logger
    When configuring logging twice
    Then that handler is still there
    """
    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    try:
        configure_logging(tmp_path / "app.log")
        configure_logging(tmp_path / "app.log")
        assert foreign in root.handlers
    finally:
        root.removeHandler(foreign)
