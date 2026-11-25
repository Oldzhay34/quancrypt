"""The fixed zero-shot prompt of the Model A comparison (P7.2, D-327c, D-328). Version 1.

It gives the LLM what the classical model sees (the canonical fields of a finding, no code) and the class definitions of
the approved labelling guideline (D-326), but not the mechanical rule table: with the table it would apply the rule, not
classify. The fields are codes written by the analyzer, never free text of a project, so the prompt holds no project
data that could carry an instruction."""

from __future__ import annotations

PROMPT_VERSION = "risk-zero-shot-v1"

SYSTEM = (
    "You classify the quantum-migration risk of one cryptographic usage found in a Java project. "
    "Answer with exactly one word: CRITICAL, HIGH, MEDIUM or LOW.\n"
    "CRITICAL: weak classical cryptography that can be broken today (MD5 or SHA-1 signatures, DES or 3DES, "
    "ECB mode for block ciphers, RSA shorter than 2048 bits, PKCS#1 v1.5 encryption, a trust manager that "
    "accepts every certificate) in production code.\n"
    "HIGH: a quantum-vulnerable key exchange on a network connection between services or to a field device; "
    "recorded traffic could be decrypted later (harvest now, decrypt later).\n"
    "MEDIUM: quantum-vulnerable encryption or key agreement inside an application, or a long-lived signature "
    "(documents, audit records, software packages).\n"
    "LOW: short-lived token signatures (for example JWT RS256), certificates, mTLS client authentication and "
    "keystores.\n"
    "A usage in test code is one class lower (LOW stays LOW)."
)

FIELDS = (
    "algorithm_family", "usage_context", "location_kind", "priority", "quantum_status", "key_size_bits", "mode",
    "padding", "hash", "library", "in_test_code", "hndl_exposure",
)  # fmt: skip
