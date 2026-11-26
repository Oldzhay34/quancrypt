"""Clustering, anomaly detection and association rules with scikit-learn and mlxtend (P7.4, D-338). The scaling follows
ml-pipeline section 3: the shares (bounded) min-max, the log1p density standardised."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import fpgrowth
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from quancrypt_ml.domain.mining import AnomalyScore, FeatureMatrix, Rule
from quancrypt_ml.port.outbound.mining import Clustering

# The threaded linear algebra of K-Means differs in the last bits from run to run; results are kept to this many
# decimals so that the same data gives the same facts (ml-pipeline section 8).
DECIMALS = 9


def _scaled(matrix: FeatureMatrix) -> np.ndarray:
    values = np.asarray(matrix.rows, dtype=np.float64)
    parts = []
    if matrix.shares:
        parts.append(MinMaxScaler().fit_transform(values[:, : matrix.shares]))
    if values.shape[1] > matrix.shares:
        parts.append(StandardScaler().fit_transform(values[:, matrix.shares :]))
    return np.hstack(parts)


def _silhouette(values: np.ndarray, labels: np.ndarray) -> float | None:
    kept = labels >= 0
    clusters = len(set(labels[kept].tolist()))
    if clusters < 2 or clusters >= int(kept.sum()):
        return None
    return round(float(silhouette_score(values[kept], labels[kept])), DECIMALS)


class SklearnClusterer:
    def kmeans(self, matrix: FeatureMatrix, k: int, seed: int) -> Clustering:
        values = _scaled(matrix)
        model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(values)
        labels = np.asarray(model.labels_)
        return Clustering(
            tuple(int(v) for v in labels), _silhouette(values, labels), round(float(model.inertia_), DECIMALS)
        )

    def hdbscan(self, matrix: FeatureMatrix, min_cluster_size: int) -> Clustering:
        values = _scaled(matrix)
        labels = np.asarray(HDBSCAN(min_cluster_size=min_cluster_size, copy=True).fit_predict(values))
        return Clustering(tuple(max(-1, int(v)) for v in labels), _silhouette(values, labels), None)

    def adjusted_rand(self, first: Sequence[int], second: Sequence[int]) -> float:
        return float(adjusted_rand_score(list(first), list(second)))

    def project_2d(self, matrix: FeatureMatrix) -> list[tuple[float, float]]:
        values = _scaled(matrix)
        axes = min(2, values.shape[0], values.shape[1])
        points = PCA(n_components=axes, random_state=42).fit_transform(values) if axes else values
        return [(float(p[0]), float(p[1]) if axes > 1 else 0.0) for p in points]


class SklearnAnomalyDetector:
    def score(self, matrix: FeatureMatrix, contamination: float, trees: int, seed: int) -> list[AnomalyScore]:
        if not matrix.keys:
            return []
        values = _scaled(matrix)
        model = IsolationForest(n_estimators=trees, contamination=contamination, random_state=seed).fit(values)
        scores = model.decision_function(values)
        return [
            AnomalyScore(key, round(float(score), DECIMALS), bool(score < 0))
            for key, score in zip(matrix.keys, scores, strict=True)
        ]


class MlxtendRuleMiner:
    """mlxtend's FP-Growth finds the frequent itemsets; the rules are their splits (support, confidence, lift)."""

    def mine(self, transactions: Sequence[frozenset[str]], min_support: float) -> list[Rule]:
        items = sorted({item for t in transactions for item in t})
        if not items:
            return []
        frame = pd.DataFrame([[item in t for item in items] for t in transactions], columns=items, dtype=bool)
        found = fpgrowth(frame, min_support=min_support - 1e-9, use_colnames=True)
        support = {frozenset(row.itemsets): float(row.support) for row in found.itertuples()}
        rules = []
        for itemset, joint in support.items():
            for size in range(1, len(itemset)):
                for antecedent in combinations(sorted(itemset), size):
                    left = frozenset(antecedent)
                    right = itemset - left
                    confidence = min(1.0, joint / support[left])
                    rules.append(
                        Rule(
                            tuple(sorted(left)),
                            tuple(sorted(right)),
                            joint,
                            confidence,
                            confidence / support[right],
                        )  # fmt: skip
                    )
        return sorted(rules, key=lambda r: (r.antecedent, r.consequent))
