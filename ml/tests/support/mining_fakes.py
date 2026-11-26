"""Test doubles of the mining ports: small deterministic implementations (they pass the same contract cases as the real
adapters, tests/support/mining_port_cases.py) and synthetic corpus profiles."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path

from quancrypt_ml.domain.mining import (
    AnomalyScore,
    Archetype,
    FeatureMatrix,
    MiningSnapshot,
    ProjectLibraries,
    ProjectProfile,
    Rule,
)
from quancrypt_ml.port.outbound.mining import ClusterAssignment, Clustering, MiningRun, TechniqueClusters


def key(number: int) -> str:
    return hashlib.sha256(f"project-{number}".encode()).hexdigest()


def profile(
    number: int,
    families: Mapping[str, float],
    contexts: Mapping[str, float],
    per_unit: float = 2.0,
    priorities: Mapping[str, float] | None = None,
) -> ProjectProfile:
    return ProjectProfile(
        key(number), 2, int(2 * per_unit), per_unit, dict(families), dict(contexts),
        dict(priorities or {"P0": 0.0, "P1": 0.0, "P2": 0.0, "P3": 1.0}),
    )  # fmt: skip


def corpus() -> list[ProjectProfile]:
    """Two clear groups (token signing with RSA, TLS with an unknown family) and one project unlike both."""
    tokens = [
        profile(i, {"RSA": 1.0, "UNKNOWN": 0.0}, {"TOKEN_SIGNATURE": 1.0, "TLS_KEY_EXCHANGE": 0.0}, 2.0 + i / 100)
        for i in range(1, 5)
    ]
    tls = [
        profile(
            i,
            {"RSA": 0.0, "UNKNOWN": 1.0},
            {"TOKEN_SIGNATURE": 0.0, "TLS_KEY_EXCHANGE": 1.0},
            3.0 + i / 100,
            {"P0": 0.0, "P1": 1.0, "P2": 0.0, "P3": 0.0},
        )  # fmt: skip
        for i in range(5, 9)
    ]
    odd = profile(9, {"RSA": 0.5, "UNKNOWN": 0.5}, {"TOKEN_SIGNATURE": 0.5, "TLS_KEY_EXCHANGE": 0.5}, 40.0)
    return [*tokens, *tls, odd]


def libraries() -> list[ProjectLibraries]:
    jjwt = [("jjwt", "RSA"), ("spring-security-oauth2-jose", "RSA")]
    return [
        *[ProjectLibraries(key(i), jjwt) for i in range(1, 5)],
        *[ProjectLibraries(key(i), [("JSSE", "UNKNOWN")]) for i in range(5, 9)],
        ProjectLibraries(key(9), [(None, "UNKNOWN")]),  # no item at all
    ]


class FakeMiningData:
    def __init__(
        self,
        profiles: Sequence[ProjectProfile] | None = None,
        usages: Sequence[ProjectLibraries] | None = None,
        with_findings: int | None = None,
    ) -> None:
        self._profiles = list(corpus() if profiles is None else profiles)
        self._libraries = list(libraries() if usages is None else usages)
        self._with_findings = len(self._profiles) if with_findings is None else with_findings
        self.reads = 0

    def snapshot(self) -> MiningSnapshot:
        self.reads += 1
        return MiningSnapshot(list(self._profiles), list(self._libraries), self._with_findings)


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.dist(a, b)


def _groups(rows: Sequence[Sequence[float]], k: int) -> list[int]:
    """Single linkage: join the closest pairs until k groups are left."""
    parent = list(range(len(rows)))

    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    groups = len(rows)
    for _, a, b in sorted((_distance(rows[a], rows[b]), a, b) for a, b in combinations(range(len(rows)), 2)):
        if groups <= k:
            break
        if root(a) != root(b):
            parent[root(b)] = root(a)
            groups -= 1
    names: dict[int, int] = {}
    return [names.setdefault(root(i), len(names)) for i in range(len(rows))]


def _silhouette(rows: Sequence[Sequence[float]], labels: Sequence[int]) -> float | None:
    kept = [i for i, label in enumerate(labels) if label >= 0]
    clusters = {labels[i] for i in kept}
    if len(clusters) < 2 or len(clusters) >= len(kept):
        return None
    total = 0.0
    for i in kept:
        means = {}
        for label in clusters:
            members = [j for j in kept if labels[j] == label and j != i]
            means[label] = sum(_distance(rows[i], rows[j]) for j in members) / len(members) if members else 0.0
        own = means.pop(labels[i])
        other = min(means.values())
        if any(labels[j] == labels[i] and j != i for j in kept):
            total += (other - own) / (max(own, other) or 1.0)
    return total / len(kept)


class FakeClusterer:
    def kmeans(self, matrix: FeatureMatrix, k: int, seed: int) -> Clustering:
        labels = _groups(matrix.rows, k)
        inertia = 0.0
        for label in set(labels):
            members = [row for row, found in zip(matrix.rows, labels, strict=True) if found == label]
            centre = [sum(column) / len(members) for column in zip(*members, strict=True)]
            inertia += sum(_distance(row, centre) ** 2 for row in members)
        return Clustering(tuple(labels), _silhouette(matrix.rows, labels), inertia)

    def hdbscan(self, matrix: FeatureMatrix, min_cluster_size: int) -> Clustering:
        labels = _groups(matrix.rows, max(1, len(matrix.rows) // min_cluster_size))
        sizes = {label: labels.count(label) for label in labels}
        labels = [label if sizes[label] >= min_cluster_size else -1 for label in labels]
        return Clustering(tuple(labels), _silhouette(matrix.rows, labels), None)

    def adjusted_rand(self, first: Sequence[int], second: Sequence[int]) -> float:
        pairs = list(combinations(range(len(first)), 2))
        agree = sum((first[a] == first[b]) == (second[a] == second[b]) for a, b in pairs)
        return 1.0 if not pairs or agree == len(pairs) else agree / len(pairs) - 0.5

    def project_2d(self, matrix: FeatureMatrix) -> list[tuple[float, float]]:
        return [(row[0], row[-1]) for row in matrix.rows]


class FakeRuleMiner:
    """Every itemset by brute force."""

    def mine(self, transactions: Sequence[frozenset[str]], min_support: float) -> list[Rule]:
        items = sorted({item for t in transactions for item in t})
        support = {}
        for size in range(1, len(items) + 1):
            for chosen in combinations(items, size):
                share = sum(set(chosen) <= t for t in transactions) / len(transactions)
                if share >= min_support - 1e-9:
                    support[frozenset(chosen)] = share
        rules = []
        for itemset, joint in support.items():
            for size in range(1, len(itemset)):
                for antecedent in combinations(sorted(itemset), size):
                    left = frozenset(antecedent)
                    confidence = min(1.0, joint / support[left])
                    right = itemset - left
                    rules.append(
                        Rule(tuple(sorted(left)), tuple(sorted(right)), joint, confidence, confidence / support[right])
                    )
        return sorted(rules, key=lambda r: (r.antecedent, r.consequent))


class FakeAnomalyDetector:
    def score(self, matrix: FeatureMatrix, contamination: float, trees: int, seed: int) -> list[AnomalyScore]:
        if not matrix.keys:
            return []
        centre = [sum(column) / len(matrix.rows) for column in zip(*matrix.rows, strict=True)]
        far = [_distance(row, centre) for row in matrix.rows]
        flagged = max(1, round(contamination * len(far)))
        limit = sorted(far, reverse=True)[flagged - 1]
        return [
            AnomalyScore(found, (limit - distance) - 1e-6, distance >= limit)
            for found, distance in zip(matrix.keys, far, strict=True)
        ]


class FakeMiningCharts:
    def __init__(self) -> None:
        self.drawn: list[str] = []

    def _draw(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.drawn.append(path.name)

    def k_selection(self, silhouettes: Mapping[int, float], inertias: Mapping[int, float], path: Path) -> None:
        self._draw(path)

    def cluster_map(self, points: Sequence[tuple[float, float]], numbers: Sequence[int | None], path: Path) -> None:
        self._draw(path)

    def rules(self, rules: Sequence[Rule], path: Path) -> None:
        self._draw(path)

    def anomaly_scores(self, scores: Sequence[AnomalyScore], path: Path) -> None:
        self._draw(path)


class FakeMiningSink:
    """ClusterSink, RuleSink and AnomalySink; `present` None: no warehouse, every project is written."""

    def __init__(self) -> None:
        self.present: set[str] | None = None
        self.runs: dict[str, MiningRun] = {}
        self.archetypes: dict[str, list[Archetype]] = {}
        self.assignments: dict[str, list[ClusterAssignment]] = {}
        self.rules: list[Rule] = []
        self.anomalies: list[AnomalyScore] = []

    def _kept(self, found: str) -> bool:
        return self.present is None or found in self.present

    def store_clusters(self, clusterings: Sequence[TechniqueClusters]) -> int:
        for c in clusterings:
            self.runs[c.technique] = c.run
            self.archetypes[c.technique] = list(c.archetypes)
            self.assignments[c.technique] = [a for a in c.assignments if self._kept(a.project_key)]
        keys = {a.project_key for c in clusterings for a in c.assignments}
        return len([k for k in keys if not self._kept(k)])

    def store_rules(self, run: MiningRun, rules: Sequence[Rule]) -> None:
        self.runs["FP_GROWTH"] = run
        self.rules = list(rules)

    def store_anomalies(self, run: MiningRun, scores: Sequence[AnomalyScore]) -> int:
        self.runs["ISOLATION_FOREST"] = run
        self.anomalies = [s for s in scores if self._kept(s.project_key)]
        return len(scores) - len(self.anomalies)
