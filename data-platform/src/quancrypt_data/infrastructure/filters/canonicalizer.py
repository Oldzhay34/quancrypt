"""Canonicalizer (P6.4, filter 5): every coded value is a value of its code list or of the canonical dictionary
(contracts/canonical_dictionary.csv, the one analyzer-service reads); a value that is neither becomes UNKNOWN and is
counted, the finding is kept (D-308e). The analyzer already writes canonical values (D-192a): this filter is the check
that they still are, and it maps the values of other producers."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from quancrypt_data.domain.prep import ALGORITHM_FAMILIES, UNKNOWN, USAGE_CONTEXTS, FilterResult, FindingRow, PrepBatch
from quancrypt_data.port.outbound.profiling import CanonicalDictionary

# The library names the analyzer writes (D-192g); a library is a name, not a dictionary value.
KNOWN_LIBRARIES = frozenset({
    "JCA", "JSSE", "BouncyCastle", "nimbus-jose-jwt", "jjwt", "java-jwt", "spring-security-oauth2-jose", "spring-boot",
    "paho", "mosquitto",
})  # fmt: skip


class Canonicalizer:
    code = "Canonicalizer"

    def __init__(self, dictionary: CanonicalDictionary) -> None:
        values = dictionary.canonical_values()
        self._known = {
            "algorithm_family": set(ALGORITHM_FAMILIES),
            "usage_context": set(USAGE_CONTEXTS),
            "mode": set(values.get("mode", set())),
            "padding": set(values.get("padding", set())),
            "hash": set(values.get("hash", set())),
            "library": set(KNOWN_LIBRARIES),
        }

    def apply(self, batch: PrepBatch) -> FilterResult:
        unknown: Counter[str] = Counter()
        findings: list[FindingRow] = []
        for finding in batch.findings:
            changes: dict[str, object] = {}
            for column, known in self._known.items():
                value = getattr(finding, column)
                if value is not None and value not in known:
                    changes[column] = UNKNOWN
                    unknown[column] += 1
            findings.append(replace(finding, **changes) if changes else finding)  # type: ignore[arg-type]
        return FilterResult(
            replace(batch, findings=tuple(findings)),
            notes={f"{column}_set_to_unknown": n for column, n in sorted(unknown.items())},
        )
