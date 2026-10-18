"""The supervisor agent (Mediator, P4.5): it reads the intent, dispatches and composes the answer.

The agents never call one another; the supervisor routes a request to the right one and turns the result into the
answer. It classifies the intent with the language model (`SUPERVISOR_INTENT`, few-shot from `templates`); if the model
is off or errors it falls back to the keyword map, and an out-of-list answer is `unknown` (D-248e). The inventory and
risk-priority intents go to the planner as a read-only task (D-248f); every other intent is answered from the knowledge
base (`ANSWER_WRITER`), and when there is no source the answer is the fixed "not sure" text with an expert-review
suggestion (guardrails-security section 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.agents.base_agent import (
    AgentContext,
    AgentResult,
    AgentRunner,
    AgentState,
    AgentTask,
    BaseAgent,
    Budget,
    Evidence,
    RunMeter,
)
from src.llm.provider import ChatMessage, LLMError, LLMProvider
from src.memory.long_term import KnowledgeBase, KnowledgeUnavailableError, RuntimeVersions
from src.memory.short_term import AuditLog
from src.prompts.system_prompts import ANSWER_WRITER, SUPERVISOR_INTENT, neutralize, unsure
from src.prompts.templates import INTENTS, few_shot_block, match_intent

_DISPATCH_INTENTS = frozenset({"inventory", "risk_priority"})


@dataclass
class SupervisorState(AgentState):
    intent: str = "unknown"
    sub_result: AgentResult | None = None
    answer_text: str = ""
    answer_evidence: tuple[Evidence, ...] = ()
    # The knowledge-base passages the answer rests on: the output checker compares the answer's numbers with them.
    passages: tuple[str, ...] = ()


class SupervisorAgent(BaseAgent[SupervisorState]):
    def __init__(
        self,
        llm: LLMProvider,
        knowledge: KnowledgeBase,
        audit: AuditLog,
        budget: Budget,
        runners: Mapping[str, AgentRunner],
    ) -> None:
        super().__init__("SUPERVISOR", budget, audit, llm=llm)
        self._knowledge = knowledge
        self._runners = runners

    def _new_state(self, task: AgentTask, meter: RunMeter) -> SupervisorState:
        return SupervisorState(meter=meter, task=task)

    def gather_context(self, context: AgentContext, state: SupervisorState) -> None:
        state.intent = self._intent(state)

    def act(self, context: AgentContext, state: SupervisorState) -> None:
        if state.intent in _DISPATCH_INTENTS:
            state.sub_result = self._dispatch(context, state)
        else:
            self._answer_from_knowledge(state)

    def report(self, context: AgentContext, state: SupervisorState) -> AgentResult:
        data: dict[str, Any] = {"intent": state.intent}
        if state.passages:
            data["passages"] = list(state.passages)
        if state.sub_result is not None:
            sub = state.sub_result
            data["inventory"] = sub.data
            return AgentResult(
                status=sub.status, text=sub.text, data=data, evidence=sub.evidence, error_code=sub.error_code
            )
        return AgentResult(status="COMPLETED", text=state.answer_text, data=data, evidence=state.answer_evidence)

    # ---- intent ----

    def _intent(self, state: SupervisorState) -> str:
        if state.task.intent is not None:  # the task router already chose it (D-252a)
            return state.task.intent if state.task.intent in INTENTS else "unknown"
        question = state.task.question or ""
        try:
            result = self._generate(
                state,
                (
                    ChatMessage(role="system", content=SUPERVISOR_INTENT.text),
                    ChatMessage(
                        role="user", content=f"{few_shot_block()}\n\nRequest: {question}\nAnswer with one intent code."
                    ),
                ),
                temperature=0,
                max_tokens=8,
            )
        except LLMError:
            return match_intent(question)
        if result.llm_disabled:
            return match_intent(question)
        answer = result.text.strip().lower()
        return answer if answer in INTENTS else "unknown"

    # ---- dispatch ----

    def _dispatch(self, context: AgentContext, state: SupervisorState) -> AgentResult:
        runner = self._runners.get("planner")
        if runner is None:
            raise RuntimeError("the supervisor has no planner runner")
        task = AgentTask(
            kind="inventory",
            language=state.task.language,
            project_id=state.task.project_id,
            scan_id=state.task.scan_id,
        )
        return runner.run(task, context)

    # ---- knowledge answer ----

    def _answer_from_knowledge(self, state: SupervisorState) -> None:
        question = state.task.question or ""
        lang = state.task.language
        state.meter.before_call()
        try:
            hits = self._knowledge.search(question, RuntimeVersions(), None)
        except KnowledgeUnavailableError:
            state.answer_text = unsure(lang)
            return
        if not hits:
            state.answer_text = unsure(lang)
            return
        evidence = tuple(
            Evidence(kind="knowledge_base", reference=hit.source_url or hit.doc_key, source_version=hit.version_tag)
            for hit in hits
        )
        sources = "\n".join(
            f"[{i + 1}] {neutralize(hit.title)} ({neutralize(hit.version_tag)}): {neutralize(hit.text)}"
            for i, hit in enumerate(hits)
        )
        try:
            result = self._generate(
                state,
                (
                    ChatMessage(role="system", content=ANSWER_WRITER.text),
                    ChatMessage(
                        role="user",
                        content=(
                            f"answer_language: {lang}\n<knowledge_base>\n{sources}\n</knowledge_base>\n"
                            f"<question>\n{neutralize(question)}\n</question>"
                        ),
                    ),
                ),
                temperature=0,
                max_tokens=512,
            )
        except LLMError:
            state.answer_text = unsure(lang)
            return
        if result.llm_disabled:
            titles = "; ".join(f"{hit.title} ({hit.version_tag})" for hit in hits)
            note = "[LLM disabled] " if lang == "en" else "[LLM kapalı] "
            state.answer_text = f"{note}{titles}"
            state.answer_evidence = evidence
            return
        state.answer_text = result.text.strip()
        state.answer_evidence = evidence
        state.passages = tuple(hit.text for hit in hits)
