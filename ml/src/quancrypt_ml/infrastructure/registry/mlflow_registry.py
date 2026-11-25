"""ModelRegistry over MLflow (P7.2, ml-pipeline section 6): one run per training step, child runs tagged with their
parent.

Telemetry is switched off before MLflow is imported (the variables read in mlflow/telemetry/utils.py of 3.16.1, D-323j);
the tracking server is the local `mlflow` service (127.0.0.1:5000) or, in tests, a file store."""

from __future__ import annotations

import os

os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
os.environ["DO_NOT_TRACK"] = "true"

from mlflow.tracking import MlflowClient  # noqa: E402 (after the telemetry switch)

from quancrypt_ml.port.outbound.risk import RunRecord  # noqa: E402

_MAX_PARAM = 500  # MLflow's parameter value limit


class MlflowModelRegistry:
    def __init__(self, tracking_uri: str) -> None:
        self._client = MlflowClient(tracking_uri=tracking_uri)

    def _experiment(self, name: str) -> str:
        found = self._client.get_experiment_by_name(name)
        return found.experiment_id if found is not None else self._client.create_experiment(name)

    def log_run(self, experiment: str, record: RunRecord, parent_run_id: str | None = None) -> str:
        tags = dict(record.tags)
        if parent_run_id is not None:
            tags["mlflow.parentRunId"] = parent_run_id
        run = self._client.create_run(self._experiment(experiment), run_name=record.name, tags=tags)
        run_id = run.info.run_id
        try:
            for key, value in sorted(record.params.items()):
                self._client.log_param(run_id, key, str(value)[:_MAX_PARAM])
            for key, number in sorted(record.metrics.items()):
                self._client.log_metric(run_id, key, float(number))
            for path in record.artifacts:
                if path.is_file():
                    self._client.log_artifact(run_id, str(path))
        except BaseException:
            self._client.set_terminated(run_id, status="FAILED")
            raise
        self._client.set_terminated(run_id, status="FINISHED")
        return str(run_id)
