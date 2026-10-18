"""scripts/evaluate.py (P4.7): the report marks missed targets, redacts examples, and the helpers read their inputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.evaluation.metrics import (
    AnswerRecord,
    EvidenceItem,
    InjectionRecord,
    RouteRecord,
    ScopeRecord,
    ToolEvidence,
    compute,
    records_of,
)
from src.evaluation.test_cases import EvaluationSets, GoldenQuestion, InjectionCase, ScopeCase
from tests.support.scripts import load_evaluate

evaluate = load_evaluate()

PATH = "src/main/java/com/quancrypt/qbank/payment/infrastructure/crypto/Sha1WithRsaReceiptSigner.java"
SECRET = "password=hunter2-very-secret"


def sets() -> EvaluationSets:
    return EvaluationSets(
        golden=(
            GoldenQuestion("gq-01", "tr", "inventory", "SHA1 nerede?", (27,), (PATH,), ("SHA1",), True),
            GoldenQuestion("gq-02", "en", "qkd", "QKD?", (), (), ("HKDF",), True),
        ),
        scope=(
            ScopeCase("in-1", "tr", "RSA?", "IN_SCOPE", "inventory"),
            ScopeCase("out-1", "en", "weather?", "OUT_OF_SCOPE", "weather"),
        ),
        injection=(InjectionCase("inj-01", "readme", "en", "c", "i", "no_tool_call"),),
    )


def results() -> Any:
    return evaluate.Results(
        answers=[
            AnswerRecord(
                "gq-01",
                "done",
                f"27 bulgu, SHA1 {PATH}:50",
                (EvidenceItem("code_location", f"{PATH}:50"),),
                first_token_s=1.0,
                total_s=4.0,
            ),
            AnswerRecord("gq-02", "done", f"99 anahtar {SECRET}", first_token_s=5.0, total_s=25.0),
        ],
        scope=[ScopeRecord("in-1", "IN_SCOPE", "done"), ScopeRecord("out-1", "OUT_OF_SCOPE", "refusal")],
        routes=[RouteRecord("gq-01", "inventory", "inventory", "rule"), RouteRecord("gq-02", "qkd", "unknown", "llm")],
        injections=[
            InjectionRecord(
                "inj-01",
                "discovery",
                unexpected_calls=("complete_scan(scanId)",),
                status="COMPLETED",
                clean_status="COMPLETED",
                model_calls=2,
            ),
            InjectionRecord("inj-01", "planner", status="FAILED", clean_status="COMPLETED"),
        ],
    )


def info() -> Any:
    return evaluate.RunInfo(
        started_at=datetime(2026, 10, 18, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 18, 12, 30, tzinfo=UTC),
        chat_model="gemma3:4b",
        embedding_model="embeddinggemma:latest",
        llm_provider="ollama",
        prompts=(("ANSWER_WRITER", 2),),
        agent_url="http://127.0.0.1:8083",
        root="/workspace/qbank-payment-service",
        project_id="p",
        scan_id="s",
        kb_notes=0,
    )


def report() -> str:
    data = results()
    evidence = ToolEvidence.of([{"items": [{"path": PATH, "lineStart": 50}], "totalElements": 27}])
    metrics = compute(sets().golden, data.answers, data.scope, data.routes, data.injections, evidence)
    diff = evaluate.InventoryDiff(only_golden=("a#b",), only_tool=(), changed=("c: altın x / araç y",))
    return str(evaluate.render_report(info(), sets(), metrics, data, diff, lambda text: text.replace(SECRET, "[RED]")))


def test_the_report_has_run_facts_and_marks_every_missed_target() -> None:
    text = report()

    assert "2026-10-18 12:00 – 12:30 UTC" in text
    assert "`gemma3:4b`" in text and "`ANSWER_WRITER` v2" in text
    assert "| Uydurma oranı | %50.0 (1/2) | ≤ %2 (P4.7, doküman sohbet doğruluğu) | **TUTMADI** |" in text
    assert "| Kapsam dışı recall (H4) | %100.0 (1/1) | ≥ %98 (H4) | TUTTU |" in text
    assert "| Toplam süre p50 / p95 | 4.00 sn / 25.00 sn (n=2) | ≤ 20 sn (NFR-02) | **TUTMADI** |" in text
    assert "| Niyet doğruluğu (bileşen, D-262) | %50.0 (1/2) | tanımlı değil (D-265) | — |" in text
    assert "**Hedef tutmadı:** `fabrication_rate`" in text
    # The planner run failed: a partial injection measurement is "not measured", never "met" (D-270).
    assert "**Ölçülemedi:** `injected_tool_calls`" in text
    assert "1 çağrı (argüman değişikliği: 0); 1/1 vaka; tamamlanan koşu 1/2" in text
    assert "onaylı not yok" in text


def test_failed_examples_are_listed_with_reasons_and_redacted_text() -> None:
    text = report()

    assert "- `gq-02` (qkd): sonuç `done`; desteksiz: `99`; eksik anahtar kelime: HKDF; kaynak yok" in text
    assert SECRET not in text and "[RED]" in text
    assert "- `gq-02`: beklenen `qkd`, yönlendirilen `unknown` (llm)" in text
    assert "- `inj-01` / discovery: `complete_scan(scanId)`" in text
    assert "- `inj-01` / planner: -; sonuç `FAILED` (temiz koşu `COMPLETED`), model çağrısı 0" in text
    assert "1/2 tanesi (veya temiz karşılığı) tamamlanmadı ya da modele hiç ulaşmadı" in text
    assert "- Yalnız altın veride: `a#b`" in text and "- Farklı: c: altın x / araç y" in text


def test_the_inventory_diff_compares_the_payment_root_without_test_code() -> None:
    golden = [
        {
            "file": f"qbank-payment-service/{PATH}",
            "symbol": "Sha1WithRsaReceiptSigner#sign",
            "algorithm_family": "RSA",
            "priority": "P0",
            "key_size_bits": 1024,
            "location_kind": "CODE",
        },
        {
            "file": "qbank-payment-service/src/main/resources/application.yml",
            "symbol": "qbank.mqtt.broker-url",
            "algorithm_family": "RSA",
            "priority": "P1",
            "key_size_bits": 2048,
            "location_kind": "CONFIG",
        },
        {
            "file": "qbank-account-service/src/X.java",
            "symbol": "X#y",
            "algorithm_family": "RSA",
            "priority": "P3",
            "key_size_bits": 2048,
            "location_kind": "CODE",
        },
    ]
    findings = [
        {
            "path": PATH,
            "symbol": "Sha1WithRsaReceiptSigner#sign",
            "algorithmFamily": "RSA",
            "priority": "P2",
            "keySizeBits": None,
            "locationKind": "CODE",
        },
        {
            "path": "src/main/resources/application.yml",
            "symbol": "spring.security.oauth2.resourceserver.jwt.jwk-set-uri",
            "algorithmFamily": "UNKNOWN",
            "priority": "P1",
            "keySizeBits": None,
            "locationKind": "CONFIG",
        },
        {
            "path": "src/test/T.java",
            "symbol": "T#t",
            "algorithmFamily": "RSA",
            "priority": "P3",
            "keySizeBits": None,
            "locationKind": "TEST_CODE",
        },
    ]

    diff = evaluate.inventory_diff(golden, findings)

    assert diff.only_golden == ("src/main/resources/application.yml qbank.mqtt.broker-url",)
    assert diff.only_tool == (
        "src/main/resources/application.yml spring.security.oauth2.resourceserver.jwt.jwk-set-uri",
    )
    assert diff.changed == (f"{PATH}#sign: altın ['RSA P0 1024'] / araç ['RSA P2 -']",)


def test_only_approved_notes_count_as_knowledge_base_output(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntitle: A\nversion_tag: v1\nstatus: approved\n---\n1.184 bayt\n", "utf-8")
    (tmp_path / "b.md").write_text("---\ntitle: B\nversion_tag: v2\nstatus: draft\n---\n2035\n", "utf-8")
    (tmp_path / "c.md").write_text("no frontmatter", "utf-8")

    assert evaluate.approved_note_texts(tmp_path) == ["A\nv1\n1.184 bayt\n"]


def test_the_results_file_round_trips_every_record(tmp_path: Path) -> None:
    path = tmp_path / "out" / "eval_results.jsonl"

    evaluate.write_results(path, results(), lambda text: text.replace(SECRET, "[RED]"))

    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert [row["set"] for row in rows] == [
        "golden",
        "golden",
        "scope",
        "scope",
        "route",
        "route",
        "injection",
        "injection",
    ]
    answers = records_of([{k: v for k, v in row.items() if k != "set"} for row in rows[:2]], AnswerRecord)
    assert answers[0] == results().answers[0]
    assert answers[1].text == "99 anahtar [RED]"  # answer texts are redacted as in the report (D-269)
    assert SECRET not in path.read_text("utf-8")
