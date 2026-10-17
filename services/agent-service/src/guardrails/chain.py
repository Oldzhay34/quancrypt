"""The scope keeper (guardrails-security section 2): a chain of rings (Chain of Responsibility), fail-closed.

Each ring answers ALLOW, DENY or UNSURE. The first ALLOW or DENY decides; if every ring is UNSURE, if there are no
rings, or if a ring fails, the decision is DENY by `FAIL_CLOSED`. The rings come from configuration in order and are
built in the container (OCP: a new ring is a new class and a configuration entry; P7.5 replaces the interim topic
gate, D-246, with the ONNX scope classifier).

The chain returns a `GuardDecision` with the fields of a `scope_decision` record (D-226) and never the request text; the
workflow layer records it (P4.6), the guardrails do not import `src.memory`.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Verdict = Literal["ALLOW", "DENY", "UNSURE"]
Decision = Literal["ALLOW", "DENY"]
RingName = Literal["RULE_FILTER", "SCOPE_CLASSIFIER", "LLM_SELF_CHECK"]
DecidingRing = Literal["RULE_FILTER", "SCOPE_CLASSIFIER", "LLM_SELF_CHECK", "FAIL_CLOSED"]
Language = Literal["tr", "en"]

_LOG = logging.getLogger("src.guardrails")


@dataclass(frozen=True)
class GuardRequest:
    text: str
    language: Language

    def __repr__(self) -> str:
        # The request text never reaches a log line, not even through a repr in an error message.
        return f"GuardRequest(language={self.language!r}, length={len(self.text)})"


@dataclass(frozen=True)
class RingVerdict:
    verdict: Verdict
    # Only a classifier ring has a score (agent_db: confidence is set only for SCOPE_CLASSIFIER).
    confidence: float | None = None


class GuardRing(Protocol):
    @property
    def name(self) -> RingName: ...

    def check(self, request: GuardRequest) -> RingVerdict: ...


@dataclass(frozen=True)
class GuardDecision:
    decision: Decision
    confidence: float | None
    deciding_ring: DecidingRing
    latency_ms: int
    language: Language

    @property
    def allowed(self) -> bool:
        return self.decision == "ALLOW"


class GuardChain:
    def __init__(self, rings: Sequence[GuardRing], clock: Callable[[], float] = time.monotonic) -> None:
        self._rings = tuple(rings)
        self._clock = clock
        if "SCOPE_CLASSIFIER" not in self.ring_names:
            # guardrails-security section 2: until Model B exists (P7.5) ring 2 is absent, and that is logged.
            _LOG.info(
                "scope classifier ring (Model B) is not in the chain; rings: %s", ", ".join(self.ring_names) or "none"
            )

    @property
    def ring_names(self) -> tuple[RingName, ...]:
        return tuple(ring.name for ring in self._rings)

    def decide(self, request: GuardRequest) -> GuardDecision:
        started = self._clock()
        for ring in self._rings:
            try:
                verdict = ring.check(request)
            except Exception as exc:  # a broken ring must never let a request through
                _LOG.warning("guard ring %s failed (%s); the request is denied", ring.name, type(exc).__name__)
                return self._decision("DENY", None, "FAIL_CLOSED", started, request)
            if verdict.verdict != "UNSURE":
                return self._decision(verdict.verdict, verdict.confidence, ring.name, started, request)
        return self._decision("DENY", None, "FAIL_CLOSED", started, request)

    def _decision(
        self,
        decision: Decision,
        confidence: float | None,
        ring: DecidingRing,
        started: float,
        request: GuardRequest,
    ) -> GuardDecision:
        latency = max(0, round((self._clock() - started) * 1000))
        return GuardDecision(decision, confidence, ring, latency, request.language)


# ---- language ----

_TURKISH_LETTERS = re.compile("[çğıöşüÇĞİÖŞÜ]")
_WORD = re.compile(r"[^\W\d_]+")


def detect_language(text: str, tr_words: frozenset[str], en_words: frozenset[str]) -> Language:
    """A light rule (D-242b): Turkish letters and common words against common English words; undecided is Turkish."""
    words = [word.casefold() for word in _WORD.findall(text)]
    tr_score = sum(word in tr_words for word in words) + (2 if _TURKISH_LETTERS.search(text) else 0)
    en_score = sum(word in en_words for word in words)
    return "en" if en_score > tr_score else "tr"
