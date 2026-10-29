"""The corpus run report (`reports/corpus_run.md`, P6.2): counts derived from the manifest, so a run in several parts
adds up and writing the report twice gives the same text."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime

from quancrypt_data.domain.corpus import CORPUS_MINIMUM, CORPUS_TARGET, AnalysisStatus, CloneStatus, ManifestEntry


def render_report(entries: Sequence[ManifestEntry], listed: int, generated_at: datetime) -> str:
    attempted = [e for e in entries if e.status is not CloneStatus.SELECTED]
    cloned = [e for e in entries if e.status is CloneStatus.CLONED]
    excluded = Counter(e.exclusion_reason.value for e in entries if e.exclusion_reason is not None)
    failed_clone = [e for e in entries if e.status is CloneStatus.FAILED]
    analyzed = [e for e in cloned if e.analysis_status is AnalysisStatus.ANALYZED]
    analysis_failed = [e for e in cloned if e.analysis_status is AnalysisStatus.FAILED]
    unsupported = [e for e in cloned if e.analysis_status is AnalysisStatus.UNSUPPORTED]
    findings = sum(e.findings_total for e in analyzed)
    stamp = generated_at.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    verdict = (
        f"Hedef ({CORPUS_TARGET}) karşılandı"
        if len(analyzed) >= CORPUS_TARGET
        else f"Alt sınır ({CORPUS_MINIMUM}) karşılandı, hedef ({CORPUS_TARGET}) değil"
        if len(analyzed) >= CORPUS_MINIMUM
        else f"Alt sınır ({CORPUS_MINIMUM}) KARŞILANMADI"
    )
    lines = [
        "# Korpus çalıştırma raporu",
        "",
        f"Üretildi: {stamp}. Sayılar `corpus_manifest.csv`'den türetilir; parçalı koşular birikir.",
        "",
        "| Ölçü | Sayı |",
        "|---|---|",
        f"| Listedeki proje (`corpus_projects.csv`) | {listed} |",
        f"| Denenen (klonlama denendi) | {len(attempted)} |",
        f"| Klonlanan ve elenmeyen | {len(cloned)} |",
        f"| Elenen (toplam) | {sum(excluded.values())} |",
        f"| Klonlama hatası | {len(failed_clone)} |",
        f"| Analiz edilen | {len(analyzed)} |",
        f"| Analizde hata veren | {len(analysis_failed)} |",
        f"| Desteklenmeyen (analizci reddetti) | {len(unsupported)} |",
        f"| Toplam bulgu (analiz edilenlerde) | {findings} |",
        "",
        f"Durum: {verdict}.",
        "",
        "## Elenme nedenleri",
        "",
    ]
    if excluded:
        lines += [
            "| Neden | Proje |",
            "|---|---|",
            *(f"| {reason} | {count} |" for reason, count in sorted(excluded.items())),
        ]
    else:
        lines.append("Eleme yok.")
    lines += ["", "## Lisansı doğrulanamayan projeler", ""]
    unverified = sorted(
        e.repo_url
        for e in entries
        if e.exclusion_reason is not None and e.exclusion_reason.value == "license-unverified"
    )
    lines += [f"- {url}" for url in unverified] or ["Yok."]
    return "\n".join(lines) + "\n"
