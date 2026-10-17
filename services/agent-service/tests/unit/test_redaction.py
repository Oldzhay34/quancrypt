"""The Python redactor against the shared rule file and test vectors (guardrails-security section 5, D-238e).

core-service runs the same vectors in Java (`RedactorVectorsTest`); a vector that passes there must pass here.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.guardrails.redaction import TOO_LONG_RULE, RedactionRulesError, Redactor, shannon_bits_per_char
from tests.support.postgres import REPO_ROOT

CONTRACTS = REPO_ROOT / "contracts"
RULES = CONTRACTS / "redaction-rules.yaml"
VECTORS: list[dict[str, Any]] = yaml.safe_load(
    (CONTRACTS / "testdata" / "redaction" / "vectors.yaml").read_text("utf-8")
)["vectors"]


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor.from_file(RULES)


def test_the_vector_file_is_not_empty_and_covers_both_kinds() -> None:
    assert len(VECTORS) >= 30
    assert {vector["kind"] for vector in VECTORS} == {"positive", "negative"}


@pytest.mark.parametrize("vector", VECTORS, ids=[vector["id"] for vector in VECTORS])
def test_every_shared_vector(redactor: Redactor, vector: dict[str, Any]) -> None:
    output = redactor.redact(vector["input"])

    if vector["kind"] == "negative":
        assert output == vector["input"]
    else:
        assert f"[REDACTED:{vector['rule']}]" in output
        for secret in vector.get("secrets", []):
            assert secret not in output


def test_input_longer_than_the_limit_is_redacted_whole(redactor: Redactor) -> None:
    limit = int(yaml.safe_load(RULES.read_text("utf-8"))["max_input_length"])

    assert redactor.redact("x" * (limit + 1)) == f"[REDACTED:{TOO_LONG_RULE}]"
    assert TOO_LONG_RULE not in redactor.redact("x" * limit)


@pytest.mark.parametrize(
    "text",
    [
        "a" * 200_000,
        "a." * 100_000,
        "x@" * 50_000 + "y",
        "-----BEGIN PRIVATE KEY-----" * 4_000,
        'password="' + "z" * 200_000,
        "a@b." * 30_000,
        "eyJxxxxx-" * 100_000,
        "eyJxxxxx.eyJxxxxx-" * 50_000,
    ],
    ids=["run", "dots", "at-signs", "key-headers", "open-quote", "mail-like", "jwt-head", "jwt-two-parts"],
)
def test_pathological_inputs_are_redacted_in_bounded_time(redactor: Redactor, text: str) -> None:
    # The inputs of the Java test (core D-163, D-205). CPU time of this thread, so a loaded machine does not fail it;
    # the bound is generous, not a goal.
    started = time.thread_time()
    redactor.redact(text)
    assert time.thread_time() - started < 10


def test_redact_value_masks_strings_at_any_depth_and_keeps_keys_and_scalars(redactor: Redactor) -> None:
    value = {
        "password": 'password="hunter2-secret"',
        "lines": [{"number": 3, "text": "AKIAIOSFODNN7EXAMPLE"}, ("ok", None, True, 1.5)],
    }

    output = redactor.redact_value(value)

    assert set(output) == {"password", "lines"}
    assert "hunter2-secret" not in output["password"]
    assert output["lines"][0]["number"] == 3
    assert "AKIAIOSFODNN7EXAMPLE" not in output["lines"][0]["text"]
    assert output["lines"][1] == ["ok", None, True, 1.5]


def test_shannon_entropy() -> None:
    assert shannon_bits_per_char("") == 0.0
    assert shannon_bits_per_char("aaaa") == 0.0
    assert shannon_bits_per_char("abcd") == pytest.approx(2.0)


@pytest.mark.parametrize(
    "document",
    [
        None,
        {},
        {"replacement": "[X]", "rules": [{"id": "a", "pattern": "a"}], "high_entropy": {}, "max_input_length": 1},
        {
            "replacement": "[{rule}]",
            "rules": [{"id": "a", "pattern": "("}],
            "high_entropy": {"id": "h", "token_pattern": "x", "min_length": 1, "min_bits_per_char": 1},
            "max_input_length": 10,
        },
        {
            "replacement": "[{rule}]",
            "rules": [],
            "high_entropy": {"id": "h", "token_pattern": "x", "min_length": 1, "min_bits_per_char": 1},
            "max_input_length": 10,
        },
    ],
    ids=["none", "empty", "no-rule-placeholder", "bad-pattern", "no-rules"],
)
def test_a_malformed_rule_file_stops_the_service(document: Any) -> None:
    with pytest.raises(RedactionRulesError):
        Redactor.from_mapping(document)


def test_a_missing_rule_file_stops_the_service(tmp_path: Path) -> None:
    with pytest.raises(RedactionRulesError):
        Redactor.from_file(tmp_path / "missing.yaml")
