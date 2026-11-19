from importlib import metadata
from typing import TextIO

from sqlalchemy.orm import Session

from src.cli import commands, format as fmt
from src.cli.errors import UsageError
from src.services.resolve import Target
from src.models.task import TaskKind
from src.services import projects, tasks, versioning, views


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
    """`nexus projects`: every active project, each followed by its active
    subprojects, indented."""
    _no_arguments(args, "projects")
    listed = projects.list(session)
    shown = {p.id for p in listed}

    def row(project, indent=""):
        return [indent + project.key, project.ref or "-", versioning.label(project),
                project.status.name, project.name]

    rows = []
    for root in (p for p in listed if p.parent_id is None):
        rows.append(row(root))
        rows.extend(row(sub, "  ") for sub in root.subprojects if sub.id in shown)
    print(fmt.table(["KEY", "REF", "VERSION", "STATUS", "NAME"], rows), file=out)


# -----------------------------------------------------------------------------
# Details
# -----------------------------------------------------------------------------

def _directory_label(project) -> str | None:
    """The project's directory, or its parent's marked as inherited; None if neither."""
    if project.directory:
        return project.directory
    inherited = projects.directory_of(project)
    return f"{inherited} (from {project.parent.key})" if inherited else None


def _view_project(session : Session, target : Target, args : list[str], out : TextIO) -> None:
    """`nexus <project> [--all]` or `nexus <subproject ref> [--all]`: project
    detail, its criteria for the next major version, its subprojects and its
    work tree. Done and cancelled items are shown only with --all."""
    project = target.entity
    name = project.ref or project.key
    include_closed = args == ["--all"]
    if not include_closed:
        _no_arguments(args, name)
    print(fmt.detail([("Key", project.key),
                      ("Ref", project.ref),
                      ("Name", project.name),
                      ("Parent", project.parent.key if project.parent else None),
                      ("Status", project.status.name),
                      ("Version", versioning.label(project)),
                      ("Directory", _directory_label(project)),
                      ("Description", project.description)]), file=out)
    if project.criteria:
        lines = [f"[{'x' if c.done else ' '}] {number}. {c.text}"
                 for number, c in enumerate(project.criteria, start=1)]
        print(fmt.section(f"Criteria for {project.version_major + 1}.0", "\n".join(lines)), file=out)
    if project.subprojects:
        rows = [[sub.ref, sub.key, versioning.label(sub), sub.status.name, sub.name] for sub in project.subprojects]
        print(fmt.section("Subprojects", fmt.table(["REF", "KEY", "VERSION", "STATUS", "NAME"], rows)), file=out)
    title = "Work" if include_closed else "Work (open items; --all shows done and cancelled)"
    print(fmt.section(title, fmt.tree(views.project_tree(project, include_closed=include_closed))), file=out)


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
                      ("Released", f"v{task.released_in}" if task.released_in else None),
                      ("Blocked", task.blocked_reason),
                      ("Created", _date(task.created_at)),
                      ("Closed", _date(task.closed_at))]), file=out)
    if task.body:
        print(fmt.section("Description", task.body), file=out)
    if task.kind is TaskKind.FEATURE:
        print(fmt.section("Children", fmt.tree(views.item_tree(task, include_closed=True))), file=out)


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
