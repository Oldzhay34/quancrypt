"""`SchemaStore` resolves contract references from local files under the contracts directory only: never from the
network and never from outside the directory (guardrails-security section 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from referencing.exceptions import Unresolvable

from src.tools.base_tool import SchemaStore, ToolError


def contracts(tmp_path: Path, ref: str) -> SchemaStore:
    root = tmp_path / "contracts"
    (root / "schemas" / "tools").mkdir(parents=True)
    (root / "schemas" / "shared.schema.json").write_text(json.dumps({"type": "string"}), "utf-8")
    # A readable schema outside the contracts directory: it must not be reachable either.
    (tmp_path / "outside.schema.json").write_text(json.dumps({"type": "integer"}), "utf-8")
    contract = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": {"input": {"$ref": ref}, "output": {"type": "object"}},
    }
    (root / "schemas" / "tools" / "probe.json").write_text(json.dumps(contract), "utf-8")
    return SchemaStore(root)


def test_a_relative_reference_inside_the_directory_and_a_project_schema_id_resolve(tmp_path: Path) -> None:
    for ref in ("../shared.schema.json", "https://quancrypt.local/schemas/shared.schema.json"):
        store = contracts(tmp_path / ref.replace("/", "_").replace(":", "_"), ref)
        store.check_contract("probe")
        assert store.validate("probe", "input", "text") == []
        assert store.validate("probe", "input", 3) == ["(root): type failed"]


@pytest.mark.parametrize(
    "ref",
    [
        "http://127.0.0.1:9/shared.schema.json",
        "https://example.org/shared.schema.json",
        "../../../outside.schema.json",
        "https://quancrypt.local/schemas/../../outside.schema.json",
        "ftp://example.org/x.json",
    ],
    ids=["http", "https-elsewhere", "relative-escape", "own-id-escape", "ftp"],
)
def test_a_reference_to_the_network_or_outside_the_directory_does_not_resolve(tmp_path: Path, ref: str) -> None:
    store = contracts(tmp_path, ref)

    with pytest.raises(Unresolvable):
        store.check_contract("probe")


def test_a_tool_name_cannot_name_a_path(tmp_path: Path) -> None:
    store = contracts(tmp_path, "../shared.schema.json")
    for name in ("../probe", "Probe", "probe.json", "pro be"):
        with pytest.raises(ToolError):
            store.document(name)


def test_a_directory_without_tool_contracts_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        SchemaStore(tmp_path)
