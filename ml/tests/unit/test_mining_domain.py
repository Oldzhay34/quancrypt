"""The mining domain with hand-computed examples (P7.4, D-338)."""

from __future__ import annotations

import math

from quancrypt_ml.domain import mining
from quancrypt_ml.domain.mining import AnomalyScore, ProjectLibraries, Rule, RuleThresholds
from tests.support.mining_fakes import corpus, key, profile


def test_the_matrix_holds_the_shares_that_occur_and_the_log_density() -> None:
    matrix = mining.feature_matrix(
        [profile(1, {"RSA": 1.0, "AES": 0.0}, {"SIGNATURE": 1.0}, per_unit=3.0)]
        + [profile(2, {"RSA": 0.5, "UNKNOWN": 0.5}, {"HASH": 1.0}, per_unit=0.0)]
    )
    assert matrix.columns == (
        "share_alg_RSA", "share_alg_UNKNOWN", "share_ctx_HASH", "share_ctx_SIGNATURE", "log1p_findings_per_unit",
    )  # fmt: skip
    assert matrix.keys == tuple(sorted((key(1), key(2)))) and matrix.shares == 4
    rows = dict(zip(matrix.keys, matrix.rows, strict=True))
    assert rows[key(1)] == (1.0, 0.0, 0.0, 1.0, math.log1p(3.0))
    assert rows[key(2)] == (0.5, 0.5, 1.0, 0.0, 0.0)


def test_k_is_the_best_silhouette_and_the_elbow_is_the_bend() -> None:
    assert mining.best_k({2: 0.4, 3: 0.6, 4: 0.6}) == 3
    assert mining.elbow_k({2: 100.0, 3: 30.0, 4: 25.0, 5: 22.0}) == 3
    assert mining.elbow_k({2: 5.0, 3: 4.0}) == 2
    assert list(mining.candidate_ks(4)) == [2, 3] and list(mining.candidate_ks(30)) == [2, 3, 4, 5, 6, 7, 8]


def test_clusters_are_numbered_by_size_and_noise_has_none() -> None:
    assert mining.number_clusters([5, 2, 2, -1, 2, 5]) == [2, 1, 1, None, 1, 2]


def test_an_archetype_is_named_from_its_centre_and_equal_names_are_numbered() -> None:
    profiles = corpus()[:8]
    numbers = {p.project_key: 1 if i < 4 else 2 for i, p in enumerate(profiles)}
    first, second = mining.archetypes(profiles, numbers)
    assert (first.name, first.size) == ("RSA / TOKEN_SIGNATURE, birim başına 2.025 bulgu", 4)
    assert second.name == "UNKNOWN / TLS_KEY_EXCHANGE, birim başına 3.065 bulgu"
    assert "birim başına ortalama 3.065 bulgu" in second.rationale
    assert "4 proje" in first.rationale and "%100" in first.rationale
    alike = [profile(i, {"RSA": 1.0}, {"TOKEN_SIGNATURE": 1.0}, 2.0) for i in range(1, 5)]
    same = mining.archetypes(alike, {p.project_key: 1 + i % 2 for i, p in enumerate(alike)})
    named = "RSA / TOKEN_SIGNATURE, birim başına 2.000 bulgu"
    assert [a.name for a in same] == [named, f"{named} (2)"]


def test_items_leave_out_the_unknown_family_and_missing_libraries() -> None:
    project = ProjectLibraries(key(1), [("jjwt", "RSA"), (None, "AES"), ("JSSE", "UNKNOWN")])
    assert mining.transaction(project) == {"lib:jjwt", "lib:JSSE", "alg:RSA", "alg:AES"}


def test_rules_meet_every_threshold_strongest_first() -> None:
    thresholds = RuleThresholds(min_support_projects=3, min_confidence=0.6)
    strong = Rule(("lib:a",), ("alg:RSA",), 0.3, 0.9, 2.0)
    exact = Rule(("lib:b",), ("alg:RSA",), 0.3, 0.6, 1.5)
    rules = [
        exact, strong,
        Rule(("lib:c",), ("alg:RSA",), 0.2, 0.9, 2.0),  # two projects of ten
        Rule(("lib:d",), ("alg:RSA",), 0.3, 0.5, 2.0),  # confidence
        Rule(("lib:e",), ("alg:RSA",), 0.3, 0.9, 1.0),  # lift not above one
    ]  # fmt: skip
    assert mining.keep_rules(rules, thresholds, 10) == [strong, exact]
    assert mining.keep_rules(rules, thresholds, 0) == []
    # two projects cannot give a support of three, however often the rule holds in them (D-337e)
    assert mining.keep_rules([Rule(("lib:a",), ("alg:RSA",), 1.0, 1.0, 2.0)], thresholds, 2) == []


def test_the_queue_is_the_flagged_projects_most_unusual_first() -> None:
    scores = [AnomalyScore("b", -0.1, True), AnomalyScore("a", 0.2, False), AnomalyScore("c", -0.3, True)]
    assert [s.project_key for s in mining.review_queue(scores)] == ["c", "b"]


def test_the_plan_proposal_follows_the_priority_table() -> None:
    odd = profile(
        1, {"RSA": 1.0}, {"TOKEN_SIGNATURE": 0.4, "ENCRYPTION": 0.3, "TLS_KEY_EXCHANGE": 0.3}, 1.0,
        {"P0": 0.1, "P1": 0.5, "P2": 0.0, "P3": 0.4},
    )  # fmt: skip
    (archetype,) = mining.archetypes([odd], {odd.project_key: 1})
    assert mining.plan_template(archetype) == [
        ("P0", "FIX_WEAK_CLASSIC"), ("P1", "HYBRID_TLS_KEX"), ("P1", "KEM_DEM_ENCRYPTION"),
        ("P3", "KEEP_SHORT_LIVED_TOKEN"),
    ]  # fmt: skip


def test_the_data_digest_follows_the_data_not_the_order() -> None:
    profiles = corpus()
    assert mining.data_digest(profiles) == mining.data_digest(list(reversed(profiles)))
    assert mining.data_digest(profiles) != mining.data_digest(profiles[:-1])


def test_key_agreement_and_keystores_have_their_strategy_in_the_proposal() -> None:
    odd = profile(
        1, {"ECDH": 1.0}, {"KEY_AGREEMENT": 0.5, "KEYSTORE": 0.5}, 1.0, {"P0": 0.0, "P1": 0.5, "P2": 0.0, "P3": 0.5}
    )
    (archetype,) = mining.archetypes([odd], {odd.project_key: 1})
    assert mining.plan_template(archetype) == [("P1", "KEM_DEM_ENCRYPTION"), ("P3", "HYBRID_KEX_CLASSIC_CERT")]
