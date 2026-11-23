"""`ProfileReportWriter` (P6.3): `reports/profiling_report.md`, `reports/figures/*.png` (matplotlib `Figure` objects
saved straight to PNG: no pyplot, no window, no global figure state) and `reports/unmapped_values.csv`.

The report shows counts, codes and crypto spellings only. File paths, quarantined records and project keys in full are
not written: a project appears by the first twelve digits of its key. A spelling is shown only when the redaction
rules find nothing in it.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Callable, Sequence
from pathlib import Path

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from quancrypt_data.domain.profiling_report import SPELLING_FIELDS, ProfileReport

UNMAPPED_COLUMNS = ("kind", "raw", "frequency", "projects")
TOP_SPELLINGS = 20


def _fmt(value: float | None) -> str:
    """Whole numbers in full (a 1024-bit key reads 1024), other numbers to four significant digits."""
    if value is None:
        return "—"
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.4g}"


def _code(text: str) -> str:
    """A spelling in a code span: a backtick would close the span, so it becomes a quote."""
    return "`" + text.replace("|", "\\|").replace("\n", " ").replace("`", "'") + "`"


def _label(text: str) -> str:
    """A chart label: matplotlib reads text between two `$` as mathtext, which can fail on a crafted spelling."""
    return text.replace("$", r"\$")


def _csv_cell(text: str) -> str:
    """A cell a spreadsheet would read as a formula (`=`, `+`, `-`, `@` first) is kept as text."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _cell(text: str) -> str:
    """A table cell: a pipe would split it and a tag would be HTML to a renderer that allows it."""
    return text.replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")


class FileProfileReportWriter:
    def __init__(self, reports_dir: Path, is_clean: Callable[[str], bool]) -> None:
        """`is_clean` says whether a spelling may be shown (the redaction rules find nothing in it)."""
        self._dir = reports_dir
        self._is_clean = is_clean

    def write(self, report: ProfileReport) -> Sequence[str]:
        figures = self._dir / "figures"
        figures.mkdir(parents=True, exist_ok=True)
        written = [
            self._histogram(report, figures / "findings_per_project.png"),
            self._bars(
                [f"{s.event_type}" for s in report.sources], [s.count for s in report.sources],
                "Kaynak bazında kayıt sayısı", figures / "records_per_source.png",
            ),
            self._bars(
                list(report.quarantine_reasons), list(report.quarantine_reasons.values()),
                "Karantina nedenleri", figures / "quarantine_reasons.png",
            ),
            self._bars(
                *self._top_spellings(report, "raw_name"), "En sık ham adlar (raw_name)",
                figures / "raw_name_variety.png",
            ),
        ]  # fmt: skip
        csv_path = self._dir / "unmapped_values.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(UNMAPPED_COLUMNS)
            for value in report.unmapped:
                raw = value.raw if self._is_clean(value.raw) else "[gizlendi: redaksiyon kuralı eşleşti]"
                writer.writerow((value.kind, _csv_cell(raw), value.frequency, value.projects))
        markdown = self._dir / "profiling_report.md"
        markdown.write_text(self._markdown(report), encoding="utf-8", newline="\n")
        return [str(markdown), str(csv_path), *written]

    def _top_spellings(self, report: ProfileReport, name: str) -> tuple[list[str], list[int]]:
        top = [(s, n) for s, n in report.spellings.get(name, []) if self._is_clean(s)][:TOP_SPELLINGS]
        return [s for s, _ in top], [n for _, n in top]

    @staticmethod
    def _empty(axes: Axes) -> None:
        axes.text(0.5, 0.5, "veri yok", ha="center", va="center", transform=axes.transAxes)
        axes.set_xticks([])
        axes.set_yticks([])

    def _histogram(self, report: ProfileReport, path: Path) -> str:
        figure = Figure(figsize=(7, 4))
        axes = figure.subplots()
        counts = sorted(report.per_project.values())
        if counts:
            top = max(counts)
            edges = [10 ** (i / 4) for i in range(int(math.log10(max(top, 1)) * 4) + 2)]
            axes.hist(counts, bins=edges, color="#0072B2")
            axes.set_xscale("log")
            axes.set_yscale("log")
            if report.outliers.threshold is not None:
                axes.axvline(report.outliers.threshold, color="#D55E00", linestyle="--", label="Q3 + 3×IQR")
                axes.legend()
            axes.set_xlabel("Proje başına bulgu (log)")
            axes.set_ylabel("Proje sayısı (log)")
        else:
            self._empty(axes)
        axes.set_title("Proje başına bulgu dağılımı")
        figure.tight_layout()
        figure.savefig(path, dpi=110)
        return str(path)

    def _bars(self, labels: list[str], values: list[int], title: str, path: Path) -> str:
        figure = Figure(figsize=(7, max(2.5, 0.3 * len(labels) + 1)))
        axes = figure.subplots()
        if labels:
            axes.barh([_label(label) for label in labels[::-1]], values[::-1], color="#009E73")
            axes.set_xlabel("Kayıt")
        else:
            self._empty(axes)
        axes.set_title(title)
        figure.tight_layout()
        figure.savefig(path, dpi=110)
        return str(path)

    def _markdown(self, report: ProfileReport) -> str:
        out = io.StringIO()
        w = out.write
        stamp = report.generated_at.isoformat(timespec="seconds")
        w("# Veri profilleme raporu (raw)\n\n")
        w(f"Üretildi: {stamp}. Rapor raw'u yalnız okuyarak üretildi (READ ONLY transaction; D-302c).\n\n")
        w("## 1. Kaynaklar ve zaman aralığı\n\n")
        if report.sources:
            w("| Kaynak | Olay türü | Kayıt | İlk | Son | Şema sürümleri |\n|---|---|---|---|---|---|\n")
            for s in report.sources:
                first = s.first_at.isoformat(timespec="seconds") if s.first_at else "—"
                last = s.last_at.isoformat(timespec="seconds") if s.last_at else "—"
                versions = ", ".join(str(v) for v in s.schema_versions)
                w(f"| {s.source} | {s.event_type} | {s.count} | {first} | {last} | {versions} |\n")
        else:
            w("raw.event boş.\n")
        w("\n![Kaynak bazında kayıt sayısı](figures/records_per_source.png)\n\n")
        w("## 2. Kolon profilleri\n\n")
        w("| Tablo | Kolon | Tip | Kayıt | Null oranı | Farklı | Min | Max | Ortalama | Medyan | Çarpıklık |\n")
        w("|---|---|---|---|---|---|---|---|---|---|---|\n")
        for c in report.columns:
            w(
                f"| {c.table} | {c.column} | {c.kind} | {c.count} | {c.null_ratio:.1%} | {c.distinct} | "
                f"{_fmt(c.minimum)} | "
                f"{_fmt(c.maximum)} | {_fmt(c.mean)} | {_fmt(c.median)} | {_fmt(c.skewness)} |\n"
            )
        w("\n## 3. Ham yazım çeşitliliği\n\n")
        w(
            "Analizcinin `mode`, `padding` ve `hash` değerleri zaten sözlük değerleridir (D-192a); "
            "`raw_name` koddaki ham addır.\n\n"
        )
        for name in SPELLING_FIELDS:
            spellings = report.spellings.get(name, [])
            clean = [(s, n) for s, n in spellings if self._is_clean(s)]
            hidden = len(spellings) - len(clean)
            w(f"### `{name}`: {len(spellings)} farklı yazım" + (f" ({hidden} gizlendi)" if hidden else "") + "\n\n")
            if clean:
                w("| Yazım | Frekans |\n|---|---|\n")
                for value, count in clean[:TOP_SPELLINGS]:
                    w(f"| {_code(value)} | {count} |\n")
                if len(clean) > TOP_SPELLINGS:
                    w(f"| … ({len(clean) - TOP_SPELLINGS} yazım daha) | |\n")
            else:
                w("Veri yok.\n")
            w("\n")
        w("![En sık ham adlar](figures/raw_name_variety.png)\n\n")
        w("## 4. Tekrarlar\n\n")
        w(
            f"Aynı proje, dosya, satır, algoritma ve kullanım bağlamında {report.duplicates.groups} tekrar grubu, "
            f"{report.duplicates.extra_rows} fazla satır.\n\n"
        )
        w("## 5. Proje başına bulgu dağılımı ve aykırı adaylar\n\n")
        counts = sorted(report.per_project.values())
        if counts:
            w(
                f"Raw'daki {report.projects_in_raw} projenin {len(counts)} tanesinde bulgu var; en az {counts[0]}, "
                f"en çok {counts[-1]}, toplam {sum(counts)} bulgu. Aykırı aday hesabı yalnız bulgusu olan projelere "
                "bakar (D-309).\n\n"
            )
        else:
            w("Bulgu yok.\n\n")
        if report.outliers.threshold is None:
            w("Aykırı aday hesabı için en az 4 proje gerekir.\n\n")
        else:
            w(f"Eşik (Q3 + 3×IQR): {report.outliers.threshold:.1f} bulgu.\n\n")
            for key, n in report.outliers.outliers:
                w(f"- `{key[:12]}…`: {n} bulgu\n")
            if not report.outliers.outliers:
                w("Eşiği aşan proje yok.\n")
            w("\n")
        classes = (
            ", ".join(f"{name}: {n}" for name, n in sorted(report.path_classes.items())) or "yol taşıyan bulgu yok"
        )
        w(f"Yol sınıfları: {classes}.\n\n")
        w("![Proje başına bulgu dağılımı](figures/findings_per_project.png)\n\n")
        w("## 6. Şema ihlalleri (quarantine.event)\n\n")
        if report.quarantine_reasons:
            w("| Neden | Kayıt |\n|---|---|\n")
            for code, n in sorted(report.quarantine_reasons.items()):
                w(f"| {code} | {n} |\n")
            w("\n| İleti | Kayıt |\n|---|---|\n")
            for message, n in report.quarantine_messages[:TOP_SPELLINGS]:
                w(f"| {_cell(message)} | {n} |\n")
        else:
            w("Karantinada kayıt yok.\n")
        w("\n![Karantina nedenleri](figures/quarantine_reasons.png)\n\n")
        w("## 7. Kişisel veri ve sır taraması\n\n")
        w(f"`contracts/redaction-rules.yaml` kuralları {report.scanned_texts} metin değerine uygulandı "
          "(bulgu yolları ve ham adları, karantina kayıtları). Yalnız eşleşme sayıları yazılır.\n\n")  # fmt: skip
        if report.secret_hits:
            w("| Kural | Eşleşme |\n|---|---|\n")
            for rule, n in sorted(report.secret_hits.items()):
                w(f"| {rule} | {n} |\n")
        else:
            w("Eşleşme yok.\n")
        w("\n## 8. Öneriler\n\n")
        if report.recommendations:
            w("| No | Filtre | Öneri | Kanıt |\n|---|---|---|---|\n")
            for r in report.recommendations:
                w(f"| {r.number} | {r.filter} | {_cell(r.text)} | {_cell(r.evidence)} |\n")
        else:
            w("Kanıtı olan öneri yok.\n")
        w("\nÖneriler kullanıcı onayıyla P6.4'ün kural listesine girer (DECISIONS.md).\n\n")
        w("## Ek: raw değişmedi mi?\n\n| Tablo | Satır (önce) | Satır (sonra) | Özet eşit |\n|---|---|---|---|\n")
        after = {check.table: check for check in report.after}
        for check in report.before:
            later = after.get(check.table)
            same = later is not None and later == check
            w(f"| {check.table} | {check.rows} | {later.rows if later else '—'} | {'evet' if same else 'HAYIR'} |\n")
        w(
            "\nSonuç: "
            + ("raw değişmedi" if report.unchanged else "raw profilleme sırasında DEĞİŞTİ (başka bir yazıcı vardı)")
            + ".\n"
        )
        return out.getvalue()
