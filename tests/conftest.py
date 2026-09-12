import pytest

from src.app import create_app
from src.config import TestConfig
from src.db import Base


@pytest.fixture
def app():
    """Flask app for tests: in-memory DB, tables created directly (no
    Alembic replay) so each test starts from a clean, fast schema."""
    app = create_app(TestConfig)
    engine = app.extensions["db_engine"]
    Base.metadata.create_all(engine)
    yield app
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(app):
    """Flask test client bound to the app fixture."""
    return app.test_client()
