"""Domain errors. Their message is always safe to show to the user."""

from __future__ import annotations


class WorkTrackError(Exception):
    """Base class: `str(exc)` is a clear, user-facing message (Spanish)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(WorkTrackError):
    pass


class NotFoundError(WorkTrackError):
    pass


class ActiveSessionExistsError(WorkTrackError):
    def __init__(
        self, message: str = "Ya hay una sesión activa. Detenela antes de iniciar otra."
    ) -> None:
        super().__init__(message)


class NoActiveSessionError(WorkTrackError):
    def __init__(self, message: str = "No hay ninguna sesión activa.") -> None:
        super().__init__(message)


class OverlapError(WorkTrackError):
    pass


class TaskProjectMismatchError(WorkTrackError):
    def __init__(
        self, message: str = "La tarea no pertenece al proyecto seleccionado (o ya no existe)."
    ) -> None:
        super().__init__(message)


class InUseError(WorkTrackError):
    """Delete blocked because other records reference this one (ON DELETE RESTRICT)."""


class DuplicateNameError(WorkTrackError):
    pass


class IntegrityViolation(WorkTrackError):
    pass
