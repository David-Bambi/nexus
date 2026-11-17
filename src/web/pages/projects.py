import json
from datetime import date

from flask import abort, current_app, redirect, render_template, request, url_for

from src.models.ai import Nature
from src.models.version import VersionStatus
from src.services import ai, export, projects, versions, views
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


def _render_project(project, error=None):
    """Render a project's page: versions, AI usage profile and AI settings.

    Args:
        project: The project to show.
        error: Message to display, or None.
    """
    session = _session()
    progress = views.version_progress(session, versions.list(session, project.key))
    return render_template("project.html", project=project, versions=progress,
                           profile=ai.profile(session, project.key),
                           natures=ai.natures(session, project.key),
                           targets=ai.targets(session, project.key), error=error)


@bp.route("/projects/<key>")
def project_detail(key):
    """Show a single project's details, its versions with their progress, and its AI usage."""
    try:
        project = projects.get(_session(), key)
    except NotFoundError:
        abort(404)
    return _render_project(project)


def _form_pct(name):
    """Read an optional percentage from the current request's form.

    Checked here, before anything is saved, so a bad value saves nothing.

    Raises:
        ValidationError: If the value is set and isn't a whole number from 0 to 100.
    """
    value = (request.form.get(name) or "").strip()
    if not value:
        return None
    if not value.isdigit() or int(value) > 100:
        raise ValidationError(f"{name} must be a whole number between 0 and 100.")
    return int(value)


@bp.route("/projects/<key>/ai", methods=["POST"])
def project_ai_settings(key):
    """Save a project's AI settings: each domain's nature and each nature's target."""
    session = _session()
    try:
        project = projects.get(session, key)
    except NotFoundError:
        abort(404)
    try:
        bounds = {nature: (_form_pct(f"min_own_{nature.name}"), _form_pct(f"max_dependent_{nature.name}"))
                  for nature in Nature}
        for slug in ai.DOMAINS:
            name = request.form.get(f"nature_{slug}")
            if name in Nature.__members__:
                ai.set_domain_nature(session, key, slug, Nature[name])
        for nature, (low, high) in bounds.items():
            ai.set_target(session, key, nature, low, high)
    except ValidationError as e:
        session.rollback()
        return _render_project(project, str(e)), 400
    return redirect(url_for("pages.project_detail", key=key))


@bp.route("/projects/<key>/delete", methods=["POST"])
def project_delete(key):
    """Delete a project"""
    projects.delete(_session(), key)
    return redirect(url_for("pages.projects_list"))
