from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class TransactionRunner(Protocol):
    def run[T](self, work: Callable[[], T]) -> T:
        """Run `work` in one transaction: commit when it returns, roll back and re-raise when it raises.

        A call made while a transaction is open joins it; only the outermost call commits, and only it repeats the
        work (at most once) after a deadlock or serialization failure, so `work` must be safe to run again."""
        ...
