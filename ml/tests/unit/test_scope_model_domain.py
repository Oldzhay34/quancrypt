"""Model B's domain: the threshold, the UNSURE band, the slices, the pick rule, H4 and the report (P7.3, D-332)."""

from __future__ import annotations

import math

import pytest

from quancrypt_ml.domain.model_b_report import AlgorithmSummary, ModelBFacts, build_model_card, build_report, h4
from quancrypt_ml.domain.scope import IN_SCOPE, OUT_OF_SCOPE
from quancrypt_ml.domain.scope_model import (
    ALL,
    ALLOW,
    DENY,
    EN,
    JAILBREAK,
    TR,
    UNSURE,
    Band,
    BinaryScore,
    Candidate,
    Scored,
    binary,
    breakdown,
    decide,
    h4_met,
    pick,
    roc_auc,
    select_threshold,
    three_way,
    unsure_band,
)


def _set(out: list[float], inside: list[float]) -> list[Scored]:
    return [Scored(OUT_OF_SCOPE, "tr", "general", p) for p in out] + [Scored(IN_SCOPE, "en", "risk", p) for p in inside]


def test_the_threshold_keeps_the_recall_and_rejects_the_fewest_and_ties_go_lower() -> None:
    # 50 out-of-scope requests: 98 % recall allows one miss (49/50); the lowest one (0.10) may be missed.
    out = [0.10] + [0.60 + 0.005 * i for i in range(49)]
    inside = [0.05, 0.20, 0.30, 0.65]
    t = select_threshold(_set(out, inside))
    score = binary(_set(out, inside), t)
    assert score.recall is not None and score.recall >= 0.98
    assert t == 0.60  # above 0.30 (no false reject but 0.65), the lowest such threshold
    assert score.false_rejects == 1


def test_without_slack_the_threshold_catches_every_out_of_scope_request() -> None:
    out, inside = [0.4, 0.7, 0.9], [0.1, 0.5]
    t = select_threshold(_set(out, inside))
    assert t == 0.4 and binary(_set(out, inside), t).recall == 1.0
    with pytest.raises(ValueError, match="no out-of-scope"):
        select_threshold(_set([], inside))


def test_the_band_allows_no_validation_out_of_scope_request_and_denies_no_in_scope_one() -> None:
    validation = _set([0.4, 0.7, 0.9], [0.1, 0.5])
    band = unsure_band(validation, 0.4)
    assert band.low == 0.4 and band.high == math.nextafter(0.5, math.inf) and band.threshold == 0.4
    decisions = {(s.label, decide(s.p_out, band)) for s in validation}
    assert (OUT_OF_SCOPE, ALLOW) not in decisions and (IN_SCOPE, DENY) not in decisions
    assert decide(0.45, band) == UNSURE and decide(0.95, band) == DENY and decide(0.05, band) == ALLOW


def test_the_band_keeps_its_order_around_the_threshold() -> None:
    separated = _set([0.8, 0.9], [0.1, 0.2])
    band = unsure_band(separated, 0.8)
    assert band.low <= band.threshold <= band.high
    assert band.high == 0.8  # the highest in-scope score is below the threshold
    assert three_way(separated, band).unsure_rate == 0.0


def test_three_way_counts_and_slices() -> None:
    scored = [
        Scored(OUT_OF_SCOPE, "tr", "jailbreak", 0.9), Scored(OUT_OF_SCOPE, "en", "general", 0.3),
        Scored(IN_SCOPE, "tr", "boundary", 0.6), Scored(IN_SCOPE, "en", "risk", 0.1),
    ]  # fmt: skip
    t = three_way(scored, Band(0.2, 0.5, 0.7))
    assert (t.allowed_out, t.unsure_out, t.denied_out, t.allowed_in, t.unsure_in, t.denied_in) == (0, 1, 1, 1, 1, 0)
    assert t.unsure_rate == 0.5
    slices = breakdown(scored, 0.5)
    assert slices[ALL] == BinaryScore(2, 2, 1, 1)
    assert slices[TR] == BinaryScore(1, 1, 1, 1) and slices[EN] == BinaryScore(1, 1, 0, 0)
    assert slices[JAILBREAK].false_reject_rate is None and slices[JAILBREAK].recall == 1.0


def test_roc_auc_counts_ties_as_half() -> None:
    assert roc_auc(_set([0.9, 0.5], [0.5, 0.1])) == pytest.approx(0.875)
    assert roc_auc(_set([0.9], [])) is None


def test_the_svm_needs_more_than_one_fewer_false_reject() -> None:
    lr = Candidate("LOGISTIC_REGRESSION", 0.5, BinaryScore(68, 64, 67, 5))
    assert pick(lr, Candidate("LINEAR_SVM", 0.4, BinaryScore(68, 64, 67, 4))) is lr
    svm = Candidate("LINEAR_SVM", 0.4, BinaryScore(68, 64, 67, 3))
    assert pick(lr, svm) is svm


def test_h4_needs_both_conditions() -> None:
    assert h4_met(BinaryScore(60, 57, 59, 2))  # 98.3 %, 3.5 %
    assert not h4_met(BinaryScore(60, 57, 58, 0))  # 96.7 % recall
    assert not h4_met(BinaryScore(60, 57, 60, 3))  # 5.3 % false rejects


def _facts(test: BinaryScore) -> ModelBFacts:
    scores = dict.fromkeys(("ALL", "TR", "EN", "JAILBREAK", "BOUNDARY"), test)
    counts = {
        s: {"OUT_OF_SCOPE": 60, "IN_SCOPE": 57, "tr": 59, "en": 58, "jailbreak": 2} for s in ("train", "val", "test")
    }
    summary = AlgorithmSummary("LOGISTIC_REGRESSION", {"C": 1.0}, 0.97, 0.01, 0.42, test, 0.98)
    t = three_way(_set([0.9], [0.1]), Band(0.2, 0.42, 0.6))
    return ModelBFacts(
        "v1", "embeddinggemma:latest", "sha256:abc", 768, counts, [summary], "LOGISTIC_REGRESSION",
        Band(0.2, 0.42, 0.6), scores, t, scores, t, 0.99, True, 1e-7, "scope_classifier-v1.onnx",
        "scope_classifier-v1.thresholds.json",
    )  # fmt: skip


def test_the_report_and_card_name_the_embedding_model_and_the_h4_verdict() -> None:
    met = _facts(BinaryScore(60, 57, 59, 2))
    report, card = build_report(met), build_model_card(met)
    assert h4(met) and "H4 **TUTTU.**" in report and "Türkçe" in report and "Jailbreak" in report
    assert "`embeddinggemma:latest`" in card and "sha256:abc" in card and "H4: tuttu" in card
    assert "P7.5" in report  # the rule-filter baseline (D-332d)
    missed = build_report(_facts(BinaryScore(60, 57, 60, 4)))
    assert "H4 **TUTMADI.**" in missed and "bir bulgudur" in missed
