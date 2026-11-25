"""TrainRiskModel (P7.2, ml-pipeline sections 2-6, D-327): split by project, cross-validate the three algorithms,
select, fit, evaluate on unseen projects against the rule baseline and the local LLM, explain with SHAP, export to ONNX,
log to MLflow, store the gold run in ml_outputs and write the report and the model card."""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.metrics import (
    CRITICAL,
    Evaluation,
    agreement,
    bootstrap_interval,
    critical_recall,
    evaluate,
    macro_f1,
)
from quancrypt_ml.domain.model_a_report import (
    ClassifierCost,
    CvSummary,
    ModelAFacts,
    build_model_card,
    build_report,
    h3,
)
from quancrypt_ml.domain.risk_features import GOLD, LABEL_SOURCES, RiskRow, risk_score
from quancrypt_ml.domain.split import CandidateScore, best_candidate, leaked_projects, partition
from quancrypt_ml.port.inbound.risk import (
    ExportOnnxCommand,
    ExportOnnxUseCase,
    RiskTrainingError,
    TrainRiskCommand,
    TrainRiskResult,
)
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.risk import (
    Attribution,
    Charts,
    Explainer,
    MetricValue,
    ModelRegistry,
    ModelTrainer,
    Prediction,
    ProjectSplitter,
    ResultSink,
    RunRecord,
    StoredModel,
    TrainedModel,
    TrainingDataSource,
    ZeroShotClassifier,
    ZeroShotUnavailableError,
)
from quancrypt_ml.port.outbound.system import Clock

MODEL_NAME = "risk_model"
RULE_NAME, RULE_VERSION = "rule_baseline", "v1"
LLM_NAME = "llm_zero_shot"
EXPERIMENT = "model_a_risk"
CV_FOLDS = 5
TOP_FEATURES = 3
GLOBAL_FEATURES = 10


@dataclass(frozen=True)
class RiskTrainingPorts:
    """The collaborators of the training, one per port (ISP); grouped so the use case has one constructor argument per
    concern (data, modelling, comparison, persistence)."""

    data: TrainingDataSource
    splitter: ProjectSplitter
    trainer: ModelTrainer
    explainer: Explainer
    charts: Charts
    zero_shot: ZeroShotClassifier
    registry: ModelRegistry
    export: ExportOnnxUseCase
    sink: ResultSink
    reports: ReportWriter
    clock: Clock


def _cost(
    name: str, truth: Sequence[str], predicted: Sequence[str | None], seconds: float | None, tokens: float | None
) -> ClassifierCost:
    return ClassifierCost(
        name=name,
        evaluation=evaluate(truth, predicted),
        macro_f1_interval=bootstrap_interval(truth, predicted, macro_f1),
        critical_recall_interval=bootstrap_interval(truth, predicted, critical_recall),
        seconds_per_finding=seconds,
        tokens_per_finding=tokens,
        consistency=None,
        invalid_answers=sum(p is None for p in predicted),
    )


def _test_metrics(cost: ClassifierCost) -> list[MetricValue]:
    e = cost.evaluation
    values = [
        MetricValue("TEST", 0, "MACRO_F1", "ALL", e.macro_f1),
        MetricValue("TEST", 0, "MACRO_F1_CI_LOW", "ALL", cost.macro_f1_interval[0]),
        MetricValue("TEST", 0, "MACRO_F1_CI_HIGH", "ALL", cost.macro_f1_interval[1]),
        MetricValue("TEST", 0, "ACCURACY", "ALL", e.accuracy),
        MetricValue("TEST", 0, "INVALID_ANSWERS", "ALL", float(cost.invalid_answers)),
    ]
    for c in e.per_class:
        values += [
            MetricValue("TEST", 0, "PRECISION", c.label, c.precision),
            MetricValue("TEST", 0, "RECALL", c.label, c.recall),
            MetricValue("TEST", 0, "F1", c.label, c.f1),
            MetricValue("TEST", 0, "SUPPORT", c.label, float(c.support)),
        ]
    if cost.seconds_per_finding is not None:
        values.append(MetricValue("TEST", 0, "SECONDS_PER_FINDING", "ALL", cost.seconds_per_finding))
    if cost.tokens_per_finding is not None:
        values.append(MetricValue("TEST", 0, "TOKENS_PER_FINDING", "ALL", cost.tokens_per_finding))
    if cost.consistency is not None:
        values.append(MetricValue("TEST", 0, "RUN_AGREEMENT", "ALL", cost.consistency.identical))
    return values


class TrainRiskModelService:
    def __init__(self, ports: RiskTrainingPorts) -> None:
        self._p = ports

    def execute(self, command: TrainRiskCommand) -> TrainRiskResult:
        if command.label_source not in LABEL_SOURCES:
            raise RiskTrainingError("the label source is GOLD or SILVER")
        rows = self._p.data.rows()
        split = self._p.splitter.split(rows, command.seed)
        if leaked_projects(split):
            raise RiskTrainingError("a project is on both sides of the split")
        labelled = [r for r in rows if r.label(command.label_source) is not None]
        train, test = partition(labelled, split)
        if not train or not test:
            raise RiskTrainingError(
                f"no {command.label_source.lower()} labels on one side of the split (import the gold labels first)"
            )
        y_train = [r.label(command.label_source) or "" for r in train]
        y_test = [r.label(command.label_source) or "" for r in test]

        cv, child_runs = self._cross_validate(train, y_train, command.label_source)
        chosen = best_candidate([CandidateScore(c.algorithm, c.mean_macro_f1, c.mean_critical_recall) for c in cv])
        model = self._p.trainer.fit(chosen.algorithm, train, y_train)

        started = time.perf_counter()
        test_probabilities = model.probabilities(test)
        model_seconds = (time.perf_counter() - started) / len(test)
        predicted = [max(p, key=p.__getitem__) for p in test_probabilities]
        model_cost = _cost(chosen.algorithm, y_test, predicted, model_seconds, 0.0)
        rule_cost = _cost("rule_baseline_v1", y_test, [r.silver_label for r in test], None, None)
        llm_cost = self._zero_shot(test, y_test) if command.with_llm else None

        command.artifacts_dir.mkdir(parents=True, exist_ok=True)
        calibration = command.artifacts_dir / "calibration.png"
        summary = command.artifacts_dir / "shap_summary.png"
        self._p.charts.calibration(y_test, test_probabilities, calibration)
        self._p.explainer.summary_chart(model, train, summary)
        attributions = self._p.explainer.top_features(model, rows, TOP_FEATURES)
        importance = self._p.explainer.global_importance(model, train, GLOBAL_FEATURES)
        parity = self._p.export.execute(ExportOnnxCommand(model, test, command.onnx))
        confusions = self._confusions(command, [model_cost, rule_cost, llm_cost])

        facts = ModelAFacts(
            label_source=command.label_source, version=command.version, total_rows=len(rows),
            labelled_rows=len(labelled), train_rows=len(train), test_rows=len(test),
            train_projects=len({r.project_key for r in train}), test_projects=len({r.project_key for r in test}),
            test_class_counts=Counter(y_test), cv=cv, selected=chosen.algorithm,
            selected_params=model.params, model=model_cost, rule=rule_cost, llm=llm_cost,
            llm_model=self._p.zero_shot.model_id if llm_cost else None,
            llm_prompt=self._p.zero_shot.prompt_version if llm_cost else None, parity_rows=parity.rows,
            parity_classes_equal=parity.classes_equal, parity_max_difference=parity.max_probability_difference,
            top_features=[(a.feature, a.value) for a in importance],
        )  # fmt: skip
        verdict = h3(facts)
        run_id = self._log_parent(
            command, facts, labelled, child_runs, [calibration, summary, command.onnx, *confusions]
        )
        stored = command.label_source == GOLD
        skipped = self._store(command, facts, model, rows, attributions, run_id) if stored else 0
        self._p.reports.write(command.report, build_report(facts))
        self._p.reports.write(command.model_card, build_model_card(facts))
        return TrainRiskResult(
            label_source=command.label_source, train_rows=len(train), test_rows=len(test),
            test_projects=facts.test_projects, selected=chosen.algorithm,
            cv_macro_f1={c.algorithm: c.mean_macro_f1 for c in cv}, test_macro_f1=model_cost.evaluation.macro_f1,
            rule_macro_f1=rule_cost.evaluation.macro_f1,
            llm_macro_f1=None if llm_cost is None else llm_cost.evaluation.macro_f1, h3_met=verdict,
            onnx_parity=True, stored=stored, erased_skipped=skipped,
        )  # fmt: skip

    def _cross_validate(
        self, train: Sequence[RiskRow], labels: Sequence[str], source: str
    ) -> tuple[list[CvSummary], list[str]]:
        summaries, runs = [], []
        for algorithm in self._p.trainer.algorithms:
            folds = self._p.trainer.cross_validate(algorithm, train, labels, CV_FOLDS)
            evaluations: list[Evaluation] = [evaluate(f.truth, f.predicted) for f in folds]
            f1s = [e.macro_f1 for e in evaluations]
            recalls = [e.recall(CRITICAL) for e in evaluations]
            summary = CvSummary(
                algorithm=algorithm,
                mean_macro_f1=statistics.fmean(f1s),
                std_macro_f1=statistics.pstdev(f1s),
                mean_critical_recall=statistics.fmean(recalls),
                params=folds[-1].params if folds else {},
            )
            summaries.append(summary)
            metrics = {f"fold{f.fold}_macro_f1": e.macro_f1 for f, e in zip(folds, evaluations, strict=True)}
            metrics |= {"cv_macro_f1_mean": summary.mean_macro_f1, "cv_macro_f1_std": summary.std_macro_f1,
                        "cv_critical_recall_mean": summary.mean_critical_recall}  # fmt: skip
            grid = {f"grid.{k}": list(v) for k, v in self._p.trainer.grid(algorithm).items()}
            runs.append(
                self._p.registry.log_run(
                    EXPERIMENT, RunRecord(f"cv-{algorithm}", grid, metrics, {"label_source": source}, [])
                )
            )
        return summaries, runs

    def _confusions(self, command: TrainRiskCommand, costs: Sequence[ClassifierCost | None]) -> list[Path]:
        """The confusion matrix of each classifier as a JSON artifact (rows: true class, columns: predicted class)."""
        paths = []
        for cost in costs:
            if cost is None:
                continue
            path = command.artifacts_dir / f"confusion_{cost.name.replace(':', '_')}.json"
            matrix = {"classes": list(RISK_CLASSES), "matrix": [list(row) for row in cost.evaluation.confusion]}
            self._p.reports.write(path, json.dumps(matrix, indent=2) + "\n")
            paths.append(path)
        return paths

    def _zero_shot(self, test: Sequence[RiskRow], truth: Sequence[str]) -> ClassifierCost:
        try:
            first = [self._p.zero_shot.classify(r) for r in test]
            second = [self._p.zero_shot.classify(r) for r in test]
        except ZeroShotUnavailableError:
            raise RiskTrainingError("the local LLM cannot be reached (run with --no-llm to skip it)") from None
        seconds = statistics.fmean(a.seconds for a in first)
        tokens = statistics.fmean(a.prompt_tokens + a.output_tokens for a in first)
        cost = _cost(self._p.zero_shot.model_id, truth, [a.label for a in first], seconds, tokens)
        consistency = agreement([a.label for a in first], [a.label for a in second])
        return replace(cost, consistency=consistency)

    def _log_parent(
        self,
        command: TrainRiskCommand,
        facts: ModelAFacts,
        labelled: Sequence[RiskRow],
        child_runs: Sequence[str],
        artifacts: Sequence[Path],
    ) -> str:
        ordered = sorted(labelled, key=lambda r: r.finding_id)
        lines = "\n".join(f"{r.finding_id}:{r.label(command.label_source)}" for r in ordered)
        snapshot = hashlib.sha256(lines.encode("utf-8")).hexdigest()
        metrics = {
            "test_macro_f1": facts.model.evaluation.macro_f1,
            "test_critical_recall": facts.model.evaluation.recall(CRITICAL),
            "rule_macro_f1": facts.rule.evaluation.macro_f1,
            "onnx_max_probability_difference": facts.parity_max_difference,
        }
        for prefix, cost in (("test", facts.model), ("rule", facts.rule), ("llm", facts.llm)):
            if cost is None:
                continue
            metrics[f"{prefix}_macro_f1"] = cost.evaluation.macro_f1
            metrics[f"{prefix}_accuracy"] = cost.evaluation.accuracy
            for c in cost.evaluation.per_class:
                scores = (("precision", c.precision), ("recall", c.recall), ("f1", c.f1))
                metrics |= {f"{prefix}_{c.label.lower()}_{name}": value for name, value in scores}
        params = {**{f"model.{k}": v for k, v in facts.selected_params.items()}, "algorithm": facts.selected,
                  "seed": command.seed, "test_projects": facts.test_projects}  # fmt: skip
        tags = {
            "label_source": command.label_source, "version": command.version, "data_rows": str(len(labelled)),
            "data_sha256": snapshot, "child_runs": ",".join(child_runs),
        }  # fmt: skip
        return self._p.registry.log_run(
            EXPERIMENT,
            RunRecord(f"{MODEL_NAME}-{command.version}", params, metrics, tags, list(artifacts)),
        )

    def _store(
        self,
        command: TrainRiskCommand,
        facts: ModelAFacts,
        model: TrainedModel,
        rows: Sequence[RiskRow],
        attributions: Sequence[Sequence[Attribution]],
        run_id: str,
    ) -> int:
        at = self._p.clock.now()
        probabilities = model.probabilities(rows)
        predictions = [
            Prediction(r.finding_id, r.project_key, max(p, key=p.__getitem__), risk_score(p), list(a))
            for r, p, a in zip(rows, probabilities, attributions, strict=True)
        ]
        cv_metrics = [
            MetricValue(scope, 0, "MACRO_F1", "ALL", value)
            for c in facts.cv
            if c.algorithm == facts.selected
            for scope, value in (("CV_MEAN", c.mean_macro_f1), ("CV_STD", c.std_macro_f1))
        ]
        stored = [StoredModel(MODEL_NAME, command.version, facts.selected, GOLD, run_id, at,
                                       cv_metrics + _test_metrics(facts.model), predictions, True),  # fmt: skip
                  StoredModel(RULE_NAME, RULE_VERSION, "RULE_BASELINE", GOLD, None, at,
                                       _test_metrics(facts.rule), [], False)]  # fmt: skip
        if facts.llm is not None and facts.llm_model is not None:
            stored.append(StoredModel(LLM_NAME, f"{facts.llm_model}-{facts.llm_prompt}", "LLM_ZERO_SHOT", GOLD,
                                           None, at, _test_metrics(facts.llm), [], False))  # fmt: skip
        return self._p.sink.store(stored)


__all__ = ["RiskTrainingPorts", "TrainRiskModelService"]
