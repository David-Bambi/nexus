import os
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from flask import Flask

from src.config import Config
from src.db import get_engine, get_session_factory
from src.web.routes_pages import bp as pages_bp

# Repo root, used to locate alembic.ini regardless of the working directory.
BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(config_class: type[Config] = Config) -> Flask:
    """Application factory: build and configure the Flask app.

    Args:
        config_class: Config class to load settings from (defaults to
            `Config`; tests pass `TestConfig`).

    Returns:
        A fully configured Flask app, with the database engine/session
        factory attached and blueprints registered.
    """
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
        instance_relative_config=True,
    )
    app.config.from_object(config_class)

    # Ensure the instance/ folder exists before SQLite tries to create the
    # database file there.
    os.makedirs(app.instance_path, exist_ok=True)

    # Skip in tests: an in-memory DB can't be migrated and then reopened by
    # a second connection — tests create tables directly instead.
    if not app.config.get("TESTING"):
        _upgrade_database(app.config["DATABASE_URL"])

    engine = get_engine(app.config["DATABASE_URL"])
    session_factory = get_session_factory(engine)
    app.extensions["db_engine"] = engine
    app.extensions["db_session"] = session_factory

    @app.teardown_appcontext
    def _remove_session(exception=None):
        """Release the thread-local session at the end of each request."""
        session_factory.remove()

    app.register_blueprint(pages_bp)

    return app


def _upgrade_database(database_url: str) -> None:
    """Run pending migrations up to head. Idempotent, safe on every start.

    Args:
        database_url: SQLAlchemy connection URL to migrate.
    """
    alembic_cfg = AlembicConfig(str(BASE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")
