from datetime import date

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from src.services import projects, versions
from src.services.errors import ConflictError, NotFoundError, ValidationError

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