from typing import TextIO

from sqlalchemy.orm import Session

from src.cli import commands
from src.cli.errors import UsageError, UsageParser
from src.models.task import TaskState
from src.services import events, tasks
from src.services.resolve import resolve


# States `nexus state` can move an item to.
_STATES = ["INBOX", "REFINED", "DOING", "WAITING", "DONE", "CANCELLED"]


def change_state(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus state <ref> <STATE> [--reason R]`: move a feature or task to a
    state, chaining the lifecycle steps on the way.

    Args:
        session: Database session to use.
        args: Arguments after `state`.
        out: Stream receiving the confirmation.

    Raises:
        UsageError: If the command line is malformed or the reference isn't
            a feature or task.
        DomainError: If the move is refused (e.g. waiting without a reason).
    """
    parser = UsageParser(prog="nexus state", add_help=False)
    parser.add_argument("ref")
    parser.add_argument("state", type=str.upper, choices=_STATES)
    parser.add_argument("-r", "--reason", default="")
    options = parser.parse_args(args)

    target = resolve(session, options.ref)
    if target.kind not in ("feature", "task"):
        raise UsageError(f"'{options.ref}' isn't a feature or a task")
    task = tasks.change_state(session, target.entity.id, TaskState[options.state], options.reason,
                              actor=events.ACTOR_CLI)
    print(f"{task.kind.name.lower().capitalize()} {task.ref} is now {task.state.name.lower()}: {task.title}",
          file=out)


commands.COMMANDS["state"] = change_state
