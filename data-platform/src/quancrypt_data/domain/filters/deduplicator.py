from __future__ import annotations

from dataclasses import replace

from quancrypt_data.domain.prep import FilterResult, FindingRow, PrepBatch


class Deduplicator:
    """Repeats of a finding (same project, path below the project root, line, family and usage context) become one; the
    first seen is kept. A coded finding has no path and is never a repeat (data-preprocessing section 3, filter 2)."""

    code = "Deduplicator"

    def apply(self, batch: PrepBatch) -> FilterResult:
        seen: set[tuple[object, ...]] = set()
        kept: list[FindingRow] = []
        for finding in batch.findings:
            path = finding.full_path
            if path is not None:
                key = (finding.project_key, path, finding.line_start, finding.algorithm_family, finding.usage_context)
                if key in seen:
                    continue
                seen.add(key)
            kept.append(finding)
        removed = len(batch.findings) - len(kept)
        return FilterResult(replace(batch, findings=tuple(kept)), notes={"duplicates_removed": removed})
