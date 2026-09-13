class DomainError(Exception):
    """Base class for all domain-level errors raised by services/."""

class ValidationError(DomainError):
    """Input is malformed or missing a required field."""
    
class ConflictError(DomainError):
    """Valid input conflicts with existing state (e.g. duplicate key)."""
    
class NotFoundError(DomainError):
    """Lookup by id/key/number found nothing."""
    
class InvalidTransitionError(DomainError):
      """Requested state change isn't allowed from the current state."""