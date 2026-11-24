from __future__ import annotations

from collections import Counter
from dataclasses import replace

from quancrypt_data.domain.prep import FilterResult, PrepBatch
from quancrypt_data.domain.profiling import outliers


class OutlierFlagger:
    """Projects whose finding count is above Q3 + 3 x IQR of the distribution are flagged `is_outlier_project`, never
    removed (filter 8, D-308d). The distribution holds the projects with findings (D-309d), one origin at a time: a
    benchmark is not a corpus project."""

    code = "OutlierFlagger"

    def apply(self, batch: PrepBatch) -> FilterResult:
        per_project = Counter(f.project_key for f in batch.findings)
        flagged: set[str] = set()
        for origin in sorted({p.origin for p in batch.projects}):
            keys = {p.project_key for p in batch.projects if p.origin == origin}
            report = outliers({key: n for key, n in per_project.items() if key in keys})
            flagged.update(key for key, _ in report.outliers)
        projects = tuple(replace(p, is_outlier_project=p.project_key in flagged) for p in batch.projects)
        return FilterResult(replace(batch, projects=projects), notes={"outlier_projects": len(flagged)})
