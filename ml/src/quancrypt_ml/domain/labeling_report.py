"""The labelling report (`ml/reports/labeling.md`, P7.1): what was labelled, how the two labellers agree (Cohen's kappa)
and which records still wait for a resolution. Pure: the text is built from numbers, the use case writes it."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quancrypt_ml.domain.labels import RISK_CLASSES, Agreement

# Landis and Koch (1977) bands; the report names the band, it does not judge the data set by it.
_BANDS = ((0.81, "neredeyse tam"), (0.61, "önemli"), (0.41, "orta"), (0.21, "makul"), (0.0, "zayıf"))


@dataclass(frozen=True)
class LabelingStats:
    batch: str
    size: int
    double_size: int
    first: Mapping[str, str]  # finding_id -> label
    second: Mapping[str, str]
    resolved: Mapping[str, str]
    agreement: Agreement | None
    unmatched: int  # labelled findings the warehouse no longer has (a re-run of the corpus pipeline changed them)


def band(kappa: float) -> str:
    for lower, name in _BANDS:
        if kappa >= lower:
            return name
    return "şanstan kötü"


def _distribution(labels: Mapping[str, str]) -> str:
    counts = Counter(labels.values())
    return " | ".join(f"{counts[c]}" for c in RISK_CLASSES)


def _confusion(first: Mapping[str, str], second: Mapping[str, str]) -> list[str]:
    common = set(first) & set(second)
    counts = Counter((first[f], second[f]) for f in common)
    rows = ["| 1. \\ 2. | " + " | ".join(RISK_CLASSES) + " |", "|---|" + "---|" * len(RISK_CLASSES)]
    rows += [f"| {a} | " + " | ".join(str(counts[(a, b)]) for b in RISK_CLASSES) + " |" for a in RISK_CLASSES]
    return rows


def build_report(stats: LabelingStats) -> str:
    lines = [
        f"# Etiketleme raporu: {stats.batch}",
        "",
        "Bu dosya `ml label-import` ve `ml label-resolve` ile her çalıştırmada yeniden yazılır (P7.1, D-25).",
        "",
        "## Parti",
        "",
        f"- Örneklem: {stats.size} bulgu, {stats.double_size} tanesi çift etiketleme için işaretli.",
        f"- 1. etiketleme (FIRST): {len(stats.first)} etiket; 2. etiketleme (SECOND): {len(stats.second)} etiket.",
        f"- Çözülen uyuşmazlık: {len(stats.resolved)}.",
        f"- Warehouse'ta artık bulunmayan etiketli bulgu: {stats.unmatched}.",
        "",
        "## Sınıf dağılımı",
        "",
        "| Etiketleme | " + " | ".join(RISK_CLASSES) + " |",
        "|---|" + "---|" * len(RISK_CLASSES),
        "| 1. | " + _distribution(stats.first) + " |",
        "| 2. | " + _distribution(stats.second) + " |",
        "",
        "## Uyum (Cohen kappa)",
        "",
        "2. etiketleme aynı kişinin, ilk etiketlere bakmadan yaptığı tekrardır (D-325):",
        "kappa kişi içi tutarlılığı ölçer, kişiler arası uyumu ölçmez.",
        "",
    ]
    if stats.agreement is None:
        lines.append("İki etiketlemenin ortak kaydı yok; kappa hesaplanmadı.")
    else:
        a = stats.agreement
        lines += [
            f"- Ortak kayıt: {a.pairs}",
            f"- Gözlenen uyum: {a.observed:.4f}",
            f"- Cohen kappa: {a.kappa:.4f} (Landis ve Koch bandı: {band(a.kappa)})",
            "",
            *_confusion(stats.first, stats.second),
            "",
            "## Uyuşmazlıklar",
            "",
        ]
        if a.disagreements:
            lines += ["| finding_id | 1. | 2. | Çözüm |", "|---|---|---|---|"]
            lines += [f"| `{f}` | {x} | {y} | {stats.resolved.get(f, 'bekliyor')} |" for f, x, y in a.disagreements]
        else:
            lines.append("Uyuşmazlık yok.")
    return "\n".join(lines) + "\n"


def disagreement_rows(agreement: Agreement, resolved: Mapping[str, str]) -> Sequence[Mapping[str, str]]:
    """The rows of the resolution CSV: one per disagreement, the resolution columns empty unless already resolved."""
    return [
        {
            "finding_id": f,
            "first_label": x,
            "second_label": y,
            "label": resolved.get(f, ""),
            "resolved_by": "",
            "notes": "",
        }
        for f, x, y in agreement.disagreements
    ]
