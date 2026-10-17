"""The output check (guardrails-security section 4): runs on every answer before the user sees it.

In order:
1. Out-of-scope signal (D-242d): the rule filter's out-of-scope keywords and jailbreak phrases applied to the answer; a
   match replaces the whole answer with the fixed refusal.
2. Redaction of secrets with the shared rules, before anything is inserted into the text (a label inside a secret
   would split the pattern and leave part of it visible; security review P4.4, D-245).
3. Claims: every number and every `path:line` reference in the answer is compared with the tool outputs of the turn
   (plain JSON values; the guardrails do not import `src.tools`, the workflow passes `ToolResult.output`). A claim no
   tool output supports is flagged (`[doğrulanamadı]` / `[unverified]`) or its sentence is removed (`on_mismatch`).
   The redaction markers hold no digits, so they never become claims.

Claims in the answer are read strictly: list markers ("1. ") and digits inside identifiers (ML-KEM-768, SHA256) are not
claims. Tool outputs are read liberally (every digit run counts), so "RSA-2048" in a tool output supports "2048" in the
answer. Fenced code blocks are not checked for claims (a label would break the code) but are redacted.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from src.guardrails.chain import Language
from src.guardrails.redaction import Redactor
from src.prompts.system_prompts import refusal

OnMismatch = Literal["flag", "strip"]

UNVERIFIED_LABEL: Mapping[Language, str] = {"tr": "[doğrulanamadı]", "en": "[unverified]"}

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_REFERENCE = re.compile(r"(?<![\w/.-])((?:[\w-]+/)*[\w-]+\.[A-Za-z0-9]{1,10}):(\d{1,7})(?:-(\d{1,7}))?(?![\w-])")
_CLAIM_NUMBER = re.compile(r"(?<![\w.,/-])(\d+(?:[.,]\d+)*)(%?)(?![\w/-]|[.,]\d)")
_LIST_MARKER = re.compile(r"^[ \t]*(\d+)[.)][ \t]", re.MULTILINE)
_LIST_MARKER_ONLY = re.compile(r"[ \t]*\d+[.)][ \t]*")
_BOUNDARY = re.compile(r"[.!?]+[ \t]+|[.!?]*\n")
_SOURCE_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_PATH_KEYS = ("path", "file", "location")
_LINE_PAIRS = (("lineStart", "lineEnd"), ("line_start", "line_end"))


class OutOfScopeSignal(Protocol):
    def matches_out_of_scope(self, text: str) -> bool: ...


@dataclass(frozen=True)
class OutputCheckResult:
    text: str
    refused: bool
    unverified_count: int
    redacted: bool


class OutputChecker:
    def __init__(self, signal: OutOfScopeSignal, redactor: Redactor, on_mismatch: OnMismatch) -> None:
        self._signal = signal
        self._redactor = redactor
        self._on_mismatch = on_mismatch

    def check(self, text: str, language: Language, tool_outputs: Sequence[Mapping[str, Any]]) -> OutputCheckResult:
        if self._signal.matches_out_of_scope(text):
            return OutputCheckResult(refusal(language), refused=True, unverified_count=0, redacted=False)
        masked = self._redactor.redact(text)
        checked, unverified = self._check_claims(masked, language, _Evidence.of(tool_outputs))
        return OutputCheckResult(checked, refused=False, unverified_count=unverified, redacted=masked != text)

    def _check_claims(self, text: str, language: Language, evidence: _Evidence) -> tuple[str, int]:
        parts: list[str] = []
        unverified = 0
        position = 0
        for fence in _FENCE.finditer(text):
            prose, count = self._check_prose(text[position : fence.start()], language, evidence)
            parts += [prose, fence.group(0)]
            unverified += count
            position = fence.end()
        prose, count = self._check_prose(text[position:], language, evidence)
        parts.append(prose)
        return "".join(parts), unverified + count

    def _check_prose(self, text: str, language: Language, evidence: _Evidence) -> tuple[str, int]:
        spans = sorted(_unverified_spans(text, evidence))
        if not spans:
            return text, 0
        if self._on_mismatch == "flag":
            return _insert_labels(text, [end for _, end in spans], UNVERIFIED_LABEL[language]), len(spans)
        kept: list[str] = []
        for a, b in _sentence_spans(text):
            if not any(a <= start < b for start, _ in spans):
                kept.append(text[a:b])
            elif text[a:b].endswith("\n"):
                kept.append("\n")
        return "".join(kept), len(spans)


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Sentences end after `.`, `!` or `?` followed by whitespace, or at a line break; "1. " at a line start is a list
    marker, not a sentence end."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        end = match.end()
        line_start = text.rfind("\n", 0, match.start()) + 1
        if not match.group(0).endswith("\n") and _LIST_MARKER_ONLY.fullmatch(text[line_start:end]):
            continue
        spans.append((start, end))
        start = end
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _unverified_spans(text: str, evidence: _Evidence) -> Iterator[tuple[int, int]]:
    covered: list[tuple[int, int]] = []
    for match in _REFERENCE.finditer(text):
        covered.append(match.span())
        first, last = int(match.group(2)), int(match.group(3) or match.group(2))
        if not evidence.has_location(match.group(1), first, last):
            yield match.span()
    markers = {m.start(1) for m in _LIST_MARKER.finditer(text)}
    for match in _CLAIM_NUMBER.finditer(text):
        start, end = match.span()
        if start in markers or any(a <= start < b for a, b in covered):
            continue
        if not evidence.has_number(match.group(1)):
            yield start, end


def _insert_labels(text: str, ends: Sequence[int], label: str) -> str:
    out = text
    for end in sorted(ends, reverse=True):
        out = f"{out[:end]} {label}{out[end:]}"
    return out


def _number_forms(raw: str) -> set[str]:
    """The same number written with a thousands separator or a decimal comma ("1.184", "1,184", "0,35")."""
    plain = raw.replace(".", "").replace(",", "")
    return {raw, plain, raw.replace(",", "."), raw.replace(".", ",")}


@dataclass(frozen=True)
class _Location:
    path: str
    first: int
    last: int


@dataclass(frozen=True)
class _Evidence:
    numbers: frozenset[str]
    locations: tuple[_Location, ...]

    @classmethod
    def of(cls, outputs: Sequence[Mapping[str, Any]]) -> _Evidence:
        numbers: set[str] = set()
        locations: list[_Location] = []
        for output in outputs:
            _walk(output, numbers, locations)
        return cls(frozenset(numbers), tuple(locations))

    def has_number(self, raw: str) -> bool:
        return bool(_number_forms(raw) & self.numbers)

    def has_location(self, path: str, first: int, last: int) -> bool:
        return any(
            _same_path(path, location.path) and location.first <= first and last <= location.last
            for location in self.locations
        )


def _same_path(claimed: str, known: str) -> bool:
    return claimed == known or known.endswith("/" + claimed) or claimed.endswith("/" + known)


def _walk(value: Any, numbers: set[str], locations: list[_Location]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        numbers.update(_number_forms(str(value)))
        if isinstance(value, float) and value.is_integer():
            numbers.add(str(int(value)))
    elif isinstance(value, str):
        for raw in _SOURCE_NUMBER.findall(value):
            numbers.update(_number_forms(raw))
    elif isinstance(value, Mapping):
        locations.extend(_locations(value))
        for item in value.values():
            _walk(item, numbers, locations)
    elif isinstance(value, list | tuple):
        for item in value:
            _walk(item, numbers, locations)


def _locations(item: Mapping[str, Any]) -> Iterator[_Location]:
    path = next((item[key] for key in _PATH_KEYS if isinstance(item.get(key), str)), None)
    if path is None:
        return
    if isinstance(item.get("line"), int):
        yield _Location(path, item["line"], item["line"])
    for start_key, end_key in _LINE_PAIRS:
        start, end = item.get(start_key), item.get(end_key)
        if isinstance(start, int):
            yield _Location(path, start, end if isinstance(end, int) else start)
    lines = item.get("lines")
    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, Mapping) and isinstance(line.get("number"), int):
                yield _Location(path, line["number"], line["number"])
