from flask import redirect, render_template, request, url_for

from src.services import projects, tasks, views
from src.web.pages._shared import PAGE_LIMIT, _session, bp
from src.web.pages.tasks import _clarify_fields, _delete_task, _run_transition


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
    queue = views.to_refine(session, context, project_key, limit=PAGE_LIMIT)
    return render_template(
        "refine.html",
        tasks=queue,
        truncated=len(queue) == PAGE_LIMIT,
        limit=PAGE_LIMIT,
        projects=projects.list(session),
        context=context,
        project_key=project_key,
    )


@bp.route("/search")
def search():
    """Show tasks matching a free-text search term."""
    session = _session()
    term = request.args.get("q", "")
    found = views.search(session, term, limit=PAGE_LIMIT)
    return render_template(
        "search.html", tasks=found, term=term, truncated=len(found) == PAGE_LIMIT, limit=PAGE_LIMIT
    )