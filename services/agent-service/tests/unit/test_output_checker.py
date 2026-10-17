"""The output check: claims against the turn's tool outputs, flag or strip, secrets masked, out-of-scope answers
replaced by the refusal (guardrails-security section 4)."""

from __future__ import annotations

from typing import Any

import pytest

from src.guardrails.output_checker import OutputChecker
from src.prompts.system_prompts import REFUSAL_EN, REFUSAL_TR
from tests.support.tools import redactor

TOOL_OUTPUTS: list[dict[str, Any]] = [
    {
        "items": [
            {
                "path": "qbank-payment-service/src/main/java/Receipt.java",
                "symbol": "Receipt#sign",
                "algorithmFamily": "RSA",
                "keySizeBits": 1024,
                "lineStart": 48,
                "lineEnd": 52,
                "priority": "P0",
            }
        ],
        "totalElements": 7,
    },
    {"path": "src/main/resources/application.yml", "lines": [{"number": 13, "text": "ssl: bundle"}]},
    {"hits": [{"title": "FIPS 203", "text": "ML-KEM-768 public key is 1,184 bytes", "distance": 0.21}]},
]


class Signal:
    def __init__(self, hit: bool = False) -> None:
        self.hit = hit

    def matches_out_of_scope(self, text: str) -> bool:
        return self.hit


def check(text: str, *, mode: str = "flag", language: str = "en", hit: bool = False) -> Any:
    return OutputChecker(Signal(hit), redactor(), mode).check(text, language, TOOL_OUTPUTS)  # type: ignore[arg-type]


def test_supported_numbers_and_references_pass_unchanged() -> None:
    text = (
        "There are 7 findings. Receipt.java:50 signs with a 1024-bit key "
        "(qbank-payment-service/src/main/java/Receipt.java:48-52), see application.yml:13. "
        "The public key has 1.184 bytes."
    )

    result = check(text)

    assert (result.text, result.unverified_count, result.refused) == (text, 0, False)


def test_an_unsupported_number_is_flagged_after_the_claim() -> None:
    result = check("There are 9 findings in 2 services.")

    assert result.text == "There are 9 [unverified] findings in 2 [unverified] services."
    assert result.unverified_count == 2


def test_an_unsupported_reference_is_flagged_in_turkish() -> None:
    result = check("Bkz. Receipt.java:90 ve Other.java:1.", language="tr")

    assert result.text == "Bkz. Receipt.java:90 [doğrulanamadı] ve Other.java:1 [doğrulanamadı]."
    assert result.unverified_count == 2


def test_strip_removes_only_the_sentence_with_the_unsupported_claim() -> None:
    text = "There are 7 findings. One uses 4096 bits. Receipt.java:50 is the worst.\nNext line stays."

    result = check(text, mode="strip")

    assert result.text == "There are 7 findings. Receipt.java:50 is the worst.\nNext line stays."
    assert result.unverified_count == 1


def test_list_markers_identifiers_and_code_blocks_are_not_claims() -> None:
    text = (
        "Steps:\n1. Move to ML-KEM-768 and SHA256.\n2) Use X25519MLKEM768.\n"
        "```java\nint size = 3072; // 99 bits\n```\nDone."
    )

    result = check(text)

    assert (result.text, result.unverified_count) == (text, 0)


def test_a_percentage_and_a_decimal_comma_are_checked_as_numbers() -> None:
    assert check("Distance 0,21 is close.").unverified_count == 0
    assert check("About 37% are critical.").text == "About 37% [unverified] are critical."


def test_secrets_are_masked_after_the_claim_check() -> None:
    result = check('Set password="hunter2-secret" in the 7 files.')

    assert "hunter2-secret" not in result.text
    assert result.redacted
    assert result.unverified_count == 0


@pytest.mark.parametrize(("language", "refusal"), [("tr", REFUSAL_TR), ("en", REFUSAL_EN)])
def test_an_out_of_scope_answer_is_replaced_by_the_refusal(language: str, refusal: str) -> None:
    result = check("Here is a pasta recipe with 9 steps.", language=language, hit=True)

    assert (result.text, result.refused, result.unverified_count) == (refusal, True, 0)


def test_the_real_rule_filter_is_a_signal() -> None:
    from tests.unit.test_rule_filter import rule_filter

    checker = OutputChecker(rule_filter(), redactor(), "flag")
    assert checker.check("Here is a recipe for soup.", "en", []).refused
    assert not checker.check("Use ML-KEM.", "en", []).refused


@pytest.mark.parametrize(
    ("text", "leak"),
    [
        ("Contact 123@example.com for access.", "123@example.com"),
        ("email: 5551234@corp.example.com", "5551234@corp.example.com"),
        ("password=1234!sEcReTtail", "sEcReTtail"),
        ("Use Zm9vYmFy+1234+YmF6cXV4K3NlY3JldEtleU1hdGVyaWFs0987 here.", "Zm9vYmFy+1234+YmF6"),
    ],
    ids=["email-local-digits", "email-label", "secret-assignment-tail", "high-entropy-with-digits"],
)
def test_a_label_never_splits_a_secret_because_redaction_runs_first(text: str, leak: str) -> None:
    # Security review P4.4 (D-245): the label used to be inserted before redaction and broke the patterns.
    result = check(text)

    assert leak not in result.text
    assert result.redacted
