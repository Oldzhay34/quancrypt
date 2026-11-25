"""The report of Model B (`ml/reports/model_b.md`) and its model card (P7.3, H4). Every number comes from one run of
TrainScopeClassifier (ml-pipeline section 1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quancrypt_ml.domain.scope_model import (
    ALL,
    BOUNDARY,
    EN,
    JAILBREAK,
    MAX_FALSE_REJECT_RATE,
    SLICES,
    TARGET_RECALL,
    TR,
    Band,
    BinaryScore,
    ThreeWay,
    h4_met,
)

SLICE_NAMES = {ALL: "Tümü", TR: "Türkçe", EN: "İngilizce", JAILBREAK: "Jailbreak", BOUNDARY: "Sınır durumu"}


@dataclass(frozen=True)
class AlgorithmSummary:
    algorithm: str
    params: Mapping[str, object]
    cv_auc_mean: float
    cv_auc_std: float
    threshold: float  # chosen on the validation set
    validation: BinaryScore
    validation_auc: float | None


@dataclass(frozen=True)
class ModelBFacts:
    version: str
    embedding_model: str
    embedding_digest: str
    dimensions: int
    counts: Mapping[str, Mapping[str, int]]  # split -> {OUT_OF_SCOPE, IN_SCOPE, tr, en, jailbreak}
    algorithms: Sequence[AlgorithmSummary]
    selected: str
    band: Band
    validation: Mapping[str, BinaryScore]
    validation_three_way: ThreeWay
    test: Mapping[str, BinaryScore]
    test_three_way: ThreeWay
    test_auc: float | None
    parity_classes_equal: bool
    parity_max_difference: float
    onnx_file: str
    thresholds_file: str


def h4(facts: ModelBFacts) -> bool:
    return h4_met(facts.test[ALL])


def _pct(value: float | None) -> str:
    return "-" if value is None else f"%{100 * value:.1f}"


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _score_rows(scores: Mapping[str, BinaryScore]) -> list[str]:
    rows = [
        "| Dilim | Kapsam dışı | Yakalanan | Recall | Kapsam içi | Yanlış ret | Yanlış ret oranı |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in SLICES:
        s = scores[name]
        rows.append(
            f"| {SLICE_NAMES[name]} | {s.out_of_scope} | {s.caught} | {_pct(s.recall)} | {s.in_scope} | "
            f"{s.false_rejects} | {_pct(s.false_reject_rate)} |"
        )
    return rows


def _three_way_rows(t: ThreeWay) -> list[str]:
    return [
        "| Gerçek sınıf | ALLOW | UNSURE (3. halka) | DENY |",
        "|---|---|---|---|",
        f"| Kapsam dışı | {t.allowed_out} | {t.unsure_out} | {t.denied_out} |",
        f"| Kapsam içi | {t.allowed_in} | {t.unsure_in} | {t.denied_in} |",
        "",
        f"UNSURE oranı {_pct(t.unsure_rate)}. 2. halkanın kendisinin ALLOW dediği kapsam dışı istek: {t.allowed_out}.",
    ]


def _counts(facts: ModelBFacts) -> list[str]:
    rows = ["| Küme | Kapsam dışı | Kapsam içi | TR | EN | Jailbreak |", "|---|---|---|---|---|---|"]
    for split in ("train", "val", "test"):
        c = facts.counts[split]
        rows.append(f"| {split} | {c['OUT_OF_SCOPE']} | {c['IN_SCOPE']} | {c['tr']} | {c['en']} | {c['jailbreak']} |")
    return rows


def build_report(facts: ModelBFacts) -> str:
    test = facts.test[ALL]
    met = h4(facts)
    lines = [
        f"# Model B: kapsam sınıflandırıcısı (scope_classifier-{facts.version})",
        "",
        "Kapsam bekçisinin 2. halkası (guardrails-security §2). Pozitif sınıf OUT_OF_SCOPE'tur: isteğin kapsam dışı "
        "olasılığı eşiğe eşit veya büyükse istek reddedilir. Veri onaylı kapsam setidir (D-326); bölme parafraz "
        "grubuna göredir (D-323i). Eşik ve UNSURE bandı yalnız doğrulama kümesinde seçildi; test kümesi bir kez, "
        "seçilen modelle kullanıldı (D-332, D-333).",
        "",
        "## Veri",
        "",
        *_counts(facts),
        "",
        f"Gömme: `{facts.embedding_model}` (Ollama özeti `{facts.embedding_digest}`), {facts.dimensions} boyut, "
        "agent-service ile aynı istek ve ham metin (D-14, D-333a).",
        "",
        "## Modeller (eğitim kümesinde iç StratifiedGroupKFold, doğrulamada eşik)",
        "",
        "| Algoritma | Parametreler | İç CV ROC AUC | Doğrulama ROC AUC | Eşik | Doğrulama recall | "
        "Doğrulama yanlış ret |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in facts.algorithms:
        params = ", ".join(f"{k}={v}" for k, v in sorted(a.params.items()))
        lines.append(
            f"| {a.algorithm} | {params} | {a.cv_auc_mean:.3f} ± {a.cv_auc_std:.3f} | {_num(a.validation_auc)} | "
            f"{a.threshold:.4f} | {_pct(a.validation.recall)} | {a.validation.false_rejects} "
            f"({_pct(a.validation.false_reject_rate)}) |"
        )
    lines += [
        "",
        f"Seçilen: **{facts.selected}**. Lojistik regresyon varsayılandır; kalibrasyonlu doğrusal SVM yalnız "
        "doğrulamada 1 kayıttan fazla daha az yanlış ret verirse seçilir (D-332b).",
        "",
        "## Eşik ve UNSURE bandı",
        "",
        f"- Eşik {facts.band.threshold:.4f}: doğrulamada kapsam dışı recall ≥ %{100 * TARGET_RECALL:.0f} olan "
        "eşikler içinde en az yanlış ret; eşitlikte daha düşük eşik.",
        f"- Alt sınır {facts.band.low:.4f}: altında ALLOW (doğrulamada hiçbir kapsam dışı istek bu bölgede değil).",
        f"- Üst sınır {facts.band.high:.4f}: üstünde DENY (doğrulamada hiçbir kapsam içi istek bu bölgede değil).",
        "- Aradaki istekler UNSURE'dur ve 3. halkaya (LLM öz-denetimi) gider (D-332c).",
        "",
        "## Doğrulama kümesi (seçilen model, eşikte)",
        "",
        *_score_rows(facts.validation),
        "",
        *_three_way_rows(facts.validation_three_way),
        "",
        "## Test kümesi (bir kez)",
        "",
        *_score_rows(facts.test),
        "",
        f"Test ROC AUC {_num(facts.test_auc)}.",
        "",
        "### Üç yollu karar (bantla)",
        "",
        *_three_way_rows(facts.test_three_way),
        "",
        "## ONNX",
        "",
        f"`{facts.onnx_file}`; eşikler `{facts.thresholds_file}`. Parite (test kümesi): sınıflar "
        f"{'aynı' if facts.parity_classes_equal else 'farklı'}, en büyük olasılık farkı "
        f"{facts.parity_max_difference:.2e}, bantla üç yollu kararlar aynı.",
        "",
        "## Baseline",
        "",
        "Yalnız kural filtresi (1. halka) baseline'ı ve 1 + 2 + 3. halkaların birlikte sonucu P7.5'te agent-service'te, "
        "aynı test kümesinde ölçülür (D-332d).",
        "",
        "## H4",
        "",
        f"Hedef: kapsam dışı recall ≥ %{100 * TARGET_RECALL:.0f} ve yanlış ret ≤ %{100 * MAX_FALSE_REJECT_RATE:.0f} "
        "(test kümesi, eşikte). Sonuç: recall "
        f"{_pct(test.recall)} ({test.caught}/{test.out_of_scope}), yanlış ret {_pct(test.false_reject_rate)} "
        f"({test.false_rejects}/{test.in_scope}). H4 **{'TUTTU' if met else 'TUTMADI'}.**",
    ]
    if not met and test.recall is not None and test.recall >= TARGET_RECALL:
        lines.append(
            "Recall koşulu sağlandı; yanlış ret sınırı aşıldı. Öncelik recall'dadır (D-332a); bu bir bulgudur."
        )
    lines += [
        "",
        "## Sınırlamalar",
        "",
        "- Set sentetik ve onaylıdır (D-326); gerçek kullanıcı isteklerinde sonuç düşebilir. P7.5 gerçek zincirle "
        "yeniden ölçer.",
        f"- Küçük kümeler: testte bir kapsam dışı kayıt recall'u %{100 / max(test.out_of_scope, 1):.1f} değiştirir.",
        f"- Jailbreak dilimi testte {facts.test[JAILBREAK].out_of_scope} kayıttır; doğrulamadaki "
        f"{facts.validation[JAILBREAK].out_of_scope} kayıtla birlikte okunmalıdır.",
        "- Eşik ve bant doğrulamada seçildi; doğrulama sonuçları iyimserdir, karar için test sonucu okunur.",
        "",
    ]
    return "\n".join(lines)


def build_model_card(facts: ModelBFacts) -> str:
    test = facts.test[ALL]
    return "\n".join([
        f"# Model kartı: scope_classifier-{facts.version}",
        "",
        "## Amaç",
        "Kapsam bekçisinin 2. halkası: kullanıcının isteğini kapsam içi (projenin kriptosu ve kuantum-güvenli geçiş) "
        "veya kapsam dışı diye ayırmak. Güvenli bölgelerde karar verir, aradaki istekleri 3. halkaya bırakır "
        "(guardrails-security §2; agent-service bağlantısı P7.5).",
        "",
        "## Veri",
        f"- Onaylı kapsam seti (D-326): {sum(c['OUT_OF_SCOPE'] + c['IN_SCOPE'] for c in facts.counts.values())} "
        "kayıt, TR ve EN, parafraz grubuna göre bölünmüş (D-323i).",
        "- Etiket kaynağı `SCOPE_SET`.",
        "",
        "## Model",
        f"- Gömme modeli: `{facts.embedding_model}`, Ollama özeti `{facts.embedding_digest}`, {facts.dimensions} boyut. "
        "Çıkarımda aynı model ve aynı istekle gömülmelidir; özet değişirse model yeniden eğitilir.",
        f"- Sınıflandırıcı başı: {facts.selected} (StandardScaler + sınıflandırıcı); ONNX yalnız bu başı içerir.",
        f"- Eşik {facts.band.threshold:.4f}; UNSURE bandı [{facts.band.low:.4f}, {facts.band.high:.4f}); "
        f"`{facts.thresholds_file}`.",
        "",
        "## Metrikler (test)",
        f"- Kapsam dışı recall {_pct(test.recall)}, yanlış ret {_pct(test.false_reject_rate)}; "
        f"TR recall {_pct(facts.test[TR].recall)}, EN recall {_pct(facts.test[EN].recall)}.",
        f"- UNSURE oranı {_pct(facts.test_three_way.unsure_rate)}.",
        f"- H4: {'tuttu' if h4(facts) else 'tutmadı'}.",
        "",
        "## Sınırlamalar",
        "- Sentetik set; küçük doğrulama ve test kümeleri; jailbreak örneklemi küçük.",
        "- Yeni biçimdeki enjeksiyonlara karşı tek başına yeterli değildir; 1. ve 3. halkalarla birlikte çalışır.",
        "",
        "## Adalet ve kapsam notları",
        "- Yalnız TR ve EN eğitildi; başka dillerde davranışı ölçülmedi. Kapsam kararı kaydı istek metnini "
        "tutmaz (guardrails-security §2); sohbet mesajları ayrıca sohbet geçmişinde saklanır (D-225).",
        "",
        "## Kullanım dışı durumlar",
        "- Başka bir gömme modeli veya özetiyle çalıştırmak; 2. halkayı tek başına bekçi olarak kullanmak.",
        "",
    ])  # fmt: skip
