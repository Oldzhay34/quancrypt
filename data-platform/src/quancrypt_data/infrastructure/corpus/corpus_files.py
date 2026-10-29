"""The corpus root on disk: reads license and build files of a clone, measures the root and removes a clone.

Nothing here follows a symbolic link or runs anything: files are read as bytes of text, directories are walked with
`lstat`. A name is only accepted when it is a plain directory name below the corpus root (the `<owner>__<name>` of a
clone, or `_benchmarks/<name>`), so no call can reach outside it."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterator, Sequence
from pathlib import Path

from quancrypt_data.domain.corpus import is_valid_benchmark_name

_CLONE_DIR = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}__[a-z0-9][a-z0-9._-]{0,99}$")
_BENCHMARK_DIR = "_benchmarks"
_LICENSE_NAMES = (
    "license",
    "license.md",
    "license.txt",
    "licence",
    "licence.md",
    "licence.txt",
    "copying",
    "copying.md",
)
_BUILD_FILES = frozenset({"pom.xml", "build.gradle", "build.gradle.kts"})
# Directories that are never services of the project.
_SKIPPED = frozenset({".git", "node_modules", "target", "build", "out", "src", ".gradle", ".idea"})
MAX_LICENSE_BYTES = 200 * 1024
MAX_BUILD_FILE_BYTES = 2 * 1024 * 1024


class LocalCorpusFiles:
    def __init__(self, corpus_root: Path) -> None:
        self._root = corpus_root

    def exists(self, dir_name: str) -> bool:
        return self._directory(dir_name).is_dir()

    def read_license(self, dir_name: str) -> str | None:
        directory = self._directory(dir_name)
        for entry in sorted(_children(directory), key=lambda p: p.name):
            if entry.name.casefold() in _LICENSE_NAMES and _is_plain_file(entry):
                return _read_head(entry, MAX_LICENSE_BYTES)
        return None

    def has_spring_boot(self, dir_name: str) -> bool:
        directory = self._directory(dir_name)
        candidates = [directory, *(directory / d for d in self._service_dirs(directory, 2, 200))]
        for candidate in candidates:
            for build_file in sorted(_BUILD_FILES):
                path = candidate / build_file
                if _is_plain_file(path) and "spring-boot" in _read_head(path, MAX_BUILD_FILE_BYTES).casefold():
                    return True
        return False

    def service_directories(self, dir_name: str, max_depth: int, limit: int) -> Sequence[str]:
        return self._service_dirs(self._directory(dir_name), max_depth, limit)

    def size_bytes(self) -> int:
        total = 0
        # `os.walk` does not enter symbolic links to directories and `lstat` sizes a link as the link itself.
        for current, _, names in os.walk(self._root, followlinks=False):
            for name in names:
                try:
                    total += os.lstat(os.path.join(current, name)).st_size
                except OSError:
                    continue
        return total

    def remove(self, dir_name: str) -> None:
        target = self._directory(dir_name)
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)

    def copy_benchmark(self, source: Path, name: str) -> str:
        if not is_valid_benchmark_name(name):
            raise ValueError("the benchmark code is not valid")
        destination = self._root / _BENCHMARK_DIR / name
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # `.git` is not needed to analyse code; symbolic links are copied as the files they point to or not at all.
        # Links are copied as links (`symlinks=True`), never followed: a link of a downloaded tree must not pull a
        # file or a
        # directory from elsewhere into the corpus root (the analyzer refuses a link when it reads the copy).
        shutil.copytree(
            source, destination, symlinks=True, ignore=shutil.ignore_patterns(".git"), ignore_dangling_symlinks=True
        )
        return f"{_BENCHMARK_DIR}/{name}"

    def _directory(self, dir_name: str) -> Path:
        parts = dir_name.split("/")
        valid_clone = len(parts) == 1 and _CLONE_DIR.fullmatch(dir_name) is not None
        valid_benchmark = len(parts) == 2 and parts[0] == _BENCHMARK_DIR and is_valid_benchmark_name(parts[1])
        if not (valid_clone or valid_benchmark):
            raise ValueError("not a directory of the corpus root")
        return self._root.joinpath(*parts)

    def _service_dirs(self, directory: Path, max_depth: int, limit: int) -> list[str]:
        found: list[str] = []

        def visit(current: Path, depth: int, prefix: str) -> None:
            if depth > max_depth or len(found) >= limit:
                return
            for child in sorted(_children(current), key=lambda p: p.name):
                if len(found) >= limit:
                    return
                if child.name in _SKIPPED or child.name.startswith(".") or not _is_plain_dir(child):
                    continue
                relative = f"{prefix}{child.name}"
                if any(_is_plain_file(child / build_file) for build_file in _BUILD_FILES):
                    found.append(relative)
                visit(child, depth + 1, relative + "/")

        visit(directory, 1, "")
        return found


def _read_head(path: Path, limit: int) -> str:
    """The first `limit` bytes of a file as text; the rest is never read into memory."""
    with path.open("rb") as stream:
        return stream.read(limit).decode("utf-8", errors="replace")


def _children(directory: Path) -> Iterator[Path]:
    try:
        yield from directory.iterdir()
    except OSError:
        return


def _is_plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _is_plain_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()
