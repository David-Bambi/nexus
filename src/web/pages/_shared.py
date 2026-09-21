from flask import Blueprint, current_app

# Full-page (non-fragment) routes. Adapters only: no business logic here —
# validate input, call a service, render a template (ADR-0001). Every module
# of this package registers its routes on this single blueprint.
bp = Blueprint("pages", __name__)

# Most rows a list page renders. Beyond that, pages get slow (spec §8: under
# 100 ms) and unreadable; a note tells the user the list was cut.
PAGE_LIMIT = 100


def _session():
    """Return this request's SQLAlchemy session, stashed on the app by create_app()."""
    return current_app.extensions["db_session"]
