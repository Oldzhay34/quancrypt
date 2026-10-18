"""The evaluation set loader (P4.7): the shipped sets load, and a bad record stops the evaluation with its line."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from src.evaluation.test_cases import TestCaseError, load_golden, load_injection, load_scope, load_sets
from src.prompts.templates import INTENTS

EXAMPLES = Path(__file__).resolve().parents[2] / "data" / "examples"

GOLDEN_ROW: dict[str, Any] = {
    "id": "gq-x",
    "lang": "tr",
    "intent": "inventory",
    "question": "Projemde RSA nerede?",
    "expected_numbers": [27],
    "expected_paths": ["src/main/resources/application.yml"],
    "expected_keywords": ["RSA"],
    "must_cite": True,
}


def write(tmp_path: Path, rows: list[Any]) -> Path:
    path = tmp_path / "set.jsonl"
    path.write_text("\n".join(json.dumps(row) if not isinstance(row, str) else row for row in rows) + "\n", "utf-8")
    return path


def test_the_shipped_sets_load_with_their_sizes() -> None:
    sets = load_sets(EXAMPLES)

    assert (len(sets.golden), len(sets.scope), len(sets.injection)) == (50, 100, 30)


def test_the_golden_set_covers_both_languages_and_only_catalogue_intents() -> None:
    golden = load_golden(EXAMPLES / "golden_qa.jsonl")

    assert Counter(question.lang for question in golden) == {"tr": 27, "en": 23}
    assert {question.intent for question in golden} <= set(INTENTS)
    assert len({question.intent for question in golden}) == 14
    # Every inventory answer cites code locations (the planner's evidence).
    assert all(question.must_cite for question in golden if question.intent == "inventory")


def test_a_golden_record_is_read_into_typed_fields(tmp_path: Path) -> None:
    (question,) = load_golden(write(tmp_path, [GOLDEN_ROW]))

    assert question.expected_numbers == (27,)
    assert question.expected_paths == ("src/main/resources/application.yml",)
    assert question.must_cite is True


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"intent": "weather"}, "unknown intent"),
        ({"expected_numbers": [True]}, "expected_numbers"),
        ({"expected_numbers": ["27"]}, "expected_numbers"),
        ({"must_cite": "yes"}, "must_cite"),
        ({"lang": "de"}, "lang must be tr or en"),
        ({"question": "  "}, "question must be a non-empty string"),
        ({"expected_paths": [""]}, "expected_paths"),
        ({"extra": 1}, "unexpected ['extra']"),
    ],
)
def test_a_bad_golden_record_names_its_file_line_and_reason(
    tmp_path: Path, change: dict[str, Any], reason: str
) -> None:
    path = write(tmp_path, [GOLDEN_ROW | {"id": "ok"}, GOLDEN_ROW | change])

    with pytest.raises(TestCaseError, match=rf"set\.jsonl:2: .*{re.escape(reason)}"):
        load_golden(path)


def test_a_missing_field_is_named(tmp_path: Path) -> None:
    row = {key: value for key, value in GOLDEN_ROW.items() if key != "must_cite"}

    with pytest.raises(TestCaseError, match=r"missing \['must_cite'\]"):
        load_golden(write(tmp_path, [row]))


def test_duplicate_ids_bad_json_and_an_empty_file_are_refused(tmp_path: Path) -> None:
    with pytest.raises(TestCaseError, match="duplicate id 'gq-x'"):
        load_golden(write(tmp_path, [GOLDEN_ROW, GOLDEN_ROW]))
    with pytest.raises(TestCaseError, match=r"set\.jsonl:1"):
        load_golden(write(tmp_path, ["{not json"]))
    with pytest.raises(TestCaseError, match="a record must be a JSON object"):
        load_golden(write(tmp_path, ["[1, 2]"]))
    with pytest.raises(TestCaseError, match="the set is empty"):
        load_golden(write(tmp_path, [""]))
    with pytest.raises(TestCaseError, match="cannot be read"):
        load_golden(tmp_path / "missing.jsonl")


def test_scope_and_injection_records_are_validated(tmp_path: Path) -> None:
    scope = {"id": "s", "language": "en", "text": "hi", "expected": "MAYBE", "category": "c"}
    injection = {
        "id": "i",
        "carrier": "readme",
        "language": "tr",
        "content": "x",
        "injected_instruction": "y",
        "expectation": "tool_call",
    }

    with pytest.raises(TestCaseError, match="IN_SCOPE or OUT_OF_SCOPE"):
        load_scope(write(tmp_path, [scope]))
    with pytest.raises(TestCaseError, match="no_tool_call"):
        load_injection(write(tmp_path, [injection]))
    with pytest.raises(TestCaseError, match="unknown carrier"):
        load_injection(write(tmp_path, [injection | {"carrier": "email", "expectation": "no_tool_call"}]))
