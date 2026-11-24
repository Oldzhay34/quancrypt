"""The scope data set: its checks, the split by paraphrase group, and the data set file itself (P7.1 acceptance 2)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from quancrypt_ml.domain.scope import (
    IN_SCOPE,
    OUT_OF_SCOPE,
    ScopeRecord,
    leaked_groups,
    problems,
    review_sample,
    split_by_group,
)

ML = Path(__file__).resolve().parents[2]
DATASET = ML / "data" / "scope" / "scope_dataset.jsonl"
SEED_SET = ML.parent / "services" / "agent-service" / "data" / "examples" / "scope_set_seed.jsonl"
AGENT_TEST_SET = ML.parent / "services" / "agent-service" / "data" / "examples" / "scope_set.jsonl"


def _records(path: Path) -> list[ScopeRecord]:
    return [ScopeRecord(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _synthetic(groups: int, label: str) -> list[ScopeRecord]:
    return [
        ScopeRecord(
            f"{label}-{g}-{i}",
            f"{label}-{g}",
            ("tr", "en")[i % 2],
            f"{label} {g} {i}",
            label,
            "c",
            "synthetic_reviewed",
        )  # fmt: skip
        for g in range(groups)
        for i in range(4)
    ]


def test_no_group_is_in_two_splits_and_the_shares_are_near_70_15_15() -> None:
    records = _synthetic(60, IN_SCOPE) + _synthetic(60, OUT_OF_SCOPE)
    splits = split_by_group(records)
    assert leaked_groups(splits) == set()
    assert sum(len(rows) for rows in splits.values()) == len(records)
    shares = {name: len(rows) / len(records) for name, rows in splits.items()}
    assert shares["train"] == pytest.approx(0.70, abs=0.03)
    assert shares["val"] == pytest.approx(0.15, abs=0.03)
    assert shares["test"] == pytest.approx(0.15, abs=0.03)
    for rows in splits.values():
        labels = Counter(r.label for r in rows)
        assert abs(labels[IN_SCOPE] - labels[OUT_OF_SCOPE]) <= 4  # one group of each label at most


def test_the_split_is_deterministic_for_a_seed() -> None:
    records = _synthetic(30, IN_SCOPE) + _synthetic(30, OUT_OF_SCOPE)
    assert split_by_group(records, seed=42) == split_by_group(list(reversed(records)), seed=42)
    assert split_by_group(records, seed=42) != split_by_group(records, seed=1)


def test_leaked_groups_names_a_group_found_in_two_splits() -> None:
    a = ScopeRecord("1", "g", "tr", "x", IN_SCOPE, "c", "synthetic_reviewed")
    b = ScopeRecord("2", "g", "en", "y", IN_SCOPE, "c", "synthetic_reviewed")
    assert leaked_groups({"train": [a], "test": [b]}) == {"g"}


def test_problems_name_duplicates_mixed_groups_codes_and_size() -> None:
    rows = [
        ScopeRecord("1", "g", "tr", "Aynı metin", IN_SCOPE, "c", "synthetic_reviewed"),
        ScopeRecord("1", "g", "en", "aynı metin ", OUT_OF_SCOPE, "c", "synthetic_reviewed"),
        ScopeRecord("3", "h", "de", "other", "MAYBE", "", "web"),
    ]
    found = problems(rows)
    assert "id 1 appears 2 times" in found
    assert "a text appears 2 times" in found
    assert "group g mixes labels" in found
    assert "3: label, lang or source is not a known code" in found
    assert "3: category and seed_id are required" in found
    assert "3 records, at least 800 are needed" in found


def test_the_review_sample_has_a_tenth_and_every_boundary_case() -> None:
    records = _synthetic(25, IN_SCOPE) + [
        ScopeRecord(f"b{i}", f"b{i}", "tr", f"sınır {i}", OUT_OF_SCOPE, "boundary", "synthetic_reviewed")
        for i in range(5)
    ]
    sample = review_sample(records)
    assert {r.id for r in records if r.category == "boundary"} <= {r.id for r in sample}
    assert len(sample) >= round(0.1 * len(records))


# ------------------------------------------------------------------ the data set file (P7.1 acceptance 2)


def test_the_data_set_is_valid_large_balanced_and_bilingual() -> None:
    records = _records(DATASET)
    assert problems(records) == []
    labels = Counter(r.label for r in records)
    assert len(records) >= 800 and labels[IN_SCOPE] >= 400 and labels[OUT_OF_SCOPE] >= 400
    for label in (IN_SCOPE, OUT_OF_SCOPE):
        langs = Counter(r.lang for r in records if r.label == label)
        assert abs(langs["tr"] - langs["en"]) <= 0.05 * labels[label]
    assert {"jailbreak", "boundary", "attack"} <= {r.category for r in records}


def test_the_data_set_holds_the_approved_p44_seed_set_unchanged() -> None:
    seeds = [json.loads(line) for line in SEED_SET.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {r.id: r for r in _records(DATASET)}
    for seed in seeds:
        record = by_id[seed["id"]]
        assert (record.text, record.label, record.lang, record.source) == (
            seed["text"], seed["expected"], seed["language"], "p44_seed",
        )  # fmt: skip


def test_the_written_splits_do_not_leak_and_the_agent_test_set_is_the_test_split() -> None:
    splits = {name: _records(DATASET.parent / f"{name}.jsonl") for name in ("train", "val", "test")}
    assert leaked_groups(splits) == set()
    assert sum(len(rows) for rows in splits.values()) == len(_records(DATASET))
    assert splits == split_by_group(_records(DATASET))
    assert AGENT_TEST_SET.read_text(encoding="utf-8") == (DATASET.parent / "test.jsonl").read_text(encoding="utf-8")
