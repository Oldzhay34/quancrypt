"""The discovery agent (M4, UC1): it scans a project's cryptography and records the inventory (P4.5).

It starts a scan, runs the static analyzer, classifies the findings the analyzer left uncertain (with the language
model, within a step allowance that always keeps the recording steps) and records the findings and the CBOM. A
successful scan stays RUNNING: the initial-scan workflow completes it after the topology is recorded, because
core-service takes a topology only for a running scan (D-256); on its own failure discovery closes the scan as FAILED
(D-250b). The inventory comes from static analysis; the language model only resolves uncertain algorithm families, and
discovery recomputes the priority of its choice with a port of the crypto-domain table (D-186, D-248d), so a family that
needs no migration is dropped. Without a model the inventory is still recorded (NFR-05): the uncertain findings stay
UNKNOWN.

`classify_priority` below is a Python port of analyzer-service's `PriorityClassifier` (D-149, D-151): the agent must
compute the same priority core-service would accept. A drift test checks it against the QBank golden inventory.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
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
from src.memory.short_term import AuditLog
from src.prompts.system_prompts import DISCOVERY_CLASSIFY, neutralize
from src.tools.base_tool import ToolError, ToolResult

# ---- the priority table port (crypto-domain, D-149, D-151; port of analyzer PriorityClassifier) ----

_LOG = logging.getLogger("src.agents")

MIN_SAFE_RSA_BITS = 2048

_FAMILIES = frozenset(
    {
        "RSA",
        "ECDSA",
        "ECDH",
        "EDDSA",
        "DH",
        "DSA",
        "ML_KEM",
        "ML_DSA",
        "SLH_DSA",
        "AES",
        "DES",
        "TRIPLE_DES",
        "CHACHA20",
        "SHA1",
        "SHA2",
        "SHA3",
        "MD5",
        "HMAC",
        "X25519",
        "HYBRID_X25519_MLKEM768",
        "UNKNOWN",
    }
)
_VULNERABLE = frozenset({"RSA", "ECDSA", "ECDH", "EDDSA", "DH", "DSA", "X25519"})
_RESISTANT = frozenset({"ML_KEM", "ML_DSA", "SLH_DSA", "HYBRID_X25519_MLKEM768"})
_SIGNATURE_CONTEXTS = frozenset({"SIGNATURE", "TOKEN_SIGNATURE", "CERTIFICATE", "TLS_SERVER_AUTH", "MTLS_CLIENT_AUTH"})
_KEY_ESTABLISHMENT = frozenset({"ENCRYPTION", "KEY_WRAP", "KEY_AGREEMENT"})
_IDENTITY_AND_CERTIFICATES = frozenset({"TLS_SERVER_AUTH", "MTLS_CLIENT_AUTH", "CERTIFICATE"})


@dataclass(frozen=True)
class Derived:
    """The table gives this priority; core-service accepts only this one."""

    priority: str


@dataclass(frozen=True)
class NotApplicable:
    """The usage needs no migration (strong symmetric or hash, quantum resistant); core-service would reject it."""


@dataclass(frozen=True)
class Undetermined:
    """Algorithm or context is unknown: no definite migration priority."""


PriorityVerdict = Derived | NotApplicable | Undetermined


def classify_priority(
    family: str,
    usage_context: str,
    *,
    key_size_bits: int | None,
    mode: str | None,
    padding: str | None,
    location_kind: str,
) -> PriorityVerdict:
    """The crypto-domain priority table; the first matching rule wins (port of analyzer `PriorityClassifier`)."""
    if _weak_classic(family, usage_context, key_size_bits, mode, padding):
        return Derived("P0")
    if usage_context == "KEYSTORE" or location_kind == "KEYSTORE_FILE":
        return Derived("P3")
    if family == "UNKNOWN" or usage_context == "UNKNOWN":
        return Undetermined()
    if family not in _VULNERABLE:  # resistant, symmetric or hash: no migration
        return NotApplicable()
    if usage_context == "TLS_KEY_EXCHANGE" or usage_context in _KEY_ESTABLISHMENT:
        return Derived("P1")
    if usage_context == "SIGNATURE":
        return Derived("P2")
    if usage_context == "TOKEN_SIGNATURE" or usage_context in _IDENTITY_AND_CERTIFICATES:
        return Derived("P3")
    return Undetermined()


def _weak_classic(
    family: str, usage_context: str, key_size_bits: int | None, mode: str | None, padding: str | None
) -> bool:
    weak_cipher = family in ("DES", "TRIPLE_DES")
    weak_rsa_key = family == "RSA" and key_size_bits is not None and key_size_bits < MIN_SAFE_RSA_BITS
    broken_digest = family in ("MD5", "SHA1")
    weak_digest_in_signature = broken_digest and usage_context in _SIGNATURE_CONTEXTS
    ecb_block_cipher = (family == "AES" or weak_cipher) and mode == "ECB"
    rsa_v15_encryption = family == "RSA" and padding == "PKCS1_V1_5" and usage_context in _KEY_ESTABLISHMENT
    return weak_cipher or weak_rsa_key or weak_digest_in_signature or ecb_block_cipher or rsa_v15_encryption


# ---- the agent ----

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
# Steps kept for the tail of the run so the inventory is always written: record_findings, record_scan_artifact.
_RESERVED_STEPS = 2
# core-service's per-scan finding limit (D-141).
MAX_FINDINGS = 500
# Classification stops when less than this share of the time budget is left, so recording still fits (D-250b).
_TIME_RESERVE_SHARE = 0.25


@dataclass
class DiscoveryState(AgentState):
    scan_id: str | None = None
    analysis: Mapping[str, Any] | None = None
    core_findings: list[dict[str, Any]] = field(default_factory=list)
    uncertain: list[int] = field(default_factory=list)
    classified: int = 0
    created_count: int = 0
    existing_count: int = 0
    llm_off: bool = False
    dropped_over_limit: int = 0


class DiscoveryAgent(BaseAgent[DiscoveryState]):
    def __init__(
        self,
        toolbox: Toolbox,
        llm: LLMProvider,
        audit: AuditLog,
        budget: Budget,
        *,
        uncertain_below: float,
        llm_confidence: float,
    ) -> None:
        super().__init__("DISCOVERY", budget, audit, toolbox=toolbox, llm=llm)
        self._uncertain_below = uncertain_below
        self._llm_confidence = llm_confidence

    def _new_state(self, task: AgentTask, meter: RunMeter) -> DiscoveryState:
        return DiscoveryState(meter=meter, task=task)

    def gather_context(self, context: AgentContext, state: DiscoveryState) -> None:
        if state.task.project_id is None or state.task.root is None:
            raise ToolError("discovery needs a project id and a root")
        scan = self._call_tool(state, "start_scan", {"projectId": str(state.task.project_id)}, self._context(context))
        state.scan_id = str(_out(scan)["id"])
        analysis = self._call_tool(state, "analyze_crypto", {"body": {"root": state.task.root}}, self._context(context))
        state.analysis = _out(analysis)

    def plan(self, context: AgentContext, state: DiscoveryState) -> None:
        analysis = state.analysis
        if analysis is None:
            raise ToolError("discovery has no analysis")
        cbom = analysis["cbom"]
        if cbom.get("bomFormat") != "CycloneDX" or cbom.get("specVersion") != "1.6":
            raise ToolError("the CBOM is not CycloneDX 1.6")
        state.core_findings = [_to_core_finding(finding) for finding in analysis["findings"]]
        state.uncertain = sorted(
            (index for index, finding in enumerate(analysis["findings"]) if self._is_uncertain(finding)),
            key=lambda index: _PRIORITY_ORDER.get(str(analysis["findings"][index]["priority"]), 9),
        )

    def act(self, context: AgentContext, state: DiscoveryState) -> None:
        self._classify(context, state)
        self._record(context, state)

    def _on_failure(self, context: AgentContext, state: DiscoveryState) -> bool:
        """Close a started but unfinished scan as FAILED; it would block the project's next scan (D-250b)."""
        if state.scan_id is None:
            return False
        try:
            self._call_tool_unbudgeted(
                "complete_scan", {"scanId": state.scan_id, "body": {"outcome": "FAILED"}}, self._context(context)
            )
        except ToolError:
            _LOG.warning("agent DISCOVERY could not close scan as FAILED")
        return True

    def _partial_data(self, state: DiscoveryState) -> Mapping[str, Any] | None:
        return {"scanId": state.scan_id} if state.scan_id is not None else None

    def report(self, context: AgentContext, state: DiscoveryState) -> AgentResult:
        families: dict[str, int] = {}
        priorities: dict[str, int] = {}
        for finding in state.core_findings:
            families[finding["algorithmFamily"]] = families.get(finding["algorithmFamily"], 0) + 1
            priorities[finding["priority"]] = priorities.get(finding["priority"], 0) + 1
        remaining = len(state.uncertain) - state.classified
        data = {
            "scanId": state.scan_id,
            "findingsRecorded": state.created_count,
            "findingsExisting": state.existing_count,
            "classifiedByLlm": state.classified,
            "uncertainRemaining": remaining,
            "droppedOverLimit": state.dropped_over_limit,
            "byAlgorithmFamily": families,
            "byPriority": priorities,
        }
        text = self._summary(state, families, priorities, remaining)
        return AgentResult(status="COMPLETED", text=text, data=data, evidence=tuple(state.evidence))

    # ---- classification ----

    def _is_uncertain(self, finding: Mapping[str, Any]) -> bool:
        return finding["algorithm_family"] == "UNKNOWN" or float(finding["confidence"]) < self._uncertain_below

    def _classify(self, context: AgentContext, state: DiscoveryState) -> None:
        if state.task.root is None:
            return
        for position in state.uncertain:
            # Keep the reserved tail (record + complete); a classification costs two steps (snippet + generate).
            if (
                state.meter.remaining_steps() <= _RESERVED_STEPS + 1
                or state.meter.time_left_share() < _TIME_RESERVE_SHARE
            ):
                break
            finding = (state.analysis or {})["findings"][position]
            snippet = self._call_tool(
                state,
                "get_snippet",
                {
                    "root": state.task.root,
                    "path": finding["file"],
                    "line": finding["line_start"] or 1,
                    "context": 10,
                },
                self._context(context),
            )
            try:
                family = self._ask_family(state, finding, _out(snippet))
            except (BudgetExceeded, LLMError):
                # Out of tokens or the model failed: classification is optional, the inventory is not (NFR-05). The
                # rest stays UNKNOWN and recording goes on.
                break
            if family is None:  # the model is off, or gave no usable answer: stop classifying, keep the rest UNKNOWN
                if state.llm_off:
                    break
                continue
            self._apply(state, position, finding, family)
            state.classified += 1

    def _ask_family(self, state: DiscoveryState, finding: Mapping[str, Any], snippet: Mapping[str, Any]) -> str | None:
        source = neutralize(f"{finding['file']}:{finding['line_start'] or 1}")
        body = "\n".join(f"{line['number']}: {neutralize(line['text'])}" for line in snippet["lines"])
        block = f'<project_data source="{source}">\n{body}\n</project_data>'
        result = self._generate(
            state,
            (ChatMessage(role="system", content=DISCOVERY_CLASSIFY.text), ChatMessage(role="user", content=block)),
            temperature=0,
            max_tokens=16,
        )
        if result.llm_disabled:
            state.llm_off = True
            return None
        answer = result.text.strip().upper()
        return answer if answer in _FAMILIES and answer != "UNKNOWN" else None

    def _apply(self, state: DiscoveryState, position: int, finding: Mapping[str, Any], family: str) -> None:
        verdict = classify_priority(
            family,
            finding["usage_context"],
            key_size_bits=finding["key_size_bits"],
            mode=finding["mode"],
            padding=finding["padding"],
            location_kind=finding["location_kind"],
        )
        if not isinstance(verdict, Derived):  # non-migration or still undetermined: keep the finding as STATIC
            return
        current = _PRIORITY_ORDER.get(str(finding["priority"]), 9)
        if _PRIORITY_ORDER[verdict.priority] > current:
            # D-250a: the model may never make a finding less urgent than the analyzer found it.
            return
        mapped = state.core_findings[position]
        mapped["algorithmFamily"] = family
        mapped["priority"] = verdict.priority
        mapped["confidence"] = self._llm_confidence
        mapped["classifiedBy"] = "LLM"
        state.evidence.append(
            Evidence(kind="code_location", reference=f"{finding['file']}:{finding['line_start'] or 1}")
        )

    # ---- recording ----

    def _record(self, context: AgentContext, state: DiscoveryState) -> None:
        if len(state.core_findings) > MAX_FINDINGS:
            # D-250c: core-service takes at most 500 findings per scan; the most urgent 500 are recorded, the rest is
            # counted in the result and the summary (no silent loss).
            ranked = sorted(state.core_findings, key=lambda f: _PRIORITY_ORDER.get(str(f["priority"]), 9))
            state.dropped_over_limit = len(ranked) - MAX_FINDINGS
            state.core_findings = ranked[:MAX_FINDINGS]
        if state.core_findings:
            for batch in _batches(state.core_findings, 500):
                result = self._call_tool(
                    state,
                    "record_findings",
                    {"scanId": state.scan_id, "body": {"findings": batch}},
                    self._context(context),
                )
                out = _out(result)
                state.created_count += int(out["createdCount"])
                state.existing_count += int(out["existingCount"])
        self._call_tool(
            state,
            "record_scan_artifact",
            {"scanId": state.scan_id, "body": (state.analysis or {})["cbom"]},
            self._context(context),
        )

    def _summary(
        self, state: DiscoveryState, families: Mapping[str, int], priorities: Mapping[str, int], remaining: int
    ) -> str:
        parts_family = ", ".join(f"{name}: {count}" for name, count in sorted(families.items())) or "-"
        parts_priority = ", ".join(f"{name}: {count}" for name, count in sorted(priorities.items())) or "-"
        if state.task.language == "en":
            lines = [
                f"Scan complete: {state.created_count} findings recorded.",
                f"By algorithm family: {parts_family}.",
                f"By priority: {parts_priority}.",
            ]
            if remaining:
                lines.append(f"{remaining} finding(s) left UNKNOWN (no classification).")
            if state.dropped_over_limit:
                lines.append(
                    f"{state.dropped_over_limit} lower-priority finding(s) were not recorded (limit {MAX_FINDINGS})."
                )
            return "\n".join(lines)
        lines = [
            f"Tarama tamamlandı: {state.created_count} bulgu kaydedildi.",
            f"Algoritma ailesine göre: {parts_family}.",
            f"Önceliğe göre: {parts_priority}.",
        ]
        if remaining:
            lines.append(f"{remaining} bulgu UNKNOWN kaldı (sınıflandırılmadı).")
        if state.dropped_over_limit:
            lines.append(f"{state.dropped_over_limit} düşük öncelikli bulgu kaydedilmedi (sınır {MAX_FINDINGS}).")
        return "\n".join(lines)


def _to_core_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    """analyzer snake_case to core-service camelCase (D-175), as the tools-live test maps it."""
    mapped: dict[str, Any] = {
        "path": finding["file"],
        "symbol": finding["symbol"],
        "algorithmFamily": finding["algorithm_family"],
        "usageContext": finding["usage_context"],
        "locationKind": finding["location_kind"],
        "priority": finding["priority"],
        "keySizeBits": finding["key_size_bits"],
        "confidence": finding["confidence"],
        "classifiedBy": "STATIC",
    }
    if finding["line_start"] is not None:
        mapped["lineStart"], mapped["lineEnd"] = finding["line_start"], finding["line_end"]
    return mapped


def _batches(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _out(result: ToolResult) -> Mapping[str, Any]:
    if result.output is None:
        raise ToolError("a tool returned no output")
    return result.output
