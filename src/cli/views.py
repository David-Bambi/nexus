from importlib import metadata
from typing import TextIO

from sqlalchemy.orm import Session

from src.cli import commands, format as fmt
from src.cli.errors import UsageError
from src.services.resolve import Target
from src.services import projects, tasks


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
    """`nexus tasks`: every feature and task, oldest first."""
    _no_arguments(args, "tasks")
    rows = [[t.ref, t.state.name, t.project.key if t.project else "-",
             t.parent.ref if t.parent else "-", t.title]
            for t in tasks.list(session)]
    print(fmt.table(["REF", "STATE", "PROJECT", "PARENT", "TITLE"], rows), file=out)


def list_projects(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus projects`: every active project."""
    _no_arguments(args, "projects")
    rows = [[p.key, p.status.name, p.name] for p in projects.list(session)]
    print(fmt.table(["KEY", "STATUS", "NAME"], rows), file=out)


# -----------------------------------------------------------------------------
# Details
# -----------------------------------------------------------------------------

def _view_project(session : Session, target : Target, args : list[str], out : TextIO) -> None:
    """`nexus <project>` or `nexus <subproject ref>`: project detail and its subprojects."""
    project = target.entity
    _no_arguments(args, project.ref or project.key)
    print(fmt.detail([("Key", project.key),
                      ("Ref", project.ref),
                      ("Name", project.name),
                      ("Parent", project.parent.key if project.parent else None),
                      ("Status", project.status.name),
                      ("Description", project.description)]), file=out)
    if project.subprojects:
        rows = [[sub.ref, sub.key, sub.status.name, sub.name] for sub in project.subprojects]
        print(fmt.section("Subprojects", fmt.table(["REF", "KEY", "STATUS", "NAME"], rows)), file=out)


def _view_task(session : Session, target : Target, args : list[str], out : TextIO) -> None:
    """`nexus <feature or task ref>`: feature or task detail."""
    task = target.entity
    _no_arguments(args, task.ref)
    print(fmt.detail([("Ref", task.ref),
                      ("Title", task.title),
                      ("Kind", task.kind.name),
                      ("State", task.state.name),
                      ("Project", task.project.key if task.project else None),
                      ("Parent", task.parent.ref if task.parent else None),
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
    "projects": list_projects,
})
commands.VIEWERS.update({
    "project": _view_project,
    "subproject": _view_project,
    "feature": _view_task,
    "task": _view_task,
})
