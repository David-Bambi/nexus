from datetime import date

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from src.services import projects, tasks, versions, views
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


def _safe_next(next_url, fallback_endpoint):
    """Resolve a client-supplied redirect target, rejecting anything unsafe.

    Args:
        next_url: Raw "next" value from the request, or None.
        fallback_endpoint: Endpoint to redirect to if next_url isn't a safe,
            same-app relative path (a bare "/..." path — a leading "//"
            is rejected too, since browsers treat it as protocol-relative
            and resolve it to an external host).

    Returns:
        A URL safe to redirect to.
    """
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return url_for(fallback_endpoint)


@bp.route("/capture", methods=["POST"])
def capture():
    """Capture a task from the global capture bar, without leaving the current page."""
    session = _session()
    tasks.capture(session, request.form["title"])
    return redirect(_safe_next(request.form.get("next"), "pages.tasks_list"))


@bp.route("/tasks/<int:task_id>")
def task_detail(task_id):
    """Show a single task's details."""
    session = _session()
    try:
        task = tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    return render_template("task.html", task=task, error=None)


def _run_transition(session, task_id, fn):
    """Look up a task and apply a transition to it, catching domain errors.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        fn: Callable taking the session and applying the transition.

    Returns:
        A (task, error) pair: task reflects the change on success, or is
        left as originally looked up on failure; error is the message
        string on failure, or None on success.
    """
    try:
        task = tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    error = None
    try:
        task = fn(session)
    except (NotFoundError, ValidationError, InvalidTransitionError) as e:
        error = str(e)
    return task, error


def _clarify_fields():
    """Read the optional clarify fields from the current request's form."""
    return {
        name: request.form.get(name) or None
        for name in ("body", "project_key", "context", "size")
    }


def _apply_transition(task_id, fn):
    """Run a task transition and render the task detail page with the result."""
    task, error = _run_transition(_session(), task_id, fn)
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
    fields = _clarify_fields()
    return _apply_transition(
        task_id,
        lambda s: tasks.clarify(
            s, task_id, request.form["title"],
            fields["body"], fields["project_key"], fields["context"], fields["size"],
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


def _delete_task(task_id, redirect_endpoint):
    """Delete a task, looking it up first for a clean 404.

    Args:
        task_id: Id of the task.
        redirect_endpoint: Endpoint to redirect to afterward.
    """
    session = _session()
    try:
        tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    tasks.delete(session, task_id)
    return redirect(url_for(redirect_endpoint))


@bp.route("/tasks/<int:task_id>/delete", methods=["POST"])
def task_delete(task_id):
    """Delete a task."""
    return _delete_task(task_id, "pages.tasks_list")


@bp.route("/inbox")
def inbox():
    """Show the next inbox item for sequential, one-at-a-time triage."""
    session = _session()
    queue = views.inbox(session)
    return render_template("inbox.html", task=queue[0] if queue else None, error=None)


def _inbox_action(task_id, fn):
    """Run an inbox transition and advance to the next item, or show the error."""
    task, error = _run_transition(_session(), task_id, fn)
    if error:
        return render_template("inbox.html", task=task, error=error)
    return redirect(url_for("pages.inbox"))


@bp.route("/inbox/<int:task_id>/clarify", methods=["POST"])
def inbox_clarify(task_id):
    """Clarify an inbox item into a refined task."""
    fields = _clarify_fields()
    return _inbox_action(
        task_id,
        lambda s: tasks.clarify(
            s, task_id, request.form["title"],
            fields["body"], fields["project_key"], fields["context"], fields["size"],
        ),
    )


@bp.route("/inbox/<int:task_id>/defer", methods=["POST"])
def inbox_defer(task_id):
    """Defer an inbox item to someday."""
    return _inbox_action(task_id, lambda s: tasks.defer(s, task_id))


@bp.route("/inbox/<int:task_id>/delete", methods=["POST"])
def inbox_delete(task_id):
    """Delete an inbox item."""
    return _delete_task(task_id, "pages.inbox")


@bp.route("/refine")
def refine():
    """List refined, unplanned tasks, filterable by context and project."""
    session = _session()
    context = request.args.get("context") or None
    project_key = request.args.get("project_key") or None
    return render_template(
        "refine.html",
        tasks=views.to_refine(session, context, project_key),
        projects=projects.list(session),
        context=context,
        project_key=project_key,
    )


@bp.route("/search")
def search():
    """Show tasks matching a free-text search term."""
    session = _session()
    term = request.args.get("q", "")
    return render_template("search.html", tasks=views.search(session, term), term=term)