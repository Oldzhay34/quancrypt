"""Gold labels of Model A (P7.1, D-25, D-322): the risk classes, the stratified sample of a label batch, the check of a
filled-in batch and Cohen's kappa of the double-labelled records.

Pure: no I/O, no framework."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

# The risk classes of crypto-domain section 1 (the labelling guideline is their definition).
RISK_CLASSES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
# Who labelled a record: the first labeller labels the whole batch, the second one the records marked for it.
FIRST, SECOND = "FIRST", "SECOND"
LABELERS = (FIRST, SECOND)
SAMPLE_SIZE = 300
DOUBLE_SIZE = 60
SEED = 42
MAX_NOTES = 500
MAX_LABELER_NAME = 64


@dataclass(frozen=True)
class Candidate:
    """A finding of marts.mart_risk_features that can be labelled (corpus and benchmark rows only, D-317h)."""

    finding_id: str
    project_key: str
    origin: str
    algorithm_family: str
    usage_context: str
    location_kind: str
    priority: str
    in_test_code: bool
    key_size_bits: int | None
    mode: str | None
    padding: str | None
    hash: str | None
    library: str | None
    confidence: float | None
    quantum_status: str
    hndl_exposure: bool

    @property
    def stratum(self) -> tuple[str, str, str, bool]:
        """The strata of the sample (D-322): algorithm family, usage context, origin and the test code flag."""
        return (self.algorithm_family, self.usage_context, self.origin, self.in_test_code)


@dataclass(frozen=True)
class SampledFinding:
    candidate: Candidate
    double_label: bool


def _allocate(sizes: Mapping[tuple[object, ...], int], total: int) -> dict[tuple[object, ...], int]:
    """Proportional allocation with the largest remainder: every stratum gets its share of `total`, rounded so that the
    shares add up exactly; ties are broken by the stratum key, so the result never depends on dictionary order."""
    population = sum(sizes.values())
    if population == 0 or total == 0:
        return dict.fromkeys(sizes, 0)
    exact = {key: size * total / population for key, size in sizes.items()}
    shares = {key: min(int(value), sizes[key]) for key, value in exact.items()}
    left = total - sum(shares.values())
    order = sorted(sizes, key=lambda key: (-(exact[key] - int(exact[key])), repr(key)))
    while left > 0:
        progressed = False
        for key in order:
            if left == 0:
                break
            if shares[key] < sizes[key]:
                shares[key] += 1
                left -= 1
                progressed = True
        if not progressed:
            break
    return shares


def stratified_sample(
    candidates: Iterable[Candidate], size: int = SAMPLE_SIZE, double: int = DOUBLE_SIZE, seed: int = SEED
) -> list[SampledFinding]:
    """`size` findings drawn proportionally from every stratum, `double` of them marked for the second labeller (drawn
    proportionally from the strata of the sample). The same candidates and seed give the same sample."""
    pool = sorted(candidates, key=lambda c: c.finding_id)
    by_stratum: dict[tuple[object, ...], list[Candidate]] = defaultdict(list)
    for candidate in pool:
        by_stratum[candidate.stratum].append(candidate)
    rng = random.Random(seed)  # noqa: S311 (a reproducible sample, not cryptography)
    shares = _allocate({key: len(rows) for key, rows in by_stratum.items()}, min(size, len(pool)))
    chosen: dict[tuple[object, ...], list[Candidate]] = {}
    for key in sorted(by_stratum, key=repr):
        chosen[key] = rng.sample(by_stratum[key], shares[key])
    doubles = _allocate({key: len(rows) for key, rows in chosen.items()}, min(double, sum(map(len, chosen.values()))))
    marked: set[str] = set()
    for key in sorted(chosen, key=repr):
        marked.update(c.finding_id for c in rng.sample(chosen[key], doubles[key]))
    sample = [SampledFinding(c, c.finding_id in marked) for rows in chosen.values() for c in rows]
    return sorted(sample, key=lambda s: s.candidate.finding_id)


# Why a row of the batch has no source context (CSV column `context_status`).
CONTEXT_OK = "ok"
CONTEXT_NO_LOCATION = "no-location"  # not a corpus finding, or a finding of a whole file (no line)
CONTEXT_UNAVAILABLE = "unavailable"  # the clone or the line is gone, or the analyzer refused the path
CONTEXT_RADIUS = 5


@dataclass(frozen=True)
class SourceLocation:
    """Where a corpus finding is: the analyzer root of its unit (/corpus/<clone>[/<unit>]) and the path below it."""

    root: str
    path: str
    line: int | None


@dataclass(frozen=True)
class BatchRow:
    """One row of an exported batch: the canonical fields, the real location and the redacted context."""

    sampled: SampledFinding
    location: SourceLocation | None
    context: tuple[tuple[int, str], ...]
    context_status: str


@dataclass(frozen=True)
class LabelRecord:
    finding_id: str
    label: str
    labeler_name: str
    notes: str | None


@dataclass(frozen=True)
class RowProblem:
    row: int
    reason: str


def check_labels(
    rows: Sequence[Mapping[str, str]], batch: Mapping[str, bool], labeler: str
) -> tuple[list[LabelRecord], list[RowProblem]]:
    """The records of a filled-in CSV that can be stored, and the problems of the others. `batch` maps every finding of
    the batch to its double-label mark; the second labeller may only label the marked ones. A label is one of the risk
    classes; the labeller's name and the label are required; a finding appears once."""
    records: list[LabelRecord] = []
    problems: list[RowProblem] = []
    seen: set[str] = set()
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        finding_id = (row.get("finding_id") or "").strip()
        label = (row.get("label") or "").strip().upper()
        name = (row.get("labeler") or "").strip()
        notes = (row.get("notes") or "").strip() or None
        if finding_id not in batch:
            problems.append(RowProblem(number, "finding_id is not in the batch"))
        elif labeler == SECOND and not batch[finding_id]:
            problems.append(RowProblem(number, "the second labeller labels only the double-label records"))
        elif finding_id in seen:
            problems.append(RowProblem(number, "finding_id appears twice"))
        elif label not in RISK_CLASSES:
            problems.append(RowProblem(number, "label must be one of " + ", ".join(RISK_CLASSES)))
        elif not name or len(name) > MAX_LABELER_NAME:
            problems.append(RowProblem(number, f"labeler is required (at most {MAX_LABELER_NAME} characters)"))
        elif notes is not None and len(notes) > MAX_NOTES:
            problems.append(RowProblem(number, f"notes has at most {MAX_NOTES} characters"))
        else:
            seen.add(finding_id)
            records.append(LabelRecord(finding_id, label, name, notes))
    expected = {fid for fid, double in batch.items() if labeler == FIRST or double}
    missing = expected - seen
    if missing:
        problems.append(RowProblem(0, f"{len(missing)} records of the batch have no valid label"))
    return records, problems


def cohen_kappa(first: Sequence[str], second: Sequence[str]) -> float:
    """Cohen's kappa of two labellings of the same records: (p_o - p_e) / (1 - p_e). Both labellers using one class only
    (p_e = 1) is perfect agreement when they agree everywhere."""
    if len(first) != len(second) or not first:
        raise ValueError("kappa needs two labellings of the same, non-empty set of records")
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / n
    first_counts, second_counts = Counter(first), Counter(second)
    expected = sum(first_counts[c] * second_counts[c] for c in set(first) | set(second)) / (n * n)
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return (observed - expected) / (1 - expected)


@dataclass(frozen=True)
class Agreement:
    pairs: int
    kappa: float
    observed: float
    disagreements: tuple[tuple[str, str, str], ...]  # (finding_id, first label, second label)


def agreement(first: Mapping[str, str], second: Mapping[str, str]) -> Agreement:
    """Kappa over the findings both labellers labelled, and the findings where they differ."""
    common = sorted(set(first) & set(second))
    a = [first[f] for f in common]
    b = [second[f] for f in common]
    kappa = cohen_kappa(a, b)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / len(common)
    differ = tuple((f, first[f], second[f]) for f in common if first[f] != second[f])
    return Agreement(len(common), kappa, observed, differ)


@dataclass(frozen=True)
class Resolution:
    finding_id: str
    label: str
    resolved_by: str
    notes: str | None


def check_resolutions(
    rows: Sequence[Mapping[str, str]], disagreements: Mapping[str, tuple[str, str]]
) -> tuple[list[Resolution], list[RowProblem]]:
    """The resolutions of a filled-in disagreement CSV. Only a record the two labellers disagree on can be resolved; a
    row left without a label is skipped (resolved later), a row with a label needs the resolver's name."""
    resolutions: list[Resolution] = []
    problems: list[RowProblem] = []
    seen: set[str] = set()
    for number, row in enumerate(rows, start=2):
        finding_id = (row.get("finding_id") or "").strip()
        label = (row.get("label") or "").strip().upper()
        name = (row.get("resolved_by") or "").strip()
        notes = (row.get("notes") or "").strip() or None
        if finding_id not in disagreements:
            problems.append(RowProblem(number, "finding_id is not a disagreement of the batch"))
        elif finding_id in seen:
            problems.append(RowProblem(number, "finding_id appears twice"))
        elif not label:
            continue
        elif label not in RISK_CLASSES:
            problems.append(RowProblem(number, "label must be one of " + ", ".join(RISK_CLASSES)))
        elif not name or len(name) > MAX_LABELER_NAME:
            problems.append(RowProblem(number, f"resolved_by is required (at most {MAX_LABELER_NAME} characters)"))
        elif notes is not None and len(notes) > MAX_NOTES:
            problems.append(RowProblem(number, f"notes has at most {MAX_NOTES} characters"))
        else:
            seen.add(finding_id)
            resolutions.append(Resolution(finding_id, label, name, notes))
    return resolutions, problems
