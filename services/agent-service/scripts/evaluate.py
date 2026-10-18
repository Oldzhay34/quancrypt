#!/usr/bin/env python3
"""Runs the evaluation and writes `docs/eval_report.md` (P4.7).

The sets are `data/examples/{golden_qa,scope_set_seed,injection_set}.jsonl`. The golden and scope sets go to the running
agent-service over HTTP (D-260); the task router and the injection paths run in this process against the same services
and the same model (D-262, D-263). Every record is written to `docs/eval_results.jsonl`; the report holds the date, the
models, the prompt versions, the metric table with the status against each target, the findings for missed targets
and the failed examples (redacted). A missed target is reported as a finding, never hidden (P4.7 out of scope).

Needs the running stack (`make up PROFILES="app demo"` with `PROJECT_ROOT=reference-system`), the local Ollama and the
agent-service environment (AGENT_DB_* passwords, INTERNAL_SERVICE_TOKEN, QUANCRYPT_SESSION_TOKEN). The project analyzed
is the QBank payment service (D-203). Each run creates a new core-service project.

Exit codes: 0 every defined target met, 3 the report was written and at least one target was missed or could not be
measured, 1 the stack was not usable, 2 invalid sets or environment.

Usage (from services/agent-service):
  python scripts/evaluate.py [--agent-url URL] [--core-url URL] [--root /workspace/qbank-payment-service]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import re
import sys
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from src.evaluation.metrics import (
    TARGETS,
    AnswerRecord,
    InjectionRecord,
    Metrics,
    Percentiles,
    Rate,
    RouteRecord,
    ScopeRecord,
)
from src.evaluation.test_cases import EvaluationSets

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
GOLDEN_INVENTORY = REPO_ROOT / "reference-system" / "expected" / "crypto_inventory.yaml"
PAYMENT_PREFIX = "qbank-payment-service/"
# The clarification answers of the injection runs' plan task: "unknown" everywhere, so no fact about QBank is invented.
PROFILE_ANSWERS: tuple[Mapping[str, Any], ...] = (
    {"question_code": "TLS_TERMINATION", "option_code": "UNKNOWN"},
    {"question_code": "JDK_UPGRADE_POSSIBLE", "option_code": "UNKNOWN"},
    {"question_code": "HYBRID_INCAPABLE_PARTNERS", "option_code": "UNKNOWN"},
    {"question_code": "COMPLIANCE_REQUIREMENT", "option_code": "UNKNOWN"},
    {"question_code": "DEVICE_HARDWARE_OPENSSL", "option_code": None, "free_text": "unknown"},
)
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_EXCERPT_CHARS = 300


@dataclass(frozen=True)
class RunInfo:
    started_at: datetime
    finished_at: datetime
    chat_model: str
    embedding_model: str
    llm_provider: str
    prompts: tuple[tuple[str, int], ...]
    agent_url: str
    root: str
    project_id: str
    scan_id: str
    kb_notes: int


@dataclass(frozen=True)
class Results:
    answers: Sequence[AnswerRecord]
    scope: Sequence[ScopeRecord]
    routes: Sequence[RouteRecord]
    injections: Sequence[InjectionRecord]


@dataclass(frozen=True)
class InventoryDiff:
    """The golden inventory (D-123) against what the tools recorded for the same root (D-266)."""

    only_golden: tuple[str, ...]
    only_tool: tuple[str, ...]
    changed: tuple[str, ...]


# ---- knowledge-base text (the tool outputs of kb_search come from the indexed notes) ----


def approved_note_texts(raw_dir: Path) -> list[str]:
    """Title, version tag and body of every note `make index` indexes (status: approved)."""
    texts = []
    for path in sorted(raw_dir.glob("*.md")):
        match = _FRONTMATTER.match(path.read_text("utf-8"))
        if match is None:
            continue
        meta = yaml.safe_load(match.group(1)) or {}
        if meta.get("status") == "approved":
            texts.append(f"{meta.get('title', '')}\n{meta.get('version_tag', '')}\n{match.group(2)}")
    return texts


# ---- golden inventory against the tool output ----


def inventory_diff(golden_entries: Sequence[Mapping[str, Any]], findings: Sequence[Mapping[str, Any]]) -> InventoryDiff:
    def key(path: str, symbol: str) -> str:
        return f"{path}#{symbol.split('#')[-1]}" if "#" in symbol else f"{path} {symbol}"

    expected: dict[str, list[Mapping[str, Any]]] = {}
    for entry in golden_entries:
        file = str(entry["file"])
        if file.startswith(PAYMENT_PREFIX) and entry.get("location_kind") != "TEST_CODE":
            expected.setdefault(key(file[len(PAYMENT_PREFIX) :], str(entry["symbol"])), []).append(entry)
    found: dict[str, list[Mapping[str, Any]]] = {}
    for finding in findings:
        if finding.get("locationKind") != "TEST_CODE":
            found.setdefault(key(str(finding["path"]), str(finding.get("symbol") or "")), []).append(finding)
    changed = []
    for name in sorted(set(expected) & set(found)):
        want = {(e["algorithm_family"], e["priority"], e.get("key_size_bits")) for e in expected[name]}
        have = {(f["algorithmFamily"], f["priority"], f.get("keySizeBits")) for f in found[name]}
        if want != have:
            changed.append(f"{name}: altın {sorted(map(_triple, want))} / araç {sorted(map(_triple, have))}")
    return InventoryDiff(
        only_golden=tuple(sorted(set(expected) - set(found))),
        only_tool=tuple(sorted(set(found) - set(expected))),
        changed=tuple(changed),
    )


def _triple(value: tuple[Any, Any, Any]) -> str:
    family, priority, size = value
    return f"{family} {priority} {size if size is not None else '-'}"


# ---- report ----


def render_report(
    info: RunInfo,
    sets: EvaluationSets,
    metrics: Metrics,
    results: Results,
    diff: InventoryDiff,
    redact: Callable[[str], str],
) -> str:
    status = metrics.target_status()
    rows = [
        ("Kapsam dışı recall (H4)", _pct(metrics.out_of_scope_recall), "out_of_scope_recall"),
        ("Yanlış ret oranı (H4)", _pct(metrics.false_refusal_rate), "false_refusal_rate"),
        ("Niyet doğruluğu (bileşen, D-262)", _pct(metrics.intent_accuracy), None),
        ("Uydurma oranı", _pct(metrics.fabrication_rate), "fabrication_rate"),
        ("Kaynak gösterme oranı", _pct(metrics.citation_rate), None),
        ("Beklenen içerik isabeti (golden)", _pct(metrics.expected_content), None),
        (
            "Araç çağrısına dönüşen enjekte talimat",
            f"{metrics.injected_tool_calls} çağrı (argüman değişikliği: {metrics.injected_argument_changes}); "
            f"{metrics.injection_cases_with_calls.hits}/{metrics.injection_cases_with_calls.total} vaka; "
            f"tamamlanan koşu {metrics.injection_runs - metrics.injection_incomplete}/{metrics.injection_runs}",
            "injected_tool_calls",
        ),
        ("İlk parça süresi p50 / p95", _seconds(metrics.first_token_s), "first_token_p95_s"),
        ("Toplam süre p50 / p95", _seconds(metrics.total_s), "total_p95_s"),
    ]
    lines = [
        "# agent-service değerlendirme raporu",
        "",
        f"- Tarih: {info.started_at:%Y-%m-%d %H:%M} – {info.finished_at:%H:%M} UTC",
        f"- Modeller: sohbet `{info.chat_model}`, embedding `{info.embedding_model}` "
        f"(sağlayıcı `{info.llm_provider}`); Model B yok (baseline, P7.5'te yeniden koşulur)",
        "- İstem sürümleri: " + ", ".join(f"`{name}` v{version}" for name, version in info.prompts),
        f"- Hedef: {info.agent_url}, kök `{info.root}` (D-203), proje `{info.project_id}`, tarama `{info.scan_id}`",
        f"- Setler: golden {len(sets.golden)}, kapsam {len(sets.scope)}, injection {len(sets.injection)} "
        f"(3 yolda {len(results.injections)} koşu); indeksli bilgi tabanı notu (approved): {info.kb_notes}",
        "",
        "## Metrikler",
        "",
        "| Metrik | Değer | Hedef | Durum |",
        "|---|---|---|---|",
    ]
    for label, value, target_name in rows:
        if target_name is None:
            lines.append(f"| {label} | {value} | tanımlı değil (D-265) | — |")
            continue
        target = TARGETS[target_name]
        sign = "≥" if target.comparison == "min" else "≤"
        verdict = status[target_name]
        shown = "veri yok" if verdict is None else ("TUTTU" if verdict else "**TUTMADI**")
        lines.append(f"| {label} | {value} | {sign} {_target(target_name)} ({target.source}) | {shown} |")
    lines += ["", "## Bulgular", ""]
    missed = [name for name, verdict in status.items() if verdict is False]
    unknown = [name for name, verdict in status.items() if verdict is None]
    if not missed and not unknown:
        lines.append("Tanımlı hedeflerin hepsi tuttu.")
    lines += [f"- **Hedef tutmadı:** `{name}` ({TARGETS[name].source})." for name in missed]
    lines += [f"- **Ölçülemedi:** `{name}` (veri yok)." for name in unknown]
    if metrics.scope_errors:
        lines.append(f"- Kapsam setinde {metrics.scope_errors} istek hata ile bitti (ret sayılmadı).")
    if metrics.injection_errors:
        lines.append(f"- Injection koşularından {metrics.injection_errors} tanesi hata ile bitti (aşağıda).")
    if metrics.injection_incomplete:
        lines.append(
            f"- Injection koşularından {metrics.injection_incomplete}/{len(results.injections)} tanesi (veya temiz "
            "karşılığı) tamamlanmadı ya da modele hiç ulaşmadı: sıfır çağrı sonucu bu koşular için kanıt değildir; "
            f"bu koşularda görülen {metrics.injected_calls_in_incomplete_runs} beklenmeyen çağrı hedef toplamına "
            "katılmadı (aşağıda listelenir). Keşif ve Planlama koşularının hepsi tamamlanmadıkça injection hedefi "
            "ölçülmüş sayılmaz."
        )
    if info.kb_notes == 0:
        lines.append(
            "- Bilgi tabanında onaylı not yok (`data/raw` notlarının hepsi `draft`): bilgi tabanı soruları "
            '"emin değilim" ile yanıtlanır.'
        )
    lines += _method_notes()
    lines += _failed_examples(sets, metrics, results, redact)
    lines += ["", "## Altın envanter ile araç çıktısı farkları (D-266)", ""]
    lines.append("Kök `qbank-payment-service`, test kodu hariç; anahtar `dosya#metot` veya `dosya anahtar`.")
    lines.append("")
    lines += [f"- Yalnız altın veride: `{name}`" for name in diff.only_golden] or ["- Yalnız altın veride: yok"]
    lines += [f"- Yalnız araç çıktısında: `{name}`" for name in diff.only_tool] or ["- Yalnız araç çıktısında: yok"]
    lines += [f"- Farklı: {line}" for line in diff.changed] or ["- Alanı farklı kayıt: yok"]
    return "\n".join(lines) + "\n"


def _method_notes() -> list[str]:
    return [
        "",
        "## Yöntem",
        "",
        "- Golden ve kapsam setleri canlı HTTP üzerinden, her soru kendi oturumunda koşuldu (D-260). Süreler istemci "
        "tarafında: ilk SSE olayı ve son olay. Hedefler p95 ile karşılaştırılır (D-265).",
        "- Niyet doğruluğu `TaskRouter` ile bileşen düzeyinde, gerçek modelle ölçüldü (D-262).",
        "- Uydurma: yanıttaki her sayı ve dosya yolu, koşunun araç çıktılarıyla (core-service bulguları ve topolojisi, "
        "onaylı bilgi tabanı notları) ve sorunun kendi sayılarıyla karşılaştırılır; çıkış denetiminin "
        "işaretlediği iddia da yanıtta kaldığı için sayılır.",
        "- Injection: vaka metni gerçek araç çıktılarına (Keşif `get_snippet` penceresinin başına, Planlama "
        "`kb_search` ilk sonucuna, Supervisor bilgi tabanı pasajına) eklenen bir test düzeneğidir; ajanlar "
        "container'ın kendi fabrikasıyla kurulur ve canlı servislere ve gerçek modele karşı koşar (D-263, D-268). "
        "Her vaka temiz koşuyla karşılaştırılır: yeni araç adı, fazla çağrı, bulgu veya plan maddesi sayısı farkı ve "
        "`record_findings` bulgularında modelin belirlediği alan farkı (aile, öncelik, `classifiedBy`) sayılır "
        "(D-270).",
        "- Araç seçimini hiçbir ajanda model yapmaz: hangi aracın çağrılacağı koddadır. Modelin çıktısının bir araç "
        "argümanına girdiği tek yer Keşif'in aile sınıflandırmasıdır. Planlama ve cevap yollarında modelin metni "
        "yalnız yanıta gider; bu yollardaki sıfır, ölçümden çok mimari bir garantidir. Cevap yolunda niyet sabit "
        "`configuration`'dır, Planlama'ya devir olmaz.",
        "- Paydalar: uydurma oranı yalnız `done` biten yanıtlar üzerindendir; beklenen içerik isabeti ve kaynak "
        "gösterme oranında ret ve hata da paydadadır (başarısız sayılır).",
        '- Yan etkiler: her koşu core-service\'te yeni bir proje ("QBank evaluation <tarih>") açar; o projede bir '
        "ilk tarama ve her injection Keşif koşusu için bir tarama, bir plan ve `UNKNOWN` netleştirme yanıtları "
        "oluşur; agent_db'ye oturumlar, kapsam kararları (istek metni olmadan) ve oturumsuz koşu ve adım satırları "
        "yazılır. Yeni projede warehouse onayı olmadığından outbox'a olay gitmez.",
        "- Planlama yolunun açıklamalara ulaşması için netleştirme soruları `UNKNOWN` ile yanıtlandı.",
    ]


def _failed_examples(
    sets: EvaluationSets, metrics: Metrics, results: Results, redact: Callable[[str], str]
) -> list[str]:
    lines = ["", "## Başarısız örnekler (redakte)", "", "### Golden", ""]
    by_id = {answer.id: answer for answer in results.answers}
    intents = {question.id: question.intent for question in sets.golden}
    failed = [check for check in metrics.golden_checks if check.failed]
    if not failed:
        lines.append("Yok.")
    for check in failed:
        answer = by_id.get(check.id)
        reasons = [f"sonuç `{check.outcome}`" + (f" ({answer.error_code})" if answer and answer.error_code else "")]
        if check.unsupported:
            reasons.append("desteksiz: " + ", ".join(f"`{redact(claim)}`" for claim in check.unsupported))
        if check.missing_numbers:
            reasons.append("eksik sayı: " + ", ".join(check.missing_numbers))
        if check.missing_paths:
            reasons.append("eksik yol: " + ", ".join(f"`{path}`" for path in check.missing_paths))
        if check.missing_keywords:
            reasons.append("eksik anahtar kelime: " + ", ".join(check.missing_keywords))
        if check.not_cited:
            reasons.append("kaynak yok")
        lines.append(f"- `{check.id}` ({intents.get(check.id)}): " + "; ".join(reasons))
        if answer and answer.text:
            lines.append(f"  > {_excerpt(redact(answer.text))}")
    lines += ["", "### Niyet", ""]
    wrong = [route for route in results.routes if route.predicted != route.expected]
    lines += [f"- `{r.id}`: beklenen `{r.expected}`, yönlendirilen `{r.predicted}` ({r.routed_by})" for r in wrong]
    if not wrong:
        lines.append("Yok.")
    lines += ["", "### Kapsam", ""]
    categories = {case.id: case.category for case in sets.scope}
    off = [r for r in results.scope if (r.outcome == "refusal") != (r.expected == "OUT_OF_SCOPE")]
    lines += [
        f"- `{r.id}` ({categories.get(r.id)}): beklenen `{r.expected}`, sonuç `{r.outcome}`"
        + (f" ({r.error_code})" if r.error_code else "")
        for r in off
    ]
    if not off:
        lines.append("Yok.")
    lines += ["", "### Injection", ""]
    bad = [r for r in results.injections if r.injected_calls or r.denied_calls or not r.completed]
    for record in bad:
        detail = ", ".join(f"`{call}`" for call in (*record.unexpected_calls, *record.denied_calls)) or "-"
        if record.changed_arguments:
            detail += "; argüman değişikliği: " + ", ".join(f"`{change}`" for change in record.changed_arguments)
        state = f"; hata {record.error}" if record.error else ""
        if not record.error and not record.completed:
            state = (
                f"; sonuç `{record.status}` (temiz koşu `{record.clean_status}`), model çağrısı {record.model_calls}"
            )
        lines.append(f"- `{record.id}` / {record.path}: {detail}{state}")
    if not bad:
        lines.append("Yok.")
    return lines


def _pct(rate: Rate) -> str:
    return "veri yok" if math.isnan(rate.value) else f"%{rate.value * 100:.1f} ({rate.hits}/{rate.total})"


def _seconds(values: Percentiles) -> str:
    if not values.count:
        return "veri yok"
    return f"{values.p50:.2f} sn / {values.p95:.2f} sn (n={values.count})"


def _target(name: str) -> str:
    value = TARGETS[name].value
    if name.endswith("_s"):
        return f"{value:g} sn"
    if name == "injected_tool_calls":
        return f"{value:g}"
    return f"%{value * 100:g}"


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= _EXCERPT_CHARS else flat[: _EXCERPT_CHARS - 1] + "…"


# ---- results file ----


def write_results(path: Path, results: Results, redact: Callable[[str], str]) -> None:
    """One JSON line per record; answer texts pass the shared redactor first, as in the report (D-269)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for kind, records in (
            ("golden", results.answers),
            ("scope", results.scope),
            ("route", results.routes),
            ("injection", results.injections),
        ):
            for record in records:
                row = {"set": kind, **dataclasses.asdict(record)}
                if isinstance(row.get("text"), str):
                    row["text"] = redact(row["text"])
                out.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---- composition ----


def injection_stack(container: Any) -> tuple[Any, Any]:
    """The injection runs' agents are the container's own (D-268); only the model is wrapped to count its answers."""
    from src.evaluation.eval_agents import CountingLLM, InjectionStack
    from src.tools.base_tool import ToolContext

    model = CountingLLM(container.llm)

    def close_scan(scan_id: str) -> None:
        context = ToolContext(trace_id=uuid.uuid4().hex)
        container.tools.call("complete_scan", {"scanId": scan_id, "body": {"outcome": "COMPLETED"}}, context)

    stack = InjectionStack(
        agents=lambda toolbox, knowledge: container.agents(model, toolbox=toolbox, knowledge=knowledge),
        toolbox=container.tools.scoped,
        knowledge=container.knowledge,
        audit=container.audit,
        close_scan=close_scan,
        model_calls=lambda: model.answered,
    )
    return stack, model


# ---- main ----


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the agent-service evaluation and write docs/eval_report.md.")
    parser.add_argument("--agent-url", default=os.environ.get("AGENT_SERVICE_URL", "http://127.0.0.1:8083"))
    parser.add_argument("--core-url", default=os.environ.get("CORE_SERVICE_URL", "http://127.0.0.1:8081"))
    parser.add_argument("--root", default=os.environ.get("QUANCRYPT_ANALYSIS_ROOT", "/workspace/qbank-payment-service"))
    parser.add_argument("--examples", type=Path, default=SERVICE_ROOT / "data" / "examples")
    parser.add_argument("--report", type=Path, default=SERVICE_ROOT / "docs" / "eval_report.md")
    parser.add_argument("--results", type=Path, default=SERVICE_ROOT / "docs" / "eval_results.jsonl")
    args = parser.parse_args(argv)

    # Imported here so that the pure functions above can be tested without building the application.
    import httpx

    from src.app.container import build_container
    from src.app.logging_setup import configure_logging
    from src.app.settings import LOCAL_SERVICE_HOSTS, bare_local_origin, load_settings
    from src.evaluation.eval_agents import InjectionRunner, LiveRunner, LiveTarget, RunnerError, route_golden
    from src.evaluation.metrics import ToolEvidence, compute
    from src.evaluation.test_cases import TestCaseError, load_sets
    from src.prompts import system_prompts
    from src.workflows.task_router import TaskRouter

    try:
        sets = load_sets(args.examples)
    except TestCaseError as exc:
        print(f"Invalid evaluation set: {exc}", file=sys.stderr)
        return 2
    token = os.environ.get("QUANCRYPT_SESSION_TOKEN", "")
    if not token:
        print("QUANCRYPT_SESSION_TOKEN is not set", file=sys.stderr)
        return 2
    try:
        # The Bearer token goes only to a bare local origin (guardrails-security section 1).
        agent_url = bare_local_origin(args.agent_url, LOCAL_SERVICE_HOSTS | {"agent-service"})
        core_url = bare_local_origin(args.core_url, LOCAL_SERVICE_HOSTS)
    except ValueError as exc:
        print(f"Invalid service address: {exc}", file=sys.stderr)
        return 2
    settings = load_settings()
    container = build_container(settings)
    configure_logging(settings.logging, container.redactor)
    started = datetime.now(UTC)
    try:
        stack, model = injection_stack(container)
        target = LiveTarget(agent_url, core_url, token, args.root)
        with httpx.Client(timeout=target.timeout_s, trust_env=False, follow_redirects=False) as client:
            live = LiveRunner(target, client)
            try:
                live.prepare()
                answers = live.run_golden(sets.golden)
                scope = live.run_scope(sets.scope)
                scan_id, outputs = live.tool_outputs()
                routes = route_golden(TaskRouter(model), sets.golden)
                live.answer_profile(PROFILE_ANSWERS)
                project_id = live.project_id or ""
                injections = InjectionRunner(stack, project_id, scan_id, args.root).run(sets.injection)
            except RunnerError as exc:
                print(f"The evaluation could not run: {exc}", file=sys.stderr)
                return 1
        notes = approved_note_texts(SERVICE_ROOT / "data" / "raw")
        evidence = ToolEvidence.of([*outputs, *notes])
        metrics = compute(sets.golden, answers, scope, routes, injections, evidence)
        results = Results(answers, scope, routes, injections)
        golden_entries = yaml.safe_load(GOLDEN_INVENTORY.read_text("utf-8"))["entries"]
        diff = inventory_diff(golden_entries, outputs[0]["items"])
        ollama = settings.models.ollama
        info = RunInfo(
            started_at=started,
            finished_at=datetime.now(UTC),
            chat_model=ollama.chat_model,
            embedding_model=ollama.embedding_model,
            llm_provider=settings.models.llm.provider,
            prompts=tuple(
                (spec.id, spec.version)
                for spec in vars(system_prompts).values()
                if isinstance(spec, system_prompts.PromptSpec)
            ),
            agent_url=agent_url,
            root=args.root,
            project_id=project_id,
            scan_id=scan_id,
            kb_notes=len(notes),
        )
        write_results(args.results, results, container.redactor.redact)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            render_report(info, sets, metrics, results, diff, container.redactor.redact), encoding="utf-8"
        )
    finally:
        container.close()
    status = metrics.target_status()
    missed = [name for name, met in status.items() if met is False]
    unmeasured = [name for name, met in status.items() if met is None]
    print(f"Report: {args.report}")
    print(f"Results: {args.results}")
    print("Targets missed: " + (", ".join(missed) if missed else "none"))
    print("Targets not measured: " + (", ".join(unmeasured) if unmeasured else "none"))
    print("Intent routing: " + json.dumps(Counter(route.routed_by for route in routes)))
    # A missed or unmeasured target fails the run (the evaluation is a release gate: "eşiğin altında sürüm çıkmaz");
    # the report is written either way.
    return 3 if missed or unmeasured else 0


if __name__ == "__main__":
    sys.exit(main())
