from sqlalchemy.orm import Session

from src.app import create_app
from src.config import Config


def open_session(config_class : type[Config] = Config) -> Session:
    """Open a database session on the same database as the web service.

    Building the app also creates the data folder and applies pending
    migrations, so the CLI works even if it runs before the service has
    upgraded the database.

    Args:
        config_class: Config class to load settings from (defaults to
            `Config`, i.e. the production database).

    Returns:
        A new Session; the caller closes it.
    """
    app = create_app(config_class)
    return app.extensions["db_session"]()
