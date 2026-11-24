from __future__ import annotations

from dataclasses import replace

from quancrypt_data.domain.prep import FilterResult, PrepBatch
from quancrypt_data.domain.profiling import path_class


class TestCodeFlagger:
    """Test-code findings are kept and flagged `in_test_code` (filter 4, D-308a): a path below `src/test/`, a
    `*Test.java`, `*Tests.java` or `*IT.java`, or the analyzer's own `TEST_CODE` location. It runs before the
    Anonymizer, which hashes the file names the rule reads."""

    __test__ = False  # not a pytest class, whatever its name
    code = "TestCodeFlagger"

    def apply(self, batch: PrepBatch) -> FilterResult:
        flagged = tuple(
            replace(
                f,
                in_test_code=f.location_kind == "TEST_CODE"
                or (f.full_path is not None and path_class(f.full_path) == "test"),
            )
            for f in batch.findings
        )
        return FilterResult(
            replace(batch, findings=flagged), notes={"in_test_code": sum(1 for f in flagged if f.in_test_code)}
        )
