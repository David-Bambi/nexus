from flask import Blueprint, current_app

from src.services import sizes

# Full-page (non-fragment) routes. Adapters only: no business logic here —
# validate input, call a service, render a template (see
# docs/concept/nexus/interfaces/service-layer.cpt). Every module
# of this package registers its routes on this single blueprint.
bp = Blueprint("pages", __name__)

# Most rows a list page renders. Beyond that, pages get slow (spec §8: under
# 100 ms) and unreadable; a note tells the user the list was cut.
PAGE_LIMIT = 100


@bp.record_once
def _size_guide(state):
    """Give every template, imported macros included, the task-size guide.

    A Jinja global is used rather than a context processor because macros
    imported without context can't see context-processor values.
    """
    state.app.jinja_env.globals.update(size_guide=sizes.SIZE_GUIDE)


def _session():
    """Return this request's SQLAlchemy session, stashed on the app by create_app()."""
    return current_app.extensions["db_session"]
