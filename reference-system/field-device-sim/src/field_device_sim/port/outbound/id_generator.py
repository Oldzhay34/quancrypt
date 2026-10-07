"""Outbound port: identifiers for new transactions."""

from __future__ import annotations

from typing import Protocol


class IdGenerator(Protocol):
    """Source of transaction identifiers."""

    def new_id(self) -> str:
        """A new UUID (version 4) as lower case text in canonical form."""
        ...
