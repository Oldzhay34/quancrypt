"""The rule baseline risk model (crypto-domain "Risk sınıfı", D-238c) against cases derived from QBank's approved golden
inventory and topology (`reference-system/expected/`, D-123).

How the golden data becomes model input: every inventory entry is a finding (`priority`, `location_kind`). A TLS key
exchange entry (`usage_context: TLS_KEY_EXCHANGE`) is listed on a topology link of the node its file belongs to (the
first path segment names the node; `field-device-sim` is the device `terminal-001`; a DEVICE_HYBRID_TLS entry goes on
the node's link with a DEVICE end, since the broker has a service link too); every other entry is on no link,
like the in-application RSA encryption (KEM_DEM_ENCRYPTION). The golden data has no test code and no P2, so those cases
are added on top.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import pytest
import yaml

from src.tools.risk_model_tool import BASELINE_MODEL_ID, CLASS_SCORES, RuleBaselineRiskModel
from tests.support.postgres import REPO_ROOT

EXPECTED = REPO_ROOT / "reference-system" / "expected"
CORE_SEED = REPO_ROOT / "services" / "core-service" / "src" / "main" / "resources" / "db" / "migration"
CORE_SEED = CORE_SEED / "V2__lookup_data.sql"

_NODE_KIND = {
    "external_client": "EXTERNAL_CLIENT",
    "gateway": "GATEWAY",
    "service": "SERVICE",
    "broker": "BROKER",
    "field_device": "DEVICE",
}
_NODE_OF_DIRECTORY = {"field-device-sim": "terminal-001"}


def _golden() -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    inventory = yaml.safe_load((EXPECTED / "crypto_inventory.yaml").read_text("utf-8"))["entries"]
    topology = yaml.safe_load((EXPECTED / "topology.yaml").read_text("utf-8"))
    findings = [
        {"id": f"golden-{index}", "priority": entry["priority"], "locationKind": entry["location_kind"]}
        for index, entry in enumerate(inventory)
    ]
    links = [{"source": edge["source"], "target": edge["target"], "findingIds": []} for edge in topology["edges"]]
    for finding, entry in zip(findings, inventory, strict=True):
        if entry["usage_context"] != "TLS_KEY_EXCHANGE":
            continue
        directory = entry["file"].split("/")[0]
        node = _NODE_OF_DIRECTORY.get(directory, directory)
        candidates = [link for link in links if node in (link["source"], link["target"])]
        if entry["strategy"] == "DEVICE_HYBRID_TLS":
            candidates = [link for link in candidates if "terminal-001" in (link["source"], link["target"])]
        candidates[0]["findingIds"].append(finding["id"])
    nodes = [{"name": node["id"], "nodeKind": _NODE_KIND[node["kind"]]} for node in topology["nodes"]]
    return findings, {"nodes": nodes, "links": links}, inventory


def _core_class(score: float) -> str:
    """The class core-service derives from a score (its seeded `risk_class_threshold`, D-128)."""
    thresholds: list[tuple[Decimal, str]] = [
        (Decimal(minimum), risk_class)
        for risk_class, minimum in re.findall(
            r"INSERT INTO risk_class_threshold \(risk_class, min_score\) VALUES \('(\w+)', ([0-9.]+)\);",
            CORE_SEED.read_text("utf-8"),
        )
    ]
    assert len(thresholds) == 4
    return next(
        risk_class for minimum, risk_class in sorted(thresholds, reverse=True) if Decimal(str(score)) >= minimum
    )


def test_the_golden_inventory_scores_as_the_rule_table_says() -> None:
    findings, topology, inventory = _golden()

    scores = {score.finding_id: score for score in RuleBaselineRiskModel().score(findings, topology)}

    assert len(scores) == len(inventory) == 53
    for finding, entry in zip(findings, inventory, strict=True):
        score = scores[finding["id"]]
        if entry["priority"] == "P0":
            expected = ("CRITICAL", "p0")
        elif entry["strategy"] == "DEVICE_HYBRID_TLS":
            expected = ("HIGH", "p1_device_link")
        elif entry["strategy"] == "HYBRID_TLS_KEX":
            expected = ("HIGH", "p1_service_path")
        elif entry["priority"] == "P1":
            expected = ("MEDIUM", "p1_off_path")  # KEM_DEM_ENCRYPTION: in-application, on no link
        else:
            expected = ("LOW", "p3")
        assert (score.risk_class, score.rule) == expected, entry["file"]


def test_the_golden_inventory_has_every_class_the_table_can_give_without_test_code() -> None:
    findings, topology, _ = _golden()

    classes = {score.risk_class for score in RuleBaselineRiskModel().score(findings, topology)}

    assert classes == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


@pytest.mark.parametrize(
    ("priority", "on_link", "expected", "rule"),
    [
        ("P0", False, "HIGH", "p0_test_code"),
        ("P1", True, "MEDIUM", "p1_service_path_test_code"),
        ("P1", False, "LOW", "p1_off_path_test_code"),
        ("P2", False, "LOW", "p2_test_code"),
        ("P3", False, "LOW", "p3_test_code"),  # never below LOW
    ],
)
def test_test_code_drops_one_class(priority: str, on_link: bool, expected: str, rule: str) -> None:
    finding = {"id": "f1", "priority": priority, "locationKind": "TEST_CODE"}
    topology = {"nodes": [], "links": [{"source": "a", "target": "b", "findingIds": ["f1"] if on_link else []}]}

    [score] = RuleBaselineRiskModel().score([finding], topology)

    assert (score.risk_class, score.rule) == (expected, rule)


def test_p2_is_medium_and_a_missing_topology_means_no_finding_is_on_a_path() -> None:
    findings = [
        {"id": "a", "priority": "P2", "locationKind": "CODE"},
        {"id": "b", "priority": "P1", "locationKind": "CODE"},
    ]

    scores = RuleBaselineRiskModel().score(findings, None)

    assert [(score.risk_class, score.rule) for score in scores] == [("MEDIUM", "p2"), ("MEDIUM", "p1_off_path")]


@pytest.mark.parametrize("risk_class", sorted(CLASS_SCORES))
def test_each_score_maps_back_to_its_class_with_the_core_thresholds(risk_class: str) -> None:
    assert _core_class(CLASS_SCORES[risk_class]) == risk_class  # type: ignore[index]


def test_the_baseline_names_itself() -> None:
    assert RuleBaselineRiskModel().model_id == BASELINE_MODEL_ID == "rule_baseline_v1"
