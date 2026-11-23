"""Profiling of the landing layer (P6.3, data-preprocessing section 2): what raw holds, measured, never changed.

The records below are what the reader extracts from raw; the functions compute the metrics of the report. Pure: no
I/O, no framework. The recommendations are derived from the numbers only; each names the preprocessing filter it
would feed (data-preprocessing section 3) and the evidence, and a filter without evidence gets no recommendation.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

# Directories whose findings are generated or build output (data-preprocessing section 3, GeneratedCodeExcluder).
GENERATED_SEGMENTS = frozenset({"target", "build", "out", "node_modules", "generated"})
# A project is an outlier candidate when its finding count is above Q3 + 3 x IQR (OutlierFlagger).
OUTLIER_IQR_FACTOR = 3.0
# Quartiles need a few projects to mean anything.
MIN_PROJECTS_FOR_OUTLIERS = 4
# An algorithm-name spelling as the analyzer copies it from code (D-193g); its own labels (`https://`,
# `SSLContext:TLS`, `JKS keystore`) have a colon or a space and are not spellings of an algorithm.
_ALGORITHM_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,63}")


@dataclass(frozen=True)
class SourceSummary:
    """One event type of raw.event: how many rows, over which time, in which schema versions."""

    source: str
    event_type: str
    count: int
    first_at: datetime | None
    last_at: datetime | None
    schema_versions: tuple[int, ...]


@dataclass(frozen=True)
class FindingRecord:
    """A crypto finding as raw holds it. Corpus and benchmark findings carry the spelling and the path; a core
    `finding_detected` event carries coded fields only (its text fields are None)."""

    source: str
    project_key: str
    algorithm_family: str
    usage_context: str
    location_kind: str
    priority: str
    key_size_bits: int | None
    confidence: float | None
    file: str | None = None
    line_start: int | None = None
    raw_name: str | None = None
    mode: str | None = None
    padding: str | None = None
    hash: str | None = None
    library: str | None = None


@dataclass(frozen=True)
class TopologyRecord:
    source: str
    project_key: str
    node_count: int
    edge_count: int
    tls_edge_count: int | None
    mtls_edge_count: int | None


@dataclass(frozen=True)
class RuntimeRecord:
    source: str
    project_key: str
    java_version: str | None
    spring_boot_version: str | None


@dataclass(frozen=True)
class ScopeRecord:
    decision: str
    deciding_ring: str
    confidence: float | None
    latency_ms: int
    language: str


@dataclass(frozen=True)
class LabelRecord:
    benchmark: str
    case_id: str
    file_path: str | None
    category: str | None
    cwe: int | None
    expected_vulnerable: bool


@dataclass(frozen=True)
class QuarantineRecord:
    error_code: str
    error_message: str


@dataclass(frozen=True)
class TableChecksum:
    """A table's row count and a digest of its rows in key order: equal before and after means nothing was changed."""

    table: str
    rows: int
    digest: str


@dataclass(frozen=True)
class TextSample:
    """A text value of raw that the secret and personal-data scan looks at (where it came from, never shown)."""

    where: str
    text: str


@dataclass(frozen=True)
class RawSnapshot:
    sources: tuple[SourceSummary, ...] = ()
    findings: tuple[FindingRecord, ...] = ()
    topologies: tuple[TopologyRecord, ...] = ()
    runtimes: tuple[RuntimeRecord, ...] = ()
    scopes: tuple[ScopeRecord, ...] = ()
    labels: tuple[LabelRecord, ...] = ()
    quarantine: tuple[QuarantineRecord, ...] = ()
    texts: tuple[TextSample, ...] = ()
    # Every project key of raw.event, findings or not: the base of "N of M projects have findings".
    project_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ColumnProfile:
    table: str
    column: str
    kind: str
    count: int
    nulls: int
    distinct: int
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    median: float | None = None
    skewness: float | None = None

    @property
    def null_ratio(self) -> float:
        return self.nulls / self.count if self.count else 0.0


def column_profile(table: str, column: str, values: Sequence[object]) -> ColumnProfile:
    """Type, null share and distinct values; for numbers also min, max, mean, median and skewness
    (Fisher-Pearson g1)."""
    present = [v for v in values if v is not None]
    nulls = len(values) - len(present)
    distinct = len({repr(v) for v in present})
    numbers = [float(v) for v in present if isinstance(v, int | float) and not isinstance(v, bool)]
    if present and len(numbers) == len(present):
        mean = statistics.fmean(numbers)
        deviation = statistics.pstdev(numbers)
        skew = statistics.fmean([(x - mean) ** 3 for x in numbers]) / deviation**3 if deviation > 0 else 0.0
        return ColumnProfile(
            table, column, "number", len(values), nulls, distinct,
            min(numbers), max(numbers), mean, statistics.median(numbers), skew,
        )  # fmt: skip
    kind = "empty" if not present else "bool" if all(isinstance(v, bool) for v in present) else "text"
    return ColumnProfile(table, column, kind, len(values), nulls, distinct)


def finding_columns(findings: Sequence[FindingRecord]) -> list[ColumnProfile]:
    names = (
        "algorithm_family", "usage_context", "location_kind", "priority", "key_size_bits", "confidence",
        "file", "line_start", "raw_name", "mode", "padding", "hash", "library",
    )  # fmt: skip
    return [column_profile("findings", name, [getattr(f, name) for f in findings]) for name in names]


def spelling_variety(findings: Iterable[FindingRecord], field_name: str) -> list[tuple[str, int]]:
    """The distinct spellings of a text field with their frequencies, most frequent first (then alphabetical)."""
    counts = Counter(value for f in findings if isinstance(value := getattr(f, field_name), str))
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


@dataclass(frozen=True)
class Duplicates:
    groups: int
    extra_rows: int


def duplicates(findings: Iterable[FindingRecord]) -> Duplicates:
    """Findings repeated at the same project, file, line, algorithm and usage context (the Deduplicator's key)."""
    keys = Counter(
        (f.project_key, f.file, f.line_start, f.algorithm_family, f.usage_context)
        for f in findings
        if f.file is not None
    )
    repeated = [count for count in keys.values() if count > 1]
    return Duplicates(groups=len(repeated), extra_rows=sum(count - 1 for count in repeated))


def path_class(path: str) -> str:
    """`generated` (build output and generated sources), `test` (test sources) or `main`."""
    segments = path.split("/")
    if any(segment in GENERATED_SEGMENTS for segment in segments[:-1]):
        return "generated"
    name = segments[-1]
    if "/src/test/" in f"/{path}" or name.endswith(("Test.java", "Tests.java", "IT.java")):
        return "test"
    return "main"


def findings_per_project(findings: Iterable[FindingRecord]) -> dict[str, int]:
    return dict(Counter(f.project_key for f in findings))


@dataclass(frozen=True)
class OutlierReport:
    threshold: float | None
    outliers: tuple[tuple[str, int], ...]


def outliers(per_project: Mapping[str, int]) -> OutlierReport:
    """Projects above Q3 + 3 x IQR of the findings-per-project distribution; none below four projects."""
    counts = sorted(per_project.values())
    if len(counts) < MIN_PROJECTS_FOR_OUTLIERS:
        return OutlierReport(None, ())
    q1, _, q3 = statistics.quantiles(counts, n=4, method="inclusive")
    threshold = q3 + OUTLIER_IQR_FACTOR * (q3 - q1)
    found = sorted(((key, n) for key, n in per_project.items() if n > threshold), key=lambda item: (-item[1], item[0]))
    return OutlierReport(threshold, tuple(found))


@dataclass(frozen=True)
class UnmappedValue:
    kind: str
    raw: str
    frequency: int
    projects: int


def unmapped_values(
    findings: Iterable[FindingRecord], known_raw_names: set[str], known_values: Mapping[str, set[str]]
) -> list[UnmappedValue]:
    """Spellings the canonical dictionary does not know, compared without case: a `raw_name` the analyzer could not
    canonicalise (its family is UNKNOWN), that has the shape of an algorithm name and is no `raw` of the dictionary;
    and a `mode`, `padding` or `hash` that is none of the dictionary's canonical values for that column. A raw name
    with a known family was canonicalised already (a transformation is read by its parts)."""
    raw_known = {name.casefold() for name in known_raw_names}
    value_known = {column: {v.casefold() for v in values} for column, values in known_values.items()}
    frequency: Counter[tuple[str, str]] = Counter()
    projects: dict[tuple[str, str], set[str]] = defaultdict(set)
    for finding in findings:
        candidates = [("raw_name", finding.raw_name)] + [(c, getattr(finding, c)) for c in ("mode", "padding", "hash")]
        for kind, value in candidates:
            if not isinstance(value, str) or value == "unrecognized":
                continue
            if kind == "raw_name" and (
                finding.algorithm_family != "UNKNOWN" or _ALGORITHM_NAME.fullmatch(value) is None
            ):
                continue
            known = raw_known if kind == "raw_name" else value_known.get(kind, set())
            if value.casefold() not in known:
                frequency[(kind, value)] += 1
                projects[(kind, value)].add(finding.project_key)
    return sorted(
        (UnmappedValue(kind, raw, n, len(projects[(kind, raw)])) for (kind, raw), n in frequency.items()),
        key=lambda v: (-v.frequency, v.kind, v.raw),
    )


@dataclass(frozen=True)
class Recommendation:
    number: int
    filter: str
    text: str
    evidence: str


@dataclass(frozen=True)
class ProfileFacts:
    """The numbers the recommendations are derived from."""

    quarantined: Mapping[str, int] = field(default_factory=dict)
    duplicates: Duplicates = Duplicates(0, 0)
    path_classes: Mapping[str, int] = field(default_factory=dict)
    test_code_findings: int = 0
    unmapped: int = 0
    secret_hits: Mapping[str, int] = field(default_factory=dict)
    findings_with_path: int = 0
    unknown_key_size: int = 0
    unknown_algorithm: int = 0
    outliers: int = 0
    findings: int = 0


def recommendations(facts: ProfileFacts) -> list[Recommendation]:
    """One recommendation per filter that the numbers give a reason for, numbered in filter order."""
    found: list[tuple[str, str, str]] = []
    if facts.quarantined:
        detail = ", ".join(f"{code}: {n}" for code, n in sorted(facts.quarantined.items()))
        found.append(
            ("SchemaValidator", "Karantinadaki kayıtlar ön işlemeye alınmaz ve nedenleriyle raporlanır.", detail)
        )
    if facts.duplicates.extra_rows:
        found.append((
            "Deduplicator",
            "Aynı proje, dosya, satır, algoritma ve bağlamdaki tekrarlar teke indirilir (ilk görülen tutulur).",
            f"{facts.duplicates.groups} grup, {facts.duplicates.extra_rows} fazla satır",
        ))  # fmt: skip
    if facts.path_classes.get("generated"):
        found.append((
            "GeneratedCodeExcluder",
            "Üretilmiş kod ve build çıktısı yollarındaki bulgular atılır.",
            f"{facts.path_classes['generated']} bulgu `target/`, `build/`, `out/`, `node_modules/` veya "
            "`generated/` altında",
        ))  # fmt: skip
    if facts.path_classes.get("test") or facts.test_code_findings:
        found.append((
            "TestCodeFlagger",
            "Test kodu bulguları silinmez, `in_test_code = true` ile işaretlenir.",
            f"{facts.path_classes.get('test', 0)} bulgu test yolunda, {facts.test_code_findings} bulgu `TEST_CODE`",
        ))  # fmt: skip
    if facts.unmapped:
        found.append((
            "Canonicalizer",
            "Sözlükte olmayan yazımda bulgu kalır ve alan UNKNOWN olur; onaylanan eşlemeler "
            "`contracts/canonical_dictionary.csv`'ye eklenir (D-308e).",
            f"{facts.unmapped} farklı eşlenmemiş değer (`reports/unmapped_values.csv`)",
        ))  # fmt: skip
    if facts.secret_hits or facts.findings_with_path:
        hits = ", ".join(f"{rule}: {n}" for rule, n in sorted(facts.secret_hits.items())) or "kural eşleşmesi yok"
        found.append((
            "Anonymizer",
            "Serbest metin redaksiyondan geçer; dosya yollarındaki proje içi modül adları tuzlu özetle "
            "değiştirilir (bilinen belirteçler `src/test`, `target` ve uzantı korunur; D-299m).",
            f"tarama: {hits}; dosya yolu taşıyan bulgu: {facts.findings_with_path}",
        ))  # fmt: skip
    if facts.unknown_key_size or facts.unknown_algorithm:
        found.append((
            "MissingValueHandler",
            "Bilinmeyen anahtar boyutu tahminle doldurulmaz (`key_size_known = false`); bilinmeyen kategori "
            "`UNKNOWN` kalır.",
            f"anahtar boyutu boş: {facts.unknown_key_size}/{facts.findings}; "
            f"algoritma UNKNOWN: {facts.unknown_algorithm}",
        ))  # fmt: skip
    if facts.outliers:
        found.append((
            "OutlierFlagger",
            "Q3 + 3×IQR üstündeki projeler `is_outlier_project = true` ile işaretlenir, silinmez.",
            f"{facts.outliers} aykırı aday proje",
        ))  # fmt: skip
    return [Recommendation(i, f, t, e) for i, (f, t, e) in enumerate(found, start=1)]
