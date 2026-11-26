"""Data mining over the corpus project profiles (P7.4, ml-pipeline section 5, D-337, D-338): the profile, the choice
of k, the archetype names, the transaction items, the rule thresholds and the review queue. Standard library only."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

RANDOM_SEED = 42
MIN_PROJECTS = 4  # silhouette needs 2 <= k <= n-1; fewer projects than this are not clustered
MAX_K = 8
HDBSCAN_MIN_CLUSTER_SIZE = 3
ISOLATION_TREES = 100
FAMILY_PREFIX, CONTEXT_PREFIX, PRIORITY_PREFIX = "share_alg_", "share_ctx_", "share_p"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProjectProfile:
    """One row of marts.mart_archetypes: the raw (unscaled) crypto profile of a corpus project."""

    project_key: str
    analysis_unit_count: int
    finding_count: int
    findings_per_unit: float
    family_shares: Mapping[str, float]  # algorithm family code -> share of the project's findings
    context_shares: Mapping[str, float]  # usage context code -> share
    priority_shares: Mapping[str, float]  # P0..P3 -> share (report only, not a feature)


@dataclass(frozen=True)
class ProjectLibraries:
    """The (library, algorithm family) pairs of a project's non-test findings (marts.mart_risk_features)."""

    project_key: str
    usages: Sequence[tuple[str | None, str]]


@dataclass(frozen=True)
class MiningSnapshot:
    """What one mining run reads, in one consistent read."""

    profiles: Sequence[ProjectProfile]
    libraries: Sequence[ProjectLibraries]
    projects_with_findings: int  # corpus projects with any finding, test code included


@dataclass(frozen=True)
class FeatureMatrix:
    """`rows` follow `keys`; the share columns come first, the density (log1p of findings per unit) is last."""

    keys: tuple[str, ...]
    columns: tuple[str, ...]
    shares: int  # how many leading columns are shares (scaled min-max); the rest are standardised
    rows: tuple[tuple[float, ...], ...]


def feature_matrix(profiles: Sequence[ProjectProfile]) -> FeatureMatrix:
    ordered = sorted(profiles, key=lambda p: p.project_key)
    families = sorted({code for p in ordered for code, share in p.family_shares.items() if share > 0})
    contexts = sorted({code for p in ordered for code, share in p.context_shares.items() if share > 0})
    columns = (
        *(f"{FAMILY_PREFIX}{c}" for c in families),
        *(f"{CONTEXT_PREFIX}{c}" for c in contexts),
        "log1p_findings_per_unit",
    )
    rows = tuple(
        (
            *(p.family_shares.get(c, 0.0) for c in families),
            *(p.context_shares.get(c, 0.0) for c in contexts),
            math.log1p(p.findings_per_unit),
        )
        for p in ordered
    )
    return FeatureMatrix(tuple(p.project_key for p in ordered), columns, len(families) + len(contexts), rows)


def data_digest(profiles: Sequence[ProjectProfile], libraries: Sequence[ProjectLibraries] = ()) -> str:
    """A digest of the data snapshot a run used (ml-pipeline section 6)."""
    payload = [
        [
            p.project_key, p.analysis_unit_count, p.finding_count, round(p.findings_per_unit, 9),
            sorted((k, round(v, 9)) for k, v in p.family_shares.items()),
            sorted((k, round(v, 9)) for k, v in p.context_shares.items()),
        ]
        for p in sorted(profiles, key=lambda p: p.project_key)
    ] + [
        [item.project_key, sorted(f"{lib or ''}|{family}" for lib, family in item.usages)]
        for item in sorted(libraries, key=lambda i: i.project_key)
    ]  # fmt: skip
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------ clustering


def candidate_ks(projects: int) -> range:
    return range(2, min(MAX_K, projects - 1) + 1)


def best_k(silhouettes: Mapping[int, float]) -> int:
    """The highest silhouette; the smaller k on a tie (D-338c)."""
    return min(silhouettes, key=lambda k: (-silhouettes[k], k))


def elbow_k(inertias: Mapping[int, float]) -> int:
    """The k whose point is farthest from the chord between the first and last inertia (reported only)."""
    ks = sorted(inertias)
    if len(ks) < 3:
        return ks[0]
    x0, x1, y0, y1 = ks[0], ks[-1], inertias[ks[0]], inertias[ks[-1]]
    drop = (y0 - y1) or 1.0

    def distance(k: int) -> float:
        # both axes scaled to 0..1, the chord runs from (0, 1) to (1, 0)
        return abs((k - x0) / (x1 - x0) + (inertias[k] - y1) / drop - 1.0)

    return max(ks, key=lambda k: (distance(k), -k))


def number_clusters(labels: Sequence[int]) -> list[int | None]:
    """Cluster numbers from 1, largest first (ties by first appearance); noise (-1) stays None."""
    sizes: dict[int, int] = {}
    first: dict[int, int] = {}
    for position, label in enumerate(labels):
        if label >= 0:
            sizes[label] = sizes.get(label, 0) + 1
            first.setdefault(label, position)
    order = sorted(sizes, key=lambda label: (-sizes[label], first[label]))
    numbers = {label: number for number, label in enumerate(order, start=1)}
    return [numbers.get(label) for label in labels]


@dataclass(frozen=True)
class Archetype:
    cluster_no: int
    name: str
    rationale: str
    size: int
    family_means: Mapping[str, float]
    context_means: Mapping[str, float]
    priority_means: Mapping[str, float]
    findings_per_unit: float


def _means(shares: Sequence[Mapping[str, float]]) -> dict[str, float]:
    codes = sorted({code for row in shares for code in row})
    return {code: sum(row.get(code, 0.0) for row in shares) / len(shares) for code in codes}


def _top(means: Mapping[str, float]) -> tuple[str, float]:
    code = min(means, key=lambda c: (-means[c], c))
    return code, means[code]


def percent(value: float) -> str:
    return f"%{100 * value:.0f}"


def archetypes(profiles: Sequence[ProjectProfile], numbers: Mapping[str, int | None]) -> list[Archetype]:
    """One archetype per cluster, named from its centre (the unscaled mean of its members): the strongest algorithm
    family and usage context, and the findings per analysed unit (D-338d, D-342); equal names get a sequence number."""
    members: dict[int, list[ProjectProfile]] = {}
    for profile in profiles:
        number = numbers.get(profile.project_key)
        if number is not None:
            members.setdefault(number, []).append(profile)
    found: list[Archetype] = []
    used: dict[str, int] = {}
    for number in sorted(members):
        group = members[number]
        families = _means([p.family_shares for p in group])
        contexts = _means([p.context_shares for p in group])
        (family, family_share), (context, context_share) = _top(families), _top(contexts)
        density = sum(p.findings_per_unit for p in group) / len(group)
        base = f"{family} / {context}, birim başına {density:.3f} bulgu"
        used[base] = used.get(base, 0) + 1
        name = base if used[base] == 1 else f"{base} ({used[base]})"
        rationale = (
            f"{len(group)} proje; merkezde en yüksek aile {family} ({percent(family_share)}), "
            f"en yüksek bağlam {context} ({percent(context_share)}), birim başına ortalama {density:.3f} bulgu"
        )
        found.append(
            Archetype(
                number,
                name,
                rationale,
                len(group),
                families,
                contexts,
                _means([p.priority_shares for p in group]),
                density,
            )  # fmt: skip
        )
    return found


# ------------------------------------------------------------------ association rules


def transaction(project: ProjectLibraries) -> frozenset[str]:
    """`lib:<library>` and `alg:<family>` items; an unrecognised family is no item (D-338e)."""
    items: set[str] = set()
    for library, family in project.usages:
        if library:
            items.add(f"lib:{library}")
        if family != UNKNOWN:
            items.add(f"alg:{family}")
    return frozenset(items)


@dataclass(frozen=True)
class RuleThresholds:
    min_support_projects: int
    min_confidence: float
    min_lift: float = 1.0  # a rule must be strictly above it

    def min_support(self, transactions: int) -> float:
        return min(1.0, self.min_support_projects / transactions)


@dataclass(frozen=True)
class Rule:
    antecedent: tuple[str, ...]
    consequent: tuple[str, ...]
    support: float
    confidence: float
    lift: float


def keep_rules(rules: Sequence[Rule], thresholds: RuleThresholds, transactions: int) -> list[Rule]:
    """The rules that meet every threshold, strongest first (lift, confidence, support, then the items)."""
    if transactions < thresholds.min_support_projects:
        return []
    floor = thresholds.min_support(transactions) - 1e-9
    kept = [
        r
        for r in rules
        if r.support >= floor
        and r.confidence >= thresholds.min_confidence - 1e-9
        and r.lift > thresholds.min_lift + 1e-9
    ]
    return sorted(kept, key=lambda r: (-r.lift, -r.confidence, -r.support, r.antecedent, r.consequent))


# ------------------------------------------------------------------ anomalies


@dataclass(frozen=True)
class AnomalyScore:
    project_key: str
    score: float  # lower is more unusual (scikit-learn decision_function)
    is_flagged: bool


def review_queue(scores: Sequence[AnomalyScore]) -> list[AnomalyScore]:
    """The flagged projects, most unusual first."""
    return sorted((s for s in scores if s.is_flagged), key=lambda s: (s.score, s.project_key))


# ------------------------------------------------------------------ plan template proposal (report only, D-338j)

# crypto-domain section 1: priority and finding kind -> strategy code, by usage context.
_P1_BY_CONTEXT = {
    "TLS_KEY_EXCHANGE": "HYBRID_TLS_KEX",
    "ENCRYPTION": "KEM_DEM_ENCRYPTION",
    "KEY_WRAP": "KEM_DEM_ENCRYPTION",
    "KEY_AGREEMENT": "KEM_DEM_ENCRYPTION",
}
_P3_BY_CONTEXT = {
    "TOKEN_SIGNATURE": "KEEP_SHORT_LIVED_TOKEN",
    "CERTIFICATE": "HYBRID_KEX_CLASSIC_CERT",
    "MTLS_CLIENT_AUTH": "HYBRID_KEX_CLASSIC_CERT",
    "TLS_SERVER_AUTH": "HYBRID_KEX_CLASSIC_CERT",
    "KEYSTORE": "HYBRID_KEX_CLASSIC_CERT",
}


def plan_template(archetype: Archetype) -> list[tuple[str, str]]:
    """(priority, strategy code) steps in priority order for the priorities and contexts present in the archetype."""
    present = {code.upper() for code, share in archetype.priority_means.items() if share > 0}
    contexts = sorted(code for code, share in archetype.context_means.items() if share > 0)
    steps: list[tuple[str, str]] = []
    if "P0" in present:
        steps.append(("P0", "FIX_WEAK_CLASSIC"))
    if "P1" in present:
        steps += [("P1", code) for code in sorted({_P1_BY_CONTEXT[c] for c in contexts if c in _P1_BY_CONTEXT})]
    if "P2" in present:
        steps.append(("P2", "PQ_SIGNATURE"))
    if "P3" in present:
        steps += [("P3", code) for code in sorted({_P3_BY_CONTEXT[c] for c in contexts if c in _P3_BY_CONTEXT})]
    return steps
