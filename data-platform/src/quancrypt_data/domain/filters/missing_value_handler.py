from __future__ import annotations

from dataclasses import replace

from quancrypt_data.domain.prep import UNKNOWN, FilterResult, FindingRow, PrepBatch


class MissingValueHandler:
    """Nothing is filled in by guess (filter 7, D-308c): an unknown key size stays NULL (`key_size_known` is false);
    a missing family or usage context becomes the `UNKNOWN` category. `mode`, `padding`, `hash` and `library` stay
    NULL when the code does not state them: for most findings they do not apply (an RSA signature has no mode)."""

    code = "MissingValueHandler"

    def apply(self, batch: PrepBatch) -> FilterResult:
        filled = 0
        findings: list[FindingRow] = []
        for finding in batch.findings:
            if finding.algorithm_family is None or finding.usage_context is None:
                filled += 1
            findings.append(
                replace(
                    finding,
                    algorithm_family=UNKNOWN if finding.algorithm_family is None else finding.algorithm_family,
                    usage_context=UNKNOWN if finding.usage_context is None else finding.usage_context,
                )
            )
        unknown_size = sum(1 for f in findings if f.key_size_bits is None)
        return FilterResult(
            replace(batch, findings=tuple(findings)),
            notes={"category_set_to_unknown": filled, "key_size_unknown": unknown_size},
        )
