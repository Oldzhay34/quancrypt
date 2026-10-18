"""Domain errors: what is wrong with the directory the user pointed at."""

from __future__ import annotations


class NotAProjectError(Exception):
    """The root holds none of pom.xml, build.gradle or build.gradle.kts."""


class AmbiguousProjectError(Exception):
    """The root holds both a Maven and a Gradle build file; the project type cannot be told."""


class InvalidSessionTokenError(ValueError):
    """The text is not a session token (32 random bytes, base64url without padding)."""
