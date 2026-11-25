"""Synthetic findings for the Model A tests: 25 projects, the gold label follows the priority (with a few exceptions so the
models have something to learn beyond the rule) and test code drops a class."""

from __future__ import annotations

import random

from quancrypt_ml.domain.risk_features import RiskRow

_CLASS = {"P0": "CRITICAL", "P1": "HIGH", "P2": "MEDIUM", "P3": "LOW"}
_LOWER = {"CRITICAL": "HIGH", "HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "LOW"}


def synthetic_rows(n: int = 330, projects: int = 25, seed: int = 1) -> list[RiskRow]:
    rng = random.Random(seed)  # noqa: S311 (test data)
    rows = []
    for i in range(n):
        priority = rng.choice(["P0", "P1", "P1", "P1", "P2", "P3", "P3", "P3"])
        test = rng.random() < 0.15
        silver = _LOWER[_CLASS[priority]] if test else _CLASS[priority]
        gold = silver if rng.random() > 0.08 else rng.choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"])
        rows.append(
            RiskRow(
                finding_id=f"00000000-0000-4000-8000-{i:012d}",
                project_key=f"{i % projects:064x}",
                algorithm_family=rng.choice(["RSA", "ECDSA", "UNKNOWN", "DES"]),
                quantum_status="VULNERABLE",
                usage_context=rng.choice(["TLS_KEY_EXCHANGE", "CERTIFICATE", "TOKEN_SIGNATURE", "KEYSTORE"]),
                location_kind="TEST_CODE" if test else "CODE",
                priority=priority,
                key_size_bits=rng.choice([None, 1024, 2048, 4096]),
                mode=rng.choice([None, "ECB", "GCM"]),
                padding=rng.choice([None, "OAEP", "PKCS1_V1_5"]),
                hash=rng.choice([None, "SHA-256"]),
                library=rng.choice(["JCA", "spring-boot", "jjwt", None]),
                confidence=round(rng.random(), 3),
                in_test_code=test,
                hndl_exposure=rng.random() < 0.5,
                is_outlier_project=i % projects == 0,
                java_major=rng.choice([None, 17, 21, 25]),
                spring_boot_version=rng.choice([None, "3.3.1", "2.7.18"]),
                project_finding_count=13,
                gold_label=gold,
                silver_label=silver,
            )  # fmt: skip
        )
    return rows
