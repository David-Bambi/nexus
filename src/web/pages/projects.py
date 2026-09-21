import json
from datetime import date

from flask import abort, current_app, redirect, render_template, request, url_for

from src.services import export, projects, views
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
        except (ConflictError, ValidationError) as e:
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
