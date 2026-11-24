"""Inbound port of the scope data set (P7.1): validate it and split it by paraphrase group."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ScopeSplitError(Exception):
    """The data set is not valid or a split leaks a paraphrase group."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("; ".join(problems[:10]))
        self.problems = problems


@dataclass(frozen=True)
class SplitCommand:
    dataset: Path
    output_dir: Path  # train.jsonl, val.jsonl, test.jsonl and review_sample.jsonl
    test_copy: Path  # the agent-service test set (data/examples/scope_set.jsonl); ml/ is its only source
    seed: int


@dataclass(frozen=True)
class SplitResult:
    records: int
    groups: int
    counts: Mapping[str, Mapping[str, int]]  # split -> label -> records
    review_sample: int


class SplitScopeDatasetUseCase(Protocol):
    def execute(self, command: SplitCommand) -> SplitResult: ...
