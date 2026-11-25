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


@app.command("train-risk")
def train_risk(
    labels: str = typer.Option(
        "gold", help="gold (the real run) or silver (a dry run while the gold labels are written)"
    ),
    version: str = typer.Option("v1"),
    llm: bool = typer.Option(True, "--llm/--no-llm", help="Compare with the local LLM's zero-shot classification"),
    seed: int = typer.Option(42),
) -> None:
    """Train Model A (risk), compare it with the rule baseline and the local LLM, export ONNX and write the report."""
    if labels.lower() not in ("gold", "silver"):
        _fail("--labels is gold or silver", 2)
    try:
        result = container.risk().train(labels, version, llm, seed)
    except container.ConfigError as error:
        _fail(str(error), 2)
        return
    except MlCommandError as error:
        _fail(str(error))
        return
    typer.echo(
        f"{result.label_source}: train {result.train_rows} findings, test {result.test_rows} findings in "
        f"{result.test_projects} unseen projects"
    )
    for name, value in result.cv_macro_f1.items():
        typer.echo(f"  CV macro-F1 {name}: {value:.3f}")
    llm_text = "-" if result.llm_macro_f1 is None else f"{result.llm_macro_f1:.3f}"
    typer.echo(
        f"selected {result.selected}: test macro-F1 {result.test_macro_f1:.3f}; rule {result.rule_macro_f1:.3f}; "
        f"LLM {llm_text}; ONNX parity {'ok' if result.onnx_parity else 'FAILED'}"
    )
    h3 = "not judged (dry run)" if result.h3_met is None else ("met" if result.h3_met else "NOT met")
    typer.echo(f"H3: {h3}; ml_outputs {'written' if result.stored else 'not written'}")
    if result.erased_skipped:
        typer.echo(f"{result.erased_skipped} predictions not written: their finding was erased (KVKK) during training")


@app.command("train-scope")
def train_scope(version: str = typer.Option("v1"), seed: int = typer.Option(42)) -> None:
    """Train Model B (scope): embed locally, choose the threshold and band on val, test once, export ONNX."""
    try:
        result = container.scope_model().train(version, seed)
    except container.ConfigError as error:
        _fail(str(error), 2)
        return
    except MlCommandError as error:
        _fail(str(error))
        return
    typer.echo(f"embedding {result.embedding_model} ({result.embedding_digest[:12]})")
    for name, value in result.cv_auc.items():
        typer.echo(f"  inner-CV ROC AUC {name}: {value:.3f}")
    band = result.band
    typer.echo(
        f"selected {result.selected}: threshold {band.threshold:.4f}, UNSURE [{band.low:.4f}, {band.high:.4f}); "
        f"test out-of-scope recall {100 * result.test_recall:.1f} %, false rejects "
        f"{100 * result.test_false_reject_rate:.1f} %, UNSURE {100 * result.test_unsure_rate:.1f} %"
    )
    typer.echo(f"H4: {'met' if result.h4_met else 'NOT met'}; ONNX parity {'ok' if result.onnx_parity else 'FAILED'}")


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
