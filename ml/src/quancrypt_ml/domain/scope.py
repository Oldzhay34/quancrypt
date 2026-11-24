"""The scope data set of Model B (P7.1, D-32, D-322): its records and the split by paraphrase group.

A paraphrase group (`seed_id`) holds the wordings of one request, in Turkish and English: the whole group goes to one
split, so no wording of a test request is seen in training (leakage). Pure: no I/O."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

IN_SCOPE, OUT_OF_SCOPE = "IN_SCOPE", "OUT_OF_SCOPE"
LABELS = (IN_SCOPE, OUT_OF_SCOPE)
LANGUAGES = ("tr", "en")
SOURCES = ("p44_seed", "synthetic_reviewed")
SPLITS = ("train", "val", "test")
RATIOS = (0.70, 0.15, 0.15)
MINIMUM_RECORDS = 800
MINIMUM_PER_LABEL = 400
MAX_TEXT = 4000  # the request limit of the guard (D-242a)
SEED = 42


@dataclass(frozen=True)
class ScopeRecord:
    id: str
    seed_id: str
    lang: str
    text: str
    label: str
    category: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id, "seed_id": self.seed_id, "lang": self.lang, "text": self.text, "label": self.label,
            "category": self.category, "source": self.source,
        }  # fmt: skip


def problems(records: Sequence[ScopeRecord]) -> list[str]:
    """What is wrong with a data set (empty when it is fine): codes, unique ids and texts, one label per group, size and
    balance (at least 400 per label, the two languages within 10 % of each other)."""
    found: list[str] = []
    ids = Counter(r.id for r in records)
    texts = Counter(r.text.casefold().strip() for r in records)
    found += [f"id {i} appears {n} times" for i, n in ids.items() if n > 1]
    found += [f"a text appears {n} times" for t, n in texts.items() if n > 1 and t]
    for r in records:
        if r.label not in LABELS or r.lang not in LANGUAGES or r.source not in SOURCES:
            found.append(f"{r.id}: label, lang or source is not a known code")
        if not r.text.strip() or len(r.text) > MAX_TEXT:
            found.append(f"{r.id}: the text is empty or longer than {MAX_TEXT} characters")
        if not r.category or not r.seed_id:
            found.append(f"{r.id}: category and seed_id are required")
    labels_of: dict[str, set[str]] = defaultdict(set)
    for r in records:
        labels_of[r.seed_id].add(r.label)
    found += [f"group {g} mixes labels" for g, labels in labels_of.items() if len(labels) > 1]
    per_label = Counter(r.label for r in records)
    if len(records) < MINIMUM_RECORDS:
        found.append(f"{len(records)} records, at least {MINIMUM_RECORDS} are needed")
    found += [f"{label}: {per_label[label]} records, at least {MINIMUM_PER_LABEL}" for label in LABELS
              if per_label[label] < MINIMUM_PER_LABEL]  # fmt: skip
    per_lang = Counter(r.lang for r in records)
    if records and abs(per_lang["tr"] - per_lang["en"]) > 0.1 * len(records):
        found.append("the two languages differ by more than 10 % of the records")
    return found


def split_by_group(
    records: Iterable[ScopeRecord], ratios: Sequence[float] = RATIOS, seed: int = SEED
) -> dict[str, list[ScopeRecord]]:
    """Train, validation and test by paraphrase group, per label (each split keeps the label balance): the groups of a
    label are shuffled with the seed and filled into the splits in order until each reaches its share of records."""
    groups: dict[str, list[ScopeRecord]] = defaultdict(list)
    for record in records:
        groups[record.seed_id].append(record)
    by_label: dict[str, list[str]] = defaultdict(list)
    for seed_id in sorted(groups):
        by_label[groups[seed_id][0].label].append(seed_id)
    rng = random.Random(seed)  # noqa: S311 (a reproducible sample, not cryptography)
    result: dict[str, list[ScopeRecord]] = {name: [] for name in SPLITS}
    for label in sorted(by_label):
        ids = by_label[label]
        rng.shuffle(ids)
        total = sum(len(groups[g]) for g in ids)
        targets = [ratio * total for ratio in ratios]
        filled = [0, 0, 0]
        split = 0
        for seed_id in ids:
            while split < len(SPLITS) - 1 and filled[split] >= targets[split]:
                split += 1
            result[SPLITS[split]].extend(groups[seed_id])
            filled[split] += len(groups[seed_id])
    return {name: sorted(rows, key=lambda r: r.id) for name, rows in result.items()}


def leaked_groups(splits: Mapping[str, Sequence[ScopeRecord]]) -> set[str]:
    """Paraphrase groups that appear in more than one split (must be empty)."""
    seen: dict[str, set[str]] = defaultdict(set)
    for name, rows in splits.items():
        for row in rows:
            seen[row.seed_id].add(name)
    return {group for group, names in seen.items() if len(names) > 1}


def review_sample(records: Sequence[ScopeRecord], fraction: float = 0.10, seed: int = SEED) -> list[ScopeRecord]:
    """What the user reviews (D-322): a random tenth of the data set and every boundary case."""
    rng = random.Random(seed)  # noqa: S311 (a reproducible sample, not cryptography)
    pool = sorted(records, key=lambda r: r.id)
    sample = {r.id: r for r in rng.sample(pool, max(1, round(fraction * len(pool))))}
    sample.update({r.id: r for r in pool if r.category.startswith("boundary")})
    return sorted(sample.values(), key=lambda r: r.id)
