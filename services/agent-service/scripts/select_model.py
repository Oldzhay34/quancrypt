#!/usr/bin/env python3
"""Yerel sohbet ve embedding modeli seçimi için değerlendirme betiği (P0.4).

Ollama HTTP API'sini doğrudan çağırır; yalnızca standart kütüphane kullanır. Kalıcı bir yardımcı
betiktir ve agent-service'in `src/` paketine bağımlı değildir.

Ne ölçer
- Sohbet modelleri (data/examples/model_selection.jsonl, 30 soru): ilk token süresi, toplam süre,
  anahtar kelime isabeti, yasak kelime ihlali, kapsam etiketi doğruluğu ve ret uyumu.
- Embedding modelleri (aşağıdaki 20 TR/EN cümle çifti): çevirisi olan cümleyi bulma isabeti,
  kosinüs benzerliği sıralaması ve gömme süresi.

Çıktı: docs/model_selection_report.md (varsayılan). Seçimi bu betik yapmaz; seçim kullanıcıya aittir.

Anahtar kelime kodlaması: `expected_keywords` ve `forbidden_keywords` içindeki bir girdi, `|` ile
ayrılmış eşdeğer yazımlar içerebilir (örneğin "1184|1,184|1.184"). Eşdeğerlerden biri yanıtta
geçerse girdi isabet sayılır. Karşılaştırma büyük/küçük harf ve Türkçe i/ı farkına duyarsızdır.

Kullanım:
  python3 scripts/select_model.py
  python3 scripts/select_model.py --chat-models qwen3:4b,gemma3:4b --skip-embed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = SCRIPT_DIR.parent
DEFAULT_DATASET = SERVICE_DIR / "data" / "examples" / "model_selection.jsonl"
DEFAULT_OUTPUT = SERVICE_DIR / "docs" / "model_selection_report.md"

# D-62: kullanıcının seçtiği adaylar.
DEFAULT_CHAT_MODELS = ["qwen3:4b", "gemma3:4b"]
DEFAULT_EMBED_MODELS = ["bge-m3", "qwen3-embedding:0.6b", "embeddinggemma"]

# crypto-domain skill'i, bölüm 4: sabit ret metinleri (harfi harfine).
REFUSAL_TR = (
    "Bahsettiğiniz şeyi anlamadım; yalnızca projenizdeki şifreleme ve "
    "kuantum-güvenli geçiş konularında yardımcı olabiliyorum."
)
REFUSAL_EN = (
    "I didn't understand what you mentioned; I can only help with encryption in "
    "your project and quantum-safe migration."
)
REFUSALS = {"tr": REFUSAL_TR, "en": REFUSAL_EN}

# Harness sistem istemleri (D-65, D-67). Bunlar test donanımıdır; ürün istemi (P4.4/P4.5) değildir.
# Üç istem vardır: bilgi soruları (ret talimatı yok), kapsam dışı sorular (ret cümleleri) ve kapsam kararı.
SYSTEM_PROMPT_KNOWLEDGE = (
    "Sen Quancrypt asistanısın: projedeki şifreleme ve kuantum-güvenli geçiş konusunda yardım edersin. "
    "Kullanıcının yazdığı dilde, kısa ve doğru yanıt ver; emin değilsen 'emin değilim' de."
)
SYSTEM_PROMPT_REFUSAL = (
    "Sen Quancrypt asistanısın. Yalnızca projedeki şifreleme ve kuantum-güvenli geçiş konularında "
    "yardım edersin: kripto envanteri, risk, PQC ve hibrit kavramları, QKD kavramları ve sınırları, "
    "TLS/mTLS/JWT/sertifika ve keystore ayarları, sürüm uyumu, uyum takvimi. Bunların dışındaki her "
    "istekte, isteğin diline göre, yalnızca şu cümleyi yaz (başka hiçbir şey yazma): "
    f"Türkçe istek için \"{REFUSAL_TR}\" İngilizce istek için \"{REFUSAL_EN}\" "
    "Kısa ve doğru yanıt ver; emin değilsen 'emin değilim' de."
)
SYSTEM_PROMPT_SCOPE = (
    "Kullanıcı isteğinin Quancrypt kapsamında olup olmadığına karar ver. Kapsam: projenin kriptosu "
    "(envanter, konum, risk), kuantum-güvenli geçiş ve stratejiler, PQC ve hibrit kavramları, QKD "
    "kavramları ve sınırları, projedeki TLS, mTLS, JWT, sertifika ve keystore ayarları, sürüm uyumu, "
    "uyum takvimi, Quancrypt'in kullanımı ve veri işleme biçimi. Bunların dışındaki her istek "
    "(kriptoyu kırma, zararlı yazılım veya başkasının sistemine saldırı dahil) kapsam dışıdır. "
    "Yalnızca IN_SCOPE veya OUT_OF_SCOPE yaz."
)

TEMPERATURE = 0
SEED = 42

# 20 TR/EN eşleştirilmiş cümle çifti. İçerikleri crypto-domain skill'indeki doğrulanmış bilgilerden
# türetilmiştir; yeni teknik iddia içermez. Benzer çiftler (5-6, 14-15) bilerek yakın anlamlıdır.
SENTENCE_PAIRS: list[tuple[str, str]] = [
    ("ML-KEM-768 açık anahtarı 1.184 bayttır.", "The ML-KEM-768 public key is 1,184 bytes."),
    ("ML-DSA-65 imzası 3.309 bayttır.", "An ML-DSA-65 signature is 3,309 bytes."),
    ("RSA-2048 imzası 256 bayttır.", "An RSA-2048 signature is 256 bytes."),
    ("FIPS 203, 204 ve 205 13 Ağustos 2024'te yayımlandı.",
     "FIPS 203, 204 and 205 were published on August 13, 2024."),
    ("NIST taslağı RSA ve ECDSA'nın 2030'dan sonra kullanımdan kaldırılmasını önerir.",
     "The NIST draft proposes deprecating RSA and ECDSA after 2030."),
    ("NIST taslağı bu algoritmaların 2035'ten sonra yasaklanmasını önerir.",
     "The NIST draft proposes disallowing these algorithms after 2035."),
    ("JDK 24, ML-KEM ve ML-DSA'yı JEP 496 ve JEP 497 ile getirdi.",
     "JDK 24 added ML-KEM and ML-DSA through JEP 496 and JEP 497."),
    ("JDK 27, TLS 1.3'te hibrit X25519MLKEM768 grubunu varsayılan yaptı.",
     "JDK 27 made the hybrid X25519MLKEM768 group the default in TLS 1.3."),
    ("javax.crypto.KEM API'si JDK 21'den beri vardır.",
     "The javax.crypto.KEM API has existed since JDK 21."),
    ("JDK 27 öncesinde TLS 1.3 varsayılan anahtar değişim grupları klasiktir.",
     "Before JDK 27 the default TLS 1.3 key exchange groups are classical."),
    ("OpenSSL 3.5.0, ML-KEM, ML-DSA ve SLH-DSA desteği ekledi.",
     "OpenSSL 3.5.0 added support for ML-KEM, ML-DSA and SLH-DSA."),
    ("QKD yazılımla kurulamaz; özel donanım ve fiziksel kanal gerektirir.",
     "QKD cannot be deployed in software; it requires dedicated hardware and a physical channel."),
    ("Quancrypt, QKD'yi yalnızca ETSI GS QKD 014 arayüzü düzeyinde destekler.",
     "Quancrypt supports QKD only at the ETSI GS QKD 014 interface level."),
    ("QBER yaklaşık yüzde 11'in altındaysa BB84'ten güvenli anahtar çıkarılabilir.",
     "If the QBER is below roughly 11 percent, a secure key can be extracted from BB84."),
    ("Tam bir intercept-resend saldırısı yaklaşık yüzde 25 QBER üretir.",
     "A full intercept-resend attack produces about 25 percent QBER."),
    ("İmzalar 'şimdi topla, sonra çöz' tehdidinden etkilenmez.",
     "Signatures are not affected by the 'harvest now, decrypt later' threat."),
    ("Bugün kırılabilen zayıf kripto her zaman ilk sıradadır.",
     "Weak cryptography that can be broken today always comes first."),
    ("Kısa ömürlü JWT token'ları P3 önceliğindedir.", "Short-lived JWT tokens have priority P3."),
    ("Servisler arası TLS ve mTLS anahtar değişimi P1 önceliğindedir.",
     "Service-to-service TLS and mTLS key exchange has priority P1."),
    ("Tüm sertifikalara güvenen bir TrustManager yazmak yasak bir kalıptır.",
     "Writing a TrustManager that trusts all certificates is a forbidden pattern."),
]

REQUIRED_FIELDS = ("id", "lang", "category", "prompt", "expected_keywords", "forbidden_keywords", "expected_label")
CATEGORIES = ("crypto", "springboot", "out_of_scope", "scope_decision")
LABEL_PATTERN = re.compile(r"\b(OUT_OF_SCOPE|IN_SCOPE)\b")


# --------------------------------------------------------------------------------------
# Ollama HTTP istemcisi
# --------------------------------------------------------------------------------------

class OllamaError(RuntimeError):
    """Ollama çağrısı başarısız oldu (HTTP hatası, bağlantı yok, model yok)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class OllamaClient:
    """Ollama HTTP API'si için ince istemci (/api/chat, /api/embed, /api/show, /api/tags)."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, payload: dict | None = None) -> urllib.request.addinfourl:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path, data=data, headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            raise OllamaError(f"{path} HTTP {exc.code}: {body}", exc.code) from exc
        except urllib.error.URLError as exc:
            raise OllamaError(f"{self.base_url} adresine bağlanılamadı: {exc.reason}") from exc

    def get_json(self, path: str) -> dict:
        with self._request(path) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, payload: dict) -> dict:
        with self._request(path, payload) as response:
            return json.loads(response.read().decode("utf-8"))

    def stream_chat(self, payload: dict) -> "ChatResult":
        """Akışlı sohbet isteği; ilk içerik ve ilk token (düşünme dahil) sürelerini ve istatistikleri toplar."""
        started = time.perf_counter()
        first_content_at: float | None = None
        first_any_at: float | None = None
        content: list[str] = []
        thinking: list[str] = []
        final: dict = {}
        with self._request("/api/chat", payload) as response:
            for raw_line in response:
                line = raw_line.strip()
                if not line:
                    continue
                chunk = json.loads(line)
                if "error" in chunk:
                    raise OllamaError(f"/api/chat: {chunk['error']}")
                message = chunk.get("message", {})
                piece = message.get("content", "")
                thought = message.get("thinking", "")
                if (piece or thought) and first_any_at is None:
                    first_any_at = time.perf_counter()
                if thought:
                    thinking.append(thought)
                if piece:
                    if first_content_at is None:
                        first_content_at = time.perf_counter()
                    content.append(piece)
                if chunk.get("done"):
                    final = chunk
        finished = time.perf_counter()
        return ChatResult(
            text=strip_think_leak("".join(content)),
            thinking_chars=len("".join(thinking)),
            first_token_s=(first_content_at - started) if first_content_at is not None else (finished - started),
            first_any_s=(first_any_at - started) if first_any_at is not None else (finished - started),
            total_s=finished - started,
            load_s=final.get("load_duration", 0) / 1e9,
            eval_count=final.get("eval_count", 0),
            eval_s=final.get("eval_duration", 0) / 1e9,
            truncated=final.get("done_reason") == "length",
        )


def strip_think_leak(text: str) -> str:
    """Düşünme kapatıldığında içeriğe sızan akıl yürütmeyi (`... </think>`) atar; yalnızca sonrası yanıttır."""
    return text.rsplit("</think>", 1)[-1].strip() if "</think>" in text else text


@dataclass
class ChatResult:
    text: str
    first_token_s: float  # ilk İÇERİK parçasına kadar (düşünme bitene kadar beklenir)
    total_s: float
    load_s: float
    eval_count: int
    eval_s: float
    thinking_chars: int = 0
    first_any_s: float = 0.0  # ilk token (düşünme dahil)
    truncated: bool = False  # num_predict sınırında kesildi

    @property
    def tokens_per_s(self) -> float:
        return self.eval_count / self.eval_s if self.eval_s > 0 else 0.0


# --------------------------------------------------------------------------------------
# Veri seti ve puanlama
# --------------------------------------------------------------------------------------

def load_dataset(path: Path) -> list[dict]:
    """Veri setini okur ve şemasını doğrular (30 soru, kategori ve dil dağılımı)."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        missing = [name for name in REQUIRED_FIELDS if name not in row]
        if missing:
            raise SystemExit(f"{path}: {row.get('id', '?')} satırında eksik alan: {missing}")
        if row["category"] not in CATEGORIES:
            raise SystemExit(f"{path}: {row['id']} bilinmeyen kategori: {row['category']}")
        if row["lang"] not in REFUSALS:
            raise SystemExit(f"{path}: {row['id']} bilinmeyen dil: {row['lang']}")
        if row["category"] == "scope_decision" and row["expected_label"] not in ("IN_SCOPE", "OUT_OF_SCOPE"):
            raise SystemExit(f"{path}: {row['id']} geçersiz expected_label")
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{path}: yinelenen id var")
    return rows


def normalize(text: str) -> str:
    """Büyük/küçük harf, Türkçe i/ı ve boşluk farklarını giderir (iki taraf aynı işlemden geçer)."""
    text = unicodedata.normalize("NFKC", text).replace("İ", "I").replace("ı", "i")
    return re.sub(r"\s+", " ", text.casefold()).strip()


def option_present(answer_norm: str, option: str) -> bool:
    """Eşdeğer yazım yanıtta geçiyor mu? Rakamla başlayan veya biten yazımlar başka bir sayının içinde sayılmaz
    (örneğin "24", "2024" içinde; "256", "2560" içinde isabet vermez)."""
    needle = normalize(option)
    pattern = re.escape(needle)
    if needle[:1].isdigit():
        pattern = r"(?<!\d)" + pattern
    if needle[-1:].isdigit():
        pattern += r"(?!\d)"
    return re.search(pattern, answer_norm) is not None


def contains_any(answer_norm: str, entry: str) -> bool:
    """`a|b|c` biçimindeki girdinin eşdeğerlerinden biri yanıtta geçiyor mu?"""
    return any(option_present(answer_norm, option) for option in entry.split("|") if option.strip())


def keyword_scores(answer: str, expected: list[str]) -> tuple[float, bool]:
    """(isabet oranı, hepsi isabet mi). Beklenen anahtar yoksa (1.0, True) döner."""
    if not expected:
        return 1.0, True
    answer_norm = normalize(answer)
    hits = sum(1 for entry in expected if contains_any(answer_norm, entry))
    return hits / len(expected), hits == len(expected)


def forbidden_violation(answer: str, forbidden: list[str]) -> bool:
    answer_norm = normalize(answer)
    return any(contains_any(answer_norm, entry) for entry in forbidden)


def parse_label(answer: str) -> str | None:
    """Yanıttaki ilk IN_SCOPE / OUT_OF_SCOPE etiketi (yoksa None)."""
    match = LABEL_PATTERN.search(answer.upper())
    return match.group(1) if match else None


def label_only(answer: str, label: str) -> bool:
    """Yanıt yalnızca etiketten mi oluşuyor (tırnak, nokta ve boşluk hariç)?"""
    return answer.strip().strip("`\"'*. \n").upper() == label


def refusal_exact(answer: str, lang: str) -> bool:
    """Yanıt, dile uygun ret sabitine harfi harfine (tırnak ve boşluk hariç) eşit mi?"""
    return normalize(answer.strip().strip("\"'`")) == normalize(REFUSALS[lang])


@dataclass
class QuestionOutcome:
    question: dict
    answer: str
    first_token_s: float
    total_s: float
    tokens_per_s: float
    first_any_s: float = 0.0
    thinking_chars: int = 0
    truncated: bool = False
    keyword_rate: float = 1.0
    keyword_full: bool = True
    violation: bool = False
    label_correct: bool | None = None
    label_strict: bool | None = None
    refusal_exact: bool | None = None
    refusal_contained: bool | None = None


def score_answer(question: dict, result: ChatResult) -> QuestionOutcome:
    """Bir yanıtı kategorisine uygun ölçütlerle puanlar."""
    outcome = QuestionOutcome(question, result.text, result.first_token_s, result.total_s, result.tokens_per_s,
                              first_any_s=result.first_any_s, thinking_chars=result.thinking_chars,
                              truncated=result.truncated)
    category = question["category"]
    if category in ("crypto", "springboot"):
        outcome.keyword_rate, outcome.keyword_full = keyword_scores(result.text, question["expected_keywords"])
        outcome.violation = forbidden_violation(result.text, question["forbidden_keywords"])
    elif category == "out_of_scope":
        outcome.refusal_exact = refusal_exact(result.text, question["lang"])
        outcome.refusal_contained = normalize(REFUSALS[question["lang"]]) in normalize(result.text)
        outcome.violation = forbidden_violation(result.text, question["forbidden_keywords"])
    else:
        expected = question["expected_label"]
        outcome.label_correct = parse_label(result.text) == expected
        outcome.label_strict = label_only(result.text, expected)
    return outcome


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


# --------------------------------------------------------------------------------------
# Sohbet değerlendirmesi
# --------------------------------------------------------------------------------------

class ResultCache:
    """Kesinti dayanıklılığı: biten her yanıtı bir JSONL dosyasına yazar; yeniden çalıştırınca kaldığı yerden devam eder.

    Anahtar; model özeti, soru, istem, token sınırı ve düşünme ayarını kapsar. Bunlardan biri değişirse eski yanıt
    kullanılmaz. Kesintide yarım yazılmış son satır sessizce atlanır.
    """

    def __init__(self, path: Path, fresh: bool) -> None:
        self.path = path
        self.entries: dict[str, dict] = {}
        if fresh and path.exists():
            path.unlink()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                    self.entries[record["key"]] = record["result"]
                except (json.JSONDecodeError, KeyError):
                    continue

    @staticmethod
    def make_key(digest: str, question: dict, system: str, num_predict: int, think: bool | None) -> str:
        raw = json.dumps([digest, question["id"], question["prompt"], system, num_predict, think], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> "ChatResult | None":
        stored = self.entries.get(key)
        return ChatResult(**stored) if stored else None

    def put(self, key: str, result: "ChatResult") -> None:
        self.entries[key] = asdict(result)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"key": key, "result": asdict(result)}, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


@dataclass
class ChatReport:
    model: str
    info: dict
    cold_load_s: float
    outcomes: list[QuestionOutcome] = field(default_factory=list)
    think_fallback: bool = False
    resumed: int = 0  # önceki (kesilen) çalıştırmadan önbellekten alınan yanıt sayısı
    error: str | None = None


def chat_payload(model: str, system: str, prompt: str, num_predict: int, think: bool | None) -> dict:
    payload: dict = {
        "model": model,
        "stream": True,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "options": {"temperature": TEMPERATURE, "seed": SEED, "num_predict": num_predict},
        "keep_alive": "10m",
    }
    if think is not None:
        payload["think"] = think
    return payload


def system_prompt_for(category: str) -> str:
    """Kategoriye uygun harness istemi (D-67)."""
    if category == "scope_decision":
        return SYSTEM_PROMPT_SCOPE
    if category == "out_of_scope":
        return SYSTEM_PROMPT_REFUSAL
    return SYSTEM_PROMPT_KNOWLEDGE


def ask(client: OllamaClient, report: ChatReport, system: str, prompt: str, num_predict: int, think: bool | None) -> ChatResult:
    """Soruyu sorar; `think` reddedilirse (D-66) aynı isteği `think` olmadan tekrarlar ve not düşer."""
    try:
        return client.stream_chat(chat_payload(report.model, system, prompt, num_predict, think))
    except OllamaError as exc:
        if think is not None and exc.status == 400 and "think" in str(exc).lower():
            report.think_fallback = True
            return client.stream_chat(chat_payload(report.model, system, prompt, num_predict, None))
        raise


def model_info(client: OllamaClient, model: str) -> dict:
    """Etiket, özet kimliği, boyut, parametre ve niceleme bilgisi (/api/tags ve /api/show).

    Etiketsiz ad (örneğin `bge-m3`) Ollama'da `:latest` etiketiyle saklanır; çözülen tam etiket rapora yazılır.
    """
    candidates = {model, model if ":" in model else f"{model}:latest"}
    info: dict = {"tag": model}
    for entry in client.get_json("/api/tags").get("models", []):
        name = entry.get("name") or entry.get("model")
        if name in candidates:
            info["tag"] = name
            info["digest"] = entry.get("digest", "")
            info["size_bytes"] = entry.get("size", 0)
            break
    else:
        raise OllamaError(f"{model} kurulu değil (ollama list). İndirme kullanıcı onayı ister: ollama pull {model}")
    details = client.post_json("/api/show", {"model": info["tag"]}).get("details", {})
    info.update(family=details.get("family", ""), parameter_size=details.get("parameter_size", ""),
                quantization=details.get("quantization_level", ""))
    return info


def unload(client: OllamaClient, model: str) -> None:
    try:
        client.post_json("/api/generate", {"model": model, "keep_alive": 0})
    except OllamaError:
        pass


def evaluate_chat(client: OllamaClient, model: str, dataset: list[dict], num_predict: int, think: bool | None,
                  cache: ResultCache | None = None) -> ChatReport:
    try:
        info = model_info(client, model)
    except OllamaError as exc:
        print(f"[sohbet] {model}: HATA {exc}", file=sys.stderr, flush=True)
        return ChatReport(model=model, info={"tag": model}, cold_load_s=0.0, error=str(exc))
    report = ChatReport(model=model, info=info, cold_load_s=0.0)
    print(f"[sohbet] {model}: ısınma", flush=True)
    try:
        warmup = ask(client, report, SYSTEM_PROMPT_KNOWLEDGE, "Merhaba", 8, think)
        report.cold_load_s = warmup.load_s if warmup.load_s else warmup.total_s
        for index, question in enumerate(dataset, start=1):
            system = system_prompt_for(question["category"])
            key = ResultCache.make_key(info.get("digest", ""), question, system, num_predict, think)
            result = cache.get(key) if cache else None
            source = "önbellek"
            if result is None:
                result = ask(client, report, system, question["prompt"], num_predict, think)
                if cache:
                    cache.put(key, result)
                source = "yeni"
            else:
                report.resumed += 1
            report.outcomes.append(score_answer(question, result))
            print(f"[sohbet] {model}: {index}/{len(dataset)} {question['id']} {result.total_s:.1f} sn ({source})", flush=True)
    except OllamaError as exc:
        report.error = str(exc)
        print(f"[sohbet] {model}: HATA {exc}", file=sys.stderr, flush=True)
    finally:
        unload(client, model)
    return report


# --------------------------------------------------------------------------------------
# Embedding değerlendirmesi
# --------------------------------------------------------------------------------------

@dataclass
class EmbedReport:
    model: str
    info: dict
    dimension: int = 0
    top1_tr_to_en: float = 0.0
    top1_en_to_tr: float = 0.0
    mean_pair_cos: float = 0.0
    mean_other_cos: float = 0.0
    mean_margin: float = 0.0
    ms_per_sentence: float = 0.0
    cold_load_s: float = 0.0
    error: str | None = None


def embed(client: OllamaClient, model: str, texts: list[str]) -> tuple[list[list[float]], float]:
    started = time.perf_counter()
    response = client.post_json("/api/embed", {"model": model, "input": texts, "keep_alive": "10m"})
    elapsed = time.perf_counter() - started
    vectors = response.get("embeddings", [])
    if len(vectors) != len(texts):
        raise OllamaError(f"/api/embed: {len(texts)} girdi için {len(vectors)} vektör döndü")
    return vectors, elapsed


def top1_rate(similarity: list[list[float]]) -> float:
    """satır i için en yüksek benzerlik sütun i'de mi (doğru çift)?"""
    hits = sum(1 for i, row in enumerate(similarity) if max(range(len(row)), key=row.__getitem__) == i)
    return hits / len(similarity)


def evaluate_embedding(client: OllamaClient, model: str) -> EmbedReport:
    try:
        info = model_info(client, model)
    except OllamaError as exc:
        print(f"[embedding] {model}: HATA {exc}", file=sys.stderr, flush=True)
        return EmbedReport(model=model, info={"tag": model}, error=str(exc))
    report = EmbedReport(model=model, info=info)
    turkish = [pair[0] for pair in SENTENCE_PAIRS]
    english = [pair[1] for pair in SENTENCE_PAIRS]
    print(f"[embedding] {model}", flush=True)
    try:
        _, report.cold_load_s = embed(client, model, ["ısınma"])
        tr_vectors, tr_elapsed = embed(client, model, turkish)
        en_vectors, en_elapsed = embed(client, model, english)
    except OllamaError as exc:
        report.error = str(exc)
        print(f"[embedding] {model}: HATA {exc}", file=sys.stderr, flush=True)
        unload(client, model)
        return report
    unload(client, model)
    count = len(SENTENCE_PAIRS)
    similarity = [[cosine(tr_vectors[i], en_vectors[j]) for j in range(count)] for i in range(count)]
    report.dimension = len(tr_vectors[0])
    report.top1_tr_to_en = top1_rate(similarity)
    report.top1_en_to_tr = top1_rate([[similarity[i][j] for i in range(count)] for j in range(count)])
    report.mean_pair_cos = statistics.mean(similarity[i][i] for i in range(count))
    report.mean_other_cos = statistics.mean(similarity[i][j] for i in range(count) for j in range(count) if i != j)
    report.mean_margin = report.mean_pair_cos - report.mean_other_cos
    report.ms_per_sentence = (tr_elapsed + en_elapsed) / (2 * count) * 1000
    return report


# --------------------------------------------------------------------------------------
# Raporlama
# --------------------------------------------------------------------------------------

def mean_of(values: list[float]) -> float:
    return statistics.mean(values) if values else float("nan")


def pct(value: float) -> str:
    return "—" if math.isnan(value) else f"{value * 100:.0f}%"


def fixed(value: float, digits: int = 2) -> str:
    return "—" if math.isnan(value) else f"{value:.{digits}f}"


def subset(outcomes: list[QuestionOutcome], category: str | None = None, lang: str | None = None) -> list[QuestionOutcome]:
    return [o for o in outcomes if (category is None or o.question["category"] == category)
            and (lang is None or o.question["lang"] == lang)]


def chat_metrics(report: ChatReport) -> dict[str, float]:
    """Sıralamada kullanılan sohbet metrikleri (isim → değer)."""
    keyword_rows = subset(report.outcomes, "crypto") + subset(report.outcomes, "springboot")
    oos = subset(report.outcomes, "out_of_scope")
    scope = subset(report.outcomes, "scope_decision")
    return {
        "anahtar kelime isabeti (ort.)": mean_of([o.keyword_rate for o in keyword_rows]),
        "kapsam etiketi doğruluğu": mean_of([1.0 if o.label_correct else 0.0 for o in scope]),
        "ret uyumu (harfi harfine)": mean_of([1.0 if o.refusal_exact else 0.0 for o in oos]),
        "yasak kelime ihlali (adet)": float(sum(1 for o in report.outcomes if o.violation)),
        "token sınırında kesilen yanıt (adet)": float(sum(1 for o in report.outcomes if o.truncated)),
        "ilk içerik süresi, medyan (sn)": statistics.median(o.first_token_s for o in report.outcomes),
        "toplam süre, medyan (sn)": statistics.median(o.total_s for o in report.outcomes),
    }


HIGHER_IS_BETTER_CHAT = {"anahtar kelime isabeti (ort.)", "kapsam etiketi doğruluğu", "ret uyumu (harfi harfine)"}
HIGHER_IS_BETTER_EMBED = {"TR→EN ilk sıra isabeti", "EN→TR ilk sıra isabeti", "çift–diğer fark (marj)"}


def rank_models(values: dict[str, dict[str, float]], higher_is_better: set[str]) -> dict[str, dict[str, int]]:
    """Her metrik için yarışma sıralaması (eşitlikte aynı sıra). Sonuç: model → metrik → sıra."""
    ranks: dict[str, dict[str, int]] = {model: {} for model in values}
    metrics = next(iter(values.values())).keys() if values else []
    for metric in metrics:
        for model in values:
            if metric in higher_is_better:
                better = sum(1 for other in values if values[other][metric] > values[model][metric])
            else:
                better = sum(1 for other in values if values[other][metric] < values[model][metric])
            ranks[model][metric] = better + 1
    return ranks


def ranking_table(values: dict[str, dict[str, float]], higher_is_better: set[str], fmt) -> list[str]:
    ranks = rank_models(values, higher_is_better)
    metrics = list(next(iter(values.values())).keys())
    lines = ["| Model | " + " | ".join(metrics) + " | Ortalama sıra |", "|---|" + "---|" * (len(metrics) + 1)]
    ordered = sorted(values, key=lambda m: statistics.mean(ranks[m].values()))
    for model in ordered:
        cells = [f"{fmt(metric, values[model][metric])} (#{ranks[model][metric]})" for metric in metrics]
        lines.append(f"| `{model}` | " + " | ".join(cells) + f" | {statistics.mean(ranks[model].values()):.2f} |")
    return lines


def fmt_chat(metric: str, value: float) -> str:
    if metric in HIGHER_IS_BETTER_CHAT:
        return pct(value)
    return fixed(value, 0) if "adet" in metric else fixed(value, 2)


def fmt_embed(metric: str, value: float) -> str:
    return pct(value) if "isabet" in metric else fixed(value, 3 if "marj" in metric else 1)


def one_line(text: str, limit: int = 220) -> str:
    flat = re.sub(r"\s+", " ", text).strip().replace("|", "\\|")
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def render_chat_section(reports: list[ChatReport], dataset: list[dict]) -> list[str]:
    ok = [r for r in reports if not r.error and r.outcomes]
    lines = ["## Sohbet modelleri", ""]
    for report in reports:
        if report.error:
            lines.append(f"- `{report.model}`: ölçülemedi — {report.error}")
    if not ok:
        return lines + [""]
    lines += ["### Özet metrikler ve gösterge sırası", ""]
    values = {r.model: chat_metrics(r) for r in ok}
    lines += ranking_table(values, HIGHER_IS_BETTER_CHAT, fmt_chat)
    lines += ["", "Ortalama sıra, metriklere eşit ağırlık veren yalnızca bir göstergedir; ağırlık ve seçim kullanıcıya aittir. "
              "Yasak kelime ihlalinde ve sürelerde düşük değer iyidir.", ""]
    lines += ["### Kategori ve dil kırılımı", "",
              "| Model | Kategori | Dil | Soru | Anahtar isabeti (ort.) | Hepsi isabet | Ret uyumu (harfi harfine) | Ret cümlesi içeriyor | Etiket doğru | Yalnızca etiket | Yasak ihlali |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for report in ok:
        for category in CATEGORIES:
            for lang in ("tr", "en"):
                rows = subset(report.outcomes, category, lang)
                if not rows:
                    continue
                lines.append(
                    f"| `{report.model}` | {category} | {lang.upper()} | {len(rows)} | "
                    f"{pct(mean_of([o.keyword_rate for o in rows])) if category in ('crypto', 'springboot') else '—'} | "
                    f"{pct(mean_of([1.0 if o.keyword_full else 0.0 for o in rows])) if category in ('crypto', 'springboot') else '—'} | "
                    f"{pct(mean_of([1.0 if o.refusal_exact else 0.0 for o in rows])) if category == 'out_of_scope' else '—'} | "
                    f"{pct(mean_of([1.0 if o.refusal_contained else 0.0 for o in rows])) if category == 'out_of_scope' else '—'} | "
                    f"{pct(mean_of([1.0 if o.label_correct else 0.0 for o in rows])) if category == 'scope_decision' else '—'} | "
                    f"{pct(mean_of([1.0 if o.label_strict else 0.0 for o in rows])) if category == 'scope_decision' else '—'} | "
                    f"{sum(1 for o in rows if o.violation)} |")
    lines += ["", "### Süre ve hız", "",
              "İlk token (düşünme dahil): akışta herhangi bir parçanın (düşünme veya içerik) ilk geldiği an. İlk içerik: yanıt metninin ilk parçası "
              "(düşünen modellerde düşünme bitene kadar beklenir). Düşünme karakteri: `thinking` alanındaki toplam karakter.", "",
              "| Model | Soğuk yükleme (sn) | İlk token (düşünme dahil), medyan (sn) | İlk içerik, medyan (sn) | İlk içerik, en yavaş (sn) | Toplam, medyan (sn) | Toplam, en yavaş (sn) | Token/sn, medyan | Düşünme karakteri, medyan | Kesilen yanıt |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for report in ok:
        ttft = [o.first_token_s for o in report.outcomes]
        any_first = [o.first_any_s for o in report.outcomes]
        total = [o.total_s for o in report.outcomes]
        speed = [o.tokens_per_s for o in report.outcomes if o.tokens_per_s > 0]
        thought = [o.thinking_chars for o in report.outcomes]
        lines.append(f"| `{report.model}` | {fixed(report.cold_load_s)} | {fixed(statistics.median(any_first))} | {fixed(statistics.median(ttft))} | {fixed(max(ttft))} | "
                     f"{fixed(statistics.median(total))} | {fixed(max(total))} | {fixed(statistics.median(speed), 1) if speed else '—'} | "
                     f"{statistics.median(thought):.0f} | {sum(1 for o in report.outcomes if o.truncated)}/{len(report.outcomes)} |")
    lines += ["", "### Soru bazında yanıtlar (Türkçe kaliteyi okuyarak değerlendirmeniz için)", "",
              "Yanıtlar tek satıra indirilmiş ve kısaltılmıştır. İsabet = anahtar kelime oranı; ✔/✘ = ilgili kategorinin ana ölçütü.", ""]
    for question in dataset:
        lines.append(f"**{question['id']}** ({question['lang'].upper()}, {question['category']}): {one_line(question['prompt'], 160)}")
        lines.append("")
        for report in ok:
            outcome = next((o for o in report.outcomes if o.question["id"] == question["id"]), None)
            if outcome is None:
                continue
            if question["category"] in ("crypto", "springboot"):
                verdict = f"isabet {pct(outcome.keyword_rate)}" + (", **YASAK**" if outcome.violation else "")
            elif question["category"] == "out_of_scope":
                verdict = "ret ✔" if outcome.refusal_exact else ("ret cümlesi var ama yanında metin ✘" if outcome.refusal_contained else "ret ✘")
            else:
                verdict = "etiket ✔" if outcome.label_correct else "etiket ✘"
            cut = ", KESİLDİ (token sınırı)" if outcome.truncated else ""
            lines.append(f"- `{report.model}` [{verdict}, {outcome.total_s:.1f} sn{cut}]: {one_line(outcome.answer) or '(boş)'}")
        lines.append("")
    return lines


def render_embed_section(reports: list[EmbedReport]) -> list[str]:
    ok = [r for r in reports if not r.error]
    lines = ["## Embedding modelleri", ""]
    for report in reports:
        if report.error:
            lines.append(f"- `{report.model}`: ölçülemedi — {report.error}")
    if not ok:
        return lines + [""]
    values = {r.model: {"TR→EN ilk sıra isabeti": r.top1_tr_to_en, "EN→TR ilk sıra isabeti": r.top1_en_to_tr,
                        "çift–diğer fark (marj)": r.mean_margin, "ms/cümle": r.ms_per_sentence} for r in ok}
    lines += ["### Özet metrikler ve gösterge sırası", ""]
    lines += ranking_table(values, HIGHER_IS_BETTER_EMBED, fmt_embed)
    lines += ["", "Marj: doğru çiftin ortalama kosinüsü eksi yanlış çiftlerin ortalama kosinüsü (yüksek iyi). ms/cümle düşük iyi. "
              "20 çiftin bir kısmı bilerek yakın anlamlıdır (5–6, 14–15); isabet bu yüzden %100'den küçük olabilir.", "",
              "### Ayrıntı", "",
              "| Model | Boyut | Doğru çift kosinüsü (ort.) | Yanlış çift kosinüsü (ort.) | Marj | ms/cümle | Soğuk yükleme (sn) |",
              "|---|---|---|---|---|---|---|"]
    for report in ok:
        lines.append(f"| `{report.model}` | {report.dimension} | {fixed(report.mean_pair_cos, 3)} | {fixed(report.mean_other_cos, 3)} | "
                     f"{fixed(report.mean_margin, 3)} | {fixed(report.ms_per_sentence, 1)} | {fixed(report.cold_load_s)} |")
    return lines + [""]


def render_candidates(chat: list[ChatReport], embed_reports: list[EmbedReport]) -> list[str]:
    lines = ["## Adaylar", "", "| Tür | Etiket | Özet kimliği | Boyut | Parametre | Niceleme | Aile |", "|---|---|---|---|---|---|---|"]
    for kind, items in (("sohbet", chat), ("embedding", embed_reports)):
        for item in items:
            info = item.info
            size = f"{info.get('size_bytes', 0) / 1e9:.2f} GB" if info.get("size_bytes") else "—"
            lines.append(f"| {kind} | `{info.get('tag', item.model)}` | `{info.get('digest', '')[:12]}` | {size} | "
                         f"{info.get('parameter_size', '—')} | {info.get('quantization', '—')} | {info.get('family', '—')} |")
    return lines + [""]


def render_report(args: argparse.Namespace, version: str, dataset: list[dict], chat: list[ChatReport], embed_reports: list[EmbedReport]) -> str:
    counts = {category: sum(1 for q in dataset if q["category"] == category) for category in CATEGORIES}
    think_note = {None: "modelin varsayılanı (parametre gönderilmedi, D-66; düşünen modellerde Ollama düşünmeyi ayırır, yalnızca içerik puanlanır)",
                  True: "açık (think: true)", False: "kapalı (think: false; düşünen modellerde akıl yürütme içeriğe sızabilir, `</think>` öncesi atılır)"}[args.think]
    fallbacks = [r.model for r in chat if r.think_fallback]
    lines = [
        "# Model seçimi raporu (P0.4)", "",
        f"Oluşturulma: {datetime.now().astimezone().isoformat(timespec='seconds')} · Ollama {version} · betik: `scripts/select_model.py`", "",
        "Bu rapor seçimi yapmaz; model seçimi kullanıcıya aittir (D-12).", "",
        "## Yöntem ve sınırlamalar", "",
        f"- Veri seti: `{Path(args.dataset).name}`, {len(dataset)} soru ({', '.join(f'{k}: {v}' for k, v in counts.items())}); her kategorinin yarısı Türkçe, yarısı İngilizce.",
        f"- Üretim ayarları: temperature {TEMPERATURE}, seed {SEED}, en fazla {args.num_predict} token, düşünme modu {think_note}.",
        f"- Düşünme parametresi reddedilip `think` olmadan tekrarlanan modeller: {', '.join(fallbacks) if fallbacks else 'yok'}.",
        "- Süreler akış tabanlıdır. İlk içerik süresi, isteğin gönderilmesinden yanıt metninin ilk parçasına kadar geçen süredir (düşünen modellerde düşünme süresini içerir); ilk token süresi düşünme parçalarını da sayar. Soğuk yükleme ayrı bir ısınma çağrısıyla ölçülür ve süre istatistiklerine girmez.",
        "- Kesinti dayanıklılığı: biten her yanıt `<çıktı>.partial.jsonl` dosyasına yazılır ve kesilen çalıştırma kaldığı yerden devam eder. "
        f"Önceki çalıştırmadan alınan yanıt sayısı: {', '.join(f'{r.model}: {r.resumed}' for r in chat) if chat else '—'}. "
        "Önbellekten gelen yanıtların süreleri önceki çalıştırmada ölçülmüştür; çalıştırmalar arasında makine yükü farklıysa süreler birebir karşılaştırılabilir olmayabilir.",
        "- Token sınırında kesilen yanıtın içeriği eksik olabilir; bu yanıtlar 'Kesilen yanıt' sütununda ve soru bazında işaretlenir.",
        "- Modeller sırayla çalıştırılır; her aday bitince bellekten atılır (`keep_alive: 0`).",
        "- Anahtar kelime isabeti otomatik ve kaba bir ölçüttür: doğru ama farklı sözcüklerle verilmiş bir yanıtı kaçırabilir. Türkçe yanıt kalitesi için soru bazında yanıtları okuyun.",
        "- 30 soru istatistiksel olarak küçüktür; farklar küçükse sıralamaya aşırı güvenilmemelidir.",
        "- Embedding süreleri (ms/cümle) güvenilir bir hız karşılaştırması değildir: 20 cümlelik iki toplu çağrının ortalamasıdır ve aynı model farklı çalıştırmalarda çok farklı çıkabilir "
        "(P0.4 geliştirme sırasında aynı yapılandırmada embeddinggemma 350 ms, ardından 44 ms ölçüldü). Süre farklarına dayanarak karar verilmemelidir; gerekirse tekrarlı ve ısınmış bir ölçüm yapılmalıdır.",
        "- Bilinen ölçüt zayıflıkları: (1) yasak kelime eşleşmesi doğru bir yanıtta da geçebilir (örneğin 'TLSv1.0 ve TLSv1.1 kapalı' demek ihlal sayılır); bu koşuda ihlal çıkmadığı için sonuca etkisi yoktur. "
        "(2) s06 'test ortamında hangi sertifikalar denenebilir' sorusunun anahtarı ML-DSA'dır (dokümandaki Ayar kataloğu); başka geçerli bir yanıt (örneğin kendinden imzalı sertifika) isabet saymaz. "
        "(3) Sayısal anahtarlar rakam sınırıyla eşleşir (24, 2024 içinde sayılmaz), ancak 'JDK 24.0' gibi ondalık yazımlar isabet sayılabilir.",
        "- Ret uyumu: yanıt, dile uygun ret sabitine harfi harfine eşit olmalıdır (crypto-domain bölüm 4). Kapsam etiketi doğruluğu yanıttaki ilk IN_SCOPE/OUT_OF_SCOPE etiketine bakar; 'yalnızca etiket' sütunu biçime uyumu gösterir.",
        "", "### Harness sistem istemleri (ürün istemi değildir)", "",
        "Bilgi soruları (crypto, springboot; ret talimatı yoktur, D-67):", "", f"> {SYSTEM_PROMPT_KNOWLEDGE}", "",
        "Kapsam dışı sorular (out_of_scope; sabit ret cümleleri):", "", f"> {SYSTEM_PROMPT_REFUSAL}", "",
        "Kapsam kararı (scope_decision):", "", f"> {SYSTEM_PROMPT_SCOPE}", "",
    ]
    lines += render_candidates(chat, embed_reports)
    if chat:
        lines += render_chat_section(chat, dataset)
    if embed_reports:
        lines += render_embed_section(embed_reports)
    return "\n".join(lines).rstrip("\n") + "\n"


# --------------------------------------------------------------------------------------
# Giriş noktası
# --------------------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Yerel sohbet ve embedding modeli seçimi için değerlendirme (P0.4).")
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--chat-models", default=",".join(DEFAULT_CHAT_MODELS), help="virgülle ayrılmış etiketler")
    parser.add_argument("--embed-models", default=",".join(DEFAULT_EMBED_MODELS), help="virgülle ayrılmış etiketler")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--num-predict", type=int, default=3000, help="yanıt başına en fazla token (düşünen modeller için yüksek tutulur, D-66)")
    parser.add_argument("--timeout", type=float, default=300.0, help="istek zaman aşımı (sn)")
    parser.add_argument("--think", choices=("off", "on", "default"), default="default",
                        help="düşünme modu: default (parametre gönderilmez, D-66), on veya off")
    parser.add_argument("--fresh", action="store_true",
                        help="ara dosyayı (<çıktı>.partial.jsonl) yok say ve sil; varsayılan olarak kesilen çalıştırma kaldığı yerden devam eder")
    parser.add_argument("--skip-chat", action="store_true")
    parser.add_argument("--skip-embed", action="store_true")
    args = parser.parse_args(argv)
    args.think = {"off": False, "on": True, "default": None}[args.think]
    return args


def split_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    dataset = load_dataset(Path(args.dataset))
    client = OllamaClient(args.ollama_url, args.timeout)
    try:
        version = client.get_json("/api/version").get("version", "?")
    except OllamaError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = ResultCache(Path(str(output) + ".partial.jsonl"), args.fresh)
    chat = [] if args.skip_chat else [evaluate_chat(client, m, dataset, args.num_predict, args.think, cache) for m in split_models(args.chat_models)]
    embed_reports = [] if args.skip_embed else [evaluate_embedding(client, m) for m in split_models(args.embed_models)]
    output.write_text(render_report(args, version, dataset, chat, embed_reports), encoding="utf-8", newline="\n")
    print(f"Rapor yazıldı: {output}")
    failed = [r.model for r in chat if r.error] + [r.model for r in embed_reports if r.error]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
