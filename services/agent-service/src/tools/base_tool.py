"""The tool contract (P4.3): what every tool is, how a call is described and how its input and output are validated.

Every tool has a JSON Schema contract in `contracts/schemas/tools/<name>.json` with `$defs.input` and `$defs.output`.
The contracts may point (`$ref`) into the service OpenAPI documents so that a tool never drifts from the endpoint it
wraps (D-17); references are resolved from local files under the contracts directory only, never from the network.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import unquote, urlparse

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource
from referencing.jsonschema import DRAFT202012

from src.memory.short_term import ToolCallStatus, ToolCode

__all__ = ["ToolCallStatus", "ToolCode"]


class ToolError(Exception):
    """Base class of every tool failure. Messages carry no argument values, bodies or secrets."""

    code = "tool-error"


class ToolNotAllowedError(ToolError):
    """The agent's allow-list (agent_config.yaml) does not contain the tool, or no such tool exists."""

    code = "tool-not-allowed"


class ToolInputError(ToolError):
    """The arguments do not fit the tool's input schema."""

    code = "invalid-input"


class ToolOutputError(ToolError):
    """The tool produced an output that does not fit its output schema (a contract drift; never passed on)."""

    code = "invalid-output"


class ToolUnavailableError(ToolError):
    """The service behind the tool cannot be reached, timed out or keeps failing (circuit open)."""

    code = "unavailable"

    def __init__(self, message: str, *, timed_out: bool = False) -> None:
        super().__init__(message)
        self.timed_out = timed_out


class ToolRejectedError(ToolError):
    """The service answered with a client error (4xx); `status` and the problem `type` code are kept, the body is
    not."""

    code = "rejected"

    def __init__(self, status: int, problem_code: str | None) -> None:
        super().__init__(f"the service rejected the request (HTTP {status}, {problem_code or 'no problem code'})")
        self.status = status
        self.problem_code = problem_code


@dataclass(frozen=True)
class ToolContext:
    """Per-call context. `call_id` is also the `Idempotency-Key` of commands sent to core-service."""

    trace_id: str
    call_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass(frozen=True)
class ToolCall:
    """One requested call as an agent plans it (name, arguments, context); the agents of P4.5 build these and hand their
    parts to `AgentToolbox.invoke`."""

    name: str
    arguments: Mapping[str, Any]
    context: ToolContext


@dataclass(frozen=True)
class ToolResult:
    call_id: uuid.UUID
    name: str
    tool_code: ToolCode
    status: ToolCallStatus
    duration_ms: int
    output: Mapping[str, Any] | None = None
    error_code: str | None = None


class Tool(Protocol):
    """One operation an agent may call. `invoke` receives validated arguments and returns a JSON-like dict."""

    @property
    def name(self) -> str: ...

    @property
    def tool_code(self) -> ToolCode: ...

    @property
    def input_schema(self) -> Mapping[str, Any]: ...

    @property
    def output_schema(self) -> Mapping[str, Any]: ...

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Mapping[str, Any]: ...


# ---- schemas ----


class SchemaStore:
    """Loads tool contracts from the contracts directory and validates against them (Draft 2020-12)."""

    def __init__(self, contracts_dir: Path) -> None:
        self._root = contracts_dir.resolve()
        if not (self._root / "schemas" / "tools").is_dir():
            raise ToolError(f"no tool contracts under {self._root.name}/schemas/tools")
        self._registry: Registry[Any] = Registry(retrieve=self._retrieve)  # type: ignore[call-arg]
        self._validators: dict[tuple[str, str], Draft202012Validator] = {}
        self._documents: dict[Path, Any] = {}

    @property
    def root(self) -> Path:
        return self._root

    def document(self, tool_name: str) -> Mapping[str, Any]:
        path = self._tool_path(tool_name)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ToolError(f"the contract of {tool_name} is not an object")
        return loaded

    def part(self, tool_name: str, part: Literal["input", "output"]) -> Mapping[str, Any]:
        """A schema that points at `$defs.input` or `$defs.output` of the tool's contract."""
        return {"$ref": f"{self._tool_path(tool_name).as_uri()}#/$defs/{part}"}

    def validate(self, tool_name: str, part: Literal["input", "output"], instance: Any) -> list[str]:
        """Return the violations as `path: reason` strings (no values); an empty list means valid."""
        key = (tool_name, part)
        validator = self._validators.get(key)
        if validator is None:
            validator = Draft202012Validator(
                self.part(tool_name, part), registry=self._registry, format_checker=Draft202012Validator.FORMAT_CHECKER
            )
            self._validators[key] = validator
        return sorted(_describe(error) for error in validator.iter_errors(instance))

    def check_contract(self, tool_name: str) -> None:
        """The contract is a valid Draft 2020-12 document with an input and an output part, and every reference
        resolves."""
        document = self.document(tool_name)
        Draft202012Validator.check_schema(document)
        defs = document.get("$defs", {})
        if "input" not in defs or "output" not in defs:
            raise ToolError(f"the contract of {tool_name} needs $defs.input and $defs.output")
        # Every reference reachable from the contract is resolved once (transitively, through the OpenAPI documents it
        # points into): a contract with an unresolvable or off-limits $ref fails here, not at the first call.
        resolver = self._registry.resolver(base_uri=self._tool_path(tool_name).as_uri())
        self._resolve_all(document, resolver, set())

    def _resolve_all(self, node: Any, resolver: Any, seen: set[str]) -> None:
        if isinstance(node, Mapping):
            ref = node.get("$ref")
            if isinstance(ref, str):
                resolved = resolver.lookup(ref)
                key = f"{resolved.resolver._base_uri}#{ref.partition('#')[2]}"
                if key not in seen:
                    seen.add(key)
                    self._resolve_all(resolved.contents, resolved.resolver, seen)
            for key_name, value in node.items():
                if key_name != "$ref":
                    self._resolve_all(value, resolver, seen)
        elif isinstance(node, list):
            for value in node:
                self._resolve_all(value, resolver, seen)

    def _tool_path(self, tool_name: str) -> Path:
        if not tool_name.replace("_", "").isalnum() or not tool_name.islower():
            raise ToolError("a tool name is lowercase letters, digits and underscores")
        return self._root / "schemas" / "tools" / f"{tool_name}.json"

    def _retrieve(self, uri: str) -> Resource[Any]:
        """Local files under the contracts directory only. The project's own schema ids
        (`https://quancrypt.local/schemas/...`) name files under `schemas/`; nothing is fetched from the network."""
        if uri.startswith(_OWN_SCHEMA_IDS):
            path = (self._root / "schemas" / uri.removeprefix(_OWN_SCHEMA_IDS)).resolve()
        else:
            parsed = urlparse(uri)
            if parsed.scheme != "file":
                raise NoSuchResource(uri)
            raw = parsed.path.lstrip("/") if _is_windows_drive(parsed.path) else parsed.path
            path = Path(unquote(raw)).resolve()
        if not path.is_relative_to(self._root) or not path.is_file():
            raise NoSuchResource(uri)
        # The registry is immutable, so a lookup does not keep what it retrieved: the parsed files are cached here
        # (the OpenAPI documents are large and every validation would parse them again).
        cached = self._documents.get(path)
        if cached is None:
            text = path.read_text(encoding="utf-8")
            cached = yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else json.loads(text)
            self._documents[path] = cached
        return Resource.from_contents(cached, default_specification=DRAFT202012)


_OWN_SCHEMA_IDS = "https://quancrypt.local/schemas/"


def _is_windows_drive(path: str) -> bool:
    return len(path) > 2 and path[0] == "/" and path[2] == ":"


def _describe(error: ValidationError) -> str:
    location = "/".join(str(part) for part in error.absolute_path) or "(root)"
    return f"{location}: {error.validator} failed"


def elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))
