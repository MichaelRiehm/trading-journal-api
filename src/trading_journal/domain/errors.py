"""Domain errors raised by services. The API layer maps each one to an HTTP status."""


class DomainError(Exception):
    """Base class. `message` is safe to show to the client."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """The resource doesn't exist, or belongs to another user (deliberately the same)."""

    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found")


class ConflictError(DomainError):
    """The request clashes with existing state: a duplicate, or an illegal transition."""


class AuthenticationError(DomainError):
    """Missing or bad credentials. Never says which part was wrong."""
