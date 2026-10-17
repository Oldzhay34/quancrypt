"""The seed evaluation sets (data/examples, D-242e): sizes, balance, unique ids and record shape."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

EXAMPLES = Path(__file__).resolve().parents[2] / "data" / "examples"


def rows(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (EXAMPLES / name).read_text("utf-8").splitlines() if line.strip()]


def test_the_scope_seed_has_100_requests_balanced_by_label_and_language() -> None:
    data = rows("scope_set_seed.jsonl")

    assert len(data) == 100
    assert len({row["id"] for row in data}) == 100
    assert Counter((row["expected"], row["language"]) for row in data) == {
        ("IN_SCOPE", "tr"): 25,
        ("IN_SCOPE", "en"): 25,
        ("OUT_OF_SCOPE", "tr"): 25,
        ("OUT_OF_SCOPE", "en"): 25,
    }
    for row in data:
        assert set(row) == {"id", "language", "text", "expected", "category"}
        assert row["text"].strip() and len(row["text"]) <= 4000


def test_the_injection_set_has_30_cases_on_four_carriers_and_expects_no_tool_call() -> None:
    data = rows("injection_set.jsonl")

    assert len(data) == 30
    assert len({row["id"] for row in data}) == 30
    assert set(Counter(row["carrier"] for row in data)) == {
        "code_comment",
        "readme",
        "application_yml",
        "commit_message",
    }
    assert {row["language"] for row in data} == {"tr", "en"}
    for row in data:
        assert set(row) == {"id", "carrier", "language", "content", "injected_instruction", "expectation"}
        assert row["expectation"] == "no_tool_call"
        assert row["content"].strip() and row["injected_instruction"].strip()
