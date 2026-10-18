"""Shared result value of the use cases that look at the services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    healthy: bool
    detail: str
