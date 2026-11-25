"""Evaluation metrics of Model A (P7.2, ml-pipeline section 4): per-class precision, recall and F1, macro-F1, the
confusion matrix, a bootstrap confidence interval and the agreement of two runs. Pure Python, so the numbers of the
report never depend on a model library."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from quancrypt_ml.domain.labels import RISK_CLASSES, cohen_kappa

CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ClassScore:
    label: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class Evaluation:
    n: int
    macro_f1: float
    accuracy: float
    per_class: tuple[ClassScore, ...]
    confusion: tuple[tuple[int, ...], ...]  # rows: true class, columns: predicted class (RISK_CLASSES order)

    def recall(self, label: str) -> float:
        return next(c.recall for c in self.per_class if c.label == label)


def _ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


def evaluate(
    truth: Sequence[str], predicted: Sequence[str | None], classes: Sequence[str] = RISK_CLASSES
) -> Evaluation:
    """Scores of predictions against the truth. A missing prediction (an invalid LLM answer) counts as wrong. Macro-F1
    averages over the classes present in the truth (a class with no true record has no recall to average)."""
    if len(truth) != len(predicted) or not truth:
        raise ValueError("evaluation needs one prediction per true label, and at least one")
    pairs = Counter(zip(truth, predicted, strict=True))
    scores = []
    for label in classes:
        tp = pairs[(label, label)]
        support = sum(n for (t, _), n in pairs.items() if t == label)
        predicted_as = sum(n for (_, p), n in pairs.items() if p == label)
        precision, recall = _ratio(tp, predicted_as), _ratio(tp, support)
        f1 = _ratio(2 * tp, support + predicted_as)
        scores.append(ClassScore(label, precision, recall, f1, support))
    present = [s for s in scores if s.support]
    macro = sum(s.f1 for s in present) / len(present)
    accuracy = sum(n for (t, p), n in pairs.items() if t == p) / len(truth)
    confusion = tuple(tuple(pairs[(t, p)] for p in classes) for t in classes)
    return Evaluation(len(truth), macro, accuracy, tuple(scores), confusion)


def bootstrap_interval(
    truth: Sequence[str],
    predicted: Sequence[str | None],
    statistic: Callable[[Evaluation], float],
    samples: int = 1000,
    seed: int = 42,
    level: float = 0.95,
) -> tuple[float, float]:
    """Percentile bootstrap interval of a statistic over records drawn with replacement (fixed seed)."""
    rng = random.Random(seed)  # noqa: S311 (a reproducible resample, not cryptography)
    n = len(truth)
    values = []
    for _ in range(samples):
        picks = [rng.randrange(n) for _ in range(n)]
        values.append(statistic(evaluate([truth[i] for i in picks], [predicted[i] for i in picks])))
    values.sort()
    low = values[int((1 - level) / 2 * samples)]
    high = values[min(samples - 1, int((1 + level) / 2 * samples))]
    return low, high


@dataclass(frozen=True)
class RunAgreement:
    """How two runs of the same classifier on the same records agree (research question 2: consistency)."""

    n: int
    identical: float  # share of records with the same answer
    kappa: float | None  # Cohen's kappa over the records both runs answered validly


def agreement(first: Sequence[str | None], second: Sequence[str | None]) -> RunAgreement:
    if len(first) != len(second) or not first:
        raise ValueError("agreement needs two runs over the same, non-empty records")
    identical = sum(a == b for a, b in zip(first, second, strict=True)) / len(first)
    valid = [(a, b) for a, b in zip(first, second, strict=True) if a is not None and b is not None]
    kappa = cohen_kappa([a for a, _ in valid], [b for _, b in valid]) if valid else None
    return RunAgreement(len(first), identical, kappa)


def macro_f1(evaluation: Evaluation) -> float:
    return evaluation.macro_f1


def critical_recall(evaluation: Evaluation) -> float:
    return evaluation.recall(CRITICAL)
