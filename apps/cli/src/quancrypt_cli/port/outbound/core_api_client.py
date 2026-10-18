"""Outbound port: core-service, the shared blackboard (project registration only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quancrypt_cli.domain.session_token import SessionToken


@dataclass(frozen=True)
class RegisteredProject:
    id: str
    created: bool  # False: the same project identity was registered before (core answers 200, D-129)


class CoreApiClient(Protocol):
    def register_project(self, token: SessionToken, identity: str, display_name: str) -> RegisteredProject:
        """`POST /api/v1/projects`; repeating it is safe (idempotent). Raises `CoreApiError`."""
        ...
