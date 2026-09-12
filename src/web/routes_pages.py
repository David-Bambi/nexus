from flask import Blueprint, render_template

# Full-page (non-fragment) routes. Adapters only: no model/service imports,
# no business logic — just render a template.
bp = Blueprint("pages", __name__)


@bp.route("/")
def home():
    """Empty home page for the 0.1.0 foundation increment."""
    return render_template("base.html")
