"""The project the CLI sets up: how its type is recognised and what is remembered about it (FR-01)."""

from __future__ import annotations

import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from quancrypt_cli.domain.errors import AmbiguousProjectError, NotAProjectError

MAVEN_FILES = ("pom.xml",)
GRADLE_FILES = ("build.gradle", "build.gradle.kts")
# core-service accepts a display name of 1 to 200 characters (contracts/openapi/core-service.yaml, ProjectRegistration).
MAX_DISPLAY_NAME = 200


class ProjectKind(Enum):
    MAVEN = "maven"
    GRADLE = "gradle"


def detect_kind(entries: Collection[str]) -> ProjectKind:
    """The project type from the names in the root directory; both build systems at once is ambiguous (D-178h)."""
    maven = any(name in entries for name in MAVEN_FILES)
    gradle = any(name in entries for name in GRADLE_FILES)
    if maven and gradle:
        raise AmbiguousProjectError
    if maven:
        return ProjectKind.MAVEN
    if gradle:
        return ProjectKind.GRADLE
    raise NotAProjectError


def display_name(directory_name: str) -> str:
    """The short name core-service shows for the project: the directory name without control characters (a terminal
    escape in a folder name must not reach the screen), never empty and at most 200 characters."""
    printable = "".join(c for c in directory_name if unicodedata.category(c) not in {"Cc", "Cf", "Cs", "Zl", "Zp"})
    return printable[:MAX_DISPLAY_NAME] or "project"


@dataclass(frozen=True)
class ProjectConfig:
    """What `.quancrypt/config.yaml` keeps (D-273: it survives a second `init`)."""

    name: str
    kind: ProjectKind
    created_at: datetime
    quancrypt_version: str
