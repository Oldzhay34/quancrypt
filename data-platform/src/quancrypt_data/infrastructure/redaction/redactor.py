"""Secret and personal-data rules of contracts/redaction-rules.yaml for the data platform (P6.3;
guardrails-security section 5).

A copy of agent-service's redactor (`src/guardrails/redaction.py`; services do not share code), checked against the
same shared vectors (contracts/testdata/redaction). The profiling uses `scan`: how many matches each rule finds, never
the text.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TOO_LONG_RULE = "max_input_length"


class RedactionRulesError(Exception):
    """The rule file is missing or malformed; the service does not start without working redaction."""


@dataclass(frozen=True)
class _PatternRule:
    rule_id: str
    pattern: re.Pattern[str]
    value_group: int


@dataclass(frozen=True)
class _HighEntropyRule:
    rule_id: str
    token: re.Pattern[str]
    min_length: int
    min_bits_per_char: float


class Redactor:
    """Masks secrets in text. Immutable and thread-safe once built."""

    def __init__(
        self, replacement: str, max_input_length: int, rules: Sequence[_PatternRule], high_entropy: _HighEntropyRule
    ) -> None:
        self._replacement = replacement
        self._max_input_length = max_input_length
        self._rules = tuple(rules)
        self._high_entropy = high_entropy

    @classmethod
    def from_file(cls, path: Path) -> Redactor:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise RedactionRulesError(f"cannot read the redaction rules {path.name}") from exc
        return cls.from_mapping(document)

    @classmethod
    def from_mapping(cls, document: Any) -> Redactor:
        try:
            replacement = str(document["replacement"])
            if "{rule}" not in replacement:
                raise RedactionRulesError("the replacement must contain {rule}")
            rules = [
                _PatternRule(
                    rule_id=str(rule["id"]),
                    pattern=re.compile(str(rule["pattern"]), re.ASCII),
                    value_group=int(rule.get("value_group", 0)),
                )
                for rule in document["rules"]
            ]
            entropy = document["high_entropy"]
            high_entropy = _HighEntropyRule(
                rule_id=str(entropy["id"]),
                token=re.compile(str(entropy["token_pattern"]), re.ASCII),
                min_length=int(entropy["min_length"]),
                min_bits_per_char=float(entropy["min_bits_per_char"]),
            )
            max_input_length = int(document["max_input_length"])
        except (KeyError, TypeError, ValueError, re.error) as exc:
            raise RedactionRulesError("the redaction rule file is malformed") from exc
        if not rules or max_input_length < 1:
            raise RedactionRulesError("the redaction rule file has no rules or no input limit")
        return cls(replacement, max_input_length, rules, high_entropy)

    def redact(self, text: str) -> str:
        if len(text) > self._max_input_length:
            return self._marker(TOO_LONG_RULE)
        out = text
        for rule in self._rules:
            out = self._apply(rule, out)
        return self._apply_high_entropy(out)

    def scan(self, texts: Sequence[str]) -> dict[str, int]:
        """Matches per rule over the texts (a text above the input limit counts once for `max_input_length`)."""
        counts: Counter[str] = Counter()
        markers = {rule.rule_id: self._marker(rule.rule_id) for rule in self._rules}
        markers[self._high_entropy.rule_id] = self._marker(self._high_entropy.rule_id)
        markers[TOO_LONG_RULE] = self._marker(TOO_LONG_RULE)
        for text in texts:
            redacted = self.redact(text)
            for rule_id, marker in markers.items():
                found = redacted.count(marker)
                if found:
                    counts[rule_id] += found
        return dict(counts)

    def redact_value(self, value: Any) -> Any:
        """Redact every string inside a JSON-like value (dicts, lists, scalars); keys are kept as they are."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, Mapping):
            return {key: self.redact_value(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self.redact_value(item) for item in value]
        return value

    def _marker(self, rule_id: str) -> str:
        return self._replacement.replace("{rule}", rule_id)

    def _apply(self, rule: _PatternRule, text: str) -> str:
        marker = self._marker(rule.rule_id)

        def replace(match: re.Match[str]) -> str:
            group = rule.value_group
            if group == 0 or match.start(group) < 0:
                return marker
            whole = match.group(0)
            start, end = match.start(group) - match.start(), match.end(group) - match.start()
            return whole[:start] + marker + whole[end:]

        return rule.pattern.sub(replace, text)

    def _apply_high_entropy(self, text: str) -> str:
        rule = self._high_entropy
        marker = self._marker(rule.rule_id)

        def replace(match: re.Match[str]) -> str:
            token = match.group(0)
            secret = len(token) >= rule.min_length and shannon_bits_per_char(token) >= rule.min_bits_per_char
            return marker if secret else token

        return rule.token.sub(replace, text)


def shannon_bits_per_char(token: str) -> float:
    """Shannon entropy of the character distribution of the token, in bits per character (core-service has the same)."""
    if not token:
        return 0.0
    length = len(token)
    return -sum((count / length) * math.log2(count / length) for count in Counter(token).values())
