"""Typed application errors with safe (content-free) HTTP responses."""
from __future__ import annotations


class TraceVaultError(Exception):
    """Base error carrying a machine code, HTTP status and safe message."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "", *, code: str | None = None,
                 status_code: int | None = None) -> None:
        self.message = message or self.__class__.__name__
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        super().__init__(self.message)


class NotFound(TraceVaultError):
    status_code = 404
    code = "not_found"


class ValidationFailed(TraceVaultError):
    status_code = 422
    code = "validation_failed"


class AuthFailed(TraceVaultError):
    status_code = 401
    code = "auth_failed"


class Forbidden(TraceVaultError):
    status_code = 403
    code = "forbidden"


class Conflict(TraceVaultError):
    status_code = 409
    code = "conflict"


class IdempotencyConflict(Conflict):
    code = "idempotency_conflict"


class ContentBlocked(TraceVaultError):
    """A tombstoned/invalidated document or artifact was requested.

    Content-free by contract: never includes the blocked content.
    """

    status_code = 410
    code = "content_blocked"


class PublicationBlocked(TraceVaultError):
    """The publication gate refused a write because a deletion fence committed."""

    status_code = 409
    code = "publication_blocked"


class AdapterUnavailable(TraceVaultError):
    """An AI/storage adapter is unavailable; response includes actionable guidance."""

    status_code = 503
    code = "adapter_unavailable"


class ConnectorUnavailable(TraceVaultError):
    status_code = 503
    code = "connector_unavailable"


class UnsupportedContent(TraceVaultError):
    status_code = 415
    code = "unsupported_content"
