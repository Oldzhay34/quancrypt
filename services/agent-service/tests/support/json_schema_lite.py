"""A small JSON Schema keyword checker for the event contract tests (no new dependency; core-service D-158 precedent).

It supports only what `contracts/schemas/events/*.json` use: type, const, enum, required, properties,
additionalProperties (false), minimum, maximum, pattern, format (uuid, date-time), allOf and if/then. An unknown keyword
raises, so the checker can never pass a schema it does not understand.
"""

from __future__ import annotations

import re
from typing import Any

_KNOWN = {
    "$schema", "$id", "title", "description", "type", "const", "enum", "required", "properties",
    "additionalProperties", "minimum", "maximum", "pattern", "format", "allOf", "if", "then",
}  # fmt: skip
_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "null": (type(None),),
    "boolean": (bool,),
}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def validate(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Return the violations (an empty list means the instance fits the schema)."""
    unknown = set(schema) - _KNOWN
    if unknown:
        raise ValueError(f"{path}: unsupported schema keywords {sorted(unknown)}")
    errors: list[str] = []
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, name) for name in names):
            return [f"{path}: expected {names}, got {type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in {schema['enum']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above {schema['maximum']}")
    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match {schema['pattern']}")
        if schema.get("format") == "uuid" and not _UUID.match(instance):
            errors.append(f"{path}: not a uuid")
        if schema.get("format") == "date-time" and not _DATE_TIME.match(instance):
            errors.append(f"{path}: not a date-time")
    if isinstance(instance, dict):
        errors += [f"{path}.{name}: missing" for name in schema.get("required", []) if name not in instance]
        properties = schema.get("properties", {})
        for name, value in instance.items():
            if name in properties:
                errors += validate(value, properties[name], f"{path}.{name}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{name}: not allowed")
    for sub in schema.get("allOf", []):
        errors += validate(instance, sub, path)
    if "if" in schema and not validate(instance, schema["if"], path):
        errors += validate(instance, schema.get("then", {}), path)
    return errors


def _is_type(instance: Any, name: str) -> bool:
    if isinstance(instance, bool) and name != "boolean":
        return False
    return isinstance(instance, _TYPES[name])
