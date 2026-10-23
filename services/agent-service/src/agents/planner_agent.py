"""The planner agent (M6, UC3): it asks the clarification questions, scores the findings, creates the plan and
explains each item (P4.5).

For a `plan` task it reads the project profile; if any of the five clarification questions is unanswered it returns
`CLARIFICATION_REQUIRED` with the missing questions and does nothing else. With a full profile it lists the findings,
scores them (rule baseline or Model A), creates the plan and then writes a short explanation for each item in risk order
as far as the budget allows. Every explanation's input is only the item's own fields and its `kb_search` results, and it
carries the source; without a knowledge-base hit, without a model or out of budget it is a template note (D-248b: the
explanations are shown in the result, not stored in core-service).

For an `inventory` task (the supervisor's inventory and risk-priority intents, D-248f) it returns a read-only summary:
the findings, their risk classes from `score_findings` and the topology — it creates no plan.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.agents.base_agent import (
    AgentContext,
    AgentResult,
    AgentState,
    AgentTask,
    BaseAgent,
    Budget,
    BudgetExceeded,
    Evidence,
    RunMeter,
    Toolbox,
)
from src.llm.provider import ChatMessage, LLMError, LLMProvider
from src.memory.long_term import KnowledgeBase
from src.memory.short_term import AuditLog
from src.prompts.system_prompts import PLANNER_EXPLAIN, neutralize
from src.prompts.templates import CLARIFICATION_QUESTIONS, no_source_note, off_note, over_budget_note
from src.tools.base_tool import ToolError, ToolRejectedError, ToolResult

_PAGE_SIZE = 200
# An inventory answer cites at most this many code locations (D-252i).
_MAX_LOCATIONS = 20
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
# Family codes a question may name ("Servisler arasında RSA nerede?"); `ML-KEM` is written with a hyphen in prose.
_FAMILY_WORD = re.compile(
    r"\b(RSA|ECDSA|ECDH|EDDSA|DSA|DH|X25519|ML[-_]KEM|ML[-_]DSA|SLH[-_]DSA|AES|TRIPLE_DES|DES|CHACHA20|SHA1|SHA2|SHA3|MD5|HMAC)\b",
    re.IGNORECASE,
)


@dataclass
class PlannerState(AgentState):
    missing: list[str] = field(default_factory=list)
    findings: list[Mapping[str, Any]] = field(default_factory=list)
    topology: Mapping[str, Any] | None = None
    scores: list[Mapping[str, Any]] = field(default_factory=list)
    plan_items: list[Mapping[str, Any]] = field(default_factory=list)
    explanations: list[dict[str, Any]] = field(default_factory=list)
    runtime: tuple[str | None, str | None] = (None, None)
    plan_existed: bool = False


class PlannerAgent(BaseAgent[PlannerState]):
    def __init__(
        self, toolbox: Toolbox, llm: LLMProvider, knowledge: KnowledgeBase, audit: AuditLog, budget: Budget
    ) -> None:
        super().__init__("PLANNER", budget, audit, toolbox=toolbox, llm=llm)
        self._knowledge = knowledge

    def _new_state(self, task: AgentTask, meter: RunMeter) -> PlannerState:
        return PlannerState(meter=meter, task=task)

    def gather_context(self, context: AgentContext, state: PlannerState) -> None:
        if state.task.scan_id is None:
            raise ToolError("the planner needs a scan id")
        if state.task.kind == "plan":
            if state.task.project_id is None:
                raise ToolError("a plan task needs a project id")
            self._check_clarifications(context, state)
            if state.short_circuit:
                return
        state.findings = self._list_findings(context, state)
        state.topology = self._topology(context, state)

    def plan(self, context: AgentContext, state: PlannerState) -> None:
        if not state.findings:
            return
        scored = self._call_tool(
            state,
            "score_findings",
            {
                "findings": [
                    {"id": f["id"], "priority": f["priority"], "locationKind": f["locationKind"]}
                    for f in state.findings
                ],
                "topology": state.topology,
            },
            self._context(context),
        )
        state.scores = list(_out(scored)["scores"])

    def act(self, context: AgentContext, state: PlannerState) -> None:
        if state.task.kind != "plan" or not state.scores:
            return
        existing = self._existing_plan(context, state)
        if existing is None:
            # D-252c: no plan yet, so this request creates it; an existing plan is only read (and explained).
            items = [
                {"findingId": score["findingId"], "riskScore": score["riskScore"], "riskFactors": score["riskFactors"]}
                for score in state.scores
            ]
            self._call_tool(
                state,
                "create_plan",
                {"scanId": str(state.task.scan_id), "body": {"items": items}},
                self._context(context),
            )
            state.plan_items = self._get_plan(context, state)
        else:
            state.plan_existed = True
            state.plan_items = existing
        self._explain(context, state)

    def report(self, context: AgentContext, state: PlannerState) -> AgentResult:
        if state.short_circuit:  # never reached (gather_context short-circuited), but keeps the type total
            return AgentResult(status="CLARIFICATION_REQUIRED", clarifications=tuple(state.missing))
        if state.task.kind == "plan":
            return self._plan_result(state)
        return self._inventory_result(state)

    # ---- clarification ----

    def _check_clarifications(self, context: AgentContext, state: PlannerState) -> None:
        profile = _out(
            self._call_tool(
                state, "get_project_profile", {"projectId": str(state.task.project_id)}, self._context(context)
            )
        )
        runtime = profile["runtimeProfile"]
        if runtime is not None:
            state.runtime = (runtime.get("javaVersion"), runtime.get("springBootVersion"))
        answered = {answer["questionCode"] for answer in profile["answers"] if _is_answered(answer)}
        state.missing = [code for code in CLARIFICATION_QUESTIONS if code not in answered]
        if state.missing:
            questions = [
                {
                    "questionCode": code,
                    "textTr": CLARIFICATION_QUESTIONS[code][0],
                    "textEn": CLARIFICATION_QUESTIONS[code][1],
                }
                for code in state.missing
            ]
            lang = state.task.language
            text = "\n".join(q["textEn" if lang == "en" else "textTr"] for q in questions)
            state.result = AgentResult(
                status="CLARIFICATION_REQUIRED",
                text=text,
                data={"questions": questions},
                clarifications=tuple(state.missing),
            )
            state.short_circuit = True

    # ---- reads ----

    def _list_findings(self, context: AgentContext, state: PlannerState) -> list[Mapping[str, Any]]:
        findings: list[Mapping[str, Any]] = []
        page = 0
        while True:
            body = _out(
                self._call_tool(
                    state,
                    "list_findings",
                    {"scanId": str(state.task.scan_id), "page": page, "size": _PAGE_SIZE},
                    self._context(context),
                )
            )
            findings.extend(body["items"])
            if (page + 1) * _PAGE_SIZE >= int(body["totalElements"]):
                break
            page += 1
        return findings

    def _topology(self, context: AgentContext, state: PlannerState) -> Mapping[str, Any] | None:
        try:
            return _out(
                self._call_tool(state, "get_topology", {"scanId": str(state.task.scan_id)}, self._context(context))
            )
        except ToolRejectedError as exc:
            if exc.status == 404:  # a scan may have no topology; scoring then runs without it
                return None
            raise

    def _existing_plan(self, context: AgentContext, state: PlannerState) -> list[Mapping[str, Any]] | None:
        try:
            return self._get_plan(context, state)
        except ToolRejectedError as exc:
            if exc.status == 404:  # no plan for this scan yet
                return None
            raise

    def _get_plan(self, context: AgentContext, state: PlannerState) -> list[Mapping[str, Any]]:
        items: list[Mapping[str, Any]] = []
        page = 0
        while True:
            body = _out(
                self._call_tool(
                    state,
                    "get_plan",
                    {"scanId": str(state.task.scan_id), "page": page, "size": _PAGE_SIZE},
                    self._context(context),
                )
            )
            items.extend(body["items"])
            if (page + 1) * _PAGE_SIZE >= int(body["totalElements"]):
                break
            page += 1
        return items

    # ---- explanations ----

    def _explain(self, context: AgentContext, state: PlannerState) -> None:
        by_id = {finding["id"]: finding for finding in state.findings}
        ordered = sorted(state.plan_items, key=lambda item: float(item["riskScore"]), reverse=True)
        exhausted = False
        for item in ordered:
            finding = by_id.get(item["findingId"])
            if finding is None:
                continue
            lang = state.task.language
            explanation: str
            evidence: list[Evidence]
            note: str | None
            if exhausted:
                explanation, evidence, note = over_budget_note(item, finding, lang), [], "budget"
            else:
                try:
                    explanation, evidence, note = self._explain_item(context, state, item, finding)
                except BudgetExceeded:
                    # The plan already exists in core-service: out of tokens only ends the explanations.
                    exhausted = True
                    explanation, evidence, note = over_budget_note(item, finding, lang), [], "budget"
                except LLMError:
                    explanation, evidence, note = off_note(item, finding, lang), [], "llm_off"
            state.explanations.append(
                {
                    "findingId": item["findingId"],
                    "strategy": item["strategy"],
                    "effort": item["effort"],
                    "riskClass": item["riskClass"],
                    "riskScore": item["riskScore"],
                    "text": explanation,
                    "note": note,
                    "sources": [e.reference for e in evidence],
                }
            )
            state.evidence.extend(evidence)

    def _explain_item(
        self, context: AgentContext, state: PlannerState, item: Mapping[str, Any], finding: Mapping[str, Any]
    ) -> tuple[str, list[Evidence], str | None]:
        lang = state.task.language
        # Keep one step for a final tail; an explanation costs up to two (kb_search + generate).
        if state.meter.remaining_steps() < 2 or state.meter.out_of_time():
            return over_budget_note(item, finding, lang), [], "budget"
        hits = _out(
            self._call_tool(
                state,
                "kb_search",
                {
                    "query": _query(item, finding),
                    "java_version": state.runtime[0],
                    "spring_boot_version": state.runtime[1],
                    "k": 3,
                },
                self._context(context),
            )
        )["hits"]
        if not hits:
            return no_source_note(item, finding, lang), [], "no_source"
        evidence = [
            Evidence(
                kind="knowledge_base",
                reference=hit["source_url"] or hit["doc_key"],
                source_version=hit["version_tag"],
                title=hit["title"],
            )
            for hit in hits
        ]
        result = self._generate(
            state,
            (
                ChatMessage(role="system", content=PLANNER_EXPLAIN.text),
                ChatMessage(role="user", content=_explain_prompt(item, finding, hits, lang)),
            ),
            temperature=0,
            max_tokens=512,
        )
        if result.llm_disabled:
            return off_note(item, finding, lang), evidence, "llm_off"
        return result.text.strip(), evidence, None

    # ---- results ----

    def _plan_result(self, state: PlannerState) -> AgentResult:
        classes = _distribution(item["riskClass"] for item in state.plan_items)
        data = {
            "scanId": str(state.task.scan_id),
            "itemCount": len(state.plan_items),
            "byRiskClass": classes,
            "explanations": state.explanations,
        }
        data["planExisted"] = state.plan_existed
        count = len(state.plan_items)
        if state.task.language == "en":
            head = "Existing plan" if state.plan_existed else "Plan created"
            text = f"{head}: {count} items. By risk class: {_fmt(classes)}."
        else:
            head = "Mevcut plan" if state.plan_existed else "Plan oluşturuldu"
            text = f"{head}: {count} madde. Risk sınıfına göre: {_fmt(classes)}."
        return AgentResult(status="COMPLETED", text=text, data=data, evidence=tuple(state.evidence))

    def _inventory_result(self, state: PlannerState) -> AgentResult:
        families = _distribution(f["algorithmFamily"] for f in state.findings)
        priorities = _distribution(f["priority"] for f in state.findings)
        classes = _distribution(score["riskClass"] for score in state.scores)
        data = {
            "scanId": str(state.task.scan_id),
            "findings": len(state.findings),
            "byAlgorithmFamily": families,
            "byPriority": priorities,
            "byRiskClass": classes,
        }
        if state.task.language == "en":
            text = (
                f"{len(state.findings)} findings. By algorithm family: {_fmt(families)}. "
                f"By priority: {_fmt(priorities)}. By risk class: {_fmt(classes)}."
            )
        else:
            text = (
                f"{len(state.findings)} bulgu. Algoritma ailesine göre: {_fmt(families)}. "
                f"Önceliğe göre: {_fmt(priorities)}. Risk sınıfına göre: {_fmt(classes)}."
            )
        locations = _locations(state.findings, state.topology, state.task.question)
        if locations:
            listing = "; ".join(f"{loc['family']} {loc['reference']}" for loc in locations)
            text += (" Locations: " if state.task.language == "en" else " Konumlar: ") + listing + "."
        evidence = tuple(Evidence(kind="code_location", reference=loc["reference"]) for loc in locations)
        data["locations"] = [loc["reference"] for loc in locations]
        return AgentResult(status="COMPLETED", text=text, data=data, evidence=evidence)


def _locations(
    findings: Sequence[Mapping[str, Any]], topology: Mapping[str, Any] | None, question: str | None
) -> list[dict[str, str]]:
    """Code locations for an inventory answer (D-252i): the findings of a family the question names (all when it names
    none), those on topology links (between services) first and all of them when no link carries one, most urgent
    first, at most `_MAX_LOCATIONS` (D-257)."""
    named = {match.upper().replace("-", "_") for match in _FAMILY_WORD.findall(question or "")}
    on_links = {str(fid) for link in (topology or {}).get("links", []) for fid in link.get("findingIds", [])}
    wanted = [f for f in findings if not named or f["algorithmFamily"] in named]
    pool = [f for f in wanted if str(f["id"]) in on_links] or wanted
    pool.sort(key=lambda f: (_PRIORITY_ORDER.get(str(f["priority"]), 9), str(f["path"]), f.get("lineStart") or 0))
    result = []
    for finding in pool[:_MAX_LOCATIONS]:
        line = finding.get("lineStart")
        reference = f"{finding['path']}:{line}" if line else str(finding["path"])
        result.append({"family": str(finding["algorithmFamily"]), "reference": reference[:1024]})
    return result


def _is_answered(answer: Mapping[str, Any]) -> bool:
    return answer.get("optionCode") is not None or answer.get("freeText") is not None


def _query(item: Mapping[str, Any], finding: Mapping[str, Any]) -> str:
    return f"{item['strategy']} {finding['algorithmFamily']} {finding['usageContext']} quantum-safe migration"


def _explain_prompt(
    item: Mapping[str, Any], finding: Mapping[str, Any], hits: Sequence[Mapping[str, Any]], lang: str
) -> str:
    sources = "\n".join(
        f"[{index + 1}] {neutralize(hit['title'])} ({neutralize(hit['version_tag'])}): {neutralize(hit['text'])}"
        for index, hit in enumerate(hits)
    )
    return (
        f"strategy: {item['strategy']}\n"
        f"effort: {item['effort']}\n"
        f"risk_class: {item['riskClass']}\n"
        f"algorithm_family: {finding['algorithmFamily']}\n"
        f"usage_context: {finding['usageContext']}\n"
        f"answer_language: {lang}\n"
        f"<knowledge_base>\n{sources}\n</knowledge_base>"
    )


def _distribution(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _fmt(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{name}: {count}" for name, count in sorted(counts.items())) or "-"


def _out(result: ToolResult) -> Mapping[str, Any]:
    if result.output is None:
        raise ToolError("a tool returned no output")
    return result.output
