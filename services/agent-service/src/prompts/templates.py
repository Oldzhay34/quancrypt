"""Few-shot examples, the clarification questions and the LLM-less templates (P4.5, D-249).

The examples map a question to an intent code only (no answer, no technical claim). The clarification questions and
their codes are the core-service V2 seed word for word (a test checks it). The note builders place only the plan item's
own fields (strategy, effort, risk class), never a new claim, so an explanation produced without a knowledge-base hit,
without a model or out of budget still says nothing unsourced (guardrails-security section 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# The intent catalogue (agent-service-layout section 6). `unknown` is the fallback (no example).
INTENTS: tuple[str, ...] = (
    "inventory",
    "risk_priority",
    "algorithm_choice",
    "version_compat",
    "configuration",
    "infrastructure",
    "compat_rollback",
    "performance",
    "cert_token",
    "testing",
    "compliance_timeline",
    "qkd",
    "field_devices",
    "tool_usage",
    "unknown",
)

# The five clarification questions, word for word as the core-service V2 seed (V2__lookup_data.sql); (tr, en).
CLARIFICATION_QUESTIONS: dict[str, tuple[str, str]] = {
    "TLS_TERMINATION": (
        "TLS nerede sonlanıyor: uygulamada mı, ingress'te mi, servis mesh'te mi, yük dengeleyicide mi?",
        "Where does TLS terminate: in the application, at the ingress, in the service mesh or at the load balancer?",
    ),
    "JDK_UPGRADE_POSSIBLE": (
        "Hedef JDK sürümüne yükseltme mümkün mü?",
        "Is upgrading to the target JDK version possible?",
    ),
    "HYBRID_INCAPABLE_PARTNERS": (
        "Hibrit grubu desteklemeyebilecek dış istemciler veya iş ortakları var mı?",
        "Are there external clients or partners that may not support the hybrid group?",
    ),
    "COMPLIANCE_REQUIREMENT": (
        "FIPS, BDDK veya kurum politikası gibi bir uyum gereksinimi var mı?",
        "Is there a compliance requirement such as FIPS, BDDK or an internal policy?",
    ),
    "DEVICE_HARDWARE_OPENSSL": (
        "Saha cihazlarının donanımı ve OpenSSL sürümü nedir?",
        "What is the hardware and OpenSSL version of the field devices?",
    ),
}

# At least one Turkish and one English example per intent (prompt task 7), question -> intent code.
INTENT_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("Projemde hangi şifreleme algoritmaları kullanılıyor?", "inventory"),
    ("What cryptography does my project use?", "inventory"),
    ("Hangi bulguları önce düzeltmeliyim?", "risk_priority"),
    ("Which findings should I fix first?", "risk_priority"),
    ("Hangi post-kuantum algoritmayı seçmeliyim?", "algorithm_choice"),
    ("Which post-quantum algorithm should I choose?", "algorithm_choice"),
    ("JDK sürümüm ML-KEM'i destekliyor mu?", "version_compat"),
    ("Does my JDK version support ML-KEM?", "version_compat"),
    ("TLS ayarlarını nasıl yapılandırırım?", "configuration"),
    ("How do I configure the TLS settings?", "configuration"),
    ("Geçişi altyapıda nasıl dağıtırım?", "infrastructure"),
    ("How do I roll out the migration across the infrastructure?", "infrastructure"),
    ("Geçiş sorun çıkarırsa nasıl geri alırım?", "compat_rollback"),
    ("How do I roll back if the migration breaks something?", "compat_rollback"),
    ("Hibrit anahtar değişiminin başarım etkisi nedir?", "performance"),
    ("What is the performance impact of hybrid key exchange?", "performance"),
    ("Sertifikalarımı ve JWT'lerimi nasıl ele almalıyım?", "cert_token"),
    ("How should I handle my certificates and JWTs?", "cert_token"),
    ("Geçişi nasıl test ederim?", "testing"),
    ("How do I test the migration?", "testing"),
    ("NIST geçiş takvimi nedir?", "compliance_timeline"),
    ("What is the NIST migration timeline?", "compliance_timeline"),
    ("QKD'yi projede kullanabilir miyim?", "qkd"),
    ("Can I use QKD in the project?", "qkd"),
    ("Saha cihazlarımın bağlantısını nasıl korurum?", "field_devices"),
    ("How do I protect my field devices' connections?", "field_devices"),
    ("Quancrypt'i nasıl kullanırım?", "tool_usage"),
    ("How do I use Quancrypt?", "tool_usage"),
)

# Keyword fallback when the model is off or gives no usable code (D-248e); lower-cased whole-word-ish substrings.
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "inventory": (
        "envanter",
        "hangi algoritma",
        "hangi şifreleme",
        "ne kullanıl",
        "inventory",
        "what cryptography",
        "which algorithms",
        "which encryption",
    ),
    "risk_priority": (
        "öncelik",
        "önce düzelt",
        "önce ele",
        "en riskli",
        "priority",
        "fix first",
        "which findings",
        "most risky",
    ),
    "algorithm_choice": (
        "hangi algoritma seç",
        "hangi post-kuantum",
        "hangi pqc",
        "which algorithm",
        "which post-quantum",
        "choose",
    ),
    "version_compat": ("sürüm", "jdk", "spring boot", "version", "support", "compatible", "compatibility"),
    "configuration": ("yapılandır", "ayar", "configure", "configuration", "settings"),
    "infrastructure": ("altyapı", "dağıt", "infrastructure", "roll out", "rollout", "deploy"),
    "compat_rollback": ("geri al", "geri dön", "rollback", "roll back", "revert"),
    "performance": ("başarım", "performans", "performance", "latency", "overhead", "slow"),
    "cert_token": ("sertifika", "token", "jwt", "certificate"),
    "testing": ("test", "doğrula", "testing"),
    "compliance_timeline": ("uyum", "takvim", "nist", "fips", "bddk", "compliance", "timeline", "deadline"),
    "qkd": ("qkd", "kuantum anahtar dağıtım", "quantum key distribution"),
    "field_devices": ("saha cihaz", "field device", "field-device", "pynq"),
    "tool_usage": ("quancrypt nasıl", "nasıl kullan", "how do i use", "how to use", "nasıl çalış"),
}


def match_intent(question: str) -> str:
    """The keyword fallback: the first intent whose keywords the question contains, else `unknown`."""
    lowered = question.casefold()
    for intent in INTENTS:
        if intent == "unknown":
            continue
        if any(keyword in lowered for keyword in INTENT_KEYWORDS.get(intent, ())):
            return intent
    return "unknown"


def few_shot_block() -> str:
    """The examples as `'question' -> intent` lines for the intent prompt."""
    return "\n".join(f"'{text}' -> {intent}" for text, intent in INTENT_EXAMPLES)


# ---- plan-item explanation notes (no new claim: only the item's own fields) ----


def _head(item: Mapping[str, Any], lang: str) -> str:
    if lang == "en":
        return f"Strategy: {item['strategy']} (effort {item['effort']}, risk {item['riskClass']})."
    return f"Strateji: {item['strategy']} (efor {item['effort']}, risk {item['riskClass']})."


def no_source_note(item: Mapping[str, Any], finding: Mapping[str, Any], lang: str) -> str:
    if lang == "en":
        return f"{_head(item, lang)} No knowledge-base source was found for this item; an expert review is advised."
    return f"{_head(item, lang)} Bu madde için bilgi tabanında kaynak bulunamadı; uzman incelemesi önerilir."


def off_note(item: Mapping[str, Any], finding: Mapping[str, Any], lang: str) -> str:
    if lang == "en":
        return f"{_head(item, lang)} [LLM disabled] This note was produced without a language model."
    return f"{_head(item, lang)} [LLM kapalı] Bu not bir dil modeli olmadan üretildi."


def over_budget_note(item: Mapping[str, Any], finding: Mapping[str, Any], lang: str) -> str:
    if lang == "en":
        return f"{_head(item, lang)} The explanation budget was reached; the strategy and effort are above."
    return f"{_head(item, lang)} Açıklama bütçesi doldu; strateji ve efor yukarıdadır."
