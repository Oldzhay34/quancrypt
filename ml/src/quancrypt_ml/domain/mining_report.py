"""The facts of one mining run and the report built from them (P7.4, ml/reports/mining.md). Each technique's facts are
logged to MLflow as `facts.json` exactly as they are here, and the report prints nothing that is not in them. Project keys
appear as their first 12 digits only. Standard library only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quancrypt_ml.domain.mining import UNKNOWN, Archetype, Rule

KEY_DIGITS = 12


@dataclass(frozen=True)
class Assignment:
    project: str  # first digits of the project key
    kmeans: int | None
    hdbscan: int | None


@dataclass(frozen=True)
class PlanProposal:
    archetype: str
    steps: Sequence[tuple[str, str]]  # (priority, strategy code)


@dataclass(frozen=True)
class ClusteringFacts:
    data_sha256: str
    seed: int
    projects_with_findings: int
    projects: int  # with at least one finding outside test code
    features: Sequence[str]
    skipped: str | None  # why nothing was clustered
    silhouettes: Mapping[str, float]  # k -> silhouette
    inertias: Mapping[str, float]  # k -> inertia
    chosen_k: int
    elbow_k: int
    kmeans_silhouette: float
    hdbscan_min_cluster_size: int
    hdbscan_clusters: int
    hdbscan_noise: int
    hdbscan_silhouette: float | None
    adjusted_rand: float | None  # over the projects HDBSCAN put in a cluster
    archetypes: Sequence[Archetype]
    hdbscan_archetypes: Sequence[Archetype]
    assignments: Sequence[Assignment]
    mean_unknown_share: float
    plans: Sequence[PlanProposal]


@dataclass(frozen=True)
class RuleFacts:
    data_sha256: str
    transactions: int  # projects with at least one item
    items: Mapping[str, int]  # item -> projects that hold it
    min_support_projects: int
    min_support: float | None  # None: nothing was mined
    min_confidence: float
    min_lift: float
    candidate_rules: int  # rules above the support floor, before confidence and lift
    rules: Sequence[Rule]
    skipped: str | None = None  # why no rule was mined


@dataclass(frozen=True)
class ScoredProject:
    project: str
    score: float
    is_flagged: bool
    finding_count: int
    top_family: str
    top_family_share: float
    top_context: str
    top_context_share: float


@dataclass(frozen=True)
class AnomalyFacts:
    data_sha256: str
    seed: int
    projects: int
    contamination: float
    trees: int
    scores: Sequence[ScoredProject]  # most unusual first
    skipped: str | None = None  # why nothing was scored

    @property
    def queue(self) -> list[ScoredProject]:
        return [s for s in self.scores if s.is_flagged]


def _f(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _p(value: float) -> str:
    return f"%{100 * value:.0f}"


def _shares(means: Mapping[str, float]) -> str:
    top = sorted(((v, c) for c, v in means.items() if v > 0), key=lambda x: (-x[0], x[1]))[:3]
    return ", ".join(f"{code} {_p(value)}" for value, code in top)


def _archetype_table(found: Sequence[Archetype]) -> list[str]:
    lines = [
        "| Küme | Ad | Proje | En yüksek aileler | En yüksek bağlamlar | Birim başına bulgu |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {a.cluster_no} | {a.name} | {a.size} | {_shares(a.family_means)} | {_shares(a.context_means)} | "
        f"{_f(a.findings_per_unit)} |"
        for a in found
    ]
    return lines


def _clustering_comment(facts: ClusteringFacts) -> list[str]:
    lines = ["### Yorum", ""]
    if facts.chosen_k != facts.elbow_k:
        lines.append(f"- Siluet k={facts.chosen_k}, dirsek k={facts.elbow_k} gösteriyor; siluet esas alındı (D-338c).")
    else:
        lines.append(f"- Siluet ve dirsek aynı k'yi gösteriyor (k={facts.chosen_k}).")
    unknown = [a for a in facts.archetypes if a.name.startswith(f"{UNKNOWN} /")]
    if not facts.hdbscan_clusters:
        lines.append(
            f"- HDBSCAN küme bulmadı ({facts.hdbscan_noise} proje gürültü): kümeleme yapısı zayıftır. K-Means her "
            "projeyi bir kümeye koymak zorunda olduğu için kümeleri belirgin gruplar olarak okumayın."
        )
    lines.append(f"- Proje başına ortalama `UNKNOWN` aile payı {_p(facts.mean_unknown_share)}.")
    if unknown:
        lines.append(
            f"- {len(unknown)} kümenin merkezinde en yüksek aile payı `UNKNOWN`'dır: bu pay için algoritma ailesi "
            "belirlenememiştir. En yüksek pay çoğunluk demek değildir."
        )
    lines.append(f"- {facts.projects} proje küçük bir örnektir; kümeler arketip adayıdır, genellenemez.")
    return lines


def _clustering(facts: ClusteringFacts, run_id: str) -> list[str]:
    lines = [
        "## 1. Kümeleme (kripto arketipleri)",
        "",
        f"MLflow run: `{run_id}`. Veri özeti: `{facts.data_sha256}`. Tohum {facts.seed}.",
        "",
        f"- Bulgusu olan korpus projesi: {facts.projects_with_findings}; test dışı bulgusu olan (kümelenen): "
        f"{facts.projects}.",
        f"- Özellik sayısı: {len(facts.features)} (aile ve bağlam payları `MinMaxScaler`, birim başına bulgu `log1p` ve "
        "`StandardScaler`).",
        "",
    ]
    if facts.skipped:
        return [*lines, f"**Kümeleme yapılmadı:** {facts.skipped}", ""]
    lines += ["| k | Siluet | Inertia |", "|---|---|---|"]
    lines += [f"| {k} | {_f(v)} | {_f(facts.inertias[k])} |" for k, v in facts.silhouettes.items()]
    lines += [
        "",
        f"Seçilen k = {facts.chosen_k} (siluet {_f(facts.kmeans_silhouette)}); dirsek noktası k = {facts.elbow_k}.",
        "",
        "![Siluet ve dirsek](mining_artifacts/k_selection.png)",
        "",
        "### K-Means arketipleri",
        "",
        *_archetype_table(facts.archetypes),
        "",
        "Ad gerekçeleri:",
        "",
        *[f"- **{a.name}**: {a.rationale}." for a in facts.archetypes],
        "",
        "![Kümeler, iki boyutlu izdüşüm](mining_artifacts/cluster_map.png)",
        "",
        "### HDBSCAN karşılaştırması",
        "",
        f"`min_cluster_size` {facts.hdbscan_min_cluster_size}: {facts.hdbscan_clusters} küme, "
        f"{facts.hdbscan_noise} proje gürültü; siluet {_f(facts.hdbscan_silhouette)}; K-Means ile ayarlı Rand indeksi "
        f"{_f(facts.adjusted_rand)} (gürültü olmayan projeler).",
        "",
        *(_archetype_table(facts.hdbscan_archetypes) if facts.hdbscan_archetypes else ["HDBSCAN küme bulmadı."]),
        "",
        "### Atamalar",
        "",
        "| Proje | K-Means | HDBSCAN |",
        "|---|---|---|",
        *[f"| `{a.project}` | {a.kmeans or '-'} | {a.hdbscan or 'gürültü'} |" for a in facts.assignments],
        "",
        *_clustering_comment(facts),
        "",
    ]
    return lines


def _rules(facts: RuleFacts, run_id: str) -> list[str]:
    lines = [
        "## 2. Birliktelik kuralları (FP-Growth)",
        "",
        f"MLflow run: `{run_id}`. Veri özeti: `{facts.data_sha256}`.",
        "",
        f"- İşlem: proje başına `lib:` ve `alg:` öğeleri, test dışı bulgulardan; `alg:UNKNOWN` öğe değildir. "
        f"{facts.transactions} proje, {len(facts.items)} farklı öğe.",
        f"- Eşikler: destek en az {facts.min_support_projects} proje"
        + ("" if facts.min_support is None else f" ({_f(facts.min_support)})")
        + f", güven en az {_f(facts.min_confidence)}, lift {_f(facts.min_lift)} üstü.",
        *(
            []
            if facts.skipped
            else [
                f"- Destek eşiğini geçen kural adayı: {facts.candidate_rules}; tüm eşikleri geçen: {len(facts.rules)}."
            ]
        ),
        "",
        "| Öğe | Proje |",
        "|---|---|",
        *[f"| `{item}` | {count} |" for item, count in facts.items.items()],
        "",
    ]
    if facts.skipped:
        return [*lines, f"**Kural madenciliği yapılmadı:** {facts.skipped}", ""]
    if not facts.rules:
        return [*lines, "**Eşikleri geçen kural yok.** Eşikler gevşetilmedi (D-337e).", ""]
    lines += ["| Öncül | Sonuç | Destek | Güven | Lift |", "|---|---|---|---|---|"]
    lines += [
        f"| {', '.join(f'`{i}`' for i in r.antecedent)} | {', '.join(f'`{i}`' for i in r.consequent)} | "
        f"{_f(r.support)} | {_f(r.confidence)} | {_f(r.lift)} |"
        for r in facts.rules
    ]
    return [
        *lines,
        "",
        "![Kurallar: destek ve güven](mining_artifacts/rules.png)",
        "",
        "### Yorum",
        "",
        "- Kural birlikte görülmeyi anlatır, nedenselliği değil. Kütüphane bilgisi bulguyu üreten dedektörün "
        "kütüphanesidir, projenin bağımlılık listesi değildir.",
        "",
    ]


def _anomalies(facts: AnomalyFacts, run_id: str) -> list[str]:
    lines = [
        "## 3. Anomali tespiti (Isolation Forest)",
        "",
        f"MLflow run: `{run_id}`. Veri özeti: `{facts.data_sha256}`. Tohum {facts.seed}.",
        "",
    ]
    if facts.skipped:
        return [*lines, f"**Anomali tespiti yapılmadı:** {facts.skipped}", ""]
    lines += [
        f"- Kontaminasyon {_f(facts.contamination)}, {facts.trees} ağaç, {facts.projects} proje; kümelemeyle aynı "
        "özellikler.",
        f"- İnceleme kuyruğu: {len(facts.queue)} proje (puan düştükçe daha sıra dışı).",
        "",
        "| Sıra | Proje | Puan | Bulgu | En yüksek aile | En yüksek bağlam |",
        "|---|---|---|---|---|---|",
        *[
            f"| {rank} | `{s.project}` | {_f(s.score)} | {s.finding_count} | {s.top_family} {_p(s.top_family_share)} | "
            f"{s.top_context} {_p(s.top_context_share)} |"
            for rank, s in enumerate(facts.queue, start=1)
        ],
        "",
    ]
    if facts.scores:
        lines += ["![Anomali puanları](mining_artifacts/anomaly_scores.png)", ""]
    return [
        *lines,
        "### Yorum",
        "",
        "- Kuyruk 'hatalı proje' listesi değildir: profili diğerlerinden farklı projelerdir ve elle incelenir. "
        "Kuyruğun boyunu büyük ölçüde kontaminasyon parametresi belirler.",
        "",
    ]


def _plans(facts: ClusteringFacts) -> list[str]:
    lines = [
        "## 4. Arketipe göre plan şablonu — ÖNERİ, onaylanmadı",
        "",
        "Küme merkezinde görülen öncelik ve bağlamlar için crypto-domain §1 tablosunun strateji kodları, öncelik "
        "sırasıyla. Planlama agent'ına bağlı değildir.",
        "",
    ]
    if not facts.plans:
        return [*lines, "Küme olmadığı için öneri yok.", ""]
    for plan in facts.plans:
        steps = " → ".join(f"{priority} `{strategy}`" for priority, strategy in plan.steps) or "adım yok"
        lines.append(f"- **{plan.archetype}**: {steps}")
    return [*lines, ""]


def build_report(
    clustering: ClusteringFacts, rules: RuleFacts, anomalies: AnomalyFacts, run_ids: Mapping[str, str]
) -> str:
    lines = [
        "# Data mining: korpus kripto profilleri",
        "",
        "Veri `marts.mart_archetypes` ve `marts.mart_risk_features`'tır: yalnız korpus projeleri, test kodu bulguları "
        "hariç (D-337). Sıralı örüntü madenciliği yapılmadı: CVEfixes yüklü değil. Proje anahtarlarının yalnız ilk "
        f"{KEY_DIGITS} hanesi yazılır. Buradaki her sayı adı geçen MLflow run'ının `facts.json` dosyasındadır.",
        "",
        *_clustering(clustering, run_ids["clustering"]),
        *_rules(rules, run_ids["rules"]),
        *_anomalies(anomalies, run_ids["anomalies"]),
        *_plans(clustering),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"
