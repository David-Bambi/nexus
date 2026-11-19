import os
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from flask import Flask
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from src.config import Config
from src.db import get_engine, get_session_factory
from src.mcp_server.http import bp as mcp_bp
from src.web.pages import bp as pages_bp

# Repo root, used to locate alembic.ini regardless of the working directory.
BASE_DIR = Path(__file__).resolve().parent.parent


class UnsupportedDatabaseError(RuntimeError):
    """The database was made by a Nexus version this code can't migrate
    (e.g. a 1.x database met by Nexus 2.0)."""


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

    # SQLite creates the database file but not its folder (e.g. ~/.nexus on
    # first run).
    _ensure_database_folder(app.config["DATABASE_URL"])

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
    app.register_blueprint(mcp_bp)

    return app


def _ensure_database_folder(database_url: str) -> None:
    """Create the folder of a file-based SQLite database if it is missing.

    Args:
        database_url: SQLAlchemy connection URL. Anything other than a
            SQLite file (another database, or in memory) is ignored.
    """
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def _upgrade_database(database_url: str) -> None:
    """Run pending migrations up to head. Idempotent, safe on every start.

    Args:
        database_url: SQLAlchemy connection URL to migrate.
    """
    alembic_cfg = AlembicConfig(str(BASE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    # Keep the app's own logging setup: env.py would otherwise replace it
    # with the one from alembic.ini.
    alembic_cfg.attributes["configure_logger"] = False
    _refuse_unknown_revision(database_url, ScriptDirectory.from_config(alembic_cfg))
    command.upgrade(alembic_cfg, "head")


def _refuse_unknown_revision(database_url: str, scripts: ScriptDirectory) -> None:
    """Refuse a database stamped with a migration this code doesn't know.

    Nexus 2.0 restarted its migration history, so a 1.x database carries a
    revision that no longer exists. Alembic would fail with an obscure
    error; this one says what to do.

    Args:
        database_url: SQLAlchemy connection URL to check.
        scripts: The app's migration scripts.

    Raises:
        UnsupportedDatabaseError: If the database's revision is unknown.
    """
    engine = get_engine(database_url)
    try:
        with engine.connect() as connection:
            if not inspect(connection).has_table("alembic_version"):
                return
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()

    known = {script.revision for script in scripts.walk_revisions()}
    if revision is not None and revision not in known:
        raise UnsupportedDatabaseError(
            f"The database {database_url} was made by an older Nexus (migration "
            f"'{revision}'). Nexus 2.0 starts on an empty database: archive this "
            "file (see README, \"Upgrade from 1.x\") and start again.")
