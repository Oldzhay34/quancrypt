"""`quancrypt-data`: the command line of the corpus tooling (P6.2). It runs on the developer machine (host), reads its
configuration from the environment (see README) and calls the facade; `corpus run` and `benchmarks load` run the
Prefect flows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import typer

from quancrypt_data.facade.corpus_facade import StepView
from quancrypt_data.infrastructure.corpus_container import bootstrap

app = typer.Typer(
    name="quancrypt-data", no_args_is_help=True, add_completion=False, help="Quancrypt data platform tools"
)
corpus = typer.Typer(no_args_is_help=True, help="The open-source corpus: list, clone, analyse, report")
benchmarks = typer.Typer(no_args_is_help=True, help="Benchmark labels and benchmark code")
app.add_typer(corpus, name="corpus")
app.add_typer(benchmarks, name="benchmarks")

Offset = Annotated[int, typer.Option(min=0, help="First project of the window (position in the corpus list)")]
Limit = Annotated[int, typer.Option(min=1, max=1000, help="Number of projects of the window")]
DiskGb = Annotated[float, typer.Option(min=0.1, help="The run stops when the corpus root reaches this size (GB)")]


def _show(view: StepView) -> None:
    for key, value in view.counts.items():
        typer.echo(f"{key}: {value}")
    for note in view.notes:
        typer.echo(note)


def _guarded(action: Callable[[], None]) -> None:
    """Runs a command; an error ends it with a short message and a non-zero exit code. Messages of this package never
    carry data of the analysed projects, so they may be shown; any other error shows its class only."""
    try:
        action()
    except Exception as exc:
        known = type(exc).__module__.startswith("quancrypt_data")
        typer.echo(f"error: {type(exc).__name__}" + (f": {exc}" if known else ""), err=True)
        raise typer.Exit(1) from None


@corpus.command("list")
def corpus_list(
    dataset: Annotated[str, typer.Option(help="The MSR dataset file (relative paths are read below DATASETS_ROOT)")],
    size: Annotated[int, typer.Option(min=1, max=1000, help="Number of projects to list")] = 100,
) -> None:
    """Build reference/corpus_projects.csv from the dataset (seed 42: a longer list starts with the shorter one)."""

    def action() -> None:
        container = bootstrap()
        try:
            _show(container.facade.build_list(container.resolve_dataset(dataset), size))
        finally:
            container.close()

    _guarded(action)


@corpus.command("clone")
def corpus_clone(offset: Offset = 0, limit: Limit = 25, max_disk_gb: DiskGb = 10.0) -> None:
    """Shallow-clone a window of the list and keep the projects that pass the license, Spring Boot and services
    checks."""

    def action() -> None:
        container = bootstrap()
        try:
            _show(container.facade.clone(offset, limit, max_disk_gb))
        finally:
            container.close()

    _guarded(action)


@corpus.command("analyze")
def corpus_analyze(offset: Offset = 0, limit: Limit = 25) -> None:
    """Analyse the cloned projects of a window and send the results to ingest-api."""

    def action() -> None:
        container = bootstrap()
        try:
            _show(container.facade.analyze(offset, limit))
        finally:
            container.close()

    _guarded(action)


@corpus.command("report")
def corpus_report() -> None:
    """Write reports/corpus_run.md from the manifest."""

    def action() -> None:
        container = bootstrap()
        try:
            _show(container.facade.report())
        finally:
            container.close()

    _guarded(action)


@corpus.command("run")
def corpus_run(
    dataset: Annotated[str | None, typer.Option(help="Build the list from this dataset first")] = None,
    size: Annotated[int, typer.Option(min=1, max=1000)] = 100,
    offset: Offset = 0,
    limit: Limit = 25,
    max_disk_gb: DiskGb = 10.0,
) -> None:
    """The corpus flow (Prefect, local mode): list (when --dataset is given), clone, analyse, ingest and report a
    window."""

    def action() -> None:
        from quancrypt_data.api.flows import corpus_flow  # Prefect is slow to import: only this command needs it

        corpus_flow(dataset=dataset, size=size, offset=offset, limit=limit, max_disk_gb=max_disk_gb)

    _guarded(action)


@benchmarks.command("load")
def benchmarks_load(
    benchmark: Annotated[str, typer.Argument(help="Benchmark code, e.g. cryptoapi-bench or owasp-benchmark")],
    source: Annotated[str, typer.Argument(help="Directory of the downloaded benchmark")],
) -> None:
    """Load the labels of a benchmark into raw.benchmark_label and send the analysis of its code (the benchmark
    flow)."""

    def action() -> None:
        from quancrypt_data.api.flows import benchmark_flow

        benchmark_flow(benchmark=benchmark, source=source)

    _guarded(action)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
