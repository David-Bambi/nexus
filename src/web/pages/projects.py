import json
from datetime import date

from flask import abort, current_app, redirect, render_template, request, url_for

from src.models.project import ProjectPriority
from src.models.task import TaskKind
from src.services import export, projects, tasks, views
from src.services.errors import ConflictError, NotFoundError, ValidationError
from src.web.pages._shared import _session, bp


@bp.route("/")
def home():
    """Show the dashboard: doing/waiting items and queue counters."""
    return render_template("dashboard.html", dashboard=views.dashboard(_session()))


@bp.route("/export.json")
def export_json():
    """Download the whole database as a JSON file."""
    body = json.dumps(export.dump_json(_session()), indent=2)
    response = current_app.response_class(body, mimetype="application/json")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="nexus-export-{date.today().isoformat()}.json"'
    )
    return response


@bp.route("/export/features.json")
def export_features_json():
    """Show the feature export for metrique as JSON (served inline, not as a download)."""
    body = json.dumps(export.features(_session()), ensure_ascii=False, indent=2)
    return current_app.response_class(body, mimetype="application/json")


@bp.route("/projects", methods=["GET", "POST"])
def projects_list():
    """List all projects and subprojects.

    A plain HTML form on the same page creates a project.
    """
    session = _session()
    error = None
    if request.method == "POST":
        try:
            projects.create(
                session,
                request.form["key"],
                request.form["name"],
                request.form.get("description") or None,
                directory=request.form.get("directory"),
            )
            return redirect(url_for("pages.projects_list"))
        except (ConflictError, ValidationError) as e:
            error = str(e)
    return render_template("projects.html", projects=projects.list(session), error=error)


def _get_project(key):
    """Look up a project by key, or answer 404."""
    try:
        return projects.get(_session(), key)
    except NotFoundError:
        abort(404)


def _render_project(project, error=None, status=200, open_form=None):
    """Render a project page: its details, subprojects and work.

    The backlog shows open items only; done and cancelled ones are left out.

    Args:
        project: The project or subproject to show.
        error: Message of a refused action, shown on the page; None if none.
        status: HTTP status of the response.
        open_form: Id of the hidden form to show open, e.g. the one whose
            action was refused; None to keep every form closed.
    """
    view = _view()
    tree = board = None
    if view == "kanban":
        board = views.project_board(project)
    else:
        tree = views.project_tree(project)
    return render_template("project.html", project=project, tree=tree, board=board,
                           columns=views.BOARD_COLUMNS, view=view,
                           open_form=open_form, error=error), status


def _view():
    """Read the work view asked for in the query string.

    Returns:
        "kanban" for `?view=kanban`; "backlog" for anything else, the default.
    """
    return "kanban" if request.args.get("view") == "kanban" else "backlog"


@bp.route("/projects/<key>")
def project_detail(key):
    """Show a single project's details, its subprojects and its work, as a
    tree of open items (backlog, the default) or as a kanban board
    (`?view=kanban`).
    """
    return _render_project(_get_project(key))


# Item kinds as the add form sends them, mapped to the model's.
_KINDS = {"task": TaskKind.TASK, "feature": TaskKind.FEATURE}


@bp.route("/projects/<key>/items", methods=["POST"])
def project_add_item(key):
    """Add a feature or task to a project's tree, in the inbox state.

    The form gives a title, a kind and, to add under a feature, its ref.
    On success, comes back to the parent feature's row (or to the work
    section); on a refusal, shows the page with that add form open.
    """
    session = _session()
    project = _get_project(key)
    title = request.form.get("title", "")
    parent_ref = request.form.get("parent_ref") or None
    kind = _KINDS.get(request.form.get("kind", "task"), TaskKind.TASK)
    try:
        # Both the project and the parent are given, so a feature of another
        # project is refused before anything is written.
        tasks.add_to_tree(session, title, project_key=key, parent_ref=parent_ref, kind=kind)
    except (NotFoundError, ValidationError, ConflictError) as e:
        session.rollback()
        return _render_project(project, str(e), 400, open_form=f"add-{parent_ref or 'root'}")
    anchor = f"item-{parent_ref}" if parent_ref else "work"
    return redirect(url_for("pages.project_detail", key=key, _anchor=anchor))


def _project_action(key, fn, status=400, anchor=None, form=None):
    """Run a change on a project and come back to its page, or show the error.

    Args:
        key: Key of the project the page shows.
        fn: Callable taking the session and applying the change.
        status: HTTP status of the response when the change is refused.
        anchor: Id on the page to come back to after the change (e.g.
            "criteria"); None for the top of the page.
        form: Id of the hidden form to show open again when the change is
            refused; None to keep every form closed.
    """
    session = _session()
    project = _get_project(key)
    try:
        fn(session)
    except (NotFoundError, ValidationError, ConflictError) as e:
        session.rollback()
        return _render_project(project, str(e), status, open_form=form)
    return redirect(url_for("pages.project_detail", key=key, _anchor=anchor))


@bp.route("/projects/<key>/subprojects", methods=["POST"])
def project_add_subproject(key):
    """Create a subproject under a root project, then show the root project."""
    return _project_action(key, lambda s: projects.create(
        s, request.form.get("key", "").strip(), request.form.get("name", "").strip(),
        request.form.get("description") or None, parent_key=key,
        directory=request.form.get("directory")), anchor="subprojects", form="add-subproject")


@bp.route("/projects/<key>/update", methods=["POST"])
def project_update(key):
    """Change a project's name, description, directory (blank clears it) and,
    for a root project, its priority (absent or unknown: unchanged)."""
    priority = ProjectPriority.__members__.get(request.form.get("priority", ""))
    return _project_action(key, lambda s: projects.update(
        s, key, request.form.get("name", ""), request.form.get("description"),
        directory=request.form.get("directory", ""), priority=priority), form="edit-project")


@bp.route("/projects/<key>/archive", methods=["POST"])
def project_archive(key):
    """Archive a project."""
    return _project_action(key, lambda s: projects.archive(s, key))


@bp.route("/projects/<key>/restore", methods=["POST"])
def project_restore(key):
    """Bring an archived project back to active."""
    return _project_action(key, lambda s: projects.restore(s, key), status=409)


@bp.route("/projects/<key>/delete", methods=["POST"])
def project_delete(key):
    """Delete an empty project; a non-empty one is shown again with the
    reason, its delete confirmation open."""
    session = _session()
    try:
        projects.delete(session, key)
    except NotFoundError:
        abort(404)
    except ConflictError as e:
        return _render_project(projects.get(session, key), str(e), 409, open_form="delete-project")
    return redirect(url_for("pages.projects_list"))
