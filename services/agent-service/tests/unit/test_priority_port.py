"""The priority table port in discovery_agent (crypto-domain, D-149, D-151): the agent computes the same priority
core-service would accept. A drift test checks it against the approved QBank golden inventory (D-186)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.agents.discovery_agent import Derived, NotApplicable, Undetermined, classify_priority

GOLDEN = Path(__file__).resolve().parents[4] / "reference-system" / "expected" / "crypto_inventory.yaml"


@pytest.mark.parametrize(
    ("family", "context", "key_size", "mode", "padding", "location", "expected"),
    [
        # Weak classic (P0, FIX_WEAK_CLASSIC).
        ("DES", "SYMMETRIC_ENCRYPTION", None, "CBC", None, "CODE", "P0"),
        ("TRIPLE_DES", "SYMMETRIC_ENCRYPTION", None, "CBC", None, "CODE", "P0"),
        ("RSA", "SIGNATURE", 1024, None, None, "CODE", "P0"),
        ("SHA1", "SIGNATURE", None, None, None, "CODE", "P0"),
        ("MD5", "CERTIFICATE", None, None, None, "CERTIFICATE_FILE", "P0"),
        ("AES", "SYMMETRIC_ENCRYPTION", 128, "ECB", None, "CODE", "P0"),
        ("RSA", "ENCRYPTION", 2048, None, "PKCS1_V1_5", "CODE", "P0"),
        # Key establishment and TLS key exchange (P1).
        ("RSA", "TLS_KEY_EXCHANGE", 2048, None, None, "CODE", "P1"),
        ("RSA", "ENCRYPTION", 2048, None, "OAEP", "CODE", "P1"),
        ("ECDH", "KEY_AGREEMENT", None, None, None, "CODE", "P1"),
        # Long-lived signatures (P2).
        ("RSA", "SIGNATURE", 2048, None, None, "CODE", "P2"),
        ("ECDSA", "SIGNATURE", None, None, None, "CODE", "P2"),
        # Short-lived tokens, certificates and identity (P3).
        ("RSA", "TOKEN_SIGNATURE", 2048, None, None, "CODE", "P3"),
        ("RSA", "CERTIFICATE", 2048, None, None, "CERTIFICATE_FILE", "P3"),
        ("RSA", "MTLS_CLIENT_AUTH", 2048, None, None, "CODE", "P3"),
    ],
)
def test_the_table_rules(
    family: str, context: str, key_size: int | None, mode: str | None, padding: str | None, location: str, expected: str
) -> None:
    verdict = classify_priority(
        family, context, key_size_bits=key_size, mode=mode, padding=padding, location_kind=location
    )
    assert verdict == Derived(expected)


def test_a_keystore_is_p3_whatever_the_family() -> None:
    assert classify_priority(
        "UNKNOWN", "KEYSTORE", key_size_bits=None, mode=None, padding=None, location_kind="CODE"
    ) == Derived("P3")
    assert classify_priority(
        "RSA", "ENCRYPTION", key_size_bits=2048, mode=None, padding=None, location_kind="KEYSTORE_FILE"
    ) == Derived("P3")


@pytest.mark.parametrize("family", ["AES", "SHA2", "SHA3", "HMAC", "CHACHA20", "ML_KEM", "ML_DSA", "SLH_DSA"])
def test_a_family_that_needs_no_migration_is_not_applicable(family: str) -> None:
    verdict = classify_priority(family, "SIGNATURE", key_size_bits=None, mode=None, padding=None, location_kind="CODE")
    assert isinstance(verdict, NotApplicable)


def test_an_unknown_family_or_context_is_undetermined() -> None:
    assert isinstance(
        classify_priority("UNKNOWN", "SIGNATURE", key_size_bits=None, mode=None, padding=None, location_kind="CODE"),
        Undetermined,
    )
    assert isinstance(
        classify_priority("RSA", "UNKNOWN", key_size_bits=2048, mode=None, padding=None, location_kind="CODE"),
        Undetermined,
    )


def test_the_port_matches_the_qbank_golden_inventory() -> None:
    entries: list[dict[str, Any]] = yaml.safe_load(GOLDEN.read_text("utf-8"))["entries"]
    assert entries, "the golden inventory is empty"

    mismatches = []
    for entry in entries:
        verdict = classify_priority(
            entry["algorithm_family"],
            entry["usage_context"],
            key_size_bits=entry["key_size_bits"],
            mode=None,
            padding=None,
            location_kind=entry["location_kind"],
        )
        if verdict != Derived(entry["priority"]):
            mismatches.append((entry["symbol"], entry["priority"], verdict))
    assert mismatches == []
