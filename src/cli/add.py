import argparse
import sys
from typing import TextIO

from sqlalchemy.orm import Session

from src.cli import commands
from src.cli.errors import UsageError, UsageParser
from src.models.task import Task, TaskKind
from src.services import events, tasks
from src.services.errors import ValidationError


# Kinds `nexus add` takes, mapped to the model's.
_KINDS = {"task": TaskKind.TASK, "feature": TaskKind.FEATURE}


def _task_parser(kind : str) -> argparse.ArgumentParser:
    """Build the parser of `nexus add task` or `nexus add feature`.

    Args:
        kind: "task" or "feature", for the usage message.
    """
    parser = UsageParser(prog=f"nexus add {kind}", add_help=False)
    parser.add_argument("project")
    parser.add_argument("-p", "--parent")
    parser.add_argument("-t", "--title")
    parser.add_argument("-b", "--body")
    parser.add_argument("-c", "--context")
    parser.add_argument("-s", "--size", choices=["XS", "S", "M", "L"])
    return parser


def _report(task : Task, out : TextIO) -> None:
    """Tell the user which item was created, and where."""
    status = task.state.name.lower()
    if task.project:
        status += f", {task.project.key}" + (f" > {task.parent.ref}" if task.parent else "")
    print(f"Created {task.kind.name.lower()} {task.ref} ({status}): {task.title}", file=out)


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
    """`nexus add task|feature <project> [--parent f-ref]`: add an item to a
    project's tree, already refined.

    Args:
        session: Database session to use.
        args: Arguments after `add`.
        out: Stream receiving the confirmation.

    Raises:
        UsageError: If the command line is malformed.
        DomainError: If a service refuses the item.
    """
    if not args or args[0] not in _KINDS:
        raise UsageError("usage: nexus add task|feature <project> [--parent f-ref] [--title T]")
    options = _task_parser(args[0]).parse_args(args[1:])
    title = _require_title(options.title)

    item = tasks.add_to_tree(session, title, project_key=options.project, parent_ref=options.parent,
                             kind=_KINDS[args[0]], body=options.body, context=options.context,
                             size=options.size, actor=events.ACTOR_CLI)
    _report(item, out)


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
