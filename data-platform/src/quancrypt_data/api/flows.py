"""Prefect flows of the corpus tooling (D-22, P6.2): the local, ephemeral mode (no Prefect server container). A flow
only
calls the facade, step after step; the work and its rules are in the use cases.

Prefect would send anonymous usage data on its own: both switches are set off here, before Prefect is imported (the
setting names were read from the installed 3.8.7 and are listed in docs/ports.md)."""

from __future__ import annotations

import os

# Assigned, not defaulted: an environment or `.env` that says otherwise must not switch telemetry back on. The flow
# also runs
# only against Prefect's own temporary local server: an API address (a profile or the environment) is refused below.
os.environ["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"
os.environ["PREFECT_CLOUD_ENABLE_ORCHESTRATION_TELEMETRY"] = "false"
os.environ["PREFECT_TELEMETRY_ENABLE_RESOURCE_METRICS"] = "false"
os.environ["DO_NOT_TRACK"] = "1"
os.environ["PREFECT_API_URL"] = ""
# The log lines go to the terminal; shipping them to the temporary local server as well only adds load.
os.environ["PREFECT_LOGGING_TO_API_ENABLED"] = "false"

from collections.abc import Callable  # noqa: E402

from prefect import flow, task  # noqa: E402
from prefect.cache_policies import NO_CACHE  # noqa: E402
from prefect.settings import get_current_settings  # noqa: E402

from quancrypt_data.facade.corpus_facade import StepView  # noqa: E402
from quancrypt_data.infrastructure.corpus_container import CorpusContainer, bootstrap  # noqa: E402


def _require_local_mode() -> None:
    if get_current_settings().api.url:
        raise RuntimeError(
            "Prefect points at an API server: the corpus flows run in local mode only (nothing leaves the machine)"
        )


@task(name="step", cache_policy=NO_CACHE)
def _step(name: str, action: Callable[[], StepView]) -> StepView:
    view = action()
    print(f"{name}: " + ", ".join(f"{key}={value}" for key, value in view.counts.items()))
    for note in view.notes:
        print(f"  {note}")
    return view


def _run(
    container: CorpusContainer, dataset: str | None, size: int, offset: int, limit: int, max_disk_gb: float
) -> None:
    facade = container.facade
    if dataset:
        resolved = container.resolve_dataset(dataset)
        _step("list", lambda: facade.build_list(resolved, size))
    _step("clone", lambda: facade.clone(offset, limit, max_disk_gb))
    _step("analyze", lambda: facade.analyze(offset, limit))
    _step("report", facade.report)


@flow(name="corpus_flow", log_prints=True)
def corpus_flow(
    dataset: str | None = None, size: int = 100, offset: int = 0, limit: int = 25, max_disk_gb: float = 10.0
) -> None:
    """list (when a dataset is given) -> clone -> analyse -> ingest -> report, for the window `offset`..`offset +
    limit`."""
    _require_local_mode()
    container = bootstrap(configure_logs=False)
    try:
        _run(container, dataset, size, offset, limit, max_disk_gb)
    finally:
        container.close()


@flow(name="benchmark_flow", log_prints=True)
def benchmark_flow(benchmark: str, source: str) -> None:
    """Loads the labels of a benchmark and sends the analysis of its code to ingest-api."""
    _require_local_mode()
    container = bootstrap(need_database=True, configure_logs=False)
    try:
        _step("benchmark", lambda: container.facade.load_benchmark(benchmark, source))
    finally:
        container.close()
