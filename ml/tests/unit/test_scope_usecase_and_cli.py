"""SplitScopeDataset over real files in a temporary directory, and the exit codes of the command line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quancrypt_ml.api.cli import app
from quancrypt_ml.domain.scope import IN_SCOPE, OUT_OF_SCOPE
from quancrypt_ml.infrastructure.files.text_files import JsonlScopeDatasetFiles
from quancrypt_ml.port.inbound.scope import ScopeSplitError, SplitCommand
from quancrypt_ml.usecase.split_scope_dataset_service import SplitScopeDatasetService


def _write(path: Path, groups: int) -> None:
    lines = []
    for label in (IN_SCOPE, OUT_OF_SCOPE):
        for g in range(groups):
            for i, lang in enumerate(("tr", "tr", "en", "en")):
                lines.append(json.dumps({
                    "id": f"{label}-{g}-{i}", "seed_id": f"{label}-{g}", "lang": lang, "text": f"{label} {g} {i}",
                    "label": label, "category": "boundary" if g == 0 else "c", "source": "synthetic_reviewed",
                }))  # fmt: skip
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_the_split_writes_three_splits_the_review_sample_and_the_agent_copy(tmp_path: Path) -> None:
    dataset = tmp_path / "scope_dataset.jsonl"
    _write(dataset, 101)
    copy = tmp_path / "agent" / "scope_set.jsonl"
    result = SplitScopeDatasetService(JsonlScopeDatasetFiles()).execute(SplitCommand(dataset, tmp_path, copy, 42))
    assert result.records == 808 and result.groups == 202
    assert sum(sum(c.values()) for c in result.counts.values()) == 808
    assert copy.read_text(encoding="utf-8") == (tmp_path / "test.jsonl").read_text(encoding="utf-8")
    review = JsonlScopeDatasetFiles().read(tmp_path / "review_sample.jsonl")
    assert sum(r.category == "boundary" for r in review) == 8


def test_an_invalid_data_set_is_refused_with_its_problems(tmp_path: Path) -> None:
    dataset = tmp_path / "scope_dataset.jsonl"
    _write(dataset, 3)
    with pytest.raises(ScopeSplitError) as error:
        SplitScopeDatasetService(JsonlScopeDatasetFiles()).execute(SplitCommand(dataset, tmp_path, tmp_path / "c", 42))
    assert "24 records, at least 800 are needed" in error.value.problems
    (tmp_path / "broken.jsonl").write_text("{", encoding="utf-8")
    with pytest.raises(ScopeSplitError, match="line 1 is not JSON"):
        SplitScopeDatasetService(JsonlScopeDatasetFiles()).execute(
            SplitCommand(tmp_path / "broken.jsonl", tmp_path, tmp_path / "c", 42)
        )


def test_a_command_without_its_configuration_exits_with_2_and_names_keys_only(tmp_path: Path) -> None:
    csv = tmp_path / "x.csv"
    csv.write_text("finding_id,label,labeler,notes\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        app, ["label-import", str(csv)], env={"WAREHOUSE_DB_URL": "", "WAREHOUSE_DB_APP_PASSWORD": ""}
    )
    assert result.exit_code == 2
    assert "WAREHOUSE_DB_URL" in result.output
    result = runner.invoke(app, ["label-export"], env={"WAREHOUSE_DB_URL": "", "WAREHOUSE_DB_APP_PASSWORD": ""})
    assert result.exit_code == 2
    result = runner.invoke(
        app, ["migrate"], env={"WAREHOUSE_DB_MIGRATOR_URL": "", "WAREHOUSE_DB_MIGRATOR_PASSWORD": ""}
    )
    assert result.exit_code == 2 and "WAREHOUSE_DB_MIGRATOR_URL" in result.output
