"""Risk scoring (`score_findings`): the `RiskModel` port and its rule baseline (P4.3, D-238c, D-239).

Until Model A exists (P7.5, `OnnxRiskModel` behind the same port) the scores come from `RuleBaselineRiskModel`: the
starting rule table of the crypto-domain skill. It is a reported baseline, not a stand-in: every score carries
`model_id = "rule_baseline_v1"` and the rule that decided it.

Rule table (crypto-domain, "Risk sınıfı"):
1. P0 outside test code → CRITICAL
2. P1 on an inter-service path or a field-device link → HIGH
3. P1 not on a network path, or P2 → MEDIUM
4. P3 → LOW
5. In test code (`locationKind = TEST_CODE`) one class lower (at least LOW).

A finding is on a path when a topology link lists it in `findingIds`; a link is a device link when one of its ends is a
`DEVICE` node. The score is the middle of the class range of core-service's thresholds (D-128), so core derives the same
class back: CRITICAL 0.90, HIGH 0.70, MEDIUM 0.475, LOW 0.175. These four values are chosen constants (D-238c), not a
measurement. A baseline has no feature contributions, so `riskFactors` is empty (nothing invented).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from src.tools.base_tool import SchemaStore, ToolCode, ToolContext

RiskClass = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]

BASELINE_MODEL_ID = "rule_baseline_v1"
CLASS_SCORES: Mapping[RiskClass, float] = {"CRITICAL": 0.90, "HIGH": 0.70, "MEDIUM": 0.475, "LOW": 0.175}
_ORDER: tuple[RiskClass, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass(frozen=True)
class RiskScore:
    finding_id: str
    risk_class: RiskClass
    risk_score: float
    rule: str


class RiskModel(Protocol):
    @property
    def model_id(self) -> str: ...

    def score(self, findings: Sequence[Mapping[str, Any]], topology: Mapping[str, Any] | None) -> list[RiskScore]: ...


class RuleBaselineRiskModel:
    @property
    def model_id(self) -> str:
        return BASELINE_MODEL_ID

    def score(self, findings: Sequence[Mapping[str, Any]], topology: Mapping[str, Any] | None) -> list[RiskScore]:
        on_path, on_device = _paths(topology)
        scores: list[RiskScore] = []
        for finding in findings:
            finding_id = str(finding["id"])
            risk_class, rule = _base_class(str(finding["priority"]), finding_id in on_path, finding_id in on_device)
            if finding.get("locationKind") == "TEST_CODE":
                risk_class = _ORDER[max(0, _ORDER.index(risk_class) - 1)]
                rule += "_test_code"
            scores.append(RiskScore(finding_id, risk_class, CLASS_SCORES[risk_class], rule))
        return scores


def _base_class(priority: str, on_path: bool, on_device: bool) -> tuple[RiskClass, str]:
    if priority == "P0":
        return "CRITICAL", "p0"
    if priority == "P1":
        if on_device:
            return "HIGH", "p1_device_link"
        return ("HIGH", "p1_service_path") if on_path else ("MEDIUM", "p1_off_path")
    if priority == "P2":
        return "MEDIUM", "p2"
    return "LOW", "p3"


def _paths(topology: Mapping[str, Any] | None) -> tuple[frozenset[str], frozenset[str]]:
    """Finding ids on any link, and those on a link with a DEVICE end."""
    if not topology:
        return frozenset(), frozenset()
    devices = {node["name"] for node in topology.get("nodes", []) if node.get("nodeKind") == "DEVICE"}
    on_path: set[str] = set()
    on_device: set[str] = set()
    for link in topology.get("links", []):
        ids = {str(finding_id) for finding_id in link.get("findingIds", [])}
        on_path |= ids
        if link.get("source") in devices or link.get("target") in devices:
            on_device |= ids
    return frozenset(on_path), frozenset(on_device)


class ScoreFindingsTool:
    """`score_findings`: findings as `list_findings` returns them, optionally the scan topology (`get_topology`)."""

    name = "score_findings"

    def __init__(self, model: RiskModel, schemas: SchemaStore) -> None:
        self._model = model
        self._input_schema = schemas.part(self.name, "input")
        self._output_schema = schemas.part(self.name, "output")

    @property
    def tool_code(self) -> ToolCode:
        return "RISK_MODEL"

    @property
    def input_schema(self) -> Mapping[str, Any]:
        return self._input_schema

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self._output_schema

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Mapping[str, Any]:
        scores = self._model.score(arguments["findings"], arguments.get("topology"))
        return {
            "model_id": self._model.model_id,
            "scores": [
                {
                    "findingId": score.finding_id,
                    "riskClass": score.risk_class,
                    "riskScore": score.risk_score,
                    "rule": score.rule,
                    "riskFactors": [],
                }
                for score in scores
            ],
        }
