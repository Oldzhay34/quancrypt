"""ZeroShotClassifier over the local Ollama (P7.2, D-327c): fixed prompt, temperature 0, fixed seed, one finding per
call. Loopback only, no proxy, no redirect (guardrails-security section 1; the same host Ollama of D-51)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.risk_features import RiskRow
from quancrypt_ml.infrastructure.llm.prompts import FIELDS, PROMPT_VERSION, SYSTEM
from quancrypt_ml.port.outbound.risk import ZeroShotAnswer, ZeroShotUnavailableError

SEED = 42


def finding_text(row: RiskRow) -> str:
    values: dict[str, Any] = {name: getattr(row, name) for name in FIELDS}
    return "Finding:\n" + "\n".join(
        f"- {name}: {'unknown' if value is None else value}" for name, value in values.items()
    )


def parse(answer: str) -> str | None:
    """The class word of an answer, or None: the stripped answer must be exactly one of the four classes."""
    word = answer.strip().strip(".").upper()
    return word if word in RISK_CLASSES else None


class OllamaZeroShotClassifier:
    def __init__(
        self, base_url: str, model: str, timeout_s: float = 120.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url=base_url, timeout=timeout_s, trust_env=False, follow_redirects=False, transport=transport
        )

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    def classify(self, row: RiskRow) -> ZeroShotAnswer:
        body = {
            "model": self._model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": finding_text(row)}],
            "stream": False,
            "options": {"temperature": 0, "seed": SEED, "num_predict": 8},
        }
        started = time.perf_counter()
        try:
            response = self._client.post("/api/chat", json=body)
        except httpx.HTTPError:
            raise ZeroShotUnavailableError("the local LLM cannot be reached") from None
        seconds = time.perf_counter() - started
        if response.status_code != 200:
            raise ZeroShotUnavailableError(f"the local LLM answered {response.status_code}")
        try:
            data = response.json()
            content = str(data["message"]["content"])
        except (ValueError, KeyError, TypeError):
            raise ZeroShotUnavailableError("the local LLM answer is not a chat message") from None
        return ZeroShotAnswer(
            label=parse(content),
            seconds=seconds,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
        )
