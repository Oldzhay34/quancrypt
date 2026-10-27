from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class RandomIdGenerator:
    def new_id(self) -> UUID:
        return uuid.uuid4()
