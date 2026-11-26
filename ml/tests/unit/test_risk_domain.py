"""The Model A domain: features, metrics, the split check, model selection and the report's H3 verdict."""

from __future__ import annotations

from dataclasses import replace

import pytest

from quancrypt_ml.domain.metrics import agreement, bootstrap_interval, critical_recall, evaluate, macro_f1
from quancrypt_ml.domain.model_a_report import ClassifierCost, ModelAFacts, build_model_card, build_report, h3
from quancrypt_ml.domain.risk_features import FEATURES, MISSING, features, risk_score
from quancrypt_ml.domain.split import CandidateScore, ProjectSplit, best_candidate, leaked_projects, partition
from tests.support.risk_rows import synthetic_rows


def test_features_fill_missing_values_with_zero_and_say_so_with_a_flag() -> None:
    row = replace(synthetic_rows(1)[0], key_size_bits=None, java_major=None, mode=None, spring_boot_version="3.3.1")
    f = features(row)
    assert list(f) == list(FEATURES)
    assert (f["key_size_bits"], f["key_size_known"], f["java_major"], f["java_major_known"]) == (0.0, 0.0, 0.0, 0.0)
    assert f["mode"] == MISSING and f["spring_boot_minor"] == "3.3"
    known = features(replace(row, key_size_bits=2048, java_major=21, spring_boot_version="UNKNOWN"))
    assert (known["key_size_known"], known["java_major_known"], known["spring_boot_minor"]) == (1.0, 1.0, "UNKNOWN")


def test_the_risk_score_is_the_expected_class_score() -> None:
    assert risk_score({"CRITICAL": 1.0}) == 0.9
    assert risk_score({"HIGH": 0.5, "LOW": 0.5}) == round(0.5 * 0.70 + 0.5 * 0.175, 4)


def test_evaluation_of_a_known_example() -> None:
    # truth:     C C H H H M L L
    # predicted: C H H H M M L C
    truth = ["CRITICAL", "CRITICAL", "HIGH", "HIGH", "HIGH", "MEDIUM", "LOW", "LOW"]
    predicted = ["CRITICAL", "HIGH", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW", "CRITICAL"]
    e = evaluate(truth, predicted)
    # CRITICAL: tp 1, predicted 2, support 2 -> P 0.5, R 0.5, F1 0.5; HIGH: tp 2, predicted 3, support 3 -> F1 4/6;
    # MEDIUM: tp 1, predicted 2, support 1 -> F1 2/3; LOW: tp 1, predicted 1, support 2 -> F1 2/3.
    scores = {c.label: c for c in e.per_class}
    assert (scores["CRITICAL"].precision, scores["CRITICAL"].recall) == (0.5, 0.5)
    assert scores["HIGH"].f1 == pytest.approx(4 / 6)
    assert e.macro_f1 == pytest.approx((0.5 + 4 / 6 + 2 / 3 + 2 / 3) / 4)
    assert e.accuracy == 5 / 8
    assert e.confusion[0] == (1, 1, 0, 0)


def test_an_invalid_answer_counts_as_wrong_and_absent_classes_do_not_dilute_macro_f1() -> None:
    e = evaluate(["HIGH", "HIGH", "LOW"], ["HIGH", None, "LOW"])
    assert e.recall("HIGH") == 0.5 and e.recall("CRITICAL") == 0.0
    assert e.macro_f1 == pytest.approx((2 / 3 + 1.0) / 2)  # CRITICAL and MEDIUM have no true record
    with pytest.raises(ValueError, match="one prediction"):
        evaluate(["HIGH"], [])


def test_the_bootstrap_interval_is_deterministic_and_brackets_the_value() -> None:
    truth = ["HIGH", "LOW", "CRITICAL", "HIGH", "MEDIUM", "LOW", "HIGH", "LOW"] * 3
    predicted = ["HIGH", "LOW", "HIGH", "HIGH", "MEDIUM", "LOW", "LOW", "LOW"] * 3
    first = bootstrap_interval(truth, predicted, macro_f1)
    assert first == bootstrap_interval(truth, predicted, macro_f1)
    assert first[0] <= evaluate(truth, predicted).macro_f1 <= first[1]
    assert bootstrap_interval(truth, predicted, critical_recall) == (0.0, 0.0)  # the CRITICAL record is always missed
    other_seed = bootstrap_interval(truth, predicted, macro_f1, seed=7)
    assert other_seed[0] <= evaluate(truth, predicted).macro_f1 <= other_seed[1]


def test_run_agreement_counts_identical_answers_and_kappa_over_valid_ones() -> None:
    result = agreement(["HIGH", "LOW", None, "LOW"], ["HIGH", "LOW", "LOW", "HIGH"])
    assert result.identical == 0.5
    assert result.kappa is not None
    assert agreement(["LOW"], ["LOW"]).identical == 1.0


def test_the_split_check_finds_a_project_on_both_sides_and_an_unknown_project() -> None:
    rows = synthetic_rows(10, projects=2)
    ok = ProjectSplit(frozenset({rows[0].project_key}), frozenset({rows[1].project_key}))
    train, test = partition(rows, ok)
    assert {r.project_key for r in train} & {r.project_key for r in test} == set()
    assert leaked_projects(ProjectSplit(frozenset({"a", "b"}), frozenset({"b"}))) == {"b"}
    with pytest.raises(ValueError, match="does not cover"):
        partition(rows, ProjectSplit(frozenset({rows[0].project_key}), frozenset()))


def test_selection_takes_macro_f1_then_critical_recall_then_the_name() -> None:
    assert best_candidate([CandidateScore("A", 0.7, 0.9), CandidateScore("B", 0.8, 0.1)]).algorithm == "B"
    assert best_candidate([CandidateScore("A", 0.8, 0.5), CandidateScore("B", 0.8, 0.9)]).algorithm == "B"
    assert best_candidate([CandidateScore("B", 0.8, 0.9), CandidateScore("A", 0.8, 0.9)]).algorithm == "A"


def _cost(macro: float) -> ClassifierCost:
    truth = ["HIGH", "LOW", "CRITICAL", "MEDIUM"]
    e = evaluate(truth, truth)
    return ClassifierCost("m", replace(e, macro_f1=macro), (macro, macro), (1.0, 1.0), 0.001, 0.0, None, 0)


def _facts(source: str, model: float, rule: float) -> ModelAFacts:
    return ModelAFacts(
        label_source=source, version="v1", total_rows=10, labelled_rows=10, train_rows=8, test_rows=2, train_projects=4,
        test_projects=1, test_class_counts={"HIGH": 2}, cv=[], selected="XGBOOST", selected_params={"max_depth": 3},
        model=_cost(model), rule=_cost(rule), llm=None, llm_model=None, llm_prompt=None, parity_rows=2,
        parity_classes_equal=True, parity_max_difference=1e-7, top_features=[("onehot__priority_P0", 0.5)],
    )  # fmt: skip


def test_h3_needs_gold_labels_macro_f1_of_080_and_a_better_score_than_the_rule() -> None:
    assert h3(_facts("SILVER", 0.95, 0.5)) is None
    assert h3(_facts("GOLD", 0.85, 0.80)) is True
    assert h3(_facts("GOLD", 0.79, 0.50)) is False
    assert h3(_facts("GOLD", 0.85, 0.85)) is False


def test_the_report_and_card_say_what_kind_of_run_it_was() -> None:
    dry = build_report(_facts("SILVER", 0.95, 0.5))
    assert "Deneme koşusu" in dry and "Ölçülmedi" in dry
    gold = build_report(_facts("GOLD", 0.79, 0.5))
    assert "**TUTMADI.**" in gold and "0.790" in gold
    assert "H3: tutmadı" in build_model_card(_facts("GOLD", 0.79, 0.5))
    assert "`risk_class` en olası sınıftır" in build_model_card(_facts("GOLD", 0.79, 0.5))


def test_the_card_names_the_inference_gap_and_the_occlusion_reasons() -> None:
    card = build_model_card(_facts("SILVER", 0.95, 0.5))
    assert "`~MISSING`, `is_outlier_project` 0 olur (D-343b)" in card
    assert "gerekçe SHAP değildir" in card and "(oklüzyon)" in card
