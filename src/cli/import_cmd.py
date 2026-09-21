import json
import sys
from pathlib import Path
from typing import TextIO

from sqlalchemy.orm import Session

from src.cli import commands, format as fmt
from src.cli.errors import UsageError, UsageParser
from src.services import events, importer
from src.services.errors import ValidationError


def _read(source : str) -> str:
    """Read the import document from a file, or from stdin for "-".

    Raises:
        UsageError: If the file can't be read.
    """
    if source == "-":
        return sys.stdin.read()
    try:
        return Path(source).read_text(encoding="utf-8")
    except OSError as error:
        raise UsageError(f"cannot read '{source}': {error.strerror}") from error


def _summary(result : importer.ImportResult) -> str:
    """Describe what an import created and reused."""
    verb = "Would create" if result.dry_run else "Created"
    return (f"{verb} {result.projects_created} project(s), {result.versions_created} version(s), "
            f"{result.tasks_created} task(s). "
            f"Reused {result.projects_reused} project(s), {result.versions_reused} version(s).")


def import_data(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus import <file|-> [--dry-run] [--text]`: import projects, versions and tasks.

    Args:
        session: Database session to use.
        args: Arguments after `import`.
        out: Stream receiving the summary.

    Raises:
        UsageError: If the command line is malformed or the file unreadable.
        ValidationError: If the content is not valid JSON.
        DomainError: If the import is refused; nothing is written.
    """
    parser = UsageParser(prog="nexus import", add_help=False)
    parser.add_argument("source")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--text", action="store_true")
    options = parser.parse_args(args)

    content = _read(options.source)
    if options.text:
        data = importer.parse_text(content)
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValidationError(f"invalid JSON: {error}") from error

    result = importer.apply(session, data, events.ACTOR_CLI, dry_run=options.dry_run)
    print(_summary(result), file=out)
    if not result.dry_run and result.created:
        print(fmt.section("Created", fmt.table(["KIND", "REF", "TITLE"], [list(row) for row in result.created])),
              file=out)


commands.COMMANDS["import"] = import_data
