from importlib import metadata
from typing import TextIO

from sqlalchemy.orm import Session

from src.cli import commands, format as fmt
from src.cli.errors import UsageError
from src.services.resolve import Target, resolve_version
from src.models.task import Task
from src.models.version import Version
from src.services import events, projects, tasks, versions


def _date(value : object) -> str | None:
    """Format a date or datetime for display, keeping only the day."""
    return value.strftime("%Y-%m-%d") if value else None


def _no_arguments(args : list[str], reference : str) -> None:
    """Refuse leftover arguments after a reference that takes none.

    Raises:
        UsageError: If any argument is left.
    """
    if args:
        raise UsageError(f"unexpected argument after '{reference}'")


# -----------------------------------------------------------------------------
# Lists
# -----------------------------------------------------------------------------

def show_app_version(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus version`: print the application version."""
    _no_arguments(args, "version")
    try:
        number = metadata.version("nexus")
    except metadata.PackageNotFoundError:
        number = "unknown"
    print(f"nexus {number}", file=out)


def list_tasks(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus tasks`: every task, oldest first."""
    _no_arguments(args, "tasks")
    rows = [[t.ref, t.state.name, t.project.key if t.project else "-",
             t.version.number if t.version else "-", t.title]
            for t in tasks.list(session)]
    print(fmt.table(["REF", "STATE", "PROJECT", "VERSION", "TITLE"], rows), file=out)


def list_versions(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus versions`: every version of every project."""
    _no_arguments(args, "versions")
    rows = [[v.ref, v.project.key, v.number, v.status.name, v.title]
            for v in versions.list_all(session)]
    print(fmt.table(["REF", "PROJECT", "NUMBER", "STATUS", "TITLE"], rows), file=out)


def list_projects(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus projects`: every active project."""
    _no_arguments(args, "projects")
    rows = [[p.key, p.status.name, p.name] for p in projects.list(session)]
    print(fmt.table(["KEY", "STATUS", "NAME"], rows), file=out)


# -----------------------------------------------------------------------------
# Details
# -----------------------------------------------------------------------------

def _version_rows(items : list[Version]) -> str:
    """Table of a project's versions."""
    return fmt.table(["REF", "NUMBER", "STATUS", "TITLE"],
                     [[v.ref, v.number, v.status.name, v.title] for v in items])


def _task_rows(items : list[Task]) -> str:
    """Table of a version's tasks."""
    return fmt.table(["REF", "STATE", "SIZE", "TITLE"],
                     [[t.ref, t.state.name, t.size or "-", t.title] for t in items])


def show_version(session : Session, version : Version, out : TextIO) -> None:
    """Print a version: its fields, its tasks and its definition of done."""
    criteria = version.definition_of_done
    checked = sum(1 for c in criteria if c.done)
    print(fmt.detail([("Ref", version.ref),
                      ("Project", version.project.key),
                      ("Version", version.number),
                      ("Title", version.title),
                      ("Status", version.status.name),
                      ("Goal", version.goal),
                      ("Target", _date(version.target_date)),
                      ("Released", _date(version.released_at))]), file=out)
    print(fmt.section("Tasks", _task_rows(versions.list_tasks(session, version.id))), file=out)
    dod = "\n".join(f"[{'x' if c.done else ' '}] {c.description}" for c in criteria)
    print(fmt.section(f"Definition of done ({checked}/{len(criteria)})", dod or "(none)"), file=out)


# -----------------------------------------------------------------------------
# Version actions
# -----------------------------------------------------------------------------

def _criterion_id(version : Version, number : str) -> int:
    """Id of a version's criterion given its number, counted from 1.

    Raises:
        UsageError: If the number is not an integer in range.
    """
    criteria = version.definition_of_done
    if not number.isdigit() or not 1 <= int(number) <= len(criteria):
        raise UsageError(f"criterion number must be between 1 and {len(criteria)}")
    return criteria[int(number) - 1].id


def _check(session : Session, version : Version, args : list[str], done : bool) -> None:
    """Check or uncheck the criterion numbered by the single argument."""
    if len(args) != 1:
        raise UsageError(f"'{'check' if done else 'uncheck'}' takes one criterion number")
    versions.set_criterion_done(session, _criterion_id(version, args[0]), done, actor=events.ACTOR_CLI)


def _add_criterion(session : Session, version : Version, args : list[str]) -> None:
    """Append a criterion whose text is the arguments joined by spaces."""
    if not args:
        raise UsageError("'add-criterion' takes the criterion text")
    versions.add_criterion(session, version.id, " ".join(args), actor=events.ACTOR_CLI)


def _edit_criterion(session : Session, version : Version, args : list[str]) -> None:
    """Change the text of the criterion numbered by the first argument to the rest, joined by spaces."""
    if len(args) < 2:
        raise UsageError("'edit-criterion' takes a criterion number and its new text")
    versions.update_criterion(session, _criterion_id(version, args[0]), " ".join(args[1:]), actor=events.ACTOR_CLI)


def _remove_criterion(session : Session, version : Version, args : list[str]) -> None:
    """Delete the criterion numbered by the single argument."""
    if len(args) != 1:
        raise UsageError("'remove-criterion' takes one criterion number")
    versions.delete_criterion(session, _criterion_id(version, args[0]), actor=events.ACTOR_CLI)


def _change_status(action, word : str):
    """A version action that runs one status change, e.g. versions.start, with no argument."""
    def run(session : Session, version : Version, args : list[str]) -> None:
        _no_arguments(args, word)
        action(session, version.id, actor=events.ACTOR_CLI)
    return run


# Actions after a version reference, by word: (session, version, arguments after the word).
VERSION_ACTIONS = {
    "check": lambda session, version, args: _check(session, version, args, True),
    "uncheck": lambda session, version, args: _check(session, version, args, False),
    "add-criterion": _add_criterion,
    "edit-criterion": _edit_criterion,
    "remove-criterion": _remove_criterion,
    "start": _change_status(versions.start, "start"),
    "release": _change_status(versions.release, "release"),
}


def _act_on_version(session : Session, version : Version, args : list[str], out : TextIO) -> None:
    """Run the action named by args[0] on a version, if any, then show the version.

    Raises:
        UsageError: If args[0] is not a version action.
    """
    if args:
        action = VERSION_ACTIONS.get(args[0])
        if action is None:
            raise UsageError(f"unknown version action '{args[0]}'")
        action(session, version, args[1:])
    show_version(session, version, out)


def _view_project(session : Session, target : Target, args : list[str], out : TextIO) -> None:
    """`nexus <project> [<version> [<action>]]`: project detail, or one of its versions."""
    project = target.entity
    if args:
        _act_on_version(session, resolve_version(session, project.key, args[0]), args[1:], out)
        return
    print(fmt.detail([("Key", project.key),
                      ("Name", project.name),
                      ("Status", project.status.name),
                      ("Description", project.description)]), file=out)
    print(fmt.section("Versions", _version_rows(versions.list(session, project.key))), file=out)


def _view_version(session : Session, target : Target, args : list[str], out : TextIO) -> None:
    """`nexus <version ref> [<action>]`: version detail, after an optional action."""
    _act_on_version(session, target.entity, args, out)


def _view_task(session : Session, target : Target, args : list[str], out : TextIO) -> None:
    """`nexus <task ref>`: task detail."""
    task = target.entity
    _no_arguments(args, task.ref)
    print(fmt.detail([("Ref", task.ref),
                      ("Title", task.title),
                      ("State", task.state.name),
                      ("Project", task.project.key if task.project else None),
                      ("Version", task.version.number if task.version else None),
                      ("Context", task.context),
                      ("Size", task.size),
                      ("Blocked", task.blocked_reason),
                      ("Created", _date(task.created_at)),
                      ("Closed", _date(task.closed_at))]), file=out)
    if task.body:
        print(fmt.section("Description", task.body), file=out)


commands.COMMANDS.update({
    "version": show_app_version,
    "tasks": list_tasks,
    "versions": list_versions,
    "projects": list_projects,
})
commands.VIEWERS.update({
    "project": _view_project,
    "version": _view_version,
    "task": _view_task,
})
