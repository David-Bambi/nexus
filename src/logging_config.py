import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Size at which the log file is rotated, and how many old files are kept.
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 5

# Attribute set on the handlers installed here, so a second call can find
# and replace them without touching handlers added by anyone else.
_MARKER = "_nexus_handler"


def configure_logging(log_file : Path) -> None:
    """Send the application's logs to a rotating file and to stderr.

    Installs the handlers on the root logger, so the app, Flask and the
    server all log the same way. Safe to call more than once: handlers from
    a previous call are replaced, not duplicated.

    Args:
        log_file: Path of the log file; its folder is created if missing.
            Rotated at 1 MB, keeping 5 old files.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    stream_handler = logging.StreamHandler(sys.stderr)

    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _MARKER, False)]:
        root.removeHandler(handler)
        handler.close()

    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        setattr(handler, _MARKER, True)
        root.addHandler(handler)
    root.setLevel(logging.INFO)
