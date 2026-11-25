"""Model B ports: the fake and the real adapter pass the same cases (tests/support/scope_port_cases.py), plus the real
adapters' own rules: the Ollama request agent-service sends, the cache files, the family precondition and the
embedding model shared with agent-service."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from quancrypt_ml.infrastructure.files.embedding_cache import NpyEmbeddingCache
from quancrypt_ml.infrastructure.files.text_files import JsonlScopeDatasetFiles
from quancrypt_ml.infrastructure.llm.ollama_embedding import OllamaEmbeddingProvider
from quancrypt_ml.infrastructure.model.analysis import MatplotlibCharts
from quancrypt_ml.infrastructure.model.scope_onnx import SklearnScopeOnnxExporter
from quancrypt_ml.infrastructure.model.scope_trainer import SklearnScopeTrainer
from quancrypt_ml.infrastructure.settings import EMBEDDING_DIMENSIONS, REPO_ROOT, ConfigError, load_scope_model
from quancrypt_ml.port.outbound.scope_model import EmbeddingProvider, EmbeddingUnavailableError, ScoreCharts
from tests.support.scope_fakes import (
    FakeEmbeddingCache,
    FakeEmbeddings,
    FakeScopeExporter,
    FakeScopeFiles,
    FakeScopeTrainer,
    FakeScoreCharts,
    FirstComponentModel,
    identity,
)
from tests.support.scope_port_cases import (
    CACHE_CASES,
    CHART_CASES,
    EMBEDDING_CASES,
    FAMILY_CASES,
    FAMILY_FILE_CASES,
    FILES_CASES,
    CacheFactory,
    EmbeddingFactory,
    FilesFactory,
    ScopeFamily,
)

URL = "http://127.0.0.1:11434"
DIGEST = "85462619ee72" + "0" * 52
TAGS = {"models": [{"name": "embeddinggemma:latest", "digest": DIGEST}, {"name": "gemma3:4b", "digest": "x"}]}


def _ollama(seen: list[dict[str, object]], size: int = 4) -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=TAGS)
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"embeddings": [[0.1] * size for _ in body["input"]]})

    return httpx.MockTransport(answer)


def _down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


def _fake_embeddings(up: bool) -> EmbeddingProvider:
    return FakeEmbeddings(down=not up)


def _real_embeddings(up: bool) -> EmbeddingProvider:
    transport = _ollama([]) if up else httpx.MockTransport(_down)
    return OllamaEmbeddingProvider(URL, "embeddinggemma:latest", 4, transport=transport)


EMBEDDINGS: dict[str, EmbeddingFactory] = {"fake": _fake_embeddings, "ollama": _real_embeddings}
CACHES: dict[str, CacheFactory] = {"fake": lambda folder: FakeEmbeddingCache(), "npy": NpyEmbeddingCache}
FAMILIES = {
    "fake": lambda: ScopeFamily(FakeScopeTrainer(), FakeScopeExporter()),
    "sklearn": lambda: ScopeFamily(SklearnScopeTrainer(), SklearnScopeOnnxExporter(4)),
}
CHARTS: dict[str, Callable[[], ScoreCharts]] = {"fake": FakeScoreCharts, "matplotlib": MatplotlibCharts}


@pytest.mark.parametrize("provider", EMBEDDINGS, ids=str)
@pytest.mark.parametrize("case", EMBEDDING_CASES, ids=lambda c: c.__name__)
def test_embedding_providers_keep_the_contract(case: Callable[[EmbeddingFactory], None], provider: str) -> None:
    case(EMBEDDINGS[provider])


@pytest.mark.parametrize("cache", CACHES, ids=str)
@pytest.mark.parametrize("case", CACHE_CASES, ids=lambda c: c.__name__)
def test_embedding_caches_keep_the_contract(
    case: Callable[[CacheFactory, Path], None], cache: str, tmp_path: Path
) -> None:
    if cache == "fake":
        shared = FakeEmbeddingCache()  # one in-memory cache stands for one folder
        case(lambda folder: shared, tmp_path)
    else:
        case(CACHES[cache], tmp_path)


@pytest.mark.parametrize("family", FAMILIES, ids=str)
@pytest.mark.parametrize("case", FAMILY_CASES, ids=lambda c: c.__name__)
def test_scope_families_keep_the_contract(case: Callable[[ScopeFamily], None], family: str) -> None:
    case(FAMILIES[family]())


@pytest.mark.parametrize("family", FAMILIES, ids=str)
@pytest.mark.parametrize("case", FAMILY_FILE_CASES, ids=lambda c: c.__name__)
def test_scope_families_keep_the_file_contract(
    case: Callable[[ScopeFamily, Path], None], family: str, tmp_path: Path
) -> None:
    case(FAMILIES[family](), tmp_path)


@pytest.mark.parametrize("charts", CHARTS, ids=str)
@pytest.mark.parametrize("case", CHART_CASES, ids=lambda c: c.__name__)
def test_score_charts_keep_the_contract(case: Callable[[ScoreCharts, Path], None], charts: str, tmp_path: Path) -> None:
    case(CHARTS[charts](), tmp_path)


def test_the_real_histogram_is_a_png(tmp_path: Path) -> None:
    path = tmp_path / "scores.png"
    MatplotlibCharts().score_histogram(["OUT_OF_SCOPE", "IN_SCOPE"], [0.9, 0.1], {"threshold": 0.5}, path)
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_embedding_request_is_agent_services_and_the_answer_is_checked() -> None:
    seen: list[dict[str, object]] = []
    provider = OllamaEmbeddingProvider(URL, "embeddinggemma:latest", 4, transport=_ollama(seen))
    assert provider.digest() == DIGEST
    provider.embed(["Projemde RSA nerede?"])
    assert seen == [{"model": "embeddinggemma:latest", "input": ["Projemde RSA nerede?"], "truncate": False}]
    wrong_size = OllamaEmbeddingProvider(URL, "embeddinggemma:latest", 768, transport=_ollama([], size=4))
    with pytest.raises(EmbeddingUnavailableError, match="768"):
        wrong_size.embed(["x"])
    missing = OllamaEmbeddingProvider(URL, "bge-m3:latest", 4, transport=_ollama([]))
    with pytest.raises(EmbeddingUnavailableError, match="not installed"):
        missing.digest()
    failing = httpx.MockTransport(lambda r: httpx.Response(500, json={"error": "secret text of the request"}))
    with pytest.raises(EmbeddingUnavailableError) as error:
        OllamaEmbeddingProvider(URL, "embeddinggemma:latest", 4, transport=failing).embed(["x"])
    assert "secret" not in str(error.value)


def test_a_damaged_cache_holds_nothing(tmp_path: Path) -> None:
    cache = NpyEmbeddingCache(tmp_path)
    key = "a" * 64
    cache.put("embeddinggemma:latest", "d", {key: [1.0, 2.0]})
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "embeddings_embeddinggemma_latest.index.json", "embeddings_embeddinggemma_latest.npy",
    ]  # fmt: skip
    (tmp_path / "embeddings_embeddinggemma_latest.index.json").write_text("{not json", encoding="utf-8")
    assert cache.get("embeddinggemma:latest", "d", [key]) == {}


def test_the_real_exporter_refuses_a_head_of_another_family(tmp_path: Path) -> None:
    foreign = FirstComponentModel("LOGISTIC_REGRESSION", {}, identity, FakeScopeTrainer().seen)
    with pytest.raises(TypeError):
        SklearnScopeOnnxExporter(4).export(foreign, [[0.1, 0.0, 0.0, 1.0]], tmp_path / "m.onnx")


def test_the_embedding_model_and_its_size_are_agent_services() -> None:
    """D-14: the head is trained on the vectors agent-service will compute (services/agent-service model_config)."""
    config = (REPO_ROOT / "services" / "agent-service" / "config" / "model_config.yaml").read_text(encoding="utf-8")
    model = re.search(r"^\s*embedding_model:\s*(\S+)\s*$", config, re.M)
    size = re.search(r"^\s*embedding_dimensions:\s*(\d+)\s*$", config, re.M)
    assert model is not None and size is not None
    settings = load_scope_model({})
    assert (settings.embedding_model, settings.embedding_dimensions) == (model.group(1), int(size.group(1)))
    assert int(size.group(1)) == EMBEDDING_DIMENSIONS


def test_the_scope_model_configuration_allows_loopback_only_and_a_model_tag() -> None:
    with pytest.raises(ConfigError, match="ML_EMBEDDING_MODEL"):
        load_scope_model({"ML_EMBEDDING_MODEL": "two words"})
    with pytest.raises(ConfigError, match="OLLAMA_BASE_URL"):
        load_scope_model({"OLLAMA_BASE_URL": "http://ollama.example.com:11434"})


FILES: dict[str, FilesFactory] = {"fake": lambda: FakeScopeFiles({}), "jsonl": JsonlScopeDatasetFiles}


@pytest.mark.parametrize("files", FILES, ids=str)
@pytest.mark.parametrize("case", FILES_CASES, ids=lambda c: c.__name__)
def test_scope_dataset_files_keep_the_contract(
    case: Callable[[FilesFactory, Path], None], files: str, tmp_path: Path
) -> None:
    case(FILES[files], tmp_path)


def test_a_discarded_model_leaves_the_previous_file_as_it_was(tmp_path: Path) -> None:
    trainer, exporter = SklearnScopeTrainer(), SklearnScopeOnnxExporter(4)
    vectors = [[0.1 * i, float(i % 2), float(i), 1.0] for i in range(40)]
    labels = ["OUT_OF_SCOPE" if i % 2 else "IN_SCOPE" for i in range(40)]
    model = trainer.fit("LOGISTIC_REGRESSION", {"C": 1.0}, vectors, labels, [f"g{i // 2}" for i in range(40)], 42)
    path = tmp_path / "head.onnx"
    path.write_bytes(b"previous")
    parity = exporter.export(model, vectors[:5], path)
    assert path.read_bytes() == b"previous" and len(parity.sha256) == 64
    exporter.discard(path)
    assert path.read_bytes() == b"previous" and list(tmp_path.iterdir()) == [path]
    parity = exporter.export(model, vectors[:5], path)  # the converter's bytes differ from run to run
    exporter.promote(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == parity.sha256
