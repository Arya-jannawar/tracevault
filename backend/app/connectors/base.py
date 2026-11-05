"""Connector interface + shared error types."""
from __future__ import annotations

from ..errors import ConnectorUnavailable


class ConnectorOutcome:
    """Structured result of a connector operation (acknowledgement semantics)."""

    def __init__(self, ok: bool, *, acknowledged: bool, detail: str = "",
                 error_code: str | None = None) -> None:
        self.ok = ok
        self.acknowledged = acknowledged  # the remote store confirmed completion
        self.detail = detail
        self.error_code = error_code

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "acknowledged": self.acknowledged,
            "detail": self.detail,
            "error_code": self.error_code,
        }


def wrap_unavailable(exc: Exception, connector: str) -> ConnectorUnavailable:
    return ConnectorUnavailable(
        f"{connector} connector is unavailable: {exc.__class__.__name__}",
        code=f"{connector}_unavailable",
    )
