"""What the three mining use cases share: logging a run whose `facts.json` holds every number of the report
(ml-pipeline section 6)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from quancrypt_ml.domain.mining_report import AnomalyFacts, ClusteringFacts, RuleFacts
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.risk import ModelRegistry, RunRecord

EXPERIMENT = "mining"
Facts = ClusteringFacts | RuleFacts | AnomalyFacts


def log_facts(
    registry: ModelRegistry,
    reports: ReportWriter,
    name: str,
    facts: Facts,
    params: Mapping[str, object],
    metrics: Mapping[str, float],
    folder: Path,
    charts: Sequence[Path],
) -> str:
    document = folder / name / "facts.json"
    reports.write(document, json.dumps(asdict(facts), indent=1, sort_keys=True) + "\n")
    return registry.log_run(
        EXPERIMENT, RunRecord(name, params, metrics, {"data_sha256": facts.data_sha256}, [document, *charts])
    )
