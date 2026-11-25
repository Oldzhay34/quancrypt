"""Model B (P7.3, H4): the threshold, the UNSURE band and the metrics of the scope classifier.

The positive class is OUT_OF_SCOPE: a request is denied when its out-of-scope probability is at least the threshold.
The threshold is chosen on the validation set only (D-332a): among the thresholds that keep the out-of-scope recall
at least 98 %, the one with the fewest false rejects; on a tie the lower one (the safer). The UNSURE band (D-332c) sends
the requests between two bounds to ring 3: below `low` no validation out-of-scope request is allowed, at or above
`high` no validation in-scope request is denied."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from quancrypt_ml.domain.scope import IN_SCOPE, OUT_OF_SCOPE

TARGET_RECALL = 0.98
MAX_FALSE_REJECT_RATE = 0.05
ALLOW, UNSURE, DENY = "ALLOW", "UNSURE", "DENY"
ALL, TR, EN, JAILBREAK, BOUNDARY = "ALL", "TR", "EN", "JAILBREAK", "BOUNDARY"
SLICES = (ALL, TR, EN, JAILBREAK, BOUNDARY)
# D-332b: the calibrated linear SVM replaces the logistic regression only with more than one fewer false reject.
SVM_MARGIN_RECORDS = 1


@dataclass(frozen=True)
class Scored:
    """One request with its true label and the model's out-of-scope probability."""

    label: str
    lang: str
    category: str
    p_out: float


@dataclass(frozen=True)
class BinaryScore:
    out_of_scope: int
    in_scope: int
    caught: int  # out-of-scope requests denied
    false_rejects: int  # in-scope requests denied

    @property
    def recall(self) -> float | None:
        return self.caught / self.out_of_scope if self.out_of_scope else None

    @property
    def false_reject_rate(self) -> float | None:
        return self.false_rejects / self.in_scope if self.in_scope else None


@dataclass(frozen=True)
class Band:
    low: float  # p_out below low: ALLOW
    threshold: float  # the binary decision (H4): p_out at least threshold: DENY
    high: float  # p_out at least high: DENY; between low and high: UNSURE


@dataclass(frozen=True)
class ThreeWay:
    allowed_out: int  # out-of-scope requests ring 2 allows (must stay rare)
    unsure_out: int
    denied_out: int
    allowed_in: int
    unsure_in: int
    denied_in: int  # in-scope requests ring 2 denies itself

    @property
    def unsure_rate(self) -> float:
        total = self.allowed_out + self.unsure_out + self.denied_out + self.allowed_in + self.unsure_in + self.denied_in
        return (self.unsure_out + self.unsure_in) / total if total else 0.0


def binary(scored: Iterable[Scored], threshold: float) -> BinaryScore:
    out = inside = caught = rejected = 0
    for s in scored:
        denied = s.p_out >= threshold
        if s.label == OUT_OF_SCOPE:
            out, caught = out + 1, caught + denied
        else:
            inside, rejected = inside + 1, rejected + denied
    return BinaryScore(out, inside, caught, rejected)


def select_threshold(validation: Sequence[Scored]) -> float:
    """The lowest-false-reject threshold that keeps the validation out-of-scope recall at least 98 %."""
    if not any(s.label == OUT_OF_SCOPE for s in validation):
        raise ValueError("the validation set has no out-of-scope request")
    best: tuple[int, float] | None = None
    for candidate in sorted({s.p_out for s in validation}):
        score = binary(validation, candidate)
        if score.recall is None or score.recall < TARGET_RECALL:
            continue
        key = (score.false_rejects, candidate)
        if best is None or key < best:
            best = key
    if best is None:  # cannot happen: the lowest out-of-scope probability keeps the recall at 100 %
        raise ValueError("no threshold keeps the out-of-scope recall")
    return best[1]


def unsure_band(validation: Sequence[Scored], threshold: float) -> Band:
    out = [s.p_out for s in validation if s.label == OUT_OF_SCOPE]
    inside = [s.p_out for s in validation if s.label == IN_SCOPE]
    low = min(out) if out else threshold
    high = math.nextafter(max(inside), math.inf) if inside else threshold
    return Band(low=min(low, threshold), threshold=threshold, high=max(high, threshold))


def decide(p_out: float, band: Band) -> str:
    if p_out < band.low:
        return ALLOW
    if p_out >= band.high:
        return DENY
    return UNSURE


def three_way(scored: Iterable[Scored], band: Band) -> ThreeWay:
    counts = {(label, d): 0 for label in (OUT_OF_SCOPE, IN_SCOPE) for d in (ALLOW, UNSURE, DENY)}
    for s in scored:
        counts[(OUT_OF_SCOPE if s.label == OUT_OF_SCOPE else IN_SCOPE, decide(s.p_out, band))] += 1
    return ThreeWay(
        counts[(OUT_OF_SCOPE, ALLOW)], counts[(OUT_OF_SCOPE, UNSURE)], counts[(OUT_OF_SCOPE, DENY)],
        counts[(IN_SCOPE, ALLOW)], counts[(IN_SCOPE, UNSURE)], counts[(IN_SCOPE, DENY)],
    )  # fmt: skip


def slice_of(scored: Sequence[Scored], name: str) -> list[Scored]:
    if name == ALL:
        return list(scored)
    if name in (TR, EN):
        return [s for s in scored if s.lang == name.lower()]
    return [s for s in scored if s.category == name.lower()]


def breakdown(scored: Sequence[Scored], threshold: float) -> dict[str, BinaryScore]:
    """The binary scores of every slice: all, Turkish, English, jailbreak and boundary requests."""
    return {name: binary(slice_of(scored, name), threshold) for name in SLICES}


def roc_auc(scored: Sequence[Scored]) -> float | None:
    """The probability that an out-of-scope request scores above an in-scope one (ties count half)."""
    out = [s.p_out for s in scored if s.label == OUT_OF_SCOPE]
    inside = [s.p_out for s in scored if s.label == IN_SCOPE]
    if not out or not inside:
        return None
    wins = sum(1.0 if o > i else 0.5 if o == i else 0.0 for o in out for i in inside)
    return wins / (len(out) * len(inside))


@dataclass(frozen=True)
class Candidate:
    algorithm: str
    threshold: float
    validation: BinaryScore


def pick(default: Candidate, challenger: Candidate) -> Candidate:
    """D-332b: the challenger only with more than SVM_MARGIN_RECORDS fewer validation false rejects."""
    if default.validation.false_rejects - challenger.validation.false_rejects > SVM_MARGIN_RECORDS:
        return challenger
    return default


def h4_met(test: BinaryScore) -> bool:
    recall, rate = test.recall, test.false_reject_rate
    return recall is not None and rate is not None and recall >= TARGET_RECALL and rate <= MAX_FALSE_REJECT_RATE
