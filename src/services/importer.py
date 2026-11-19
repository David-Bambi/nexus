from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.models.project import Project
from src.services import projects, tasks
from src.services.errors import NotFoundError, ValidationError

# Sizes a task may take.
_SIZES = ("XS", "S", "M", "L")

# Fields each kind of entry accepts; anything else is reported as an error.
_DOCUMENT_FIELDS = {"projects", "tasks"}
_PROJECT_FIELDS = {"key", "name", "description"}
_TASK_FIELDS = {"title", "body", "context", "size"}
_LOOSE_TASK_FIELDS = _TASK_FIELDS | {"project"}


class ImportInvalid(ValidationError):
    """The import document breaks one or more rules; nothing was written."""

    def __init__(self, errors : list[str]):
        """Build the error from every problem found.

        Args:
            errors: One message per problem, each naming the offending entry.
        """
        self.errors = errors
        super().__init__(f"invalid import: {len(errors)} problem(s)\n" +
                         "\n".join(f"  - {error}" for error in errors))


@dataclass
class ImportResult:
    """What an import created or reused."""

    # True if nothing was written.
    dry_run: bool = False
    projects_created: int = 0
    projects_reused: int = 0
    tasks_created: int = 0
    # (kind, ref, title) for each item created, in creation
    # order; ref is None on a dry run, since nothing is stored.
    created: list = field(default_factory=list)


class _DeferredCommit:
    """Session stand-in whose commit only flushes.

    The services commit after each change; wrapping the session lets an
    import run many of them and still store or discard the lot at once.
    """

    def __init__(self, session : Session):
        """Wrap a session.

        Args:
            session: The real session, committed or rolled back by the caller.
        """
        self._session = session

    def commit(self) -> None:
        """Flush the pending changes without ending the transaction."""
        self._session.flush()

    def __getattr__(self, name : str) -> object:
        """Delegate everything else to the real session."""
        return getattr(self._session, name)


# -----------------------------------------------------------------------------
# Text input
# -----------------------------------------------------------------------------

def parse_text(text : str) -> dict:
    """Turn a plain-text list into an import document.

    Args:
        text: One task title per line; blank lines are skipped.

    Returns:
        A document with each line as a loose (inbox) task.
    """
    titles = [line.strip() for line in text.splitlines() if line.strip()]
    return {"tasks": [{"title": title} for title in titles]}


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

def _text(entry : dict, name : str, where : str, errors : list, required : bool = False) -> str | None:
    """Read a string field, reporting a wrong type or a missing required value.

    Args:
        entry: The entry holding the field.
        name: Field name.
        where: Label of the entry, for messages.
        errors: List receiving the problems found.
        required: Whether a missing or blank value is a problem.

    Returns:
        The stripped string, or None if absent, blank or of the wrong type.
    """
    value = entry.get(name)
    if value is not None and not isinstance(value, str):
        errors.append(f"{where}: '{name}' must be a string")
        return None
    value = value.strip() if value else None
    if required and not value:
        errors.append(f"{where}: '{name}' is required")
    return value or None


def _entries(container : dict, name : str, where : str, errors : list) -> list:
    """Read a list field made of objects, reporting anything else.

    Returns:
        The entries that are objects (paired with their index); empty if the
        field is absent or not a list.
    """
    value = container.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{where}: '{name}' must be a list")
        return []
    entries = []
    for index, entry in enumerate(value):
        if isinstance(entry, dict):
            entries.append((index, entry))
        else:
            errors.append(f"{where}: {name}[{index}] must be an object")
    return entries


def _unknown_fields(entry : dict, allowed : set, where : str, errors : list) -> None:
    """Report fields the format doesn't define (usually typos)."""
    for name in sorted(set(entry) - allowed):
        errors.append(f"{where}: unknown field '{name}'")


def _check_task(entry : dict, where : str, errors : list, loose : bool = False) -> None:
    """Check one task entry's fields."""
    _unknown_fields(entry, _LOOSE_TASK_FIELDS if loose else _TASK_FIELDS, where, errors)
    _text(entry, "title", where, errors, required=True)
    _text(entry, "body", where, errors)
    _text(entry, "context", where, errors)
    size = _text(entry, "size", where, errors)
    if size is not None and size not in _SIZES:
        errors.append(f"{where}: 'size' must be one of {', '.join(_SIZES)}")


def _project_exists(session : Session, key : str) -> bool:
    """Tell whether a project key is already taken.

    Args:
        session: Database session to use.
        key: Project key.
    """
    try:
        projects.get(session, key)
    except NotFoundError:
        return False
    return True


def validate(session : Session, data : object) -> list[str]:
    """Check an import document against the format and the current data.

    Every problem is collected, so a caller can fix them all in one go.

    Args:
        session: Database session to use (read only).
        data: The parsed document.

    Returns:
        One message per problem, each naming the offending entry; empty if
        the document can be applied.
    """
    errors = []
    if not isinstance(data, dict):
        return ["the document must be an object with 'projects' and/or 'tasks'"]
    _unknown_fields(data, _DOCUMENT_FIELDS, "document", errors)

    declared = set()
    for index, entry in _entries(data, "projects", "document", errors):
        where = f"projects[{index}]"
        _unknown_fields(entry, _PROJECT_FIELDS, where, errors)
        key = _text(entry, "key", where, errors, required=True)
        if key is None:
            continue
        where = f"{where} ('{key}')"
        if projects.is_reserved_key(key):
            errors.append(f"{where}: key is reserved")
        if key in declared:
            errors.append(f"{where}: project declared twice")
            continue
        declared.add(key)
        if not _project_exists(session, key):
            _text(entry, "name", where, errors, required=True)
        _text(entry, "description", where, errors)

    for index, entry in _entries(data, "tasks", "document", errors):
        where = f"tasks[{index}]"
        _check_task(entry, where, errors, loose=True)
        key = _text(entry, "project", where, errors)
        if key and key not in declared and not _project_exists(session, key):
            errors.append(f"{where}: project '{key}' doesn't exist")
    return errors


# -----------------------------------------------------------------------------
# Applying
# -----------------------------------------------------------------------------

def apply(session : Session, data : object, actor : str, dry_run : bool = False) -> ImportResult:
    """Import projects and tasks from a document.

    Projects are matched by their key: an existing one is reused and never
    overwritten, a missing one is created. Tasks are always created. Refs and
    ids in the document are not part of the format. The whole import is
    stored at once, or not at all.

    Args:
        session: Database session to use.
        data: The parsed document: {"projects": [{"key", "name",
            "description"}], "tasks": [{"title", "body", "context", "size",
            "project"}]}.
        actor: Who runs the import, recorded in the event log.
        dry_run: If True, run everything then discard it, so the result
            shows what would happen.

    Returns:
        An ImportResult of what was created or reused.

    Raises:
        ImportInvalid: If the document breaks any rule; nothing is written.
        DomainError: If a service refuses a change midway; nothing is written.
    """
    errors = validate(session, data)
    if errors:
        raise ImportInvalid(errors)

    result = ImportResult(dry_run=dry_run)
    deferred = _DeferredCommit(session)
    try:
        _create_projects(deferred, data, actor, result)
        for entry in data.get("tasks", []):
            _create_task(deferred, entry, entry.get("project"), actor, result)
    except Exception:
        session.rollback()
        raise
    if dry_run:
        session.rollback()
        result.created = [(kind, None, title) for kind, _, title in result.created]
    else:
        session.commit()
    return result


def _create_projects(session : _DeferredCommit, data : dict, actor : str, result : ImportResult) -> None:
    """Create each missing project, reuse the existing ones."""
    for entry in data.get("projects", []):
        key = entry["key"].strip()
        if session.query(Project).filter_by(key=key).first() is None:
            projects.create(session, key, entry["name"].strip(),
                            (entry.get("description") or "").strip() or None, actor=actor)
            result.projects_created += 1
        else:
            result.projects_reused += 1


def _create_task(session : _DeferredCommit, entry : dict, project_key : str | None,
                 actor : str, result : ImportResult) -> None:
    """Create one task in the inbox, in its project if it names one."""
    fields = {"body": (entry.get("body") or "").strip() or None,
              "context": (entry.get("context") or "").strip() or None,
              "size": (entry.get("size") or "").strip() or None}
    title = entry["title"].strip()
    task = tasks.create(session, title, project_key=project_key.strip() if project_key else None,
                        actor=actor, **fields)
    result.tasks_created += 1
    result.created.append(("task", task.ref, title))
