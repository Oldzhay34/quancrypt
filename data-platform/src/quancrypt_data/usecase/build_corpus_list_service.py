from __future__ import annotations

from quancrypt_data.domain.corpus import SelectionPolicy
from quancrypt_data.port.inbound.corpus import BuildCorpusListCommand, BuildCorpusListResult, BuildCorpusListUseCase
from quancrypt_data.port.outbound.corpus import CorpusListStore, DatasetReader


class BuildCorpusListService(BuildCorpusListUseCase):
    """Reads the dataset and writes the corpus list: the candidates the dataset does not rule out, a seeded sample of
    them (D-25, D-298). What the dataset does not say is verified after cloning."""

    def __init__(self, reader: DatasetReader, store: CorpusListStore, policy: SelectionPolicy) -> None:
        self._reader = reader
        self._store = store
        self._policy = policy

    def execute(self, command: BuildCorpusListCommand) -> BuildCorpusListResult:
        candidates = self._reader.read(command.dataset)
        selected, turned_away = self._policy.select(candidates, command.size)
        self._store.write(selected)
        return BuildCorpusListResult(
            candidates=len(candidates),
            selected=len(selected),
            turned_away={rule.value: count for rule, count in sorted(turned_away.items())},
        )
