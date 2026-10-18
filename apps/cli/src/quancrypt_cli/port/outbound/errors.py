"""Errors of the outbound ports. Messages are safe to show: no token, no response body, no environment values."""

from __future__ import annotations


class ComposeError(Exception):
    """`docker compose` could not be run or did not succeed."""


class CoreApiError(Exception):
    """core-service did not register the project. `kind` is `unreachable`, `unauthorized` or `rejected`."""

    def __init__(self, kind: str, status: int | None = None) -> None:
        super().__init__(kind if status is None else f"{kind} (HTTP {status})")
        self.kind = kind
        self.status = status


class StateStoreError(Exception):
    """`.quancrypt/` could not be read or written, or is not what it should be (for example a symbolic link)."""
