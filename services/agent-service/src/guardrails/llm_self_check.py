"""Ring 3, the LLM self-check (guardrails-security section 2): a fixed prompt, temperature 0, a label and nothing else.

The answer, trimmed of surrounding whitespace, must be exactly `IN_SCOPE` (ALLOW) or `OUT_OF_SCOPE` (DENY); any other
answer is DENY. Without a language model (NullProvider) or when the model cannot be reached, the ring is UNSURE, so the
chain ends in DENY (fail-closed, D-242c). The request is the user message, never part of the system prompt.
"""

from __future__ import annotations

import logging

from src.guardrails.chain import GuardRequest, RingName, RingVerdict
from src.llm.provider import ChatMessage, GenerationRequest, LLMError, LLMProvider
from src.prompts.system_prompts import SCOPE_SELF_CHECK

_LOG = logging.getLogger("src.guardrails")


class LLMSelfCheck:
    def __init__(self, llm: LLMProvider, max_tokens: int) -> None:
        self._llm = llm
        self._max_tokens = max_tokens

    @property
    def name(self) -> RingName:
        return "LLM_SELF_CHECK"

    def check(self, request: GuardRequest) -> RingVerdict:
        generation = GenerationRequest(
            messages=(ChatMessage("system", SCOPE_SELF_CHECK.text), ChatMessage("user", request.text)),
            temperature=0,
            max_tokens=self._max_tokens,
        )
        try:
            result = self._llm.generate(generation)
        except LLMError as exc:
            _LOG.warning("scope self-check unavailable (%s)", type(exc).__name__)
            return RingVerdict("UNSURE")
        if result.llm_disabled:
            return RingVerdict("UNSURE")
        label = result.text.strip()
        if label == "IN_SCOPE":
            return RingVerdict("ALLOW")
        if label != "OUT_OF_SCOPE":
            _LOG.info("scope self-check answered without an exact label; the request is denied")
        return RingVerdict("DENY")
