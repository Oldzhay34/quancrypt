from __future__ import annotations

import logging
from dataclasses import replace

from quancrypt_data.domain.corpus import (
    MAX_UNIT_DEPTH,
    MAX_UNIT_DIRECTORIES,
    CloneStatus,
    Eligibility,
    ExclusionReason,
    ManifestEntry,
    RepoRef,
)
from quancrypt_data.domain.licenses import identify_license
from quancrypt_data.port.inbound.corpus import CloneCorpusCommand, CloneCorpusResult, CloneCorpusUseCase
from quancrypt_data.port.outbound.corpus import CloneError, CorpusFiles, CorpusListStore, GitRepository, ManifestStore

_LOG = logging.getLogger("quancrypt_data.usecase")


class CloneCorpusService(CloneCorpusUseCase):
    """Clones the listed projects (a window of the list) and keeps only those that pass the checks made on the clone: an
    allowed license read from the LICENSE text, a Spring Boot dependency and at least three service directories.

    A project that is already cloned (or already excluded) is skipped. The corpus root is measured before every clone
    and the run stops when it is at the disk limit (D-298d). A project that fails a check is removed from disk and the
    reason is kept in the manifest."""

    def __init__(
        self, listing: CorpusListStore, manifest: ManifestStore, git: GitRepository, files: CorpusFiles
    ) -> None:
        self._listing = listing
        self._manifest = manifest
        self._git = git
        self._files = files

    def execute(self, command: CloneCorpusCommand) -> CloneCorpusResult:
        window = self._listing.read()[command.offset : command.offset + command.limit]
        entries = dict(self._manifest.load())
        attempted = cloned = already = failed = 0
        excluded: dict[str, int] = {}
        stopped = False
        for repo in window:
            entry = entries.get(repo.canonical, ManifestEntry(repo_url=repo.url))
            if entry.status is CloneStatus.EXCLUDED or (
                entry.status is CloneStatus.CLONED and self._files.exists(repo.dir_name)
            ):
                already += 1
                entries[repo.canonical] = entry
                continue
            if self._files.size_bytes() >= command.max_disk_bytes:
                stopped = True
                break
            attempted += 1
            outcome = self._clone_and_check(repo, entry)
            entries[repo.canonical] = outcome
            if outcome.status is CloneStatus.CLONED:
                cloned += 1
            elif outcome.status is CloneStatus.FAILED:
                failed += 1
            elif outcome.exclusion_reason is not None:
                excluded[outcome.exclusion_reason.value] = excluded.get(outcome.exclusion_reason.value, 0) + 1
            self._manifest.save(entries)
        self._manifest.save(entries)
        return CloneCorpusResult(
            attempted=attempted,
            cloned=cloned,
            already_there=already,
            excluded=dict(sorted(excluded.items())),
            failed=failed,
            stopped_by_disk_limit=stopped,
            disk_bytes=self._files.size_bytes(),
        )

    def _clone_and_check(self, repo: RepoRef, entry: ManifestEntry) -> ManifestEntry:
        try:
            cloned = self._git.clone(repo)
        except CloneError:
            _LOG.warning("a repository could not be cloned")
            return replace(entry, status=CloneStatus.FAILED, exclusion_reason=ExclusionReason.CLONE_FAILED)
        text = self._files.read_license(repo.dir_name)
        checks = Eligibility(
            license_spdx=identify_license(text) if text is not None else None,
            has_spring_boot=self._files.has_spring_boot(repo.dir_name),
            service_directories=len(
                self._files.service_directories(repo.dir_name, MAX_UNIT_DEPTH, MAX_UNIT_DIRECTORIES)
            ),
        )
        reason = checks.exclusion()
        if reason is not None:
            self._files.remove(repo.dir_name)
            return replace(
                entry,
                status=CloneStatus.EXCLUDED,
                exclusion_reason=reason,
                commit_sha=cloned.commit_sha,
                license_verified=checks.license_spdx,
            )
        return replace(
            entry,
            status=CloneStatus.CLONED,
            exclusion_reason=None,
            commit_sha=cloned.commit_sha,
            license_verified=checks.license_spdx,
        )
