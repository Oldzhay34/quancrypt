from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EnvelopeValidator(Protocol):
    """Checks a whole envelope against contracts/schemas/events/<event_type>.json."""

    def knows(self, event_type: str) -> bool: ...

    def violations(self, item: object) -> Sequence[str]:
        """The reasons the envelope fails its schema, each naming a path and a rule, never a value. Empty when valid."""
        ...
