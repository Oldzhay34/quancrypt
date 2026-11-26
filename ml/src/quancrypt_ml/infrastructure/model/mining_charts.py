"""The charts of the mining report (matplotlib Figure objects written straight to PNG, no global state)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from matplotlib.figure import Figure

from quancrypt_ml.domain.mining import AnomalyScore, Rule


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(path, dpi=120)


class MatplotlibMiningCharts:
    def k_selection(self, silhouettes: Mapping[int, float], inertias: Mapping[int, float], path: Path) -> None:
        figure = Figure(figsize=(9, 3.5))
        left, right = figure.subplots(1, 2)
        for axis, values, title in ((left, silhouettes, "silhouette"), (right, inertias, "inertia (elbow)")):
            ks = sorted(values)
            axis.plot(ks, [values[k] for k in ks], marker="o")
            axis.set_xlabel("k")
            axis.set_title(title)
        _save(figure, path)

    def cluster_map(self, points: Sequence[tuple[float, float]], numbers: Sequence[int | None], path: Path) -> None:
        figure = Figure(figsize=(6, 4.5))
        axis = figure.subplots()
        for number in sorted({n or 0 for n in numbers}):
            members = [p for p, n in zip(points, numbers, strict=True) if (n or 0) == number]
            axis.scatter([p[0] for p in members], [p[1] for p in members], label=f"cluster {number}")
        axis.set_xlabel("component 1")
        axis.set_ylabel("component 2")
        if points:
            axis.legend()
        _save(figure, path)

    def rules(self, rules: Sequence[Rule], path: Path) -> None:
        figure = Figure(figsize=(6, 4))
        axis = figure.subplots()
        drawn = axis.scatter([r.support for r in rules], [r.confidence for r in rules], c=[r.lift for r in rules])
        if rules:
            figure.colorbar(drawn, ax=axis, label="lift")
        axis.set_xlabel("support")
        axis.set_ylabel("confidence")
        _save(figure, path)

    def anomaly_scores(self, scores: Sequence[AnomalyScore], path: Path) -> None:
        ordered = sorted(scores, key=lambda s: s.score)
        figure = Figure(figsize=(7, 3.5))
        axis = figure.subplots()
        axis.bar(
            range(len(ordered)), [s.score for s in ordered],
            color=["tab:red" if s.is_flagged else "tab:blue" for s in ordered],
        )  # fmt: skip
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_xlabel("projects, most unusual first (red: review queue)")
        axis.set_ylabel("anomaly score")
        _save(figure, path)
