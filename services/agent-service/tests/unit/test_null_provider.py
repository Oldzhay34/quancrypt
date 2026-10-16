from __future__ import annotations

import pytest

from src.llm.null_provider import LLM_DISABLED_NOTE, NullProvider
from src.llm.provider import ChatMessage, GenerationRequest, LLMUnavailableError

REQUEST = GenerationRequest(messages=(ChatMessage("user", "explain"),))


def test_generate_returns_the_fixed_note_and_marks_it() -> None:
    result = NullProvider().generate(REQUEST)

    assert result.text == LLM_DISABLED_NOTE
    assert result.llm_disabled is True
    assert result.usage.prompt_tokens == 0
    assert result.usage.completion_tokens == 0


def test_the_note_names_the_missing_model_in_both_languages() -> None:
    assert "LLM kapalı" in LLM_DISABLED_NOTE
    assert "LLM disabled" in LLM_DISABLED_NOTE


def test_stream_yields_the_note_then_a_final_marked_chunk() -> None:
    chunks = list(NullProvider().stream(REQUEST))

    assert [c.text for c in chunks] == [LLM_DISABLED_NOTE, ""]
    assert chunks[-1].done is True
    assert all(c.llm_disabled for c in chunks)


def test_embedding_is_unavailable_and_status_is_disabled() -> None:
    provider = NullProvider()

    with pytest.raises(LLMUnavailableError):
        provider.embed(["text"])
    assert provider.status() == "disabled"
