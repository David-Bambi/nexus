from datetime import date

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from src.services import projects, tasks, versions
from src.services.errors import ConflictError, InvalidTransitionError, NotFoundError, ValidationError

# Full-page (non-fragment) routes. Adapters only: no business logic here —
# validate input, call a service, render a template (ADR-0001).
bp = Blueprint("pages", __name__)


def _session():
    """Return this request's SQLAlchemy session, stashed on the app by create_app()."""
    return current_app.extensions["db_session"]


@bp.route("/")
def home():
    """Empty home page for the 0.1.0 foundation increment."""
    return render_template("base.html")     


@bp.route("/projects", methods=["GET", "POST"])
def projects_list():
    """List all projects; a plain HTML form on the same page creates one."""
    session = _session()
    error = None
    if request.method == "POST":
        try:
            projects.create(
                session,
                request.form["key"],
                request.form["name"],
                request.form.get("description") or None,
            )
            return redirect(url_for("pages.projects_list"))
        except ConflictError as e:
            error = str(e)
    return render_template("projects.html", projects=projects.list(session), error=error)


@bp.route("/projects/<key>")
def project_detail(key):
    """Show a single project's details."""
    session = _session()
    try:
        project = projects.get(session, key)
    except NotFoundError:
        abort(404)
    return render_template("project.html", project=project)

@bp.route("/projects/<key>/delete", methods=["POST"])
def project_delete(key):
    """Delete a project"""
    projects.delete(_session(), key)
    return redirect(url_for("pages.projects_list"))


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
        dod = [line.strip() for line in request.form.get("dod", "").splitlines() if line.strip()]
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


@bp.route("/projects/<key>/versions/<number>")
def version_detail(key, number):
    """Show a single version's details."""
    session = _session()
    try:
        version = versions.get(session, key, number)
    except NotFoundError:
        abort(404)
    return render_template("version.html", version=version, error=None)


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
    return render_template("version.html", version=version, error=error)


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
    return render_template("version.html", version=version, error=error)


@bp.route("/tasks", methods=["GET", "POST"])
def tasks_list():
    """List all tasks; a plain HTML form on the same page captures one."""
    session = _session()
    if request.method == "POST":
        tasks.capture(session, request.form["title"])
        return redirect(url_for("pages.tasks_list"))
    return render_template("tasks.html", tasks=tasks.list(session))


@bp.route("/tasks/<int:task_id>")
def task_detail(task_id):
    """Show a single task's details."""
    session = _session()
    try:
        task = tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    return render_template("task.html", task=task, error=None)


def _apply_transition(task_id, fn):
    """Run a task transition, looking the task up first for a clean 404.

    Args:
        task_id: Id of the task.
        fn: Callable taking the session and applying the transition.

    Returns:
        The rendered task detail page, with an inline error on failure.
    """
    session = _session()
    try:
        task = tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    error = None
    try:
        task = fn(session)
    except (NotFoundError, ValidationError, InvalidTransitionError) as e:
        error = str(e)
    return render_template("task.html", task=task, error=error)


@bp.route("/tasks/<int:task_id>/update", methods=["POST"])
def task_update(task_id):
    """Update a task's descriptive fields."""
    return _apply_transition(
        task_id,
        lambda s: tasks.update(
            s,
            task_id,
            title=request.form["title"],
            body=request.form.get("body") or None,
            context=request.form.get("context") or None,
            size=request.form.get("size") or None,
        ),
    )


@bp.route("/tasks/<int:task_id>/clarify", methods=["POST"])
def task_clarify(task_id):
    """Clarify a captured or someday task into a refined one."""
    return _apply_transition(
        task_id,
        lambda s: tasks.clarify(
            s,
            task_id,
            request.form["title"],
            request.form.get("body") or None,
            request.form.get("project_key") or None,
            request.form.get("context") or None,
            request.form.get("size") or None,
        ),
    )


@bp.route("/tasks/<int:task_id>/plan", methods=["POST"])
def task_plan(task_id):
    """Plan a refined task into a version."""
    return _apply_transition(
        task_id, lambda s: tasks.plan(s, task_id, int(request.form["version_id"]))
    )


@bp.route("/tasks/<int:task_id>/unplan", methods=["POST"])
def task_unplan(task_id):
    """Unplan a planned task back to refined."""
    return _apply_transition(task_id, lambda s: tasks.unplan(s, task_id))


@bp.route("/tasks/<int:task_id>/start", methods=["POST"])
def task_start(task_id):
    """Start a planned task."""
    return _apply_transition(task_id, lambda s: tasks.start(s, task_id))


@bp.route("/tasks/<int:task_id>/block", methods=["POST"])
def task_block(task_id):
    """Block a task that's being worked on."""
    return _apply_transition(
        task_id, lambda s: tasks.block(s, task_id, request.form.get("reason", ""))
    )


@bp.route("/tasks/<int:task_id>/unblock", methods=["POST"])
def task_unblock(task_id):
    """Unblock a waiting task."""
    return _apply_transition(task_id, lambda s: tasks.unblock(s, task_id))


@bp.route("/tasks/<int:task_id>/complete", methods=["POST"])
def task_complete(task_id):
    """Complete a task that's being worked on."""
    return _apply_transition(task_id, lambda s: tasks.complete(s, task_id))


@bp.route("/tasks/<int:task_id>/reopen", methods=["POST"])
def task_reopen(task_id):
    """Reopen a completed task."""
    return _apply_transition(task_id, lambda s: tasks.reopen(s, task_id))


@bp.route("/tasks/<int:task_id>/defer", methods=["POST"])
def task_defer(task_id):
    """Defer a task to someday."""
    return _apply_transition(task_id, lambda s: tasks.defer(s, task_id))


@bp.route("/tasks/<int:task_id>/delete", methods=["POST"])
def task_delete(task_id):
    """Delete a task."""
    session = _session()
    try:
        tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    tasks.delete(session, task_id)
    return redirect(url_for("pages.tasks_list"))