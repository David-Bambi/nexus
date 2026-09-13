from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from src.services import projects
from src.services.errors import ConflictError, NotFoundError

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