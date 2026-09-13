# Function declarations

The mental model behind `def`, grounded in `src/services/` and
`src/models/` rather than invented examples.

## Basic shape

```python
def name(params) -> ReturnType:
    """..."""
    ...
```

From `src/services/projects.py`:

```python
def get(session: Session, key: str) -> Project:
```

`session` and `key` are parameters; `-> Project` is the return type. None
of this is enforced at runtime — it's documentation the type checker
(and the next reader) relies on, not a guard Python inserts for you.

## Positional vs. default arguments

```python
def create(session: Session, key: str, name: str, description: str | None = None) -> Project:
```

`session`, `key`, `name` are positional: the caller must supply all
three, in order. `description` has a default (`None`), so it's optional —
callers can omit it (`create(session, "nexus", "Nexus")`) or pass it
(`create(session, "nexus", "Nexus", "A project manager")`). A parameter
with a default can't be followed by one without — Python rejects that at
definition time.

## Type hints

- Parameter annotations (`key: str`) and the return annotation
  (`-> Project`) are hints, checked by tools like mypy/pyright, not by the
  interpreter.
- `description: str | None = None` and `description: Optional[str] = None`
  mean the same thing — `str | None` is the newer syntax (Python 3.10+),
  `Optional[str]` (from `typing`) is the older one. This project targets
  3.12+ (`pyproject.toml`), so prefer `|` — see `src/services/projects.py`
  for `str | None` and `src/models/project.py` for `Optional[str]` still
  in use in the model layer's `Mapped[...]` annotations.

## Keyword-only arguments (`*`)

A bare `*` in the parameter list marks everything after it as
keyword-only — it can't be passed positionally:

```python
def list(session: Session, *, include_archived: bool = False) -> list:
```

Call sites must then write `projects.list(session, include_archived=True)`
— `projects.list(session, True)` is a `TypeError`. This is worth doing for
`include_archived` in particular: an unlabeled positional `bool` at a call
site (`projects.list(session, True)`) is meaningless to read without
checking the signature — this is the "boolean trap." Forcing the keyword
makes the call self-documenting at the cost of a few extra characters.
`src/services/projects.py`'s current `list()` takes `include_archived` as
a plain positional-or-keyword argument; adding the `*` is a candidate
follow-up, not yet done.

## `*args` / `**kwargs`

Python also lets a function collect any number of extra positional
arguments (`*args`, a tuple) or keyword arguments (`**kwargs`, a dict) it
wasn't given named parameters for. Useful for wrappers/decorators that
forward arguments they don't need to inspect. Not used anywhere in this
project currently, so not covered further here.

## Docstrings

This project's convention (root `CLAUDE.md`): every function, class, and
variable is commented. For functions/classes that means a triple-quoted
docstring right after the signature, e.g. `src/services/errors.py`:

```python
class ConflictError(DomainError):
    """Valid input conflicts with existing state (e.g. duplicate key)."""
```

or `src/services/projects.py`:

```python
def create(session: Session, key: str, name: str, description: str | None = None) -> Project:
    """Create a project. Raises ConflictError if the key is already taken."""
```

A docstring is a string literal the interpreter attaches to the
function/class object (accessible as `.__doc__`) — tools like
`mkdocstrings` (this site's `reference/` section) and `help()` read it. An
inline `#` comment is just source-level text the interpreter discards
entirely; it's for a note next to a line of code, not for describing what
a whole function does. `src/models/project.py`'s `# Short unique slug
used in URLs...` above the `key` column is that latter kind.
