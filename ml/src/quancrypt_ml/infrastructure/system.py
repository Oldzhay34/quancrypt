"""Clock and IdGenerator of the command line."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class RandomIdGenerator:
    def new_id(self) -> str:
        return str(uuid.uuid4())
