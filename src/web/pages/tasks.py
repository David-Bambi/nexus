from flask import abort, redirect, render_template, request, url_for

from src.models.task import TaskKind, TaskState
from src.services import events, sizes, tasks, views
from src.services.errors import ConflictError, InvalidTransitionError, NotFoundError, ValidationError
from src.web.pages._shared import PAGE_LIMIT, _session, bp


# Item kinds as the forms send them, mapped to the model's.
_KINDS = {"task": TaskKind.TASK, "feature": TaskKind.FEATURE}


@bp.route("/sizes")
def sizes_guide():
    """Show the task-size guide: when to choose each size, an example, and the rules."""
    return render_template("sizes.html", size_rules=sizes.SIZE_RULES)


@bp.route("/tasks", methods=["GET", "POST"])
def tasks_list():
    """List all tasks; a plain HTML form on the same page captures one."""
    session = _session()
    if request.method == "POST":
        tasks.capture(session, request.form["title"])
        return redirect(url_for("pages.tasks_list"))
    recent = tasks.list(session, limit=PAGE_LIMIT)
    return render_template("tasks.html", tasks=recent, truncated=len(recent) == PAGE_LIMIT, limit=PAGE_LIMIT)


def _local_path(target):
    """Return target if it is a same-app relative path, else None.

    Args:
        target: Raw client-supplied URL, or None.
    """
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


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
    return _local_path(next_url) or url_for(fallback_endpoint)


@bp.route("/capture", methods=["POST"])
def capture():
    """Capture a task from the global capture bar, without leaving the current page."""
    session = _session()
    tasks.capture(session, request.form["title"])
    return redirect(_safe_next(request.form.get("next"), "pages.tasks_list"))


def _render_task(task, error):
    """Render the task detail page with its event history.

    Args:
        task: The task to show.
        error: Message to display, or None.
    """
    return render_template(
        "task.html",
        task=task,
        history=events.history(_session(), "task", task.id),
        children=views.item_tree(task, include_closed=True),
        error=error,
        next=_local_path(request.values.get("next")),
    )


@bp.route("/tasks/<int:task_id>")
def task_detail(task_id):
    """Show a single task's details."""
    session = _session()
    try:
        task = tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    return _render_task(task, None)


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
    except (NotFoundError, ValidationError, InvalidTransitionError, ConflictError) as e:
        error = str(e)
    return task, error


def _clarify_fields():
    """Read the optional clarify fields from the current request's form.

    Returns:
        body, project_key, context, size and parent_ref (None when blank),
        and kind (a TaskKind, or None to keep the current one).
    """
    fields = {
        name: (request.form.get(name) or "").strip() or None
        for name in ("body", "project_key", "context", "size", "parent_ref")
    }
    fields["kind"] = _KINDS.get(request.form.get("kind", ""))
    return fields


def _clarify(session, task_id, fields):
    """Clarify a task from the form fields read by _clarify_fields().

    Args:
        session: Database session to use.
        task_id: Id of the task.
        fields: The clarify fields.
    """
    return tasks.clarify(
        session, task_id, request.form["title"],
        fields["body"], fields["project_key"], fields["context"], fields["size"],
        parent_ref=fields["parent_ref"], kind=fields["kind"],
    )


def _apply_transition(task_id, fn):
    """Run a task transition and render the task detail page with the result."""
    task, error = _run_transition(_session(), task_id, fn)
    return _render_task(task, error)


@bp.route("/tasks/<int:task_id>/update", methods=["POST"])
def task_update(task_id):
    """Update a task's descriptive fields; with the "correction" box ticked,
    the change is logged as a correction."""
    return _apply_transition(
        task_id,
        lambda s: tasks.update(
            s,
            task_id,
            correction=request.form.get("correction") == "1",
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
    return _apply_transition(task_id, lambda s: _clarify(s, task_id, fields))


@bp.route("/tasks/<int:task_id>/start", methods=["POST"])
def task_start(task_id):
    """Start a refined task."""
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


@bp.route("/tasks/<int:task_id>/cancel", methods=["POST"])
def task_cancel(task_id):
    """Cancel a task that won't be done."""
    return _apply_transition(task_id, lambda s: tasks.cancel(s, task_id))


@bp.route("/tasks/<int:task_id>/restore", methods=["POST"])
def task_restore(task_id):
    """Bring a cancelled task back to refined."""
    return _apply_transition(task_id, lambda s: tasks.restore(s, task_id))


@bp.route("/tasks/<int:task_id>/state", methods=["POST"])
def task_state(task_id):
    """Move a task to the state picked in the form ("state", plus "reason" for waiting).

    On success, goes back to the safe "return_to" page when one is given
    (e.g. the kanban board the form sits on); otherwise, and on a refusal,
    shows the task page. "return_to" is separate from "next", which the task
    page keeps as its back link.
    """
    def move(session):
        try:
            target = TaskState[request.form.get("state", "")]
        except KeyError:
            raise ValidationError("unknown state.")
        return tasks.change_state(session, task_id, target, request.form.get("reason", ""))

    task, error = _run_transition(_session(), task_id, move)
    target = _local_path(request.values.get("return_to"))
    if target and not error:
        return redirect(target)
    return _render_task(task, error)


@bp.route("/tasks/<int:task_id>/children", methods=["POST"])
def task_add_child(task_id):
    """Add a refined feature or task under a feature, then show the feature."""
    def add(session):
        feature = tasks.get(session, task_id)
        if feature.project is None:
            raise ValidationError(f"'{feature.ref}' has no project yet.")
        tasks.add_to_tree(session, request.form.get("title", ""), project_key=feature.project.key,
                          parent_ref=feature.ref,
                          kind=_KINDS.get(request.form.get("kind", "task"), TaskKind.TASK))
        return tasks.get(session, task_id)

    return _apply_transition(task_id, add)


@bp.route("/tasks/<int:task_id>/move", methods=["POST"])
def task_move(task_id):
    """Move an item to another project (top level) or under a feature."""
    return _apply_transition(task_id, lambda s: tasks.move(
        s, task_id,
        project_key=(request.form.get("project_key") or "").strip() or None,
        parent_ref=(request.form.get("parent_ref") or "").strip() or None))


@bp.route("/tasks/<int:task_id>/reorder", methods=["POST"])
def task_reorder(task_id):
    """Move an item up or down among its siblings ("direction" = up or down).

    On success, goes back to the safe "next" page (the tree it was moved
    in), else to the item's project; a refusal shows the item page.
    """
    session = _session()
    task, error = _run_transition(
        session, task_id, lambda s: tasks.reorder(s, task_id, request.form.get("direction", "")))
    if error:
        return _render_task(task, error)
    target = _local_path(request.values.get("next"))
    return redirect(target or url_for("pages.project_detail", key=task.project.key))


@bp.route("/tasks/<int:task_id>/kind", methods=["POST"])
def task_change_kind(task_id):
    """Turn a task into a feature, or an empty feature into a task."""
    def change(session):
        kind = _KINDS.get(request.form.get("kind", ""))
        if kind is None:
            raise ValidationError("unknown kind.")
        return tasks.change_kind(session, task_id, kind)

    return _apply_transition(task_id, change)


def _delete_task(task_id, redirect_endpoint):
    """Delete a task, looking it up first for a clean 404.

    Args:
        task_id: Id of the task.
        redirect_endpoint: Endpoint to redirect to afterward, unless the
            request carries a safe "next" page to return to.
    """
    session = _session()
    try:
        tasks.get(session, task_id)
    except NotFoundError:
        abort(404)
    tasks.delete(session, task_id)
    return redirect(_safe_next(request.values.get("next"), redirect_endpoint))


@bp.route("/tasks/<int:task_id>/delete", methods=["POST"])
def task_delete(task_id):
    """Delete a task."""
    return _delete_task(task_id, "pages.tasks_list")
