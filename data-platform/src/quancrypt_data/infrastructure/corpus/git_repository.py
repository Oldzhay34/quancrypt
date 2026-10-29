"""The git adapter: a shallow clone of a repository's default branch, with nothing of the repository ever run
(D-298)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess  # noqa: S404 (the only process this adapter starts is git, with a fixed argument list)
import tempfile
from pathlib import Path

from quancrypt_data.domain.corpus import RepoRef
from quancrypt_data.port.outbound.corpus import CloneError, CloneResult

# One clone may take at most this much disk (a chosen value, not a measurement); the run-wide limit is checked by
# the use case.
MAX_CLONE_BYTES = 2 * 1024**3


class SubprocessGitRepository:
    """`git clone --depth 1` with every way for the repository to run something switched off:

    - no hooks: the clone is made with an empty template (no sample hooks are copied) and `core.hooksPath` points
      nowhere;
    - only `allowed_protocol` may be used (https; a test passes `file`), so the address cannot select another
      transport;
    - submodules are not fetched, symlinks are checked out as plain files (`core.symlinks=false`), no tags;
    - git never asks a question (`GIT_TERMINAL_PROMPT=0`) and reads no system or user configuration.

    The clone is removed again when it fails. Nothing from the clone is executed afterwards either: the analyzer only
    reads it."""

    def __init__(
        self,
        corpus_root: Path,
        timeout_s: int,
        allowed_protocol: str = "https",
        max_clone_bytes: int = MAX_CLONE_BYTES,
    ) -> None:
        self._root = corpus_root
        self._timeout_s = timeout_s
        self._protocol = allowed_protocol
        self._max_clone_bytes = max_clone_bytes

    def clone(self, repo: RepoRef) -> CloneResult:
        return self.clone_url(repo.url, repo.dir_name)

    def clone_url(self, url: str, dir_name: str) -> CloneResult:
        target = self._root / dir_name
        self._root.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise CloneError("the target directory already exists")
        command = [
            "git",
            "-c", "core.hooksPath=" + os.devnull,
            "-c", "core.symlinks=false",
            "-c", "core.fsmonitor=false",
            "-c", "protocol.allow=never",
            "-c", f"protocol.{self._protocol}.allow=always",
            "clone", "--depth", "1", "--single-branch", "--no-tags", "--no-recurse-submodules", "--template=",
            "--", url, str(target),
        ]  # fmt: skip
        try:
            with tempfile.TemporaryDirectory(prefix="quancrypt-git-home-") as home:
                self._run(command, home, self._timeout_s)
                if _size(target) > self._max_clone_bytes:
                    raise OSError("the clone is larger than the limit of one clone")
                sha = self._run(["git", "-C", str(target), "rev-parse", "HEAD"], home, 60)
                branch = self._run(["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"], home, 60)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            shutil.rmtree(target, ignore_errors=True)
            raise CloneError(f"git clone failed ({type(exc).__name__})") from None
        return CloneResult(commit_sha=sha, default_branch=branch)

    def _run(self, command: list[str], home: str, timeout_s: int) -> str:
        """Runs git in a process group of its own and kills the whole group on a timeout: `git-remote-https` and
        `index-pack`
        are children of git and would otherwise go on writing into a directory that is being removed."""
        process = subprocess.Popen(  # noqa: S603
            command,
            env=self._environment(home),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            out, _ = process.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, "git")
        return out.strip()

    @staticmethod
    def _environment(home: str) -> dict[str, str]:
        # An empty home: libcurl then finds no ~/.netrc, and git no user configuration, whatever the user has.
        return {
            "PATH": os.environ.get("PATH", ""),
            "HOME": home,
            "LC_ALL": "C",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }


def _size(directory: Path) -> int:
    total = 0
    for current, _, names in os.walk(directory, followlinks=False):
        for name in names:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                continue
    return total
