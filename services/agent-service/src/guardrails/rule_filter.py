"""Ring 1, the rule filter (guardrails-security section 2): deterministic, the first match decides.

DENY: an empty request, a request longer than the limit (D-242a), a request that tries to speak for the self-check
model (chat template control tokens, a line starting with a role prefix such as `model:`, or one of the self-check
labels; security review P4.4, D-245), a jailbreak phrase, an out-of-scope keyword. Everything else is UNSURE, an
in-scope keyword too (D-242c): a word like "RSA" alone does not make a request acceptable ("how do I break RSA"), the
next ring decides.

Before any check the text is normalised: NFKC (full-width and compatibility forms), format characters removed
(zero-width characters, direction marks) and combining marks dropped, so full-width letters, a zero-width space inside
a word and a dotted i written with a combining dot read as the plain words. Phrase matching is on words, never on
regular expressions from configuration (no ReDoS): text and phrases are folded the same way (Turkish dotted and
dotless i, casefold, non-word characters as separators), and a phrase matches a run of whole words. A phrase word
ending in `*` matches by prefix, for Turkish suffixes ("tarif*" matches "tarifini").
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from src.guardrails.chain import GuardRequest, RingName, RingVerdict

_WORD = re.compile(r"[^\W_]+")
_PATTERN_WORD = re.compile(r"[^\W_]+\*?")
# A forged turn for the self-check model: template control tokens (Gemma `<start_of_turn>`, `<end_of_turn>`, `<bos>`,
# and the `<|...|>` form of other templates) or a line that starts with a role name followed by a colon.
# Possessive quantifiers: "<" followed by thousands of spaces must not backtrack (security review P4.4, round 2).
_TEMPLATE_TOKEN = re.compile(
    r"<\s*+(?:/\s*+)?(?:start_of_turn|end_of_turn|bos|eos)\s*+>|<\|[^|<>\n]{1,40}+\|>", re.IGNORECASE
)
# Latin look-alikes from Cyrillic and Greek (a small confusables table, no new dependency) and every dash (category Pd)
# as "-": "mоdel" with a Cyrillic o and "IN–SCOPE" with an en dash read as the plain words (security review P4.4).
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d",
        "ӏ": "l", "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
        "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
        "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "ο": "o", "ν": "v",
    }
)  # fmt: skip
_ROLE_PREFIX = re.compile(r"^[ \t>*_-]*(?:model|assistant|system|user)[ \t]*:", re.IGNORECASE | re.MULTILINE)
# The self-check labels themselves ("IN_SCOPE", "in-scope", "OUT_OF_SCOPE"); the plain phrase "in scope" stays allowed.
_LABEL = re.compile(r"(?<![^\W_])(?:in|out[_-]of)[_-]scope(?![^\W_])", re.IGNORECASE)


def normalize(text: str) -> str:
    """NFKC, without format characters (Cf) and combining marks (Mn after NFD), dashes (Pd) as "-", and Cyrillic and
    Greek look-alikes as Latin letters."""
    compatible = unicodedata.normalize("NFKC", text)
    visible = "".join(ch for ch in compatible if unicodedata.category(ch) != "Cf")
    decomposed = unicodedata.normalize("NFD", visible)
    bare = unicodedata.normalize("NFC", "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn"))
    return "".join("-" if unicodedata.category(ch) == "Pd" else ch for ch in bare).translate(_CONFUSABLES)


def _fold(text: str) -> str:
    # Turkish İ and ı first (casefold alone maps İ to i plus a combining dot), then everything to one i.
    return normalize(text.replace("İ", "i").replace("I", "i")).casefold().replace("ı", "i")


def normalize_words(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(_fold(text)))


def _pattern_words(entry: str) -> tuple[str, ...]:
    return tuple(_PATTERN_WORD.findall(_fold(entry)))


def speaks_for_the_model(text: str) -> bool:
    """The request contains a forged turn or a self-check label (D-245)."""
    plain = normalize(text)
    return bool(_TEMPLATE_TOKEN.search(plain) or _ROLE_PREFIX.search(plain) or _LABEL.search(plain))


@dataclass(frozen=True)
class _Phrase:
    words: tuple[str, ...]

    def found_in(self, words: Sequence[str]) -> bool:
        size = len(self.words)
        return any(
            all(_word_matches(pattern, words[start + offset]) for offset, pattern in enumerate(self.words))
            for start in range(len(words) - size + 1)
        )


def _word_matches(pattern: str, word: str) -> bool:
    return word.startswith(pattern[:-1]) if pattern.endswith("*") else word == pattern


def _phrases(entries: Iterable[str]) -> tuple[_Phrase, ...]:
    return tuple(_Phrase(words) for words in (_pattern_words(entry) for entry in entries) if words)


@dataclass(frozen=True)
class RuleFilterConfig:
    max_request_chars: int
    jailbreak_phrases: Mapping[str, Sequence[str]]
    out_of_scope_keywords: Mapping[str, Sequence[str]]
    in_scope_keywords: Mapping[str, Sequence[str]]


class RuleFilter:
    """Ring 1. Both languages' lists apply to every request: a request may mix languages."""

    def __init__(self, config: RuleFilterConfig) -> None:
        self._max = config.max_request_chars
        self._jailbreak = _phrases(phrase for phrases in config.jailbreak_phrases.values() for phrase in phrases)
        self._out_of_scope = _phrases(word for words in config.out_of_scope_keywords.values() for word in words)
        self._in_scope = _phrases(word for words in config.in_scope_keywords.values() for word in words)

    @property
    def name(self) -> RingName:
        return "RULE_FILTER"

    def check(self, request: GuardRequest) -> RingVerdict:
        text = request.text
        if not text.strip() or len(text) > self._max or speaks_for_the_model(text):
            return RingVerdict("DENY")
        words = normalize_words(text)
        if self._any(self._jailbreak, words) or self._any(self._out_of_scope, words):
            return RingVerdict("DENY")
        return RingVerdict("UNSURE")

    def mentions_scope(self, text: str) -> bool:
        """An in-scope keyword appears (informational; it never allows a request on its own, D-242c)."""
        return self._any(self._in_scope, normalize_words(text))

    def matches_out_of_scope(self, text: str) -> bool:
        """The output check's out-of-scope signal (D-242d): a jailbreak phrase or an out-of-scope keyword in a text."""
        words = normalize_words(text)
        return self._any(self._jailbreak, words) or self._any(self._out_of_scope, words)

    @staticmethod
    def _any(phrases: Sequence[_Phrase], words: Sequence[str]) -> bool:
        return any(phrase.found_in(words) for phrase in phrases)
