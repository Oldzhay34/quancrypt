"""The task router (P4.6, D-252a): picks the intent of an allowed message, rule first, the language model only when the
rules do not decide.

1. The keyword rules of `templates.match_intent` (Turkish and English phrases).
2. If no rule matches, the language model picks one code from the fixed intent list (`SUPERVISOR_INTENT`, few-shot
   examples). An answer outside the list is `unknown`, never a guess such as `tool_usage`.
3. Without a model (LLM-less mode) or on a model error the intent is `unknown`; `unknown` is answered from the knowledge
   base, and without a source the answer is "not sure" (agent-service-layout section 6).

The multi-class extension of Model B is out of scope (P4.6 prompt).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.llm.provider import ChatMessage, GenerationRequest, LLMError, LLMProvider, TokenUsage
from src.prompts.system_prompts import SUPERVISOR_INTENT, neutralize
from src.prompts.templates import INTENTS, few_shot_block, match_intent

RoutedBy = Literal["rule", "llm", "fallback"]
_NO_USAGE = TokenUsage(prompt_tokens=0, completion_tokens=0)


@dataclass(frozen=True)
class RoutedIntent:
    intent: str
    routed_by: RoutedBy
    usage: TokenUsage
    # True when the language model was asked and answered as the null provider (LLM-less mode).
    llm_disabled: bool = False


class TaskRouter:
    def __init__(self, llm: LLMProvider, max_tokens: int = 8) -> None:
        self._llm = llm
        self._max_tokens = max_tokens

    def route(self, text: str) -> RoutedIntent:
        ruled = match_intent(text)
        if ruled != "unknown":
            return RoutedIntent(ruled, "rule", _NO_USAGE)
        request = GenerationRequest(
            (
                ChatMessage(role="system", content=SUPERVISOR_INTENT.text),
                ChatMessage(
                    role="user",
                    content=(
                        f"{few_shot_block()}\n\n<question>\n{neutralize(text)}\n</question>\n"
                        "Answer with one intent code."
                    ),
                ),
            ),
            temperature=0,
            max_tokens=self._max_tokens,
        )
        try:
            result = self._llm.generate(request)
        except LLMError:
            return RoutedIntent("unknown", "fallback", _NO_USAGE)
        if result.llm_disabled:
            return RoutedIntent("unknown", "fallback", result.usage, llm_disabled=True)
        answer = result.text.strip().lower()
        return RoutedIntent(answer if answer in INTENTS else "unknown", "llm", result.usage)
