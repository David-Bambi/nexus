from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, scoped_session, sessionmaker


class Base(DeclarativeBase):
    """Shared declarative base; every model subclasses this so they all
    register their table into the same Base.metadata."""

    pass


def get_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for the given connection URL.

    Args:
        database_url: SQLAlchemy connection URL (e.g. a `sqlite:///` path).

    Returns:
        A configured `Engine`, ready to bind to a session factory.
    """
    # SQLite forbids sharing a connection across threads by default; Flask's
    # dev server can serve a request on a different thread, so relax that.
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)

    # WAL lets readers and the writer work at the same time, and survives a
    # crash better than the default journal. It needs a real file, so
    # in-memory databases are left alone.
    if engine.dialect.name == "sqlite" and engine.url.database not in (None, "", ":memory:"):
        @event.listens_for(engine, "connect")
        def _enable_wal(dbapi_connection, connection_record):
            """Switch each new SQLite connection to write-ahead logging."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def get_session_factory(engine: Engine) -> scoped_session[Session]:
    """Build a thread-scoped session factory bound to the given engine.

    Args:
        engine: SQLAlchemy `Engine` to bind sessions to.

    Returns:
        A `scoped_session` yielding one `Session` per thread.
    """
    # scoped_session gives one Session per thread automatically, which is
    # what a Flask app needs (one request = one thread = one session).
    return scoped_session(
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    )
