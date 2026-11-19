from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.models.project import Project
from src.models.task import TaskKind
from src.services import projects, tasks, versioning
from src.services.errors import NotFoundError, ValidationError

# Sizes a task may take.
_SIZES = ("XS", "S", "M", "L")

# Item kinds as written in a document, mapped to the model's.
_KINDS = {"feature": TaskKind.FEATURE, "task": TaskKind.TASK}

# Fields each kind of entry accepts; anything else is reported as an error.
_DOCUMENT_FIELDS = {"projects", "tasks"}
_SUBPROJECT_FIELDS = {"key", "name", "description", "version", "criteria", "items"}
_PROJECT_FIELDS = _SUBPROJECT_FIELDS | {"subprojects"}
_TASK_FIELDS = {"title", "body", "context", "size"}
_ITEM_FIELDS = _TASK_FIELDS | {"kind", "children"}
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
    # Features and tasks created (both count here).
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


def _check_task(entry : dict, where : str, errors : list, fields : set = _TASK_FIELDS) -> None:
    """Check one task entry's fields.

    Args:
        entry: The task, feature or loose-task entry.
        where: Label of the entry, for messages.
        errors: List receiving the problems found.
        fields: The fields this kind of entry accepts.
    """
    _unknown_fields(entry, fields, where, errors)
    _text(entry, "title", where, errors, required=True)
    _text(entry, "body", where, errors)
    _text(entry, "context", where, errors)
    size = _text(entry, "size", where, errors)
    if size is not None and size not in _SIZES:
        errors.append(f"{where}: 'size' must be one of {', '.join(_SIZES)}")


def _existing(session : Session, key : str) -> Project | None:
    """Return the project with this key, or None.

    Args:
        session: Database session to use.
        key: Project key.
    """
    try:
        return projects.get(session, key)
    except NotFoundError:
        return None


def _check_items(container : dict, field_name : str, where : str, errors : list) -> None:
    """Check the "items" of a project, or the "children" of a feature, recursively.

    Args:
        container: The project or feature entry.
        field_name: "items" or "children".
        where: Label of the container, for messages.
        errors: List receiving the problems found.
    """
    for index, item in _entries(container, field_name, where, errors):
        item_where = f"{where} {field_name}[{index}]"
        _check_task(item, item_where, errors, fields=_ITEM_FIELDS)
        kind = item.get("kind", "task")
        if not isinstance(kind, str) or kind not in _KINDS:
            errors.append(f"{item_where}: 'kind' must be one of {', '.join(_KINDS)}")
            continue
        if "children" in item:
            if kind != "feature":
                errors.append(f"{item_where}: only a feature can have 'children'")
            else:
                _check_items(item, "children", item_where, errors)


def _check_version(entry : dict, where : str, existing : bool, errors : list) -> None:
    """Check a project entry's "version" and "criteria".

    Both only apply to a project the import creates: an existing one is
    never overwritten.

    Args:
        entry: The project entry.
        where: Label of the entry, for messages.
        existing: Whether the project already exists.
        errors: List receiving the problems found.
    """
    for name in ("version", "criteria"):
        if existing and name in entry:
            errors.append(f"{where}: '{name}' can't be set on an existing project")
    if existing:
        return

    version = _text(entry, "version", where, errors)
    if version is not None and versioning.parse_label(version) is None:
        errors.append(f"{where}: 'version' must look like '1.4'")

    criteria = entry.get("criteria")
    if criteria is None:
        return
    if not isinstance(criteria, list):
        errors.append(f"{where}: 'criteria' must be a list")
        return
    for index, criterion in enumerate(criteria):
        criterion_where = f"{where} criteria[{index}]"
        if isinstance(criterion, str):
            if not criterion.strip():
                errors.append(f"{criterion_where}: text is required")
            continue
        if not isinstance(criterion, dict):
            errors.append(f"{criterion_where}: must be a string or an object")
            continue
        _unknown_fields(criterion, {"text", "done"}, criterion_where, errors)
        _text(criterion, "text", criterion_where, errors, required=True)
        if not isinstance(criterion.get("done", False), bool):
            errors.append(f"{criterion_where}: 'done' must be true or false")


def _check_project(session : Session, entry : dict, where : str, parent_key : str | None,
                   declared : set, errors : list) -> None:
    """Check one project or subproject entry, its subprojects and its items.

    Args:
        session: Database session to use (read only).
        entry: The project entry.
        where: Label of the entry, for messages.
        parent_key: Key of the root project it sits under; None at the top.
        declared: Keys already declared in the document, extended with this one.
        errors: List receiving the problems found.
    """
    _unknown_fields(entry, _PROJECT_FIELDS if parent_key is None else _SUBPROJECT_FIELDS, where, errors)
    key = _text(entry, "key", where, errors, required=True)
    if key is None:
        return
    where = f"{where} ('{key}')"
    if projects.is_reserved_key(key):
        errors.append(f"{where}: key is reserved")
    if key in declared:
        errors.append(f"{where}: project declared twice")
        return
    declared.add(key)

    existing = _existing(session, key)
    if existing is None:
        _text(entry, "name", where, errors, required=True)
    else:
        existing_parent = existing.parent.key if existing.parent else None
        if existing_parent != parent_key:
            place = f"a subproject of '{existing_parent}'" if existing_parent else "a root project"
            errors.append(f"{where}: already exists as {place}")
    _text(entry, "description", where, errors)
    _check_version(entry, where, existing is not None, errors)
    _check_items(entry, "items", where, errors)

    for index, sub in _entries(entry, "subprojects", where, errors):
        _check_project(session, sub, f"{where} subprojects[{index}]", key, declared, errors)


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
        _check_project(session, entry, f"projects[{index}]", None, declared, errors)

    for index, entry in _entries(data, "tasks", "document", errors):
        where = f"tasks[{index}]"
        _check_task(entry, where, errors, fields=_LOOSE_TASK_FIELDS)
        key = _text(entry, "project", where, errors)
        if key and key not in declared and _existing(session, key) is None:
            errors.append(f"{where}: project '{key}' doesn't exist")
    return errors


# -----------------------------------------------------------------------------
# Applying
# -----------------------------------------------------------------------------

def apply(session : Session, data : object, actor : str, dry_run : bool = False) -> ImportResult:
    """Import projects, subprojects, features and tasks from a document.

    Projects and subprojects are matched by their key: an existing one is
    reused and never overwritten, a missing one is created, with its
    version and major criteria if the document gives them. Features and
    tasks are always created: those placed in a project's tree are refined
    (already triaged), loose ones land in the inbox. Tasks are always created. Refs and
    ids in the document are not part of the format. The whole import is
    stored at once, or not at all.

    Args:
        session: Database session to use.
        data: The parsed document: {"projects": [{"key", "name",
            "description", "version", "criteria", "items": [ITEM],
            "subprojects": [{"key", "name", "description", "version",
            "criteria", "items": [ITEM]}]}], "tasks": [{"title", "body",
            "context", "size", "project"}]}, where an ITEM is {"kind":
            "feature" or "task" (default), "title", "body", "context",
            "size", "children": [ITEM] (features only)}. "version" is
            "MAJOR.MINOR"; "criteria" is a list of texts or {"text",
            "done"} objects.
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
    """Create or reuse each project, then its items and its subprojects."""
    for entry in data.get("projects", []):
        _create_project(session, entry, None, actor, result)


def _create_project(session : _DeferredCommit, entry : dict, parent_key : str | None,
                    actor : str, result : ImportResult) -> None:
    """Create or reuse one project or subproject, then fill its tree."""
    key = entry["key"].strip()
    if session.query(Project).filter_by(key=key).first() is None:
        projects.create(session, key, entry["name"].strip(),
                        (entry.get("description") or "").strip() or None,
                        parent_key=parent_key, actor=actor)
        _create_version(session, entry, key, actor)
        result.projects_created += 1
    else:
        result.projects_reused += 1

    for item in entry.get("items", []):
        _create_item(session, item, key, None, actor, result)
    for sub in entry.get("subprojects", []):
        _create_project(session, sub, key, actor, result)


def _create_version(session : _DeferredCommit, entry : dict, key : str, actor : str) -> None:
    """Give a newly created project its version and major criteria, if any."""
    version = (entry.get("version") or "").strip()
    if version:
        major, minor = versioning.parse_label(version)
        versioning.set_version(session, key, major, minor, actor=actor)
    for criterion in entry.get("criteria", []):
        if isinstance(criterion, str):
            criterion = {"text": criterion}
        added = versioning.add_criterion(session, key, criterion["text"], actor=actor)
        if criterion.get("done", False):
            versioning.set_criterion_done(session, added.id, True, actor=actor)


def _fields(entry : dict) -> dict:
    """The optional detail of a task entry, stripped, blanks as None."""
    return {name: (entry.get(name) or "").strip() or None for name in ("body", "context", "size")}


def _create_item(session : _DeferredCommit, entry : dict, project_key : str, parent_ref : str | None,
                 actor : str, result : ImportResult) -> None:
    """Create one feature or task in a project's tree, refined, then its children."""
    kind = _KINDS[entry.get("kind", "task")]
    title = entry["title"].strip()
    fields = _fields(entry)
    item = tasks.add_to_tree(session, title, project_key=project_key, parent_ref=parent_ref,
                             kind=kind, actor=actor, **fields)
    result.tasks_created += 1
    result.created.append((kind.name.lower(), item.ref, title))
    for child in entry.get("children", []):
        _create_item(session, child, project_key, item.ref, actor, result)


def _create_task(session : _DeferredCommit, entry : dict, project_key : str | None,
                 actor : str, result : ImportResult) -> None:
    """Create one loose task in the inbox, in its project if it names one."""
    title = entry["title"].strip()
    task = tasks.create(session, title, project_key=project_key.strip() if project_key else None,
                        actor=actor, **_fields(entry))
    result.tasks_created += 1
    result.created.append(("task", task.ref, title))
