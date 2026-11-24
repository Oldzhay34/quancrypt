"""SplitScopeDataset (P7.1, D-32): the scope data set is checked, split by paraphrase group (70/15/15, no group in two
splits) and written with the review sample; the test split is copied to agent-service (ml/ is its only source)."""

from __future__ import annotations

from collections import Counter

from quancrypt_ml.domain.scope import SPLITS, leaked_groups, problems, review_sample, split_by_group
from quancrypt_ml.port.inbound.scope import ScopeSplitError, SplitCommand, SplitResult
from quancrypt_ml.port.outbound.scope import ScopeDatasetError, ScopeDatasetFiles


class SplitScopeDatasetService:
    def __init__(self, files: ScopeDatasetFiles) -> None:
        self._files = files

    def execute(self, command: SplitCommand) -> SplitResult:
        try:
            records = self._files.read(command.dataset)
        except ScopeDatasetError as error:
            raise ScopeSplitError((str(error),)) from None
        found = problems(records)
        if found:
            raise ScopeSplitError(tuple(found))
        splits = split_by_group(records, seed=command.seed)
        leaked = leaked_groups(splits)
        if leaked:
            raise ScopeSplitError(tuple(f"group {g} is in more than one split" for g in sorted(leaked)))
        for name in SPLITS:
            self._files.write(command.output_dir / f"{name}.jsonl", splits[name])
        sample = review_sample(records, seed=command.seed)
        self._files.write(command.output_dir / "review_sample.jsonl", sample)
        self._files.write(command.test_copy, splits["test"])
        return SplitResult(
            records=len(records),
            groups=len({r.seed_id for r in records}),
            counts={name: dict(Counter(r.label for r in rows)) for name, rows in splits.items()},
            review_sample=len(sample),
        )
