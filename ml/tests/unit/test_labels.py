"""The label domain: the stratified sample, the check of a filled-in batch and Cohen's kappa."""

from __future__ import annotations

from collections import Counter

import pytest

from quancrypt_ml.domain.labels import (
    FIRST,
    SECOND,
    Candidate,
    agreement,
    check_labels,
    check_resolutions,
    cohen_kappa,
    stratified_sample,
)
from tests.support.fakes import candidate


def _pool() -> list[Candidate]:
    rows = [candidate(n, "RSA", "ENCRYPTION") for n in range(200)]
    rows += [candidate(200 + n, "ECDSA", "SIGNATURE") for n in range(100)]
    rows += [candidate(300 + n, "SHA1", "SIGNATURE", priority="P0") for n in range(40)]
    rows += [candidate(340 + n, "RSA", "ENCRYPTION", test=True) for n in range(60)]
    return rows


def test_the_sample_has_the_asked_size_and_double_marks_inside_it() -> None:
    sample = stratified_sample(_pool(), 300, 60, 42)
    assert len(sample) == 300
    assert len({s.candidate.finding_id for s in sample}) == 300
    assert sum(s.double_label for s in sample) == 60


def test_the_same_seed_gives_the_same_sample_and_another_seed_another() -> None:
    first = [(s.candidate.finding_id, s.double_label) for s in stratified_sample(_pool(), 300, 60, 42)]
    again = [(s.candidate.finding_id, s.double_label) for s in stratified_sample(list(reversed(_pool())), 300, 60, 42)]
    other = [(s.candidate.finding_id, s.double_label) for s in stratified_sample(_pool(), 300, 60, 7)]
    assert first == again
    assert first != other


def test_every_stratum_keeps_its_share_of_the_population() -> None:
    sample = stratified_sample(_pool(), 300, 60, 42)
    counts = Counter(s.candidate.stratum for s in sample)
    # 400 candidates -> 300: every stratum is cut to three quarters (200, 100, 40, 60 -> 150, 75, 30, 45).
    assert counts[("RSA", "ENCRYPTION", "CORPUS", False)] == 150
    assert counts[("ECDSA", "SIGNATURE", "CORPUS", False)] == 75
    assert counts[("SHA1", "SIGNATURE", "CORPUS", False)] == 30
    assert counts[("RSA", "ENCRYPTION", "CORPUS", True)] == 45
    doubles = Counter(s.candidate.stratum for s in sample if s.double_label)
    assert sum(doubles.values()) == 60
    assert doubles[("RSA", "ENCRYPTION", "CORPUS", False)] == 30


def test_a_small_pool_is_sampled_whole() -> None:
    sample = stratified_sample([candidate(n) for n in range(12)], 300, 60, 42)
    assert len(sample) == 12
    assert sum(s.double_label for s in sample) == 12


def _batch() -> dict[str, bool]:
    return {"a": True, "b": False, "c": True}


def _row(finding: str, label: str = "HIGH", labeler: str = "olcay", notes: str = "") -> dict[str, str]:
    return {"finding_id": finding, "label": label, "labeler": labeler, "notes": notes}


def test_a_complete_valid_batch_is_accepted_and_labels_are_normalised() -> None:
    records, problems = check_labels([_row("a", "high"), _row("b", " LOW "), _row("c", "Critical")], _batch(), FIRST)
    assert problems == []
    assert [(r.finding_id, r.label) for r in records] == [("a", "HIGH"), ("b", "LOW"), ("c", "CRITICAL")]


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (_row("zzz"), "finding_id is not in the batch"),
        (_row("a", "SEVERE"), "label must be one of CRITICAL, HIGH, MEDIUM, LOW"),
        (_row("a", ""), "label must be one of CRITICAL, HIGH, MEDIUM, LOW"),
        (_row("a", labeler=""), "labeler is required (at most 64 characters)"),
        (_row("a", labeler="x" * 65), "labeler is required (at most 64 characters)"),
        (_row("a", notes="n" * 501), "notes has at most 500 characters"),
    ],
)
def test_an_invalid_row_is_named_by_its_line(row: dict[str, str], reason: str) -> None:
    _, problems = check_labels([row, _row("b"), _row("c")], _batch(), FIRST)
    assert (problems[0].row, problems[0].reason) == (2, reason)


def test_a_duplicate_and_a_missing_record_are_problems() -> None:
    _, problems = check_labels([_row("a"), _row("a")], _batch(), FIRST)
    reasons = [p.reason for p in problems]
    assert "finding_id appears twice" in reasons
    assert "2 records of the batch have no valid label" in reasons


def test_the_second_labeller_labels_only_the_marked_records() -> None:
    records, problems = check_labels([_row("a"), _row("c")], _batch(), SECOND)
    assert problems == [] and len(records) == 2
    _, problems = check_labels([_row("a"), _row("b"), _row("c")], _batch(), SECOND)
    assert [p.reason for p in problems] == ["the second labeller labels only the double-label records"]


def test_kappa_of_a_known_two_class_example() -> None:
    # 50 records: both say yes 20, first yes second no 5, first no second yes 10, both no 15.
    # p_o = 35/50 = 0.7; p_e = (25*30 + 25*20) / 2500 = 0.5; kappa = (0.7 - 0.5) / 0.5 = 0.4.
    first = ["HIGH"] * 25 + ["LOW"] * 25
    second = ["HIGH"] * 20 + ["LOW"] * 5 + ["HIGH"] * 10 + ["LOW"] * 15
    assert cohen_kappa(first, second) == pytest.approx(0.4)


def test_kappa_of_a_known_four_class_example() -> None:
    # Hand-computed: 10 records, 7 agreements; marginals A (C3 H3 M2 L2), B (C2 H4 M2 L2).
    # p_o = 0.7; p_e = (3*2 + 3*4 + 2*2 + 2*2) / 100 = 0.26; kappa = 0.44 / 0.74.
    a = ["CRITICAL", "CRITICAL", "CRITICAL", "HIGH", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW", "LOW"]
    b = ["CRITICAL", "CRITICAL", "HIGH", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "HIGH", "LOW", "LOW"]
    assert cohen_kappa(a, b) == pytest.approx(0.44 / 0.74)


def test_kappa_of_perfect_and_of_single_class_agreement() -> None:
    assert cohen_kappa(["HIGH", "LOW"], ["HIGH", "LOW"]) == 1.0
    assert cohen_kappa(["LOW", "LOW"], ["LOW", "LOW"]) == 1.0
    with pytest.raises(ValueError, match="non-empty"):
        cohen_kappa([], [])


def test_agreement_lists_the_disagreements_of_the_common_records() -> None:
    result = agreement({"a": "HIGH", "b": "LOW", "c": "MEDIUM"}, {"a": "HIGH", "b": "MEDIUM", "x": "LOW"})
    assert result.pairs == 2
    assert result.disagreements == (("b", "LOW", "MEDIUM"),)
    assert result.observed == 0.5


def test_resolutions_only_for_disagreements_and_empty_rows_wait() -> None:
    rows = [
        {"finding_id": "b", "label": "medium", "resolved_by": "olcay", "notes": ""},
        {"finding_id": "c", "label": "", "resolved_by": "", "notes": ""},
        {"finding_id": "a", "label": "HIGH", "resolved_by": "olcay", "notes": ""},
    ]
    resolutions, problems = check_resolutions(rows, {"b": ("LOW", "MEDIUM"), "c": ("HIGH", "LOW")})
    assert [(r.finding_id, r.label) for r in resolutions] == [("b", "MEDIUM")]
    assert [(p.row, p.reason) for p in problems] == [(4, "finding_id is not a disagreement of the batch")]
    _, problems = check_resolutions([{"finding_id": "b", "label": "LOW", "resolved_by": ""}], {"b": ("LOW", "HIGH")})
    assert problems[0].reason.startswith("resolved_by is required")
