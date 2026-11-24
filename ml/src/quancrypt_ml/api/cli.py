"""The `ml` command line (Typer, ml-pipeline section 1). It runs on the host (docker-local section 2) with the variables
of the user's .env (`make ml ARGS="..."`); it never reads .env itself. Exit codes: 0 done, 1 the command could not run
or the file has problems, 2 the configuration is invalid."""

from __future__ import annotations

from pathlib import Path

import typer

from quancrypt_ml.facade.labeling_facade import MlCommandError
from quancrypt_ml.infrastructure import container

app = typer.Typer(no_args_is_help=True, help="Quancrypt ML: labelling and the scope data set (P7.1)")

_BATCH = typer.Option("batch_001", help="Batch name (lower-case letters, digits and _)")
_LABEL_FILE = typer.Argument(..., exists=True, dir_okay=False, readable=True)
_RESOLUTION_FILE = typer.Argument(
    None, help="The filled-in disagreement CSV (default ml/labeling/<batch>_disagreements.csv)"
)


def _fail(message: str, code: int = 1) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code)


@app.command("migrate")
def migrate() -> None:
    """Create or upgrade the labels schema of warehouse_db (warehouse_db_migrator)."""
    try:
        container.migrate()
    except container.ConfigError as error:
        _fail(str(error), 2)
    typer.echo("labels schema is up to date")


@app.command("label-export")
def label_export(
    batch: str = _BATCH,
    size: int = typer.Option(300, min=1, max=5000),
    double: int = typer.Option(60, min=0, max=5000),
    seed: int = typer.Option(42),
) -> None:
    """Draw a stratified sample of the warehouse findings and write ml/labeling/<batch>.csv."""
    try:
        result = container.labeling(with_analyzer=True).export_batch(batch, size, double, seed)
    except container.ConfigError as error:
        _fail(str(error), 2)
        return
    except MlCommandError as error:
        _fail(str(error))
        return
    typer.echo(
        f"{result.batch}: {result.sampled} of {result.candidates} findings ({result.double} double-labelled); context "
        f"{result.with_context}, no location {result.without_location}, unavailable {result.context_unavailable}"
    )
    typer.echo(f"written: {result.output}")


@app.command("label-import")
def label_import(
    file: Path = _LABEL_FILE,
    batch: str = _BATCH,
    labeler: str = typer.Option("FIRST", help="FIRST (the whole batch) or SECOND (the double-label records)"),
) -> None:
    """Check a filled-in batch CSV and store the labels; rebuilds ml/reports/labeling.md."""
    try:
        result = container.labeling(with_analyzer=False).import_labels(batch, labeler.upper(), file)
    except container.ConfigError as error:
        _fail(str(error), 2)
        return
    except MlCommandError as error:
        _fail(str(error))
        return
    if result.issues:
        for issue in result.issues[:50]:
            typer.echo(f"row {issue.row}: {issue.reason}" if issue.row else issue.reason, err=True)
        _fail(f"{len(result.issues)} problems; nothing was stored")
    typer.echo(f"{result.batch} {result.labeler_role}: {result.stored} labels stored")
    if result.kappa is not None:
        typer.echo(f"Cohen kappa {result.kappa:.4f} over {result.pairs} records; {result.disagreements} disagreements")


@app.command("label-resolve")
def label_resolve(
    file: Path | None = _RESOLUTION_FILE,
    batch: str = _BATCH,
) -> None:
    """Store the resolutions of the disagreements; rebuilds ml/reports/labeling.md."""
    try:
        result = container.labeling(with_analyzer=False).resolve(batch, file)
    except container.ConfigError as error:
        _fail(str(error), 2)
        return
    except MlCommandError as error:
        _fail(str(error))
        return
    if result.issues:
        for issue in result.issues[:50]:
            typer.echo(f"row {issue.row}: {issue.reason}", err=True)
        _fail(f"{len(result.issues)} problems; nothing was stored")
    typer.echo(f"{result.batch}: {result.stored} resolutions stored, {result.open_disagreements} still open")


@app.command("scope-split")
def scope_split(seed: int = typer.Option(42)) -> None:
    """Check ml/data/scope/scope_dataset.jsonl, split it by paraphrase group (70/15/15) and copy the test split to
    agent-service."""
    folders = container.paths()
    try:
        result = container.scope().split(
            folders.scope_dir / "scope_dataset.jsonl", folders.scope_dir, folders.agent_scope_set, seed
        )
    except MlCommandError as error:
        _fail(str(error))
        return
    typer.echo(f"{result.records} records in {result.groups} paraphrase groups; review sample {result.review_sample}")
    for name, counts in result.counts.items():
        typer.echo(f"  {name}: " + ", ".join(f"{label} {count}" for label, count in sorted(counts.items())))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
