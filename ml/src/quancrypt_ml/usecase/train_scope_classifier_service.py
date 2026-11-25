"""TrainScopeClassifier (P7.3, ml-pipeline section 4, D-332, D-333): embed the scope data set with the local embedding
model, search and fit each head on the training set, choose the threshold and the UNSURE band on the validation set,
pick the model, evaluate it once on the test set, export ONNX, log to MLflow, store the metrics in ml_outputs and write
the report and the model card."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import reduce
from pathlib import Path

from quancrypt_ml.domain.model_b_report import AlgorithmSummary, ModelBFacts, build_model_card, build_report, h4
from quancrypt_ml.domain.scope import LABELS, OUT_OF_SCOPE, ScopeRecord
from quancrypt_ml.domain.scope_model import (
    ALL,
    SLICES,
    Band,
    BinaryScore,
    Candidate,
    Scored,
    ThreeWay,
    breakdown,
    pick,
    roc_auc,
    select_threshold,
    three_way,
    unsure_band,
)
from quancrypt_ml.port.inbound.scope_model import (
    ExportScopeOnnxCommand,
    ExportScopeOnnxUseCase,
    ScopeTrainingError,
    TrainScopeCommand,
    TrainScopeResult,
)
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.risk import MetricValue, ModelRegistry, ResultSink, RunRecord, StoredModel
from quancrypt_ml.port.outbound.scope import ScopeDatasetError, ScopeDatasetFiles
from quancrypt_ml.port.outbound.scope_model import (
    EmbeddingCache,
    EmbeddingProvider,
    EmbeddingUnavailableError,
    ScopeModel,
    ScopeTrainer,
    ScoreCharts,
    Vector,
)
from quancrypt_ml.port.outbound.system import Clock

MODEL_NAME = "scope_classifier"
LABEL_SOURCE = "SCOPE_SET"
EXPERIMENT = "model_b_scope"
INNER_FOLDS = 5
EMBED_BATCH = 32
SPLITS = ("train", "val", "test")


@dataclass(frozen=True)
class ScopeTrainingPorts:
    files: ScopeDatasetFiles
    embeddings: EmbeddingProvider
    cache: EmbeddingCache
    trainer: ScopeTrainer
    export: ExportScopeOnnxUseCase
    charts: ScoreCharts
    registry: ModelRegistry
    sink: ResultSink
    reports: ReportWriter
    clock: Clock


@dataclass(frozen=True)
class _Fitted:
    summary: AlgorithmSummary
    model: ScopeModel
    validation: list[Scored]
    fold_auc: tuple[float, ...]


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scored(records: Sequence[ScopeRecord], p_out: Sequence[float]) -> list[Scored]:
    return [Scored(r.label, r.lang, r.category, p) for r, p in zip(records, p_out, strict=True)]


def _counts(records: Sequence[ScopeRecord]) -> dict[str, int]:
    labels, langs = Counter(r.label for r in records), Counter(r.lang for r in records)
    return {
        "OUT_OF_SCOPE": labels["OUT_OF_SCOPE"], "IN_SCOPE": labels["IN_SCOPE"], "tr": langs["tr"], "en": langs["en"],
        "jailbreak": sum(r.category == "jailbreak" for r in records),
    }  # fmt: skip


def _slice_metrics(scope: str, scores: Mapping[str, BinaryScore]) -> list[MetricValue]:
    values = []
    for name in SLICES:
        s = scores[name]
        if s.recall is not None:
            values.append(MetricValue(scope, 0, "OUT_OF_SCOPE_RECALL", name, s.recall))
        if s.false_reject_rate is not None:
            values.append(MetricValue(scope, 0, "FALSE_REJECT_RATE", name, s.false_reject_rate))
    return values


class TrainScopeClassifierService:
    def __init__(self, ports: ScopeTrainingPorts) -> None:
        self._p = ports

    def execute(self, command: TrainScopeCommand) -> TrainScopeResult:
        data = self._read(command)
        digest = self._digest()
        vectors = self._vectors({_key(r.text): r.text for records in data.values() for r in records}, digest)

        def matrix(split: str) -> list[Vector]:
            return [vectors[_key(r.text)] for r in data[split]]

        train, val, test = data["train"], data["val"], data["test"]
        x_train, y_train, groups = matrix("train"), [r.label for r in train], [r.seed_id for r in train]
        x_val = matrix("val")
        fitted, child_runs = [], []
        for algorithm in self._p.trainer.algorithms:
            item = self._fit(algorithm, command.seed, x_train, y_train, groups, x_val, val)
            fitted.append(item)
            child_runs.append(self._log_child(item, digest))
        candidates = [Candidate(f.summary.algorithm, f.summary.threshold, f.summary.validation) for f in fitted]
        chosen = reduce(pick, candidates)
        selected = next(f for f in fitted if f.summary.algorithm == chosen.algorithm)
        band = unsure_band(selected.validation, chosen.threshold)
        x_test = matrix("test")
        test_p = selected.model.p_out(x_test)  # the one use of the test set
        tested = _scored(test, test_p)
        parity = self._p.export.execute(ExportScopeOnnxCommand(selected.model, x_test, test_p, band, command.onnx))
        facts = ModelBFacts(
            version=command.version, embedding_model=self._p.embeddings.model_id, embedding_digest=digest,
            dimensions=self._p.embeddings.dimensions, counts={s: _counts(data[s]) for s in SPLITS},
            algorithms=[f.summary for f in fitted], selected=chosen.algorithm, band=band,
            validation=breakdown(selected.validation, band.threshold),
            validation_three_way=three_way(selected.validation, band),
            test=breakdown(tested, band.threshold), test_three_way=three_way(tested, band), test_auc=roc_auc(tested),
            parity_classes_equal=parity.classes_equal, parity_max_difference=parity.max_probability_difference,
            onnx_file=command.onnx.name, thresholds_file=command.thresholds.name,
        )  # fmt: skip
        self._p.reports.write(command.thresholds, self._thresholds(facts, command, parity.sha256))
        artifacts = self._artifacts(command, tested, band, facts)
        run_id = self._log_parent(command, facts, data, child_runs, [*artifacts, command.onnx, command.thresholds])
        self._p.sink.store([
            StoredModel(MODEL_NAME, command.version, chosen.algorithm, LABEL_SOURCE, run_id, self._p.clock.now(),
                        self._metrics(facts, selected.summary), [], True)
        ])  # fmt: skip
        self._p.reports.write(command.report, build_report(facts))
        self._p.reports.write(command.model_card, build_model_card(facts))
        test_all = facts.test[ALL]
        return TrainScopeResult(
            selected=chosen.algorithm, embedding_model=facts.embedding_model, embedding_digest=digest,
            cv_auc={f.summary.algorithm: f.summary.cv_auc_mean for f in fitted}, band=band,
            test_recall=test_all.recall or 0.0, test_false_reject_rate=test_all.false_reject_rate or 0.0,
            test_unsure_rate=facts.test_three_way.unsure_rate, h4_met=h4(facts), onnx_parity=True, stored=True,
        )  # fmt: skip

    def _read(self, command: TrainScopeCommand) -> dict[str, list[ScopeRecord]]:
        paths = {"train": command.train, "val": command.val, "test": command.test}
        data: dict[str, list[ScopeRecord]] = {}
        for split, path in paths.items():
            try:
                data[split] = self._p.files.read(path)
            except (ScopeDatasetError, OSError) as error:
                raise ScopeTrainingError(f"the {split} set cannot be read: {type(error).__name__}") from None
            labels = {r.label for r in data[split]}
            if not labels <= set(LABELS) or len(labels) != len(LABELS):
                raise ScopeTrainingError(f"the {split} set must hold both labels and no other")
        return data

    def _digest(self) -> str:
        try:
            return self._p.embeddings.digest()
        except EmbeddingUnavailableError as error:
            raise ScopeTrainingError(f"the local embedding model cannot be used: {error}") from None

    def _vectors(self, texts: Mapping[str, str], digest: str) -> dict[str, Vector]:
        model, size = self._p.embeddings.model_id, self._p.embeddings.dimensions
        cached = self._p.cache.get(model, digest, sorted(texts))
        found: dict[str, Vector] = {k: v for k, v in cached.items() if len(v) == size}
        missing = sorted(k for k in texts if k not in found)
        for start in range(0, len(missing), EMBED_BATCH):
            keys = missing[start : start + EMBED_BATCH]
            try:
                batch = self._p.embeddings.embed([texts[k] for k in keys])
            except EmbeddingUnavailableError as error:
                raise ScopeTrainingError(f"the local embedding model cannot be used: {error}") from None
            fresh = dict(zip(keys, batch, strict=True))
            self._p.cache.put(model, digest, fresh)
            found.update(fresh)
        return found

    def _fit(
        self,
        algorithm: str,
        seed: int,
        x_train: Sequence[Vector],
        y_train: Sequence[str],
        groups: Sequence[str],
        x_val: Sequence[Vector],
        val: Sequence[ScopeRecord],
    ) -> _Fitted:
        search = self._p.trainer.search(algorithm, x_train, y_train, groups, INNER_FOLDS, seed)
        model = self._p.trainer.fit(algorithm, search.params, x_train, y_train, groups, seed)
        validation = _scored(val, model.p_out(x_val))
        threshold = select_threshold(validation)
        summary = AlgorithmSummary(
            algorithm=algorithm, params=dict(search.params), cv_auc_mean=statistics.fmean(search.fold_auc),
            cv_auc_std=statistics.pstdev(search.fold_auc), threshold=threshold,
            validation=breakdown(validation, threshold)[ALL], validation_auc=roc_auc(validation),
        )  # fmt: skip
        return _Fitted(summary, model, validation, tuple(search.fold_auc))

    def _log_child(self, item: _Fitted, digest: str) -> str:
        s = item.summary
        grid = {k: ",".join(map(str, v)) for k, v in self._p.trainer.grid(s.algorithm).items()}
        metrics = {f"cv_auc_fold_{i}": v for i, v in enumerate(item.fold_auc, start=1)}
        metrics |= {"cv_auc_mean": s.cv_auc_mean, "cv_auc_std": s.cv_auc_std, "val_threshold": s.threshold,
                    "val_false_rejects": float(s.validation.false_rejects)}  # fmt: skip
        if s.validation_auc is not None:
            metrics["val_roc_auc"] = s.validation_auc
        params = {**grid, **{f"best.{k}": v for k, v in s.params.items()}}
        return self._p.registry.log_run(
            EXPERIMENT, RunRecord(f"cv-{s.algorithm}", params, metrics, {"embedding_digest": digest}, [])
        )

    def _thresholds(self, facts: ModelBFacts, command: TrainScopeCommand, onnx_sha256: str) -> str:
        document = {
            "model": f"{MODEL_NAME}-{command.version}", "onnx": command.onnx.name, "onnx_sha256": onnx_sha256,
            "positive_class": OUT_OF_SCOPE,
            "threshold": facts.band.threshold, "unsure_low": facts.band.low, "unsure_high": facts.band.high,
            "embedding_model": facts.embedding_model, "embedding_digest": facts.embedding_digest,
            "input_dimensions": facts.dimensions, "algorithm": facts.selected,
        }  # fmt: skip
        return json.dumps(document, indent=2) + "\n"

    def _artifacts(
        self, command: TrainScopeCommand, tested: Sequence[Scored], band: Band, facts: ModelBFacts
    ) -> list[Path]:
        histogram = command.artifacts_dir / "score_histogram.png"
        bounds = {"threshold": band.threshold, "unsure_low": band.low, "unsure_high": band.high}
        self._p.charts.score_histogram([s.label for s in tested], [s.p_out for s in tested], bounds, histogram)
        confusion = command.artifacts_dir / f"confusion_{facts.selected}.json"
        test = facts.test[ALL]
        t: ThreeWay = facts.test_three_way
        matrix = {
            "binary": {"OUT_OF_SCOPE": {"DENY": test.caught, "ALLOW": test.out_of_scope - test.caught},
                       "IN_SCOPE": {"DENY": test.false_rejects, "ALLOW": test.in_scope - test.false_rejects}},
            "three_way": {"OUT_OF_SCOPE": {"ALLOW": t.allowed_out, "UNSURE": t.unsure_out, "DENY": t.denied_out},
                          "IN_SCOPE": {"ALLOW": t.allowed_in, "UNSURE": t.unsure_in, "DENY": t.denied_in}},
        }  # fmt: skip
        self._p.reports.write(confusion, json.dumps(matrix, indent=2) + "\n")
        return [histogram, confusion]

    def _metrics(self, facts: ModelBFacts, summary: AlgorithmSummary) -> list[MetricValue]:
        values = [
            MetricValue("CV_MEAN", 0, "ROC_AUC", ALL, summary.cv_auc_mean),
            MetricValue("CV_STD", 0, "ROC_AUC", ALL, summary.cv_auc_std),
            MetricValue("VALIDATION", 0, "THRESHOLD", ALL, facts.band.threshold),
            MetricValue("VALIDATION", 0, "UNSURE_LOW", ALL, facts.band.low),
            MetricValue("VALIDATION", 0, "UNSURE_HIGH", ALL, facts.band.high),
            MetricValue("VALIDATION", 0, "UNSURE_RATE", ALL, facts.validation_three_way.unsure_rate),
            MetricValue("TEST", 0, "UNSURE_RATE", ALL, facts.test_three_way.unsure_rate),
        ]
        if summary.validation_auc is not None:
            values.append(MetricValue("VALIDATION", 0, "ROC_AUC", ALL, summary.validation_auc))
        if facts.test_auc is not None:
            values.append(MetricValue("TEST", 0, "ROC_AUC", ALL, facts.test_auc))
        return values + _slice_metrics("VALIDATION", facts.validation) + _slice_metrics("TEST", facts.test)

    def _log_parent(
        self,
        command: TrainScopeCommand,
        facts: ModelBFacts,
        data: Mapping[str, Sequence[ScopeRecord]],
        child_runs: Sequence[str],
        artifacts: Sequence[Path],
    ) -> str:
        snapshot = hashlib.sha256(
            "\n".join(f"{s}\t{r.id}\t{r.label}\t{_key(r.text)}" for s in SPLITS for r in data[s]).encode("utf-8")
        ).hexdigest()
        metrics: dict[str, float] = {
            "threshold": facts.band.threshold, "unsure_low": facts.band.low, "unsure_high": facts.band.high,
            "test_unsure_rate": facts.test_three_way.unsure_rate,
            "onnx_max_probability_difference": facts.parity_max_difference,
        }  # fmt: skip
        for scope, scores in (("val", facts.validation), ("test", facts.test)):
            for name in SLICES:
                s = scores[name]
                if s.recall is not None:
                    metrics[f"{scope}_{name.lower()}_out_of_scope_recall"] = s.recall
                if s.false_reject_rate is not None:
                    metrics[f"{scope}_{name.lower()}_false_reject_rate"] = s.false_reject_rate
        if facts.test_auc is not None:
            metrics["test_roc_auc"] = facts.test_auc
        selected = next(a for a in facts.algorithms if a.algorithm == facts.selected)
        params = {**{f"model.{k}": v for k, v in selected.params.items()}, "algorithm": facts.selected,
                  "seed": command.seed, "embedding_model": facts.embedding_model,
                  "embedding_dimensions": facts.dimensions}  # fmt: skip
        tags = {
            "label_source": LABEL_SOURCE, "version": command.version, "embedding_digest": facts.embedding_digest,
            "data_rows": str(sum(len(data[s]) for s in SPLITS)), "data_sha256": snapshot,
            "child_runs": ",".join(child_runs),
        }  # fmt: skip
        return self._p.registry.log_run(
            EXPERIMENT, RunRecord(f"{MODEL_NAME}-{command.version}", params, metrics, tags, list(artifacts))
        )


__all__ = ["ScopeTrainingPorts", "TrainScopeClassifierService"]
