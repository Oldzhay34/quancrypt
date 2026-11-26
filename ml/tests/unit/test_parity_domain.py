"""domain.parity (P7.5, D-346c): the parity file name and the round-robin choice of its rows."""

from __future__ import annotations

from pathlib import Path

from quancrypt_ml.domain.parity import balanced_rows, parity_path


def test_the_parity_file_sits_beside_the_model() -> None:
    assert parity_path(Path("models/risk_model-v1.onnx")) == Path("models/risk_model-v1.parity.json")


def test_rows_are_taken_round_robin_over_the_answers_and_come_back_sorted() -> None:
    answers = ["A", "A", "A", "A", "B", "C", "A", "B"]
    assert balanced_rows(answers, 4) == [0, 1, 4, 5]  # A, B, C, then A again
    assert balanced_rows(answers, 100) == list(range(len(answers)))
    assert balanced_rows(answers, 0) == [] and balanced_rows([], 5) == []


def test_every_answer_present_is_kept_when_the_limit_allows() -> None:
    answers = ["ALLOW"] * 30 + ["UNSURE"] * 5 + ["DENY"]
    chosen = balanced_rows(answers, 20)
    assert len(chosen) == 20 and {answers[i] for i in chosen} == {"ALLOW", "UNSURE", "DENY"}
