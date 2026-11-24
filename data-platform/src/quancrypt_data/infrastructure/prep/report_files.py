"""`PrepReportWriter` (P6.4): `reports/preprocessing_report.md` and `reports/figures/prep_funnel.png` (matplotlib
`Figure`, no pyplot). The report holds counts, codes and rule names only: no path, no project key, no value of a record
(data-preprocessing section 4)."""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path

from matplotlib.figure import Figure

from quancrypt_data.domain.corpus import CORPUS_MINIMUM, CORPUS_TARGET
from quancrypt_data.domain.prep_report import FINDINGS_TARGET, QUARANTINE_WARNING, PreprocessReport
from quancrypt_data.port.outbound.prep import TableStat

REPORT_FILE = "preprocessing_report.md"
FUNNEL_FILE = "prep_funnel.png"


def _yes(flag: bool) -> str:
    return "evet" if flag else "HAYIR"


class FilePrepReportWriter:
    def __init__(self, reports_dir: Path) -> None:
        self._dir = reports_dir

    def write(self, report: PreprocessReport, stats: Sequence[TableStat]) -> Sequence[str]:
        figures = self._dir / "figures"
        figures.mkdir(parents=True, exist_ok=True)
        funnel = figures / FUNNEL_FILE
        self._funnel(report, funnel)
        markdown = self._dir / REPORT_FILE
        markdown.write_text(self._markdown(report, stats), encoding="utf-8", newline="\n")
        return [str(markdown), str(funnel)]

    @staticmethod
    def _funnel(report: PreprocessReport, path: Path) -> None:
        figure = Figure(figsize=(8, 4.5))
        axes = figure.subplots()
        labels = ["raw", *(c.filter_code for c in report.counts)]
        values = [report.rows_in, *(c.rows_out for c in report.counts)]
        axes.barh(labels[::-1], values[::-1], color="#0072B2")
        for y, value in enumerate(values[::-1]):
            axes.text(value, y, f" {value}", va="center")
        axes.set_xlabel("Satır")
        axes.set_title("Ön işleme hunisi (filtre sonrası kalan satır)")
        figure.tight_layout()
        figure.savefig(path, dpi=110)

    @staticmethod
    def _markdown(report: PreprocessReport, stats: Sequence[TableStat]) -> str:
        out = io.StringIO()
        w = out.write
        w("# Ön işleme raporu (prep)\n\n")
        w(f"Üretildi: {report.generated_at.isoformat(timespec='seconds')}. Kurallar: D-308, D-309, D-310.\n\n")
        w("## 1. Filtre hunisi\n\n")
        w("| Filtre | Giren | Çıkan | Karantina | Atılan | Not |\n|---|---|---|---|---|---|\n")
        for c in report.counts:
            notes = ", ".join(f"{k}: {v}" for k, v in sorted(c.notes.items())) or "—"
            w(f"| {c.filter_code} | {c.rows_in} | {c.rows_out} | {c.rows_rejected} | {c.rows_dropped} | {notes} |\n")
        w(f"\nHuni tutarlı (her filtrenin çıkanı bir sonrakinin gireni): {_yes(report.funnel_consistent)}. ")
        w("Atılan: karantinaya yazılmadan çıkarılan satır (tekrar, üretilmiş kod).\n\n")
        w(f"![Ön işleme hunisi](figures/{FUNNEL_FILE})\n\n")
        w("## 2. Kanonikleştirme öncesi ve sonrası farklı değer sayısı\n\n| Kolon | raw | prep |\n|---|---|---|\n")
        for column, (before, after) in report.distinct.items():
            w(f"| {column} | {before} | {'— (prep tutmaz, D-310c)' if after is None else after} |\n")
        w("\n## 3. Karantina\n\n")
        w(
            f"{report.rows_in} satırın {report.rows_rejected} tanesi karantinaya ayrıldı "
            f"(%{report.quarantine_rate * 100:.1f}; eşik %{QUARANTINE_WARNING * 100:.0f}, D-310d).\n\n"
        )
        if report.quarantine_warning:
            w("**UYARI: karantina oranı eşiği aşıyor; G-PREP'ten önce kullanıcıya sorulur.**\n\n")
        if report.rejections:
            w("| Filtre ve neden | Kayıt |\n|---|---|\n")
            for reason, n in sorted(report.rejections.items()):
                w(f"| {reason} | {n} |\n")
        else:
            w("Karantinaya ayrılan kayıt yok.\n")
        w(
            "\nKaydın kendisi raw'da kalır; `quarantine.prep_record` yalnız olay kimliğini, filtreyi ve nedeni "
            "tutar.\n\n"
        )
        w("## 4. Sızıntı kontrolü (H6)\n\n")
        w("prep'e yazılan tüm metin değerleri geri okundu; redaksiyon kuralları (e-posta, token, özel anahtar, yüksek ")
        w("entropi), adres (`://`) ve mutlak yol arandı.\n\n")
        if report.leak_free:
            w("Sonuç: **0 eşleşme**.\n\n")
        else:
            w("| Kural | Eşleşme |\n|---|---|\n")
            for rule, n in sorted(report.leaks.items()):
                w(f"| {rule} | {n} |\n")
            w("\n**Sızıntı sıfır değil: prep onaylanamaz.**\n\n")
        w("## 5. prep tabloları\n\n| Tablo | Satır | Null oranı (sıfır olmayanlar) |\n|---|---|---|\n")
        for s in stats:
            nulls = ", ".join(f"{c} %{r * 100:.1f}" for c, r in s.null_ratios.items() if r) or "—"
            w(f"| {s.table} | {s.rows} | {nulls} |\n")
        w("\n## 6. Hedef kontrolü\n\n| Ölçüt | Hedef | Değer | Karşılandı |\n|---|---|---|---|\n")
        w(
            f"| Korpus projesi | en az {CORPUS_MINIMUM} (D-306; hedef {CORPUS_TARGET}) | {report.corpus_projects} | "
            f"{_yes(report.projects_target_met)} |\n"
        )
        w(f"| Bulgu (H5) | en az {FINDINGS_TARGET} | {report.findings} | {_yes(report.findings_target_met)} |\n")
        origins = ", ".join(f"{o}: {n}" for o, n in sorted(report.projects_by_origin.items())) or "—"
        w(f"\nProjeler kökene göre: {origins}.\n")
        if not report.findings_target_met:
            w(
                "\n**Bulgu:** H5 hedefi karşılanmıyor. Korpus 40 projede kaldı (D-306) ve projelerin çoğunda az kripto "
                "kullanımı var; G-PREP onayında karara bağlanır.\n"
            )
        return out.getvalue()
