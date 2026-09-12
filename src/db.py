from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    """Shared declarative base; every model subclasses this so they all
    register their table into the same Base.metadata."""

    pass


def get_engine(database_url: str):
    """Create a SQLAlchemy engine for the given connection URL."""
    # SQLite forbids sharing a connection across threads by default; Flask's
    # dev server can serve a request on a different thread, so relax that.
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def get_session_factory(engine):
    """Build a thread-scoped session factory bound to the given engine."""
    # scoped_session gives one Session per thread automatically, which is
    # what a Flask app needs (one request = one thread = one session).
    return scoped_session(
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    )
