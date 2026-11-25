"""The project split of Model A (P7.2, ml-pipeline section 2): the findings of one project are never in training and
test at once. The split itself is drawn by the infrastructure (scikit-learn); the domain checks it and selects the
model."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from quancrypt_ml.domain.risk_features import RiskRow


@dataclass(frozen=True)
class ProjectSplit:
    train_projects: frozenset[str]
    test_projects: frozenset[str]


def leaked_projects(split: ProjectSplit) -> set[str]:
    """Projects on both sides (must be empty)."""
    return set(split.train_projects & split.test_projects)


def partition(rows: Iterable[RiskRow], split: ProjectSplit) -> tuple[list[RiskRow], list[RiskRow]]:
    """Training and test rows; a row of a project the split does not know is a broken split."""
    train, test = [], []
    for row in rows:
        if row.project_key in split.test_projects:
            test.append(row)
        elif row.project_key in split.train_projects:
            train.append(row)
        else:
            raise ValueError("a row belongs to a project the split does not cover")
    return train, test


@dataclass(frozen=True)
class CandidateScore:
    algorithm: str
    mean_macro_f1: float
    mean_critical_recall: float


def best_candidate(candidates: Sequence[CandidateScore]) -> CandidateScore:
    """The selection rule of D-327e: the highest mean validation macro-F1; on a tie the higher Critical recall; then the
    algorithm name (deterministic)."""
    if not candidates:
        raise ValueError("no candidate to select")
    return sorted(
        candidates, key=lambda c: (-round(c.mean_macro_f1, 12), -round(c.mean_critical_recall, 12), c.algorithm)
    )[0]
