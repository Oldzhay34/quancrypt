"""`ml train-scope`: the facade's file layout and error translation, and the command's output and exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from quancrypt_ml.api.cli import app
from quancrypt_ml.domain.scope_model import Band
from quancrypt_ml.facade.labeling_facade import MlCommandError
from quancrypt_ml.facade.scope_model_facade import ScopeModelFacade, ScopeModelPaths
from quancrypt_ml.infrastructure import container
from quancrypt_ml.port.inbound.scope_model import ScopeTrainingError, TrainScopeCommand, TrainScopeResult

RESULT = TrainScopeResult(
    "LOGISTIC_REGRESSION", "embeddinggemma:latest", "a" * 64, {"LOGISTIC_REGRESSION": 0.97}, Band(0.2, 0.4, 0.6),
    0.983, 0.035, 0.1, True, True, True,
)  # fmt: skip


class FakeTrain:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.commands: list[TrainScopeCommand] = []

    def execute(self, command: TrainScopeCommand) -> TrainScopeResult:
        self.commands.append(command)
        if self.error:
            raise ScopeTrainingError(self.error)
        return RESULT


def _facade(tmp: Path, train: FakeTrain) -> ScopeModelFacade:
    return ScopeModelFacade(train, ScopeModelPaths(tmp / "scope", tmp / "reports", tmp / "cards", tmp / "models"))


def test_the_facade_builds_the_fixed_file_layout(tmp_path: Path) -> None:
    train = FakeTrain()
    assert _facade(tmp_path, train).train("v2", 7) == RESULT
    command = train.commands[0]
    assert (command.version, command.seed) == ("v2", 7)
    assert [command.train, command.val, command.test] == [
        tmp_path / "scope" / n for n in ("train.jsonl", "val.jsonl", "test.jsonl")
    ]
    assert command.report == tmp_path / "reports" / "model_b.md"
    assert command.model_card == tmp_path / "cards" / "scope_classifier-v2.md"
    assert command.onnx == tmp_path / "models" / "scope_classifier-v2.onnx"
    assert command.thresholds == tmp_path / "models" / "scope_classifier-v2.thresholds.json"
    assert command.artifacts_dir == tmp_path / "reports" / "model_b_artifacts"


def test_the_facade_turns_a_training_error_into_a_command_error(tmp_path: Path) -> None:
    with pytest.raises(MlCommandError, match="parity"):
        _facade(tmp_path, FakeTrain("parity failed")).train("v1", 42)


def test_the_command_prints_the_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container, "scope_model", lambda: _facade(tmp_path, FakeTrain()))
    result = CliRunner().invoke(app, ["train-scope"])
    assert result.exit_code == 0, result.output
    assert "selected LOGISTIC_REGRESSION: threshold 0.4000, UNSURE [0.2000, 0.6000)" in result.output
    assert "out-of-scope recall 98.3 %" in result.output and "H4: met" in result.output


def test_the_command_exits_with_1_on_a_training_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container, "scope_model", lambda: _facade(tmp_path, FakeTrain("the val set is missing")))
    result = CliRunner().invoke(app, ["train-scope"])
    assert result.exit_code == 1 and "the val set is missing" in result.output


def test_the_command_exits_with_2_without_its_configuration() -> None:
    result = CliRunner().invoke(app, ["train-scope"], env={"WAREHOUSE_DB_URL": "", "WAREHOUSE_DB_APP_PASSWORD": ""})
    assert result.exit_code == 2 and "WAREHOUSE_DB_URL" in result.output
