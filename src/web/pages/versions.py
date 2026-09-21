from datetime import date

from flask import abort, redirect, render_template, request, url_for

from src.models.task import TaskState
from src.services import events, projects, tasks, versions, views
from src.services.errors import ConflictError, InvalidTransitionError, NotFoundError, ValidationError
from src.web.pages._shared import PAGE_LIMIT, _session, bp


@bp.route("/projects/<key>/versions", methods=["GET", "POST"])
def versions_list(key):
    """List a project's versions; a plain HTML form on the same page creates one."""
    session = _session()
    try:
        project = projects.get(session, key)
    except NotFoundError:
        abort(404)

    error = None
    if request.method == "POST":
        # One "dod" field per criterion; a field holding several lines is split too.
        dod = [
            line.strip()
            for value in request.form.getlist("dod")
            for line in value.splitlines()
            if line.strip()
        ]
        target_date = request.form.get("target_date") or None
        try:
            versions.create(
                session,
                key,
                request.form["number"],
                request.form["title"],
                dod,
                request.form.get("goal") or None,
                date.fromisoformat(target_date) if target_date else None,
            )
            return redirect(url_for("pages.versions_list", key=key))
        except (ConflictError, ValidationError) as e:
            error = str(e)
    return render_template(
        "versions.html", project=project, versions=versions.list(session, key), error=error
    )


def _render_version(version, error):
    """Render the version detail page with its changelog.

    Args:
        version: The version to show.
        error: Message to display, or None.

    The page also lists the project's refined, unplanned tasks as candidates
    to add to the version.
    """
    return render_template(
        "version.html",
        version=version,
        tasks=versions.list_tasks(_session(), version.id),
        candidates=views.to_refine(_session(), project_key=version.project.key, limit=PAGE_LIMIT),
        changelog=events.changelog(_session(), version.id),
        error=error,
    )


@bp.route("/projects/<key>/versions/<number>")
def version_detail(key, number):
    """Show a single version's details."""
    session = _session()
    try:
        version = versions.get(session, key, number)
    except NotFoundError:
        abort(404)
    return _render_version(version, None)


@bp.route("/projects/<key>/versions/<number>/start", methods=["POST"])
def version_start(key, number):
    """Start a version."""
    session = _session()
    try:
        version = versions.get(session, key, number)
    except NotFoundError:
        abort(404)
    error = None
    try:
        versions.start(session, version.id)
    except ValidationError as e:
        error = str(e)
    return _render_version(version, error)


@bp.route("/projects/<key>/versions/<number>/release", methods=["POST"])
def version_release(key, number):
    """Release a version."""
    session = _session()
    try:
        version = versions.get(session, key, number)
    except NotFoundError:
        abort(404)
    error = None
    try:
        versions.release(session, version.id)
    except ValidationError as e:
        error = str(e)
    return _render_version(version, error)


def _dod_mutation(key, number, criterion_id, mutate):
    """Apply a definition-of-done change to a version, then re-render its page.

    Args:
        key: Key of the owning project.
        number: Version number.
        criterion_id: Id of the targeted criterion, or None when the change
            targets no existing criterion (adding one).
        mutate: Callable(session, version, criterion) performing the change
            through the service layer.

    Returns:
        The rendered version page, with the error message if the service refused.
    """
    session = _session()
    try:
        version = versions.get(session, key, number)
    except NotFoundError:
        abort(404)
    criterion = None
    if criterion_id is not None:
        criterion = next((c for c in version.definition_of_done if c.id == criterion_id), None)
        if criterion is None:
            abort(404)
    error = None
    try:
        mutate(session, version, criterion)
    except (ValidationError, ConflictError) as e:
        error = str(e)
    return _render_version(version, error)


@bp.route("/projects/<key>/versions/<number>/dod", methods=["POST"])
def version_dod_add(key, number):
    """Add a criterion to a version's definition of done."""
    return _dod_mutation(
        key, number, None,
        lambda session, version, _: versions.add_criterion(
            session, version.id, request.form.get("description", "")),
    )


@bp.route("/projects/<key>/versions/<number>/dod/<int:criterion_id>/toggle", methods=["POST"])
def version_dod_toggle(key, number, criterion_id):
    """Check or uncheck a criterion, flipping its current state."""
    return _dod_mutation(
        key, number, criterion_id,
        lambda session, _, criterion: versions.set_criterion_done(
            session, criterion.id, not criterion.done),
    )


@bp.route("/projects/<key>/versions/<number>/dod/<int:criterion_id>/edit", methods=["POST"])
def version_dod_edit(key, number, criterion_id):
    """Change the description of a criterion."""
    return _dod_mutation(
        key, number, criterion_id,
        lambda session, _, criterion: versions.update_criterion(
            session, criterion.id, request.form.get("description", "")),
    )


@bp.route("/projects/<key>/versions/<number>/dod/<int:criterion_id>/delete", methods=["POST"])
def version_dod_delete(key, number, criterion_id):
    """Delete a criterion from a version's definition of done."""
    return _dod_mutation(
        key, number, criterion_id,
        lambda session, _, criterion: versions.delete_criterion(session, criterion.id),
    )

@bp.route("/projects/<key>/versions/<number>/tasks/", methods=["POST"])
def version_task_add(key: str, number: str) -> str:
    """Create a task directly in a version, already planned, then re-render its page.

    Skips the capture/refine steps. Reads the form fields "title" (required)
    and "context", "size", "body" (optional; blank means none).

    Args:
        key: Key of the owning project.
        number: Version number.

    Returns:
        The rendered version page, with the error message if the service
        refused (blank title, released version).

    Raises:
        werkzeug.exceptions.NotFound: 404 if the project or version doesn't exist.
    """
    session = _session()
    try:
        version = versions.get(session, key, number)
    except NotFoundError:
        abort(404)

    error=None
    try:
        tasks.create_in_version(
              session, 
              version.id, 
              request.form.get("title", ""),
              request.form.get("context") or None,
              request.form.get("size") or None,
              request.form.get("body") or None,
        )
    except ValidationError as e:
        error = str(e)
    return _render_version(version, error)


@bp.route("/projects/<key>/versions/<number>/task/<int:task_id>/state", methods=["POST"])
def version_task_state(key: str, number: str, task_id: int) -> str:
    """Move a task of a version to the state picked in the form, then re-render its page.

    Reads the form fields "state" (a TaskState name) and "reason" (for waiting).

    Args:
        key: Key of the owning project.
        number: Version number.
        task_id: Id of the task to move.

    Returns:
        The rendered version page, with the error message if the state is
        unknown or the service refused the move.

    Raises:
        werkzeug.exceptions.NotFound: 404 if the project, version or task
            doesn't exist, or the task isn't in this version.
    """
    session = _session()
    try:
        version = versions.get(session, key, number)
        task = tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    if task.version_id != version.id:
        abort(404)

    error = None
    try:
        target = TaskState[request.form.get("state", "")]
        tasks.change_state(session, task_id, target, request.form.get("reason", ""))
    except KeyError:
        error = "unknown state."
    except (InvalidTransitionError, ValidationError) as e:
        error = str(e)
    return _render_version(version, error)


@bp.route("/projects/<key>/versions/<number>/task/<int:task_id>/plan", methods=["POST"])
def version_task_plan(key: str, number: str, task_id: int) -> str:
    """Plan a candidate task into a version, then re-render its page.

    Args:
        key: Key of the owning project.
        number: Version number.
        task_id: Id of the refined task to add to the version.

    Returns:
        The rendered version page, with the error message if the service
        refused (task not refined, released version, other project).

    Raises:
        werkzeug.exceptions.NotFound: 404 if the project, version or task
            doesn't exist.
    """
    session = _session()
    try:
        version = versions.get(session, key, number)
        tasks.plan(session, task_id, version.id)
    except NotFoundError:
        abort(404)
    except (InvalidTransitionError, ValidationError) as e:
        return _render_version(version, str(e))
    return _render_version(version, None)
