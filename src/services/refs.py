import secrets

from sqlalchemy.orm import Session

from src.models.task import Task
from src.models.version import Version

# Lowercase base36 alphabet used for the code part of a ref.
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

# Ref prefix for each referable model.
_PREFIXES = {Task: "t", Version: "v"}

# Code length of a fresh ref; grows by one every _ATTEMPTS_PER_LENGTH
# collisions so a crowded namespace never becomes a dead end.
_MIN_LENGTH = 3
_ATTEMPTS_PER_LENGTH = 5


def _is_taken(session : Session, model : type, ref : str) -> bool:
    """Tell whether a ref is already used, stored or pending in the session.

    Args:
        session: Database session to use.
        model: The model the ref belongs to (Task or Version).
        ref: Candidate ref.
    """
    if any(isinstance(obj, model) and obj.ref == ref for obj in session.new):
        return True
    return session.query(model).filter_by(ref=ref).first() is not None


def generate(session : Session, model : type) -> str:
    """Generate a short unique ref for a new row, e.g. "t-4k2".

    Args:
        session: Database session to use.
        model: The model to generate for (Task or Version).

    Returns:
        A ref made of the model's prefix and a random base36 code, unused in
        the model's table.
    """
    prefix = _PREFIXES[model]
    attempt = 0
    while True:
        length = _MIN_LENGTH + attempt // _ATTEMPTS_PER_LENGTH
        code = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        ref = f"{prefix}-{code}"
        if not _is_taken(session, model, ref):
            return ref
        attempt += 1
