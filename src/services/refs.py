import re
import secrets

from sqlalchemy.orm import Session

from src.models.project import Project
from src.models.task import Task, TaskKind

# Lowercase base36 alphabet used for the code part of a ref.
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

# Ref prefix of a subproject.
SUBPROJECT = "s"

# Ref prefix of each kind of work item. Features and tasks share the task
# table and one code namespace: a task turned into a feature keeps its code
# ("t-4k2" becomes "f-4k2"), so either spelling still finds it.
KIND_PREFIXES = {TaskKind.FEATURE: "f", TaskKind.TASK: "t"}

# Code length of a fresh ref; grows by one every _ATTEMPTS_PER_LENGTH
# collisions so a crowded namespace never becomes a dead end.
_MIN_LENGTH = 3
_ATTEMPTS_PER_LENGTH = 5

# Shape of a ref: a prefix, a dash, then a base36 code.
_REF_PATTERN = re.compile(r"([sft])-([0-9a-z]{3,})")


def is_ref(text : str) -> bool:
    """Tell whether a string has the shape of a subproject, feature or task ref.

    Args:
        text: Any string, e.g. a command-line argument or a project key.

    Returns:
        True if it looks like "s-4k2", "f-4k2" or "t-4k2" (case-insensitive).
        It says nothing about whether such a row exists.
    """
    return _REF_PATTERN.fullmatch(normalize(text)) is not None


def normalize(ref : str) -> str:
    """Return a ref as stored: trimmed and lowercase.

    Args:
        ref: A ref as typed, e.g. " T-4K2 ".
    """
    return ref.strip().lower()


def prefix_of(ref : str) -> str:
    """Return the prefix letter of a ref ("s", "f" or "t").

    Args:
        ref: A string for which is_ref() is True.
    """
    return normalize(ref)[0]


def code_of(ref : str) -> str:
    """Return the code part of a ref, e.g. "4k2" for "t-4k2".

    Args:
        ref: A string for which is_ref() is True.
    """
    return normalize(ref)[2:]


def item_spellings(ref : str) -> list[str]:
    """Return every stored ref a feature or task ref may designate.

    Args:
        ref: A feature or task ref, e.g. "t-4k2".

    Returns:
        The ref under each work-item prefix, e.g. ["f-4k2", "t-4k2"].
    """
    code = code_of(ref)
    return [f"{prefix}-{code}" for prefix in KIND_PREFIXES.values()]


def with_kind(ref : str, kind : TaskKind) -> str:
    """Return a work item's ref respelled for a new kind, same code.

    Args:
        ref: Current ref of the item, e.g. "t-4k2".
        kind: The item's new kind.

    Returns:
        The ref with the kind's prefix, e.g. "f-4k2".
    """
    return f"{KIND_PREFIXES[kind]}-{code_of(ref)}"


def _is_taken(session : Session, prefix : str, code : str) -> bool:
    """Tell whether a code is already used in its namespace, stored or
    pending in the session.

    Args:
        session: Database session to use.
        prefix: Prefix the new ref will carry.
        code: Candidate code.
    """
    if prefix == SUBPROJECT:
        model, spellings = Project, [f"{SUBPROJECT}-{code}"]
    else:
        model, spellings = Task, item_spellings(f"{prefix}-{code}")

    if any(isinstance(obj, model) and obj.ref in spellings for obj in session.new):
        return True
    return session.query(model).filter(model.ref.in_(spellings)).first() is not None


def generate(session : Session, prefix : str) -> str:
    """Generate a short unique ref for a new row, e.g. "t-4k2".

    Args:
        session: Database session to use.
        prefix: SUBPROJECT, or a value of KIND_PREFIXES.

    Returns:
        A ref made of the prefix and a random base36 code, unused in its
        namespace.
    """
    attempt = 0
    while True:
        length = _MIN_LENGTH + attempt // _ATTEMPTS_PER_LENGTH
        code = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not _is_taken(session, prefix, code):
            return f"{prefix}-{code}"
        attempt += 1
