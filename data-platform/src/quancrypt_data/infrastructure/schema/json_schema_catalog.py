"""EnvelopeValidator over contracts/schemas/events/*.json (JSON Schema draft 2020-12, jsonschema)."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from itertools import islice
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

_MAX_REPORTED = 5


class SchemaCatalogError(Exception):
    """The schema directory is missing, empty or holds a schema that is not usable."""


class JsonSchemaCatalog:
    """Loads every `<event_type>.json` of the directory once, at startup. A schema whose `event_type` constant differs
    from its file name is refused: the file name is how an envelope finds its schema."""

    def __init__(self, directory: Path) -> None:
        if not directory.is_dir():
            raise SchemaCatalogError(f"the event schema directory does not exist: {directory.name}")
        self._validators: dict[str, Draft202012Validator] = {}
        # The names the schemas define (properties, and the enum values that name the keys of the count maps): the only
        # object keys that may appear in a reported path. Any other key is the sender's text and is shown as `*`.
        self._known_names: set[str] = {"payload"}
        for path in sorted(directory.glob("*.json")):
            schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise SchemaCatalogError(f"{path.name} is not a valid JSON Schema") from exc
            self._known_names.update(_names(schema))
            declared = schema.get("properties", {}).get("event_type", {}).get("const")
            if declared != path.stem:
                raise SchemaCatalogError(f"{path.name}: its event_type constant is not the file name")
            # `format: uuid` is checked; `date-time` needs an extra package: the domain checks it (parse_timestamp).
            self._validators[path.stem] = Draft202012Validator(
                schema, format_checker=Draft202012Validator.FORMAT_CHECKER
            )
        if not self._validators:
            raise SchemaCatalogError("the event schema directory holds no schema")

    @property
    def event_types(self) -> frozenset[str]:
        return frozenset(self._validators)

    def knows(self, event_type: str) -> bool:
        return event_type in self._validators

    def violations(self, item: object) -> Sequence[str]:
        event_type = item.get("event_type") if isinstance(item, dict) else None
        validator = self._validators.get(event_type) if isinstance(event_type, str) else None
        if validator is None:
            return ["event_type: no schema for this type"]
        # Only the first few errors are generated, never all of them: one record with millions of bad elements must
        # not cost
        # minutes of CPU and gigabytes (the size of a record is bounded as well, MAX_RECORD_NODES).
        errors = list(islice(validator.iter_errors(item), _MAX_REPORTED + 1))
        reasons = [self._reason(error) for error in errors[:_MAX_REPORTED]]
        if len(errors) > _MAX_REPORTED:
            reasons.append("and more")
        return reasons

    def _reason(self, error: ValidationError) -> str:
        # The path and the rule only: the library's own message quotes the offending value, and a record may carry
        # anything,
        # a key included, so only the names the schemas define are written into the path.
        path = "$"
        for segment in error.absolute_path:
            if isinstance(segment, int):
                path += "[*]"
            else:
                path += f".{segment}" if segment in self._known_names else ".*"
        return f"{path}: {error.validator}"


def _names(schema: object) -> Iterator[str]:
    """Every property name of a schema document and every enum value that restricts the keys of a map."""
    pending: list[object] = [schema]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            properties = current.get("properties")
            if isinstance(properties, dict):
                yield from (name for name in properties if isinstance(name, str))
            key_names = current.get("propertyNames")
            if isinstance(key_names, dict) and isinstance(key_names.get("enum"), list):
                yield from (value for value in key_names["enum"] if isinstance(value, str))
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
