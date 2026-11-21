"""Routes of a project's version block: major criteria and major release."""

from flask import abort, request

from src.services import versioning
from src.services.errors import NotFoundError
from src.web.pages._shared import _session, bp
from src.web.pages.projects import _project_action


def _criterion_of(session, key, criterion_id):
    """Look up a criterion of a given project, or answer 404.

    Args:
        session: Database session to use.
        key: Key of the project the criterion must belong to.
        criterion_id: Id of the criterion.
    """
    try:
        criterion = versioning.get_criterion(session, criterion_id)
    except NotFoundError:
        abort(404)
    if criterion.project.key != key:
        abort(404)
    return criterion


@bp.route("/projects/<key>/criteria", methods=["POST"])
def criterion_add(key):
    """Add a criterion for the project's next major version."""
    return _project_action(key, lambda s: versioning.add_criterion(s, key, request.form.get("text", "")),
                           anchor="criteria", form="add-criterion")


@bp.route("/projects/<key>/criteria/<int:criterion_id>/update", methods=["POST"])
def criterion_update(key, criterion_id):
    """Change a criterion's text."""
    _criterion_of(_session(), key, criterion_id)
    return _project_action(
        key, lambda s: versioning.update_criterion(s, criterion_id, request.form.get("text", "")),
        anchor="criteria")


@bp.route("/projects/<key>/criteria/<int:criterion_id>/check", methods=["POST"])
def criterion_check(key, criterion_id):
    """Check a criterion (form field done=1) or uncheck it (done=0)."""
    _criterion_of(_session(), key, criterion_id)
    done = request.form.get("done") == "1"
    return _project_action(key, lambda s: versioning.set_criterion_done(s, criterion_id, done),
                           anchor="criteria")


@bp.route("/projects/<key>/criteria/<int:criterion_id>/delete", methods=["POST"])
def criterion_delete(key, criterion_id):
    """Delete a criterion."""
    _criterion_of(_session(), key, criterion_id)
    return _project_action(key, lambda s: versioning.delete_criterion(s, criterion_id), anchor="criteria")


@bp.route("/projects/<key>/release", methods=["POST"])
def project_release(key):
    """Move the project to its next major version."""
    return _project_action(key, lambda s: versioning.release_major(s, key), status=409)
