"""The real contracts/schemas/events/*.json against the real classifier (what ingest-api does with every envelope)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from quancrypt_data.domain.events import SOURCE_BY_EVENT_TYPE, QuarantineReason
from quancrypt_data.infrastructure.schema.json_schema_catalog import JsonSchemaCatalog, SchemaCatalogError
from quancrypt_data.usecase.classification import EventClassifier
from tests.support.envelopes import PAYLOADS, envelope

SCHEMAS = Path(__file__).resolve().parents[3] / "contracts" / "schemas" / "events"


@pytest.fixture(scope="module")
def catalog() -> JsonSchemaCatalog:
    return JsonSchemaCatalog(SCHEMAS)


def test_every_schema_file_is_an_event_type_the_domain_knows(catalog: JsonSchemaCatalog) -> None:
    # A new schema file must come with a source (SOURCE_BY_EVENT_TYPE) and a lookup row (migration), or the event is quarantined.
    assert catalog.event_types == set(SOURCE_BY_EVENT_TYPE)
    assert {p.stem for p in SCHEMAS.glob("*.json")} == set(SOURCE_BY_EVENT_TYPE)


@pytest.mark.parametrize("event_type", sorted(PAYLOADS))
def test_the_envelope_the_relays_send_is_valid(catalog: JsonSchemaCatalog, event_type: str) -> None:
    assert catalog.violations(envelope(event_type)) == []
    classified = EventClassifier(catalog).classify(0, envelope(event_type))
    # A consent_revoked record is a command (it erases), every other type is an event.
    assert (classified.revocation is not None) if event_type == "consent_revoked" else (classified.event is not None)
    assert classified.rejection is None


@pytest.mark.parametrize("event_type", sorted(PAYLOADS))
def test_an_unexpected_field_in_the_envelope_or_the_payload_is_a_violation(
    catalog: JsonSchemaCatalog, event_type: str
) -> None:
    extra_envelope = envelope(event_type)
    extra_envelope["surprise"] = 1
    extra_payload = envelope(event_type)
    extra_payload["payload"]["surprise"] = 1

    assert catalog.violations(extra_envelope) == ["$: additionalProperties"]
    assert catalog.violations(extra_payload) == ["$.payload: additionalProperties"]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda e: e.pop("payload"), "$: required"),
        (lambda e: e.update(schema_version=2), "$.schema_version: const"),
        (lambda e: e.update(project_key="A" * 64), "$.project_key: pattern"),
        (lambda e: e.update(project_key="a" * 10), "$.project_key: pattern"),
        (lambda e: e.update(event_id="not-a-uuid"), "$.event_id: format"),
        (lambda e: e["payload"].update(priority="P9"), "$.payload.priority: enum"),
        (lambda e: e["payload"].update(confidence=2), "$.payload.confidence: maximum"),
        (lambda e: e.update(payload="text"), "$.payload: type"),
    ],
)
def test_a_violation_names_the_path_and_the_rule(catalog: JsonSchemaCatalog, mutate: Any, expected: str) -> None:
    item = envelope("finding_detected")
    mutate(item)

    assert expected in catalog.violations(item)


def test_a_violation_never_repeats_the_offending_value(catalog: JsonSchemaCatalog) -> None:
    secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    item = envelope("finding_detected")
    item["payload"]["priority"] = secret
    item["project_key"] = secret

    assert secret not in " ".join(catalog.violations(item))


def test_the_cross_field_rules_of_scope_decision_hold(catalog: JsonSchemaCatalog) -> None:
    bad = envelope("scope_decision")
    bad["payload"].update(deciding_ring="RULE_FILTER")  # a rule filter has no confidence
    allow_on_fail_closed = envelope("scope_decision")
    allow_on_fail_closed["payload"].update(deciding_ring="FAIL_CLOSED", confidence=None, decision="ALLOW")

    assert catalog.violations(bad)
    assert catalog.violations(allow_on_fail_closed)


def test_an_event_type_without_a_schema_is_unknown_to_the_classifier(catalog: JsonSchemaCatalog) -> None:
    item = envelope("finding_detected")
    item["event_type"] = "made_up"

    classified = EventClassifier(catalog).classify(0, item)

    assert classified.rejection is not None
    assert classified.rejection.reason is QuarantineReason.UNKNOWN_EVENT_TYPE


def test_a_date_time_the_schema_library_does_not_check_is_checked_by_the_domain(catalog: JsonSchemaCatalog) -> None:
    item = envelope("finding_detected", occurred_at="last tuesday")

    assert catalog.violations(item) == []  # date-time needs an extra package; the classifier reads the timestamp itself
    classified = EventClassifier(catalog).classify(0, item)
    assert classified.rejection is not None
    assert classified.rejection.reason is QuarantineReason.SCHEMA_VIOLATION


def test_the_relays_timestamps_with_and_without_fractions_are_accepted(catalog: JsonSchemaCatalog) -> None:
    for stamp in ("2026-10-09T10:00:00Z", "2026-10-09T10:00:00.123456Z", "2026-10-09T10:00:00.1Z"):
        assert EventClassifier(catalog).classify(0, envelope(occurred_at=stamp)).event is not None


def test_a_catalog_refuses_a_schema_whose_event_type_is_not_its_file_name(tmp_path: Path) -> None:
    schema = json.loads((SCHEMAS / "finding_detected.json").read_text(encoding="utf-8"))
    (tmp_path / "other_name.json").write_text(json.dumps(schema), encoding="utf-8")

    with pytest.raises(SchemaCatalogError, match="file name"):
        JsonSchemaCatalog(tmp_path)


def test_a_catalog_refuses_a_missing_or_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(SchemaCatalogError, match="does not exist"):
        JsonSchemaCatalog(tmp_path / "nowhere")
    with pytest.raises(SchemaCatalogError, match="no schema"):
        JsonSchemaCatalog(tmp_path)


def test_only_the_first_errors_are_generated_so_a_huge_bad_record_stays_cheap(catalog: JsonSchemaCatalog) -> None:
    item = envelope("topology_recorded")
    item["payload"]["links"] = [1] * 200_000  # every element is wrong

    started = time.monotonic()
    reasons = catalog.violations(item)

    assert time.monotonic() - started < 2
    assert len(reasons) == 6
    assert reasons[-1] == "and more"
    assert reasons[0] == "$.payload.links[*]: type"


def test_a_key_of_the_sender_never_reaches_a_reported_path(catalog: JsonSchemaCatalog) -> None:
    item = envelope("plan_created")
    item["payload"]["strategy_counts"] = {"user=alice@example.com": "not a number"}

    reasons = " ".join(catalog.violations(item))

    assert "alice" not in reasons
    assert "$.payload.strategy_counts" in reasons


def test_the_names_the_schemas_define_are_kept_in_a_path(catalog: JsonSchemaCatalog) -> None:
    item = envelope("plan_created")
    item["payload"]["strategy_counts"] = {"HYBRID_TLS_KEX": "x"}

    assert "$.payload.strategy_counts.HYBRID_TLS_KEX: type" in catalog.violations(item)


def test_a_project_key_with_a_trailing_line_break_is_refused_by_the_domain_with_the_right_reason(
    catalog: JsonSchemaCatalog,
) -> None:
    item = envelope("finding_detected", project_key="a" * 64 + "\n")

    # The schema pattern is matched with `search` and lets it pass; the classifier does not.
    assert catalog.violations(item) == []
    classified = EventClassifier(catalog).classify(0, item)
    assert classified.rejection is not None
    assert classified.rejection.message == "project_key: not 64 lower-case hexadecimal digits"


def test_a_revocation_with_a_future_consent_type_is_still_a_command(catalog: JsonSchemaCatalog) -> None:
    item = envelope("consent_revoked", payload={"consent_type": "SOMETHING_NEW", "delete_requested": False})

    classified = EventClassifier(catalog).classify(0, item)

    assert catalog.violations(item)  # it no longer matches the schema ...
    assert classified.revocation is not None  # ... and erases all the same
    assert not classified.revocation.schema_valid
