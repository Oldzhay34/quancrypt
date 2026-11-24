from __future__ import annotations

from dataclasses import replace

from quancrypt_data.domain.prep import FilterResult, PrepBatch
from quancrypt_data.domain.profiling import path_class


class GeneratedCodeExcluder:
    """Findings below build output and generated sources (`target/`, `build/`, `out/`, `node_modules/`, `generated/`)
    are dropped: they are not the project's code (filter 3; the same rule the profiling report counted)."""

    code = "GeneratedCodeExcluder"

    def apply(self, batch: PrepBatch) -> FilterResult:
        kept = tuple(f for f in batch.findings if f.full_path is None or path_class(f.full_path) != "generated")
        removed = len(batch.findings) - len(kept)
        return FilterResult(replace(batch, findings=kept), notes={"generated_removed": removed})
