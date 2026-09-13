# Context managers (`with`)

`with` is plain Python syntax, not something pytest or SQLAlchemy invented
— they just provide objects that plug into it. It implements a single
pattern: **acquire something, use it, always release it** — even if the
code in between raises.

## The protocol

Any object with `__enter__(self)` and `__exit__(self, exc_type, exc_value,
traceback)` can follow `with`:

```python
with resource as x:
    ...
```

- `resource.__enter__()` runs first; its return value is what `as x` binds.
- `__exit__` always runs when the block exits — normally or via exception.
- If `__exit__` returns `True`, the exception (if any) is swallowed instead
  of propagating.

## Real examples in this repo

**Closing a connection** — `src/migrations/env.py:71`:

```python
with connectable.connect() as connection:
    ...
```
`__enter__` returns the open `Connection`; `__exit__` closes it whether
`context.configure`/`run_migrations` below succeeds or raises.

**Commit-or-rollback a transaction** — `src/migrations/env.py:54,76`:

```python
with context.begin_transaction():
    context.run_migrations()
```
`__enter__` starts the transaction; `__exit__` commits if the block
finished cleanly, rolls back if it raised.

**Asserting an exception is raised** — `tests/test_project.py:13`:

```python
with pytest.raises(ConflictError):
    projects.create(session, "nexus", "Nexus", "")
```
Here `__exit__` *is* the assertion: it checks the exception type raised
inside the block matches `ConflictError`, raises `AssertionError` if the
block raised nothing (or the wrong type), and returns `True` to swallow
the expected `ConflictError` so it doesn't propagate further.

## Writing your own

### Class-based

Sketch of a session-scope helper for this project's SQLAlchemy sessions
(not currently in `src/`, but this is the shape a `services/`-level
helper would take):

```python
class session_scope:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def __enter__(self):
        self.session = self.session_factory()
        return self.session

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()
```

```python
with session_scope(get_session_factory(engine)) as session:
    projects.create(session, "nexus", "Nexus", "")
```

### `@contextlib.contextmanager` shortcut

Same behavior, written as a generator with one `yield`: code before
`yield` is `__enter__`, code after — in a `try`/`finally` — is `__exit__`.

```python
from contextlib import contextmanager

@contextmanager
def session_scope(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

Used identically to the class-based version above.

Context managers can also nest (`with a() as x, b() as y:`) and `__exit__`
can selectively suppress exceptions — not covered here, see the
[`contextlib` docs](https://docs.python.org/3/library/contextlib.html)
when needed.
