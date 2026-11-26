"""Composition root of the ml command line: each command builds only what it needs (`scope-split` needs no database, the
import needs no analyzer), so a missing variable of another command never stops it."""

from __future__ import annotations

import os
from collections.abc import Mapping

from quancrypt_ml.facade.labeling_facade import LabelingFacade, LabelPaths, ScopeFacade
from quancrypt_ml.facade.mining_facade import MiningFacade, MiningPaths
from quancrypt_ml.facade.risk_facade import RiskFacade, RiskPaths
from quancrypt_ml.facade.scope_model_facade import ScopeModelFacade, ScopeModelPaths
from quancrypt_ml.infrastructure.analyzer.snippet_client import AnalyzerSnippetClient
from quancrypt_ml.infrastructure.files.batch_csv import CsvBatchFiles
from quancrypt_ml.infrastructure.files.text_files import FileReportWriter, JsonlScopeDatasetFiles
from quancrypt_ml.infrastructure.persistence import database
from quancrypt_ml.infrastructure.persistence.candidates import PostgresCandidateSource
from quancrypt_ml.infrastructure.persistence.label_store import PostgresLabelStore
from quancrypt_ml.infrastructure.persistence.locator import PostgresSourceLocator
from quancrypt_ml.infrastructure.settings import (
    ML_ROOT,
    ConfigError,
    Paths,
    load_analyzer,
    load_database,
    load_mlflow,
    load_paths,
    load_risk,
    load_salt,
    load_scope_model,
)
from quancrypt_ml.infrastructure.system import RandomIdGenerator, SystemClock
from quancrypt_ml.port.inbound.labeling import ExportCommand, ExportLabelBatchUseCase, ExportResult
from quancrypt_ml.usecase.export_label_batch_service import ExportLabelBatchService
from quancrypt_ml.usecase.import_labels_service import ImportLabelsService
from quancrypt_ml.usecase.labeling_report_writer import LabelingReporter
from quancrypt_ml.usecase.resolve_disagreements_service import ResolveDisagreementsService
from quancrypt_ml.usecase.split_scope_dataset_service import SplitScopeDatasetService

__all__ = ["ConfigError", "labeling", "migrate", "mining", "paths", "risk", "scope", "scope_model"]


def _env(source: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if source is None else source


def paths(source: Mapping[str, str] | None = None) -> Paths:
    return load_paths(_env(source))


def labeling(with_analyzer: bool, source: Mapping[str, str] | None = None) -> LabelingFacade:
    env = _env(source)
    folders = load_paths(env)
    engine = database.engine(load_database(env))
    store = PostgresLabelStore(engine)
    candidates = PostgresCandidateSource(engine)
    files = CsvBatchFiles()
    clock, ids = SystemClock(), RandomIdGenerator()
    reporter = LabelingReporter(store, candidates, files, FileReportWriter())
    export: ExportLabelBatchUseCase = _NoExport()
    if with_analyzer:
        analyzer = load_analyzer(env)
        locator = PostgresSourceLocator(engine, load_salt(env), folders.manifest)
        snippets = AnalyzerSnippetClient(analyzer.url, analyzer.token, analyzer.timeout_s)
        export = ExportLabelBatchService(candidates, locator, snippets, store, files, clock, ids)
    return LabelingFacade(
        export,
        ImportLabelsService(store, files, reporter, clock),
        ResolveDisagreementsService(store, files, reporter, clock),
        LabelPaths(folders.labeling_dir, folders.reports_dir / "labeling.md"),
    )


def risk(source: Mapping[str, str] | None = None) -> RiskFacade:
    """Model A (P7.2). The model libraries are imported here, not at module load, so the labelling commands stay
    light."""
    from quancrypt_ml.infrastructure.llm.ollama_zero_shot import OllamaZeroShotClassifier
    from quancrypt_ml.infrastructure.model.analysis import MatplotlibCharts, ShapExplainer, StratifiedProjectSplitter
    from quancrypt_ml.infrastructure.model.onnx_exporter import SklearnOnnxExporter
    from quancrypt_ml.infrastructure.model.trainer import SklearnModelTrainer
    from quancrypt_ml.infrastructure.persistence.result_sink import PostgresResultSink
    from quancrypt_ml.infrastructure.persistence.training_data import PostgresTrainingData
    from quancrypt_ml.infrastructure.registry.mlflow_registry import MlflowModelRegistry
    from quancrypt_ml.usecase.export_onnx_service import ExportOnnxService
    from quancrypt_ml.usecase.train_risk_model_service import RiskTrainingPorts, TrainRiskModelService

    env = _env(source)
    folders = load_paths(env)
    settings = load_risk(env)
    engine = database.engine(load_database(env))
    ports = RiskTrainingPorts(
        data=PostgresTrainingData(engine),
        splitter=StratifiedProjectSplitter(),
        trainer=SklearnModelTrainer(),
        explainer=ShapExplainer(),
        charts=MatplotlibCharts(),
        zero_shot=OllamaZeroShotClassifier(settings.ollama_url, settings.ollama_model),
        registry=MlflowModelRegistry(settings.mlflow_uri),
        export=ExportOnnxService(SklearnOnnxExporter()),
        sink=PostgresResultSink(engine),
        reports=FileReportWriter(),
        clock=SystemClock(),
    )
    return RiskFacade(
        TrainRiskModelService(ports), RiskPaths(folders.reports_dir, ML_ROOT / "model_cards", settings.models_dir)
    )


def scope_model(source: Mapping[str, str] | None = None) -> ScopeModelFacade:
    """Model B (P7.3). The model libraries are imported here, as in risk()."""
    from quancrypt_ml.infrastructure.files.embedding_cache import NpyEmbeddingCache
    from quancrypt_ml.infrastructure.llm.ollama_embedding import OllamaEmbeddingProvider
    from quancrypt_ml.infrastructure.model.analysis import MatplotlibCharts
    from quancrypt_ml.infrastructure.model.scope_onnx import SklearnScopeOnnxExporter
    from quancrypt_ml.infrastructure.model.scope_trainer import SklearnScopeTrainer
    from quancrypt_ml.infrastructure.persistence.result_sink import PostgresResultSink
    from quancrypt_ml.infrastructure.registry.mlflow_registry import MlflowModelRegistry
    from quancrypt_ml.usecase.export_scope_onnx_service import ExportScopeOnnxService
    from quancrypt_ml.usecase.train_scope_classifier_service import ScopeTrainingPorts, TrainScopeClassifierService

    env = _env(source)
    folders = load_paths(env)
    settings = load_scope_model(env)
    engine = database.engine(load_database(env))
    ports = ScopeTrainingPorts(
        files=JsonlScopeDatasetFiles(),
        embeddings=OllamaEmbeddingProvider(
            settings.ollama_url, settings.embedding_model, settings.embedding_dimensions
        ),
        cache=NpyEmbeddingCache(folders.scope_dir),
        trainer=SklearnScopeTrainer(),
        export=ExportScopeOnnxService(SklearnScopeOnnxExporter(settings.embedding_dimensions)),
        charts=MatplotlibCharts(),
        registry=MlflowModelRegistry(settings.mlflow_uri),
        sink=PostgresResultSink(engine),
        reports=FileReportWriter(),
        clock=SystemClock(),
    )
    paths = ScopeModelPaths(folders.scope_dir, folders.reports_dir, ML_ROOT / "model_cards", settings.models_dir)
    return ScopeModelFacade(TrainScopeClassifierService(ports), paths)


def mining(source: Mapping[str, str] | None = None) -> MiningFacade:
    """Data mining (P7.4). The model libraries are imported here, as in risk()."""
    from quancrypt_ml.infrastructure.model.mining import MlxtendRuleMiner, SklearnAnomalyDetector, SklearnClusterer
    from quancrypt_ml.infrastructure.model.mining_charts import MatplotlibMiningCharts
    from quancrypt_ml.infrastructure.persistence.mining_data import PostgresMiningData
    from quancrypt_ml.infrastructure.persistence.mining_sink import PostgresMiningSink
    from quancrypt_ml.infrastructure.registry.mlflow_registry import MlflowModelRegistry
    from quancrypt_ml.usecase.detect_anomalies_service import AnomalyPorts, DetectAnomaliesService
    from quancrypt_ml.usecase.mine_association_rules_service import MineAssociationRulesService, RulePorts
    from quancrypt_ml.usecase.mine_corpus_service import MineCorpusService
    from quancrypt_ml.usecase.run_clustering_service import ClusteringPorts, RunClusteringService

    env = _env(source)
    folders = load_paths(env)
    mlflow_uri = load_mlflow(env)
    engine = database.engine(load_database(env))
    data, charts, sink = PostgresMiningData(engine), MatplotlibMiningCharts(), PostgresMiningSink(engine)
    registry, reports, clock = MlflowModelRegistry(mlflow_uri), FileReportWriter(), SystemClock()
    clustering = RunClusteringService(ClusteringPorts(SklearnClusterer(), charts, registry, sink, reports, clock))
    rules = MineAssociationRulesService(RulePorts(MlxtendRuleMiner(), charts, registry, sink, reports, clock))
    anomalies = DetectAnomaliesService(AnomalyPorts(SklearnAnomalyDetector(), charts, registry, sink, reports, clock))
    return MiningFacade(
        MineCorpusService(data, clustering, rules, anomalies, reports), MiningPaths(folders.reports_dir)
    )


def scope() -> ScopeFacade:
    return ScopeFacade(SplitScopeDatasetService(JsonlScopeDatasetFiles()))


def migrate(source: Mapping[str, str] | None = None) -> None:
    env = _env(source)
    database.migrate(load_database(env, migrator=True), load_paths(env).migrations_dir)


class _NoExport:
    def execute(self, command: ExportCommand) -> ExportResult:  # pragma: no cover (only import and resolve are wired)
        raise RuntimeError("the export is built with the analyzer")
