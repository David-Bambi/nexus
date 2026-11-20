import sys
from typing import Callable, TextIO

from sqlalchemy.orm import Session

from src.cli import add, commands, export_cmd, import_cmd, state, views  # noqa: F401  (register commands)
from src.cli.errors import UsageError
from src.services.resolve import resolve
from src.cli.session import open_session
from src.services.errors import DomainError

# Shown when nexus runs with no arguments or a wrong command line.
USAGE = """usage: nexus <command> | <reference>

  nexus version            app version
  nexus tasks              all features and tasks
  nexus projects           all projects, subprojects indented, with versions
  nexus <project> [--all]  project: version, criteria, subprojects, work tree
  nexus <subproject> [--all]
  nexus <feature|task>     feature or task detail (a feature: its children)
  nexus add task|feature <project> [--parent f-ref] [--title T] [--body B]
                           [--context C] [--size S]   add to the tree, in inbox
  nexus state <feature|task> <STATE> [--reason R]
                           move to INBOX, REFINED, DOING, WAITING, DONE or
                           CANCELLED, through each step on the way
  nexus "<description>"     capture a task into the inbox
  nexus import <file|->
  nexus export features [-o FILE]   feature export for metrique (JSON)

A reference is a project key, a subproject ref (s-4k2), a feature ref
(f-4k2) or a task ref (t-4k2)."""

# Exit codes.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def dispatch(session : Session, argv : list[str], out : TextIO) -> None:
    """Run one command line against a session.

    Args:
        session: Database session to use.
        argv: Arguments after the program name.
        out: Stream receiving the output.

    Raises:
        UsageError: If the command line is empty or malformed.
        DomainError: If a service refuses the request.
    """
    if not argv:
        raise UsageError("missing command")

    word = argv[0]
    if word in commands.COMMANDS:
        commands.COMMANDS[word](session, argv[1:], out)
        return

    # A lone argument that reads as a sentence is a task to capture.
    if len(argv) == 1 and (not word.strip() or any(c.isspace() for c in word)):
        add.capture(session, word, out)
        return

    target = resolve(session, word)
    viewer = commands.VIEWERS.get(target.kind)
    if viewer is None:
        raise UsageError(f"cannot show a {target.kind}")
    viewer(session, target, argv[1:], out)


def main(argv : list[str] | None = None,
         session_factory : Callable[[], Session] = open_session,
         out : TextIO | None = None,
         err : TextIO | None = None) -> int:
    """Entry point of the `nexus` command.

    Args:
        argv: Arguments after the program name (defaults to sys.argv[1:]).
        session_factory: Builds the database session; tests inject their own.
        out: Output stream (defaults to sys.stdout).
        err: Error stream (defaults to sys.stderr).

    Returns:
        The exit code: 0 on success, 1 when a service refuses the request,
        2 on a wrong command line.
    """
    argv = sys.argv[1:] if argv is None else argv
    out = out or sys.stdout
    err = err or sys.stderr

    if not argv:
        print(USAGE, file=out)
        return EXIT_OK

    session = session_factory()
    try:
        dispatch(session, argv, out)
    except UsageError as error:
        print(f"error: {error}\n\n{USAGE}", file=err)
        return EXIT_USAGE
    except DomainError as error:
        print(f"error: {error}", file=err)
        return EXIT_ERROR
    finally:
        session.close()
    return EXIT_OK
