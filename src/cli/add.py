import argparse
import sys
from typing import NoReturn, TextIO

from sqlalchemy.orm import Session

from src.cli import commands
from src.cli.errors import UsageError
from src.cli.resolve import resolve_version
from src.models.task import Task
from src.services import events, tasks
from src.services.errors import ValidationError


class _Parser(argparse.ArgumentParser):
    """Argument parser that reports mistakes as a UsageError instead of exiting."""

    def error(self, message : str) -> NoReturn:
        """Raise the parsing mistake as a UsageError."""
        raise UsageError(message)


def _task_parser() -> argparse.ArgumentParser:
    """Build the parser of `nexus add task`."""
    parser = _Parser(prog="nexus add task", add_help=False)
    parser.add_argument("project")
    parser.add_argument("version", nargs="?")
    parser.add_argument("-t", "--title")
    parser.add_argument("-b", "--body")
    parser.add_argument("-c", "--context")
    parser.add_argument("-s", "--size", choices=["XS", "S", "M", "L"])
    return parser


def _report(task : Task, out : TextIO) -> None:
    """Tell the user which task was created."""
    where = "inbox" if task.version_id is None else "planned"
    print(f"Created task {task.ref} ({where}): {task.title}", file=out)


def _require_title(title : str | None) -> str:
    """Return a usable title, asking for it on a terminal when it is missing.

    Args:
        title: The title given on the command line, if any.

    Returns:
        The stripped title.

    Raises:
        UsageError: If there is no title and nowhere to ask for one.
        ValidationError: If the title is empty.
    """
    if title is None:
        if not sys.stdin.isatty():
            raise UsageError("missing title (use --title)")
        title = input("Title: ")
    if not title.strip():
        raise ValidationError("The title must be specified.")
    return title.strip()


def add(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus add task <project> [<version>]`: create a task.

    Without a version the task lands in the project's inbox; with one it is
    planned into that version straight away.

    Args:
        session: Database session to use.
        args: Arguments after `add`.
        out: Stream receiving the confirmation.

    Raises:
        UsageError: If the command line is malformed.
        DomainError: If a service refuses the task.
    """
    if not args or args[0] != "task":
        raise UsageError("usage: nexus add task <project> [<version>] [--title T]")
    options = _task_parser().parse_args(args[1:])
    title = _require_title(options.title)

    if options.version is None:
        task = tasks.create(session, title, project_key=options.project, body=options.body,
                            context=options.context, size=options.size, actor=events.ACTOR_CLI)
    else:
        version = resolve_version(session, options.project, options.version)
        task = tasks.create_in_version(session, version.id, title, context=options.context,
                                       size=options.size, body=options.body, actor=events.ACTOR_CLI)
    _report(task, out)


def capture(session : Session, text : str, out : TextIO) -> None:
    """`nexus "<description>"`: capture a task into the inbox.

    Args:
        session: Database session to use.
        text: The task title, as typed.
        out: Stream receiving the confirmation.

    Raises:
        ValidationError: If the text is empty.
    """
    title = _require_title(text)
    _report(tasks.capture(session, title, actor=events.ACTOR_CLI), out)


commands.COMMANDS["add"] = add
