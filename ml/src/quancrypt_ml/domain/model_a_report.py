"""The Model A report (`ml/reports/model_a.md`) and model card (`ml/model_cards/risk_model-v1.md`), built from the
numbers of one training run (P7.2). Pure: every number in the text comes from the run, nothing is written by hand
(ml-pipeline §1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.metrics import CRITICAL, Evaluation, RunAgreement

H3_MACRO_F1 = 0.80


@dataclass(frozen=True)
class CvSummary:
    algorithm: str
    mean_macro_f1: float
    std_macro_f1: float
    mean_critical_recall: float
    params: Mapping[str, object]


@dataclass(frozen=True)
class ClassifierCost:
    name: str
    evaluation: Evaluation
    macro_f1_interval: tuple[float, float]
    critical_recall_interval: tuple[float, float]
    seconds_per_finding: float | None
    tokens_per_finding: float | None
    consistency: RunAgreement | None
    invalid_answers: int


@dataclass(frozen=True)
class ModelAFacts:
    label_source: str
    version: str
    total_rows: int
    labelled_rows: int
    train_rows: int
    test_rows: int
    train_projects: int
    test_projects: int
    test_class_counts: Mapping[str, int]
    cv: Sequence[CvSummary]
    selected: str
    selected_params: Mapping[str, object]
    model: ClassifierCost
    rule: ClassifierCost
    llm: ClassifierCost | None
    llm_model: str | None
    llm_prompt: str | None
    parity_rows: int
    parity_classes_equal: bool
    parity_max_difference: float
    top_features: Sequence[tuple[str, float]]


def h3(facts: ModelAFacts) -> bool | None:
    """H3 (D-327): macro-F1 >= 0.80 on the gold test set and better than the rule baseline. Not judged on a dry run."""
    if facts.label_source != "GOLD":
        return None
    return (
        facts.model.evaluation.macro_f1 >= H3_MACRO_F1
        and facts.model.evaluation.macro_f1 > facts.rule.evaluation.macro_f1
    )


def _f(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _interval(pair: tuple[float, float]) -> str:
    return f"[{pair[0]:.3f}, {pair[1]:.3f}]"


def _classifier_rows(costs: Sequence[ClassifierCost]) -> list[str]:
    rows = [
        "| Sınıflandırıcı | Macro-F1 (%95 GA) | Kritik recall (%95 GA) | Doğruluk | Geçersiz yanıt | Bulgu başına süre (sn) | Bulgu başına token | Tekrar tutarlılığı |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in costs:
        e = c.evaluation
        consistency = "—" if c.consistency is None else f"%{100 * c.consistency.identical:.1f} aynı"
        rows.append(
            f"| {c.name} | {e.macro_f1:.3f} {_interval(c.macro_f1_interval)} | {e.recall(CRITICAL):.3f} "
            f"{_interval(c.critical_recall_interval)} | {e.accuracy:.3f} | {c.invalid_answers} | "
            f"{_f(c.seconds_per_finding, 4)} | {_f(c.tokens_per_finding, 1)} | {consistency} |"
        )
    return rows


def _per_class(e: Evaluation) -> list[str]:
    rows = ["| Sınıf | Precision | Recall | F1 | Destek |", "|---|---|---|---|---|"]
    rows += [f"| {c.label} | {c.precision:.3f} | {c.recall:.3f} | {c.f1:.3f} | {c.support} |" for c in e.per_class]
    return rows


def _confusion(e: Evaluation) -> list[str]:
    rows = ["| Gerçek \\ Tahmin | " + " | ".join(RISK_CLASSES) + " |", "|---|" + "---|" * len(RISK_CLASSES)]
    rows += [
        f"| {t} | " + " | ".join(str(n) for n in line) + " |" for t, line in zip(RISK_CLASSES, e.confusion, strict=True)
    ]
    return rows


def _rq2(facts: ModelAFacts) -> list[str]:
    if facts.llm is None:
        return ["LLM karşılaştırması bu koşuda yapılmadı (`--no-llm`); araştırma sorusu 2 yanıtlanmadı."]
    m, llm = facts.model, facts.llm
    lines = [
        f"- Doğruluk: klasik model macro-F1 {m.evaluation.macro_f1:.3f}, LLM {llm.evaluation.macro_f1:.3f}.",
    ]
    if llm.consistency is not None:
        kappa = "—" if llm.consistency.kappa is None else f"{llm.consistency.kappa:.3f}"
        lines.append(
            f"- Tutarlılık: aynı {llm.consistency.n} bulgu iki kez soruldu; LLM yanıtlarının %"
            f"{100 * llm.consistency.identical:.1f}'i aynı (kappa {kappa}). Klasik model aynı girdiye her zaman aynı "
            "yanıtı verir (deterministik, tohum 42)."
        )
    if llm.seconds_per_finding is not None and m.seconds_per_finding:
        ratio = llm.seconds_per_finding / m.seconds_per_finding
        lines.append(
            f"- Süre: LLM bulgu başına {llm.seconds_per_finding:.3f} sn, klasik model {m.seconds_per_finding:.6f} sn "
            f"(yaklaşık {ratio:,.0f} kat). Token: LLM bulgu başına {_f(llm.tokens_per_finding, 1)}, model 0."
        )
    lines.append(f"- Geçersiz yanıt: LLM {llm.invalid_answers} bulguda dört sınıftan birini vermedi (yanlış sayıldı).")
    return lines


def build_report(facts: ModelAFacts) -> str:
    verdict = h3(facts)
    dry = facts.label_source != "GOLD"
    lines = [
        f"# Model A (risk) raporu: {facts.version}",
        "",
        "Bu dosya `ml train-risk` her çalıştığında yeniden yazılır (P7.2). Sayıların tamamı koşudan ve MLflow kaydından gelir.",
        "",
    ]
    if dry:
        lines += [
            "> **Deneme koşusu (gümüş etiket).** Eğitim ve test gümüş etiketle (kural tablosu) yapıldı; altın etiketler henüz "
            "içe aktarılmadı (D-327a). Bu koşu H3 için kullanılmaz ve ml_outputs'a yazılmaz.",
            "",
        ]
    lines += [
        "## Veri ve bölme",
        "",
        f"- Etiket kaynağı: {facts.label_source}. Mart'ta {facts.total_rows} bulgu, etiketli {facts.labelled_rows}.",
        f"- Eğitim: {facts.train_projects} proje, {facts.train_rows} bulgu. Test: {facts.test_projects} hiç görülmemiş "
        f"proje, {facts.test_rows} bulgu (StratifiedGroupKFold, tohum 42, D-327f; ayrıklık testle doğrulandı).",
        "- Test kümesindeki sınıf sayıları: "
        + ", ".join(f"{c} {facts.test_class_counts.get(c, 0)}" for c in RISK_CLASSES)
        + ".",
        "",
        "## Çapraz doğrulama (eğitim projeleri, GroupKFold 5)",
        "",
        "| Model | Macro-F1 ort. ± std | Kritik recall ort. | Seçilen parametreler (iç CV) |",
        "|---|---|---|---|",
    ]
    for c in facts.cv:
        params = ", ".join(f"{k}={v}" for k, v in sorted(c.params.items()))
        lines.append(
            f"| {c.algorithm} | {c.mean_macro_f1:.3f} ± {c.std_macro_f1:.3f} | {c.mean_critical_recall:.3f} | {params} |"
        )
    lines += [
        "",
        f"Seçilen model: **{facts.selected}** (en yüksek doğrulama macro-F1'i, eşitlikte Kritik recall; D-327e).",
        "",
        "## Test kümesi: model, kural baseline'ı ve LLM",
        "",
        *_classifier_rows([c for c in (facts.model, facts.rule, facts.llm) if c is not None]),
        "",
        "Güven aralıkları 1000 örnekli bootstrap'tir (tohum 42); test kümesi küçük olduğu için geniştir (D-313).",
        "",
        f"### {facts.selected}: sınıf bazında",
        "",
        *_per_class(facts.model.evaluation),
        "",
        *_confusion(facts.model.evaluation),
        "",
        "Kalibrasyon eğrisi: `calibration.png` (MLflow artifact'i).",
        "",
        "## H3",
        "",
    ]
    if verdict is None:
        lines.append("Ölçülmedi: deneme koşusu (gümüş etiket).")
    else:
        m, r = facts.model.evaluation.macro_f1, facts.rule.evaluation.macro_f1
        state = "TUTTU" if verdict else "TUTMADI"
        lines.append(f"**{state}.** Test macro-F1 {m:.3f} (hedef ≥ {H3_MACRO_F1:.2f}); kural baseline'ı {r:.3f}.")
        if not verdict:
            lines.append("H3'ün tutmaması bir bulgudur ve model kartına da yazılır.")
    lines += [
        "",
        "## Araştırma sorusu 2: klasik ML ile yerel LLM",
        "",
        *_rq2(facts),
        "",
        "## Açıklanabilirlik (SHAP)",
        "",
    ]
    lines.append(
        "En etkili 10 özellik: eğitim bulguları ve tüm sınıflar üzerinden ortalama |SHAP| (`shap_summary.png` aynı değerleri gösterir)."
    )
    lines.append("")
    lines += [f"- {name}: {value:.4f}" for name, value in facts.top_features]
    lines += [
        "",
        "Bulgu başına en etkili 3 özellik ml_outputs.risk_explanation'a yazılır (yalnız altın koşuda).",
        "",
        "## ONNX",
        "",
        f"- Parite ({facts.parity_rows} bulgu): sınıflar {'birebir aynı' if facts.parity_classes_equal else 'FARKLI'}, en "
        f"büyük olasılık farkı {facts.parity_max_difference:.2e} (eşik 1e-4).",
        "",
        "## Sınırlamalar",
        "",
        "- Korpus 40 proje ve 330 bulgudur (H5 karşılanmadı, D-313); test kümesi birkaç projedir, Kritik ve Orta sınıflarında "
        "örnek azdır ve metrikler geniş güven aralıklıdır.",
        "- LLM yalnız bulgunun kanonik alanlarını görür (modelle aynı bilgi, kod bağlamı yok).",
    ]
    return "\n".join(lines) + "\n"


def build_model_card(facts: ModelAFacts) -> str:
    verdict = h3(facts)
    e = facts.model.evaluation
    return "\n".join([
        f"# Model kartı: risk_model-{facts.version}",
        "",
        "## Amaç",
        "Quancrypt'in bulduğu bir kripto kullanımını geçiş riskine göre CRITICAL, HIGH, MEDIUM veya LOW olarak sınıflandırmak "
        "(Model A). Planlama agent'ı sıralama ve gerekçe için kullanır (P7.5).",
        "",
        "## Veri",
        f"- Kaynak: `marts.mart_risk_features` (korpus, D-317h). Etiket: {facts.label_source}"
        + (" (altın etiket: kullanıcının kılavuza göre etiketlemesi, D-326)." if facts.label_source == "GOLD" else " (deneme)."),
        f"- Eğitim {facts.train_rows} bulgu / {facts.train_projects} proje; test {facts.test_rows} bulgu / "
        f"{facts.test_projects} hiç görülmemiş proje.",
        "",
        "## Model",
        f"- Algoritma: {facts.selected}; parametreler: "
        + ", ".join(f"{k}={v}" for k, v in sorted(facts.selected_params.items())) + ".",
        "- Ön işleme: log1p + StandardScaler (sayımlar, anahtar boyutu), MinMaxScaler (güven, Java ana sürümü), one-hot "
        "(kategoriler), bayraklar; eksik değer doldurulmaz, bayrakla belirtilir.",
        "- Çıktı: `risk_class` en olası sınıftır; `risk_score` sınıf olasılıklarıyla ağırlıklı beklenen skordur "
        "(CRITICAL 0,90, HIGH 0,70, MEDIUM 0,475, LOW 0,175). Kalibre bir olasılık değildir; ender durumda D-128 "
        "eşikleriyle `risk_class`'tan farklı bir sınıfa düşebilir (D-330a).",
        "",
        "## Metrikler (test)",
        f"- Macro-F1 {e.macro_f1:.3f} {_interval(facts.model.macro_f1_interval)}; Kritik recall {e.recall(CRITICAL):.3f} "
        f"{_interval(facts.model.critical_recall_interval)}; kural baseline'ı macro-F1 {facts.rule.evaluation.macro_f1:.3f}.",
        f"- H3: {'ölçülmedi (deneme)' if verdict is None else ('tuttu' if verdict else 'tutmadı')}.",
        "",
        "## Sınırlamalar",
        "- Az veri: 40 proje, 330 bulgu; güven aralıkları geniştir.",
        "- Model yalnız analizcinin kanonik alanlarını görür; kodun iş bağlamını bilmez.",
        "- Gümüş etiket kuralının ağ yolu yaklaşımı (TLS anahtar değişimi, D-323h) baseline'ı etkiler.",
        "",
        "## Çıkarım (agent-service, P7.5)",
        "- core-service'in bulgu API'si `mode`, `padding`, `hash` ve `library` alanlarını taşımaz; çıkarımda bu dört "
        "özellik eğitimdeki eksik değer olan `~MISSING`, `is_outlier_project` 0 olur (D-343b). Eğitim ile çıkarım "
        "arasındaki bu fark tahminleri kaydırabilir; etkisi ölçülmedi.",
        "- Çıkarımdaki gerekçe SHAP değildir: her özellik tek tek bilinmeyen değeriyle değiştirilir ve tahmin edilen "
        "sınıfın olasılığındaki düşüş ölçülür (oklüzyon); en etkili 3 özellik plana gerekçe olarak girer (D-343c). "
        "SHAP değerleri yalnız eğitim raporunda ve `ml_outputs.risk_explanation`'dadır.",
        "",
        "## Adalet ve kapsam notları",
        "- Model kişisel veri işlemez; girdiler kodlu kripto alanlarıdır. Proje anahtarı özellik değildir.",
        "",
        "## Kullanım dışı durumlar",
        "- Java ve Spring Boot dışındaki projeler; analizcinin tanımadığı kütüphaneler; insan incelemesi olmadan geçiş "
        "kararı vermek.",
        "",
        "## ONNX",
        f"- `models/risk_model-{facts.version}.onnx`; parite: sınıflar "
        f"{'aynı' if facts.parity_classes_equal else 'farklı'}, en büyük olasılık farkı {facts.parity_max_difference:.2e}.",
        "",
    ])  # fmt: skip
