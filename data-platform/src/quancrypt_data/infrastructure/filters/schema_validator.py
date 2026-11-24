"""SchemaValidator (P6.4, filter 1): every raw event is validated again against its schema in contracts/schemas/events.
raw holds what ingest-api accepted, but the schemas may have changed since, and prep must hold only valid events."""

from __future__ import annotations

from collections import Counter

from quancrypt_data.domain.prep import FilterResult, PrepBatch, RawEvent, Rejection
from quancrypt_data.infrastructure.schema.json_schema_catalog import JsonSchemaCatalog


def _envelope(event: RawEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "occurred_at": event.occurred_at.isoformat().replace("+00:00", "Z"),
        "project_key": event.project_key,
        "payload": dict(event.payload),
    }


class SchemaValidator:
    code = "SchemaValidator"

    def __init__(self, catalog: JsonSchemaCatalog) -> None:
        self._catalog = catalog

    def apply(self, batch: PrepBatch) -> FilterResult:
        rows_of = Counter(
            [f.source_event_id for f in batch.findings]
            + [t.source_event_id for t in batch.topologies]
            + [link.source_event_id for link in batch.links]
            + [s.event_id for s in batch.scopes]
        )
        rejected: list[Rejection] = []
        for event in batch.events:
            reasons = self._catalog.violations(_envelope(event))
            if reasons:
                # The reason names schema paths and rules only (JsonSchemaCatalog), never a value.
                rejected.append(
                    Rejection(
                        self.code, "schema-violation", reasons[0][:500], event.project_key, event.event_id,
                        rows=rows_of[event.event_id],
                    )
                )  # fmt: skip
        return FilterResult(batch.without_events(r.raw_event_id for r in rejected if r.raw_event_id), tuple(rejected))
