"""The evaluation sets under `data/examples` (P4.7): loading and record validation.

Three sets are read: the golden question set (`golden_qa.jsonl`, 50 QBank questions, D-266), the scope seed set
(`scope_set_seed.jsonl`, H4) and the injection set (`injection_set.jsonl`, D-263). Every record must carry exactly its
set's fields with the right types; a bad record stops the evaluation with its file and line, so a report is never built
on a set that was silently read wrong.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.prompts.templates import INTENTS

Language = Literal["tr", "en"]
ScopeLabel = Literal["IN_SCOPE", "OUT_OF_SCOPE"]

GOLDEN_FILE = "golden_qa.jsonl"
SCOPE_FILE = "scope_set_seed.jsonl"
INJECTION_FILE = "injection_set.jsonl"

_LANGUAGES = frozenset({"tr", "en"})
_CARRIERS = frozenset({"code_comment", "readme", "application_yml", "commit_message"})


class TestCaseError(ValueError):
    """A set file is missing, is not JSON Lines, or holds a record of the wrong shape."""

    __test__ = False  # not a pytest class despite the name


@dataclass(frozen=True)
class GoldenQuestion:
    """One golden question. The expected values come from the tool outputs of the QBank payment service analysis
    (D-266): `expected_numbers` and `expected_paths` must appear in the answer, `expected_keywords` too (any case)."""

    id: str
    lang: Language
    intent: str
    question: str
    expected_numbers: tuple[int | float, ...]
    expected_paths: tuple[str, ...]
    expected_keywords: tuple[str, ...]
    must_cite: bool


@dataclass(frozen=True)
class ScopeCase:
    id: str
    language: Language
    text: str
    expected: ScopeLabel
    category: str


@dataclass(frozen=True)
class InjectionCase:
    id: str
    carrier: str
    language: Language
    content: str
    injected_instruction: str
    expectation: Literal["no_tool_call"]


@dataclass(frozen=True)
class EvaluationSets:
    golden: tuple[GoldenQuestion, ...]
    scope: tuple[ScopeCase, ...]
    injection: tuple[InjectionCase, ...]


def load_sets(examples_dir: Path) -> EvaluationSets:
    return EvaluationSets(
        golden=load_golden(examples_dir / GOLDEN_FILE),
        scope=load_scope(examples_dir / SCOPE_FILE),
        injection=load_injection(examples_dir / INJECTION_FILE),
    )


def load_golden(path: Path) -> tuple[GoldenQuestion, ...]:
    return _load(path, _golden)


def load_scope(path: Path) -> tuple[ScopeCase, ...]:
    return _load(path, _scope)


def load_injection(path: Path) -> tuple[InjectionCase, ...]:
    return _load(path, _injection)


# ---- record parsers ----


def _golden(row: Mapping[str, Any]) -> GoldenQuestion:
    _fields(
        row,
        {
            "id",
            "lang",
            "intent",
            "question",
            "expected_numbers",
            "expected_paths",
            "expected_keywords",
            "must_cite",
        },
    )
    intent = _text(row, "intent")
    if intent not in INTENTS:
        raise TestCaseError(f"unknown intent {intent!r}")
    numbers = row["expected_numbers"]
    if not isinstance(numbers, list) or not all(_is_number(value) for value in numbers):
        raise TestCaseError("expected_numbers must be a list of numbers")
    return GoldenQuestion(
        id=_text(row, "id"),
        lang=_language(row, "lang"),
        intent=intent,
        question=_text(row, "question"),
        expected_numbers=tuple(numbers),
        expected_paths=_texts(row, "expected_paths"),
        expected_keywords=_texts(row, "expected_keywords"),
        must_cite=_flag(row, "must_cite"),
    )


def _scope(row: Mapping[str, Any]) -> ScopeCase:
    _fields(row, {"id", "language", "text", "expected", "category"})
    expected = _text(row, "expected")
    if expected not in ("IN_SCOPE", "OUT_OF_SCOPE"):
        raise TestCaseError(f"expected must be IN_SCOPE or OUT_OF_SCOPE, not {expected!r}")
    return ScopeCase(
        id=_text(row, "id"),
        language=_language(row, "language"),
        text=_text(row, "text"),
        expected="IN_SCOPE" if expected == "IN_SCOPE" else "OUT_OF_SCOPE",
        category=_text(row, "category"),
    )


def _injection(row: Mapping[str, Any]) -> InjectionCase:
    _fields(row, {"id", "carrier", "language", "content", "injected_instruction", "expectation"})
    carrier = _text(row, "carrier")
    if carrier not in _CARRIERS:
        raise TestCaseError(f"unknown carrier {carrier!r}")
    if row["expectation"] != "no_tool_call":
        raise TestCaseError("expectation must be no_tool_call")
    return InjectionCase(
        id=_text(row, "id"),
        carrier=carrier,
        language=_language(row, "language"),
        content=_text(row, "content"),
        injected_instruction=_text(row, "injected_instruction"),
        expectation="no_tool_call",
    )


# ---- helpers ----


def _load[T: (GoldenQuestion, ScopeCase, InjectionCase)](
    path: Path, parse: Callable[[Mapping[str, Any]], T]
) -> tuple[T, ...]:
    try:
        lines = path.read_text("utf-8").splitlines()
    except OSError as exc:
        raise TestCaseError(f"{path.name}: cannot be read ({type(exc).__name__})") from exc
    records: list[T] = []
    seen: set[str] = set()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise TestCaseError("a record must be a JSON object")
            record = parse(row)
        except (TestCaseError, json.JSONDecodeError) as exc:
            raise TestCaseError(f"{path.name}:{number}: {exc}") from exc
        if record.id in seen:
            raise TestCaseError(f"{path.name}:{number}: duplicate id {record.id!r}")
        seen.add(record.id)
        records.append(record)
    if not records:
        raise TestCaseError(f"{path.name}: the set is empty")
    return tuple(records)


def _fields(row: Mapping[str, Any], expected: set[str]) -> None:
    if set(row) != expected:
        missing = sorted(expected - set(row))
        extra = sorted(set(row) - expected)
        raise TestCaseError(f"fields do not match (missing {missing}, unexpected {extra})")


def _text(row: Mapping[str, Any], name: str) -> str:
    value = row[name]
    if not isinstance(value, str) or not value.strip():
        raise TestCaseError(f"{name} must be a non-empty string")
    return value


def _texts(row: Mapping[str, Any], name: str) -> tuple[str, ...]:
    values: Sequence[Any] = row[name]
    if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
        raise TestCaseError(f"{name} must be a list of non-empty strings")
    return tuple(values)


def _flag(row: Mapping[str, Any], name: str) -> bool:
    value = row[name]
    if not isinstance(value, bool):
        raise TestCaseError(f"{name} must be true or false")
    return value


def _language(row: Mapping[str, Any], name: str) -> Language:
    value = _text(row, name)
    if value not in _LANGUAGES:
        raise TestCaseError(f"{name} must be tr or en")
    return "tr" if value == "tr" else "en"


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
