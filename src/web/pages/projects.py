import json
from datetime import date

from flask import abort, current_app, redirect, render_template, request, url_for

from src.models.version import VersionStatus
from src.services import export, projects, versions, views
from src.services.errors import ConflictError, NotFoundError, ValidationError
from src.web.pages._shared import _session, bp


@bp.route("/")
def home():
    """Show the dashboard: in-progress versions, doing/waiting tasks and queue counters."""
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


@bp.route("/projects", methods=["GET", "POST"])
def projects_list():
    """List all projects, each with its unreleased versions and their progress.

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
            )
            return redirect(url_for("pages.projects_list"))
        except (ConflictError, ValidationError) as e:
            error = str(e)
    unreleased = [v for v in versions.list_all(session) if v.status != VersionStatus.RELEASED]
    # Progress of each project's unreleased versions, by project id, in the project's own order.
    progress_by_project = {}
    for progress in views.version_progress(session, unreleased):
        progress_by_project.setdefault(progress.version.project_id, []).append(progress)
    return render_template("projects.html", projects=projects.list(session),
                           progress_by_project=progress_by_project, error=error)


@bp.route("/projects/<key>")
def project_detail(key):
    """Show a single project's details and its versions with their progress."""
    session = _session()
    try:
        project = projects.get(session, key)
    except NotFoundError:
        abort(404)
    progress = views.version_progress(session, versions.list(session, key))
    return render_template("project.html", project=project, versions=progress)


@bp.route("/projects/<key>/delete", methods=["POST"])
def project_delete(key):
    """Delete a project"""
    projects.delete(_session(), key)
    return redirect(url_for("pages.projects_list"))
